"""Validate coordinate identity before a prediction becomes a ready artifact."""
import math

import gemmi

from .structures import normalize_sequence


def validate_prediction(text: str, sequences: dict[str, str]) -> list[dict]:
    try:
        block = gemmi.cif.read_string(text).sole_block()
        polymers = {row[0]: normalize_sequence(gemmi.cif.as_string(row[1]))
                    for row in block.find('_entity_poly.', ['entity_id', 'pdbx_seq_one_letter_code_can'])}
        asym = {row[0]: row[1] for row in block.find('_struct_asym.', ['id', 'entity_id'])}
        rows = list(block.find('_atom_site.', ['label_asym_id', 'label_entity_id', 'label_seq_id',
                        'label_comp_id', 'Cartn_x', 'Cartn_y', 'Cartn_z', 'pdbx_PDB_model_num',
                        'type_symbol', 'label_atom_id', 'occupancy', 'label_alt_id']))
        if not rows:
            raise ValueError('필수 원자 좌표가 없다.')
        # Some providers omit _struct_asym; atom/entity identities still provide label chains.
        for row in rows:
            if row[0] in asym and asym[row[0]] != row[1]:
                raise ValueError('사슬과 entity 대응이 일치하지 않는다.')
            asym[row[0]] = row[1]
        mapping = []
        used = set()
        for role in ('target', 'heavy', 'light'):
            expected = normalize_sequence(sequences.get(role, ''))
            matches = [chain for chain, entity in asym.items() if expected and polymers.get(entity) == expected]
            if len(matches) != 1 or matches[0] in used:
                raise ValueError(f'{role} 서열과 유일한 사슬을 대응시키지 못했다.')
            chain = matches[0]
            used.add(chain)
            atoms = [r for r in rows if r[0] == chain and r[7] == '1']
            if not atoms:
                raise ValueError(f'{role} 사슬의 모델 1 좌표가 없다.')
            identities = set()
            positions = set()
            for atom in atoms:
                position = int(atom[2])
                if not 1 <= position <= len(expected) or not all(math.isfinite(float(atom[i])) for i in (4, 5, 6)):
                    raise ValueError('잔기 번호 또는 좌표가 유효하지 않다.')
                if gemmi.find_tabulated_residue(atom[3]).one_letter_code.upper() != expected[position - 1]:
                    raise ValueError('좌표의 잔기 종류가 입력 서열과 다르다.')
                identity = (position, atom[9])
                if identity in identities or float(atom[10]) != 1 or atom[11] not in {'.', '?'}:
                    raise ValueError('중복 원자·부분 점유율·대체 좌표는 자동 선택하지 않는다.')
                identities.add(identity)
                if atom[8] not in {'H', 'D'}:
                    positions.add(position)
            if not positions:
                raise ValueError(f'{role} 사슬에 검토할 중원자 좌표가 없다.')
            mapping.append({'role': role, 'model_number': 1, 'label_asym_id': chain,
                            'auth_asym_id': None, 'operator_id': None})
        return mapping
    except (ValueError, RuntimeError, IndexError) as exc:
        raise ValueError(f'예측 구조 검증 실패: {exc}') from exc
