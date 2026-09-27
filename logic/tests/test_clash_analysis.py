from logic.clash_analysis import parse_contacts
import os
import subprocess

import gemmi
import pytest


def line(kind, a, b, gap):
    return f'name:1:{kind}:{a}:{b}:1:0:{gap}:0'


def test_contacts_are_deduplicated_and_hydrogen_bonds_excluded():
    text = '\n'.join([line('bo', 'A', 'B', -.4), line('bo', 'B', 'A', -.5),
                      line('bo', 'C', 'D', -.39), line('bo', 'E', 'F', -.7), line('hb', 'F', 'E', -.7)])
    assert parse_contacts(text) == {('A', 'B'): -.5}


@pytest.mark.skipif(not os.getenv('PROBE_BIN'), reason='pinned Probe executable required')
def test_official_probe_distinguishes_overlap_bond_and_hydrogen_bond():
    def check(atoms):
        structure = gemmi.Structure(); model = gemmi.Model('1')
        for chain_id, residue_name, coordinates in atoms:
            chain = gemmi.Chain(chain_id); residue = gemmi.Residue()
            residue.name = residue_name; residue.seqid = gemmi.SeqId(1, ' '); residue.het_flag = 'A'
            for name, element, xyz in coordinates:
                atom = gemmi.Atom(); atom.name = name; atom.element = gemmi.Element(element)
                atom.pos = gemmi.Position(*xyz); atom.occ = 1; residue.add_atom(atom)
            chain.add_residue(residue); model.add_chain(chain)
        structure.add_model(model)
        p = subprocess.run([os.environ['PROBE_BIN'], '-u', '-q', '-mc', '-het', '-once', '-NOVDWOUT', '-CON',
                            'ogt10 not water', 'ogt10', '-'], input=structure.make_pdb_string(), text=True, capture_output=True, check=True)
        return parse_contacts(p.stdout), p.stdout
    def carbons(distance):
        return [('A', 'ALA', [('CB', 'C', (0, 0, 0))]), ('B', 'ALA', [('CB', 'C', (distance, 0, 0))])]
    assert len(check(carbons(2))[0]) == 1
    assert not check(carbons(6))[0]
    assert not check([('A', 'GLY', [('N', 'N', (0, 0, 0)), ('CA', 'C', (1.45, 0, 0))])])[0]
    bad, output = check([('A', 'SER', [('OG', 'O', (0, 0, 0)), ('HG', 'H', (.84, 0, 0))]),
                         ('B', 'ASP', [('OD1', 'O', (2.5, 0, 0))])])
    assert ':hb:' in output
    assert not bad
