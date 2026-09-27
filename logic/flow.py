"""HER2 후보 검토의 판단 흐름 (계획서 B-03).

LogicRequest를 받아 후보별로 다섯 단계를 진행하고 LogicOutput을 만든다.
단계 ID는 임시 계약의 step_id를 그대로 쓴다.

    input_mapping        ② 입력 검사·공개 자료 조회
    evidence_review      ④ 사슬 번호 확인 및 구조 검사
    prediction           ③ Boltz-2 구조 예측 (기존 구조가 있으면 건너뜀)
    structure_comparison ⑤ 접촉 부위·구조상 문제 계산
    reporting            ⑥ 후보 비교·근거 설명

고정 파이프라인이 되지 않게 하는 분기는 설계 문서를 따른다.
일치하는 실험 구조가 있으면 예측을 생략하고, 입력이 맞지 않으면 그 후보를
먼저 보류하며, 필수 자료가 없으면 보완 요청으로 남긴다. 신뢰도가 높아도
입력 오류를 통과시키지 않고, 실패한 호출을 성공한 분석으로 표시하지 않는다.
"""

from __future__ import annotations

import math
import os
from uuid import uuid4
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import analysis, structures, runtime_skill
from .agent import Decider, Decision, Option, RuleDecider
from .agent_session import CandidateSession
from .contract import SCHEMA_VERSION, now_rfc3339, validate
from .nvidia_client import CallFailed, MissingCredentials, NvidiaClient

STEP_IDS = (
    "input_mapping",
    "evidence_review",
    "prediction",
    "structure_comparison",
    "reporting",
)

# 예측 요청을 보내기 전에 요구하는 최소 서열 길이. 형식 오류를 예측 호출로
# 넘기지 않기 위한 하한이며 과학적 기준이 아니다(Q05에서 확정).
MIN_CHAIN_LENGTH = 50

# 입력 검사가 받는 문자: 표준 20종 + IUPAC 모호·비표준 코드(X B Z U O).
# 서열로는 틀리지 않았으므로 입력 오류로 떨어뜨리지 않는다.
IUPAC_PROTEIN = set("ACDEFGHIKLMNPQRSTVWYXBZUO")
# Boltz-2가 받는 문자: 표준 20종 + X. 출처는 422 응답 본문 "Valid characters
# are: A, C, D, E, F, G, H, I, K, L, M, N, P, Q, R, S, T, V, W, X, Y"
# (2026-09-26, work/task-6b-diag/call_log.jsonl). 여기서 벗어난 서열은
# 유료 호출 전에 예측을 보류한다.
BOLTZ2_PROTEIN = set("ACDEFGHIKLMNPQRSTVWXY")

ProgressCallback = Callable[[dict[str, Any]], None]


def _format_fact_value(value: Any) -> str:
    """사실 문장에 값을 쓸 표기. 정수 값인 float는 "39.0"이 아니라 "39"로 쓴다.

    `analysis.contact_measurement`는 계약(Evidence.value: number)을 지키려고
    `float(len(residues))`로 저장한다. 그 값을 문장에 그대로 넣으면 모델이
    읽는 사실이 "39.0residue"가 되어, 모델이 자연스럽게 쓰는 "39"와 문자열이
    달라진다. 계약의 value 필드 자체는 그대로 두고, 문장 표기만 정수로
    맞춘다.
    """
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _explain(decision) -> str:
    """판단 결과를 화면에 그대로 쓸 문장으로.

    누가 정했는지를 문장 안에 넣는다. 모델이 못 답해서 규칙으로 간
    것을 모델이 판단한 것처럼 보이게 두면, 화면이 사실과 달라진다.
    """
    if decision.decided_by == "model":
        return f"{decision.reason} (판단: {decision.model})"
    # 실패 사유에는 서버가 돌려준 본문이 통째로 들어 있다. 화면에서 보니
    # {"error":{"message":...}} 가 그대로 문장 안에 박혔다. 자세한 내용은
    # call_log.jsonl에 남아 있으므로 여기서는 짧게 줄인다.
    why = decision.fallback_reason or ""
    if len(why) > 80:
        why = why[:80].rstrip() + "…"
    return f"{decision.reason} (판단: 규칙 — {why})"


@dataclass
class _CandidateState:
    candidate_id: str
    steps: dict[str, dict[str, str | None]]
    status: str = "queued"
    reason: str | None = None

    def set_step(self, step_id: str, status: str, reason: str | None = None) -> None:
        self.steps[step_id] = {"step_id": step_id, "status": status, "reason": reason}

    def to_progress(self) -> dict[str, Any]:
        current = next(
            (s for s in STEP_IDS if self.steps[s]["status"] in ("pending", "running")), None
        )
        return {
            "candidate_id": self.candidate_id,
            "status": self.status,
            "current_step": current,
            "steps": [self.steps[s] for s in STEP_IDS],
            "reason": self.reason,
        }


def select_structure(response: dict[str, Any]) -> tuple[int | None, list[float | None]]:
    """쓸 구조의 인덱스와 구조별 신뢰도를 함께 돌려준다.

    비어 있지 않은 구조 중 유효한 [0,1] 신뢰도가 가장 높은 것을 고른다.
    인덱스를 함께 돌려주는 이유: 같은 본문이 두 번 오면(실측에서 반복본이
    sha256까지 같았다) 파일을 대조해 어느 것을 골랐는지 되찾을 수 없다.
    """
    found = response.get("structures") or []
    usable = [i for i, item in enumerate(found) if isinstance(item, dict)
              and isinstance(item.get("structure"), str) and item["structure"].strip()]
    scores = response.get("confidence_scores")
    if isinstance(scores, (int, float)) and len(found) == 1:
        scores = [scores]
    # ponytail: 대응이 불명확한 점수 배열은 순위를 추정하지 않고 unknown으로 남긴다.
    if not isinstance(scores, list) or len(scores) != len(found):
        scores = [None] * len(found)
    scores = [float(s) if type(s) in (int, float) and math.isfinite(s) and 0 <= s <= 1
              else None for s in scores]
    if not usable:
        return None, scores
    return max(usable, key=lambda i: scores[i] if scores[i] is not None else -1), scores


class Flow:
    """한 번의 실행. 인스턴스는 재사용하지 않는다."""

    def __init__(
        self,
        request: dict[str, Any],
        *,
        client: NvidiaClient | None = None,
        progress: ProgressCallback | None = None,
        decider: Decider | None = None,
    ):
        validate(request, "LogicRequest")
        self.request = request
        self.run_id = request["run_id"]
        self.review_id = request["review_id"]
        self.data_mode = request["data_mode"]
        self.settings_version = request["settings_version"]
        self.work_dir = Path(request["work_dir"])
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.client = client if client is not None else NvidiaClient(self.work_dir)
        # 분기 선택은 판단부가 한다. 모델을 못 부르면 아래 default로 돌아간다.
        self.decider = decider if decider is not None else Decider(self.client)
        self._progress = progress
        self._stage_actor = "workflow"

        self.states: dict[str, _CandidateState] = {
            c["candidate_id"]: _CandidateState(
                c["candidate_id"],
                {s: {"step_id": s, "status": "pending", "reason": None} for s in STEP_IDS},
            )
            for c in request["input"]["candidates"]
        }
        self.structures: list[dict[str, Any]] = []
        self.conditions: list[dict[str, Any]] = []
        self.evidence: list[dict[str, Any]] = []
        self.opinions: list[dict[str, Any]] = []
        self.artifacts: list[dict[str, Any]] = []
        self.agent_traces: dict[str, list[dict[str, Any]]] = {}
        self.agent_errors: dict[str, str] = {}
        self.rule_finishes: dict[str, str] = {}

    # ------------------------------------------------------------ 진행 보고
    def _emit(self, candidate_id: str | None, step_id: str, status: str, reason: str | None) -> None:
        if candidate_id is not None:
            self.states[candidate_id].set_step(step_id, status, reason)
        update = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "candidate_id": candidate_id,
            "step_id": step_id,
            "status": status,
            "reason": reason,
            "updated_at": now_rfc3339(),
            "activity": {"event_id": uuid4().hex, "kind": "stage", "name": step_id,
                         "phase": status, "actor": self._stage_actor},
        }
        validate(update, "ProgressUpdate")
        if self._progress:
            self._progress(update)

    def _activity(self, cid: str, kind: str, name: str, phase: str, actor: str, **details) -> None:
        # Observation only: never advance a stage or expose model prompts/raw tool output.
        step = next((s for s in self.states[cid].steps.values() if s["status"] == "running"),
                    self.states[cid].steps["input_mapping"])
        update = {
            "schema_version": SCHEMA_VERSION, "run_id": self.run_id, "candidate_id": cid,
            "step_id": step["step_id"], "status": step["status"], "reason": None,
            "updated_at": now_rfc3339(),
            "activity": {"event_id": uuid4().hex, "kind": kind, "name": name,
                         "phase": phase, "actor": actor, **details},
        }
        validate(update, "ProgressUpdate")
        if self._progress:
            self._progress(update)

    # ------------------------------------------------------------ 실행
    def run(self) -> dict[str, Any]:
        mode = os.getenv("LOGIC_AGENT_MODE", "nat")
        if mode not in {"nat", "rule"}:
            raise ValueError("LOGIC_AGENT_MODE must be nat or rule")
        for candidate in self.request["input"]["candidates"]:
            if mode == "nat":
                self._run_candidate_nat(candidate)
            else:
                self._run_candidate(candidate)
        output = {
            "result": self._build_result(),
            "files": [],
        }
        validate(output, "LogicOutput")
        return output

    def _run_candidate(self, candidate: dict[str, Any]) -> None:
        previous = self._stage_actor
        self._stage_actor = "rule"
        try:
            self._resume(CandidateSession(candidate))
        finally:
            self._stage_actor = previous

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
            self.agent_errors[session.cid] = why
            self._continue_by_rule(session, why)

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
            s.match = self._lookup(candidate)
            s.lengths = self._lengths(candidate)
            self._emit(cid, "input_mapping", "completed", None)

        if s.match.blocked_reason:
            self._hold_candidate(cid, s.match.blocked_reason)
            s.terminal = "partial"
            return

        # ③ 분기: 기존 구조 / 예측 / 자료 부족 — 판단 주체는 self.decider
        if s.structure_id is None:
            choice = self._choose_source(cid, candidate, s.match)
            self._skill_choice(cid, choice)
            if choice.action == "use_experimental":
                s.structure_id = self._record_experimental(cid, s.match)
                if s.structure_id is None:
                    s.terminal = "failed"
                    return
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
        if s.terminal:
            return
        self.rule_finishes[s.cid] = why
        self._activity(s.cid, "fallback", "continue_by_rule", "running", "rule", reason=why[:200])
        saved = self.decider
        previous = self._stage_actor
        self._stage_actor = "rule"
        self.decider = RuleDecider(why, decisions=saved.decisions, model=saved.model)
        try:
            self._resume(s)
        finally:
            self.decider = saved
            self._stage_actor = previous

    # ------------------------------------------------------------ 입력 검사
    def _check_input(self, candidate: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        target = self.request["input"]["target"]
        if target.get("identifier") != "P04626" or not target.get("fasta"):
            problems.append("HER2 표적 ID와 검증된 세포외 구간 서열이 필요하다.")
        if target.get("fasta"):
            invalid = sorted(set(structures.sequence_body(target["fasta"])) - IUPAC_PROTEIN)
            if invalid:
                problems.append(f"표적 서열에 아미노산이 아닌 문자가 있다: {''.join(invalid)}.")
            elif structures.sequence_body(target["fasta"]) != structures.her2_target_sequence():
                problems.append("표적 서열이 검증된 HER2 세포외 구간과 일치하지 않는다.")
        for label, key, range_key in (
            ("중쇄", "heavy_chain_fasta", "heavy_analysis_range"),
            ("경쇄", "light_chain_fasta", "light_analysis_range"),
        ):
            body = structures.sequence_body(candidate[key])
            if not body:
                problems.append(f"{label} 서열에서 아미노산 문자를 찾지 못했다.")
                continue
            # 검사는 걸러내기 전 본문으로 한다. 숫자·기호가 조용히 사라지면
            # 잘못된 입력이 예측 호출까지 넘어간다.
            invalid = sorted(set(body) - IUPAC_PROTEIN)
            seq = structures.normalize_sequence(candidate[key])
            if invalid:
                problems.append(f"{label} 서열에 아미노산이 아닌 문자가 있다: {''.join(invalid)}.")
            rng = candidate.get(range_key)
            if rng:
                if rng["start"] > rng["end"]:
                    problems.append(f"{label} 분석 구간의 시작이 끝보다 크다.")
                elif rng["end"] > len(seq):
                    problems.append(
                        f"{label} 분석 구간의 끝({rng['end']})이 서열 길이({len(seq)})를 넘는다."
                    )
        return problems

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

    # ------------------------------------------------------------ 판단 분기
    def _lookup(self, candidate: dict[str, Any]) -> structures.StructureMatch:
        from .structure_sources import lookup
        return lookup(candidate, self.request["input"]["target"]["fasta"], self.work_dir)

    def _source_facts(self, candidate: dict[str, Any], match: structures.StructureMatch) -> list[str]:
        # 예측에 쓸 자료가 있는지도 사실로 넣는다. 구조 검색 결과만 주면
        # 모델은 "일치하는 구조가 없다"를 "자료가 부족하다"로 읽는다.
        # 실제로 그렇게 보류한 실행을 화면에서 확인했다.
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
        facts.extend(match.notes)
        if match.blocked_reason:
            facts.append(match.blocked_reason)
        return facts

    def _lengths(self, candidate: dict[str, Any]) -> dict[str, int]:
        return {
            "표적": len(structures.normalize_sequence(self.request["input"]["target"].get("fasta") or "")),
            "중쇄": len(structures.normalize_sequence(candidate["heavy_chain_fasta"])),
            "경쇄": len(structures.normalize_sequence(candidate["light_chain_fasta"])),
        }

    def _choose_source(
        self, cid: str, candidate: dict[str, Any], match: structures.StructureMatch
    ):
        """이 후보를 무엇으로 검토할지 고른다.

        설계 문서의 "일치하는 공개 실험 구조로 충분하면 불필요한 복합체
        예측을 생략한다"가 이 자리다. 규칙만 두면 부분 일치·자료 부족이
        전부 예측 호출로 떠밀린다.

        사실은 전부 코드가 조회한 것이다. 모델은 이 값들을 읽고 고르기만
        한다.
        """
        facts = self._source_facts(candidate, match)
        if match.complete:
            options = [
                Option("use_experimental", "이미 있는 공개 실험 구조로 검토한다. 예측을 건너뛴다."),
                Option("predict", "그래도 Boltz-2로 새로 예측해 교차 확인한다."),
            ]
            default = "use_experimental"
        else:
            # 문구를 두 번 고쳤다. 처음엔 "Boltz-2로 예측해 검토한다"였는데
            # 모델이 "일치하는 공개 구조가 없다"를 보류 사유로 읽고 계속
            # hold를 골랐다. 예측이 **없는 구조를 만들어 내는 행동**이라는
            # 것을 몰랐던 것이다. 답을 유도하는 게 아니라 각 행동이 실제로
            # 무엇을 하는지 적는다. hold의 조건은 코드의 MIN_CHAIN_LENGTH가
            # 이미 정해 둔 것과 같다.
            options = [
                Option(
                    "predict",
                    "표적·중쇄·경쇄 서열을 Boltz-2에 보내 복합체 구조를 새로 만든다. "
                    "공개 구조가 없을 때 쓰는 정상 경로다.",
                ),
                Option(
                    "hold",
                    "예측 입력으로 쓸 서열 자체가 없거나 너무 짧을 때만 고른다. "
                    "서열이 충분하면 고르지 않는다.",
                ),
            ]
            default = "predict"
        return self.decider.choose(
            "structure_source",
            question=(
                f"후보 {cid}를 검토할 구조를 어디서 얻을 것인가? "
                "부분 일치는 같은 항체로 보지 않는다. "
                "일치하는 공개 구조가 없다는 것 자체는 보류 사유가 아니다."
            ),
            facts=facts,
            options=options,
            default=default,
        )

    # ------------------------------------------------------------ 기존 구조 경로
    def _record_experimental(self, cid: str, match: structures.StructureMatch) -> str | None:
        catalog = structures.load_catalog()
        public = match.public or catalog[match.pdb_id]
        structure_id = f"st-{cid}-{public.pdb_id.lower()}"
        source = {
            "title": f"RCSB PDB {public.pdb_id}",
            "url": public.source_url,
            "record_id": public.pdb_id,
        }
        chains = [
            self._chain("target", match.target_entity),
            self._chain("heavy", match.heavy_entity),
            self._chain("light", match.light_entity),
        ]
        if match.chain_mapping:
            chains = list(match.chain_mapping)
        actual_sha = structures.file_sha256(public.path)
        if actual_sha != public.verified_sha256:
            reason = "공개 구조 파일의 해시가 검증된 원본과 다르다."
            self._emit(cid, "evidence_review", "failed", reason)
            for step in ("prediction", "structure_comparison", "reporting"):
                self._emit(cid, step, "skipped", reason)
            self.states[cid].status = "failed"
            self.states[cid].reason = reason
            self._hold_opinion(cid, "structure_availability", "not_assessed", reason)
            return None
        # Keep the reviewed bytes with this run so later requests cannot replace them.
        saved_path = self.work_dir / f"{structure_id}.cif"
        saved_path.write_bytes(public.path.read_bytes())
        if structures.file_sha256(saved_path) != actual_sha:
            raise ValueError("구조 복사 중 파일 무결성이 달라졌다.")
        self.structures.append(
            {
                "structure_id": structure_id,
                "candidate_id": cid,
                "artifact_id": f"af-{structure_id}",
                "kind": "experimental",
                "source": source,
                "model_number": 1,
                "assembly_id": None,
                "chain_mapping": [c for c in chains if c],
                "residue_mapping": [],
                "alignment": None,
            }
        )
        self.artifacts.append(
            {
                "artifact_id": f"af-{structure_id}",
                "role": "structure",
                "format": "mmcif",
                "status": "ready",
                "file_name": saved_path.name,
                "size_bytes": saved_path.stat().st_size,
                "sha256": actual_sha,
                "reason": None,
            }
        )
        # 핵심 조건과, 당쇄를 확보한 경우의 주변 구조 조건을 나눠 둔다.
        core_id = f"cond-{cid}-core"
        self.conditions.append(
            {
                "condition_id": core_id,
                "candidate_id": cid,
                "kind": "core",
                "structure_ids": [structure_id],
                "included_components": ["target", "heavy", "light"],
                "gaps": list(match.notes),
                "sources": [source],
            }
        )
        if public.glycan_descriptions:
            self.conditions.append(
                {
                    "condition_id": f"cond-{cid}-context",
                    "candidate_id": cid,
                    "kind": "context",
                    "structure_ids": [structure_id],
                    "included_components": ["target", "heavy", "light", "glycan"],
                    "gaps": [
                        "당쇄 조성·점유율은 이 구조 파일에 기록된 범위까지만 확인했다.",
                        "표면 노출 비교는 FreeSASA 검증 전이라 계산하지 않았다.",
                    ],
                    "sources": [source],
                }
            )
        self._emit(cid, "evidence_review", "completed", None)
        return structure_id

    def _chain(self, role: str, entity: structures.PolymerEntity | None) -> dict[str, Any] | None:
        if entity is None:
            return None
        return {
            "role": role,
            "model_number": 1,
            "label_asym_id": entity.strand_ids[0] if entity.strand_ids else None,
            "auth_asym_id": None,
            "operator_id": None,
        }

    def _skill_choice(self, cid: str, decision: Decision) -> None:
        phase = {"predict": "selected", "use_experimental": "skipped", "hold": "held"}[decision.action]
        self._activity(cid, "skill", "boltz2-nim", phase,
                       "agent" if decision.decided_by == "model" else "rule",
                       skill=runtime_skill.identity(), reason=decision.reason[:1000],
                       next_action={"predict": "predict_structure", "use_experimental": "compare_structure", "hold": "종료"}[decision.action])

    def _verify_skill_result(self, cid: str, response: dict, structure_id: str | None) -> None:
        from .contacts import parse_atoms
        entries = response.get("structures") or []
        structure = next((s for s in self.structures if s["structure_id"] == structure_id), None)
        scores = response.get("confidence_scores")
        confidence_ok = (isinstance(scores, list) and len(scores) == len(entries)
                         and all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in scores))
        atoms_ok = False
        if structure:
            try:
                atoms_ok = bool(parse_atoms((self.work_dir / f"{structure_id}.cif").read_text()))
            except (OSError, ValueError):
                pass
        mapping_ok = bool(structure and all(any(c["role"] == role and c.get("label_asym_id")
                          for c in structure["chain_mapping"]) for role in ("target", "heavy", "light")))
        checks = [{"name": name, "status": "passed" if passed else "failed"} for name, passed in [
            ("응답 구조 존재", len(entries) >= 1),
            ("mmCIF 형식", bool(entries) and all(isinstance(e, dict) and e.get("format", "mmcif") == "mmcif" for e in entries)),
            ("좌표 파싱", atoms_ok), ("입력 서열·사슬 대응", mapping_ok),
        ]]
        checks.append({"name": "구조별 신뢰도 범위·개수", "status": "passed" if confidence_ok else "unverified"})
        status = "failed" if any(c["status"] == "failed" for c in checks) else "unverified" if not confidence_ok else "passed"
        self._activity(cid, "verification", "boltz2-nim", "completed", "code",
                       skill=runtime_skill.identity(), verification={"status": status, "checks": checks},
                       reason="응답 형식과 입력 대응 확인이며 구조 정확도·결합력 검증은 아닙니다.",
                       next_action="compare_structure" if structure_id else "종료")

    # ------------------------------------------------------------ 예측 경로
    def _predict(
        self, cid: str, candidate: dict[str, Any], match: structures.StructureMatch
    ) -> str | None:
        """예측을 시도한다. 자료가 부족하거나 호출이 막히면 None을 돌려 보류한다."""
        try:
            runtime_skill.load_boltz_skill()
        except (OSError, ValueError, KeyError):
            reason = "고정된 NVIDIA 스킬 파일을 검증하지 못해 호출을 보류합니다."
            self._activity(cid, "skill", "boltz2-nim", "held", "code", skill=runtime_skill.identity(), reason=reason, next_action="스킬 파일 확인")
            self._hold_candidate(cid, reason)
            return None
        target_seq = structures.normalize_sequence(self.request["input"]["target"].get("fasta") or "")
        heavy = structures.normalize_sequence(candidate["heavy_chain_fasta"])
        light = structures.normalize_sequence(candidate["light_chain_fasta"])

        missing: list[str] = []
        if len(target_seq) < MIN_CHAIN_LENGTH:
            missing.append(
                f"표적 서열이 없거나 {MIN_CHAIN_LENGTH}자 미만이라 복합체 예측 입력을 만들 수 없다."
            )
        for label, seq in (("중쇄", heavy), ("경쇄", light)):
            if len(seq) < MIN_CHAIN_LENGTH:
                missing.append(f"{label} 서열이 {MIN_CHAIN_LENGTH}자 미만이다.")
        for label, seq in (("표적", target_seq), ("중쇄", heavy), ("경쇄", light)):
            rejected = sorted(set(seq) - BOLTZ2_PROTEIN)
            if rejected:
                missing.append(
                    f"{label} 서열에 Boltz-2가 받지 않는 문자({''.join(rejected)})가 있어 예측을 보내지 않았다."
                )
        if missing:
            reason = " ".join(missing) + " 자료 보완 후 다시 실행해야 한다."
            self._activity(cid, "skill", "boltz2-nim", "held", "code", skill=runtime_skill.identity(), reason=reason[:1000], next_action="입력 보완")
            self._emit(cid, "evidence_review", "held", reason)
            self._emit(cid, "prediction", "held", reason)
            for step in ("structure_comparison", "reporting"):
                self._emit(cid, step, "skipped", "예측 구조가 없어 진행하지 않았다.")
            self.states[cid].reason = reason
            self._hold_opinion(cid, "structure_availability", "hold", reason, limitations=missing)
            return None

        partial_note = None
        if match.pdb_id and (match.heavy_exact or match.light_exact):
            partial_note = (
                f"{match.pdb_id}과 한쪽 사슬만 서열이 일치한다. 같은 후보로 보지 않고 예측 경로로 진행했다."
            )
        self._emit(cid, "evidence_review", "completed", partial_note)

        self._emit(cid, "prediction", "running", None)
        polymers = [
            {"id": "A", "molecule_type": "protein", "sequence": target_seq},
            {"id": "H", "molecule_type": "protein", "sequence": heavy},
            {"id": "L", "molecule_type": "protein", "sequence": light},
        ]
        self._activity(cid, "skill", "boltz2-nim", "running", "code", skill=runtime_skill.identity(), next_action="응답 검증")
        try:
            response = self.client.predict_complex(polymers, diffusion_samples=2)
        except MissingCredentials as exc:
            self._activity(cid, "skill", "boltz2-nim", "held", "code", skill=runtime_skill.identity(), reason="인증 정보가 없어 호출하지 못했습니다.", next_action="인증 확인")
            reason = str(exc)
            self._emit(cid, "prediction", "held", reason)
            for step in ("structure_comparison", "reporting"):
                self._emit(cid, step, "skipped", "예측 구조가 없어 진행하지 않았다.")
            self.states[cid].reason = reason
            self._hold_opinion(cid, "structure_availability", "hold", reason)
            return None
        except CallFailed as exc:
            self._activity(cid, "skill", "boltz2-nim", "failed", "code", skill=runtime_skill.identity(), reason="예측 호출이 실패했습니다.", next_action="실패 기록 확인")
            self._fail_prediction(cid, str(exc))
            return None

        self._activity(cid, "skill", "boltz2-nim", "completed", "code", skill=runtime_skill.identity(), next_action="응답 검증")
        structure_id = self._record_predicted(cid, response, {"target": target_seq, "heavy": heavy, "light": light})
        self._verify_skill_result(cid, response, structure_id)
        return structure_id

    def _fail_prediction(self, cid: str, reason: str) -> None:
        self._emit(cid, "prediction", "failed", reason)
        for step in ("structure_comparison", "reporting"):
            self._emit(cid, step, "skipped", "예측이 실패해 진행하지 않았다.")
        self.states[cid].status = "failed"
        self.states[cid].reason = reason
        self._hold_opinion(cid, "structure_availability", "not_assessed", reason)

    def _record_predicted(
        self, cid: str, response: dict[str, Any], sequences: dict[str, str] | None = None
    ) -> str | None:
        found = response.get("structures") or []
        selected, scores = select_structure(response)
        if selected is None:
            reason = "예측 호출은 성공했지만 응답에 구조가 없다."
            self._emit(cid, "prediction", "failed", reason)
            for step in ("structure_comparison", "reporting"):
                self._emit(cid, step, "skipped", "예측 구조가 없어 진행하지 않았다.")
            self.states[cid].status = "failed"
            self.states[cid].reason = reason
            self._hold_opinion(cid, "structure_availability", "not_assessed", reason)
            return None

        structure_id = f"st-{cid}-boltz2"
        artifact_id = f"af-{structure_id}"
        path = self.work_dir / f"{structure_id}.cif"
        from .prediction_validation import validate_prediction
        try:
            if found[selected].get("format", "mmcif") != "mmcif":
                raise ValueError("지원하지 않는 예측 구조 형식이다.")
            mapping = validate_prediction(found[selected]["structure"], sequences or {})
        except ValueError as exc:
            self._fail_prediction(cid, str(exc))
            return None
        path.write_text(found[selected]["structure"], encoding="utf-8")
        self.structures.append(
            {
                "structure_id": structure_id,
                "candidate_id": cid,
                "artifact_id": artifact_id,
                "kind": "predicted",
                "source": {
                    "title": "NVIDIA Boltz-2 NIM 예측",
                    "url": "https://build.nvidia.com/mit/boltz2",
                    "record_id": self.run_id,
                },
                "model_number": 1,
                "assembly_id": None,
                "chain_mapping": mapping,
                "residue_mapping": [],
                "alignment": None,
            }
        )
        self.artifacts.append(
            {
                "artifact_id": artifact_id,
                "role": "structure",
                "format": "mmcif",
                "status": "ready",
                "file_name": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": structures.file_sha256(path),
                "reason": None,
            }
        )
        self.conditions.append(
            {
                "condition_id": f"cond-{cid}-core",
                "candidate_id": cid,
                "kind": "core",
                "structure_ids": [structure_id],
                "included_components": ["target", "heavy", "light"],
                "gaps": ["예측 구조에는 당쇄·주변 구조가 포함되지 않는다."],
                "sources": [],
            }
        )
        # 응답이 실제로 준 신뢰도만 근거로 남긴다. 주지 않은 지표는 만들지 않는다.
        # 완료 통보는 기록이 다 끝난 뒤에 한다. 되돌리기(agent_session.predict_structure)는
        # 기록 리스트만 자르므로, 먼저 내보낸 completed 이벤트와 단계 상태는 복구되지 않는다.
        self._record_confidence(cid, structure_id, scores[selected])
        self._record_pose_samples(cid, response, selected, sequences or {}, structure_id)
        self._emit(cid, "prediction", "completed",
                   f"응답 구조 {len(found)}개 중 {selected + 1}번째를 선택했다. "
                   + ("유효한 신뢰도 점수가 가장 높다." if scores[selected] is not None
                      else "신뢰도로 순위를 정할 수 없어 첫 유효 구조를 사용했다."))
        return structure_id

    def _record_pose_samples(self, cid, response, selected, sequences, reference_id):
        from .prediction_validation import validate_prediction
        from .pose_analysis import compare
        found = response.get('structures') or []
        condition = next(c for c in self.conditions if c['condition_id'] == f'cond-{cid}-core')
        source = next(s['source'] for s in self.structures if s['structure_id'] == reference_id)
        measurement = analysis.Measurement(topic='pose_consistency', kind='computed', state='unknown',
            reason='동일 입력의 검증된 예측 2샘플이 없어 자세 차이를 계산하지 않았다.', sources=[source])
        evidence_structure = reference_id
        if len(found) == 2:
            other = 1 - selected
            item = found[other]
            try:
                if item.get('format', 'mmcif') != 'mmcif':
                    raise ValueError('지원하지 않는 예측 구조 형식이다.')
                mapping = validate_prediction(item['structure'], sequences)
                sample_id = f'st-{cid}-boltz2-sample-{other + 1}'
                path = self.work_dir / f'{sample_id}.cif'
                path.write_text(item['structure'], encoding='utf-8')
                sample = {'structure_id': sample_id, 'candidate_id': cid, 'artifact_id': f'af-{sample_id}',
                    'kind': 'predicted', 'source': source, 'model_number': 1, 'assembly_id': None,
                    'chain_mapping': mapping, 'residue_mapping': [], 'alignment': None}
                self.structures.append(sample)
                self.artifacts.append({'artifact_id': sample['artifact_id'], 'role': 'structure', 'format': 'mmcif',
                    'status': 'ready', 'file_name': path.name, 'size_bytes': path.stat().st_size,
                    'sha256': structures.file_sha256(path), 'reason': None})
                condition['structure_ids'].append(sample_id)
                detail = compare(found[selected]['structure'], item['structure'], sequences)
                reference = next(s for s in self.structures if s['structure_id'] == reference_id)
                def target_residues(record):
                    chain = next(m['label_asym_id'] for m in record['chain_mapping'] if m['role'] == 'target')
                    return [analysis.residue(label_asym_id=chain, label_seq_id=n) for n in detail['target_positions']]
                sample['alignment'] = {'reference_structure_id': reference_id, 'reference_residues': target_residues(reference),
                    'mobile_residues': target_residues(sample), 'matrix': detail['matrix'], 'applied': False,
                    'coordinate_unit': 'angstrom'}
                evidence_structure = sample_id
                measurement = analysis.Measurement(topic='pose_consistency', kind='computed', state='measured',
                    value=detail['antibody_ca_rmsd'], unit='angstrom', sources=[source],
                    definition=f"예측 2샘플의 공통 표적 Cα {detail['target_ca_count']}개 정렬 후 항체 Cα {detail['antibody_ca_count']}개의 RMSD. "
                    f"표적 정렬 RMSD {detail['target_ca_rmsd']:.4f} Å. 공통 관측 잔기만 비교하며 일치도는 정확도·결합력 증거가 아니다. "
                    f"참조 {reference_id}, 비교 {sample_id}; 원본 좌표는 보존하고 표시 시 정렬한다.")
            except (ValueError, KeyError, TypeError) as exc:
                measurement.state, measurement.reason = 'failed', f'복수 예측 비교 실패: {exc}'
        self._add_evidence(cid, condition['condition_id'], evidence_structure, measurement)

    def _record_confidence(self, cid: str, structure_id: str, value: float | None) -> None:
        condition_id = f"cond-{cid}-core"
        if value is None:
            self._add_evidence(
                cid,
                condition_id,
                structure_id,
                analysis.Measurement(
                    topic="prediction_confidence",
                    kind="computed",
                    state="unknown",
                    reason="응답에 confidence_scores가 없거나 해석할 수 있는 형식이 아니다.",
                ),
            )
            return
        self._add_evidence(
            cid,
            condition_id,
            structure_id,
            analysis.Measurement(
                topic="prediction_confidence",
                kind="computed",
                state="measured",
                value=value,
                unit="score",
                definition=(
                    "선택한 Boltz-2 구조에 대응하는 confidence_scores 값. "
                    "구조 예측의 자기 평가이며 결합력·효능 지표가 아니다."
                ),
                sources=[
                    {
                        "title": "NVIDIA Boltz-2 NIM 응답",
                        "url": "https://build.nvidia.com/mit/boltz2",
                        "record_id": self.run_id,
                    }
                ],
            ),
        )

    # ------------------------------------------------------------ ⑤ 비교
    def _compare(self, cid: str, structure_id: str, match: structures.StructureMatch) -> None:
        from . import surface_analysis
        self._emit(cid, "structure_comparison", "running", None)
        core_id = f"cond-{cid}-core"
        record = next(s for s in self.structures if s["structure_id"] == structure_id)
        predicted = record["kind"] == "predicted"
        artifact = next(a for a in self.artifacts if a["artifact_id"] == record["artifact_id"])
        path = self.work_dir / artifact["file_name"]
        source = record["source"]
        if not predicted and match.calculation_hold_reason:
            contact = analysis.Measurement.not_run("interface_contact_residues", match.calculation_hold_reason)
            contact.sources = [source]
        else:
            contact = analysis.predicted_contact_measurement(path, record["chain_mapping"], source, predicted=predicted,
                        residue_ranges=None if predicted else {chain: (start, end) for chain, start, end in match.residue_ranges})
        self._add_evidence(cid, core_id, structure_id, contact)
        if predicted:
            self._add_evidence(cid, core_id, structure_id, analysis.reference_epitope_overlap_measurement(
                path, record["chain_mapping"], self.request["input"]["target"]["fasta"], source))
        candidate = next(c for c in self.request["input"]["candidates"] if c["candidate_id"] == cid)
        values = surface_analysis.calculate(path.read_text(encoding="utf-8"), record["chain_mapping"], {
            "target": self.request["input"]["target"]["fasta"],
            "heavy": candidate["heavy_chain_fasta"], "light": candidate["light_chain_fasta"],
        })
        record["residue_mapping"] = values["residues"]
        record["chain_mapping"] = [m for m in record["chain_mapping"] if m["role"] != "context"] + [
            {"role": "context", "model_number": 1, "label_asym_id": chain, "auth_asym_id": None, "operator_id": None}
            for chain in values["context_chains"]]
        context_id = f"cond-{cid}-context"
        if not any(c["condition_id"] == context_id for c in self.conditions):
            self.conditions.append({"condition_id": context_id, "candidate_id": cid, "kind": "context",
                "structure_ids": [structure_id], "included_components": ["target", "heavy", "light"],
                "gaps": [], "sources": [source]})
        definitions = {
            "surface_exposure": "선택한 관측 단백질 원자만의 용매 접근 표면적",
            "buried_sasa_sum": "같은 좌표의 표적 단독+Fab 단독−복합체 SASA. 양쪽 감소량의 합이며 2로 나누지 않음",
            "observed_glycan_protein_sasa_reduction": "동일 단백질 좌표의 core SASA−관측 NAG를 포함한 context의 단백질 SASA",
        }
        for kind, condition_id, topics in (("core", core_id, ("surface_exposure", "buried_sasa_sum")),
                                           ("context", context_id, ("surface_exposure", "observed_glycan_protein_sasa_reduction"))):
            condition = next(c for c in self.conditions if c["condition_id"] == condition_id)
            condition["gaps"] = list(match.notes) + values["gaps"] + ["미관측 원자·전체 당쇄·세포막은 복원하지 않았다. 관측 좌표에 한정한 기하학 계산이다."]
            condition["included_components"] = ["target", "heavy", "light"] + (["glycan"] if kind == "context" and values[kind] else [])
            for topic in topics:
                if values[kind] is not None:
                    m = analysis.Measurement(topic=topic, kind="computed", state="measured", value=values[kind][topic],
                        unit="angstrom^2", definition=definitions[topic] + " (Shrake–Rupley, probe 1.4 Å, 960점, C/N/O/S 반지름). 결합력·효능·전체 접근성 지표가 아니다.", sources=[source])
                else:
                    m = analysis.Measurement(topic=topic, kind="computed", state="unknown" if kind == "context" else "not_run",
                        reason=values.get("reason") or values["context_reason"])
                self._add_evidence(cid, condition_id, structure_id, m)
            from .clash_analysis import calculate as calculate_clashes
            if values[kind] is not None:
                clash = calculate_clashes(path.read_text(encoding='utf-8'), record['chain_mapping'], values['residues'],
                    values['context_chains'] if kind == 'context' else [], self.work_dir / f'clashes-{cid}-{kind}', source)
            else:
                clash = analysis.Measurement.not_run('atom_clash', values.get('reason') or values['context_reason'])
            self._add_evidence(cid, condition_id, structure_id, clash)
            self._add_evidence(cid, condition_id, structure_id, analysis.Measurement(
                topic='whole_range_accessibility', kind='unknown', state='unknown',
                reason='미관측 원자·당쇄·막 환경 때문에 전체 구간 접근성은 판단하지 않았다.'))
        self._emit(cid, "structure_comparison", "completed", None)

    # ------------------------------------------------------------ ⑥ 보고
    def _opinion_facts(self, cid: str) -> tuple[list[str], list[dict[str, Any]], list[dict[str, Any]]]:
        mine = [e for e in self.evidence if e["candidate_id"] == cid]
        measured = [e for e in mine if e["measurement_state"] == "measured"]
        unmeasured = [e for e in mine if e["measurement_state"] != "measured"]
        def _measured_fact(e: dict[str, Any]) -> str:
            value = _format_fact_value(e["value"])
            unit = e["unit"]
            # 숫자 바로 뒤에 영문 단위를 붙이면("39residue") 식별자로 오인돼
            # invented_numbers가 값 주장으로 보지 않는다. 공백으로 떼어 둔다.
            suffix = f" {unit}" if unit else ""
            condition = next(c for c in self.conditions if c['condition_id'] == e['condition_id'])
            label = "관측 당 포함" if condition['kind'] == 'context' else "단백질 중심"
            return f"[{label}] {e['topic']}: {value}{suffix} ({e['definition']})"

        facts = [
            f"계산해 확보한 근거 {len(measured)}건, 아직 계산하지 않은 항목 {len(unmeasured)}건.",
            *(_measured_fact(e) for e in measured if e["definition"]),
            *(f"{e['topic']}: 미계산 — {e['reason']}" for e in unmeasured if e["reason"]),
        ]
        return facts, measured, unmeasured

    def _report(
        self,
        cid: str,
        structure_id: str,
        match: structures.StructureMatch,
        verdict: Decision | None = None,
    ) -> None:
        self._emit(cid, "reporting", "running", None)
        facts, measured, unmeasured = self._opinion_facts(cid)

        # Availability is a contract decision per topic; another model call cannot
        # supply missing measurements. Keep the agent's submission in its trace.
        from .review_policy import topic_opinions
        if verdict is None:
            action = "reviewable" if measured and not unmeasured else "needs_confirmation"
            verdict = RuleDecider("항목별 근거 상태로 판정한다.", decisions=self.decider.decisions,
                                  model=self.decider.model).choose(
                "review_opinion", question="확보한 근거의 검토 범위", facts=facts,
                options=[Option(action, "각 항목의 근거 상태를 보존한다.")], default=action)
        attribution = f"모델 {verdict.model}" if verdict.decided_by == "model" else "규칙"
        if cid in self.rule_finishes:
            attribution += f" — {self.rule_finishes[cid][:80]}"
        for condition in (c for c in self.conditions if c["candidate_id"] == cid):
            items = [e for e in self.evidence if e["condition_id"] == condition["condition_id"]]
            self.opinions.extend(topic_opinions(cid, condition, items, attribution))
        self._emit(cid, "reporting", "completed", None)

    # ------------------------------------------------------------ 보조
    def _add_evidence(
        self,
        cid: str,
        condition_id: str,
        structure_id: str | None,
        m: analysis.Measurement,
    ) -> None:
        evidence = {
            "evidence_id": f"ev-{cid}-{condition_id.rsplit('-', 1)[-1]}-{m.topic}",
            "candidate_id": cid,
            "condition_id": condition_id,
            "structure_id": structure_id,
            "topic": m.topic,
            "kind": m.kind,
            "measurement_state": m.state,
            "value": m.value,
            "unit": m.unit,
            "definition": m.definition,
            "reason": m.reason,
            "residues": m.residues,
            "sources": m.sources,
        }
        validate(evidence, "Evidence")
        self.evidence.append(evidence)

    def _hold_opinion(
        self,
        cid: str,
        topic: str,
        decision: str,
        reason: str,
        *,
        limitations: list[str] | None = None,
    ) -> None:
        condition_id = f"cond-{cid}-core"
        if not any(c["condition_id"] == condition_id for c in self.conditions):
            self.conditions.append(
                {
                    "condition_id": condition_id,
                    "candidate_id": cid,
                    "kind": "core",
                    "structure_ids": [],
                    "included_components": [],
                    "gaps": [reason],
                    "sources": [],
                }
            )
        self.opinions.append(
            {
                "opinion_id": f"op-{cid}-{topic}",
                "candidate_id": cid,
                "condition_id": condition_id,
                "topic": topic,
                "decision": decision,
                "evidence_ids": [],
                "conflicting_evidence_ids": [],
                "reason": reason,
                "limitations": limitations or [],
                "follow_up_questions": ["보완할 입력·자료를 확인한 뒤 새 실행으로 다시 접수해야 한다."],
            }
        )

    def _build_result(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "data_mode": self.data_mode,
            "run_id": self.run_id,
            "review_id": self.review_id,
            "candidate_ids": [c["candidate_id"] for c in self.request["input"]["candidates"]],
            "created_at": now_rfc3339(),
            "settings_version": self.settings_version,
            "structures": self.structures,
            "conditions": self.conditions,
            "evidence": self.evidence,
            "opinions": self.opinions,
            "artifacts": self.artifacts,
        }

    # ------------------------------------------------------------ 실행 상태
    def run_status(self) -> str:
        statuses = {s.status for s in self.states.values()}
        if statuses <= {"completed"}:
            return "completed"
        if "completed" in statuses or "partial" in statuses:
            return "partial"
        return "failed"

    def candidate_progress(self) -> list[dict[str, Any]]:
        return [self.states[c["candidate_id"]].to_progress()
                for c in self.request["input"]["candidates"]]


def run_flow(
    request: dict[str, Any],
    *,
    client: NvidiaClient | None = None,
    progress: ProgressCallback | None = None,
    decider: Decider | None = None,
) -> tuple[dict[str, Any], Flow]:
    flow = Flow(request, client=client, progress=progress, decider=decider)
    return flow.run(), flow
