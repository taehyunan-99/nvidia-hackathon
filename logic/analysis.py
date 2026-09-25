"""구조 계산 결과를 Evidence 재료로 바꾸는 층 (D2 소비부).

계산 함수 자체는 로직 A의 담당이다. 이 모듈은 A가 만든 결과를 B의 흐름에
연결하는 자리이며, 아직 없는 계산은 `not_run`으로 남긴다. 여기서 임계값을
정하거나 없는 값을 채우지 않는다.

지금 실제로 사용할 수 있는 것은 팀이 미리 계산해 둔 접촉 잔기 선택뿐이다
(frontend/public/structures/contacts.json). 그 파일의 생성 스크립트는 스스로를
"proximity selections ... Not binding assessment"로 적고 있으므로, 결합력·효능이
아니라 접촉 위치 근거로만 쓴다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import contacts
from .contract import REPO_ROOT

CONTACTS_PATH = REPO_ROOT / "frontend" / "public" / "structures" / "contacts.json"

# contacts.json은 auth_chains=False로 만들어졌다. 따라서 label 번호다.
CONTACT_NUMBERING = "label"

# 실험 구조와 예측 구조가 같은 문장을 쓴다. 화면에서 둘을 나란히 놓고
# 비교하므로, 기준 설명이 다르면 같은 기준이라는 것을 알 수 없다.
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
    path: Path, chain_mapping: list[dict[str, Any]], source: dict[str, Any]
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
    if not atoms:
        return Measurement.not_run(
            "interface_contact_residues",
            "예측 구조 파일에서 원자 좌표를 읽지 못했다.",
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
            definition=_CONTACT_DEFINITION.format(cutoff=contacts.CUTOFF_ANGSTROM),
            sources=[source],
        )
    return Measurement(
        topic="interface_contact_residues",
        kind="computed",
        state="measured",
        value=float(len(found)),
        unit="residue",
        definition=_CONTACT_DEFINITION.format(cutoff=contacts.CUTOFF_ANGSTROM),
        residues=[residue(label_asym_id=c, label_seq_id=s) for c, s in found],
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
