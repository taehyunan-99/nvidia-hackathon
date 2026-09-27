import pytest

from logic.prediction_validation import validate_prediction
from logic.tests.test_flow import _boltz2_cif

SEQUENCES = {'target': 'ACD', 'heavy': 'EFG', 'light': 'HIK'}


def valid_text():
    return _boltz2_cif([('X', 'ACD'), ('Y', 'EFG'), ('Z', 'HIK')])


def test_label_chain_mapping_and_input_identity_are_verified():
    mapping = validate_prediction(valid_text(), SEQUENCES)
    assert [c['label_asym_id'] for c in mapping] == ['X', 'Y', 'Z']


@pytest.mark.parametrize('text', [
    'data_empty\n#\n',
    valid_text().replace('10 3 0 1', 'nan 3 0 1'),
    valid_text().replace('X 1 1 ALA', 'X 1 1 GLY'),
    valid_text().replace('0 1 1 .', '0 1 0.5 .'),
    valid_text().replace('0 1 1 .', '0 1 1 A'),
    _boltz2_cif([('X', 'ACD'), ('Y', 'EFG')]),
    _boltz2_cif([('X', 'ACD'), ('Y', 'EFG'), ('Z', 'HIK'), ('W', 'HIK')]),
])
def test_invalid_or_ambiguous_coordinates_are_rejected(text):
    with pytest.raises(ValueError, match='예측 구조 검증 실패'):
        validate_prediction(text, SEQUENCES)


def test_partial_coordinates_are_preserved_as_missing_not_fabricated():
    from logic.surface_analysis import calculate
    text = valid_text().replace('Z 3 3 LYS C CA 30 9 0 1 1 .\n', '')
    mapping = validate_prediction(text, SEQUENCES)
    result = calculate(text, mapping, SEQUENCES)
    assert result['core'] is not None
    missing = next(r for r in result['residues'] if r['label_asym_id'] == 'Z' and r['label_seq_id'] == 3)
    assert not missing['has_coordinates']
