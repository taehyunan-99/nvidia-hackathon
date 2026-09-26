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
        conn.execute("TRUNCATE runs, uploads, reviews, sessions CASCADE")
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
