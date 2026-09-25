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

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import analysis, structures
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

ProgressCallback = Callable[[dict[str, Any]], None]


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


class Flow:
    """한 번의 실행. 인스턴스는 재사용하지 않는다."""

    def __init__(
        self,
        request: dict[str, Any],
        *,
        client: NvidiaClient | None = None,
        progress: ProgressCallback | None = None,
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
        self._progress = progress

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
        }
        validate(update, "ProgressUpdate")
        if self._progress:
            self._progress(update)

    # ------------------------------------------------------------ 실행
    def run(self) -> dict[str, Any]:
        for candidate in self.request["input"]["candidates"]:
            self._run_candidate(candidate)
        output = {
            "result": self._build_result(),
            "files": [],
        }
        validate(output, "LogicOutput")
        return output

    def _run_candidate(self, candidate: dict[str, Any]) -> None:
        cid = candidate["candidate_id"]
        state = self.states[cid]
        state.status = "running"

        # ① ② 입력 검사
        self._emit(cid, "input_mapping", "running", None)
        problems = self._check_input(candidate)
        if problems:
            reason = " ".join(problems)
            self._emit(cid, "input_mapping", "failed", reason)
            for step in STEP_IDS[1:]:
                self._emit(cid, step, "skipped", "입력 정정 전에는 진행하지 않는다.")
            state.status = "failed"
            state.reason = reason
            self._hold_opinion(cid, "input", "hold", reason, limitations=problems)
            return

        # 공개 자료 조회
        match = structures.find_structure(
            candidate["heavy_chain_fasta"], candidate["light_chain_fasta"]
        )
        self._emit(cid, "input_mapping", "completed", None)

        # ③ 분기: 기존 구조 / 예측 / 자료 부족
        if match.complete:
            structure_id = self._record_experimental(cid, match)
            self._emit(cid, "prediction", "skipped", "일치하는 공개 실험 구조가 있어 예측하지 않았다.")
        else:
            structure_id = self._predict(cid, candidate, match)
            if structure_id is None:
                # _predict가 이미 failed로 표시했으면 덮어쓰지 않는다.
                # 실패한 호출을 부분 결과로 바꾸지 않기 위한 것이다.
                if state.status == "running":
                    state.status = "partial"
                return

        self._compare(cid, structure_id, match)
        self._report(cid, structure_id, match)
        state.status = "completed"

    # ------------------------------------------------------------ 입력 검사
    def _check_input(self, candidate: dict[str, Any]) -> list[str]:
        problems: list[str] = []
        target = self.request["input"]["target"]
        if not (target.get("identifier") or target.get("fasta")):
            problems.append("표적 HER2의 식별자와 서열이 모두 없다.")
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
            invalid = sorted(set(body) - set("ACDEFGHIKLMNPQRSTVWYXBZUO"))
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

    # ------------------------------------------------------------ 기존 구조 경로
    def _record_experimental(self, cid: str, match: structures.StructureMatch) -> str:
        catalog = structures.load_catalog()
        public = catalog[match.pdb_id]
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
        actual_sha = structures.file_sha256(public.path)
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
                "file_name": public.path.name,
                "size_bytes": public.path.stat().st_size,
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
                "gaps": [],
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

    # ------------------------------------------------------------ 예측 경로
    def _predict(
        self, cid: str, candidate: dict[str, Any], match: structures.StructureMatch
    ) -> str | None:
        """예측을 시도한다. 자료가 부족하거나 호출이 막히면 None을 돌려 보류한다."""
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
        if missing:
            reason = " ".join(missing) + " 자료 보완 후 다시 실행해야 한다."
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
        try:
            response = self.client.predict_complex(polymers)
        except MissingCredentials as exc:
            reason = str(exc)
            self._emit(cid, "prediction", "held", reason)
            for step in ("structure_comparison", "reporting"):
                self._emit(cid, step, "skipped", "예측 구조가 없어 진행하지 않았다.")
            self.states[cid].reason = reason
            self._hold_opinion(cid, "structure_availability", "hold", reason)
            return None
        except CallFailed as exc:
            reason = str(exc)
            self._emit(cid, "prediction", "failed", reason)
            for step in ("structure_comparison", "reporting"):
                self._emit(cid, step, "skipped", "예측이 실패해 진행하지 않았다.")
            self.states[cid].status = "failed"
            self.states[cid].reason = reason
            self._hold_opinion(cid, "structure_availability", "not_assessed", reason)
            return None

        return self._record_predicted(
            cid, response, {"target": target_seq, "heavy": heavy, "light": light}
        )

    def _predicted_chain_mapping(
        self, path: Path, sequences: dict[str, str]
    ) -> list[dict[str, Any]]:
        """반환된 mmCIF에서 실제 사슬 ID를 읽는다.

        요청에 보낸 id를 그대로 믿지 않는다. 실제 응답에서 Boltz-2는 보낸
        A·H·L을 순서대로 A·B·C로 다시 붙였다. 서열로 대응을 찾고, 찾지
        못하면 지어내지 않고 null로 둔다.
        """
        by_sequence: dict[str, str] = {}
        try:
            entities, _ = structures.parse_entities(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            entities = ()
        for entity in entities:
            if entity.sequence and entity.strand_ids:
                by_sequence.setdefault(entity.sequence, entity.strand_ids[0])
        return [
            {
                "role": role,
                "model_number": 1,
                "label_asym_id": by_sequence.get(sequences.get(role, "")),
                "auth_asym_id": None,
                "operator_id": None,
            }
            for role in ("target", "heavy", "light")
        ]

    def _record_predicted(
        self, cid: str, response: dict[str, Any], sequences: dict[str, str] | None = None
    ) -> str | None:
        found = response.get("structures") or []
        if not found:
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
        path.write_text(found[0]["structure"], encoding="utf-8")
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
                "chain_mapping": self._predicted_chain_mapping(path, sequences or {}),
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
        self._emit(cid, "prediction", "completed", None)

        # 응답이 실제로 준 신뢰도만 근거로 남긴다. 주지 않은 지표는 만들지 않는다.
        self._record_confidence(cid, structure_id, response)
        return structure_id

    def _record_confidence(self, cid: str, structure_id: str, response: dict[str, Any]) -> None:
        scores = response.get("confidence_scores")
        value = None
        if isinstance(scores, list) and scores and isinstance(scores[0], (int, float)):
            value = float(scores[0])
        elif isinstance(scores, (int, float)):
            value = float(scores)
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
                    "Boltz-2가 반환한 confidence_scores의 첫 값. "
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
        self._emit(cid, "structure_comparison", "running", None)
        condition_id = f"cond-{cid}-core"
        measurements: list[analysis.Measurement] = []

        if match.complete:
            public = structures.load_catalog()[match.pdb_id]
            source = {
                "title": f"RCSB PDB {public.pdb_id}",
                "url": public.source_url,
                "record_id": public.pdb_id,
            }
            measurements.append(
                analysis.contact_measurement(
                    public.pdb_id, source, structures.file_sha256(public.path)
                )
            )
        else:
            measurements.append(
                analysis.Measurement.not_run(
                    "interface_contact_residues",
                    "예측 구조의 접촉 잔기 계산은 A의 계산 함수(A-02) 인계 후에 한다.",
                )
            )
        measurements.extend(analysis.pending_measurements("예측·실험 구조 공통으로"))

        for m in measurements:
            self._add_evidence(cid, condition_id, structure_id, m)
        self._emit(cid, "structure_comparison", "completed", None)

    # ------------------------------------------------------------ ⑥ 보고
    def _report(self, cid: str, structure_id: str, match: structures.StructureMatch) -> None:
        self._emit(cid, "reporting", "running", None)
        condition_id = f"cond-{cid}-core"
        mine = [e for e in self.evidence if e["candidate_id"] == cid]
        measured = [e for e in mine if e["measurement_state"] == "measured"]
        unmeasured = [e for e in mine if e["measurement_state"] != "measured"]

        decision = "reviewable" if measured else "needs_confirmation"
        if match.complete:
            reason = (
                f"{match.pdb_id}의 실험 구조와 후보 서열이 정확히 일치해 예측 없이 검토했다. "
                f"근거 {len(measured)}건을 계산했고 {len(unmeasured)}건은 아직 계산하지 않았다."
            )
        else:
            reason = (
                f"일치하는 공개 실험 구조가 없어 예측 구조로 검토했다. "
                f"근거 {len(measured)}건을 확보했고 {len(unmeasured)}건은 아직 계산하지 않았다."
            )

        self.opinions.append(
            {
                "opinion_id": f"op-{cid}-core",
                "candidate_id": cid,
                "condition_id": condition_id,
                "topic": "interface_review",
                "decision": decision,
                "evidence_ids": [e["evidence_id"] for e in measured],
                "conflicting_evidence_ids": [],
                "reason": reason,
                "limitations": [e["reason"] for e in unmeasured if e["reason"]],
                "follow_up_questions": self._follow_ups(match),
            }
        )
        self._emit(cid, "reporting", "completed", None)

    def _follow_ups(self, match: structures.StructureMatch) -> list[str]:
        questions = [
            "접촉 잔기 선택 기준(4.5 Å)을 이 비교의 판정 기준으로 쓸 것인지 확정이 필요하다.",
            "충돌·표면 노출 계산의 정의와 제외 규칙을 A-02에서 확정해야 한다.",
        ]
        if match.complete and structures.load_catalog()[match.pdb_id].glycan_descriptions:
            questions.append(
                "구조에 포함된 당쇄를 표면 노출 계산에 넣을지, 넣는다면 원자 반지름을 어떻게 둘지 정해야 한다."
            )
        return questions

    # ------------------------------------------------------------ 보조
    def _add_evidence(
        self,
        cid: str,
        condition_id: str,
        structure_id: str | None,
        m: analysis.Measurement,
    ) -> None:
        evidence = {
            "evidence_id": f"ev-{cid}-{m.topic}",
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
) -> tuple[dict[str, Any], Flow]:
    flow = Flow(request, client=client, progress=progress)
    return flow.run(), flow
