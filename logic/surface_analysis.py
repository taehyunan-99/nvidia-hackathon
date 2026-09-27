"""The same coordinate-based surface calculation for experimental and predicted structures.

No PDB/candidate allowlist or stored measurement lookup. A-02's geometry is reused;
unsupported coordinate conditions are withheld for either source kind.
"""
import copy
import importlib.util
import math
import sys
from functools import lru_cache

import gemmi

from .contract import REPO_ROOT
from .structures import normalize_sequence

POINTS = 960
METRICS_PATH = REPO_ROOT / 'docs/topics/her2/assets/a02/metrics.py'
spec = importlib.util.spec_from_file_location('her2_geometry', METRICS_PATH)
geometry = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = geometry
spec.loader.exec_module(geometry)


def rows(block, category):
    table = block.find_mmcif_category(category + '.')
    names = [tag.split('.', 1)[1] for tag in table.tags]
    return [dict(zip(names, row)) for row in table]


def calculate(text: str, mapping: list[dict], sequences: dict[str, str]) -> dict:
    roles = tuple((role, next((m['label_asym_id'] for m in mapping if m['role'] == role), None),
                   normalize_sequence(sequences[role])) for role in ('target', 'heavy', 'light'))
    return copy.deepcopy(_calculate(text, roles))


@lru_cache(maxsize=16)
def _calculate(text, roles):
    result = {'core': None, 'context': None, 'context_chains': [], 'residues': [], 'gaps': [], 'context_reason': None}
    try:
        block = gemmi.cif.read_string(text).sole_block()
        raw = rows(block, '_atom_site')
        seqs = {r['entity_id']: normalize_sequence(gemmi.cif.as_string(r['pdbx_seq_one_letter_code_can']))
                for r in rows(block, '_entity_poly')}
        atoms, target, antibody, ranges = [], [], [], {}
        if len({chain for _, chain, _ in roles}) != 3 or any(not chain or not seq for _, chain, seq in roles):
            raise ValueError('표적·중쇄·경쇄의 유일한 서열 대응이 필요하다.')
        for role, chain, expected in roles:
            selected = [r for r in raw if r['label_asym_id'] == chain and r['pdbx_PDB_model_num'] == '1']
            entities = {r['label_entity_id'] for r in selected}
            source_sequence = seqs.get(next(iter(entities)), '') if len(entities) == 1 else ''
            offset = source_sequence.find(expected)
            if offset < 0 or source_sequence.find(expected, offset + 1) != -1:
                raise ValueError(f'{role} 좌표와 입력 서열의 대응을 확인하지 못했다.')
            ranges[chain] = (offset + 1, offset + len(expected))
            coords, observed = [], set()
            for r in selected:
                n = int(r['label_seq_id'])
                if not offset < n <= offset + len(expected) or r['type_symbol'] in {'H', 'D'}:
                    continue
                if n < 1 or float(r['occupancy']) != 1 or r['label_alt_id'] not in {'.', '?'}:
                    raise ValueError('부분 점유율·대체 좌표·잘못된 잔기 번호는 자동 선택하지 않는다.')
                if gemmi.find_tabulated_residue(r['label_comp_id']).one_letter_code.upper() != expected[n - offset - 1]:
                    raise ValueError('좌표의 잔기 종류가 입력 서열과 다르다.')
                coords.append(geometry.Coordinate(chain, n, r['label_atom_id'], r['type_symbol'],
                                                  tuple(float(r[f'Cartn_{a}']) for a in 'xyz')))
                observed.add(n - offset)
            if not coords:
                raise ValueError(f'{role}의 관측 중원자가 없다.')
            geometry.validate_atoms(coords)
            atoms.extend(coords)
            (target if role == 'target' else antibody).extend(coords)
            result['gaps'].append(f'{role}: 입력 {len(expected)}잔기 중 좌표 없는 잔기 {len(expected)-len(observed)}개. 미관측 원자는 복원하지 않았다.')
            result['residues'].extend({'model_number': 1, 'label_asym_id': chain, 'auth_asym_id': None,
                'label_seq_id': n + offset, 'auth_seq_id': None, 'insertion_code': None, 'sequence_position': n,
                'has_coordinates': n in observed, 'operator_id': None} for n in range(1, len(expected) + 1))
        surface = geometry.surface(target, antibody, POINTS)
        result['core'] = {'surface_exposure': surface['complex_sasa'], 'buried_sasa_sum': surface['buried_sasa_sum']}
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        result['reason'] = f'표면 계산 보류: {exc}'
        return result

    # Review only observed NAG attached to these selected protein chains. Other glycans
    # or unverified linkage/occupancy stay unknown equally for public and new candidates.
    try:
        sugars = {r['id'] for r in rows(block, '_chem_comp') if 'saccharide' in r['type'].lower()}
        sugar_chains = {r['label_asym_id'] for r in raw if r['label_comp_id'] in sugars}
        links = [r for r in rows(block, '_struct_conn') if r['conn_type_id'] == 'covale']
        links = [link for link in links if all(
            link[f'ptnr{i}_label_asym_id'] not in ranges or
            (link[f'ptnr{i}_label_seq_id'].isdigit() and
             ranges[link[f'ptnr{i}_label_asym_id']][0] <= int(link[f'ptnr{i}_label_seq_id']) <= ranges[link[f'ptnr{i}_label_asym_id']][1])
            for i in (1, 2))]
        connected = {chain for _, chain, _ in roles}
        changed = True
        while changed:
            before = set(connected)
            for link in links:
                a, b = link['ptnr1_label_asym_id'], link['ptnr2_label_asym_id']
                if a in connected and b in sugar_chains:
                    connected.add(b)
                if b in connected and a in sugar_chains:
                    connected.add(a)
            changed = connected != before
        context_chains = connected & sugar_chains
        context_raw = [r for r in raw if r['label_asym_id'] in context_chains and r['pdbx_PDB_model_num'] == '1']
        if not context_raw:
            raise ValueError('입력 단백질에 연결된 관측 당과 공유결합 주석이 없어 당 영향을 판단하지 않았다.')
        for link in links:
            if not {link['ptnr1_label_asym_id'], link['ptnr2_label_asym_id']} & context_chains:
                continue
            if not {link['ptnr1_label_asym_id'], link['ptnr2_label_asym_id']} <= connected:
                raise ValueError('선택한 단백질 밖으로 연결된 당은 자동 포함하지 않는다.')
            endpoints = []
            for partner in (1, 2):
                prefix = f'ptnr{partner}_'
                if link[prefix + 'symmetry'] != '1_555':
                    raise ValueError('다른 대칭 복사체의 당은 자동 포함하지 않는다.')
                if link.get(f'pdbx_ptnr{partner}_label_alt_id', '.') not in {'.', '?'}:
                    raise ValueError('공유결합 주석의 대체 좌표를 자동 선택하지 않는다.')
                found = [r for r in raw if r['pdbx_PDB_model_num'] == '1' and
                         all(r[k] == link[prefix + k] for k in ('label_asym_id', 'label_seq_id', 'label_atom_id', 'label_comp_id', 'auth_asym_id', 'auth_seq_id'))
                         and (r.get('pdbx_PDB_ins_code', '?') == link.get(f'pdbx_ptnr{partner}_PDB_ins_code', '?')
                              or {r.get('pdbx_PDB_ins_code', '?'), link.get(f'pdbx_ptnr{partner}_PDB_ins_code', '?')} <= {'.', '?'})]
                if len(found) != 1:
                    raise ValueError('공유결합 원자의 대응이 유일하지 않다.')
                endpoints.append(found[0])
            distance = math.dist([float(endpoints[0][f'Cartn_{a}']) for a in 'xyz'],
                                 [float(endpoints[1][f'Cartn_{a}']) for a in 'xyz'])
            if abs(distance - float(link['pdbx_dist_value'])) > 0.002:
                raise ValueError('공유결합 주석과 좌표 거리가 일치하지 않는다.')
        context, identities = [], {}
        for r in context_raw:
            if r['type_symbol'] in {'H', 'D'}:
                continue
            if r['label_comp_id'] != 'NAG' or float(r['occupancy']) != 1 or r['label_alt_id'] not in {'.', '?'}:
                raise ValueError('미검증 당 종류·부분 점유율·대체 좌표는 계산하지 않는다.')
            key = (r['label_asym_id'], r['auth_seq_id'], r.get('pdbx_PDB_ins_code'), r['label_comp_id'])
            identities.setdefault(key, len(identities) + 1)
            context.append(geometry.Coordinate(r['label_asym_id'], identities[key], r['label_atom_id'], r['type_symbol'],
                                               tuple(float(r[f'Cartn_{a}']) for a in 'xyz')))
        together = geometry.sasa(atoms + context, POINTS)
        protein_keys = {a.residue_key for a in atoms}
        surrounded = sum(together[k] for k in protein_keys)
        reduction = surface['complex_sasa'] - surrounded
        if reduction < -1e-8:
            raise ValueError('관측 당을 추가한 뒤 표면적이 증가해 검산이 필요하다.')
        result['context'] = {'surface_exposure': surrounded, 'observed_glycan_protein_sasa_reduction': reduction}
        result['context_chains'] = sorted(context_chains)
    except (ValueError, RuntimeError, KeyError, TypeError) as exc:
        result['context_reason'] = f'당 포함 비교 보류: {exc}'
    return result
