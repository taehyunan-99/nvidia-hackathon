import csv
import hashlib
import json
import platform
from collections import Counter, defaultdict
from importlib.metadata import version
from pathlib import Path

from Bio.Data.PDBData import protein_letters_3to1
from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from jsonschema import Draft202012Validator, FormatChecker

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = HERE / 'generated'
PDBS = ('1N8Z', '1S78')
CANDIDATES = {'1N8Z': 'reference-trastuzumab-fab', '1S78': 'reference-pertuzumab-fab'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rows(cif, category):
    columns = {k.split('.', 1)[1]: v for k, v in cif.items() if k.startswith(category + '.')}
    require(len({len(v) for v in columns.values()}) <= 1, f'Ragged category: {category}')
    return [dict(zip(columns, values)) for values in zip(*columns.values())]


def nullable(value):
    return None if value in (None, '.', '?') else value


def number(value):
    return int(value) if nullable(value) is not None else None


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def write_csv(name, data):
    with (OUT / name).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(data)


def fasta(name, sequence):
    return '>' + name + '\n' + '\n'.join(sequence[i:i + 80] for i in range(0, len(sequence), 80)) + '\n'


def ranges(values):
    result = []
    for value in sorted(set(values)):
        if result and value == result[-1][1] + 1:
            result[-1][1] = value
        else:
            result.append([value, value])
    return result


def source(pdb):
    return {'title': f'RCSB PDB {pdb}', 'url': f'https://www.rcsb.org/structure/{pdb}', 'record_id': pdb}


def role(entity):
    description = entity['pdbx_description'].lower()
    if entity['type'] == 'polymer':
        if 'erb' in description:
            return 'target'
        if 'heavy chain' in description:
            return 'heavy'
        if 'light chain' in description:
            return 'light'
        raise ValueError(f'Unreviewed polymer role: {description}')
    return 'context' if 'glucopyranose' in description else 'other'


def atom_signature(atom):
    fields = ('group_PDB', 'type_symbol', 'label_atom_id', 'label_alt_id', 'label_comp_id',
              'label_asym_id', 'label_seq_id', 'pdbx_PDB_ins_code', 'Cartn_x', 'Cartn_y',
              'Cartn_z', 'occupancy', 'B_iso_or_equiv', 'auth_seq_id', 'auth_asym_id',
              'pdbx_PDB_model_num')
    return tuple(atom[field] for field in fields)


def inspect_entry(pdb, canonical):
    cif = MMCIF2Dict(str(HERE / 'sources' / f'{pdb}.cif'))
    atoms = rows(cif, '_atom_site')
    require({a['pdbx_PDB_model_num'] for a in atoms} == {'1'}, f'{pdb}: unreviewed models')
    entities = {r['id']: r for r in rows(cif, '_entity')}
    chains = {r['id']: r['entity_id'] for r in rows(cif, '_struct_asym')}
    polymers = {r['entity_id']: ''.join(r['pdbx_seq_one_letter_code_can'].split())
                for r in rows(cif, '_entity_poly')}
    sequence_rows = rows(cif, '_entity_poly_seq')
    for entity, sequence in polymers.items():
        table = sorted((r for r in sequence_rows if r['entity_id'] == entity), key=lambda r: int(r['num']))
        require([int(r['num']) for r in table] == list(range(1, len(sequence) + 1)), 'Ambiguous sequence')
        require(''.join(protein_letters_3to1[r['mon_id']] for r in table) == sequence,
                f'{pdb}: deposited sequence mismatch')
    reference = [r for r in rows(cif, '_struct_ref_seq') if r['pdbx_db_accession'] == 'P04626']
    by_auth = {r['pdbx_strand_id']: r for r in reference}
    by_label = defaultdict(list)
    for atom in atoms:
        by_label[(atom['label_asym_id'], number(atom['label_seq_id']))].append(atom)
    missing = {(r['label_asym_id'], int(r['label_seq_id'])): r
               for r in rows(cif, '_pdbx_unobs_or_zero_occ_residues') if r['polymer_flag'] == 'Y'}
    mapping = []
    for seq in rows(cif, '_pdbx_poly_seq_scheme'):
        chain, pos = seq['asym_id'], int(seq['seq_id'])
        entity = seq['entity_id']
        chain_role = role(entities[entity])
        observed = by_label[(chain, pos)]
        auth_chain = seq['pdb_strand_id']
        auth_id = int(seq['pdb_seq_num'])
        insertion = nullable(seq['pdb_ins_code'])
        require({(a['auth_asym_id'], int(a['auth_seq_id']), nullable(a['pdbx_PDB_ins_code']))
                 for a in observed} <= {(auth_chain, auth_id, insertion)}, f'{pdb}/{chain}/{pos}: numbering')
        require({a['label_comp_id'] for a in observed} <= {seq['mon_id']}, 'Residue identity mismatch')
        require(protein_letters_3to1[seq['mon_id']] == polymers[entity][pos - 1], 'Sequence position mismatch')
        uniprot_pos = None
        if chain_role == 'target':
            ref = by_auth[auth_chain]
            begin, end = int(ref['seq_align_beg']), int(ref['seq_align_end'])
            db_begin, db_end = int(ref['db_align_beg']), int(ref['db_align_end'])
            require(end - begin == db_end - db_begin, 'Nonlinear reference mapping requires review')
            require(polymers[entity][begin - 1:end] == canonical[db_begin - 1:db_end], 'UniProt sequence mismatch')
            require(begin <= pos <= end, 'Target outside verified reference mapping')
            uniprot_pos = db_begin + pos - begin
        if not observed:
            require((chain, pos) in missing, f'{pdb}/{chain}/{pos}: missing residue not annotated')
            annotation = missing[(chain, pos)]
            require((annotation['auth_asym_id'], int(annotation['auth_seq_id']),
                     nullable(annotation['PDB_ins_code'])) == (auth_chain, auth_id, insertion),
                    'Missing residue author identity mismatch')
        mapping.append({
            'pdb_id': pdb, 'model_number': 1, 'entity_id': entity, 'role': chain_role,
            'label_asym_id': chain, 'auth_asym_id': auth_chain,
            'label_seq_id': pos, 'auth_seq_id': auth_id, 'insertion_code': insertion,
            'scheme_auth_seq_num': nullable(seq['auth_seq_num']), 'component_id': seq['mon_id'],
            'entity_sequence_position': pos,
            'sequence_position': uniprot_pos if chain_role == 'target' else pos,
            'uniprot_accession': 'P04626' if chain_role == 'target' else None,
            'uniprot_position': uniprot_pos, 'has_coordinates': bool(observed),
            'atom_count': len(observed), 'positive_occupancy_atom_count': sum(float(a['occupancy']) > 0 for a in observed),
            'coordinate_status': 'observed' if observed else 'unobserved',
        })
    require({(r['label_asym_id'], r['label_seq_id']) for r in mapping if not r['has_coordinates']}
            == set(missing), f'{pdb}: missing-residue annotation coverage mismatch')
    nonpoly = defaultdict(list)
    for atom in atoms:
        if nullable(atom['label_seq_id']) is None:
            key = (atom['label_asym_id'], atom['auth_asym_id'], atom['auth_seq_id'],
                   nullable(atom['pdbx_PDB_ins_code']), atom['label_comp_id'])
            nonpoly[key].append(atom)
    for (chain, auth_chain, auth_seq, insertion, component), group in sorted(nonpoly.items()):
        mapping.append({
            'pdb_id': pdb, 'model_number': 1, 'entity_id': chains[chain], 'role': role(entities[chains[chain]]),
            'label_asym_id': chain, 'auth_asym_id': auth_chain,
            'label_seq_id': None, 'auth_seq_id': int(auth_seq), 'insertion_code': insertion,
            'scheme_auth_seq_num': None, 'component_id': component, 'entity_sequence_position': None,
            'sequence_position': None, 'uniprot_accession': None, 'uniprot_position': None,
            'has_coordinates': True, 'atom_count': len(group),
            'positive_occupancy_atom_count': sum(float(a['occupancy']) > 0 for a in group),
            'coordinate_status': 'observed',
        })
    require(sum(r['atom_count'] for r in mapping) == len(atoms), f'{pdb}: lost or duplicated atoms')
    summaries = []
    for chain, entity in chains.items():
        selected = [r for r in mapping if r['label_asym_id'] == chain]
        auth = {r['auth_asym_id'] for r in selected}
        require(len(auth) == 1, f'{pdb}/{chain}: ambiguous author chain')
        summaries.append({
            'pdb_id': pdb, 'label_asym_id': chain, 'auth_asym_id': next(iter(auth)),
            'entity_id': entity, 'role': role(entities[entity]), 'entity_type': entities[entity]['type'],
            'description': entities[entity]['pdbx_description'],
            'sequence_length': len(polymers[entity]) if entity in polymers else None,
            'observed_residues': sum(r['has_coordinates'] for r in selected),
            'missing_residues': sum(not r['has_coordinates'] for r in selected),
            'missing_label_ranges': ranges(r['label_seq_id'] for r in selected if not r['has_coordinates']),
            'insertion_residues': [{'label': r['label_seq_id'], 'auth': r['auth_seq_id'], 'code': r['insertion_code']}
                                   for r in selected if r['insertion_code']],
            'uniprot_ranges': ranges(r['uniprot_position'] for r in selected if r['uniprot_position']),
            'atom_count': sum(r['atom_count'] for r in selected),
            'components': dict(Counter(r['component_id'] for r in selected)) if entity not in polymers else {},
        })
    glycan_links = [r for r in rows(cif, '_struct_conn') if r['conn_type_id'] == 'covale'
                   and (r['ptnr1_label_comp_id'] in ('NAG', 'BMA') or r['ptnr2_label_comp_id'] in ('NAG', 'BMA'))]
    return cif, atoms, mapping, summaries, polymers, glycan_links


def main():
    OUT.mkdir(exist_ok=True)
    lock = json.loads((HERE / 'source-lock.json').read_text(encoding='utf-8'))
    for item in lock['sources']:
        path = ROOT / item['path']
        require(path.stat().st_size == item['bytes'] and digest(path) == item['sha256'], f'Source changed: {path}')
    canonical_fasta = (HERE / 'sources/P04626.fasta').read_text(encoding='utf-8')
    canonical = ''.join(canonical_fasta.splitlines()[1:])
    require('P04626' in canonical_fasta.splitlines()[0], 'Unexpected reference identifier')
    all_residues, all_chains, structures, artifacts, files, entry_summaries = [], [], [], [], [], []
    candidates, uploads, sequence_records = [], [], []
    for pdb in PDBS:
        cif, atoms, mapping, chains, polymers, glycan_links = inspect_entry(pdb, canonical)
        all_residues.extend(mapping)
        all_chains.extend(chains)
        for entity, sequence in polymers.items():
            sequence_records.append(fasta(f'{pdb}|entity={entity}|deposited_sequence', sequence))
        heavy = next(r for r in chains if r['role'] == 'heavy')
        light = next(r for r in chains if r['role'] == 'light')
        candidates.append({
            'candidate_id': CANDIDATES[pdb],
            'name': 'Trastuzumab (Herceptin) Fab reference' if pdb == '1N8Z' else 'Pertuzumab Fab reference',
            'antibody_format': 'Fab',
            'heavy_chain_fasta': fasta(f'{pdb}|heavy|entity={heavy["entity_id"]}', polymers[heavy['entity_id']]),
            'light_chain_fasta': fasta(f'{pdb}|light|entity={light["entity_id"]}', polymers[light['entity_id']]),
            'heavy_analysis_range': {'start': 1, 'end': heavy['sequence_length']},
            'light_analysis_range': {'start': 1, 'end': light['sequence_length']}, 'sources': [source(pdb)],
        })
        assemblies = []
        operations = {r['id']: r for r in rows(cif, '_pdbx_struct_oper_list')}
        for assembly in rows(cif, '_pdbx_struct_assembly_gen'):
            assembly_id = assembly['assembly_id']
            require(assembly['oper_expression'] == '1', 'Nonidentity assembly requires explicit transformation support')
            operation = operations['1']
            require(all(float(operation[f'matrix[{i}][{j}]']) == int(i == j)
                        for i in range(1, 4) for j in range(1, 4))
                    and all(float(operation[f'vector[{i}]']) == 0 for i in range(1, 4)), 'Nonidentity operator')
            labels = assembly['asym_id_list'].split(',')
            path = HERE / 'sources' / f'{pdb}-assembly{assembly_id}.cif'
            assembly_cif = MMCIF2Dict(str(path))
            assembly_atoms = rows(assembly_cif, '_atom_site')
            expected_atoms = [a for a in atoms if a['label_asym_id'] in labels]
            require(Counter(map(atom_signature, assembly_atoms)) == Counter(map(atom_signature, expected_atoms)),
                    f'{pdb} assembly {assembly_id}: deposited and assembly atoms differ')
            selected_chains = [r for r in chains if r['label_asym_id'] in labels]
            selected_residues = [r for r in mapping if r['label_asym_id'] in labels]
            structure_id = f'{pdb.lower()}-assembly-{assembly_id}'
            artifact_id = f'{structure_id}-mmcif'
            service_keys = ('model_number', 'label_asym_id', 'auth_asym_id', 'label_seq_id',
                            'auth_seq_id', 'insertion_code', 'sequence_position', 'has_coordinates')
            structures.append({
                'structure_id': structure_id, 'candidate_id': CANDIDATES[pdb], 'artifact_id': artifact_id,
                'kind': 'experimental', 'source': source(pdb), 'model_number': 1, 'assembly_id': assembly_id,
                'chain_mapping': [{'role': r['role'], 'model_number': 1, 'label_asym_id': r['label_asym_id'],
                                   'auth_asym_id': r['auth_asym_id'], 'operator_id': '1'} for r in selected_chains],
                'residue_mapping': [{**{key: r[key] for key in service_keys}, 'operator_id': '1'}
                                    for r in selected_residues], 'alignment': None,
            })
            artifacts.append({'artifact_id': artifact_id, 'role': 'structure', 'format': 'mmcif', 'status': 'ready',
                              'file_name': path.name, 'size_bytes': path.stat().st_size, 'sha256': digest(path), 'reason': None})
            files.append({'artifact_id': artifact_id, 'repository_path': path.relative_to(ROOT).as_posix()})
            assemblies.append({'assembly_id': assembly_id, 'label_asym_ids': labels, 'operator_id': '1',
                               'operator_is_identity': True, 'atom_count': len(assembly_atoms),
                               'primary_for_contract_example': assembly_id == '1',
                               'coordinate_unit': 'angstrom', 'superposition_applied': False})
            if assembly_id == '1':
                uploads.append({'upload_key': f'structure_{pdb.lower()}', 'file_name': path.name, 'format': 'mmcif',
                                'candidate_id': CANDIDATES[pdb], 'role': 'complex', 'source': source(pdb)})
        entry_summaries.append({
            'pdb_id': pdb, 'title': cif['_struct.title'][0], 'method': cif['_exptl.method'][0],
            'resolution_angstrom': float(cif['_refine.ls_d_res_high'][0]),
            'asu_atom_count': len(atoms), 'deposited_polymer_residues': sum(r['sequence_length'] or 0 for r in chains),
            'observed_polymer_residues': sum(r['has_coordinates'] for r in mapping if r['label_seq_id'] is not None),
            'missing_polymer_residues': sum(not r['has_coordinates'] for r in mapping),
            'assemblies': assemblies, 'glycan_covalent_links': glycan_links,
            'target_reference_annotations': [r for r in rows(cif, '_struct_ref_seq') if r['pdbx_db_accession'] == 'P04626'],
            'revision_history': rows(cif, '_pdbx_audit_revision_history'),
            'zero_occupancy_atoms': sum(float(a['occupancy']) == 0 for a in atoms),
        })
    review_input = {
        'schema_version': '0.1.0', 'example_id': None, 'public_data_confirmed': True,
        'target': {'identifier': 'UniProt:P04626', 'fasta': canonical_fasta,
                   'analysis_range': {'start': 23, 'end': 629},
                   'sources': [{'title': 'UniProtKB P04626', 'url': 'https://www.uniprot.org/uniprotkb/P04626/entry',
                                'record_id': 'P04626'}]},
        'candidates': candidates, 'uploads': uploads,
    }
    schema = json.loads((ROOT / 'docs/frontend-hosting/contracts/service.schema.json').read_text(encoding='utf-8'))
    for definition, values in [('ReviewInput', [review_input]), ('Structure', structures), ('Artifact', artifacts)]:
        validator = Draft202012Validator({**schema, '$ref': f'#/$defs/{definition}'}, format_checker=FormatChecker())
        for value in values:
            validator.validate(value)
    write_json('review-input.json', review_input)
    write_json('structures.json', structures)
    write_json('artifacts.json', artifacts)
    write_json('chain-mapping.json', all_chains)
    write_csv('residue-mapping.csv', all_residues)
    write_csv('chain-mapping.csv', [{**r, 'missing_label_ranges': json.dumps(r['missing_label_ranges']),
                                   'insertion_residues': json.dumps(r['insertion_residues']),
                                   'uniprot_ranges': json.dumps(r['uniprot_ranges']), 'components': json.dumps(r['components'])}
                                  for r in all_chains])
    (OUT / 'deposited-sequences.fasta').write_text(''.join(sequence_records), encoding='utf-8', newline='\n')
    write_json('summary.json', {
        'task': 'A-01', 'status': 'technical_input_audit_passed_team_review_pending',
        'source_retrieved_at': lock['retrieved_at'], 'coordinate_unit': 'angstrom',
        'uniprot_length': len(canonical), 'entries': entry_summaries,
        'checks': {'source_hashes': 'PASS', 'sequence_table_agreement': 'PASS', 'uniprot_sequence_agreement': 'PASS',
                   'missing_annotation_agreement': 'PASS', 'all_atoms_accounted_for': 'PASS',
                   'assembly_coordinate_agreement': 'PASS', 'service_schema_fragments': 'PASS'},
        'not_validated': ['Q04 final demo selection and general input limits', 'G1 producer-consumer review', '3D viewer residue selection',
                          'A-02 contact/clash/SASA/alignment metrics', 'full glycan/cell environment', 'clinical efficacy'],
        'runtime': {'python': platform.python_version(), 'biopython': version('biopython'), 'jsonschema': version('jsonschema')},
    })
    write_json('bundle.json', {
        'bundle_version': 'a01-2', 'purpose': 'public_reference_input_audit', 'final_demo_selection': False,
        'coordinate_unit': 'angstrom', 'files': files,
        'input': 'review-input.json', 'structures': 'structures.json', 'artifacts': 'artifacts.json',
        'residue_mapping': 'residue-mapping.csv', 'source_lock': '../source-lock.json',
        'sequence_position_basis': {'target': 'full UniProt P04626 FASTA', 'heavy_light': 'deposited entity FASTA',
                                    'nonpolymer': None},
        'analysis_ranges_approved': True,
        'approval_scope': 'User-approved first public-structure analysis on 2026-09-26; team consumer confirmation pending',
        'metrics_state': 'not_run', 'alignment': None,
        'assembly_choice': 'Assembly 1 approved for first analysis; 1S78 assembly 2 retained as alternate, not an extra candidate',
    })
    print(json.dumps({'status': 'PASS', 'polymer_chains': sum(r['sequence_length'] is not None for r in all_chains),
                      'mapping_rows': len(all_residues), 'assemblies': len(structures),
                      'missing_polymer_residues': sum(not r['has_coordinates'] for r in all_residues),
                      'summary': str(OUT / 'summary.json')}))


if __name__ == '__main__':
    main()
