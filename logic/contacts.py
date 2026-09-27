"""좌표에서 접촉 잔기를 직접 고른다 — 예측 구조용.

공개 실험 구조의 접촉 잔기는 팀이 Biopython으로 미리 계산해
`contacts.json`에 넣어 두었다. 예측 구조는 실행할 때마다 새로 생기므로
미리 계산해 둘 수 없다. 그래서 같은 선택 기준을 여기서 다시 구현한다.

**같은 기준이어야 한다.** 실험 구조 후보와 예측 구조 후보를 한 화면에서
비교하는데 선택 기준이 다르면 그 비교는 의미가 없다. 기준은
`docs/frontend-hosting/assets/3d-research/build-contacts.py`가 쓴 것을 따른다:

- label 기준 사슬·잔기 번호 (`auth_chains=False, auth_residues=False`)
- 수소(H·D) 제외한 중원자만
- 표적 원자와 항체 원자 사이 거리 4.5 Å 이내
- 가까운 쌍의 **양쪽** 잔기를 모두 담는다 (표적 쪽과 항체 쪽 둘 다)

이 구현이 Biopython과 같은 답을 내는지는 공개 구조 두 개에서 직접
대조한다(`logic/tests/test_contacts.py`). 대조가 깨지면 예측 구조 결과도
믿을 수 없다는 뜻이다.

생성 스크립트가 스스로 "Not binding assessment"라고 적은 것도 그대로
이어받는다. 접촉 위치 근거일 뿐 결합력·효능 판정이 아니다.
"""

from __future__ import annotations

import difflib
import math
from collections import defaultdict
from dataclasses import dataclass

CUTOFF_ANGSTROM = 4.5

# 수소는 결정 구조에 대개 없고 예측 구조에는 있을 수 있다. 한쪽에만 있는
# 원자를 거리 계산에 넣으면 두 경로의 결과가 달라진다.
_EXCLUDED_ELEMENTS = frozenset({"H", "D"})


@dataclass(frozen=True)
class Atom:
    label_asym_id: str
    label_seq_id: int
    x: float
    y: float
    z: float


def sequence_position_map(seq_from: str, seq_to: str) -> dict[int, int]:
    """두 표적 서열을 맞춰 1-기반 잔기 번호 대응을 만든다.

    구조마다 표적 construct가 달라 같은 자리가 다른 번호를 갖는다. 서로 다른
    구조의 에피토프를 견주려면 먼저 한 번호 체계로 옮겨야 한다.
    """
    matcher = difflib.SequenceMatcher(None, seq_from, seq_to, autojunk=False)
    return {a + k + 1: b + k + 1
            for a, b, size in matcher.get_matching_blocks() for k in range(size)}


def parse_atoms(text: str, *, model_number: int = 1) -> list[Atom]:
    """mmCIF의 줄바꿈·따옴표를 보존해 label 기준 중원자 좌표를 읽는다."""
    import gemmi

    # ponytail: 설치된 CIF 파서가 행 경계와 토큰을 처리한다. 직접 split하지 않는다.
    try:
        block = gemmi.cif.read_string(text).sole_block()
    except (ValueError, RuntimeError):
        return []
    names = ("label_asym_id", "label_seq_id", "type_symbol", "Cartn_x", "Cartn_y", "Cartn_z")
    columns = [block.find_values("_atom_site." + name) for name in names]
    if not all(len(c) for c in columns):
        return []
    models = block.find_values("_atom_site.pdbx_PDB_model_num")
    atoms = []
    for i, (chain, seq, element, x, y, z) in enumerate(zip(*columns)):
        if models and gemmi.cif.as_string(models[i]) != str(model_number):
            continue
        if element.upper() in _EXCLUDED_ELEMENTS:
            continue
        try:
            atom = Atom(gemmi.cif.as_string(chain), int(seq), float(x), float(y), float(z))
        except ValueError:
            continue
        if all(math.isfinite(v) for v in (atom.x, atom.y, atom.z)):
            atoms.append(atom)
    return atoms


def contact_residues(
    atoms: list[Atom],
    target_chains: set[str],
    antibody_chains: set[str],
    *,
    cutoff: float = CUTOFF_ANGSTROM,
) -> list[tuple[str, int]]:
    """표적과 항체가 `cutoff` 이내로 만나는 잔기를 양쪽 다 모은다.

    격자로 나눠 이웃 칸만 본다. 전수 비교는 원자 수의 제곱이라
    1,000잔기 복합체에서 쓸 수 없다.
    """
    target = [a for a in atoms if a.label_asym_id in target_chains]
    antibody = [a for a in atoms if a.label_asym_id in antibody_chains]
    if not target or not antibody:
        return []

    grid: dict[tuple[int, int, int], list[Atom]] = defaultdict(list)
    for atom in antibody:
        grid[_cell(atom, cutoff)].append(atom)

    limit = cutoff * cutoff
    found: set[tuple[str, int]] = set()
    for atom in target:
        cx, cy, cz = _cell(atom, cutoff)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for other in grid.get((cx + dx, cy + dy, cz + dz), ()):
                        dist = (
                            (atom.x - other.x) ** 2
                            + (atom.y - other.y) ** 2
                            + (atom.z - other.z) ** 2
                        )
                        if dist <= limit:
                            found.add((atom.label_asym_id, atom.label_seq_id))
                            found.add((other.label_asym_id, other.label_seq_id))
    return sorted(found)


def _cell(atom: Atom, size: float) -> tuple[int, int, int]:
    return (
        math.floor(atom.x / size),
        math.floor(atom.y / size),
        math.floor(atom.z / size),
    )
