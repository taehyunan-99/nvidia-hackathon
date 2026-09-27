"""Exercise the same-origin persistent mock path against a running Compose stack."""

import json
import os
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

base = os.environ.get("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
opener = build_opener(HTTPCookieProcessor(CookieJar()))
input_data = json.loads(Path("docs/frontend-hosting/fixtures/scenarios.json").read_text())["input"]
input_data["target"] = json.loads(Path("docs/frontend-hosting/fixtures/public-reference-input.json").read_text())["target"]
input_data["candidates"][0]["name"] = "User candidate A"
input_data["candidates"][1]["name"] = "User candidate B"


def request(path, *, method="GET", body=None, content_type="application/json"):
    data = None if body is None else body
    req = Request(base + path, data=data, method=method, headers={"Content-Type": content_type} if data is not None else {})
    with opener.open(req, timeout=15) as response:
        return json.load(response)


assert request("/api/session", method="POST")["status"] == "active"
boundary = "her2-test-boundary"
payload = f"--{boundary}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n\r\n{json.dumps(input_data)}\r\n--{boundary}--\r\n".encode()
review_id = request("/api/reviews", method="POST", body=payload, content_type=f"multipart/form-data; boundary={boundary}")["review_id"]
assert request(f"/api/reviews/{review_id}")["candidates"][0]["name"] == "User candidate A"
run = request(f"/api/reviews/{review_id}/runs", method="POST", body=b'{"request_key":"ci-smoke"}')
for _ in range(30):
    current = request(f"/api/runs/{run['run_id']}")
    if current["status"] in {"completed", "partial", "failed", "interrupted"}:
        break
    time.sleep(1)
else:
    raise AssertionError("mock worker did not finish within 30 seconds")
assert current["result_available"] and current["data_mode"] == "mock"
result = request(f"/api/runs/{run['run_id']}/result")
assert result["run_id"] == run["run_id"] and result["candidate_ids"] == ["mock-candidate-a", "mock-candidate-b"]
for artifact in result["artifacts"]:
    assert artifact["status"] != "ready"
    try:
        request(f"/api/artifacts/{artifact['artifact_id']}")
    except HTTPError as error:
        assert error.code == 404
    else:
        raise AssertionError("mock artifact was downloadable")
print("Persistent mock flow passed")
