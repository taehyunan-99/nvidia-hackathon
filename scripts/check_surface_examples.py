"""Check the common calculator against a additional public HER2 inputs; no model calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import gemmi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from logic.surface_analysis import calculate, rows
from logic.structures import find_structure, her2_target_sequence, normalize_sequence


def run(path, out):
    content = path.read_text()
    block = gemmi.cif.read_string(content).sole_block()
    pdb_id = block.find_value('_entry.id')
    if pdb_id not in {'3N85', '6BGT'}:
        raise ValueError('This verification covers 3N85 and 6BGT.')
    seqs = {r['entity_id']: normalize_sequence(gemmi.cif.as_string(r['pdbx_seq_one_letter_code_can']))
            for r in rows(block, '_entity_poly')}
    target = her2_target_sequence()
    assert seqs['1'].count(target) == 1
    offset = seqs['1'].index(target)
    assert not find_structure(seqs['3'], seqs['2']).complete
    mapping = [{'role': role, 'label_asym_id': chain} for role, chain in
               [('target', 'A'), ('heavy', 'C'), ('light', 'B')]]
    result = calculate(content, mapping, {'target': target, 'heavy': seqs['3'], 'light': seqs['2']})
    ambiguous = [r for r in rows(block, '_atom_site') if r['label_asym_id'] in {'A','B','C'}
                 and (r['label_asym_id'] != 'A' or offset < int(r['label_seq_id']) <= offset + 607)
                 and (float(r['occupancy']) != 1 or r['label_alt_id'] not in {'.','?'})]
    report = {'source': {'pdb_id':pdb_id,'url':f'https://www.rcsb.org/structure/{pdb_id}',
                        'sha256':hashlib.sha256(path.read_bytes()).hexdigest()},
              'mode':'experimental ASU pair, common calculator extension check; not prediction accuracy',
              'target_scope_matches':True,'candidate_not_in_service_catalog':True,
              'state':'measured' if result['core'] is not None else 'not_run',
              'unreviewed_atom_count':len(ambiguous),
              'unreviewed_states':dict(Counter(f"{r['occupancy']} / {r['label_alt_id']}" for r in ambiguous)),
              'result':result,'external_model_calls':0}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'state':report['state'],'unreviewed_atom_count':len(ambiguous),'reason':result.get('reason')},ensure_ascii=False))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--structure',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    run(args.structure,args.out)
