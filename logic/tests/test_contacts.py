"""접촉 잔기 계산 검증.

핵심은 하나다 — 예측 구조에 쓰는 이 구현이 실험 구조에 쓴 Biopython 계산과
**같은 답**을 내는가. 두 경로의 답이 다르면 한 화면에서 후보를 비교할 수 없다.
그래서 공개 구조 두 개에서 개수가 아니라 잔기 집합 전체를 대조한다.
"""

from __future__ import annotations

import json

import pytest

from logic import analysis, contacts, structures

# build-contacts.py가 쓴 것과 같은 사슬 구분. 첫째가 표적이다.
CHAINS = {"1N8Z": ({"C"}, {"A", "B"}), "1S78": ({"A"}, {"C", "D"})}


def _known() -> dict:
    return json.loads(analysis.CONTACTS_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("pdb_id", sorted(CHAINS))
def test_matches_the_biopython_selection_exactly(pdb_id):
    """개수만 맞는 것으로는 부족하다. 어느 잔기인지까지 같아야 한다."""
    target, antibody = CHAINS[pdb_id]
    path = structures.STRUCTURE_DIR / f"{pdb_id}.cif"
    atoms = contacts.parse_atoms(path.read_text(encoding="utf-8"))

    got = contacts.contact_residues(atoms, target, antibody)
    want = sorted((r["chain"], r["seq"]) for r in _known()[pdb_id]["residues"])

    assert got == want


def test_the_cutoff_is_the_one_the_public_file_used():
    """기준 거리가 어긋나면 위 대조가 통과해도 의미가 없다."""
    for entry in _known().values():
        assert entry["cutoff_angstrom"] == contacts.CUTOFF_ANGSTROM


def test_multiline_atom_rows_preserve_the_experimental_contacts():
    """실제 PDB의 원자 행을 여러 줄로 나눠도 원자·접촉 집합이 같아야 한다."""
    text = (structures.STRUCTURE_DIR / "1N8Z.cif").read_text()
    wrapped = "\n".join(line.replace(" ", "\n") if line.startswith(("ATOM ", "HETATM "))
                        else line for line in text.splitlines())
    original = contacts.parse_atoms(text)
    reparsed = contacts.parse_atoms(wrapped)
    assert original and reparsed == original
    assert contacts.contact_residues(reparsed, {"C"}, {"A", "B"}) == sorted(
        (r["chain"], r["seq"]) for r in _known()["1N8Z"]["residues"])


def test_both_sides_of_the_interface_are_collected():
    """표적 쪽 잔기만 모으면 항체의 어느 자리가 닿는지 알 수 없다."""
    target, antibody = CHAINS["1N8Z"]
    atoms = contacts.parse_atoms(
        (structures.STRUCTURE_DIR / "1N8Z.cif").read_text(encoding="utf-8")
    )

    chains = {c for c, _ in contacts.contact_residues(atoms, target, antibody)}

    assert chains & target
    assert chains & antibody


def test_hydrogen_is_excluded():
    """결정 구조에는 수소가 없다. 예측 구조에만 있으면 두 경로가 어긋난다."""
    text = """data_x
loop_
_atom_site.group_PDB
_atom_site.type_symbol
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
ATOM C A 1 0.000 0.000 0.000
ATOM H A 1 1.000 0.000 0.000
ATOM D A 1 2.000 0.000 0.000
#
"""
    atoms = contacts.parse_atoms(text)

    assert len(atoms) == 1


def test_non_polymer_rows_are_dropped():
    """물·당쇄는 label_seq_id가 없다. 잔기로 지목할 수 없으므로 버린다."""
    text = """data_x
loop_
_atom_site.group_PDB
_atom_site.type_symbol
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
ATOM C A 1 0.000 0.000 0.000
HETATM O W . 1.000 0.000 0.000
#
"""
    atoms = contacts.parse_atoms(text)

    assert [(a.label_asym_id, a.label_seq_id) for a in atoms] == [("A", 1)]


def test_only_the_requested_model_is_read():
    """예측 응답이 모델을 여러 개 주면 섞어서 재면 안 된다."""
    text = """data_x
loop_
_atom_site.group_PDB
_atom_site.type_symbol
_atom_site.label_asym_id
_atom_site.label_seq_id
_atom_site.Cartn_x
_atom_site.Cartn_y
_atom_site.Cartn_z
_atom_site.pdbx_PDB_model_num
ATOM C A 1 0.000 0.000 0.000 1
ATOM C A 2 1.000 0.000 0.000 2
#
"""
    assert [a.label_seq_id for a in contacts.parse_atoms(text)] == [1]
    assert [a.label_seq_id for a in contacts.parse_atoms(text, model_number=2)] == [2]


def test_distance_boundary_is_inclusive_and_bounded():
    """4.5 Å 안은 잡고 밖은 놓는지. 격자 경계를 넘는 쌍도 포함해서 본다."""
    inside = contacts.contact_residues(
        [
            contacts.Atom("A", 1, 0.0, 0.0, 0.0),
            contacts.Atom("B", 1, 4.4, 0.0, 0.0),
        ],
        {"A"},
        {"B"},
    )
    outside = contacts.contact_residues(
        [
            contacts.Atom("A", 1, 0.0, 0.0, 0.0),
            contacts.Atom("B", 1, 4.6, 0.0, 0.0),
        ],
        {"A"},
        {"B"},
    )

    assert inside == [("A", 1), ("B", 1)]
    assert outside == []


# ------------------------------------------------------- Measurement 쪽 경계
def test_unmapped_chain_is_not_measured(tmp_path):
    """사슬 대응을 모르면 계산하지 않는다. 아무 사슬이나 재면 무의미한 수가 나온다."""
    mapping = [
        {"role": "target", "label_asym_id": None},
        {"role": "heavy", "label_asym_id": "B"},
        {"role": "light", "label_asym_id": "C"},
    ]

    m = analysis.predicted_contact_measurement(tmp_path / "none.cif", mapping, {})

    assert m.state == "not_run"
    assert m.value is None
    assert m.reason


def test_zero_contacts_is_measured_not_unrun(tmp_path):
    """0건은 '재어 보니 없다'이다. 미실행과 같은 칸에 넣으면 화면이 거짓말한다."""
    path = tmp_path / "far.cif"
    path.write_text(
        "data_x\nloop_\n"
        "_atom_site.group_PDB\n_atom_site.type_symbol\n_atom_site.label_asym_id\n"
        "_atom_site.label_seq_id\n_atom_site.Cartn_x\n_atom_site.Cartn_y\n_atom_site.Cartn_z\n"
        "ATOM C A 1 0.000 0.000 0.000\n"
        "ATOM C B 1 99.000 0.000 0.000\n"
        "ATOM C C 1 99.000 9.000 0.000\n#\n",
        encoding="utf-8",
    )
    mapping = [
        {"role": "target", "label_asym_id": "A"},
        {"role": "heavy", "label_asym_id": "B"},
        {"role": "light", "label_asym_id": "C"},
    ]

    m = analysis.predicted_contact_measurement(path, mapping, {})

    assert m.state == "measured"
    assert m.value == 0.0
    assert m.residues == []


def test_missing_antibody_coordinates_are_not_zero_contacts(tmp_path):
    path = tmp_path / "target-only.cif"
    path.write_text(
        "data_x\nloop_\n_atom_site.type_symbol\n_atom_site.label_asym_id\n"
        "_atom_site.label_seq_id\n_atom_site.Cartn_x\n_atom_site.Cartn_y\n_atom_site.Cartn_z\n"
        "C A 1 0 0 0\n#\n", encoding="utf-8",
    )
    mapping = [{"role": role, "label_asym_id": chain}
               for role, chain in (("target", "A"), ("heavy", "B"), ("light", "C"))]
    result = analysis.predicted_contact_measurement(path, mapping, {})
    assert result.state == "not_run"
    assert result.value is None
    assert result.reason


def test_missing_file_fails_without_inventing_a_number(tmp_path):
    mapping = [
        {"role": "target", "label_asym_id": "A"},
        {"role": "heavy", "label_asym_id": "B"},
        {"role": "light", "label_asym_id": "C"},
    ]

    m = analysis.predicted_contact_measurement(tmp_path / "missing.cif", mapping, {})

    assert m.state == "failed"
    assert m.value is None


def test_predicted_and_experimental_state_the_same_criterion():
    """두 경로의 기준 설명이 갈라지면 비교가 같은 기준이라는 근거가 사라진다."""
    experimental = analysis.contact_measurement(
        "1N8Z", {}, _known()["1N8Z"]["sha256"]
    )

    assert experimental.state == "measured"
    assert experimental.definition == analysis._CONTACT_DEFINITION.format(
        cutoff=contacts.CUTOFF_ANGSTROM
    )


def test_a_quoted_model_number_does_not_drop_every_atom():
    """CIF는 값을 따옴표로 감쌀 수 있다. model 번호도 토큰이 아니라 값으로 비교해야 한다."""
    header = "\n".join(["data_test", "loop_"] + [
        "_atom_site." + n for n in ("group_PDB", "label_asym_id", "label_seq_id", "type_symbol",
                                    "Cartn_x", "Cartn_y", "Cartn_z", "pdbx_PDB_model_num")])
    rows = '\nATOM A 1 C 0.0 0.0 0.0 "1"\nATOM B 1 C 1.0 0.0 0.0 "1"\n'
    assert len(contacts.parse_atoms(header + rows)) == 2


def _synthetic_prediction(seqs: dict[str, list[int]]) -> str:
    """사슬별 접촉 잔기 번호를 주면 그 자리만 닿는 최소 mmCIF를 만든다."""
    header = "\n".join(["data_pred", "loop_"] + [
        "_atom_site." + n for n in ("group_PDB", "label_asym_id", "label_seq_id", "type_symbol",
                                    "Cartn_x", "Cartn_y", "Cartn_z", "pdbx_PDB_model_num")])
    rows = []
    for chain, positions in seqs.items():
        for seq in positions:
            # 표적은 x=0, 항체는 x=2 줄에 두고 y로 잔기를 떼어 놓는다.
            # 같은 번호끼리만 4.5 Å 안에서 만난다.
            x = 0.0 if chain == "A" else 2.0
            rows.append(f"ATOM {chain} {seq} C {x} {float(seq * 10)} 0.0 1")
    return header + "\n" + "\n".join(rows) + "\n"


def _trastuzumab_target_sequence() -> str:
    text = (structures.STRUCTURE_DIR / "1N8Z.cif").read_text()
    ents, _ = structures.parse_entities(text)
    return next(e.sequence for e in ents if "C" in e.strand_ids)


def test_a_prediction_landing_on_the_trastuzumab_interface_is_measured_as_such(tmp_path):
    """새 항체를 이미 본 트라스투주맙 자리에 붙인 예측을 수치로 드러낸다.

    실측 근거: 개발 미사용 8JYR·3N85는 예측 접촉과 실험 접촉의 겹침이 0이었고,
    3N85는 예측 접촉 22개 중 12개가 1N8Z 실험 에피토프와 같은 자리였다.
    """
    epitope = sorted(r["seq"] for r in _known()["1N8Z"]["residues"] if r["chain"] == "C")[:3]
    mapping = [{"role": "target", "label_asym_id": "A"},
               {"role": "heavy", "label_asym_id": "H"},
               {"role": "light", "label_asym_id": "L"}]
    source = {"title": "t", "url": "https://example.invalid", "record_id": "r"}
    target_seq = _trastuzumab_target_sequence()

    on = tmp_path / "on.cif"
    on.write_text(_synthetic_prediction({"A": epitope, "H": epitope[:2], "L": epitope[2:3]}))
    hit = analysis.reference_epitope_overlap_measurement(on, mapping, target_seq, source)
    assert hit.state == "measured" and hit.value == 1.0
    assert sorted(r["label_seq_id"] for r in hit.residues) == epitope

    off = tmp_path / "off.cif"
    elsewhere = [n for n in range(20, 40) if n not in epitope][:3]
    off.write_text(_synthetic_prediction({"A": elsewhere, "H": elsewhere[:2], "L": elsewhere[2:3]}))
    miss = analysis.reference_epitope_overlap_measurement(off, mapping, target_seq, source)
    assert miss.state == "measured" and miss.value == 0.0 and not miss.residues


def test_the_overlap_is_not_reported_when_the_target_cannot_contain_the_reference_epitope(tmp_path):
    """기준 계면이 들어 있지 않은 표적에서는 0.000이 아니라 미실행으로 낸다.

    실측 근거: 8JYR은 HER2 도메인 I 202잔기만 제출한다. 기준 계면(1N8Z) 잔기 19개는
    도메인 IV(557~605)에 있어 서열 정렬로 대응되는 자리가 0개다. 그 입력에서 0.000을
    내보내면 "다른 자리에 붙었다"로 읽힌다. 3N85는 624잔기라 19개가 모두 대응된다.
    """
    full = structures.normalize_sequence(_trastuzumab_target_sequence())
    epitope = sorted(r["seq"] for r in _known()["1N8Z"]["residues"] if r["chain"] == "C")
    # 기준 계면보다 앞쪽만 잘라 낸 construct. 도메인 I만 보내는 8JYR과 같은 모양이다.
    head = full[:min(epitope) - 50]
    assert len(head) > 100
    mapping = [{"role": "target", "label_asym_id": "A"}, {"role": "heavy", "label_asym_id": "H"},
               {"role": "light", "label_asym_id": "L"}]
    source = {"title": "t", "url": "https://example.invalid", "record_id": "r"}
    path = tmp_path / "head.cif"
    path.write_text(_synthetic_prediction({"A": [10, 11, 12], "H": [10, 11], "L": [12]}))

    m = analysis.reference_epitope_overlap_measurement(path, mapping, head, source)
    assert m.state == "not_run"
    assert m.value is None
    assert "잴 대상이 없다" in m.reason

    # 같은 예측이라도 표적이 온전하면 값을 낸다. 미실행이 되는 조건은 표적 쪽이다.
    whole = analysis.reference_epitope_overlap_measurement(path, mapping, full, source)
    assert whole.state == "measured" and whole.value == 0.0


def test_the_overlap_is_not_invented_without_a_target_sequence(tmp_path):
    """표적 서열이 없으면 좌표를 공통 번호로 옮길 수 없다. 값을 만들지 않는다."""
    path = tmp_path / "p.cif"
    path.write_text(_synthetic_prediction({"A": [1, 2], "H": [1], "L": [2]}))
    m = analysis.reference_epitope_overlap_measurement(
        path, [{"role": "target", "label_asym_id": "A"}, {"role": "heavy", "label_asym_id": "H"},
               {"role": "light", "label_asym_id": "L"}], "", {"title": "t", "url": "u", "record_id": "r"})
    assert m.state == "not_run" and m.reason


def test_predicted_contacts_carry_the_held_out_result_in_their_definition(tmp_path):
    """예측 구조의 접촉 잔기는 실험 구조와 같은 권위로 읽히면 안 된다.

    실측: 개발에 쓰지 않은 8JYR·3N85에서 예측 접촉과 실험 접촉의 겹침이 0이었다.
    그 사실이 근거 정의에 붙어 보고서·화면까지 따라가야 한다.
    """
    path = tmp_path / "p.cif"
    path.write_text(_synthetic_prediction({"A": [10, 11], "H": [10], "L": [11]}))
    m = analysis.predicted_contact_measurement(
        path, [{"role": "target", "label_asym_id": "A"}, {"role": "heavy", "label_asym_id": "H"},
               {"role": "light", "label_asym_id": "L"}], {"title": "t", "url": "u", "record_id": "r"})
    # contact_residues는 가까운 쌍의 양쪽 잔기를 모두 담는다(표적 2 + 항체 2).
    assert m.state == "measured" and m.value == 4.0
    assert "개발에 쓰지 않은" in m.definition and "겹침" in m.definition
