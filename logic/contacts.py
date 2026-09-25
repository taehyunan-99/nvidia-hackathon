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


def parse_atoms(text: str, *, model_number: int = 1) -> list[Atom]:
    """mmCIF `_atom_site` loop에서 중원자 좌표를 읽는다.

    `structures._read_loop`을 쓰지 않는다. 원자 행은 수만 줄이고 따옴표·
    세미콜론 블록이 없는 고정 모양이라, 줄 단위로 바로 쪼개는 쪽이 빠르다.

    `label_seq_id`가 숫자가 아닌 행(물·당쇄 같은 비중합체)은 버린다. 잔기
    번호가 없으면 접촉 잔기로 지목할 수 없다.
    """
    lines = text.splitlines()
    columns: list[str] = []
    index = 0
    # _atom_site loop의 열 이름을 모은다.
    for i, line in enumerate(lines):
        if line.strip().startswith("_atom_site."):
            j = i
            while j < len(lines) and lines[j].strip().startswith("_atom_site."):
                columns.append(lines[j].strip())
                j += 1
            index = j
            break
    if not columns:
        return []

    try:
        col = {
            "asym": columns.index("_atom_site.label_asym_id"),
            "seq": columns.index("_atom_site.label_seq_id"),
            "element": columns.index("_atom_site.type_symbol"),
            "x": columns.index("_atom_site.Cartn_x"),
            "y": columns.index("_atom_site.Cartn_y"),
            "z": columns.index("_atom_site.Cartn_z"),
        }
    except ValueError:
        # 필요한 열이 없으면 지어내지 않고 빈 결과를 낸다.
        return []
    model_col = (
        columns.index("_atom_site.pdbx_PDB_model_num")
        if "_atom_site.pdbx_PDB_model_num" in columns
        else None
    )
    width = len(columns)

    atoms: list[Atom] = []
    for line in lines[index:]:
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("loop_"):
            break
        if not stripped:
            continue
        if not (stripped.startswith("ATOM") or stripped.startswith("HETATM")):
            break
        parts = stripped.split()
        if len(parts) != width:
            continue
        if model_col is not None and parts[model_col] != str(model_number):
            continue
        if parts[col["element"]].upper() in _EXCLUDED_ELEMENTS:
            continue
        try:
            seq = int(parts[col["seq"]])
            x = float(parts[col["x"]])
            y = float(parts[col["y"]])
            z = float(parts[col["z"]])
        except ValueError:
            continue
        atoms.append(Atom(parts[col["asym"]], seq, x, y, z))
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
