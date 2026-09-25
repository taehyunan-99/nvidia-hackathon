"""Public-demo proximity selections; run with uv --with biopython. Not binding assessment."""
from pathlib import Path
import json, hashlib
from Bio.PDB import MMCIFParser, NeighborSearch
root = Path(__file__).resolve().parents[4] / 'frontend/public/structures'
output = {}
for pdb, chains in [('1N8Z', ['C','A','B']), ('1S78', ['A','C','D'])]:
    path = root / (pdb + '.cif')
    model = MMCIFParser(QUIET=True, auth_chains=False, auth_residues=False).get_structure(pdb, path)[0]
    target = [a for a in model[chains[0]].get_atoms() if a.element not in ('H','D')]
    antibody = [a for c in chains[1:] for a in model[c].get_atoms() if a.element not in ('H','D')]
    search = NeighborSearch(antibody)
    residues = set()
    for atom in target:
        for other in search.search(atom.coord, 4.5):
            for item in [atom, other]:
                residue = item.get_parent()
                residues.add((residue.get_parent().id, residue.id[1]))
    assert residues and all(any(c == chain for c, r in residues) for chain in chains)
    output[pdb] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'cutoff_angstrom':4.5,
                   'residues':[{'chain':c,'seq':r} for c,r in sorted(residues)]}
(root/'contacts.json').write_text(json.dumps(output,indent=2)+'\n')
print({k:len(v['residues']) for k,v in output.items()})
