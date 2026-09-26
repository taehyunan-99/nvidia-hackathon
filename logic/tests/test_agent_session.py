"""관문과 도구. 모델 없이 도구를 직접 불러 본다. NVIDIA를 부르지 않는다."""

from __future__ import annotations

import pytest

from logic.agent_session import CandidateSession, CandidateTools, allowed_tools
from logic.flow import Flow
from logic.tests.test_flow import TRASTUZUMAB, _long, candidate, entity_sequence, make_request
from logic.tests.test_flow_decisions import ScriptedClient


# make_request의 표적 서열 기본값은 None이다. 예측 경로에는 50자 이상이 필요하다.
TARGET = _long("HERTWOSEQ", 300)


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
    assert session.calls[-1] == {"tool": "predict_structure", "accepted": False}


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
    opinion = next(o for o in flow.opinions if o["candidate_id"] == "cand-t")
    assert opinion["decision"] == "needs_confirmation"
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
