"""NAT 연결부. 실제 모델은 RUN_LIVE_NAT=1일 때만 부른다."""

from __future__ import annotations

import os

import pytest

from logic import nat_agent
from logic.contract import validate
from logic.flow import run_flow
from logic.tests.test_flow import TRASTUZUMAB, candidate, entity_sequence, make_request
from logic.tests.test_flow_decisions import ScriptedClient, _filler


def _request(tmp_path):
    t = candidate("cand-t", "trastuzumab",
                  entity_sequence(TRASTUZUMAB, "heavy"), entity_sequence(TRASTUZUMAB, "light"))
    return make_request([t, _filler()], tmp_path)


def _opinion_for(output, candidate_id):
    for op in output["result"]["opinions"]:
        if op["candidate_id"] == candidate_id:
            return op
    raise AssertionError(f"no opinion for {candidate_id}")


def test_nat_mode_is_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGIC_AGENT_MODE", raising=False)
    called = []
    monkeypatch.setattr(nat_agent, "NAT_AVAILABLE", True)
    monkeypatch.setattr(nat_agent, "run_candidate", lambda *a, **k: called.append(1) or "완료")
    output, _ = run_flow(_request(tmp_path), client=ScriptedClient())
    assert called  # nat_agent.run_candidate가 최소 한 번은 불렸다
    validate(output, "LogicOutput")


def test_nat_failure_falls_back_to_rule_with_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    monkeypatch.setattr(nat_agent, "NAT_AVAILABLE", True)
    monkeypatch.setattr(nat_agent, "run_candidate", lambda flow, s, **k: "에이전트 반복 상한")
    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    validate(output, "LogicOutput")
    assert flow.states["cand-t"].status == "completed"
    opinion = _opinion_for(output, "cand-t")
    assert "진행: 규칙 — 에이전트 반복 상한" in opinion["reason"]


def test_missing_nat_falls_back_to_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    monkeypatch.setattr(nat_agent, "NAT_AVAILABLE", False)
    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    validate(output, "LogicOutput")
    opinion = _opinion_for(output, "cand-t")
    assert "NAT를 불러오지 못했다" in opinion["reason"]


def test_fallback_reason_includes_last_refusal_note(tmp_path):
    from logic.agent_session import CandidateSession

    session = CandidateSession(candidate("cand-t", "trastuzumab",
                                          entity_sequence(TRASTUZUMAB, "heavy"),
                                          entity_sequence(TRASTUZUMAB, "light")))
    session.calls.append({"tool": "check_input", "accepted": True})
    session.calls.append({"tool": "submit_opinion", "accepted": False,
                           "note": "거부: decision은 reviewable 또는 needs_confirmation 중 하나여야 한다."})
    reason = nat_agent._fallback_reason(session, "다 됐다")
    assert reason is not None
    assert "마지막 거부" in reason
    assert reason.startswith("에이전트가 종료 도구 없이 끝났다")


def test_fallback_reason_is_none_for_terminal_session(tmp_path):
    from logic.agent_session import CandidateSession

    session = CandidateSession(candidate("cand-t", "trastuzumab",
                                          entity_sequence(TRASTUZUMAB, "heavy"),
                                          entity_sequence(TRASTUZUMAB, "light")))
    session.terminal = "completed"
    assert nat_agent._fallback_reason(session, "검토를 끝냈다.") is None


def test_run_candidate_turns_an_agent_crash_into_a_rule_finish_reason(tmp_path):
    """에이전트 실행이 예외로 터지면 run_candidate가 사유 문자열로 바꿔 돌려준다.

    위의 `test_nat_failure_falls_back_to_rule_with_reason`은 run_candidate를
    스텁으로 갈아끼우므로 이 try/except를 지나지 않는다. 안전망의 핵심(에이전트가
    어떻게 실패해도 후보가 결과 없이 끝나지 않는다)이 여기 달려 있어 직접 확인한다.
    없는 설정 파일을 줘서 load_workflow가 터지게 한다 — 모델을 부르지 않는다.
    """
    pytest.importorskip("nat")
    from logic.agent_session import CandidateSession
    from logic.flow import Flow

    cand = candidate("cand-t", "trastuzumab",
                     entity_sequence(TRASTUZUMAB, "heavy"), entity_sequence(TRASTUZUMAB, "light"))
    flow = Flow(make_request([cand, _filler()], tmp_path), client=ScriptedClient())
    session = CandidateSession(cand)

    why = nat_agent.run_candidate(flow, session, config_path=tmp_path / "없는-설정.yml")

    assert why is not None, "예외가 났으면 규칙 마무리 사유를 돌려줘야 한다"
    assert why.startswith("에이전트 실행 오류:")
    assert session.terminal is None, "터진 세션은 종료 상태가 아니어야 규칙이 이어받는다"

    # 그 사유로 규칙이 마무리하면 계약을 지키는 결과가 나온다.
    flow._continue_by_rule(session, why)
    assert flow.states["cand-t"].status in {"completed", "partial", "failed"}


def test_fallback_reason_detects_iteration_limit_by_call_count(tmp_path):
    """M2: 반복 상한은 NAT의 영어 문구가 아니라 도구 호출 수로도 알아본다.

    NAT는 상한에 닿으면 GraphRecursionError를 삼키고 영어 문장을 돌려준다.
    그 문장이 바뀌어도 사유가 "종료 도구 없이 끝났다"로 잘못 분류되지 않게 한다.
    """
    from logic.agent_session import CandidateSession

    session = CandidateSession(candidate("cand-t", "trastuzumab",
                                          entity_sequence(TRASTUZUMAB, "heavy"),
                                          entity_sequence(TRASTUZUMAB, "light")))
    for _ in range(10):
        session.calls.append({"tool": "compare_structure", "accepted": False, "note": "거부: …"})
    changed = "문구가 바뀐 상한 메시지"
    assert nat_agent._fallback_reason(session, changed, max_iterations=10) == "에이전트 반복 상한"
    assert nat_agent._fallback_reason(session, changed, max_iterations=11).startswith(
        "에이전트가 종료 도구 없이 끝났다")


def test_max_iterations_is_read_from_the_shipped_config():
    assert nat_agent._max_iterations(nat_agent.CONFIG_PATH) == 10


def test_workflow_config_loads_with_registered_tools():
    pytest.importorskip("nat")
    from nat.runtime.loader import load_config
    config = load_config(nat_agent.CONFIG_PATH)
    assert set(config.functions) == set(nat_agent.TOOL_NAMES)
    assert config.workflow.max_empty_response_retries == 2


def test_invalid_input_never_loads_a_model_workflow(tmp_path, monkeypatch):
    from logic.agent_session import CandidateSession
    from logic.flow import Flow

    def unexpected(*args, **kwargs):
        raise AssertionError("잘못된 입력에 모델 워크플로를 열었다")

    monkeypatch.setattr(nat_agent, "load_workflow", unexpected)
    flow = Flow(_request(tmp_path), client=ScriptedClient())
    session = CandidateSession(_filler())
    assert nat_agent.run_candidate(flow, session) is None
    assert session.terminal == "failed"
    assert session.calls == [{"tool": "check_input", "accepted": True, "executed_by": "code"}]


def test_error_after_submission_is_retained_without_replacing_the_opinion(tmp_path, monkeypatch):
    from logic.agent_session import CandidateTools

    def agent(flow, session):
        tools = CandidateTools(flow, session)
        tools.check_input()
        if session.terminal:
            return None
        tools.lookup_public_structure()
        tools.use_experimental_structure("일치한다.")
        tools.compare_structure()
        tools.submit_opinion("needs_confirmation", "미계산 항목을 확인해야 한다.")
        return "에이전트 실행 오류: 429 Too Many Requests"

    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    monkeypatch.setattr(nat_agent, "NAT_AVAILABLE", True)
    monkeypatch.setattr(nat_agent, "run_candidate", agent)
    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    assert "429" in flow.agent_errors["cand-t"]
    assert flow.states["cand-t"].status == "completed"
    assert "진행: 모델" in _opinion_for(output, "cand-t")["reason"]
    assert "판단: 규칙 — 항목별 근거" in _opinion_for(output, "cand-t")["reason"]
    assert "429" not in _opinion_for(output, "cand-t")["reason"]
    from logic import measure_agent
    monkeypatch.setattr(measure_agent, "run_flow", lambda request: (output, flow))
    row = measure_agent._one("trastuzumab", "nat")
    assert row["rate_limited"] is True
    assert row["rule_finish"] is False
    assert row["decision"] == "needs_confirmation"
    assert any(o["topic"] == "contact" and o["decision"] == "reviewable" for o in row["topic_decisions"])
    assert any(o["topic"] == "accessibility" and o["decision"] == "needs_confirmation" for o in row["topic_decisions"])


@pytest.mark.live
@pytest.mark.skipif(os.getenv("RUN_LIVE_NAT") != "1", reason="실제 Nemotron 호출은 RUN_LIVE_NAT=1에서만")
def test_live_agent_reviews_experimental_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    trace = flow.agent_traces["cand-t"]
    assert not flow.agent_errors
    assert not flow.rule_finishes
    assert any(item["tool"] == "use_experimental_structure" and item["accepted"] for item in trace)
    assert trace[0]["tool"] == "check_input"
    assert flow.states["cand-t"].status == "completed"


def test_a_control_candidates_error_is_not_charged_to_the_measured_one(tmp_path, monkeypatch):
    """측정 행은 후보 하나의 기록이다. 같은 흐름의 다른 후보 오류를 끌어오면 안 된다."""
    from logic import measure_agent

    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    flow.agent_errors = {"filler": "에이전트 실행 오류: 429 Too Many Requests"}
    monkeypatch.setattr(measure_agent, "run_flow", lambda request: (output, flow))

    row = measure_agent._one("trastuzumab", "nat")

    assert row["agent_error"] is None
    assert row["rate_limited"] is False


def test_the_measurement_row_separates_recovered_429_from_a_failed_run(tmp_path, monkeypatch):
    """인계서 우선순위 2: 복구된 429·빈 200 응답·미처리 오류를 각각 센다."""
    from logic import measure_agent, nat_model

    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())

    def _run(_request_unused):
        for status, emitted in ((429, False), (200, False), (200, True)):
            nat_model.record_attempt(status=status, attempt=1, emitted=emitted,
                                     started_at="now", headers={})
        return output, flow

    monkeypatch.setattr(measure_agent, "run_flow", _run)

    row = measure_agent._one("trastuzumab", "nat")

    assert row["http_statuses"] == {"200": 2, "429": 1}
    assert row["http_429_recovered"] is True
    assert row["http_empty_responses"] == 1
    assert row["rate_limited"] is False
