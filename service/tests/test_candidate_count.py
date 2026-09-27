"""Four candidates share the same input and result contract; a fifth is rejected."""
from copy import deepcopy

import pytest
from fastapi import HTTPException

from logic.contract import validate
from logic.flow import run_flow
from logic.tests.test_flow import StubClient, make_request
from service.demo_input import experimental_demo
from service.operational import _check_input


def four_candidates():
    body = experimental_demo()
    original = body['candidates']
    body['candidates'] = [dict(deepcopy(original[i % 2]), candidate_id=f'candidate-{i+1}', name=f'후보 {i+1}') for i in range(4)]
    return body


def test_four_candidates_are_accepted():
    _check_input(four_candidates())


def test_fifth_candidate_is_rejected():
    body = four_candidates()
    body['candidates'].append(dict(deepcopy(body['candidates'][0]), candidate_id='candidate-5'))
    with pytest.raises(HTTPException) as error:
        _check_input(body)
    assert error.value.status_code == 422


def test_four_candidates_keep_distinct_progress_and_results(tmp_path):
    body = four_candidates()
    client = StubClient()
    output, flow = run_flow(make_request(body['candidates'], tmp_path), client=client)
    validate(output, 'LogicOutput')
    assert output['result']['candidate_ids'] == [c['candidate_id'] for c in body['candidates']]
    assert len(flow.candidate_progress()) == 4
    assert all(c['status'] == 'completed' for c in flow.candidate_progress())
    assert client.calls == 0
