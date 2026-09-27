"""모델의 선택이 실제 실행을 바꾸는지 확인한다.

판단부를 붙여 놓고 결과가 규칙 때와 똑같다면 장식일 뿐이다. 여기서
보는 것은 하나다 — **규칙이라면 하지 않았을 일을 모델이 시키면 하는가.**

그래서 시험은 규칙과 반대되는 답을 모델에게 시킨다. 일치하는 실험
구조가 있어 규칙은 예측을 건너뛸 자리에서 모델이 "예측하라"고 하면
Boltz-2가 실제로 불려야 하고, 규칙이 예측할 자리에서 "보류하라"고
하면 불리지 않아야 한다.

NVIDIA를 실제로 부르지 않는다.
"""

from __future__ import annotations

import json

import pytest

from logic import structures
from logic.agent import Decider
from logic.flow import run_flow
from logic.nvidia_client import CallFailed, MissingCredentials
from logic.tests.test_flow import (
    PERTUZUMAB,
    TRASTUZUMAB,
    _long,
    candidate,
    entity_sequence,
    make_request,
)

PREDICTED = {
    "structures": [{"structure": "data_x\n#\n"}],
    "confidence_scores": [0.87],
}


class ScriptedClient:
    """predict_complex는 세어 두고, chat은 미리 정한 답을 돌려준다."""

    def __init__(self, *choices: str):
        self._choices = list(choices)
        self.predictions = 0
        self.asked: list[str] = []

    def predict_complex(self, polymers, **kwargs):
        self.predictions += 1
        return PREDICTED

    def chat(self, model, messages, **kwargs):
        self.asked.append(messages[1]["content"])
        if not self._choices:
            raise MissingCredentials("대본이 끝났다.")
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"action": self._choices.pop(0), "reason": "대본대로 골랐다."}
                        )
                    }
                }
            ]
        }


# 계약이 후보 2건 이상을 요구한다. 판단을 보는 후보는 하나로 두고,
# 나머지 한 건은 입력 검사에서 바로 걸리게 해서 판단부를 거치지 않게 한다.
# 그래야 대본의 답과 판단 순서가 어긋나지 않는다.
def _filler():
    return candidate("filler", "입력 오류 후보", ">bad\n123", ">bad\n456")


def _matched_candidate():
    """공개 구조와 정확히 일치하는 후보. 규칙이라면 예측을 건너뛴다."""
    return [
        candidate(
            "trastuzumab",
            "Trastuzumab Fab",
            entity_sequence(TRASTUZUMAB, "heavy"),
            entity_sequence(TRASTUZUMAB, "light"),
        ),
        _filler(),
    ]


def _unmatched_candidate():
    """일치하는 공개 구조가 없는 후보. 규칙이라면 예측한다."""
    return [
        candidate(
            "variant",
            "가상 변이 후보",
            _long("QVQLVESGGG", 230),
            _long("DIQMTQSPSS", 210),
        ),
        _filler(),
    ]


def _mine(output, cid, key="opinions"):
    return [o for o in output["result"][key] if o["candidate_id"] == cid]


def test_the_model_can_order_a_prediction_the_rule_would_have_skipped(tmp_path):
    """일치하는 실험 구조가 있어도 모델이 교차 확인을 시키면 실제로 부른다."""
    client = ScriptedClient("predict", "reviewable")

    output, flow = run_flow(
        make_request(_matched_candidate(), tmp_path, target_fasta=_long("HERTWASEQ", 300)),
        client=client,
        decider=Decider(client, model="test-model"),
    )

    assert client.predictions == 1, "모델이 예측을 시켰는데 부르지 않았다"
    kinds = {s["kind"] for s in _mine(output, "trastuzumab", "structures")}
    assert kinds == {"predicted"}


def test_the_model_can_hold_a_candidate_the_rule_would_have_predicted(tmp_path):
    """서열이 길어 규칙은 예측할 자리에서, 모델이 보류하면 호출하지 않는다."""
    client = ScriptedClient("hold")

    output, flow = run_flow(
        make_request(_unmatched_candidate(), tmp_path, target_fasta=_long("HERTWASEQ", 300)),
        client=client,
        decider=Decider(client, model="test-model"),
    )

    assert client.predictions == 0, "보류하기로 했는데 NVIDIA를 불렀다"
    assert flow.run_status() == "partial"
    opinions = _mine(output, "variant")
    assert [o["decision"] for o in opinions] == ["hold"]
    assert "test-model" in opinions[0]["reason"]


def test_the_rule_result_says_it_came_from_the_rule(tmp_path):
    """모델을 못 부르면 화면 문구가 모델 판단인 척하지 않아야 한다."""
    client = ScriptedClient()  # 대본 없음 = 모델 사용 불가

    output, _ = run_flow(
        make_request(_matched_candidate(), tmp_path, target_fasta=_long("HERTWASEQ", 300)),
        client=client,
        decider=Decider(client, model="test-model"),
    )

    reason = _mine(output, "trastuzumab")[0]["reason"]
    assert "판단: 규칙" in reason
    assert "test-model" not in reason


def test_the_state_we_measured_is_what_the_model_was_asked_about(tmp_path):
    """모델이 상태를 상상하지 않도록, 조회 결과를 그대로 넣어 묻는다."""
    client = ScriptedClient("use_experimental", "reviewable")

    run_flow(
        make_request(_matched_candidate(), tmp_path, target_fasta=_long("HERTWASEQ", 300)),
        client=client,
        decider=Decider(client, model="test-model"),
    )

    first = client.asked[0]
    assert TRASTUZUMAB in first
    assert "중쇄 서열 정확히 일치: 예" in first
    # 두 번째 판단은 계산된 근거를 보고 한다.
    assert "interface_contact_residues" in client.asked[1]


def test_every_decision_is_recorded_for_the_run(tmp_path):
    """시연에서 '에이전트가 판단했다'고 말하려면 남아 있어야 한다."""
    client = ScriptedClient("use_experimental", "needs_confirmation")
    decider = Decider(client, model="test-model")

    run_flow(
        make_request(_matched_candidate(), tmp_path, target_fasta=_long("HERTWASEQ", 300)),
        client=client,
        decider=decider,
    )

    steps = [d.step for d in decider.decisions]
    assert steps == ["structure_source", "review_opinion"]
    assert all(d.decided_by == "model" for d in decider.decisions)


def test_the_rule_agrees_with_the_model_instead_of_contradicting_it(tmp_path):
    """모델이 죽어도 결론이 뒤집히지 않아야 한다.

    실측 4회 중 1회에서 trastuzumab이 needs_confirmation 대신 reviewable로
    나왔다. 모델이 503으로 죽어 규칙이 대신 골랐고, 그 규칙의 입장이
    모델과 달랐기 때문이다. 같은 입력에 NVIDIA 서버 상태에 따라 다른
    결론이 나오면 시연에서 재현이 안 된다.

    지금 흐름에는 충돌·표면 노출이 늘 미계산으로 남는다. 규칙도 모델처럼
    그 자리에서 확인이 필요하다고 봐야 한다.
    """
    client = ScriptedClient()  # 모델 사용 불가 = 규칙만으로 판단

    output, _ = run_flow(
        make_request(_matched_candidate(), tmp_path, target_fasta=_long("HERTWASEQ", 300)),
        client=client,
        decider=Decider(client, model="test-model"),
    )

    opinion = _mine(output, "trastuzumab")[0]
    assert opinion["decision"] == "needs_confirmation"
    # 근거를 계산하긴 했다. 아무것도 못 한 것과는 다르다.
    measured = [
        e
        for e in _mine(output, "trastuzumab", "evidence")
        if e["measurement_state"] == "measured"
    ]
    assert measured, "근거를 하나도 계산하지 못했다면 다른 문제다"
    assert opinion["limitations"], "무엇이 모자란지 남아 있어야 한다"


def test_model_cannot_approve_unmeasured_evidence_in_the_non_nat_path(tmp_path):
    client = ScriptedClient("use_experimental", "reviewable")
    output, _ = run_flow(make_request(_matched_candidate(), tmp_path), client=client,
                         decider=Decider(client, model="test-model"))
    opinion = _mine(output, "trastuzumab")[0]
    assert opinion["decision"] == "needs_confirmation"
    assert opinion["limitations"]


def test_the_model_is_told_whether_prediction_is_even_possible(tmp_path):
    """구조 검색 결과만 주면 "일치 없음"을 "자료 부족"으로 읽는다.

    실제로 그렇게 보류한 실행을 화면에서 봤다. 서열은 충분히 길었는데
    모델에게는 그걸 알 방법이 없었다.
    """
    client = ScriptedClient("predict", "needs_confirmation")

    run_flow(
        make_request(_unmatched_candidate(), tmp_path, target_fasta=_long("HERTWASEQ", 300)),
        client=client,
        decider=Decider(client, model="test-model"),
    )

    asked = client.asked[0]
    for label in ("표적", "중쇄", "경쇄"):
        assert f"{label} 서열 길이" in asked
    assert "예측 입력으로 충분" in asked


def test_the_raw_server_error_body_does_not_end_up_on_screen(tmp_path):
    """화면에서 {"error":{"message":...}}가 문장 안에 박힌 것을 봤다.

    규칙으로 갔다는 사실은 남기되, 서버 응답 본문까지 보여줄 필요는 없다.
    자세한 내용은 call_log.jsonl에 있다.
    """

    class Overloaded(ScriptedClient):
        def chat(self, model, messages, **kwargs):
            raise CallFailed(
                'nemotron.chat 호출이 HTTP 503로 실패했다: '
                '{"error":{"message":"Service temporarily overloaded",'
                '"type":"Service Unavailable","code":503}}',
                status=503,
            )

    client = Overloaded()
    output, _ = run_flow(
        make_request(_matched_candidate(), tmp_path, target_fasta=_long("HERTWASEQ", 300)),
        client=client,
        decider=Decider(client, model="test-model"),
    )

    reason = _mine(output, "trastuzumab")[0]["reason"]
    assert "판단: 규칙" in reason, "규칙으로 갔다는 사실은 남아야 한다"
    assert '"code":503' not in reason
    assert len(reason) < 200
