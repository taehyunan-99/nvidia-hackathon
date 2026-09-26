import argparse
import copy
import hashlib
import json
import platform
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from importlib.metadata import version

import numpy as np
from Bio.PDB.Atom import Atom
from Bio.PDB.Chain import Chain
from Bio.PDB.Residue import Residue
from Bio.PDB.SASA import ShrakeRupley

HERE = Path(__file__).resolve().parent
A02 = HERE.parent / 'a02'
sys.path.insert(0, str(A02))
import analyze as baseline
import metrics

ROOT = baseline.ROOT
POINTS = (960, 1920)
CONTEXT_CHAIN = '__a03_occluders__'
LIMITS = [
    'Observed NAG fragments only; unobserved glycans and missing atoms are not reconstructed.',
    'No glycan coordinates means unknown context, not glycan absence or zero shielding.',
    'Protein-only SASA in fixed coordinates; no glycan surface is added to the readout.',
    'Water, ions, hydrogen/deuterium, membrane and assembly 2 are excluded.',
    'No efficacy, affinity, complete accessibility or validated clash classification.',
]


def identity(atom):
    return (atom['model_number'], atom['label_asym_id'], atom['auth_asym_id'],
            atom['auth_seq_id'], atom['insertion_code'], atom['component'])


def select_glycans(raw, components):
    sugars = {c['id'] for c in components if 'saccharide' in c['type'].lower()}
    atoms, excluded = [], Counter()
    for row in raw:
        if baseline.inputs.number(row['label_seq_id']) is not None:
            continue
        comp = row['label_comp_id']
        if comp not in sugars:
            excluded[comp] += 1
            continue
        if comp != 'NAG':
            raise ValueError(f'Unreviewed saccharide: {comp}')
        if row['type_symbol'] in ('H', 'D'):
            excluded['hydrogen_deuterium'] += 1
            continue
        if (int(row['pdbx_PDB_model_num']) != 1 or float(row['occupancy']) != 1
                or baseline.inputs.nullable(row['label_alt_id']) is not None):
            raise ValueError('Glycan model, occupancy or alternate conformer requires review')
        atoms.append({
            'model_number': 1, 'operator_id': '1', 'assembly_id': '1',
            'label_asym_id': row['label_asym_id'], 'auth_asym_id': row['auth_asym_id'],
            'label_seq_id': None, 'sequence_position': None,
            'auth_seq_id': baseline.inputs.number(row['auth_seq_id']),
            'insertion_code': baseline.inputs.nullable(row['pdbx_PDB_ins_code']),
            'component': comp, 'atom_name': row['label_atom_id'], 'element': row['type_symbol'],
            'xyz': [float(row[f'Cartn_{axis}']) for axis in 'xyz'],
        })
    validate_glycans(atoms)
    return atoms, dict(excluded)


def validate_glycans(atoms):
    seen = set()
    for atom in atoms:
        if atom['element'] not in metrics.RADII:
            raise ValueError(f"Unsupported element: {atom['element']}")
        if len(atom['xyz']) != 3 or not np.isfinite(atom['xyz']).all():
            raise ValueError('Invalid glycan coordinates')
        if atom['label_seq_id'] is not None or atom['sequence_position'] is not None:
            raise ValueError('Glycan cannot have fabricated protein sequence positions')
        key = identity(atom) + (atom['atom_name'],)
        if key in seen:
            raise ValueError('Duplicate glycan atom')
        seen.add(key)


def link_endpoint(row, partner, raw):
    prefix = f'ptnr{partner}_'
    if row[prefix + 'symmetry'] != '1_555':
        raise ValueError('Unsupported covalent symmetry')
    if baseline.inputs.nullable(row[f'pdbx_ptnr{partner}_label_alt_id']) is not None:
        raise ValueError('Unsupported covalent alternate conformer')
    matches = [a for a in raw if (
        a['label_asym_id'], a['label_comp_id'], baseline.inputs.number(a['label_seq_id']),
        a['label_atom_id'], a['auth_asym_id'], baseline.inputs.number(a['auth_seq_id']),
        baseline.inputs.nullable(a['pdbx_PDB_ins_code'])) == (
        row[prefix + 'label_asym_id'], row[prefix + 'label_comp_id'],
        baseline.inputs.number(row[prefix + 'label_seq_id']), row[prefix + 'label_atom_id'],
        row[prefix + 'auth_asym_id'], baseline.inputs.number(row[prefix + 'auth_seq_id']),
        baseline.inputs.nullable(row[f'pdbx_ptnr{partner}_PDB_ins_code']))]
    if len(matches) != 1:
        raise ValueError('Covalent endpoint is absent or ambiguous in assembly 1')
    return matches[0]


def load_context(ref):
    assembly = baseline.MMCIF2Dict(str(ref.path))
    raw = baseline.inputs.rows(assembly, '_atom_site')
    original_path = baseline.A01 / 'sources' / f'{ref.pdb}.cif'
    original = baseline.MMCIF2Dict(str(original_path))
    components = baseline.inputs.rows(original, '_chem_comp')
    atoms, excluded = select_glycans(raw, components)
    groups = defaultdict(list)
    for atom in atoms:
        groups[identity(atom)].append(atom)
    residues = []
    for key, group in sorted(groups.items()):
        first = group[0]
        matches = [r for r in ref.structure['residue_mapping'] if (
            r['model_number'], r['label_asym_id'], r['auth_asym_id'],
            r['auth_seq_id'], r['insertion_code']) == key[:5]
            and r['label_seq_id'] is None and r['sequence_position'] is None]
        if len(matches) != 1 or not matches[0]['has_coordinates']:
            raise ValueError('Glycan identity differs from A-01 residue mapping')
        residues.append({'residue': matches[0], 'component': first['component'],
                         'observed_heavy_atoms': len(group),
                         'atom_names': sorted(a['atom_name'] for a in group)})
    chains = {c['label_asym_id'] for c in ref.structure['chain_mapping']}
    sugar_chains = {a['label_asym_id'] for a in atoms}
    links = []
    for row in baseline.inputs.rows(original, '_struct_conn'):
        partners = {row['ptnr1_label_asym_id'], row['ptnr2_label_asym_id']}
        if row['conn_type_id'] != 'covale' or not partners & sugar_chains:
            continue
        if not partners <= chains:
            raise ValueError('Glycan link crosses the approved assembly')
        endpoints = [link_endpoint(row, i, raw) for i in (1, 2)]
        resolved = []
        for a in endpoints:
            matches = [r for r in ref.structure['residue_mapping'] if (
                r['label_asym_id'], r['auth_asym_id'], r['auth_seq_id'], r['insertion_code'], r['label_seq_id']) == (
                a['label_asym_id'], a['auth_asym_id'], baseline.inputs.number(a['auth_seq_id']),
                baseline.inputs.nullable(a['pdbx_PDB_ins_code']), baseline.inputs.number(a['label_seq_id']))]
            if len(matches) != 1:
                raise ValueError('Covalent residue mapping is ambiguous')
            resolved.append({'residue': matches[0], 'atom_name': a['label_atom_id'], 'component': a['label_comp_id']})
        distance = float(np.linalg.norm(np.array([float(endpoints[0][f'Cartn_{a}']) for a in 'xyz'])
                                       - np.array([float(endpoints[1][f'Cartn_{a}']) for a in 'xyz'])))
        links.append({'annotation': row, 'endpoints': resolved, 'observed_distance_angstrom': distance})
    return atoms, {'pdb_id': ref.pdb, 'assembly_id': '1', 'operator_id': '1',
                   'state': 'observed_partial' if atoms else 'unknown',
                   'observed_glycan_residues': residues, 'observed_glycan_atoms': len(atoms),
                   'excluded_nonprotein_atoms': excluded, 'covalent_links': links,
                   'component_definitions': [c for c in components if c['id'] in {a['component'] for a in atoms}],
                   'covalent_annotation_source': original_path.relative_to(ROOT).as_posix(),
                   'limits': LIMITS}


def protein_surface(protein, context, points):
    metrics.validate_atoms(protein)
    validate_glycans(context)
    if not protein:
        raise ValueError('No usable protein atoms')
    if any(a.chain == CONTEXT_CHAIN for a in protein):
        raise ValueError('Reserved internal context chain collision')
    model = metrics.make_model(protein)
    protein_residues = list(model.get_residues())
    chain = Chain(CONTEXT_CHAIN)
    model.add(chain)
    groups = {}
    for serial, atom in enumerate(context, len(protein) + 1):
        key = identity(atom)
        if key not in groups:
            residue = Residue(('H_NAG', len(groups) + 1, ' '), atom['component'], ' ')
            groups[key] = residue
            chain.add(residue)
        groups[key].add(Atom(atom['atom_name'], np.array(atom['xyz'], dtype=float), 0, 1, ' ',
                             atom['atom_name'], serial, element=atom['element']))
    ShrakeRupley(probe_radius=metrics.PROBE_RADIUS, n_points=points,
                radii_dict=metrics.RADII).compute(model, level='R')
    return {(r.get_parent().id, r.id[1]): float(r.sasa) for r in protein_residues}


def compare(protein, context, points=960):
    if not protein or not context:
        return {'state': 'unknown', 'reason': 'Usable protein or observed glycan coordinates are absent',
                'core': None, 'context': None, 'reduction': None}
    core = protein_surface(protein, [], points)
    surrounded = protein_surface(protein, context, points)
    if core.keys() != surrounded.keys():
        raise ValueError('Protein readout changed across conditions')
    reduction = {key: core[key] - surrounded[key] for key in core}
    if min(reduction.values()) < -1e-8:
        raise ValueError('Occluders unexpectedly increased protein SASA')
    return {'state': 'measured', 'reason': None, 'core': core, 'context': surrounded, 'reduction': reduction}


def fingerprints(atoms):
    rows = [(a.chain, a.label, a.name, a.element, a.xyz) for a in atoms]
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


def validate_fragments(fragments):
    dependency = fragments['a02_dependency']
    path = ROOT / dependency['repository_path']
    if baseline.digest(path) != dependency['sha256']:
        raise ValueError('A-02 dependency changed')
    resolved = baseline.read_json(path)
    resolved['conditions'] = fragments['conditions']
    resolved['evidence'] = fragments['evidence']
    baseline.validate_fragments(resolved)
    ids = [e['evidence_id'] for e in fragments['evidence']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate evidence ID')


def run(output):
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    dependency = A02 / 'generated/service-fragments.json'
    fragments = {'format': 'a03-fragments-1', 'purpose': 'Condition/Evidence additions; not a live Result',
                 'a02_dependency': {'repository_path': dependency.relative_to(ROOT).as_posix(),
                                    'sha256': baseline.digest(dependency)}, 'conditions': [], 'evidence': []}
    entries, inventories = [], []
    reference_summary = baseline.read_json(A02 / 'generated/summary.json')
    for pdb in baseline.PDBS:
        ref = baseline.load_reference(pdb)
        context, inventory = load_context(ref)
        inventories.append(inventory)
        before = fingerprints(ref.atoms)
        rows, results = [], []
        baseline_entry = next(s for s in reference_summary['entries'] if s['pdb_id'] == pdb)
        roles = {c['label_asym_id']: c['role'] for c in ref.structure['chain_mapping']}
        for points in POINTS:
            result = compare(ref.atoms, context, points)
            if result['state'] != 'measured':
                results.append({'points': points, 'state': 'unknown', 'reason': result['reason'],
                                'core_protein_sasa': None, 'context_protein_sasa': None, 'reduction': None})
                continue
            expected = next(s['complex_sasa'] for s in baseline_entry['sasa'] if s['points'] == points)
            core_total = sum(result['core'].values())
            if abs(core_total - expected) > 1e-7:
                raise ValueError('Core SASA differs from A-02 at the same resolution')
            by_role = {role: {field: sum(value for key, value in result[field].items() if roles[key[0]] == role)
                             for field in ('core', 'context', 'reduction')} for role in ('target', 'heavy', 'light')}
            results.append({'points': points, 'state': 'measured', 'core_protein_sasa': core_total,
                            'context_protein_sasa': sum(result['context'].values()),
                            'reduction': sum(result['reduction'].values()), 'by_role': by_role})
            for key in sorted(result['core']):
                rows.append({**baseline.residue(ref.selected[key]), 'role': roles[key[0]], 'points': points,
                             **{f'{field}_sasa_angstrom2': result[field][key] for field in ('core', 'context', 'reduction')}})
        if fingerprints(ref.atoms) != before:
            raise ValueError('Protein coordinates mutated')
        gaps = [g for g in ref.gaps if not g.startswith('Glycans, water')] + LIMITS
        conditions = {}
        for kind in ('core', 'context'):
            condition_id = f'a03-{pdb.lower()}-{kind}'
            conditions[kind] = condition_id
            fragments['conditions'].append({
                'condition_id': condition_id, 'candidate_id': ref.structure['candidate_id'], 'kind': kind,
                'structure_ids': [ref.structure['structure_id']],
                'included_components': ['observed HER2 heavy atoms', 'observed Fab heavy/light-chain heavy atoms']
                    + (['observed assembly-1 NAG heavy atoms as occluders only'] if kind == 'context' and context else []),
                'gaps': gaps + (['Observed glycans intentionally omitted in core condition.'] if kind == 'core' else []),
                'sources': [ref.structure['source']]})
        primary = results[0]
        for kind, topic, field in (('core', 'surface_exposure', 'core_protein_sasa'),
                                  ('context', 'surface_exposure', 'context_protein_sasa'),
                                  ('context', 'observed_glycan_protein_sasa_reduction', 'reduction')):
            item = baseline.evidence(ref, topic, primary[field], 'angstrom^2',
                'Fixed identical protein atom readout; observed NAG occluders only in context; core minus context for reduction; 1.4 A probe, 960 points; not efficacy.',
                state=primary['state'], reason=primary.get('reason'))
            item.update(evidence_id=f'a03-{pdb.lower()}-{kind}-{topic}', condition_id=conditions[kind])
            fragments['evidence'].append(item)
        for kind in ('core', 'context'):
            for topic, state, reason in (
                ('whole_range_accessibility', 'unknown', 'Incomplete protein and glycans/environment.'),
                ('atom_clash', 'not_run', 'Validated bonded/hydrogen-aware clash classification not implemented.')):
                item = baseline.evidence(ref, topic, None, None, None, state=state, reason=reason)
                item.update(evidence_id=f'a03-{pdb.lower()}-{kind}-{topic}', condition_id=conditions[kind])
                fragments['evidence'].append(item)
        entries.append({'pdb_id': pdb, 'candidate_id': ref.structure['candidate_id'], 'structure_id': ref.structure['structure_id'],
                        'conditions': conditions, 'protein_atom_count': len(ref.atoms),
                        'core_protein_fingerprint': before, 'context_protein_fingerprint': fingerprints(ref.atoms),
                        'glycan_residue_count': len(inventory['observed_glycan_residues']), 'glycan_atom_count': len(context),
                        'coverage': ref.coverage, 'missing_atom_annotations': ref.missing_atoms,
                        'sasa': results, 'reduction_resolution_difference_angstrom2':
                            abs(results[1]['reduction'] - primary['reduction']) if primary['state'] == results[1]['state'] == 'measured' else None,
                        'gaps': gaps})
        if rows:
            baseline.write_csv(output / f'{pdb.lower()}-protein-sasa.csv', rows, list(rows[0]))
    validate_fragments(fragments)
    summary = {'format': 'a03-1', 'readout': 'Fixed observed protein atoms only; reduction = core - context',
               'unit': 'angstrom^2', 'parameters': {'points': list(POINTS), 'probe_radius_angstrom': metrics.PROBE_RADIUS,
                                                   'atomic_radii_angstrom': metrics.RADII},
               'entries': entries, 'limits': LIMITS,
               'runtime': {'python': platform.python_version(), **{k: version(k) for k in ('biopython', 'numpy', 'jsonschema')}}}
    for name, value in (('summary.json', summary), ('glycan-inventory.json', inventories), ('service-fragments.json', fragments)):
        baseline.write_json(output / name, value)
    inputs = [HERE / 'compare.py', A02 / 'analyze.py', A02 / 'metrics.py', baseline.A01 / 'build_inputs.py',
              A02 / 'generated/summary.json', dependency, baseline.A01 / 'source-lock.json',
              ROOT / 'docs/frontend-hosting/contracts/service.schema.json']
    inputs.extend(baseline.A01 / 'generated' / name for name in ('review-input.json', 'structures.json', 'artifacts.json'))
    baseline.write_json(output / 'provenance.json', {
        'inputs_and_implementation': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': baseline.digest(p)} for p in inputs],
        'source_files': baseline.read_json(baseline.A01 / 'source-lock.json')['sources'],
        'output_files': [{'path': p.name, 'sha256': baseline.digest(p)} for p in sorted(output.iterdir())
                         if p.suffix in ('.csv', '.json') and p.name not in ('provenance.json', 'validation.json')],
        'elapsed_seconds': round(time.perf_counter() - started, 3)})
    print(json.dumps({'status': 'calculated', 'entries': [
        {'pdb': s['pdb_id'], 'glycans': s['glycan_residue_count'], 'sasa': s['sasa']} for s in entries],
        'seconds': round(time.perf_counter() - started, 2)}))
    return summary, fragments


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=HERE / 'generated')
    run(parser.parse_args().out)
