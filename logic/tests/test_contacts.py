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
