"""세션에서 이어 가는 규칙 경로를 확인한다. NVIDIA를 부르지 않는다."""

from __future__ import annotations

from logic import structures
from logic.agent_session import CandidateSession
from logic.flow import Flow
from logic.tests.test_flow import TRASTUZUMAB, _long, candidate, entity_sequence, make_request
from logic.tests.test_flow_decisions import ScriptedClient

# make_request의 표적 서열 기본값은 None이다. 예측 경로에는 50자 이상이 필요하다.
TARGET = _long("HERTWASEQ", 300)

# 계약이 후보 2건 이상을 요구한다(test_flow_decisions.py와 같은 이유). 세션은
# 그 중 하나만 감싸므로 나머지 한 건은 입력 검사에서 바로 걸리는 채움용이다.
def _filler():
    return candidate("filler", "입력 오류 후보", ">bad\n123", ">bad\n456")


def _trastuzumab():
    return candidate(
        "cand-t", "trastuzumab",
        entity_sequence(TRASTUZUMAB, "heavy"), entity_sequence(TRASTUZUMAB, "light"),
    )


def test_resume_from_scratch_matches_rule_run(tmp_path):
    client = ScriptedClient()  # chat 대본 없음 → 판단부는 규칙으로 간다
    flow = Flow(make_request([_trastuzumab(), _filler()], tmp_path), client=client)
    session = CandidateSession(_trastuzumab())
    flow._resume(session)
    assert session.terminal == "completed"
    assert flow.states["cand-t"].status == "completed"
    assert client.predictions == 0


def test_continue_after_prediction_does_not_predict_again(tmp_path):
    variant = candidate("cand-v", "variant", _long("QVQLVESGG"), _long("DIQMTQSPS"))
    client = ScriptedClient()
    flow = Flow(make_request([variant, _filler()], tmp_path, target_fasta=TARGET), client=client)
    session = CandidateSession(variant)
    session.input_checked = True
    session.match = structures.find_structure(variant["heavy_chain_fasta"], variant["light_chain_fasta"])
    flow._emit("cand-v", "input_mapping", "completed", None)
    session.structure_id = flow._predict("cand-v", variant, session.match)
    assert client.predictions == 1

    flow._continue_by_rule(session, "모델 호출이 503으로 실패했다")

    assert client.predictions == 1  # 규칙 마무리가 예측을 다시 부르지 않는다
    assert session.terminal is not None
    assert any("진행: 규칙 — 모델 호출이 503으로 실패했다" in (o["reason"] or "")
               for o in flow.opinions if o["candidate_id"] == "cand-v")


def test_continue_on_terminal_session_changes_nothing(tmp_path):
    flow = Flow(make_request([_trastuzumab(), _filler()], tmp_path), client=ScriptedClient())
    session = CandidateSession(_trastuzumab())
    flow._resume(session)
    before = list(flow.opinions)
    flow._continue_by_rule(session, "상한")
    assert flow.opinions == before
