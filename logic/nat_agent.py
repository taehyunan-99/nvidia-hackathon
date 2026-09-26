"""CandidateTools를 NAT 함수로 등록하고 후보 하나를 NAT 에이전트로 돌린다.

NAT 도구는 YAML 설정으로 만들어지므로 인자로 세션을 넘길 수 없다.
실행 직전 contextvars에 현재 도구 묶음을 넣고, 도구는 그것을 꺼내 쓴다.
asyncio.to_thread는 context를 복사하므로 스레드 안에서도 보인다.
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
from pathlib import Path
from typing import Any

from .agent_session import TOOL_NAMES, CandidateSession, CandidateTools
from .env import load_env

CONFIG_PATH = Path(__file__).with_name("nat_workflow.yml")
_CURRENT: contextvars.ContextVar[CandidateTools] = contextvars.ContextVar("her2_tools")

try:
    from nat.builder.builder import Builder
    from nat.builder.function_info import FunctionInfo
    from nat.cli.register_workflow import register_function
    from nat.data_models.function import FunctionBaseConfig
    from nat.runtime.loader import load_workflow

    NAT_AVAILABLE = True
except ImportError:  # 로컬 테스트·규칙 모드는 NAT 없이도 돈다
    NAT_AVAILABLE = False


def _tools() -> CandidateTools:
    return _CURRENT.get()


if NAT_AVAILABLE:

    class _CheckInput(FunctionBaseConfig, name="her2_check_input"):
        pass

    class _Lookup(FunctionBaseConfig, name="her2_lookup_public_structure"):
        pass

    class _UseExperimental(FunctionBaseConfig, name="her2_use_experimental_structure"):
        pass

    class _Predict(FunctionBaseConfig, name="her2_predict_structure"):
        pass

    class _Compare(FunctionBaseConfig, name="her2_compare_structure"):
        pass

    class _Submit(FunctionBaseConfig, name="her2_submit_opinion"):
        pass

    class _Hold(FunctionBaseConfig, name="her2_hold_candidate"):
        pass

    @register_function(config_type=_CheckInput)
    async def _reg_check(_c, _b: Builder):
        async def check_input(note: str = "") -> str:
            """후보 입력(서열 문자·분석 구간·표적)을 검사한다. 가장 먼저 부른다."""
            return await asyncio.to_thread(_tools().check_input)
        yield FunctionInfo.from_fn(check_input, description=check_input.__doc__)

    @register_function(config_type=_Lookup)
    async def _reg_lookup(_c, _b: Builder):
        async def lookup_public_structure(note: str = "") -> str:
            """공개 실험 구조와 서열이 일치하는지 조회하고 확인된 사실을 돌려준다."""
            return await asyncio.to_thread(_tools().lookup_public_structure)
        yield FunctionInfo.from_fn(lookup_public_structure, description=lookup_public_structure.__doc__)

    @register_function(config_type=_UseExperimental)
    async def _reg_use(_c, _b: Builder):
        async def use_experimental_structure(reason: str) -> str:
            """중쇄·경쇄가 공개 구조와 정확히 일치할 때 그 실험 구조로 검토한다. 예측을 건너뛴다."""
            return await asyncio.to_thread(_tools().use_experimental_structure, reason)
        yield FunctionInfo.from_fn(use_experimental_structure, description=use_experimental_structure.__doc__)

    @register_function(config_type=_Predict)
    async def _reg_predict(_c, _b: Builder):
        async def predict_structure(reason: str) -> str:
            """표적·중쇄·경쇄 서열을 Boltz-2에 보내 복합체 구조를 새로 만든다. 공개 구조가 없을 때의 정상 경로다."""
            return await asyncio.to_thread(_tools().predict_structure, reason)
        yield FunctionInfo.from_fn(predict_structure, description=predict_structure.__doc__)

    @register_function(config_type=_Compare)
    async def _reg_compare(_c, _b: Builder):
        async def compare_structure(note: str = "") -> str:
            """확보한 구조에서 접촉 잔기 등 근거를 계산하고 확인된 사실을 돌려준다."""
            return await asyncio.to_thread(_tools().compare_structure)
        yield FunctionInfo.from_fn(compare_structure, description=compare_structure.__doc__)

    @register_function(config_type=_Submit)
    async def _reg_submit(_c, _b: Builder):
        async def submit_opinion(decision: str, reason: str) -> str:
            """검토 의견을 기록하고 끝낸다. decision은 reviewable 또는 needs_confirmation."""
            return await asyncio.to_thread(_tools().submit_opinion, decision, reason)
        yield FunctionInfo.from_fn(submit_opinion, description=submit_opinion.__doc__)

    @register_function(config_type=_Hold)
    async def _reg_hold(_c, _b: Builder):
        async def hold_candidate(reason: str) -> str:
            """예측 입력으로 쓸 서열이 없거나 너무 짧을 때만 검토를 보류하고 끝낸다."""
            return await asyncio.to_thread(_tools().hold_candidate, reason)
        yield FunctionInfo.from_fn(hold_candidate, description=hold_candidate.__doc__)


def _prompt(session: CandidateSession) -> str:
    c = session.candidate
    return (f"후보 {c['candidate_id']}({c.get('display_name') or c['candidate_id']})의 검토를 진행해라. "
            "check_input부터 시작한다.")


def _run_sync(coro) -> Any:
    """이미 이벤트 루프가 도는 스레드(예: async 서버)에서 불려도 동작하게 한다."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict[str, Any] = {}

    def _target():
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # 호출한 쪽에서 다시 던진다
            box["error"] = exc

    t = threading.Thread(target=_target)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box.get("value")


def run_candidate(flow, session: CandidateSession, *, config_path: Path = CONFIG_PATH) -> str | None:
    """후보 하나를 NAT 에이전트로 돌린다. 끝내지 못했으면 규칙 마무리 사유를 돌려준다."""
    load_env()  # NAT의 nim LLM이 os.environ의 NVIDIA_API_KEY를 읽는다.
    tools = CandidateTools(flow, session)

    async def _go() -> str:
        token = _CURRENT.set(tools)
        try:
            async with load_workflow(config_path) as sm:
                async with sm.run(_prompt(session)) as runner:
                    return await runner.result(to_type=str)
        finally:
            _CURRENT.reset(token)

    try:
        final = _run_sync(_go())
    except Exception as exc:
        return f"에이전트 실행 오류: {type(exc).__name__}: {exc}"[:200]
    if session.terminal:
        return None
    if "could not produce a final answer" in (final or ""):
        return "에이전트 반복 상한"
    return "에이전트가 종료 도구 없이 끝났다"
