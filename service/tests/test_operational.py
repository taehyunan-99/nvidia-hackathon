"""Persistent intake, ownership, and idempotency against a disposable PostgreSQL DB."""

from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from psycopg.types.json import Jsonb

import pytest
from fastapi.testclient import TestClient

from service.db import connect, migrate
from service.demo_input import experimental_demo
from service.operational import COOKIE_NAME, create_app

DSN = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture
def client(tmp_path):
    if not DSN:
        pytest.skip("TEST_DATABASE_URL required for PostgreSQL integration tests")
    migrate(DSN)
    with connect(DSN) as conn:
        conn.execute("TRUNCATE runs, uploads, reviews, sessions, request_budget CASCADE")
    with TestClient(create_app(DSN, tmp_path)) as api:
        yield api


def review(client):
    assert client.post("/api/session").status_code == 201
    response = client.post("/api/reviews", data={"metadata": json.dumps(experimental_demo())})
    assert response.status_code == 201, response.text
    return response.json()["review_id"]


def test_session_cookie_heartbeat_expiry_and_delete(client):
    response = client.post("/api/session")
    assert response.status_code == 201
    assert response.json()["status"] == "active"
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()
    assert COOKIE_NAME not in response.text
    first_expiry = response.json()["expires_at"]
    renewed = client.post("/api/session/heartbeat")
    assert renewed.status_code == 200
    assert renewed.json()["expires_at"] >= first_expiry
    assert client.delete("/api/session").json()["status"] == "deleting"
    assert client.post("/api/session/heartbeat").status_code == 401


def test_expired_session_cannot_be_revived(client):
    client.post("/api/session")
    token = client.cookies.get(COOKIE_NAME)
    with connect(DSN) as conn:
        conn.execute("UPDATE sessions SET expires_at = %s", (datetime.now(timezone.utc) - timedelta(seconds=1),))
    assert client.post("/api/session/heartbeat").json()["code"] == "SESSION_EXPIRED"
    assert client.post("/api/session/heartbeat").status_code == 410
    assert client.cookies.get(COOKIE_NAME) == token


def test_run_is_idempotent_private_and_survives_app_recreation(client, tmp_path):
    review_id = review(client)
    path = f"/api/reviews/{review_id}/runs"
    first = client.post(path, json={"request_key": "one"})
    assert first.status_code == 202, first.text
    second = client.post(path, json={"request_key": "one"})
    assert second.json()["run_id"] == first.json()["run_id"]
    assert first.json()["status"] == "queued"
    assert client.get(f"/api/runs/{first.json()['run_id']}/result").json()["code"] == "RESULT_NOT_READY"
    with connect(DSN) as conn:
        assert conn.execute("SELECT count(*) AS n FROM runs").fetchone()["n"] == 1
    restarted = TestClient(create_app(DSN, tmp_path))
    restarted.cookies.set(COOKIE_NAME, client.cookies.get(COOKIE_NAME))
    assert restarted.get(f"/api/runs/{first.json()['run_id']}").json() == first.json()
    stranger = TestClient(create_app(DSN, tmp_path))
    stranger.post("/api/session")
    assert stranger.post(path, json={"request_key": "one"}).status_code == 404
    assert stranger.get(f"/api/runs/{first.json()['run_id']}").status_code == 404
    assert stranger.get(f"/api/runs/{first.json()['run_id']}/result").status_code == 404
    assert stranger.get("/api/artifacts/unknown").status_code == 404


def test_saved_input_is_private_and_matches_the_run(client, tmp_path):
    review_id = review(client)
    response = client.get(f"/api/reviews/{review_id}")
    assert response.status_code == 200
    assert response.json()["candidates"] == experimental_demo()["candidates"]
    assert response.headers["cache-control"] == "no-store"
    stranger = TestClient(create_app(DSN, tmp_path))
    stranger.post("/api/session")
    assert stranger.get(f"/api/reviews/{review_id}").status_code == 404


def test_ready_artifact_requires_owner_safe_path_and_matching_hash(client, tmp_path):
    review_id = review(client)
    run_id = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "artifact"}).json()["run_id"]
    content = b"{\"ok\":true}\n"
    relative = f"artifacts/{run_id}/report.json"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    artifact = {"artifact_id": "report-1", "role": "report_json", "format": "json", "status": "ready", "file_name": "report.json", "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "reason": None}
    with connect(DSN) as conn:
        conn.execute("UPDATE runs SET result_json = %s WHERE id = %s", (Jsonb({"artifacts": [artifact]}), run_id))
        conn.execute("INSERT INTO artifact_files(artifact_id, run_id, relative_path) VALUES (%s, %s, %s)", (artifact["artifact_id"], run_id, relative))
    url = "/api/artifacts/report-1"
    response = client.get(url)
    assert response.status_code == 200 and response.content == content
    assert response.headers["cache-control"] == "no-store"
    stranger = TestClient(create_app(DSN, tmp_path))
    stranger.post("/api/session")
    assert stranger.get(url).status_code == 404
    path.write_bytes(b"tampered")
    assert client.get(url).status_code == 404
    path.write_bytes(content)
    with connect(DSN) as conn:
        conn.execute("UPDATE artifact_files SET relative_path = %s WHERE artifact_id = %s", ("../outside.json", artifact["artifact_id"]))
    assert client.get(url).status_code == 404
    with connect(DSN) as conn:
        conn.execute("UPDATE artifact_files SET relative_path = %s WHERE artifact_id = %s", (relative, artifact["artifact_id"]))
        artifact["status"] = "mock"
        artifact["size_bytes"] = None
        artifact["sha256"] = None
        artifact["reason"] = "모의 파일"
        conn.execute("UPDATE runs SET result_json = %s WHERE id = %s", (Jsonb({"artifacts": [artifact]}), run_id))
    assert client.get(url).status_code == 404


def test_bad_manifest_and_sequence_leave_no_review(client):
    client.post("/api/session")
    body = experimental_demo()
    body["candidates"][0]["heavy_chain_fasta"] = ">bad\nABC*"
    assert client.post("/api/reviews", data={"metadata": json.dumps(body)}).status_code == 422
    body = experimental_demo()
    body["uploads"] = [{
        "upload_key": "structure_a", "file_name": "a.pdb", "format": "pdb",
        "candidate_id": body["candidates"][0]["candidate_id"], "role": "complex",
        "source": {"title": "test", "url": "https://example.org/a", "record_id": None},
    }]
    assert client.post("/api/reviews", data={"metadata": json.dumps(body)}).status_code == 422
    with connect(DSN) as conn:
        assert conn.execute("SELECT count(*) AS n FROM reviews").fetchone()["n"] == 0


@pytest.mark.parametrize("change", [
    {"identifier": "P12345"},
    {"fasta": None},
    {"fasta": ">other\n" + "A" * 607},
])
def test_wrong_target_is_rejected_before_review(client, change):
    client.post("/api/session")
    body = experimental_demo()
    body["target"].update(change)
    response = client.post("/api/reviews", data={"metadata": json.dumps(body)})
    assert response.status_code == 422
    with connect(DSN) as conn:
        assert conn.execute("SELECT count(*) AS n FROM reviews").fetchone()["n"] == 0


def test_invalid_structure_is_rejected_without_file_or_db_row(client, tmp_path):
    client.post("/api/session")
    body = experimental_demo()
    body["uploads"] = [{
        "upload_key": "structure_a", "file_name": "../secret.pdb", "format": "pdb",
        "candidate_id": body["candidates"][0]["candidate_id"], "role": "complex",
        "source": {"title": "test", "url": "https://example.org/a", "record_id": None},
    }]
    response = client.post("/api/reviews", data={"metadata": json.dumps(body)}, files={"structure_a": ("../secret.pdb", b"garbage")})
    assert response.status_code == 422
    assert not list(tmp_path.rglob("*.pdb"))
    with connect(DSN) as conn:
        assert conn.execute("SELECT count(*) AS n FROM reviews").fetchone()["n"] == 0


def test_valid_structure_is_stored_with_hash_but_client_path_is_ignored(client, tmp_path):
    import hashlib

    client.post("/api/session")
    body = experimental_demo()
    source = Path("docs/topics/her2/assets/a01/sources/1N8Z-assembly1.cif")
    structure = source.read_bytes()
    body["uploads"] = [{
        "upload_key": "structure_a", "file_name": "../../unsafe.cif", "format": "mmcif",
        "candidate_id": body["candidates"][0]["candidate_id"], "role": "complex",
        "source": {"title": "PDB 1N8Z", "url": "https://www.rcsb.org/structure/1N8Z", "record_id": "1N8Z"},
    }]
    response = client.post("/api/reviews", data={"metadata": json.dumps(body)}, files={"structure_a": ("../../unsafe.cif", structure)})
    assert response.status_code == 201, response.text
    review_id = response.json()["review_id"]
    saved = tmp_path / "uploads" / review_id / "structure_a.cif"
    assert saved.read_bytes() == structure
    assert not (tmp_path / "unsafe.cif").exists()
    with connect(DSN) as conn:
        row = conn.execute("SELECT relative_path, sha256, size_bytes FROM uploads WHERE review_id = %s", (review_id,)).fetchone()
    assert row["relative_path"] == f"uploads/{review_id}/structure_a.cif"
    assert row["sha256"] == hashlib.sha256(structure).hexdigest()
    assert row["size_bytes"] == len(structure)


def test_cross_origin_mutation_is_rejected(client):
    response = client.post("/api/session", headers={"Origin": "https://other.example"})
    assert response.status_code == 403


def test_admission_is_idempotent_and_rejects_second_active_run(client):
    review_id = review(client)
    first = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "one"})
    assert first.status_code == 202
    assert client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "one"}).json() == first.json()
    rejected = client.post(f"/api/reviews/{review_id}/runs", json={"request_key": "two"})
    assert rejected.status_code == 429 and rejected.json()["code"] == "RUN_LIMIT_REACHED"


def test_concurrent_global_admission_and_reports(client, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from service.worker import process_one
    review(client)
    peers = [TestClient(create_app(DSN, tmp_path, max_active_runs=1)) for _ in range(2)]
    ids = [review(peer) for peer in peers]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda item: item[0].post(f"/api/reviews/{item[1]}/runs", json={"request_key": "one"}), zip(peers, ids)))
    assert sorted(r.status_code for r in responses) == [202, 429]
    winner = next(i for i, response in enumerate(responses) if response.status_code == 202)
    owner = peers[winner]
    run_id = responses[winner].json()["run_id"]
    assert owner.get(f"/api/runs/{run_id}/report.json").status_code == 409
    process_one(DSN, data_root=tmp_path)
    response = owner.get(f"/api/runs/{run_id}/report.json")
    assert response.status_code == 200
    assert response.json()["run"] == owner.get(f"/api/runs/{run_id}").json()
    assert response.json()["result"] == owner.get(f"/api/runs/{run_id}/result").json()
    assert response.headers["cache-control"] == "no-store"
    assert owner.get(f"/api/runs/{run_id}/report.csv").status_code == 200
    assert client.get(f"/api/runs/{run_id}/report.json").status_code == 404
    assert owner.get(f"/api/runs/{run_id}/report.exe").status_code == 404


def test_session_review_and_storage_limits(client, tmp_path):
    limited = TestClient(create_app(DSN, tmp_path, max_sessions=1, max_session_reviews=1))
    assert limited.post('/api/session').status_code == 201
    assert TestClient(create_app(DSN, tmp_path, max_sessions=1)).post('/api/session').status_code == 429
    from service.demo_input import experimental_demo
    body = {'metadata': json.dumps(experimental_demo())}
    assert limited.post('/api/reviews', data=body).status_code == 201
    assert limited.post('/api/reviews', data=body).json()['code'] == 'REVIEW_LIMIT_REACHED'
    storage_limited = TestClient(create_app(DSN, tmp_path, max_storage_bytes=1))
    assert storage_limited.post('/api/session').json()['code'] == 'STORAGE_LIMIT_REACHED'


def test_global_mutation_rate_limit(client, tmp_path):
    limited = TestClient(create_app(DSN, tmp_path, requests_per_minute=2))
    assert limited.post('/api/session').status_code == 201
    assert limited.post('/api/session/heartbeat').status_code == 200
    assert limited.post('/api/session/heartbeat').json()['code'] == 'REQUEST_LIMIT_REACHED'
    assert limited.get('/api/config').status_code == 200


def test_request_limit_applies_before_multipart_including_chunked(client, tmp_path):
    limited = TestClient(create_app(DSN, tmp_path, max_request_bytes=10))
    for body in [b'a' * 11, iter([b'12345', b'678901'])]:
        response = limited.post('/api/reviews', content=body, headers={'content-type': 'multipart/form-data; boundary=x'})
        assert response.status_code == 413
        assert response.json()['code'] == 'INPUT_TOO_LARGE'
    assert not list(tmp_path.rglob('*'))


def test_request_budget_is_shared_and_atomic(client):
    from concurrent.futures import ThreadPoolExecutor
    from service.limits import admit_request
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: admit_request(DSN, 3), range(20)))
    assert sum(results) == 3
    with connect(DSN) as conn:
        conn.execute("UPDATE request_budget SET bucket = bucket - interval '2 minutes'")
    assert admit_request(DSN, 3)


def test_slow_body_is_rejected_before_the_application(monkeypatch):
    import asyncio
    from service.limits import IntakeLimit
    sent = []
    async def application(*args):
        raise AssertionError('oversize/slow body reached parser')
    async def send(message): sent.append(message)
    async def receive():
        await asyncio.sleep(1)
        return {'type': 'http.request', 'body': b''}
    async def deadline_exceeded(awaitable, timeout):
        awaitable.close()
        raise TimeoutError
    monkeypatch.setattr("service.limits.asyncio.wait_for", deadline_exceeded)
    # Test the receiving boundary directly, independently of DB admission.
    limiter = IntakeLimit(application, dsn='', mode='live', max_bytes=10, requests_per_minute=1)
    asyncio.run(limiter.read_body({'type': 'http'}, receive, send))
    assert sent[0]['status'] == 408


def test_continuously_ready_body_cannot_bypass_receive_deadline(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from service.limits import IntakeLimit
    sent = []
    async def app(*args): raise AssertionError('must not reach app')
    async def receive(): raise AssertionError('deadline must be checked before receive')
    async def send(message): sent.append(message)
    moments = iter([0, 31])
    monkeypatch.setattr('service.limits.time', SimpleNamespace(monotonic=lambda: next(moments)))
    limiter = IntakeLimit(app, dsn='', mode='live', max_bytes=10, requests_per_minute=1)
    asyncio.run(limiter.read_body({'type': 'http'}, receive, send))
    assert sent[0]['status'] == 408
