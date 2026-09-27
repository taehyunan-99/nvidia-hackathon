"""Check persisted public-structure analysis. Configure worker keys empty for offline checks; rule mode alone can call models."""

import hashlib
import json
import os
import time

import requests

from service.demo_input import experimental_demo

base = os.environ.get("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
client = requests.Session()


def request(method, path, **kwargs):
    response = client.request(method, base + path, timeout=20, **kwargs)
    assert response.ok, f"{path}: HTTP {response.status_code}: {response.text[:180]}"
    return response


assert request("GET", "/api/config").json()["data_mode"] == "live"
assert request("POST", "/api/session").json()["status"] == "active"
input_data = experimental_demo()
review_id = request("POST", "/api/reviews", data={"metadata": json.dumps(input_data)}).json()["review_id"]
run = request("POST", f"/api/reviews/{review_id}/runs", json={"request_key": "live-public-check"}).json()
for _ in range(90):
    state = request("GET", f"/api/runs/{run['run_id']}").json()
    if state["status"] in {"completed", "partial", "failed", "interrupted"}:
        break
    time.sleep(1)
else:
    raise AssertionError("saved live analysis did not finish within 90 seconds")
assert state["status"] == "completed" and state["result_available"], state
result = request("GET", f"/api/runs/{run['run_id']}/result").json()
assert result["run_id"] == run["run_id"] and result["data_mode"] == "live"
assert result["candidate_ids"] == [candidate["candidate_id"] for candidate in state["candidates"]]
ready = [artifact for artifact in result["artifacts"] if artifact["status"] == "ready"]
assert ready, "expected a public experimental structure file"
for artifact in ready:
    data = request("GET", f"/api/runs/{run['run_id']}/artifacts/{artifact['artifact_id']}").content
    assert len(data) == artifact["size_bytes"] and hashlib.sha256(data).hexdigest() == artifact["sha256"]
    assert client.get(base + f"/api/runs/another-run/artifacts/{artifact['artifact_id']}").status_code == 404
stranger = requests.Session()
stranger.post(base + "/api/session", timeout=20)
assert stranger.get(base + f"/api/runs/{run['run_id']}/artifacts/{ready[0]['artifact_id']}", timeout=20).status_code == 404
print("Persisted live input, progress, result, file integrity, and ownership: PASS")
