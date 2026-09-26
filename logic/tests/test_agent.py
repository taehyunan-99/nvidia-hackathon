"""판단부 검증.

모델에게 분기를 맡기면 새 위험이 생긴다. 없는 선택지를 고르거나, 없는
숫자를 만들어 설명에 넣거나, 아예 답을 못 하거나. 여기서 보는 것은
그 셋을 실제로 막는가, 그리고 **막았다는 사실이 기록에 남는가**다.

조용히 규칙으로 되돌아가는 것이 가장 나쁘다. 그러면 화면에는 모델이
판단한 것처럼 보이는데 실제로는 아니다.

NVIDIA를 실제로 부르지 않는다. chat을 가짜로 바꿔서 본다.
"""

from __future__ import annotations

import json

import pytest

from logic.agent import Decider, Option, invented_numbers, parse_choice
from logic.nvidia_client import CallFailed, MissingCredentials, NvidiaClient

OPTIONS = [
    Option("use_experimental", "공개 실험 구조로 검토한다."),
    Option("predict", "Boltz-2로 복합체를 예측한다."),
    Option("hold", "자료가 모자라 보류한다."),
]
FACTS = ["중쇄 서열이 1N8Z와 정확히 일치한다.", "표적 서열 길이는 624자다."]


@pytest.fixture
def decider(tmp_path):
    return Decider(NvidiaClient(tmp_path, api_key="test-key"), model="test-model")


def _answers(decider, monkeypatch, content):
    """모델이 content를 돌려주게 한다. 보낸 프롬프트도 모아 둔다."""
    sent: list[dict] = []

    def fake_chat(model, messages, **kwargs):
        sent.append({"model": model, "messages": messages, **kwargs})
        if isinstance(content, Exception):
            raise content
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(decider.client, "chat", fake_chat)
    return sent


def _choose(decider, default="predict"):
    return decider.choose(
        "structure_source",
        question="이 후보를 어떻게 검토할 것인가?",
        facts=FACTS,
        options=OPTIONS,
        default=default,
    )


def test_the_model_picks_the_branch(decider, monkeypatch):
    """규칙이 predict를 고를 자리에서 모델이 다른 길을 고를 수 있어야 한다."""
    sent = _answers(
        decider,
        monkeypatch,
        json.dumps({"action": "use_experimental", "reason": "서열이 그대로 일치한다."}),
    )

    decision = _choose(decider, default="predict")

    assert decision.action == "use_experimental"
    assert decision.decided_by == "model"
    assert decision.model == "test-model"
    assert decision.fallback_reason is None
    assert sent[0]["temperature"] == 0.0


def test_the_facts_we_measured_are_what_the_model_sees(decider, monkeypatch):
    """모델이 스스로 상태를 상상하지 않게, 사실을 프롬프트에 넣어 보낸다."""
    sent = _answers(
        decider, monkeypatch, json.dumps({"action": "predict", "reason": "일치가 없다."})
    )

    _choose(decider)

    prompt = sent[0]["messages"][1]["content"]
    for fact in FACTS:
        assert fact in prompt
    for option in OPTIONS:
        assert option.action in prompt


def test_an_action_we_did_not_offer_is_refused(decider, monkeypatch):
    """모델이 만들어낸 행동을 실행하면 허용 범위 밖으로 나간다."""
    _answers(
        decider,
        monkeypatch,
        json.dumps({"action": "publish_to_pdb", "reason": "좋아 보인다."}),
    )

    decision = _choose(decider, default="hold")

    assert decision.action == "hold"
    assert decision.decided_by == "rule"
    assert "선택지에 없는" in decision.fallback_reason


def test_a_number_the_model_invented_throws_out_the_whole_decision(decider, monkeypatch):
    """설명에 없는 수치가 있으면 고른 행동까지 버린다.

    행동만 쓰고 설명을 갈아 끼우면, 나중에 어디까지가 근거였는지
    구분할 수 없다.
    """
    _answers(
        decider,
        monkeypatch,
        json.dumps(
            {"action": "use_experimental", "reason": "접촉 잔기가 42개로 충분하다."}
        ),
    )

    decision = _choose(decider, default="predict")

    assert decision.action == "predict"
    assert decision.decided_by == "rule"
    assert "42" in decision.fallback_reason


def test_a_number_that_came_from_the_facts_is_allowed(decider, monkeypatch):
    """사실에 있는 값을 인용하는 것은 막지 않는다. 그게 근거다."""
    _answers(
        decider,
        monkeypatch,
        json.dumps({"action": "predict", "reason": "표적 624자는 예측에 충분하다."}),
    )

    decision = _choose(decider)

    assert decision.decided_by == "model"
    assert "624" in decision.reason


@pytest.mark.parametrize(
    "failure",
    [
        MissingCredentials("키가 없다"),
        CallFailed("HTTP 429", status=429),
        "죄송합니다, JSON이 아닌 답변입니다.",
        "",
    ],
)
def test_the_flow_keeps_going_when_the_model_cannot_answer(decider, monkeypatch, failure):
    """모델이 죽어도 검토는 끝나야 한다. 다만 규칙으로 갔다고 남긴다."""
    _answers(decider, monkeypatch, failure)

    decision = _choose(decider, default="hold")

    assert decision.action == "hold"
    assert decision.decided_by == "rule"
    assert decision.fallback_reason


def test_every_decision_is_kept_with_who_made_it(decider, monkeypatch):
    """화면이 '모델이 판단했다'고 말하려면 근거가 남아 있어야 한다."""
    _answers(decider, monkeypatch, json.dumps({"action": "hold", "reason": "자료 부족."}))
    _choose(decider)
    _answers(decider, monkeypatch, "형식을 지키지 않은 답")
    _choose(decider)

    records = [d.to_record() for d in decider.decisions]

    assert [r["decided_by"] for r in records] == ["model", "rule"]
    assert records[0]["model"] == "test-model"
    assert records[1]["model"] is None
    assert records[0]["facts"] == FACTS


def test_a_default_outside_the_options_is_a_programming_error(decider):
    """규칙 쪽 기본값도 허용 목록 안에 있어야 한다."""
    with pytest.raises(AssertionError):
        _choose(decider, default="delete_everything")


def test_reasoning_text_around_the_json_is_tolerated(decider, monkeypatch):
    """lightning 모델은 실측에서 사고 과정을 답변에 섞어 보냈다."""
    _answers(
        decider,
        monkeypatch,
        'Here is my thinking...\n```json\n{"action": "hold", "reason": "자료 부족."}\n```\n끝.',
    )

    decision = _choose(decider)

    assert decision.action == "hold"
    assert decision.decided_by == "model"


def test_invented_numbers_compares_against_every_fact():
    assert invented_numbers("4.5 Å 기준 39개", ["4.5 Å", "39개를 골랐다"]) == []
    assert invented_numbers("잔기 40개", ["39개를 골랐다"]) == ["40"]


def test_parse_choice_refuses_an_empty_reason():
    assert parse_choice(json.dumps({"action": "hold", "reason": "  "}), {"hold"}) is None
