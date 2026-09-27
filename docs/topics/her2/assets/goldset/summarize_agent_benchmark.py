"""Summarize every attempted case; score held-out structures independently of product contacts."""
import json
import hashlib
import math
import statistics
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT))
import gemmi
from logic import contacts


def target_contacts(text, target, antibody, expected_sequence):
    # Independent brute-force reference: direct CIF columns, not product parser/grid/remapping.
    block = gemmi.cif.read_string(text).sole_block()
    entity_id = dict(block.find(['_struct_asym.id', '_struct_asym.entity_id']))[target]
    sequences = dict(block.find(['_entity_poly.entity_id', '_entity_poly.pdbx_seq_one_letter_code_can']))
    actual = ''.join(gemmi.cif.as_string(sequences[entity_id]).split())
    assert actual == expected_sequence, 'Residue coordinates require the identical target construct'
    rows = block.find('_atom_site.', ['label_asym_id', 'label_seq_id', 'type_symbol',
                                      'Cartn_x', 'Cartn_y', 'Cartn_z', 'pdbx_PDB_model_num'])
    target_atoms, ab_atoms = [], []
    for chain, residue, element, x, y, z, model in rows:
        if model != '1' or element in ('H', 'D') or not residue.isdigit(): continue
        atom = (int(residue), float(x), float(y), float(z))
        if chain == target: target_atoms.append(atom)
        elif chain in antibody: ab_atoms.append(atom)
    assert target_atoms and ab_atoms, "Cannot score missing/unmapped coordinates as zero contacts"
    found = set()
    for residue, x, y, z in target_atoms:
        if residue in found: continue
        if any((x-a)**2 + (y-b)**2 + (z-c)**2 <= 4.5**2 for _, a, b, c in ab_atoms):
            found.add(residue)
    product = {n for chain, n in contacts.contact_residues(contacts.parse_atoms(text), {target}, antibody) if chain == target}
    assert found == product, "Product contact calculation disagrees with independent reference"
    return found


def main():
    manifest = json.loads((HERE / 'generated/agent-benchmark-manifest.json').read_text())
    rows = [json.loads(s) for s in (HERE / 'generated/agent-benchmark-results.jsonl').read_text().splitlines()]
    cases = {c['id']: c for c in manifest['cases']}
    model = [r for r in rows if r['mode'] == 'nat' and cases[r['id']]['model_required']]
    baseline = [r for r in rows if r['mode'] == 'rule' and cases[r['id']]['model_required']]
    quality = []
    for pid in ('8JYR', '3N85'):
        run = ROOT / 'work/agent-benchmark/runs' / f'{pid}-nat'
        if not (run / 'output.json').exists(): continue
        result = json.loads((run / 'output.json').read_text())['result']
        predicted = next((s for s in result['structures'] if s['candidate_id']=='subject' and s['kind']=='predicted'), None)
        if not predicted: continue
        artifact = next(a for a in result['artifacts'] if a['artifact_id']==predicted['artifact_id'])
        text = (run / artifact['file_name']).read_text()
        mapping = {c['role']: c['label_asym_id'] for c in predicted['chain_mapping']}
        assert hashlib.sha256(text.encode()).hexdigest() == artifact['sha256']
        seq = cases[pid]['sequences']['target']
        predicted_set = target_contacts(text, mapping['target'], {mapping['heavy'], mapping['light']}, seq)
        ref = ROOT / 'work/agent-benchmark/sources' / f'{pid}.cif'
        assert hashlib.sha256(ref.read_bytes()).hexdigest() == cases[pid]['source']['sha256']
        gold = target_contacts(ref.read_text(), 'A', {'B', 'C'}, seq)
        tp = len(gold & predicted_set)
        quality.append({'pdb':pid, 'reference_target_contacts':sorted(gold), 'predicted_target_contacts':sorted(predicted_set),
                        'tp':tp, 'precision':tp/len(predicted_set) if predicted_set else 0,
                        'recall':tp/len(gold), 'f1':2*tp/(len(gold)+len(predicted_set)),
                        'reference_sha256':hashlib.sha256(ref.read_bytes()).hexdigest(),
                        'prediction_sha256':hashlib.sha256(text.encode()).hexdigest(),
                        'independent_bruteforce_agrees':True})
    correct = sum(r['agent_task_success'] for r in model)
    n = len(model)
    z = 1.96
    p = correct/n if n else 0
    center = (p+z*z/(2*n))/(1+z*z/n) if n else 0
    radius = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n) if n else 0
    summary = {'attempted_model_cases':n, 'planned_model_cases':sum(c['model_required'] for c in cases.values()),
               'model_task_success':correct, 'clean_success':sum(r['clean_success'] for r in model),
               'source_route_correct':sum(r['route_correct'] for r in model),
               'fallbacks':sum(r['fallback_used'] for r in model),
               'any_agent_error':sum(bool(r['agent_errors']) for r in model),
               'success_wilson95_descriptive_only':[center-radius,center+radius],
               'latency_median_seconds':statistics.median(r['seconds'] for r in model) if model else None,
               'baseline_correct':sum(r['output_correct'] and r['route_correct'] for r in baseline),
               'baseline_attempted':len(baseline), 'structure_quality':quality,
               'limitation':'Purposive small sample, not an iid population estimate. Routing labels are product-policy ground truth, not affinity or clinical truth.'}
    (HERE / 'generated/agent-benchmark-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
