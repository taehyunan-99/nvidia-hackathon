from pathlib import Path
import shutil

import pytest

from logic import runtime_skill
from logic.tests.test_agent_session import _setup, _trastuzumab, _variant
from logic.nvidia_client import CallFailed


def test_pinned_skill_is_loaded_and_modified_files_are_rejected(tmp_path, monkeypatch):
    text = runtime_skill.load_boltz_skill()
    assert 'Boltz2 NIM' in text and 'Response Checks' in text
    root = tmp_path / 'skill'
    shutil.copytree(runtime_skill.ROOT, root)
    monkeypatch.setattr(runtime_skill, 'ROOT', root)
    (root / 'SKILL.md').write_text('changed')
    with pytest.raises(ValueError, match='해시'):
        runtime_skill.load_boltz_skill()


def test_public_structure_records_reason_for_skipping_skill_without_prediction(tmp_path):
    client, flow, _, tools = _setup(tmp_path, _trastuzumab())
    events = []; flow._progress = events.append
    tools.check_input(); tools.lookup_public_structure()
    tools.use_experimental_structure('공개 구조가 두 사슬 모두 일치한다.')
    selected = [e['activity'] for e in events if e['activity']['kind'] == 'skill']
    assert selected[-1]['phase'] == 'skipped'
    assert selected[-1]['reason'] == '공개 구조가 두 사슬 모두 일치한다.'
    assert selected[-1]['skill'] == runtime_skill.identity()
    assert client.predictions == 0


def test_selected_skill_records_call_and_independent_validation_failure(tmp_path):
    client, flow, _, tools = _setup(tmp_path, _variant())
    flow.client.predict_complex = lambda *args, **kwargs: {"structures": [{"structure": "data_x\n#\n"}]}
    events = []; flow._progress = events.append
    tools.check_input(); tools.lookup_public_structure()
    tools.predict_structure('공개 구조가 없어 구조 예측이 필요하다.')
    skill = [e['activity'] for e in events if e['activity']['kind'] == 'skill']
    assert [a['phase'] for a in skill] == ['selected', 'running', 'completed']
    checked = next(e['activity'] for e in events if e['activity']['kind'] == 'verification')
    assert checked['verification']['status'] == 'failed'  # stub is data_x with no atoms
    assert checked['next_action'] == '종료'
    assert any(c['name'] == '좌표 파싱' and c['status'] == 'failed' for c in checked['verification']['checks'])


def test_call_failure_has_no_successful_verification(tmp_path, monkeypatch):
    _, flow, _, tools = _setup(tmp_path, _variant())
    events = []; flow._progress = events.append
    def fail(*args, **kwargs):
        raise CallFailed('test failure')
    monkeypatch.setattr(flow.client, 'predict_complex', fail)
    tools.check_input(); tools.lookup_public_structure()
    tools.predict_structure('공개 구조가 없어 구조 예측이 필요하다.')
    skill = [e['activity'] for e in events if e['activity']['kind'] == 'skill']
    assert [a['phase'] for a in skill] == ['selected', 'running', 'failed']
    assert not any(e['activity']['kind'] == 'verification' for e in events)


def test_unavailable_pinned_skill_holds_without_calling_prediction(tmp_path, monkeypatch):
    client, flow, _, tools = _setup(tmp_path, _variant())
    events = []; flow._progress = events.append
    monkeypatch.setattr(runtime_skill, 'ROOT', tmp_path / 'missing')
    tools.check_input(); tools.lookup_public_structure()
    tools.predict_structure('공개 구조가 없어 구조 예측이 필요하다.')
    assert client.predictions == 0
    assert any(e['activity']['kind'] == 'skill' and e['activity']['phase'] == 'held' for e in events)
    assert not any(e['activity']['kind'] == 'verification' for e in events)


def test_nat_receives_pinned_instructions_before_tool_selection(tmp_path, monkeypatch):
    from contextlib import asynccontextmanager
    from logic import nat_agent
    _, flow, session, _ = _setup(tmp_path, _trastuzumab())
    prompts = []

    class Runner:
        async def result(self, **kwargs):
            session.terminal = 'completed'
            return '검토 종료'

    class Workflow:
        @asynccontextmanager
        async def run(self, prompt):
            prompts.append(prompt)
            yield Runner()

    @asynccontextmanager
    async def workflow(*args):
        yield Workflow()

    monkeypatch.setattr(nat_agent, 'load_workflow', workflow)
    nat_agent.run_candidate(flow, session)
    assert len(prompts) == 1
    assert runtime_skill.REVISION in prompts[0]
    assert '# Boltz2 NIM' in prompts[0] and '# Boltz2 Validation' in prompts[0]
