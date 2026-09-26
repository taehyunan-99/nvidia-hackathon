# NAT 에이전트 루프 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로직 B의 후보 검토를 Nemotron이 NAT `tool_calling_agent` 안에서 도구를 골라 진행하게 하고, 실패·상한 시 규칙 경로로 마무리한다.

**Architecture:** 후보 하나의 진행 상태를 `CandidateSession`에 두고, 허용 도구는 순수 함수 `allowed_tools(session)`가 정한다. 도구 7개(`CandidateTools`)는 기존 `Flow` 단계 메서드를 감싸며 허용되지 않으면 거부 문구를 돌려준다. `Flow._resume(session)`이 규칙 경로를 세션 기준으로 이어 가므로, 규칙 모드·에이전트 후 마무리가 같은 코드를 쓴다. NAT 연결부(`logic/nat_agent.py`)는 이 도구를 NAT 함수로 등록하고 `contextvars`로 세션을 넘긴다.

**Tech Stack:** Python 3.13, `nvidia-nat[langchain]` 1.9.0, NVIDIA 호스팅 `nvidia/nemotron-3-super-120b-a12b`, pytest, uv.

**Spec:** [nat-agent-loop.md](nat-agent-loop.md)

## Global Constraints

- `requires-python = ">=3.11,<3.14"` — NAT 1.9.0이 3.14를 지원하지 않는다.
- `run_flow(request, *, client, progress, decider)` 시그니처와 `LogicOutput` 스키마를 바꾸지 않는다.
- 모드 선택은 환경변수 `LOGIC_AGENT_MODE=nat|rule`, 기본 `rule` (5단계 전까지).
- 숫자는 코드만 계산한다. 모델이 쓴 `reason`은 `agent.invented_numbers`로 검사한다.
- 판단 주체 표기는 `(판단: <모델명>)` / `(판단: 규칙 — <이유>)` 형식을 유지한다 (`flow._explain`).
- 이미 성공한 Boltz-2 호출을 다시 보내지 않는다.
- `max_iterations` 초기값 10.
- 커밋은 사용자가 요청할 때만 한다 (저장소 `AGENTS.md`). 아래 커밋 단계는 요청을 받은 경우에만 실행한다.

## Review Focus

1. 에이전트가 예측 직후 503으로 끊김 → 규칙 마무리가 예측을 다시 부르지 않고 비교·보고만 해야 한다.
2. 모델이 종료 도구 뒤에 도구를 또 부름 → 전부 거부되고 결과가 바뀌지 않아야 한다.
3. 모델이 `submit_opinion`에 허용되지 않은 `decision` 값을 넣음 → 거부, 상태 불변.
4. 입력 오류 후보 → 에이전트 모드에서도 규칙 모드와 같은 failed·보류 의견이 나와야 한다.
5. NAT가 설치되지 않은 환경에서 `LOGIC_AGENT_MODE=nat` → 규칙으로 끝까지 실행되고 사유가 의견 문장에 남아야 한다.

각 항목의 테스트는 Task 2·3·4에 들어 있다.

## 파일 구조

| 파일 | 책임 |
|---|---|
| `pyproject.toml` (수정) | Python 범위, NAT 의존성 |
| `logic/agent.py` (수정) | `RuleDecider` 추가 — 모델을 부르지 않고 규칙 결정을 기록 |
| `logic/flow.py` (수정) | 단계 보조 메서드 추출, `_resume(session)`, `_continue_by_rule`, 모드 분기 |
| `logic/agent_session.py` (신규) | `CandidateSession`, `allowed_tools`, `CandidateTools` — NAT 비의존 |
| `logic/nat_agent.py` (신규) | NAT 함수 등록, 세션 전달, 동기 실행 래퍼 |
| `logic/nat_workflow.yml` (신규) | NAT LLM·도구·에이전트 설정 |
| `logic/measure_agent.py` (신규) | 7절 측정 시나리오 실행기 |
| `logic/tests/test_agent_session.py` (신규) | 관문·도구 단위 테스트 |
| `logic/tests/test_flow_resume.py` (신규) | 재개·규칙 마무리 테스트 |
| `logic/tests/test_nat_agent.py` (신규) | NAT 설정 로드·폴백 테스트 |

---

### Task 1: 환경 — Python 범위와 NAT 의존성

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock` (uv가 생성)
- Modify: `docs/topics/her2/nat-agent-loop.md` (2절에 0단계 결과 기록)

**Interfaces:**
- Produces: `.venv`(Python 3.13)에서 `import nat` 가능

- [ ] **Step 1: `pyproject.toml` 수정**

```toml
requires-python = ">=3.11,<3.14"
dependencies = [
  "fastapi>=0.115,<1",
  "uvicorn>=0.34,<1",
  "jsonschema>=4.23,<5",
  "python-multipart>=0.0.20,<1",
  "psycopg[binary]>=3.2,<4",
  "gemmi>=0.7,<1",
  "requests>=2.32,<3",
  "nvidia-nat[langchain]>=1.9,<2",
]
```

- [ ] **Step 2: 잠금·설치**

Run: `UV_LINK_MODE=copy uv sync -p 3.13`
Expected: 오류 없이 종료, `.venv/bin/python -c "import nat, sys; print(sys.version)"`가 3.13 출력

- [ ] **Step 3: 기존 테스트가 3.13에서 그대로 통과하는지**

Run: `uv run pytest -q`
Expected: 전부 PASS (logic 38건 + service 테스트). 실패하면 여기서 멈추고 원인 보고.

- [ ] **Step 4: 스펙 2절에 0단계 결과 기록**

`nat-agent-loop.md` 2절 표에 행 추가:
```markdown
| NAT 루프 실호출 (0단계) | `tool_calling_agent` + 커스텀 도구 3개 + `nemotron-3-super` 스트리밍: 6.2초, 호출 순서 check→predict→finish, `return_direct`로 종료, `contextvars` 상태가 도구 안에서 보임. 최종 문장이 영어로 나옴 → 시스템 프롬프트에 한국어 지시 필요 | 임시 스크립트, 2026-09-26 |
```
그리고 "미확인: … 스트리밍 + tool-calling 조합" 문단을 "확인됨(위 행)"으로 바꾼다.

- [ ] **Step 5: Commit (요청 시)**

```bash
git add pyproject.toml uv.lock docs/topics/her2/nat-agent-loop.md
git commit -m "chore(logic): NAT 의존성 추가와 Python 3.14 제외"
```

---

### Task 2: Flow 단계 추출과 세션 기반 재개

기존 `_run_candidate`의 동작을 바꾸지 않고 세션을 따라 이어 갈 수 있게 나눈다. 기존 테스트가 회귀 검사다.

**Files:**
- Modify: `logic/agent.py` (끝에 `RuleDecider` 추가)
- Create: `logic/agent_session.py` (이 태스크에서는 `CandidateSession`만)
- Modify: `logic/flow.py:149-202` (`_run_candidate`), `:234-306` (`_choose_source`), `:635-687` (`_report`)
- Test: `logic/tests/test_flow_resume.py`

**Interfaces:**
- Produces:
  - `agent_session.CandidateSession(candidate: dict)` — 필드 `input_checked: bool`, `match: StructureMatch | None`, `lengths: dict[str, int]`, `structure_id: str | None`, `compared: bool`, `terminal: str | None` (`"completed" | "partial" | "failed"`), `calls: list[dict]`; 속성 `cid -> str`
  - `agent.RuleDecider(why: str, *, decisions: list, model: str)` — `choose(step, *, question, facts, options, default) -> Decision` (항상 `decided_by="rule"`, `fallback_reason=why`)
  - `Flow._source_facts(candidate, match) -> list[str]`
  - `Flow._opinion_facts(cid) -> tuple[list[str], list[dict], list[dict]]` — (facts, measured, unmeasured)
  - `Flow._fail_input(cid, problems: list[str]) -> None`
  - `Flow._hold_candidate(cid, reason: str) -> None`
  - `Flow._report(cid, structure_id, match, verdict: Decision | None = None) -> None`
  - `Flow._resume(session: CandidateSession) -> None`
  - `Flow._continue_by_rule(session, why: str) -> None`

- [ ] **Step 1: 실패하는 테스트 작성** — `logic/tests/test_flow_resume.py`

```python
"""세션에서 이어 가는 규칙 경로를 확인한다. NVIDIA를 부르지 않는다."""

from __future__ import annotations

from logic import structures
from logic.agent_session import CandidateSession
from logic.flow import Flow
from logic.tests.test_flow import TRASTUZUMAB, _long, candidate, entity_sequence, make_request
from logic.tests.test_flow_decisions import ScriptedClient

# make_request의 표적 서열 기본값은 None이다. 예측 경로에는 50자 이상이 필요하다.
TARGET = _long("HERTWOSEQ", 300)


def _trastuzumab():
    return candidate(
        "cand-t", "trastuzumab",
        entity_sequence(TRASTUZUMAB, "heavy"), entity_sequence(TRASTUZUMAB, "light"),
    )


def test_resume_from_scratch_matches_rule_run(tmp_path):
    client = ScriptedClient()  # chat 대본 없음 → 판단부는 규칙으로 간다
    flow = Flow(make_request([_trastuzumab()], tmp_path), client=client)
    session = CandidateSession(_trastuzumab())
    flow._resume(session)
    assert session.terminal == "completed"
    assert flow.states["cand-t"].status == "completed"
    assert client.predictions == 0


def test_continue_after_prediction_does_not_predict_again(tmp_path):
    variant = candidate("cand-v", "variant", _long("QVQLVESGG"), _long("DIQMTQSPS"))
    client = ScriptedClient()
    flow = Flow(make_request([variant], tmp_path, target_fasta=TARGET), client=client)
    session = CandidateSession(variant)
    session.input_checked = True
    session.match = structures.find_structure(variant["heavy_chain_fasta"], variant["light_chain_fasta"])
    flow._emit("cand-v", "input_mapping", "completed", None)
    session.structure_id = flow._predict("cand-v", variant, session.match)
    assert client.predictions == 1

    flow._continue_by_rule(session, "모델 호출이 503으로 실패했다")

    assert client.predictions == 1  # 규칙 마무리가 예측을 다시 부르지 않는다
    assert session.terminal is not None
    assert any("판단: 규칙 — 모델 호출이 503으로 실패했다" in (o["reason"] or "")
               for o in flow.opinions if o["candidate_id"] == "cand-v")


def test_continue_on_terminal_session_changes_nothing(tmp_path):
    flow = Flow(make_request([_trastuzumab()], tmp_path), client=ScriptedClient())
    session = CandidateSession(_trastuzumab())
    flow._resume(session)
    before = list(flow.opinions)
    flow._continue_by_rule(session, "상한")
    assert flow.opinions == before
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest logic/tests/test_flow_resume.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.agent_session'`

- [ ] **Step 3: `CandidateSession` 작성** — `logic/agent_session.py`

```python
"""후보 하나의 진행 상태와 에이전트 도구 (NAT 설계 nat-agent-loop.md 4·5절).

NAT에 의존하지 않는다. 규칙 경로(Flow._resume)와 에이전트 도구가 같은
세션을 읽고 쓰므로, 에이전트가 중간에 끊겨도 규칙이 그 자리부터 잇는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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
```

- [ ] **Step 4: `RuleDecider` 추가** — `logic/agent.py` 끝

```python
class RuleDecider:
    """모델을 부르지 않고 규칙 결과를 기록한다.

    에이전트가 끊긴 뒤 규칙으로 마무리할 때 쓴다. 다시 모델을 부르면
    방금 실패한 호출을 되풀이하게 된다. 끊긴 이유를 결정마다 남긴다.
    """

    def __init__(self, why: str, *, decisions: list[Decision], model: str):
        self.why = why
        self.decisions = decisions
        self.model = model

    def choose(self, step: str, *, question: str, facts: list[str],
               options: list[Option], default: str) -> Decision:
        del question
        assert any(o.action == default for o in options), "default가 선택지에 없다"
        decision = Decision(
            step=step, action=default, reason="코드에 정해 둔 규칙대로 진행했다.",
            decided_by="rule", model=None, fallback_reason=self.why, facts=facts,
        )
        self.decisions.append(decision)
        return decision
```

- [ ] **Step 5: `flow.py` 보조 메서드 추출**

`_choose_source`의 facts 조립(현재 `facts = [...]`부터 `for label, n in lengths.items()]`까지)을 그대로 옮긴다:

```python
    def _source_facts(self, candidate: dict[str, Any], match: structures.StructureMatch) -> list[str]:
        facts = [
            f"공개 구조 검색 결과: {match.pdb_id or '일치 후보 없음'}",
            f"중쇄 서열 정확히 일치: {'예' if match.heavy_exact else '아니오'}",
            f"경쇄 서열 정확히 일치: {'예' if match.light_exact else '아니오'}",
            f"같은 구조에 표적 사슬 있음: {'예' if match.target_entity else '아니오'}",
        ]
        facts += [
            f"{label} 서열 길이 {n}자 "
            f"({'예측 입력으로 충분' if n >= MIN_CHAIN_LENGTH else f'{MIN_CHAIN_LENGTH}자 미만이라 예측 불가'})"
            for label, n in self._lengths(candidate).items()
        ]
        return facts

    def _lengths(self, candidate: dict[str, Any]) -> dict[str, int]:
        return {
            "표적": len(structures.normalize_sequence(self.request["input"]["target"].get("fasta") or "")),
            "중쇄": len(structures.normalize_sequence(candidate["heavy_chain_fasta"])),
            "경쇄": len(structures.normalize_sequence(candidate["light_chain_fasta"])),
        }
```

`_choose_source` 안에서는 `facts = self._source_facts(candidate, match)` 한 줄로 바꾸고, 기존 주석(“예측에 쓸 자료가 있는지도 사실로 넣는다…”)은 `_source_facts` 위로 옮긴다.

`_report`의 앞부분(measured·unmeasured·facts)을 옮긴다:

```python
    def _opinion_facts(self, cid: str) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
        mine = [e for e in self.evidence if e["candidate_id"] == cid]
        measured = [e for e in mine if e["measurement_state"] == "measured"]
        unmeasured = [e for e in mine if e["measurement_state"] != "measured"]
        facts = [
            f"계산해 확보한 근거 {len(measured)}건, 아직 계산하지 않은 항목 {len(unmeasured)}건.",
            *(f"{e['topic']}: {e['value']}{e['unit'] or ''} ({e['definition']})"
              for e in measured if e["definition"]),
            *(f"{e['topic']}: 미계산 — {e['reason']}" for e in unmeasured if e["reason"]),
        ]
        return facts, measured, unmeasured
```

`_report` 시그니처를 `def _report(self, cid, structure_id, match, verdict: Decision | None = None)`로 바꾸고 본문 앞부분을:

```python
        self._emit(cid, "reporting", "running", None)
        condition_id = f"cond-{cid}-core"
        facts, measured, unmeasured = self._opinion_facts(cid)
        if verdict is None:
            verdict = self.decider.choose(
                # (기존 인자 그대로 — question, facts, options, default와 주석 유지)
            )
```

로 바꾼다. `from .agent import Decider, Decision, Option`으로 import를 늘린다.

`_run_candidate`의 입력 실패 블록과 보류 블록을 옮긴다:

```python
    def _fail_input(self, cid: str, problems: list[str]) -> None:
        reason = " ".join(problems)
        self._emit(cid, "input_mapping", "failed", reason)
        for step in STEP_IDS[1:]:
            self._emit(cid, step, "skipped", "입력 정정 전에는 진행하지 않는다.")
        self.states[cid].status = "failed"
        self.states[cid].reason = reason
        self._hold_opinion(cid, "input", "hold", reason, limitations=problems)

    def _hold_candidate(self, cid: str, reason: str) -> None:
        # 판단 주체가 지금 예측하지 않기로 했다. 실패가 아니라 보류다.
        self._emit(cid, "evidence_review", "held", reason)
        self._emit(cid, "prediction", "held", reason)
        for step in ("structure_comparison", "reporting"):
            self._emit(cid, step, "skipped", "예측 구조가 없어 진행하지 않았다.")
        self.states[cid].status = "partial"
        self.states[cid].reason = reason
        self._hold_opinion(cid, "structure_availability", "hold", reason)
```

- [ ] **Step 6: `_resume`·`_continue_by_rule` 작성, `_run_candidate` 교체**

```python
    def _run_candidate(self, candidate: dict[str, Any]) -> None:
        self._resume(CandidateSession(candidate))

    def _resume(self, s: CandidateSession) -> None:
        """세션이 멈춘 자리부터 규칙 경로로 끝까지 간다. 끝난 단계는 다시 하지 않는다."""
        if s.terminal:
            return
        cid, candidate = s.cid, s.candidate
        state = self.states[cid]
        state.status = "running"

        # ① ② 입력 검사
        if not s.input_checked:
            self._emit(cid, "input_mapping", "running", None)
            problems = self._check_input(candidate)
            s.input_checked = True
            if problems:
                self._fail_input(cid, problems)
                s.terminal = "failed"
                return

        # 공개 자료 조회
        if s.match is None:
            s.match = structures.find_structure(candidate["heavy_chain_fasta"], candidate["light_chain_fasta"])
            s.lengths = self._lengths(candidate)
            self._emit(cid, "input_mapping", "completed", None)

        # ③ 분기: 기존 구조 / 예측 / 자료 부족 — 판단 주체는 self.decider
        if s.structure_id is None:
            choice = self._choose_source(cid, candidate, s.match)
            if choice.action == "use_experimental":
                s.structure_id = self._record_experimental(cid, s.match)
                self._emit(cid, "prediction", "skipped", _explain(choice))
            elif choice.action == "hold":
                self._hold_candidate(cid, _explain(choice))
                s.terminal = "partial"
                return
            else:
                s.structure_id = self._predict(cid, candidate, s.match)
                if s.structure_id is None:
                    # _predict가 이미 failed로 표시했으면 덮어쓰지 않는다.
                    if state.status == "running":
                        state.status = "partial"
                    s.terminal = state.status
                    return

        if not s.compared:
            self._compare(cid, s.structure_id, s.match)
            s.compared = True
        self._report(cid, s.structure_id, s.match)
        state.status = "completed"
        s.terminal = "completed"

    def _continue_by_rule(self, s: CandidateSession, why: str) -> None:
        """에이전트가 끝내지 못한 후보를 규칙으로 마무리한다. 모델을 다시 부르지 않는다."""
        saved = self.decider
        self.decider = RuleDecider(why, decisions=saved.decisions, model=saved.model)
        try:
            self._resume(s)
        finally:
            self.decider = saved
```

import 추가: `from .agent import Decider, Decision, Option, RuleDecider`, `from .agent_session import CandidateSession`.

- [ ] **Step 7: 새 테스트와 기존 테스트 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS. 기존 테스트가 하나라도 깨지면 추출 과정의 동작 차이이므로 고친다.

- [ ] **Step 8: Commit (요청 시)**

```bash
git add logic/agent.py logic/agent_session.py logic/flow.py logic/tests/test_flow_resume.py
git commit -m "refactor(logic): 후보 흐름을 세션에서 이어 갈 수 있게 나눈다"
```

---

### Task 3: 관문과 에이전트 도구

**Files:**
- Modify: `logic/agent_session.py` (`allowed_tools`, `CandidateTools` 추가)
- Test: `logic/tests/test_agent_session.py`

**Interfaces:**
- Consumes: Task 2의 `CandidateSession`, `Flow._source_facts/_opinion_facts/_fail_input/_hold_candidate/_report/_record_experimental/_predict/_compare/_lengths`, `flow._explain`, `agent.Decision`, `agent.invented_numbers`
- Produces:
  - `TOOL_NAMES: tuple[str, ...]`, `TERMINAL_TOOLS: frozenset[str]`
  - `allowed_tools(s: CandidateSession) -> set[str]`
  - `CandidateTools(flow, session)` — 메서드 `check_input() -> str`, `lookup_public_structure() -> str`, `use_experimental_structure(reason: str) -> str`, `predict_structure(reason: str) -> str`, `compare_structure() -> str`, `submit_opinion(decision: str, reason: str) -> str`, `hold_candidate(reason: str) -> str`. 거부 시 `"거부: "`로 시작하는 문자열.

- [ ] **Step 1: 실패하는 테스트 작성** — `logic/tests/test_agent_session.py`

```python
"""관문과 도구. 모델 없이 도구를 직접 불러 본다. NVIDIA를 부르지 않는다."""

from __future__ import annotations

import pytest

from logic.agent_session import CandidateSession, CandidateTools, allowed_tools
from logic.flow import Flow
from logic.tests.test_flow import TRASTUZUMAB, _long, candidate, entity_sequence, make_request
from logic.tests.test_flow_decisions import ScriptedClient


# make_request의 표적 서열 기본값은 None이다. 예측 경로에는 50자 이상이 필요하다.
TARGET = _long("HERTWOSEQ", 300)


def _setup(tmp_path, cand):
    client = ScriptedClient()
    flow = Flow(make_request([cand], tmp_path, target_fasta=TARGET), client=client)
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
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest logic/tests/test_agent_session.py -q`
Expected: FAIL — `ImportError: cannot import name 'CandidateTools'`

- [ ] **Step 3: 관문과 도구 구현** — `logic/agent_session.py`에 추가

```python
from .agent import Decision, invented_numbers

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
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS

- [ ] **Step 5: Commit (요청 시)**

```bash
git add logic/agent_session.py logic/tests/test_agent_session.py
git commit -m "feat(logic): 에이전트 도구 7개와 상태 관문 추가"
```

---

### Task 4: NAT 연결과 모드 분기

**Files:**
- Create: `logic/nat_agent.py`, `logic/nat_workflow.yml`
- Modify: `logic/flow.py` (`Flow.run`에서 모드 분기, `_run_candidate_nat`, `agent_traces`)
- Test: `logic/tests/test_nat_agent.py`

**Interfaces:**
- Consumes: Task 3의 `CandidateTools`, `CandidateSession`; Task 2의 `_continue_by_rule`
- Produces:
  - `nat_agent.NAT_AVAILABLE: bool`
  - `nat_agent.run_candidate(flow, session, *, config_path: Path = CONFIG_PATH) -> str | None` — 에이전트가 종료 도구로 끝냈으면 `None`, 아니면 규칙 마무리 사유
  - `Flow.agent_traces: dict[str, list[dict]]` — 후보별 도구 호출 기록(계약 밖, 측정용)
  - 환경변수 `LOGIC_AGENT_MODE`

- [ ] **Step 1: 실패하는 테스트 작성** — `logic/tests/test_nat_agent.py`

```python
"""NAT 연결부. 실제 모델은 RUN_LIVE_NAT=1일 때만 부른다."""

from __future__ import annotations

import os

import pytest

from logic import nat_agent
from logic.contract import validate
from logic.flow import run_flow
from logic.tests.test_flow import TRASTUZUMAB, candidate, entity_sequence, make_request
from logic.tests.test_flow_decisions import ScriptedClient


def _request(tmp_path):
    t = candidate("cand-t", "trastuzumab",
                  entity_sequence(TRASTUZUMAB, "heavy"), entity_sequence(TRASTUZUMAB, "light"))
    return make_request([t], tmp_path)


def test_rule_mode_is_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGIC_AGENT_MODE", raising=False)
    called = []
    monkeypatch.setattr(nat_agent, "run_candidate", lambda *a, **k: called.append(1))
    output, _ = run_flow(_request(tmp_path), client=ScriptedClient())
    assert called == []
    validate(output, "LogicOutput")


def test_nat_failure_falls_back_to_rule_with_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    monkeypatch.setattr(nat_agent, "NAT_AVAILABLE", True)
    monkeypatch.setattr(nat_agent, "run_candidate", lambda flow, s, **k: "에이전트 반복 상한")
    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    validate(output, "LogicOutput")
    assert flow.states["cand-t"].status == "completed"
    opinion = output["result"]["opinions"][0]
    assert "판단: 규칙 — 에이전트 반복 상한" in opinion["reason"]


def test_missing_nat_falls_back_to_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    monkeypatch.setattr(nat_agent, "NAT_AVAILABLE", False)
    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    validate(output, "LogicOutput")
    assert "NAT를 불러오지 못했다" in output["result"]["opinions"][0]["reason"]


def test_workflow_config_loads_with_registered_tools():
    pytest.importorskip("nat")
    from nat.runtime.loader import load_config
    config = load_config(nat_agent.CONFIG_PATH)
    assert set(config.functions) == set(nat_agent.TOOL_NAMES)


@pytest.mark.skipif(os.getenv("RUN_LIVE_NAT") != "1", reason="실제 Nemotron 호출은 RUN_LIVE_NAT=1에서만")
def test_live_agent_reviews_experimental_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    trace = flow.agent_traces["cand-t"]
    assert trace[0]["tool"] == "check_input"
    assert flow.states["cand-t"].status == "completed"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest logic/tests/test_nat_agent.py -q`
Expected: FAIL — `ImportError: cannot import name 'nat_agent'`

- [ ] **Step 3: NAT 설정 작성** — `logic/nat_workflow.yml`

```yaml
# 로직 B 에이전트 루프 (docs/topics/her2/nat-agent-loop.md).
# 모델 ID는 2026-09-26 이 계정에서 실측으로 쓸 수 있었던 것 (logic/agent.py 주석).
llms:
  nemotron:
    _type: nim
    model_name: nvidia/nemotron-3-super-120b-a12b
    temperature: 0.0
    max_tokens: 1024
functions:
  check_input: {_type: her2_check_input}
  lookup_public_structure: {_type: her2_lookup_public_structure}
  use_experimental_structure: {_type: her2_use_experimental_structure}
  predict_structure: {_type: her2_predict_structure}
  compare_structure: {_type: her2_compare_structure}
  submit_opinion: {_type: her2_submit_opinion}
  hold_candidate: {_type: her2_hold_candidate}
workflow:
  _type: tool_calling_agent
  llm_name: nemotron
  tool_names: [check_input, lookup_public_structure, use_experimental_structure,
               predict_structure, compare_structure, submit_opinion, hold_candidate]
  return_direct: [submit_opinion, hold_candidate]
  max_iterations: 10
  system_prompt: |
    너는 HER2 항체 후보 하나를 검토하는 에이전트다. 도구를 불러서만 진행한다.
    규칙:
    1. 도구가 돌려준 '확인된 사실'에 없는 수치를 쓰지 않는다.
    2. 결합력·치료 효능을 판정하지 않는다. 구조상 검토 가능 여부만 본다.
    3. 도구가 '거부:'로 답하면 그 안에 적힌 '지금 가능한 도구' 중에서 다시 고른다.
    4. 일치하는 공개 구조가 없다는 것은 보류 사유가 아니다. 서열이 충분하면 predict_structure로 구조를 만든다.
    5. reason은 한국어 두 문장 이내로 쓴다.
    6. submit_opinion 또는 hold_candidate로 검토를 끝낸다.
```

- [ ] **Step 4: NAT 연결부 작성** — `logic/nat_agent.py`

```python
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
```

`TOOL_NAMES`는 테스트가 설정의 함수 목록과 대조하려고 가져다 쓴다 (`nat_agent.TOOL_NAMES`).

- [ ] **Step 5: `Flow`에 모드 분기** — `logic/flow.py`

`__init__` 끝에 `self.agent_traces: dict[str, list[dict[str, Any]]] = {}` 추가. `run`을:

```python
    def run(self) -> dict[str, Any]:
        mode = os.getenv("LOGIC_AGENT_MODE", "rule")
        for candidate in self.request["input"]["candidates"]:
            if mode == "nat":
                self._run_candidate_nat(candidate)
            else:
                self._run_candidate(candidate)
        # (이하 기존 그대로)

    def _run_candidate_nat(self, candidate: dict[str, Any]) -> None:
        from . import nat_agent

        session = CandidateSession(candidate)
        self.states[session.cid].status = "running"
        if nat_agent.NAT_AVAILABLE:
            why = nat_agent.run_candidate(self, session)
        else:
            why = "NAT를 불러오지 못했다"
        self.agent_traces[session.cid] = session.calls
        if why:
            self._continue_by_rule(session, why)
```

`import os`를 파일 위쪽 import에 추가한다.

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest -q`
Expected: 전부 PASS, live 테스트 1건 SKIPPED

- [ ] **Step 7: 실제 모델로 한 번 확인**

Run: `RUN_LIVE_NAT=1 uv run pytest logic/tests/test_nat_agent.py -q -k live`
Expected: PASS. 실패하면 `flow.agent_traces`와 오류를 그대로 보고하고 Task 5 전에 원인을 본다.

- [ ] **Step 8: Commit (요청 시)**

```bash
git add logic/nat_agent.py logic/nat_workflow.yml logic/flow.py logic/tests/test_nat_agent.py
git commit -m "feat(logic): NAT tool-calling 에이전트로 후보 검토를 진행한다"
```

---

### Task 5: 측정

**Files:**
- Create: `logic/measure_agent.py`
- Modify: `docs/topics/her2/nat-agent-loop.md` (7절 아래 측정 결과 표)

**Interfaces:**
- Consumes: `run_flow`, `Flow.agent_traces`, 테스트 도우미 `logic.tests.test_flow`의 `candidate/entity_sequence/make_request/_long`
- Produces: 콘솔 표와 `work/measure-agent.jsonl` (저장소 밖 작업 폴더가 아니라 `logic/` 기준 상대 경로 `../work/`, `.gitignore` 확인 후 사용)

- [ ] **Step 1: 측정기 작성** — `logic/measure_agent.py`

```python
"""NAT 에이전트 측정 (nat-agent-loop.md 7절). 실제 NVIDIA를 부른다.

    uv run python -m logic.measure_agent --repeat 3
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from .flow import run_flow
from .tests.test_flow import PERTUZUMAB, TRASTUZUMAB, _long, candidate, entity_sequence, make_request

# 예측 경로에 쓰는 합성 표적 서열. 테스트와 같은 값이며 실제 HER2 서열이 아니다.
TARGET = _long("HERTWOSEQ", 300)

SCENARIOS = {
    "trastuzumab": lambda: candidate("cand-t", "trastuzumab",
                                     entity_sequence(TRASTUZUMAB, "heavy"), entity_sequence(TRASTUZUMAB, "light")),
    "pertuzumab": lambda: candidate("cand-p", "pertuzumab",
                                    entity_sequence(PERTUZUMAB, "heavy"), entity_sequence(PERTUZUMAB, "light")),
    "variant": lambda: candidate("cand-v", "variant", _long("QVQLVESGG"), _long("DIQMTQSPS")),
    "invalid": lambda: candidate("cand-x", "invalid", "QVQL123", "DIQM!!"),
    "short": lambda: candidate("cand-s", "short", "QVQLVESGG", "DIQMTQSPS"),
}


def _one(name: str, mode: str) -> dict:
    os.environ["LOGIC_AGENT_MODE"] = mode
    with tempfile.TemporaryDirectory() as tmp:
        cand = SCENARIOS[name]()
        t = time.time()
        output, flow = run_flow(make_request([cand], Path(tmp), target_fasta=TARGET))
        elapsed = round(time.time() - t, 1)
    cid = cand["candidate_id"]
    trace = flow.agent_traces.get(cid, [])
    opinion = next((o for o in output["result"]["opinions"] if o["candidate_id"] == cid), {})
    return {
        "scenario": name, "mode": mode, "seconds": elapsed,
        "calls": len(trace), "refused": sum(1 for c in trace if not c["accepted"]),
        "rule_finish": "판단: 규칙" in (opinion.get("reason") or ""),
        "hit_limit": "반복 상한" in (opinion.get("reason") or ""),
        "status": flow.states[cid].status, "decision": opinion.get("decision"),
        "trace": [c["tool"] + ("" if c["accepted"] else "✗") for c in trace],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=3)
    args = ap.parse_args()
    out = Path(__file__).resolve().parent.parent / "work" / "measure-agent.jsonl"
    out.parent.mkdir(exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        for name in SCENARIOS:
            rows = [_one(name, "rule")] + [_one(name, "nat") for _ in range(args.repeat)]
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                print(f"{r['scenario']:12} {r['mode']:4} {r['seconds']:6}s calls={r['calls']} "
                      f"refused={r['refused']} rule_finish={r['rule_finish']} limit={r['hit_limit']} "
                      f"{r['status']}/{r['decision']} {' → '.join(r['trace'])}")
    print("기록:", out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: `.gitignore`에 `work/`가 있는지 확인**

Run: `git check-ignore -q work/x && echo ignored || echo NOT-IGNORED`
Expected: `ignored`. 아니면 `work/`를 `.gitignore`에 추가한다.

- [ ] **Step 3: 측정 실행**

Run: `uv run python -m logic.measure_agent --repeat 3`
Expected: 시나리오 5개 × (rule 1 + nat 3) = 20줄. 이 명령은 Boltz-2를 variant 4회 부른다.

- [ ] **Step 4: 스펙 7절 아래에 결과 기록**

```markdown
### 측정 결과 (YYYY-MM-DD)

| 시나리오 | 규칙 모드 시간 | 에이전트 시간(3회) | 평균 거부 | 상한 도달 | 규칙 마무리 | 최종 상태·의견 |
|---|---|---|---|---|---|---|
```
출력값만 옮긴다. 실행하지 않은 칸은 비운다. 7절 기준 1–3 각각에 대해 해당/비해당을 한 줄씩 적는다.

- [ ] **Step 5: Commit (요청 시)**

```bash
git add logic/measure_agent.py docs/topics/her2/nat-agent-loop.md .gitignore
git commit -m "test(logic): NAT 에이전트 측정기와 첫 측정 결과"
```

---

### Task 6: A/B 판단 (사용자 확인)

- [ ] **Step 1:** Task 5 결과와 7절 기준을 사용자에게 보고하고 A 유지 / B 전환을 묻는다. 기준에 걸리지 않으면 A 유지를 권한다.
- [ ] **Step 2:** B 전환으로 결정되면 Task 6B를 진행하고, 아니면 Task 7로 간다.

### Task 6B (조건부): 상태별 도구 노출

A의 도구·세션·폴백은 그대로 두고, 모델에게 보여 줄 도구만 매 바퀴 `allowed_tools`로 좁힌다.

**Files:**
- Modify: `logic/nat_agent.py` (그래프 하위 클래스와 워크플로 등록)
- Modify: `logic/nat_workflow.yml` (`workflow._type: her2_gated_agent`)
- Test: `logic/tests/test_nat_agent.py` (노출 도구 검사)

- [ ] **Step 1: 확장 가능 여부 확인** — NAT `ToolCallAgentGraph._invoke_llm`이 `self.agent`(= `prompt | self.bound_llm`)를 쓰는지 읽는다.

Run: `uv run python -c "import inspect, nat.plugins.langchain.agent.tool_calling_agent.agent as a; print(inspect.getsource(a.ToolCallAgentGraph.__init__)); print(inspect.getsource(a.ToolCallAgentGraph._invoke_llm))"`
Expected: `bind_tools(tools)` 결과로 `self.agent`를 만드는 위치 확인. 구조가 다르면 여기서 멈추고 보고.

- [ ] **Step 2: 실패하는 테스트**

```python
def test_gated_graph_exposes_only_allowed_tools(tmp_path):
    pytest.importorskip("nat")
    from logic.agent_session import CandidateSession
    session = CandidateSession({"candidate_id": "cand-t"})
    assert nat_agent.exposed_tool_names(session) == ["check_input"]
```

- [ ] **Step 3: 구현** — `logic/nat_agent.py`

```python
def exposed_tool_names(session: CandidateSession) -> list[str]:
    from .agent_session import allowed_tools
    return [n for n in TOOL_NAMES if n in allowed_tools(session)]
```

그리고 Step 1에서 확인한 구조에 맞춰 `ToolCallAgentGraph`를 상속한 `_GatedGraph`를 만든다. `_invoke_llm` 직전에 `exposed_tool_names(_tools().s)`로 도구를 골라 `self.llm.bind_tools(selected)`로 `self.agent`를 다시 만든다. 이것을 `her2_gated_agent` 워크플로 타입으로 `register_function`에 등록한다. 등록 함수 본문은 NAT의 `tool_calling_agent_workflow`(`nat/plugins/langchain/agent/tool_calling_agent/register.py:104-190`)를 복사해 그래프 클래스만 `_GatedGraph`로 바꾼다.

- [ ] **Step 4:** `uv run pytest -q` 전부 PASS, `RUN_LIVE_NAT=1` live 테스트 PASS
- [ ] **Step 5:** Task 5 측정을 다시 실행하고 결과 표에 B 행을 추가한다. 거부 0을 확인한다.
- [ ] **Step 6: Commit (요청 시)** — `feat(logic): 상태별로 허용 도구만 모델에 노출한다`

---

### Task 7: 인계와 기본 모드

**Files:**
- Modify: `logic/flow.py` (기본 모드 `nat`)
- Modify: `logic/README.md`, `docs/topics/her2/logic-b-handoff.md`, `docs/ADR.md`, `docs/topics/her2/nat-agent-loop.md`(상태), `docs/topics/her2/AGENTS.md`

- [ ] **Step 1: 기본 모드 변경**

`logic/flow.py`의 `os.getenv("LOGIC_AGENT_MODE", "rule")` → `os.getenv("LOGIC_AGENT_MODE", "nat")`. `test_rule_mode_is_default`를 `test_nat_mode_is_default`로 바꿔 `LOGIC_AGENT_MODE` 미설정 시 `run_candidate`가 불리는지 확인하게 고친다.

- [ ] **Step 2:** `uv run pytest -q` 전부 PASS

- [ ] **Step 3: 문서 갱신**
  - `logic/README.md`: 실행 절에 `LOGIC_AGENT_MODE`, `RUN_LIVE_NAT`, `python -m logic.measure_agent` 추가. "단계와 분기" 절에 도구 7개와 관문 표 링크.
  - `logic-b-handoff.md` 1절 표에 `B-07 NAT 에이전트 루프 | 동작 | <측정 결과 한 줄>` 행 추가. 5절(D6)에 의존성 `nvidia-nat[langchain]`, Python `<3.14`, 설치 용량(Task 1에서 `du -sh .venv`로 잰 값) 추가. 서비스 담당에게 `opinions[].reason` 문장이 도구 선택마다 달라진다는 점 명시.
  - `docs/ADR.md` 36행 상태: "NAT·모델 조합은 미검증" → 확인된 조합과 날짜.
  - `nat-agent-loop.md` 상태 줄: "설계. 구현·측정 전." → 실제 상태. `AGENTS.md` 설명의 "(설계, 미구현)" 갱신.

- [ ] **Step 4: 링크 확인**

Run: `git diff --check && grep -o '](\S*\.md[^)]*)' docs/topics/her2/nat-agent-loop.md | sort -u`
Expected: 공백 오류 없음, 나열된 링크 파일이 모두 존재

- [ ] **Step 5: Commit (요청 시)**

```bash
git add -A logic docs
git commit -m "docs(logic-b): NAT 에이전트 루프 인계와 기본 모드 전환"
```
