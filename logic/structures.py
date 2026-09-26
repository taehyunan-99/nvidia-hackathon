"""공개 실험 구조 조회와 후보-구조 대응.

흐름 ②의 "공개 자료 조회"와 그 다음 분기 판정을 담당한다.
판정은 서열 일치 여부로만 하며, 이름이 비슷하다는 이유로 대응시키지 않는다.

여기서 읽는 mmCIF는 팀이 이미 확보·검증한 파일이다.
출처와 sha256은 docs/frontend-hosting/assets/3d-research/verified-structures.json에 있다.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .contract import REPO_ROOT

STRUCTURE_DIR = REPO_ROOT / "frontend" / "public" / "structures"
VERIFIED_PATH = (
    REPO_ROOT / "docs" / "frontend-hosting" / "assets" / "3d-research" / "verified-structures.json"
)

# 사슬 역할 판정에 쓰는 표기. RCSB의 entity 설명 문자열에 근거한다.
_HEAVY = re.compile(r"heavy chain", re.I)
_LIGHT = re.compile(r"light chain", re.I)
_TARGET = re.compile(r"erbB-2|HER2", re.I)


@dataclass(frozen=True)
class PolymerEntity:
    entity_id: str
    description: str
    sequence: str
    strand_ids: tuple[str, ...]

    @property
    def role(self) -> str:
        """heavy / light / target / other. 설명 문자열에 근거한 분류다."""
        if _HEAVY.search(self.description):
            return "heavy"
        if _LIGHT.search(self.description):
            return "light"
        if _TARGET.search(self.description):
            return "target"
        return "other"


@dataclass(frozen=True)
class PublicStructure:
    pdb_id: str
    path: Path
    source_url: str
    verified_sha256: str
    entities: tuple[PolymerEntity, ...]
    glycan_descriptions: tuple[str, ...] = field(default=())

    def by_role(self, role: str) -> list[PolymerEntity]:
        return [e for e in self.entities if e.role == role]


def sequence_body(fasta_or_seq: str) -> str:
    """FASTA 헤더와 공백만 제거한 본문. 잘못된 문자를 그대로 남긴다.

    입력 검사는 이 함수를 쓴다. normalize_sequence를 먼저 쓰면 숫자·기호가
    조용히 사라져 잘못된 입력이 통과한다.
    """
    body = "\n".join(
        line for line in fasta_or_seq.splitlines() if not line.lstrip().startswith(">")
    )
    return re.sub(r"\s+", "", body).upper()


def normalize_sequence(fasta_or_seq: str) -> str:
    """FASTA 헤더와 공백을 제거한 대문자 1문자 서열. 비교·대조용이다."""
    return re.sub(r"[^A-Z]", "", sequence_body(fasta_or_seq))


# ---------------------------------------------------------------- mmCIF 최소 파서
def _tokenize_loop_values(lines: list[str], start: int) -> tuple[list[str], int]:
    """loop_ 본문의 값 토큰을 순서대로 읽는다. 세미콜론 블록과 따옴표를 처리한다."""
    values: list[str] = []
    i = start
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if stripped == "#" or stripped.startswith(("loop_", "_", "data_")):
            break
        if stripped == "":
            # 빈 줄은 loop의 끝이 아니다. Boltz-2가 돌려주는 mmCIF는 세미콜론
            # 블록 사이에 빈 줄을 넣는다. 여기서 멈추면 행이 통째로 사라진다.
            i += 1
            continue
        if raw.startswith(";"):
            block = [raw[1:]]
            i += 1
            while i < len(lines) and not lines[i].startswith(";"):
                block.append(lines[i])
                i += 1
            i += 1  # 닫는 세미콜론
            values.append("\n".join(block))
            continue
        values.extend(_split_cif_line(stripped))
        i += 1
    return values, i


def _split_cif_line(line: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r"'([^']*)'|\"([^\"]*)\"|(\S+)", line):
        out.append(next(g for g in m.groups() if g is not None))
    return out


def _read_loop(text: str, prefix: str) -> list[dict[str, str]]:
    """`prefix`로 시작하는 loop_ 블록을 열 이름 → 값 사전 목록으로 읽는다."""
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if not line.strip().startswith(prefix):
            continue
        # 열 이름 수집 — 이 블록이 시작되는 loop_까지 거슬러 올라간다.
        head = idx
        while head > 0 and lines[head - 1].strip().startswith("_"):
            head -= 1
        if head == 0 or lines[head - 1].strip() != "loop_":
            return []
        columns: list[str] = []
        j = head
        while j < len(lines) and lines[j].strip().startswith("_"):
            columns.append(lines[j].strip())
            j += 1
        values, _ = _tokenize_loop_values(lines, j)
        if not columns or len(values) % len(columns) != 0:
            return []
        rows = []
        for r in range(0, len(values), len(columns)):
            rows.append(dict(zip(columns, values[r : r + len(columns)])))
        return rows
    return []


def parse_entities(text: str) -> tuple[tuple[PolymerEntity, ...], tuple[str, ...]]:
    descriptions = {
        row["_entity.id"]: row.get("_entity.pdbx_description", "")
        for row in _read_loop(text, "_entity.id")
    }
    entities = []
    for row in _read_loop(text, "_entity_poly.entity_id"):
        eid = row["_entity_poly.entity_id"]
        seq = normalize_sequence(row.get("_entity_poly.pdbx_seq_one_letter_code_can", ""))
        strands = tuple(
            s for s in row.get("_entity_poly.pdbx_strand_id", "").split(",") if s and s != "?"
        )
        entities.append(PolymerEntity(eid, descriptions.get(eid, ""), seq, strands))
    poly_ids = {e.entity_id for e in entities}
    glycans = tuple(
        desc
        for eid, desc in descriptions.items()
        if eid not in poly_ids and "glucopyranose" in desc.lower()
    )
    return tuple(entities), glycans


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, PublicStructure]:
    """확보·검증된 공개 구조만 담은 조회 대상."""
    if not VERIFIED_PATH.exists():
        return {}
    verified = json.loads(VERIFIED_PATH.read_text(encoding="utf-8"))
    catalog: dict[str, PublicStructure] = {}
    for pdb_id, meta in verified.items():
        path = STRUCTURE_DIR / f"{pdb_id}.cif"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        entities, glycans = parse_entities(text)
        catalog[pdb_id] = PublicStructure(
            pdb_id=pdb_id,
            path=path,
            source_url=meta.get("source", ""),
            verified_sha256=meta.get("sha256", ""),
            entities=entities,
            glycan_descriptions=glycans,
        )
    return catalog


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- 후보 대응
@dataclass(frozen=True)
class StructureMatch:
    """후보 하나에 대한 공개 구조 조회 결과."""

    pdb_id: str | None
    heavy_entity: PolymerEntity | None
    light_entity: PolymerEntity | None
    target_entity: PolymerEntity | None
    heavy_exact: bool
    light_exact: bool

    @property
    def complete(self) -> bool:
        """중쇄·경쇄 모두 서열이 정확히 일치하고 표적 사슬도 같은 구조에 있다."""
        return self.heavy_exact and self.light_exact and self.target_entity is not None


def find_structure(heavy_fasta: str, light_fasta: str) -> StructureMatch:
    """후보 서열과 정확히 일치하는 공개 복합체 구조를 찾는다.

    부분 일치(중쇄만 맞는 등)는 일치로 처리하지 않는다. 판단은 호출부가 한다.
    """
    heavy = normalize_sequence(heavy_fasta)
    light = normalize_sequence(light_fasta)
    best = StructureMatch(None, None, None, None, False, False)
    for structure in load_catalog().values():
        h = next((e for e in structure.by_role("heavy") if e.sequence == heavy), None)
        l = next((e for e in structure.by_role("light") if e.sequence == light), None)
        if not h and not l:
            continue
        target = next(iter(structure.by_role("target")), None)
        match = StructureMatch(structure.pdb_id, h, l, target, h is not None, l is not None)
        if match.complete:
            return match
        # 더 많이 맞는 부분 일치를 남겨 둔다.
        if (match.heavy_exact + match.light_exact) > (best.heavy_exact + best.light_exact):
            best = match
    return best
