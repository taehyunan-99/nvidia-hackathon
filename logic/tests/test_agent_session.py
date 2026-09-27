"""관문과 도구. 모델 없이 도구를 직접 불러 본다. NVIDIA를 부르지 않는다."""

from __future__ import annotations

import pytest

from logic import structures
from logic.agent_session import CandidateSession, CandidateTools, allowed_tools
from logic.flow import Flow
from logic.tests.test_flow import TRASTUZUMAB, _long, candidate, entity_sequence, make_request
from logic.tests.test_flow_decisions import ScriptedClient


TARGET = structures.her2_target_sequence()


# 계약이 후보 2건 이상을 요구한다(test_flow_resume.py와 같은 이유). 세션은
# 그 중 하나만 감싸므로 나머지 한 건은 입력 검사에서 바로 걸리는 채움용이다.
def _filler():
    return candidate("filler", "입력 오류 후보", ">bad\n123", ">bad\n456")


def _setup(tmp_path, cand):
    client = ScriptedClient()
    flow = Flow(make_request([cand, _filler()], tmp_path, target_fasta=TARGET), client=client)
    session = CandidateSession(cand)
    return client, flow, session, CandidateTools(flow, session)


def _trastuzumab():
    return candidate("cand-t", "trastuzumab",
                     entity_sequence(TRASTUZUMAB, "heavy"), entity_sequence(TRASTUZUMAB, "light"))


def _variant():
    return candidate("cand-v", "variant", _long("QVQLVESGG"), _long("DIQMTQSPS"))


def test_constructing_tools_marks_candidate_running(tmp_path):
    _, flow, session, _ = _setup(tmp_path, _trastuzumab())
    assert flow.states[session.cid].status == "running"


def test_first_only_check_input_is_allowed(tmp_path):
    _, _, session, _ = _setup(tmp_path, _trastuzumab())
    assert allowed_tools(session) == {"check_input"}


def test_predict_before_check_is_refused_without_calling_boltz(tmp_path):
    client, _, session, tools = _setup(tmp_path, _variant())
    out = tools.predict_structure("바로 예측한다")
    assert out.startswith("거부:")
    assert "check_input" in out  # 지금 가능한 도구를 알려 준다
    assert client.predictions == 0
    assert session.input_checked is False
    last = session.calls[-1]
    assert last["tool"] == "predict_structure"
    assert last["accepted"] is False
    assert last["note"].startswith("거부:")


def test_experimental_path_end_to_end(tmp_path):
    client, flow, session, tools = _setup(tmp_path, _trastuzumab())
    assert not tools.check_input().startswith("거부")
    facts = tools.lookup_public_structure()
    assert "1N8Z" in facts
    assert allowed_tools(session) >= {"use_experimental_structure"}
    tools.use_experimental_structure("공개 실험 구조가 두 사슬 모두 일치한다.")
    tools.compare_structure()
    out = tools.submit_opinion("needs_confirmation", "충돌·표면 노출이 미계산이라 확인이 필요하다.")
    assert not out.startswith("거부")
    assert session.terminal == "completed"
    assert client.predictions == 0
    assert flow.states["cand-t"].status == "completed"
    opinion = next(o for o in flow.opinions if o["candidate_id"] == "cand-t" and o["topic"] == "contact")
    assert opinion["decision"] == "reviewable"
    assert all(o["decision"] == "needs_confirmation" for o in flow.opinions if o["topic"] in {"clash", "accessibility"})
    assert "(판단: " in opinion["reason"]


def test_prediction_path_calls_boltz_once(tmp_path):
    client, _, session, tools = _setup(tmp_path, _variant())
    tools.check_input()
    tools.lookup_public_structure()
    assert "use_experimental_structure" not in allowed_tools(session)
    tools.predict_structure("일치하는 공개 구조가 없어 새로 만든다.")
    assert client.predictions == 1
    assert session.structure_id is not None


def test_invented_number_in_opinion_is_refused(tmp_path):
    _, _, session, tools = _setup(tmp_path, _trastuzumab())
    tools.check_input(); tools.lookup_public_structure()
    tools.use_experimental_structure("일치한다.")
    tools.compare_structure()
    out = tools.submit_opinion("reviewable", "접촉 잔기 9999개로 충분하다.")
    assert out.startswith("거부:")
    assert "9999" in out
    assert session.terminal is None


def test_unknown_decision_is_refused(tmp_path):
    _, _, session, tools = _setup(tmp_path, _trastuzumab())
    tools.check_input(); tools.lookup_public_structure()
    tools.use_experimental_structure("일치한다.")
    tools.compare_structure()
    out = tools.submit_opinion("approved", "좋다.")
    assert out.startswith("거부:")
    assert session.terminal is None


def test_every_call_after_terminal_is_refused(tmp_path):
    _, flow, session, tools = _setup(tmp_path, _trastuzumab())
    tools.check_input(); tools.lookup_public_structure()
    tools.use_experimental_structure("일치한다.")
    tools.compare_structure()
    tools.submit_opinion("needs_confirmation", "확인이 필요하다.")
    before = list(flow.opinions)
    assert allowed_tools(session) == set()
    assert tools.hold_candidate("보류").startswith("거부:")
    assert tools.submit_opinion("reviewable", "다시").startswith("거부:")
    assert flow.opinions == before


def test_invalid_input_ends_failed_like_rule_mode(tmp_path):
    bad = candidate("cand-x", "bad", "QVQL123", "DIQM!!")
    _, flow, session, tools = _setup(tmp_path, bad)
    out = tools.check_input()
    assert "문자" in out
    assert session.terminal == "failed"
    assert flow.states["cand-x"].status == "failed"
    assert any(o["candidate_id"] == "cand-x" and o["decision"] == "hold" for o in flow.opinions)


def test_short_sequences_only_allow_hold(tmp_path):
    short = candidate("cand-s", "short", "QVQLVESGG", "DIQMTQSPS")
    _, _, session, tools = _setup(tmp_path, short)
    tools.check_input(); tools.lookup_public_structure()
    assert allowed_tools(session) == {"hold_candidate"}
    assert tools.predict_structure("예측").startswith("거부:")
    tools.hold_candidate("중쇄·경쇄 서열이 너무 짧다.")
    assert session.terminal == "partial"


def test_opinion_fact_sentence_shows_integer_not_39_point_0(tmp_path):
    """접촉 잔기 수는 계약을 지키려고 float로 저장된다(analysis.contact_measurement).
    모델이 읽는 문장은 "39.0residue"가 아니라 "39 residue"여야, 모델이 자연스럽게
    쓰는 "39"와 표기가 같아진다(숫자와 단위 사이는 공백으로 뗀다 — 붙이면
    "39residue"가 되어 invented_numbers의 식별자 판정에 걸려 값 주장으로 안
    보인다). value 필드 자체(계약)는 바꾸지 않는다."""
    _, flow, session, tools = _setup(tmp_path, _trastuzumab())
    tools.check_input(); tools.lookup_public_structure()
    tools.use_experimental_structure("일치한다.")
    out = tools.compare_structure()
    assert "39 residue" in out
    assert "39.0residue" not in out
    assert "39.0 residue" not in out
    facts, measured, _ = flow._opinion_facts(session.cid)
    assert any("39 residue" in f for f in facts)
    # 계약이 요구하는 숫자 값(Evidence.value)은 여전히 float 39.0이다.
    contact = next(e for e in measured if e["topic"] == "interface_contact_residues")
    assert contact["value"] == 39.0


def test_opinion_reason_may_cite_a_number_shown_earlier_by_lookup(tmp_path):
    """lookup_public_structure가 보여 준 "1N8Z"에는 숫자 "8"이 들어 있다. 모델이
    나중에 submit_opinion에서 그 숫자를 다시 쓰면, 그 단계의 facts(_opinion_facts)
    에는 없더라도 오탐으로 거부하면 안 된다 — 모델이 실제로 본 값이다
    (실측: work/measure-agent.jsonl trastuzumab "8", pertuzumab "78" 모두
    PDB ID의 숫자 부분과 일치)."""
    _, _, session, tools = _setup(tmp_path, _trastuzumab())
    tools.check_input()
    lookup_out = tools.lookup_public_structure()
    assert "1N8Z" in lookup_out
    tools.use_experimental_structure("일치한다.")
    tools.compare_structure()
    out = tools.submit_opinion("needs_confirmation", "1N8Z 접촉 잔기 39개를 확인했으나 미계산 항목을 확인해야 한다.")
    assert not out.startswith("거부:")
    assert session.terminal == "completed"


def test_unmeasured_evidence_cannot_be_submitted_as_reviewable(tmp_path):
    _, flow, session, tools = _setup(tmp_path, _trastuzumab())
    events = []
    flow._progress = events.append
    tools.check_input()
    tools.lookup_public_structure()
    tools.use_experimental_structure("일치한다.")
    reply = tools.compare_structure()
    assert '현재 허용되는 decision: needs_confirmation.' in reply
    assert 'reviewable 또는' not in reply
    assert tools.submit_opinion("reviewable", "추가 검증이 필요 없다.").startswith("거부:")
    assert 'needs_confirmation' in next(e['activity']['reason'] for e in events
        if e['activity']['name'] == 'submit_opinion' and e['activity']['phase'] == 'rejected')
    assert session.terminal is None
    assert not flow.opinions
    assert not tools.submit_opinion("needs_confirmation", "미계산 항목을 확인해야 한다.").startswith("거부:")
    assert session.terminal == "completed"


def test_opinion_reason_with_a_truly_invented_number_is_still_refused(tmp_path):
    """앞선 도구가 보여 준 어떤 문장에도 없는 숫자는 여전히 잡는다. 축적한 facts로
    검사를 느슨하게 만들지 않는다."""
    _, _, session, tools = _setup(tmp_path, _trastuzumab())
    tools.check_input(); tools.lookup_public_structure()
    tools.use_experimental_structure("일치한다.")
    tools.compare_structure()
    out = tools.submit_opinion("reviewable", "접촉 잔기 9999개로 충분하다.")
    assert out.startswith("거부:")
    assert "9999" in out
    assert session.terminal is None


def _break_recording(flow):
    """Boltz-2 호출은 성공하고, 그 뒤 기록 단계가 중간에서 터지게 한다.

    구조 목록에 한 건을 넣은 뒤 터져서, 반쯤 쌓인 기록이 남는 상황을 만든다.
    """
    def _record(cid, response, sequences=None):
        flow.structures.append({"structure_id": f"st-{cid}-boltz2", "candidate_id": cid})
        raise OSError("디스크에 쓰지 못했다")
    flow._record_predicted = _record


def test_predict_failure_after_paid_call_ends_candidate_without_repredicting(tmp_path):
    """M1: 예측 호출이 성공한 뒤 도구가 터지면 후보를 실패로 끝내고 다시 예측하지 않는다.

    NAT의 ToolNode는 도구 예외를 모델에게 오류 메시지로 돌려준다
    (tool_calling_agent의 handle_tool_errors 기본값 True). 예외를 그대로 두면
    structure_id가 비어 있어 관문이 predict_structure를 다시 허용하고, 모델이
    다시 부르면 유료 Boltz-2가 한 번 더 나간다.
    """
    client, flow, session, tools = _setup(tmp_path, _variant())
    tools.check_input()
    tools.lookup_public_structure()
    _break_recording(flow)

    out = tools.predict_structure("일치하는 공개 구조가 없어 새로 만든다.")

    assert client.predictions == 1
    assert "OSError" in out
    assert session.terminal == "failed"
    assert flow.states[session.cid].status == "failed"
    assert flow.structures == []  # 반쯤 쌓인 기록은 되돌린다
    again = tools.predict_structure("다시 만든다.")
    assert again.startswith("거부:")
    assert client.predictions == 1


def test_rule_finish_after_predict_failure_does_not_repredict(tmp_path, monkeypatch):
    """M1: 에이전트가 그 뒤 종료 도구 없이 끝나도 규칙 마무리가 다시 예측하지 않는다."""
    from logic import nat_agent
    from logic.contract import validate
    from logic.flow import run_flow

    def _agent(flow, session, **kwargs):
        tools = CandidateTools(flow, session)
        tools.check_input()
        tools.lookup_public_structure()
        _break_recording(flow)
        tools.predict_structure("일치하는 공개 구조가 없어 새로 만든다.")
        return nat_agent._fallback_reason(session, "")

    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    monkeypatch.setattr(nat_agent, "NAT_AVAILABLE", True)
    monkeypatch.setattr(nat_agent, "run_candidate", _agent)
    client = ScriptedClient()
    output, flow = run_flow(make_request([_variant(), _filler()], tmp_path, target_fasta=TARGET),
                            client=client)

    validate(output, "LogicOutput")
    assert client.predictions == 1
    assert flow.states["cand-v"].status == "failed"


def test_prediction_step_is_never_reported_completed_when_recording_fails(tmp_path, monkeypatch):
    """M2: 기록이 터진 예측 단계를 completed로 먼저 알리면 화면이 성공으로 보인다.

    되돌리기는 기록 리스트만 자르므로, 이미 나간 진행 이벤트와 단계 상태는
    복구되지 않는다. 그러니 기록이 끝난 뒤에 완료를 알려야 한다.
    """
    def _boom(*_args, **_kwargs):
        raise OSError("근거를 쓰지 못했다")

    updates = []
    client = ScriptedClient()
    flow = Flow(make_request([_variant(), _filler()], tmp_path, target_fasta=TARGET),
                client=client, progress=updates.append)
    session = CandidateSession(_variant())
    tools = CandidateTools(flow, session)
    tools.check_input()
    tools.lookup_public_structure()
    monkeypatch.setattr(flow, "_record_confidence", _boom)

    out = tools.predict_structure("일치하는 공개 구조가 없어 새로 만든다.")

    assert client.predictions == 1
    assert "OSError" in out and session.terminal == "failed"
    steps = [(u["step_id"], u["status"]) for u in updates]
    assert ("prediction", "completed") not in steps
    assert ("prediction", "failed") in steps
    assert flow.states[session.cid].steps["prediction"]["status"] == "failed"
