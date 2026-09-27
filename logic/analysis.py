"""구조 계산 결과를 Evidence 재료로 바꾸는 층 (D2 소비부).

계산 함수 자체는 로직 A의 담당이다. 이 모듈은 A가 만든 결과를 B의 흐름에
연결하는 자리이며, 아직 없는 계산은 `not_run`으로 남긴다. 여기서 임계값을
정하거나 없는 값을 채우지 않는다.

공개·예측 구조의 표면 계산은 surface_analysis.py가 같은 좌표 기준으로 수행한다.
이 모듈은 좌표의 접촉과 기준 계면 비교를 담당한다.
계산값은 구조 근거이며 결합력·효능 판정이 아니다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import contacts, structures
from .contract import REPO_ROOT

CONTACTS_PATH = REPO_ROOT / "frontend" / "public" / "structures" / "contacts.json"

# contacts.json은 auth_chains=False로 만들어졌다. 따라서 label 번호다.
CONTACT_NUMBERING = "label"

# 실험 구조와 예측 구조가 같은 문장을 쓴다. 화면에서 둘을 나란히 놓고
# 비교하므로, 기준 설명이 다르면 같은 기준이라는 것을 알 수 없다.
# 예측 구조에서 계산한 접촉에만 붙인다. 실험 좌표에는 해당하지 않는다.
_PREDICTED_CONTACT_LIMIT = (
    " 이 값은 예측 구조에서 계산한 것이다. 개발에 쓰지 않은 항체 2건(8JYR·3N85)에서는 "
    "예측 접촉과 실험 접촉의 겹침이 0이었다. 에피토프 근거로 확정해 쓰지 말고 사람이 확인한다."
)
_CONTACT_DEFINITION = (
    "표적·항체 중원자 간 거리 {cutoff} Å 이내로 선택한 잔기 수. "
    f"잔기 번호는 {CONTACT_NUMBERING} 기준이며 결합력·효능 판정이 아니다."
)


@dataclass
class Measurement:
    """Evidence 한 건이 될 계산 결과.

    measured가 아니면 value는 None이고 reason이 반드시 있어야 한다.
    이 규칙은 service.schema.json의 Evidence가 강제한다.
    """

    topic: str
    kind: str  # experimental | computed | unknown
    state: str  # measured | unknown | not_applicable | not_run | failed
    value: float | None = None
    unit: str | None = None
    definition: str | None = None
    reason: str | None = None
    residues: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def not_run(cls, topic: str, reason: str, *, kind: str = "computed") -> "Measurement":
        return cls(topic=topic, kind=kind, state="not_run", reason=reason)


def residue(
    *,
    label_asym_id: str | None,
    label_seq_id: int | None,
    model_number: int = 1,
    auth_asym_id: str | None = None,
    auth_seq_id: int | None = None,
    has_coordinates: bool = True,
) -> dict[str, Any]:
    """계약의 Residue 한 건. 확인하지 않은 번호 체계는 null로 둔다."""
    return {
        "model_number": model_number,
        "label_asym_id": label_asym_id,
        "auth_asym_id": auth_asym_id,
        "label_seq_id": label_seq_id,
        "auth_seq_id": auth_seq_id,
        "insertion_code": None,
        "sequence_position": None,
        "operator_id": None,
        "has_coordinates": has_coordinates,
    }


@lru_cache(maxsize=1)
def _contacts() -> dict[str, Any]:
    if not CONTACTS_PATH.exists():
        return {}
    return json.loads(CONTACTS_PATH.read_text(encoding="utf-8"))


def contact_measurement(pdb_id: str, source: dict[str, Any], expected_sha256: str) -> Measurement:
    """공개 실험 구조의 접촉 잔기. 팀이 미리 계산한 결과를 근거와 함께 옮긴다."""
    entry = _contacts().get(pdb_id)
    if entry is None:
        return Measurement.not_run(
            "interface_contact_residues",
            f"{pdb_id}의 접촉 잔기 계산 결과가 contacts.json에 없다.",
        )
    if expected_sha256 and entry.get("sha256") != expected_sha256:
        return Measurement(
            topic="interface_contact_residues",
            kind="computed",
            state="failed",
            reason=(
                f"{pdb_id}의 접촉 잔기는 다른 구조 파일에서 계산됐다. "
                f"기록된 sha256={entry.get('sha256')}, 현재 구조={expected_sha256}."
            ),
        )
    cutoff = entry["cutoff_angstrom"]
    residues = [
        residue(label_asym_id=r["chain"], label_seq_id=r["seq"]) for r in entry["residues"]
    ]
    return Measurement(
        topic="interface_contact_residues",
        kind="computed",
        state="measured",
        value=float(len(residues)),
        unit="residue",
        definition=_CONTACT_DEFINITION.format(cutoff=cutoff),
        residues=residues,
        sources=[source],
    )


def predicted_contact_measurement(
    path: Path, chain_mapping: list[dict[str, Any]], source: dict[str, Any], *, predicted: bool = True,
    residue_ranges: dict[str, tuple[int, int]] | None = None,
) -> Measurement:
    """예측 구조의 접촉 잔기. 좌표에서 직접 고른다.

    실험 구조 쪽(`contact_measurement`)과 **같은 기준**을 쓴다. 그 동일성은
    `logic/tests/test_contacts.py`가 공개 구조 두 개로 대조해 지킨다.

    사슬 대응을 못 찾았으면 계산하지 않는다. 어느 사슬이 표적인지 모르는
    채로 거리를 재면 아무 의미 없는 수가 나온다.
    """
    roles = {c["role"]: c.get("label_asym_id") for c in chain_mapping}
    target = roles.get("target")
    antibody = {roles.get("heavy"), roles.get("light")} - {None}
    if not target or len(antibody) != 2:
        return Measurement.not_run(
            "interface_contact_residues",
            "예측 응답에서 표적·중쇄·경쇄 사슬을 모두 대응시키지 못해 접촉 잔기를 계산하지 않았다.",
        )
    try:
        atoms = contacts.parse_atoms(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return Measurement(
            topic="interface_contact_residues",
            kind="computed",
            state="failed",
            reason=f"예측 구조 파일을 읽지 못했다: {exc}",
        )
    if residue_ranges:
        atoms = [atom for atom in atoms if atom.label_asym_id in residue_ranges and
                 residue_ranges[atom.label_asym_id][0] <= atom.label_seq_id <= residue_ranges[atom.label_asym_id][1]]
    if not atoms:
        return Measurement.not_run(
            "interface_contact_residues",
            "예측 구조 파일에서 원자 좌표를 읽지 못했다.",
        )
    if not ({target} | antibody).issubset({atom.label_asym_id for atom in atoms}):
        return Measurement.not_run(
            "interface_contact_residues",
            "예측 구조에 표적·중쇄·경쇄 중 일부 사슬의 원자 좌표가 없어 접촉 잔기를 계산하지 않았다.",
        )
    found = contacts.contact_residues(atoms, {target}, antibody)
    if not found:
        # 0건은 "계산했는데 접촉이 없다"이다. 미실행과 구분해서 내보낸다.
        return Measurement(
            topic="interface_contact_residues",
            kind="computed",
            state="measured",
            value=0.0,
            unit="residue",
            definition=_CONTACT_DEFINITION.format(cutoff=contacts.CUTOFF_ANGSTROM) + (_PREDICTED_CONTACT_LIMIT if predicted else ""),
            sources=[source],
        )
    return Measurement(
        topic="interface_contact_residues",
        kind="computed",
        state="measured",
        value=float(len(found)),
        unit="residue",
        definition=_CONTACT_DEFINITION.format(cutoff=contacts.CUTOFF_ANGSTROM) + (_PREDICTED_CONTACT_LIMIT if predicted else ""),
        residues=[residue(label_asym_id=c, label_seq_id=s) for c, s in found],
        sources=[source],
    )


# 예측 에피토프를 견주는 기준 복합체. 이 항체-표적 계면은 공개 실험 구조로 확정돼 있다.
REFERENCE_COMPLEX = "1N8Z"
_REFERENCE_TARGET_CHAIN = "C"
_OVERLAP_TOPIC = "predicted_epitope_overlap_with_reference"


@lru_cache(maxsize=1)
def _reference_epitope() -> tuple[frozenset[int], str]:
    """기준 복합체의 표적 쪽 접촉 잔기와 그 표적 서열."""
    entry = _contacts().get(REFERENCE_COMPLEX) or {}
    positions = frozenset(r["seq"] for r in entry.get("residues", [])
                          if r["chain"] == _REFERENCE_TARGET_CHAIN)
    path = structures.STRUCTURE_DIR / f"{REFERENCE_COMPLEX}.cif"
    try:
        entities, _ = structures.parse_entities(path.read_text(encoding="utf-8"))
    except OSError:
        return positions, ""
    sequence = next((e.sequence for e in entities
                     if _REFERENCE_TARGET_CHAIN in e.strand_ids), "")
    return positions, structures.normalize_sequence(sequence or "")


def reference_epitope_overlap_measurement(
    path: Path, chain_mapping: list[dict[str, Any]], target_sequence: str, source: dict[str, Any]
) -> Measurement:
    """예측 에피토프가 기준 복합체의 계면과 같은 자리인지 잰다.

    왜 재는가: 개발에 쓰지 않은 항체 2건(8JYR·3N85)에서 예측 접촉과 실험 접촉의
    겹침이 0이었다. 그런데 3N85는 예측 접촉 22개 중 12개가, 퍼투주맙(1S78)은
    23개 중 10개가 1N8Z 실험 에피토프와 같은 자리였다. 새 항체를 이미 본
    트라스투주맙 자리에 붙인 것이다. 그 비율을 근거로 남겨 사람이 보게 한다.

    이 값은 예측이 틀렸다는 판정이 아니다. 실제로 그 자리에 붙는 항체도 있다.
    후보가 트라스투주맙과 다른데 비율이 높으면 의심하라는 뜻이다.
    """
    roles = {c["role"]: c.get("label_asym_id") for c in chain_mapping}
    target = roles.get("target")
    antibody = {roles.get("heavy"), roles.get("light")} - {None}
    if not target or len(antibody) != 2:
        return Measurement.not_run(
            _OVERLAP_TOPIC,
            "예측 응답에서 표적·중쇄·경쇄 사슬을 모두 대응시키지 못해 기준 계면과 견주지 않았다.",
        )
    sequence = structures.normalize_sequence(target_sequence or "")
    if not sequence:
        return Measurement.not_run(
            _OVERLAP_TOPIC, "표적 서열이 없어 예측 좌표를 기준 구조의 잔기 번호로 옮길 수 없다.")
    reference, reference_sequence = _reference_epitope()
    if not reference or not reference_sequence:
        return Measurement.not_run(
            _OVERLAP_TOPIC,
            f"{REFERENCE_COMPLEX}의 실험 접촉 잔기나 표적 서열을 찾지 못해 견주지 않았다.")
    try:
        atoms = contacts.parse_atoms(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return Measurement(topic=_OVERLAP_TOPIC, kind="computed", state="failed",
                           reason=f"예측 구조 파일을 읽지 못했다: {exc}")
    own = sorted(n for c, n in contacts.contact_residues(atoms, {target}, antibody) if c == target)
    if not own:
        return Measurement.not_run(
            _OVERLAP_TOPIC, "예측 구조에서 표적 쪽 접촉 잔기를 찾지 못해 견줄 대상이 없다.")
    to_reference = contacts.sequence_position_map(sequence, reference_sequence)
    # 표적 construct가 기준 에피토프를 담고 있지 않으면 0이 아니라 잴 대상이 없는 것이다.
    # 실측: 8JYR은 도메인 I 202잔기만 제출해 기준 잔기 19개 중 0개가 대응된다. 그 입력에서
    # 0.000을 내보내면 "다른 자리에 붙었다"로 읽힌다. 3N85는 624잔기라 19개가 모두 대응된다.
    covered = sorted(reference & set(to_reference.values()))
    if not covered:
        return Measurement.not_run(
            _OVERLAP_TOPIC,
            f"제출된 표적 서열({len(sequence)}잔기)에 {REFERENCE_COMPLEX} 계면 잔기가 "
            f"하나도 대응되지 않아 견줄 수 없다. 겹침이 0인 것이 아니라 잴 대상이 없다.",
        )
    hits = [n for n in own if to_reference.get(n) in reference]
    return Measurement(
        topic=_OVERLAP_TOPIC,
        kind="computed",
        state="measured",
        value=round(len(hits) / len(own), 3),
        unit="fraction",
        definition=(
            f"예측 구조의 표적 쪽 접촉 잔기 {len(own)}개 중 {len(hits)}개가 "
            f"{REFERENCE_COMPLEX}(트라스투주맙-HER2) 실험 계면과 같은 자리다. "
            f"제출된 표적에 대응되는 기준 계면 잔기는 {len(covered)}/{len(reference)}개다. "
            "서열 정렬로 번호를 맞춰 셌다. 후보가 트라스투주맙과 다른데 이 비율이 높으면 "
            "학습에서 본 계면을 재현한 예측일 수 있다. 결합력·효능 지표가 아니다."
        ),
        residues=[residue(label_asym_id=target, label_seq_id=n) for n in hits],
        sources=[source],
    )


def pending_measurements(reason_prefix: str) -> list[Measurement]:
    """아직 A가 인계하지 않은 계산들. 값을 만들지 않고 미실행으로 남긴다."""
    return [
        Measurement.not_run(
            "atom_clash",
            f"{reason_prefix} 충돌 판정 기준(A-02의 거리·제외 규칙)이 합의 전이라 계산하지 않았다.",
        ),
        Measurement.not_run(
            "surface_exposure",
            f"{reason_prefix} 표면 노출 계산은 FreeSASA 설치와 당쇄 포함 여부 검증(A-03) 이후에 한다.",
        ),
    ]
