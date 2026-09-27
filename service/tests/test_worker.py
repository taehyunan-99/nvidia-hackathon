"""Worker ownership and lifecycle against a disposable PostgreSQL database."""

from __future__ import annotations

import os
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from service.db import connect, migrate
from service.operational import create_app
from service.tests.test_operational import review
from service.worker import LEASE, claim, cleanup_sessions, finish, heartbeat, process_one, reap, _mock_output

DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def service(tmp_path):
    if not DSN:
        pytest.skip("TEST_DATABASE_URL required")
    migrate(DSN)
    with connect(DSN) as conn:
        conn.execute("TRUNCATE runs, uploads, reviews, sessions, request_budget CASCADE")
    with TestClient(create_app(DSN, tmp_path)) as client:
        yield client, tmp_path


def _run(client):
    review_id = review(client)
    response = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "worker-test"})
    assert response.status_code == 202
    return response.json()["run_id"]


def test_packaged_mock_scenarios_match_contract_fixtures():
    root = Path(__file__).resolve().parents[2]
    source = json.loads((root / "docs/frontend-hosting/fixtures/scenarios.json").read_text())
    packaged = json.loads((root / "service/mock_scenarios.json").read_text())
    assert packaged["scenarios"] == [
        item for item in source["scenarios"] if item["name"] in {"completed", "scientific-hold", "partial", "failed"}
    ]


@pytest.mark.parametrize("scenario,expected,result", [
    ("completed", "completed", True),
    ("scientific-hold", "completed", True),
    ("partial", "partial", True),
    ("failed", "failed", False),
])
def test_mock_scenarios_persist_across_api_restart(service, scenario, expected, result):
    client, root = service
    run_id = _run(client)
    assert process_one(DSN, scenario, data_root=root) == run_id
    restarted = TestClient(create_app(DSN, root))
    restarted.cookies.update(client.cookies)
    run = restarted.get(f"/api/runs/{run_id}").json()
    assert run["status"] == expected
    assert run["result_available"] is result
    if run["error"] is not None:
        assert run["error"]["run_id"] == run_id
        assert run["error"]["candidate_id"] in [c["candidate_id"] for c in run["candidates"]]
    response = restarted.get(f"/api/runs/{run_id}/result")
    assert response.status_code == (200 if result else 409)
    if result:
        assert response.json()["data_mode"] == "mock"
        assert response.json()["candidate_ids"] == [c["candidate_id"] for c in run["candidates"]]
        assert all(item["measurement_state"] != "measured" for item in response.json()["evidence"])


def test_separate_worker_process_handles_saved_run(service):
    client, root = service
    run_id = _run(client)
    completed = subprocess.run(
        [sys.executable, "-m", "service.worker", "--scenario", "scientific-hold", "--once"],
        env={**os.environ, "DATABASE_URL": DSN, "SERVICE_DATA_ROOT": str(root)},
        capture_output=True, text=True, timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "completed"
    assert client.get(f"/api/runs/{run_id}/result").status_code == 200


def test_only_current_unexpired_owner_can_finish(service):
    client, _ = service
    run_id = _run(client)
    job = claim(DSN, "owner-1")
    assert job["id"] == run_id
    assert claim(DSN, "owner-2") is None
    assert not heartbeat(DSN, run_id, "owner-2")
    state, result = _mock_output(job["state"], job["input"], "completed")
    assert not finish(DSN, run_id, "owner-2", state, result)
    with connect(DSN) as conn:
        conn.execute("UPDATE runs SET lease_until = %s WHERE id = %s", (datetime.now(timezone.utc) - timedelta(seconds=1), run_id))
    assert not finish(DSN, run_id, "owner-1", state, result)
    assert reap(DSN) == 1
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "interrupted"
    assert client.get(f"/api/runs/{run_id}/result").status_code == 409
    assert process_one(DSN) is None


def test_session_expiry_blocks_finish_and_cleans_upload(service):
    client, root = service
    run_id = _run(client)
    job = claim(DSN, "owner")
    with connect(DSN) as conn:
        conn.execute("UPDATE sessions SET expires_at = %s", (datetime.now(timezone.utc) - timedelta(seconds=1),))
    state, result = _mock_output(job["state"], job["input"], "completed")
    assert not heartbeat(DSN, run_id, "owner")
    assert not finish(DSN, run_id, "owner", state, result)
    assert cleanup_sessions(DSN, root) == 0
    with connect(DSN) as conn:
        conn.execute("UPDATE runs SET lease_until = %s WHERE id = %s", (datetime.now(timezone.utc) - LEASE, run_id))
    assert reap(DSN) == 1
    assert cleanup_sessions(DSN, root) == 1
    assert client.get(f"/api/runs/{run_id}").status_code == 410
    with connect(DSN) as conn:
        assert conn.execute("SELECT cleaned_at FROM sessions").fetchone()["cleaned_at"] is not None


def test_delete_waits_for_lease_then_removes_file(service):
    client, root = service
    run_id = _run(client)
    job = claim(DSN, "owner")
    upload = root / "uploads" / "sample" / "structure.cif"
    upload.parent.mkdir(parents=True)
    upload.write_text("mock file")
    with connect(DSN) as conn:
        review_id = conn.execute("SELECT review_id FROM runs WHERE id = %s", (run_id,)).fetchone()["review_id"]
        conn.execute(
            "INSERT INTO uploads(id, review_id, upload_key, relative_path, sha256, size_bytes) VALUES (%s, %s, %s, %s, %s, %s)",
            ("upload-test", review_id, "sample", "uploads/sample/structure.cif", "0" * 64, 9),
        )
    assert client.delete("/api/session").status_code == 202
    assert cleanup_sessions(DSN, root) == 0
    assert upload.exists()
    state, result = _mock_output(job["state"], job["input"], "completed")
    assert not finish(DSN, run_id, "owner", state, result)
    with connect(DSN) as conn:
        conn.execute("UPDATE runs SET lease_until = %s WHERE id = %s", (datetime.now(timezone.utc) - LEASE, run_id))
    assert reap(DSN) == 1
    assert cleanup_sessions(DSN, root) == 1
    assert not upload.exists()
    with connect(DSN) as conn:
        assert conn.execute("SELECT status FROM sessions").fetchone()["status"] == "deleted"


def test_cleanup_failure_retries_without_blocking_other_sessions(service, monkeypatch):
    import shutil
    client, root = service
    first = _run(client)
    path = root / "runs" / first
    path.mkdir(parents=True)
    (path / "request.json").write_text("private input")
    client.delete("/api/session")
    second = _run(client)
    client.delete("/api/session")
    real = shutil.rmtree

    def fail_first(target):
        if target == path:
            raise PermissionError("injected")
        return real(target)

    with monkeypatch.context() as patch:
        patch.setattr("service.worker.shutil.rmtree", fail_first)
        assert cleanup_sessions(DSN, root) == 1
    assert path.exists()
    with connect(DSN) as conn:
        assert conn.execute("SELECT count(*) AS n FROM sessions WHERE cleaned_at IS NULL").fetchone()["n"] == 1
        assert conn.execute("SELECT id FROM runs").fetchone()["id"] == first
    assert cleanup_sessions(DSN, root) == 1
    assert not path.exists()
    with connect(DSN) as conn:
        for table in ("reviews", "runs", "uploads", "artifact_files"):
            assert conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
