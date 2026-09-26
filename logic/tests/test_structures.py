"""mmCIF 파싱 검증.

공개 구조(1N8Z·1S78)와 NVIDIA Boltz-2가 돌려준 구조는 같은 mmCIF지만 줄
모양이 다르다. 두 모양을 모두 읽는지 확인한다. fixture는 지어낸 파일이
아니라 2026-09-25 실제 Boltz-2 응답에서 발췌한 것이다.
"""

from __future__ import annotations

from pathlib import Path

from logic import structures

FIXTURE = Path(__file__).parent / "fixtures" / "boltz2-response-excerpt.cif"


def test_fixture_has_the_shape_that_broke_the_parser():
    """세미콜론 블록 사이의 빈 줄 — 공개 구조 파일에는 없고 Boltz-2에는 있다."""
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    start = lines.index("_entity_poly.entity_id")
    end = next(i for i in range(start, len(lines)) if lines[i].strip() == "#")
    assert "" in lines[start:end], "fixture가 회귀를 재현하지 못한다"


def test_parses_boltz2_response():
    entities, _ = structures.parse_entities(FIXTURE.read_text(encoding="utf-8"))

    assert len(entities) == 3, "빈 줄에서 멈추면 행이 통째로 사라진다"
    assert [e.strand_ids for e in entities] == [("A",), ("B",), ("C",)]
    assert [len(e.sequence) for e in entities] == [607, 226, 214]


def test_blank_line_does_not_end_a_loop():
    text = "\n".join(
        [
            "loop_",
            "_x.id",
            "_x.seq",
            "1",
            ";AAA",
            ";",
            "",
            "2",
            ";CCC",
            ";",
            "#",
        ]
    )
    rows = structures._read_loop(text, "_x.id")

    assert [r["_x.id"] for r in rows] == ["1", "2"]
    assert [r["_x.seq"] for r in rows] == ["AAA", "CCC"]


def test_loop_still_ends_at_its_real_terminators():
    """빈 줄을 건너뛰게 만들면서 진짜 끝까지 넘어가면 안 된다."""
    text = "\n".join(
        ["loop_", "_x.id", "1", "2", "", "#", "loop_", "_y.id", "9", "#"]
    )
    rows = structures._read_loop(text, "_x.id")

    assert [r["_x.id"] for r in rows] == ["1", "2"]
    assert "9" not in [r["_x.id"] for r in rows]


def test_public_structures_still_parse():
    """공개 구조 경로가 함께 깨지지 않았는지 확인한다."""
    catalog = structures.load_catalog()

    for pdb_id, expected in (("1N8Z", {214, 220, 607}), ("1S78", {214, 226, 624})):
        lengths = {len(e.sequence) for e in catalog[pdb_id].entities}
        assert lengths == expected, f"{pdb_id} 파싱이 달라졌다"
