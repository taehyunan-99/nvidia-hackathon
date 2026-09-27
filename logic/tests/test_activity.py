"""Public activity follows real tool execution without changing candidate state."""
from copy import deepcopy

import pytest

from logic import nat_agent
from logic.contract import validate
from logic.flow import run_flow
from logic.tests.test_agent_session import _setup, _trastuzumab
from logic.tests.test_nat_agent import _request
from logic.tests.test_flow_decisions import ScriptedClient


def test_tool_events_are_emitted_during_execution_and_refusals_do_not_advance(tmp_path, monkeypatch):
    _, flow, session, tools = _setup(tmp_path, _trastuzumab())
    events = []
    flow._progress = events.append
    before = deepcopy(flow.states[session.cid].steps)
    tools.predict_structure("too early")
    assert flow.states[session.cid].steps == before
    assert events[0]["activity"]["phase"] == "rejected"
    assert not any(e["activity"]["phase"] == "completed" for e in events)
    events.clear()
    original = flow._check_input

    def inspect_in_flight(candidate):
        assert events[0]["activity"]["name"] == "check_input"
        assert events[0]["activity"]["phase"] == "running"
        return original(candidate)

    monkeypatch.setattr(flow, "_check_input", inspect_in_flight)
    tools.actor = "code"
    tools.check_input()
    tools.actor = "agent"
    tools.lookup_public_structure()
    tools.use_experimental_structure("공개 실험 구조가 두 사슬 모두 일치한다.")
    tools.compare_structure()
    tools.submit_opinion("needs_confirmation", "충돌·표면 노출이 미계산이라 확인이 필요하다.")
    assert session.terminal == "completed"
    assert events[-1]["activity"]["name"] == "submit_opinion"
    assert events[-1]["activity"]["phase"] == "completed"
    assert events[0]["activity"]["actor"] == "code"
    assert len({e["activity"]["event_id"] for e in events}) == len(events)
    for event in events:
        validate(event, "ProgressUpdate")
        if event["activity"]["kind"] == "tool":
            assert "reason" not in event["activity"]  # validated decision reasons belong to skill events


def test_tool_exception_emits_failure_without_a_completion(tmp_path, monkeypatch):
    _, flow, _, tools = _setup(tmp_path, _trastuzumab())
    events = []
    flow._progress = events.append
    monkeypatch.setattr(flow, "_check_input", lambda _: (_ for _ in ()).throw(RuntimeError("private detail")))
    with pytest.raises(RuntimeError):
        tools.check_input()
    tool_events = [e["activity"] for e in events if e["activity"]["kind"] == "tool"]
    assert [e["phase"] for e in tool_events] == ["running", "failed"]
    assert "private detail" not in str(events)


def test_nat_unavailable_records_rule_transition_then_actual_stages(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    monkeypatch.setattr(nat_agent, "NAT_AVAILABLE", False)
    events = []
    output, _ = run_flow(_request(tmp_path), client=ScriptedClient(), progress=events.append)
    assert events[0]["activity"]["kind"] == "fallback"
    assert events[0]["activity"]["actor"] == "rule"
    assert any(e["activity"]["kind"] == "stage" and e["step_id"] == "reporting" for e in events)
    assert all(e["activity"]["actor"] == "rule" for e in events if e["activity"]["kind"] == "stage")
    validate(output, "LogicOutput")


def test_tool_options_are_not_reported_as_an_already_selected_action(tmp_path):
    _, flow, _, tools = _setup(tmp_path, _trastuzumab())
    events = []
    flow._progress = events.append
    tools.check_input()
    tools.lookup_public_structure()
    completed = next(e["activity"] for e in events if e["activity"]["name"] == "lookup_public_structure" and e["activity"]["phase"] == "completed")
    assert set(completed["available_tools"]) == {"predict_structure", "use_experimental_structure"}
    assert "next_action" not in completed
    validate(next(e for e in events if e["activity"] is completed), "ProgressUpdate")
