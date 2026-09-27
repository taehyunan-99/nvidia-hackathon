import gemmi
import numpy as np
import pytest

from logic.pose_analysis import compare
from logic.tests.test_flow import _boltz2_cif

SEQUENCES = {'target': 'ACDE', 'heavy': 'FGHI', 'light': 'KLMN'}


def coordinates(rotation=None, translation=None, antibody_shift=0):
    block = gemmi.cif.read_string(_boltz2_cif(list(zip('ABC', SEQUENCES.values())))).sole_block()
    atoms = block.find('_atom_site.', ['label_asym_id', 'label_seq_id', 'Cartn_x', 'Cartn_y', 'Cartn_z'])
    tetrahedron = np.array([[0, 0, 0], [3, 0, 0], [0, 4, 0], [0, 0, 5]])
    for r in atoms:
        point = tetrahedron[int(r[1])-1].astype(float) + (ord(r[0])-ord('A')) * 10
        if r[0] != 'A':
            point[0] += antibody_shift
        if rotation is not None:
            point = point @ rotation + translation
        for i in range(3):
            r[i+2] = str(point[i])
    return block.as_string()


def test_global_rigid_motion_does_not_change_antibody_pose():
    rotation = np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1]])
    result = compare(coordinates(), coordinates(rotation, np.array([12, -3, 7])), SEQUENCES)
    assert result['antibody_ca_rmsd'] == pytest.approx(0, abs=1e-10)
    assert result['target_ca_rmsd'] == pytest.approx(0, abs=1e-10)
    assert result['target_ca_count'] == 4 and result['antibody_ca_count'] == 8


def test_antibody_only_displacement_has_known_distance():
    result = compare(coordinates(), coordinates(antibody_shift=5), SEQUENCES)
    assert result['antibody_ca_rmsd'] == pytest.approx(5)
    assert result['target_ca_rmsd'] == pytest.approx(0, abs=1e-10)


def test_degenerate_alignment_and_wrong_sequence_are_rejected():
    line = _boltz2_cif(list(zip('ABC', SEQUENCES.values())))
    with pytest.raises(ValueError, match='퇴화'):
        compare(line, line, SEQUENCES)
    with pytest.raises(ValueError, match='서열'):
        compare(coordinates(), coordinates(), {**SEQUENCES, 'heavy': 'YYYY'})


def test_both_valid_samples_are_saved_with_alignment_and_private_artifacts(tmp_path):
    from logic.flow import Flow
    from logic.tests.test_flow import make_request, candidate, StubClient
    from service.live import verified_files
    c = candidate('candidate', 'Synthetic geometry', SEQUENCES['heavy'], SEQUENCES['light'])
    flow = Flow(make_request([c, {**c, 'candidate_id': 'other'}], tmp_path, target_fasta=SEQUENCES['target']), client=StubClient())
    response = {'structures': [{'format': 'mmcif', 'structure': coordinates()},
                              {'format': 'mmcif', 'structure': coordinates(antibody_shift=5)}], 'confidence_scores': [.8, .7]}
    sid = flow._record_predicted('candidate', response, SEQUENCES)
    assert len(flow.structures) == len(flow.artifacts) == 2
    second = flow.structures[1]
    assert second['alignment']['reference_structure_id'] == sid
    assert second['alignment']['applied'] is False
    pose = next(e for e in flow.evidence if e['topic'] == 'pose_consistency')
    assert pose['value'] == pytest.approx(5)
    assert pose['structure_id'] == second['structure_id']
    assert len(verified_files({'result': {'artifacts': flow.artifacts, 'structures': flow.structures}, 'files': []}, tmp_path)) == 2


def test_invalid_second_sample_cannot_become_a_ready_artifact(tmp_path):
    from logic.flow import Flow
    from logic.tests.test_flow import make_request, candidate, StubClient
    c = candidate('candidate', 'Synthetic geometry', SEQUENCES['heavy'], SEQUENCES['light'])
    flow = Flow(make_request([c, {**c, 'candidate_id': 'other'}], tmp_path, target_fasta=SEQUENCES['target']), client=StubClient())
    flow._record_predicted('candidate', {'structures': [{'structure': coordinates()}, {'structure': 'invalid'}],
                                         'confidence_scores': [.8, .7]}, SEQUENCES)
    assert len(flow.artifacts) == 1
    assert next(e for e in flow.evidence if e['topic'] == 'pose_consistency')['measurement_state'] == 'failed'
