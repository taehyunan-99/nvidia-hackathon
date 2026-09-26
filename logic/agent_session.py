"""후보 하나의 진행 상태와 에이전트 도구 (NAT 설계 nat-agent-loop.md 4·5절).

NAT에 의존하지 않는다. 규칙 경로(Flow._resume)와 에이전트 도구가 같은
세션을 읽고 쓰므로, 에이전트가 중간에 끊겨도 규칙이 그 자리부터 잇는다.
"""

from __future__ import annotations

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


class CandidateTools:
    """에이전트가 부르는 도구 7개. 각 도구는 기존 Flow 단계를 그대로 쓴다."""

    def __init__(self, flow, session: CandidateSession):
        self.flow = flow
        self.s = session

    # ---------------------------------------------------------- 관문
    def _gate(self, name: str) -> str | None:
        allowed = allowed_tools(self.s)
        if name in allowed:
            return None
        self.s.calls.append({"tool": name, "accepted": False})
        if not allowed:
            return f"거부: 이 후보의 검토는 이미 끝났다({self.s.terminal}). 더 부를 도구가 없다."
        return f"거부: {name}은(는) 지금 쓸 수 없다. 지금 가능한 도구: {', '.join(sorted(allowed))}."

    def _accept(self, name: str) -> None:
        self.s.calls.append({"tool": name, "accepted": True})

    def _decision(self, step: str, action: str, reason: str, facts: list[str]) -> Decision:
        d = Decision(step=step, action=action, reason=reason, decided_by="model",
                     model=self.flow.decider.model, facts=facts)
        self.flow.decider.decisions.append(d)
        return d

    def _check_reason(self, name: str, reason: str, facts: list[str]) -> str | None:
        if not reason.strip():
            self.s.calls.append({"tool": name, "accepted": False})
            return "거부: reason이 비어 있다. 고른 이유를 두 문장 이내로 쓴다."
        invented = invented_numbers(reason, facts)
        if invented:
            self.s.calls.append({"tool": name, "accepted": False})
            return (f"거부: reason에 확인된 사실에 없는 숫자가 있다: {', '.join(invented)}. "
                    "사실에 있는 값만 쓰거나 숫자를 빼고 다시 쓴다.")
        return None

    # ---------------------------------------------------------- 도구
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
        return "확인된 사실:\n" + "\n".join(f"- {f}" for f in facts) + (
            f"\n지금 가능한 도구: {', '.join(sorted(allowed_tools(self.s)))}")

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

    def predict_structure(self, reason: str) -> str:
        if (r := self._gate("predict_structure")):
            return r
        facts = self.flow._source_facts(self.s.candidate, self.s.match)
        if (r := self._check_reason("predict_structure", reason, facts)):
            return r
        self._accept("predict_structure")
        self._decision("structure_source", "predict", reason, facts)
        cid = self.s.cid
        self.s.structure_id = self.flow._predict(cid, self.s.candidate, self.s.match)
        if self.s.structure_id is None:
            state = self.flow.states[cid]
            if state.status == "running":
                state.status = "partial"
            self.s.terminal = state.status
            return f"예측을 얻지 못해 검토를 끝냈다: {state.reason}"
        return f"예측 구조를 확보했다({self.s.structure_id}). 다음은 compare_structure."

    def compare_structure(self) -> str:
        if (r := self._gate("compare_structure")):
            return r
        self._accept("compare_structure")
        self.flow._compare(self.s.cid, self.s.structure_id, self.s.match)
        self.s.compared = True
        facts, _, _ = self.flow._opinion_facts(self.s.cid)
        return ("비교를 마쳤다. 확인된 사실:\n" + "\n".join(f"- {f}" for f in facts)
                + f"\n다음은 submit_opinion. decision은 {' 또는 '.join(OPINIONS)} 중 하나.")

    def submit_opinion(self, decision: str, reason: str) -> str:
        if (r := self._gate("submit_opinion")):
            return r
        if decision not in OPINIONS:
            self.s.calls.append({"tool": "submit_opinion", "accepted": False})
            return f"거부: decision은 {' 또는 '.join(OPINIONS)} 중 하나여야 한다. 받은 값: {decision!r}."
        facts, _, _ = self.flow._opinion_facts(self.s.cid)
        if (r := self._check_reason("submit_opinion", reason, facts)):
            return r
        self._accept("submit_opinion")
        verdict = self._decision("review_opinion", decision, reason, facts)
        self.flow._report(self.s.cid, self.s.structure_id, self.s.match, verdict=verdict)
        self.flow.states[self.s.cid].status = "completed"
        self.s.terminal = "completed"
        return f"검토 의견을 기록했다({decision}). 검토를 끝냈다."

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
