"""Describe paired predictions after target alignment; never score accuracy."""
import gemmi
import numpy as np

from .prediction_validation import validate_prediction


def _coordinates(text, sequences):
    mapping = validate_prediction(text, sequences)
    roles = {m['label_asym_id']: m['role'] for m in mapping}
    atoms = gemmi.cif.read_string(text).sole_block().find('_atom_site.', [
        'label_asym_id', 'label_seq_id', 'label_atom_id', 'Cartn_x', 'Cartn_y', 'Cartn_z', 'pdbx_PDB_model_num'])
    return {(roles[r[0]], int(r[1])): np.array([float(r[i]) for i in (3, 4, 5)])
            for r in atoms if r[0] in roles and r[2] == 'CA' and r[6] == '1'}


def compare(reference: str, mobile: str, sequences: dict) -> dict:
    a, b = _coordinates(reference, sequences), _coordinates(mobile, sequences)
    target = sorted(k for k in a.keys() & b.keys() if k[0] == 'target')
    antibody = sorted(k for k in a.keys() & b.keys() if k[0] in {'heavy', 'light'})
    if len(target) < 3 or not all(any(k[0] == role for k in antibody) for role in ('heavy', 'light')):
        raise ValueError('공통 표적 Cα 3개 이상과 양쪽 항체 사슬의 공통 Cα가 필요하다.')
    x, y = np.array([b[k] for k in target]), np.array([a[k] for k in target])
    cx, cy = x.mean(axis=0), y.mean(axis=0)
    if min(np.linalg.matrix_rank(x-cx), np.linalg.matrix_rank(y-cy)) < 2:
        raise ValueError('표적 정렬 기준점이 퇴화했다.')
    u, _, vt = np.linalg.svd((x-cx).T @ (y-cy))
    correction = np.diag([1, 1, np.linalg.det(u @ vt)])
    rotation = u @ correction @ vt
    translation = cy - cx @ rotation
    rmsd = lambda keys: float(np.sqrt(np.mean([
        np.sum((b[k] @ rotation + translation - a[k]) ** 2) for k in keys])))
    matrix = np.eye(4)
    matrix[:3, :3], matrix[:3, 3] = rotation.T, translation
    return {'antibody_ca_rmsd': rmsd(antibody), 'target_ca_rmsd': rmsd(target),
            'target_ca_count': len(target), 'antibody_ca_count': len(antibody),
            'target_positions': [k[1] for k in target], 'matrix': matrix.ravel().tolist()}
