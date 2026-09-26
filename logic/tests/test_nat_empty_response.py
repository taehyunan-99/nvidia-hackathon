"""빈 응답 재시도가 실제로 회복시키는지 (nat_workflow.yml max_empty_response_retries).

왜 이 테스트가 필요한가. 기존 `test_workflow_config_loads_with_registered_tools`는
설정값이 2라는 것만 본다. 그 값으로 에이전트가 실제로 회복하는지는 확인하지
못했고, 실측으로 확인하려는 시도는 두 번 막혔다 —

1. NVIDIA API가 429로 호출을 거부했다(2026-09-26 다섯 차례).
2. 더 근본적으로, 그날 모델은 빈 응답을 한 번도 내지 않았다(로그 0건).
   고치려는 현상이 발생하지 않으면 수리 효과는 측정할 수 없다. 베이스라인
   4/15는 모델이 빈 응답을 내던 시점의 측정이다.

그래서 기다리는 대신 빈 응답을 주입한다. 모델을 부르지 않으므로 한도·유료
호출과 무관하고, 모델 기분에 좌우되지 않는다. 확인하는 것은 "우리가 고른
설정값에서 NAT의 재시도가 루프를 살려 내는가"다.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("nat")

from langchain_core.messages import AIMessageChunk, HumanMessage  # noqa: E402
from langchain_core.runnables import Runnable  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

from nat.plugins.langchain.agent.tool_calling_agent.agent import (  # noqa: E402
    ToolCallAgentGraph,
    ToolCallAgentGraphState,
)


@tool
def noop_tool(note: str = "") -> str:
    """이 시험에서는 부르지 않는다. bind_tools에 넘길 목록을 채우기 위한 것이다."""
    return "ok"


class ScriptedLLM(Runnable):
    """미리 정한 응답을 순서대로 내놓는 가짜 모델. NVIDIA를 부르지 않는다.

    NAT는 `llm.bind_tools(tools)`로 묶은 뒤 `astream`으로 조각을 받는다.
    여기서는 조각 하나씩만 내놓는다(누적 경로는 이 시험의 대상이 아니다).
    """

    def __init__(self, responses: list[AIMessageChunk]):
        self.responses = responses
        self.calls = 0

    def bind_tools(self, tools):  # NAT가 생성자에서 부른다
        return self

    def invoke(self, input, config=None, **kwargs):  # Runnable 추상 메서드
        raise AssertionError("이 시험은 astream만 쓴다")

    async def astream(self, input, config=None, **kwargs):
        # 대본보다 많이 불리면 마지막 응답을 계속 돌려준다(전부 빈 응답 시험용).
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        yield self.responses[index]


def _empty() -> AIMessageChunk:
    return AIMessageChunk(content="")


def _answer(text: str = "검토를 진행한다.") -> AIMessageChunk:
    return AIMessageChunk(content=text)


def _graph(llm: ScriptedLLM, retries: int) -> ToolCallAgentGraph:
    return ToolCallAgentGraph(llm=llm, tools=[noop_tool], prompt="너는 검토 에이전트다.",
                              max_empty_response_retries=retries)


def _run_agent_node(llm: ScriptedLLM, retries: int) -> ToolCallAgentGraphState:
    graph = _graph(llm, retries)
    state = ToolCallAgentGraphState(messages=[HumanMessage(content="후보 검토를 진행해라.")])
    return asyncio.run(graph.agent_node(state))


def _shipped_retries() -> int:
    """실제로 배포되는 nat_workflow.yml의 값. 테스트가 제 값을 따로 들고 있으면
    yml을 0으로 되돌려도 이 시험이 통과해 버린다. 실물과 묶어 둔다."""
    from nat.runtime.loader import load_config

    from logic import nat_agent
    return load_config(nat_agent.CONFIG_PATH).workflow.max_empty_response_retries


def test_empty_response_is_retried_and_the_loop_recovers():
    """빈 응답 1회 뒤 정상 응답이 오면, 예외 없이 그 응답으로 진행한다.

    재시도 횟수는 실제 `nat_workflow.yml`에서 읽는다. 값이 0이면 첫 빈 응답에서
    바로 예외가 나고 후보는 규칙 마무리로 떨어진다(재측정 15회 중 4회가 그랬다).
    """
    retries = _shipped_retries()
    assert retries >= 1, f"nat_workflow.yml의 max_empty_response_retries가 {retries}다 — 빈 응답에서 회복하지 못한다"
    llm = ScriptedLLM([_empty(), _answer("공개 구조를 조회한다.")])
    state = _run_agent_node(llm, retries=retries)

    assert llm.calls == 2, "첫 호출이 비었으면 한 번 더 불러야 한다"
    assert "공개 구조를 조회한다." in str(state.messages[-1].content)


def test_without_retries_a_single_empty_response_breaks_the_run():
    """대조군. 재시도가 0이면 같은 상황에서 예외가 난다 — 설정이 실제로 효과를
    내는 것이지, 빈 응답이 원래 무해한 것이 아니라는 확인이다."""
    llm = ScriptedLLM([_empty(), _answer("이 응답까지 가지 못한다.")])
    with pytest.raises(RuntimeError, match="empty response"):
        _run_agent_node(llm, retries=0)
    assert llm.calls == 1, "재시도가 없으면 한 번만 부르고 끝난다"


def test_retries_are_bounded_and_give_up_with_a_clear_error():
    """계속 비어 있으면 무한히 재시도하지 않는다. 2회까지만 더 부르고 포기한다.

    포기할 때 나는 예외는 `nat_agent.run_candidate`가 잡아 규칙 마무리 사유로
    바꾼다. 즉 최악의 경우에도 후보는 결과 없이 끝나지 않는다.
    """
    llm = ScriptedLLM([_empty()])
    with pytest.raises(RuntimeError, match="still returning empty responses"):
        _run_agent_node(llm, retries=2)
    assert llm.calls == 3, "첫 호출 1회 + 재시도 2회"
