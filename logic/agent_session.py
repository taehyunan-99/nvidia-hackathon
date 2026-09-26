"""후보 하나의 진행 상태와 에이전트 도구 (NAT 설계 nat-agent-loop.md 4·5절).

NAT에 의존하지 않는다. 규칙 경로(Flow._resume)와 에이전트 도구가 같은
세션을 읽고 쓰므로, 에이전트가 중간에 끊겨도 규칙이 그 자리부터 잇는다.
"""

from __future__ import annotations

import functools
import threading
from dataclasses import dataclass, field
from typing import Any

from .agent import Decision, invented_numbers
from .structures import StructureMatch


@dataclass
class CandidateSession:
    candidate: dict[str, Any]
    input_checked: bool = False
    match: StructureMatch | None = None
    lengths: dict[str, int] = field(default_factory=dict)
    structure_id: str | None = None
    compared: bool = False
    terminal: str | None = None  # "completed" | "partial" | "failed"
    calls: list[dict[str, Any]] = field(default_factory=list)
    # 모델에게 "확인된 사실"로 보여 준 문장을 도구 호출을 거치며 계속 쌓아 둔다.
    # 숫자 검사(invented_numbers)가 매번 그 단계의 facts만 보면, 이전 도구가
    # 보여 준 문장(예: lookup_public_structure의 "1N8Z")에 있던 숫자를 모델이
    # 뒤에서 다시 쓸 때 사실에 없는 것처럼 잘못 걸린다(측정: work/measure-agent.jsonl
    # trastuzumab "8", pertuzumab "78" — 둘 다 PDB ID의 숫자 부분과 일치).
    shown_facts: list[str] = field(default_factory=list)

    @property
    def cid(self) -> str:
        return self.candidate["candidate_id"]


TOOL_NAMES = (
    "check_input", "lookup_public_structure", "use_experimental_structure",
    "predict_structure", "compare_structure", "submit_opinion", "hold_candidate",
)
TERMINAL_TOOLS = frozenset({"submit_opinion", "hold_candidate"})
OPINIONS = ("reviewable", "needs_confirmation")


def _min_length() -> int:
    from .flow import MIN_CHAIN_LENGTH  # flow가 이 모듈을 import하므로 늦게 가져온다
    return MIN_CHAIN_LENGTH


def allowed_tools(s: CandidateSession) -> set[str]:
    """지금 부를 수 있는 도구. A안에서는 거부 판단, B안에서는 노출 목록으로 쓴다."""
    if s.terminal:
        return set()
    if not s.input_checked:
        return {"check_input"}
    if s.match is None:
        return {"lookup_public_structure"}
    if s.structure_id is None:
        out: set[str] = set()
        if s.lengths and all(n >= _min_length() for n in s.lengths.values()):
            out.add("predict_structure")
        if s.match.complete:
            out.add("use_experimental_structure")
        else:
            out.add("hold_candidate")
        return out
    if not s.compared:
        return {"compare_structure"}
    return {"submit_opinion"}


def _locked(method):
    """관문 확인부터 실행까지를 인스턴스 락으로 감싼다.

    NAT/langgraph의 ToolNode는 모델 응답 하나에 담긴 도구 호출을 전부
    `asyncio.gather`로 동시에 실행하고, 각 래퍼는 `asyncio.to_thread`로 그
    도구를 부른다. `CandidateTools`는 후보 하나당 하나씩 만들어지므로,
    한 후보에 대해 같은 모델 메시지가 predict_structure를 두 번 발행하면
    두 스레드가 거의 동시에 `_gate`를 통과해 Boltz-2가 중복 호출될 수
    있다(실측: 구조·기록이 두 번 남았다). 도구 메서드 전체(관문 확인 +
    행동)를 락으로 감싸 두 번째 호출이 첫 번째가 상태를 바꾼 뒤에야
    관문을 보게 만든다.
    """

    @functools.wraps(method)
    def wrapper(self: "CandidateTools", *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class CandidateTools:
    """에이전트가 부르는 도구 7개. 각 도구는 기존 Flow 단계를 그대로 쓴다."""

    def __init__(self, flow, session: CandidateSession):
        self.flow = flow
        self.s = session
        self._lock = threading.Lock()
        if not session.terminal:
            self.flow.states[self.s.cid].status = "running"

    # ---------------------------------------------------------- 관문
    def _gate(self, name: str) -> str | None:
        allowed = allowed_tools(self.s)
        if name in allowed:
            return None
        if not allowed:
            note = f"거부: 이 후보의 검토는 이미 끝났다({self.s.terminal}). 더 부를 도구가 없다."
        else:
            note = f"거부: {name}은(는) 지금 쓸 수 없다. 지금 가능한 도구: {', '.join(sorted(allowed))}."
        self.s.calls.append({"tool": name, "accepted": False, "note": note})
        return note

    def _accept(self, name: str) -> None:
        self.s.calls.append({"tool": name, "accepted": True})

    def _decision(self, step: str, action: str, reason: str, facts: list[str]) -> Decision:
        d = Decision(step=step, action=action, reason=reason, decided_by="model",
                     model=self.flow.decider.model, facts=facts)
        self.flow.decider.decisions.append(d)
        return d

    def _check_reason(self, name: str, reason: str, facts: list[str]) -> str | None:
        if not reason.strip():
            note = "거부: reason이 비어 있다. 고른 이유를 두 문장 이내로 쓴다."
            self.s.calls.append({"tool": name, "accepted": False, "note": note})
            return note
        # 이번 단계의 facts뿐 아니라, 앞선 도구가 모델에게 이미 보여 준 문장도
        # 같이 대조한다. 대화가 이어지는 한 모델은 그 값도 계속 볼 수 있다.
        invented = invented_numbers(reason, facts + self.s.shown_facts)
        if invented:
            note = (f"거부: reason에 확인된 사실에 없는 숫자가 있다: {', '.join(invented)}. "
                    "사실에 있는 값만 쓰거나 숫자를 빼고 다시 쓴다.")
            self.s.calls.append({"tool": name, "accepted": False, "note": note})
            return note
        return None

    # ---------------------------------------------------------- 도구
    @_locked
    def check_input(self) -> str:
        if (r := self._gate("check_input")):
            return r
        self._accept("check_input")
        cid = self.s.cid
        self.flow._emit(cid, "input_mapping", "running", None)
        problems = self.flow._check_input(self.s.candidate)
        self.s.input_checked = True
        if problems:
            self.flow._fail_input(cid, problems)
            self.s.terminal = "failed"
            return "입력 검사 실패. 검토를 끝냈다: " + " ".join(problems)
        return "입력 검사 통과. 다음은 lookup_public_structure로 공개 구조를 조회한다."

    @_locked
    def lookup_public_structure(self) -> str:
        if (r := self._gate("lookup_public_structure")):
            return r
        self._accept("lookup_public_structure")
        from . import structures
        c = self.s.candidate
        self.s.match = structures.find_structure(c["heavy_chain_fasta"], c["light_chain_fasta"])
        self.s.lengths = self.flow._lengths(c)
        self.flow._emit(self.s.cid, "input_mapping", "completed", None)
        facts = self.flow._source_facts(c, self.s.match)
        self.s.shown_facts.extend(facts)
        return "확인된 사실:\n" + "\n".join(f"- {f}" for f in facts) + (
            f"\n지금 가능한 도구: {', '.join(sorted(allowed_tools(self.s)))}")

    @_locked
    def use_experimental_structure(self, reason: str) -> str:
        if (r := self._gate("use_experimental_structure")):
            return r
        facts = self.flow._source_facts(self.s.candidate, self.s.match)
        if (r := self._check_reason("use_experimental_structure", reason, facts)):
            return r
        self._accept("use_experimental_structure")
        from .flow import _explain
        d = self._decision("structure_source", "use_experimental", reason, facts)
        self.s.structure_id = self.flow._record_experimental(self.s.cid, self.s.match)
        self.flow._emit(self.s.cid, "prediction", "skipped", _explain(d))
        return f"공개 실험 구조를 검토 구조로 정했다({self.s.structure_id}). 다음은 compare_structure."

    @_locked
    def predict_structure(self, reason: str) -> str:
        if (r := self._gate("predict_structure")):
            return r
        facts = self.flow._source_facts(self.s.candidate, self.s.match)
        if (r := self._check_reason("predict_structure", reason, facts)):
            return r
        self._accept("predict_structure")
        self._decision("structure_source", "predict", reason, facts)
        cid = self.s.cid
        # NAT는 도구 예외를 모델에게 오류 메시지로 돌려주고 루프를 잇는다. 예외를
        # 그냥 두면 structure_id가 비어 있어 모델이 predict_structure를 다시 부를
        # 수 있다. 호출이 성공한 뒤 기록에서 터졌다면 그건 유료 재호출이다.
        # 그래서 여기서 잡아 후보를 실패로 끝내고, 반쯤 쌓인 기록은 되돌린다.
        flow = self.flow
        records = (flow.structures, flow.artifacts, flow.conditions, flow.evidence, flow.opinions)
        sizes = [len(r) for r in records]
        try:
            self.s.structure_id = flow._predict(cid, self.s.candidate, self.s.match)
        except Exception as exc:
            for r, n in zip(records, sizes):
                del r[n:]
            reason = f"예측 단계 오류로 검토를 끝냈다: {type(exc).__name__}: {exc}"[:200]
            flow._fail_prediction(cid, reason)
            self.s.terminal = "failed"
            return reason
        if self.s.structure_id is None:
            state = self.flow.states[cid]
            if state.status == "running":
                state.status = "partial"
            self.s.terminal = state.status
            return f"예측을 얻지 못해 검토를 끝냈다: {state.reason}"
        return f"예측 구조를 확보했다({self.s.structure_id}). 다음은 compare_structure."

    @_locked
    def compare_structure(self) -> str:
        if (r := self._gate("compare_structure")):
            return r
        self._accept("compare_structure")
        self.flow._compare(self.s.cid, self.s.structure_id, self.s.match)
        self.s.compared = True
        facts, _, _ = self.flow._opinion_facts(self.s.cid)
        self.s.shown_facts.extend(facts)
        return ("비교를 마쳤다. 확인된 사실:\n" + "\n".join(f"- {f}" for f in facts)
                + f"\n다음은 submit_opinion. decision은 {' 또는 '.join(OPINIONS)} 중 하나.")

    @_locked
    def submit_opinion(self, decision: str, reason: str) -> str:
        if (r := self._gate("submit_opinion")):
            return r
        if decision not in OPINIONS:
            note = f"거부: decision은 {' 또는 '.join(OPINIONS)} 중 하나여야 한다. 받은 값: {decision!r}."
            self.s.calls.append({"tool": "submit_opinion", "accepted": False, "note": note})
            return note
        facts, _, _ = self.flow._opinion_facts(self.s.cid)
        if (r := self._check_reason("submit_opinion", reason, facts)):
            return r
        self._accept("submit_opinion")
        verdict = self._decision("review_opinion", decision, reason, facts)
        self.flow._report(self.s.cid, self.s.structure_id, self.s.match, verdict=verdict)
        self.flow.states[self.s.cid].status = "completed"
        self.s.terminal = "completed"
        return f"검토 의견을 기록했다({decision}). 검토를 끝냈다."

    @_locked
    def hold_candidate(self, reason: str) -> str:
        if (r := self._gate("hold_candidate")):
            return r
        facts = self.flow._source_facts(self.s.candidate, self.s.match)
        if (r := self._check_reason("hold_candidate", reason, facts)):
            return r
        self._accept("hold_candidate")
        from .flow import _explain
        d = self._decision("structure_source", "hold", reason, facts)
        self.flow._hold_candidate(self.s.cid, _explain(d))
        self.s.terminal = "partial"
        return "검토를 보류하고 끝냈다."
