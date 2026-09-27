"""Persisted analysis against the real public structures and an isolated database."""

from __future__ import annotations

import os
import json
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from service.db import connect, migrate
from service.demo_input import experimental_demo, prediction_demo
from service.live import request_for_job, run_process, verified_files
from service.operational import create_app
from service.tests.test_operational import review
from service.worker import claim, cleanup_sessions, heartbeat, process_one, reap

DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def live_service(tmp_path: Path, monkeypatch):
    if not DSN:
        pytest.skip("TEST_DATABASE_URL required")
    migrate(DSN)
    with connect(DSN) as conn:
        conn.execute("TRUNCATE runs, uploads, reviews, sessions CASCADE")
    monkeypatch.setenv("LOGIC_AGENT_MODE", "rule")
    with TestClient(create_app(DSN, tmp_path, mode="live")) as client:
        yield client, tmp_path


def test_public_structure_run_persists_progress_result_and_private_files(live_service):
    client, root = live_service
    assert client.get("/api/config").json() == {"schema_version": "0.1.0", "data_mode": "live"}
    client.post("/api/session")
    data = json.loads(Path("docs/frontend-hosting/fixtures/public-reference-input.json").read_text())
    accepted = client.post("/api/reviews", data={"metadata": json.dumps(data)})
    assert accepted.status_code == 201, accepted.text
    review_id = accepted.json()["review_id"]
    assert client.get(f"/api/reviews/{review_id}").json()["example_id"] == "her2-public-reference-v1"
    response = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "live-public"})
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert process_one(DSN, data_root=root, mode="live") == run_id
    restarted = TestClient(create_app(DSN, root, mode="live"))
    restarted.cookies.update(client.cookies)
    state = restarted.get(f"/api/runs/{run_id}").json()
    assert state["status"] == "completed", state
    assert state["result_available"]
    events = state["activity_events"]
    assert events and all(event["activity"]["kind"] in {"stage", "skill"} for event in events)
    assert len([e for e in events if e["activity"]["kind"] == "skill" and e["activity"]["phase"] == "skipped"]) == 2
    for candidate in state["candidates"]:
        assert any(event["candidate_id"] == candidate["candidate_id"] and event["step_id"] == "reporting"
                   and event["activity"]["phase"] == "completed" for event in events)
    assert [candidate["status"] for candidate in state["candidates"]] == ["completed", "completed"]
    assert all(any(step["status"] == "completed" for step in candidate["steps"]) for candidate in state["candidates"])
    result = restarted.get(f"/api/runs/{run_id}/result").json()
    assert result["data_mode"] == "live"
    assert result["candidate_ids"] == [candidate["candidate_id"] for candidate in state["candidates"]]
    ready = [artifact for artifact in result["artifacts"] if artifact["status"] == "ready"]
    assert len(ready) == 2
    for artifact in ready:
        path = f"/api/runs/{run_id}/artifacts/{artifact['artifact_id']}"
        assert len(restarted.get(path).content) == artifact["size_bytes"]
        assert restarted.get(f"/api/runs/another-run/artifacts/{artifact['artifact_id']}").status_code == 404
    second = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "live-public-again"}).json()["run_id"]
    assert process_one(DSN, data_root=root, mode="live") == second
    assert restarted.get(f"/api/runs/{second}/artifacts/{ready[0]['artifact_id']}").status_code == 200
    assert restarted.get(f"/api/runs/{run_id}/artifacts/{ready[0]['artifact_id']}").status_code == 200
    assert restarted.get(f"/api/artifacts/{ready[0]['artifact_id']}").status_code == 404
    stranger = TestClient(create_app(DSN, root, mode="live"))
    stranger.post("/api/session")
    assert stranger.get(f"/api/runs/{run_id}/artifacts/{ready[0]['artifact_id']}").status_code == 404
    assert not list(root.glob("runs/*/call_log.jsonl")), "offline subprocess must not load local API credentials"


def test_direct_input_uses_same_saved_live_result(live_service):
    client, root = live_service
    client.post("/api/session")
    body = experimental_demo()
    body["example_id"] = None
    for index, candidate in enumerate(body["candidates"], 1):
        candidate["candidate_id"] = f"candidate-{index}"
        candidate["name"] = f"직접 입력 후보 {index}"
        candidate["sources"] = []
    accepted = client.post("/api/reviews", data={"metadata": json.dumps(body)})
    assert accepted.status_code == 201, accepted.text
    review_id = accepted.json()["review_id"]
    run_id = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "direct-input"}).json()["run_id"]
    assert process_one(DSN, data_root=root, mode="live") == run_id
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"
    result = client.get(f"/api/runs/{run_id}/result").json()
    assert result["candidate_ids"] == ["candidate-1", "candidate-2"]
    assert client.get(f"/api/reviews/{review_id}").json()["target"] == body["target"]


def test_live_claim_limits_active_runs_globally(live_service):
    client, _ = live_service
    first = review(client)
    second = client.post("/api/reviews", data={"metadata": json.dumps(experimental_demo())}).json()["review_id"]
    for index, review_id in enumerate((first, second)):
        assert client.post(f"/api/reviews/{review_id}/runs", json={"request_key": f"claim-{index}"}).status_code == 202
    first_job = claim(DSN, "worker-one", "live")
    assert first_job is not None
    assert claim(DSN, "worker-two", "live") is None


def test_uploaded_structure_is_verified_before_analysis(live_service):
    client, root = live_service
    client.post("/api/session")
    body = experimental_demo()
    body["uploads"] = [{"upload_key": "structure_a", "file_name": "1N8Z.cif", "format": "mmcif",
                        "candidate_id": body["candidates"][0]["candidate_id"], "role": "complex",
                        "source": {"title": "RCSB PDB 1N8Z", "url": "https://www.rcsb.org/structure/1N8Z", "record_id": "1N8Z"}}]
    content = Path("frontend/public/structures/1N8Z.cif").read_bytes()
    accepted = client.post("/api/reviews", data={"metadata": json.dumps(body)}, files={"structure_a": ("1N8Z.cif", content)})
    assert accepted.status_code == 201, accepted.text
    review_id = accepted.json()["review_id"]
    run_id = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "upload"}).json()["run_id"]
    job = claim(DSN, "owner", "live")
    assert job["id"] == run_id
    request = request_for_job(DSN, job, root)
    assert len(request["uploads"]) == 1
    path = Path(request["uploads"][0]["path"])
    assert path.read_bytes() == content
    path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="무결성"):
        request_for_job(DSN, job, root)


def test_expired_live_session_interrupts_and_removes_run_files(live_service):
    client, root = live_service
    review_id = review(client)
    run_id = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "expire-live"}).json()["run_id"]
    assert claim(DSN, "owner", "live")["id"] == run_id
    work_dir = root / "runs" / run_id
    work_dir.mkdir(parents=True)
    (work_dir / "request.json").write_text("test")
    with connect(DSN) as conn:
        conn.execute("UPDATE sessions SET expires_at = %s", (datetime.now(timezone.utc) - timedelta(seconds=1),))
        conn.execute("UPDATE runs SET lease_until = %s WHERE id = %s", (datetime.now(timezone.utc) - timedelta(seconds=1), run_id))
    assert not heartbeat(DSN, run_id, "owner")
    assert reap(DSN) == 1
    assert cleanup_sessions(DSN, root) == 1
    assert not work_dir.exists()
    with connect(DSN) as conn:
        assert conn.execute("SELECT state_json FROM runs WHERE id = %s", (run_id,)).fetchone()["state_json"]["status"] == "interrupted"
    assert client.get(f"/api/runs/{run_id}").status_code == 410


def test_predicted_file_must_match_hash_and_stay_in_work_dir(tmp_path):
    work_dir = tmp_path / "run"
    work_dir.mkdir()
    content = b"data_predicted\n"
    path = work_dir / "structure.cif"
    path.write_bytes(content)
    artifact = {"artifact_id": "af-structure", "status": "ready", "file_name": path.name,
                "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    output = {"result": {"artifacts": [artifact], "structures": [{"artifact_id": "af-structure", "kind": "predicted"}]}, "files": []}
    assert verified_files(output, work_dir)[0][2] == content
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="무결성"):
        verified_files(output, work_dir)
    outside = tmp_path / "outside.cif"
    outside.write_bytes(content)
    output["files"] = [{"artifact_id": "af-structure", "path": str(outside)}]
    with pytest.raises(ValueError, match="밖"):
        verified_files(output, work_dir)


def test_lost_lease_terminates_analysis_process(tmp_path, monkeypatch):
    class Process:
        returncode = None
        terminated = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True

        def wait(self, timeout=None):
            self.returncode = -15

    process = Process()
    monkeypatch.setattr("service.live.subprocess.Popen", lambda *args, **kwargs: process)
    with pytest.raises(InterruptedError):
        run_process({"work_dir": str(tmp_path), "run_id": "run-test"}, lambda update: None, lambda: False)
    assert process.terminated


@pytest.mark.skipif(os.getenv("RUN_LIVE_PERSISTED") != "1", reason="actual NVIDIA calls require RUN_LIVE_PERSISTED=1")
def test_nat_prediction_is_saved_with_its_file(live_service, monkeypatch):
    client, root = live_service
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    client.post("/api/session")
    response = client.post("/api/reviews", data={"metadata": json.dumps(prediction_demo())})
    assert response.status_code == 201, response.text
    review_id = response.json()["review_id"]
    run_id = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "live-prediction"}).json()["run_id"]
    assert process_one(DSN, data_root=root, mode="live") == run_id
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["result_available"], state
    result = client.get(f"/api/runs/{run_id}/result").json()
    predicted = [item for item in result["structures"] if item["kind"] == "predicted"]
    assert predicted, result["opinions"]
    artifact = next(item for item in result["artifacts"] if item["artifact_id"] == predicted[0]["artifact_id"])
    assert client.get(f"/api/runs/{run_id}/artifacts/{artifact['artifact_id']}").status_code == 200
