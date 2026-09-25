"""호출부의 한도 대응 검증.

실측에서 Boltz-2는 한도를 넘기면 Retry-After 없이 429를 즉시 돌려준다.
순차 호출에서도 났다. 재시도가 없으면 시연 중 후보 하나가 그대로 실패로
표시된다. 여기서 보는 것은 세 가지다 — 재시도를 하는가, 고쳐지지 않을
오류까지 붙들고 늘어지지는 않는가, 그리고 **한도를 밟은 사실을 기록에서
지우지는 않는가**.

NVIDIA를 실제로 부르지 않는다. requests.post를 가짜로 바꿔서 본다.
"""

from __future__ import annotations

import json

import pytest

from logic import nvidia_client
from logic.nvidia_client import CallFailed, NvidiaClient


class FakeResponse:
    def __init__(self, status: int, *, retry_after: str | None = None, payload=None):
        self.status_code = status
        self.headers = {} if retry_after is None else {"Retry-After": retry_after}
        self._payload = payload if payload is not None else {"ok": True}
        self.text = json.dumps({"status": status})

    def json(self):
        return self._payload


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(nvidia_client.time, "sleep", lambda _s: None)  # 테스트를 재우지 않는다
    return NvidiaClient(tmp_path, api_key="test-key")


def _responses(client, monkeypatch, sequence):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(url)
        return sequence[len(calls) - 1]

    monkeypatch.setattr(nvidia_client.requests, "post", fake_post)
    return calls


def test_retries_past_a_rate_limit(client, monkeypatch):
    calls = _responses(
        client, monkeypatch, [FakeResponse(429), FakeResponse(429), FakeResponse(200)]
    )

    result = client._post("http://x", {}, "boltz2.predict", {})

    assert result == {"ok": True}
    assert len(calls) == 3


def test_the_rate_limit_is_still_recorded_after_a_successful_retry(client, monkeypatch):
    """429를 지우면 시연이 왜 느렸는지 나중에 알 수 없다."""
    _responses(client, monkeypatch, [FakeResponse(429), FakeResponse(200)])

    client._post("http://x", {}, "boltz2.predict", {})

    statuses = [r.status for r in client.records]
    assert statuses == [429, 200]
    logged = (client.work_dir / "call_log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(logged) == 2
    assert json.loads(logged[0])["status"] == 429


def test_retries_are_bounded(client, monkeypatch):
    """끝없이 기다리면 시연이 멈춘 것처럼 보인다."""
    calls = _responses(client, monkeypatch, [FakeResponse(429)] * 10)

    with pytest.raises(CallFailed) as exc:
        client._post("http://x", {}, "boltz2.predict", {})

    assert exc.value.status == 429
    assert len(calls) == nvidia_client.MAX_RETRIES + 1


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_errors_that_will_not_fix_themselves_are_not_retried(client, monkeypatch, status):
    """잘못된 입력·잘못된 키는 기다린다고 나아지지 않는다."""
    calls = _responses(client, monkeypatch, [FakeResponse(status)] * 5)

    with pytest.raises(CallFailed):
        client._post("http://x", {}, "boltz2.predict", {})

    assert len(calls) == 1


def test_retry_after_header_wins_over_our_guess(client, monkeypatch):
    """실측에서는 없었지만 서버가 알려주면 우리 추측보다 그쪽이 맞다."""
    slept: list[float] = []
    monkeypatch.setattr(nvidia_client.time, "sleep", slept.append)
    _responses(
        client, monkeypatch, [FakeResponse(429, retry_after="7"), FakeResponse(200)]
    )

    client._post("http://x", {}, "boltz2.predict", {})

    assert slept == [7.0]


def test_a_broken_retry_after_falls_back_instead_of_crashing(client, monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr(nvidia_client.time, "sleep", slept.append)
    _responses(
        client, monkeypatch, [FakeResponse(429, retry_after="곧"), FakeResponse(200)]
    )

    client._post("http://x", {}, "boltz2.predict", {})

    assert slept == [nvidia_client.RETRY_WAITS[0]]


def test_the_judgement_call_does_not_wait_as_long_as_a_prediction(client, monkeypatch):
    """실측에서 503 재시도 35초가 실행 시간을 57초에서 105초로 늘렸다.

    판단 호출이 막히는 이유는 한도가 아니라 잠깐 지나가는 혼잡이다.
    예측 호출용 간격을 그대로 쓰면 시연이 그만큼 멈춘다.
    """
    slept: list[float] = []
    monkeypatch.setattr(nvidia_client.time, "sleep", slept.append)
    _responses(client, monkeypatch, [FakeResponse(503)] * 3 + [FakeResponse(200)])

    client.chat("test-model", [{"role": "user", "content": "x"}])

    assert slept == list(nvidia_client.CHAT_RETRY_WAITS)
    assert sum(slept) < sum(nvidia_client.RETRY_WAITS)


def test_the_prediction_call_keeps_the_longer_waits(client, monkeypatch):
    """Boltz-2 쪽은 실제 한도라서 짧게 두드려도 소용없다. 그대로 둔다."""
    slept: list[float] = []
    monkeypatch.setattr(nvidia_client.time, "sleep", slept.append)
    _responses(client, monkeypatch, [FakeResponse(429), FakeResponse(200)])

    client.predict_complex([{"id": "A", "molecule_type": "protein", "sequence": "AAA"}])

    assert slept == [nvidia_client.RETRY_WAITS[0]]
