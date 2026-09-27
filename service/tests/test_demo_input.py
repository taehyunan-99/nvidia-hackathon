"""The website input must retain its source identity and useful measured evidence."""
import copy
import json
from pathlib import Path

import pytest

from logic.contract import validate
from logic.flow import run_flow
from logic.nvidia_client import CallFailed
from logic.structures import normalize_sequence
from logic.tests.test_flow import StubClient, make_request
from service.demo_input import public_reference_demo

INPUT_PATH = Path(__file__).resolve().parents[2] / 'docs/frontend-hosting/fixtures/public-reference-input.json'


def test_shipped_input_matches_public_sources():
    data = json.loads(INPUT_PATH.read_text())
    validate(data, 'ReviewInput')
    assert data == public_reference_demo(), 'Regenerate the website input after public-source changes'
    assert data['example_id'] == 'her2-public-reference-v1'
    assert len(data['target']['fasta'].split('\n')[1]) == 607
    reference = INPUT_PATH.parents[2] / 'topics/her2/assets/a01/generated/review-input.json'
    full_target = json.loads(reference.read_text())['target']['fasta']
    assert normalize_sequence(data['target']['fasta']) == normalize_sequence(full_target)[22:629]


def test_website_input_produces_contacts_and_honest_limits(tmp_path):
    data = json.loads(INPUT_PATH.read_text())
    request = make_request(data['candidates'], tmp_path)
    request['input'] = data
    client = StubClient()
    output, flow = run_flow(request, client=client)
    assert flow.run_status() == 'completed'
    assert client.calls == 0
    result = output['result']
    for cid, count in [('trastuzumab', 39), ('pertuzumab', 56)]:
        evidence = [e for e in result['evidence'] if e['candidate_id'] == cid]
        contact = next(e for e in evidence if e['topic'] == 'interface_contact_residues')
        assert contact['measurement_state'] == 'measured'
        assert contact['value'] == count and len(contact['residues']) == count
        assert contact['sources']
        for topic in ['atom_clash']:
            item = next(e for e in evidence if e['topic'] == topic)
            assert item['value'] is None and item['measurement_state'] == 'not_run'
        opinion = next(o for o in result['opinions'] if o['candidate_id'] == cid)
        assert opinion['evidence_ids'] and opinion['limitations'] and opinion['follow_up_questions']
    assert len(result['structures']) == 2
    assert all(c['gaps'] for c in result['conditions'] if c['kind'] == 'context')


@pytest.mark.parametrize('kind', ['short', 'invalid', 'mismatch'])
def test_synthetic_negative_inputs_do_not_inherit_reference_evidence(tmp_path, kind):
    data = copy.deepcopy(public_reference_demo())
    data['example_id'] = None
    candidate = data['candidates'][1]
    candidate['name'] = f'Synthetic {kind} test'
    candidate['sources'] = []
    candidate['heavy_chain_fasta'] = {'short': 'ACDE', 'invalid': 'ACDE123', 'mismatch': data['candidates'][0]['heavy_chain_fasta']}[kind]
    request = make_request(data['candidates'], tmp_path)
    request['input'] = data
    client = StubClient(error=CallFailed('Synthetic prediction failure'))
    output, flow = run_flow(request, client=client)
    assert flow.run_status() != 'completed'
    assert not any(e['candidate_id'] == 'pertuzumab' and e['measurement_state'] == 'measured' for e in output['result']['evidence'])
    assert any(e['candidate_id'] == 'trastuzumab' and e['measurement_state'] == 'measured' for e in output['result']['evidence'])
    assert client.calls == (1 if kind == 'mismatch' else 0)
