"""Exercise transport without spending requests or waiting on real time."""
import asyncio
from types import SimpleNamespace

import pytest
pytest.importorskip("nat")
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from logic import nat_agent, nat_model


def test_transport_paces_recovers_logs_and_only_skips_accepted_terminal(monkeypatch, caplog):
    model = nat_model.PacedNIM.model_construct(request_interval=15)
    model._async_client = SimpleNamespace(last_response=None)
    paced, cooled, calls = [], [], []

    async def pace(interval):
        paced.append(interval)

    async def stream(self, *args, **kwargs):
        assert kwargs['chat_template_kwargs'] == {'enable_thinking': False}
        calls.append(1)
        status = 429 if len(calls) == 1 else 200
        self._async_client.last_response = SimpleNamespace(status=status, headers={
            "Retry-After": "45", "x-request-id": "test-id", "Authorization": "secret"})
        if status == 429:
            raise RuntimeError("429")
        yield ChatGenerationChunk(message=AIMessageChunk(content="ok"))

    monkeypatch.setattr(nat_model, "_pace", pace)
    monkeypatch.setattr(nat_model, "_cooldown", cooled.append)
    monkeypatch.setattr(nat_model.ChatNVIDIA, "_astream", stream)
    caplog.set_level("INFO", logger="logic.nat_model")

    async def run():
        session = SimpleNamespace(terminal=None)
        token = nat_agent._CURRENT.set(SimpleNamespace(s=session))
        try:
            # Refused/not-yet-terminal submission must continue calling the model.
            chunks = [c async for c in model._astream([])]
            assert chunks[0].text == "ok"
            session.terminal = "completed"
            assert [c.text async for c in model._astream([])] == ["검토를 끝냈다."]
        finally:
            nat_agent._CURRENT.reset(token)
    asyncio.run(run())
    assert paced == [15, 15] and cooled == [45] and len(calls) == 2
    assert '"status": 429' in caplog.text and '"status": 200' in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.parametrize("status,partial,expected", [(429, False, 3), (429, True, 1), (401, False, 1)])
def test_retry_is_bounded_and_never_replays_partial_output(monkeypatch, status, partial, expected):
    model = nat_model.PacedNIM.model_construct(request_interval=0)
    model._async_client = SimpleNamespace(last_response=None)
    calls = []
    async def stream(self, *args, **kwargs):
        calls.append(1)
        self._async_client.last_response = SimpleNamespace(status=status, headers={})
        if partial:
            yield ChatGenerationChunk(message=AIMessageChunk(content="partial"))
        raise RuntimeError(str(status))
    monkeypatch.setattr(nat_model.ChatNVIDIA, "_astream", stream)
    monkeypatch.setattr(nat_model, "_cooldown", lambda seconds: None)
    async def run():
        with pytest.raises(RuntimeError):
            async for _ in model._astream([]):
                pass
    asyncio.run(run())
    assert len(calls) == expected


def test_pacing_applies_between_requests(monkeypatch):
    clock, sleeps = [100.0], []
    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay
    monkeypatch.setattr(nat_model.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(nat_model.asyncio, "sleep", sleep)
    monkeypatch.setattr(nat_model, "_next_request", 0.0)
    async def run():
        await nat_model._pace(15)
        await nat_model._pace(15)
        nat_model._cooldown(45)
        await nat_model._pace(15)
    asyncio.run(run())
    assert sleeps == [15, 45]


@pytest.mark.parametrize("status,attempt,partial,retry_after,expected", [
    # 서버가 상한보다 긴 대기를 요구하면 재시도하지 않고, 전역 대기도 상한까지만 심는다.
    (429, 0, False, 3600.0, (nat_model.MAX_WAIT_SECONDS, False)),
    (429, 0, False, None, (30.0, True)),
    (429, 1, False, None, (60.0, True)),
    (429, 2, False, None, (nat_model.MAX_WAIT_SECONDS, False)),
    (429, 0, True, None, (30.0, False)),
    (401, 0, False, None, (0.0, False)),
])
def test_a_long_retry_after_never_parks_the_whole_process(status, attempt, partial, retry_after, expected):
    assert nat_model.plan_retry(status, attempt, partial, retry_after) == expected


def test_recovered_and_empty_responses_are_countable_after_the_run(monkeypatch):
    """복구된 429와 빈 200 응답을 실행 뒤에 세려면 시도 기록이 남아야 한다."""
    nat_model.take_attempts()
    model = nat_model.PacedNIM.model_construct(request_interval=0)
    model._async_client = SimpleNamespace(last_response=None)
    calls = []

    async def stream(self, *args, **kwargs):
        calls.append(1)
        status = 429 if len(calls) == 1 else 200
        self._async_client.last_response = SimpleNamespace(status=status, headers={})
        if status == 429:
            raise RuntimeError("429")
        if len(calls) == 2:  # 200인데 아무것도 내놓지 않은 빈 응답
            return
        yield ChatGenerationChunk(message=AIMessageChunk(content="ok"))

    monkeypatch.setattr(nat_model.ChatNVIDIA, "_astream", stream)
    monkeypatch.setattr(nat_model, "_cooldown", lambda seconds: None)

    async def run():
        async for _ in model._astream([]):
            pass
        async for _ in model._astream([]):
            pass
    asyncio.run(run())

    attempts = nat_model.take_attempts()
    assert [(a["status"], a["emitted"]) for a in attempts] == [(429, False), (200, False), (200, True)]
    assert nat_model.take_attempts() == []
