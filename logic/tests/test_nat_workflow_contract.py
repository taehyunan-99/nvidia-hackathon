"""Real NAT graph and tools, with only the remote model/structure responses replaced."""
import copy
import json

import pytest
from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGenerationChunk

from logic import nat_agent, nat_model
from logic.agent_session import allowed_tools
from logic.flow import run_flow
from logic.tests.test_flow import CoordinateClient, make_request
from service.demo_input import prediction_demo


@pytest.mark.parametrize('repeat_rejection', [False, True])
def test_actual_nat_graph_enforces_current_contract_and_bounded_recovery(tmp_path, monkeypatch, repeat_rejection):
    monkeypatch.setenv('LOGIC_AGENT_MODE', 'nat')
    monkeypatch.setenv('NVIDIA_API_KEY', 'nvapi-offline-test')
    monkeypatch.setenv('MODEL_BUDGET_PATH', str(tmp_path / 'budget.sqlite3'))
    observed = []

    async def pace(_):
        pass

    async def stream(self, messages, **kwargs):
        tools = nat_agent._CURRENT.get()
        offered = {t['function']['name']: t['function'] for t in kwargs['tools']}
        assert set(offered) == allowed_tools(tools.s)
        assert kwargs['tool_choice'] == 'required'
        observed.append((copy.deepcopy(kwargs['tools']), list(messages)))
        i = len(observed) - 1
        if i == 0:
            name, args = 'lookup_public_structure', {}
        elif i in (1, 2):
            name = 'predict_structure'
            reason = ('새로 만든 수치 9999를 사용한다.' if i == 1 or repeat_rejection else
                      offered[name]['parameters']['properties']['reason']['enum'][0])
            args = {'reason': reason}
            if i == 2:
                assert any(isinstance(m, ToolMessage) and '9999' in m.content and '거부:' in m.content for m in messages)
        elif i == 3:
            name, args = 'compare_structure', {}
        elif i == 4:
            name = 'submit_opinion'
            properties = offered[name]['parameters']['properties']
            assert properties['decision']['enum'] == ['needs_confirmation']
            args = {'decision': 'needs_confirmation', 'reason': properties['reason']['enum'][0]}
        else:
            raise AssertionError('The model was called after completion or repeated rejection')
        yield ChatGenerationChunk(message=AIMessageChunk(content='', tool_call_chunks=[{
            'name': name, 'args': json.dumps(args), 'id': f'call-{i}', 'index': 0}]))

    monkeypatch.setattr(nat_model, '_pace', pace)
    monkeypatch.setattr(nat_model.ChatNVIDIA, '_astream', stream)
    data = prediction_demo()
    data['candidates'][0]['heavy_chain_fasta'] = '123'  # code-only rejected control
    client = CoordinateClient()
    output, flow = run_flow(make_request(data['candidates'], tmp_path / 'run'), client=client)
    assert client.calls == 1
    assert len(observed) == (3 if repeat_rejection else 5)
    if repeat_rejection:
        assert '두 번 거부' in flow.rule_finishes['pertuzumab-variant']
        assert any('진행: 규칙' in o['reason'] for o in output['result']['opinions'])
    else:
        assert not flow.rule_finishes and not flow.agent_errors
        assert flow.agent_traces['pertuzumab-variant'][-1]['tool'] == 'submit_opinion'
        assert flow.agent_traces['pertuzumab-variant'][-1]['accepted']


def test_request_schemas_do_not_mutate_shared_nat_definitions(tmp_path):
    from logic.tests.test_agent_session import _setup, _trastuzumab
    _, _, _, tools = _setup(tmp_path, _trastuzumab())
    schemas = [{'type': 'function', 'function': {'name': name, 'parameters': {'properties': {
        'reason': {'type': 'string'}, 'decision': {'type': 'string'}}}}}
        for name in ['check_input', 'lookup_public_structure', 'use_experimental_structure',
                     'predict_structure', 'compare_structure', 'submit_opinion', 'hold_candidate']]
    original = copy.deepcopy(schemas)
    assert [s['function']['name'] for s in tools.model_tool_schemas(schemas)] == ['check_input']
    tools.check_input(); tools.lookup_public_structure(); tools.use_experimental_structure('서열이 일치한다.')
    tools.compare_structure()
    constrained = tools.model_tool_schemas(schemas)
    assert constrained[0]['function']['parameters']['properties']['decision']['enum'] == ['needs_confirmation']
    assert schemas == original
