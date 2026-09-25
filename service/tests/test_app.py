"""시연용 실행부 검증.

NVIDIA를 실제로 부르지 않는다. 실행부가 책임지는 것만 본다 — 입력을 받아
로직 B에 넘기고, 돌려받은 것을 계약으로 확인한 뒤, 프런트가 읽는 모양으로
내보내는가. 분석 판단이 맞는지는 logic/tests의 몫이다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from logic.contract import SCHEMA_VERSION
from service import app as service_app
from service.app import app

client = TestClient(app)


# ---------------------------------------------------------------- health
def test_health_does_not_leak_the_key(monkeypatch):
    from logic import env

    secret = "nvapi-" + "z" * 58
    monkeypatch.setenv("NVIDIA_API_KEY", secret)
    body = client.get("/api/health").json()
    text = str(body)

    assert body["key_present"] is True
    assert secret not in text, "키 전체가 응답에 실렸다"
    # mask()는 어느 키를 쓰는지 알아볼 만큼만 남긴다. 그 이상이면 안 된다.
    assert env.mask(secret) in text
    assert text.count("z") < 20, "가린 자리가 너무 적다"


def test_health_reports_absent_key_without_failing(monkeypatch):
    from logic import env

    for name in env.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env, "ENV_PATH", service_app.WORK_ROOT / "does-not-exist.env")

    body = client.get("/api/health").json()

    assert body["key_present"] is False
    assert body["data_mode"] == "live"


# ---------------------------------------------------------------- presets
@pytest.mark.parametrize("name", ["experimental", "prediction"])
def test_presets_are_valid_review_input(name):
    """계약을 어기는 입력을 시연 버튼이 만들면 안 된다."""
    body = client.get(f"/api/presets/{name}").json()

    assert body["schema_version"] == SCHEMA_VERSION
    assert 2 <= len(body["candidates"]) <= 3
    assert body["public_data_confirmed"] is True


def test_unknown_preset_is_404():
    assert client.get("/api/presets/nope").status_code == 404
    assert client.post("/api/review", json={"preset": "nope"}).status_code == 404


def test_preset_sequences_come_from_the_public_files():
    """서열을 코드에 적어 두면 원본과 어긋나도 아무도 모른다."""
    from logic import structures
    from service import demo_input

    body = client.get("/api/presets/experimental").json()
    heavy = structures.normalize_sequence(body["candidates"][0]["heavy_chain_fasta"])

    assert heavy == structures.load_catalog()[demo_input.TRASTUZUMAB].by_role("heavy")[0].sequence


# ---------------------------------------------------------------- review
def test_experimental_run_needs_no_api_key(monkeypatch):
    """시연의 기본 경로는 키 없이 돌아야 한다."""
    from logic import env

    for name in env.KEY_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env, "ENV_PATH", service_app.WORK_ROOT / "does-not-exist.env")

    body = client.post("/api/review", json={"preset": "experimental"}).json()

    frame = body["scenarios"][0]
    assert frame["run"]["status"] == "completed"
    assert all(c["status"] == "completed" for c in frame["run"]["candidates"])
    steps = {s["step_id"]: s["status"] for s in frame["run"]["candidates"][0]["steps"]}
    assert steps["prediction"] == "skipped"


def test_response_is_shaped_for_the_frontend():
    body = client.post("/api/review", json={"preset": "experimental"}).json()

    assert body["schema_version"] == SCHEMA_VERSION
    assert body["data_mode"] == "live"
    assert len(body["scenarios"]) == 1
    frame = body["scenarios"][0]
    assert set(frame) == {"name", "description", "session", "run", "result", "error"}
    # 프런트는 파일 안에서 mode가 섞이는 것을 거부한다.
    assert frame["session"]["data_mode"] == "live"
    assert frame["run"]["data_mode"] == "live"
    assert frame["result"]["data_mode"] == "live"
    assert frame["run"]["run_id"] == frame["result"]["run_id"]
    assert frame["run"]["result_available"] is True


def test_each_run_gets_its_own_id():
    first = client.post("/api/review", json={"preset": "experimental"}).json()
    second = client.post("/api/review", json={"preset": "experimental"}).json()

    assert first["scenarios"][0]["run"]["run_id"] != second["scenarios"][0]["run"]["run_id"]


def test_unmeasured_evidence_keeps_a_reason_and_null_value():
    """미확인을 0으로 내보내면 화면이 '측정했는데 0'으로 읽는다."""
    body = client.post("/api/review", json={"preset": "experimental"}).json()

    unmeasured = [
        e for e in body["scenarios"][0]["result"]["evidence"]
        if e["measurement_state"] != "measured"
    ]
    assert unmeasured, "미실행 근거가 하나도 없으면 이 검사가 무의미하다"
    for item in unmeasured:
        assert item["value"] is None
        assert item["reason"]


def test_contract_violating_input_is_rejected_without_running():
    """계약을 어긴 입력을 분석으로 넘기지 않는다."""
    body = client.get("/api/presets/experimental").json()
    body["candidates"] = body["candidates"][:1]  # minItems 2 위반

    response = client.post("/api/review", json={"input": body})

    assert response.status_code == 422
    assert "candidates" in response.text


def test_broken_result_is_not_served_as_success(monkeypatch):
    """계약을 어긴 결과가 나오면 화면으로 내보내지 않는다."""

    real = service_app.run_flow

    def broken(request, **kwargs):
        output, flow = real(request, **kwargs)
        output["result"]["evidence"] = [{"이건": "계약에 없는 모양"}]
        return output, flow

    monkeypatch.setattr(service_app, "run_flow", broken)

    response = client.post("/api/review", json={"preset": "experimental"})

    assert response.status_code == 500
    assert "계약" in response.text
