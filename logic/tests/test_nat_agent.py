"""NAT 연결부. 실제 모델은 RUN_LIVE_NAT=1일 때만 부른다."""

from __future__ import annotations

import os

import pytest

from logic import nat_agent
from logic.contract import validate
from logic.flow import run_flow
from logic.tests.test_flow import TRASTUZUMAB, candidate, entity_sequence, make_request
from logic.tests.test_flow_decisions import ScriptedClient, _filler


def _request(tmp_path):
    t = candidate("cand-t", "trastuzumab",
                  entity_sequence(TRASTUZUMAB, "heavy"), entity_sequence(TRASTUZUMAB, "light"))
    return make_request([t, _filler()], tmp_path)


def _opinion_for(output, candidate_id):
    for op in output["result"]["opinions"]:
        if op["candidate_id"] == candidate_id:
            return op
    raise AssertionError(f"no opinion for {candidate_id}")


def test_rule_mode_is_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LOGIC_AGENT_MODE", raising=False)
    called = []
    monkeypatch.setattr(nat_agent, "run_candidate", lambda *a, **k: called.append(1))
    output, _ = run_flow(_request(tmp_path), client=ScriptedClient())
    assert called == []
    validate(output, "LogicOutput")


def test_nat_failure_falls_back_to_rule_with_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    monkeypatch.setattr(nat_agent, "NAT_AVAILABLE", True)
    monkeypatch.setattr(nat_agent, "run_candidate", lambda flow, s, **k: "에이전트 반복 상한")
    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    validate(output, "LogicOutput")
    assert flow.states["cand-t"].status == "completed"
    opinion = _opinion_for(output, "cand-t")
    assert "판단: 규칙 — 에이전트 반복 상한" in opinion["reason"]


def test_missing_nat_falls_back_to_rule(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    monkeypatch.setattr(nat_agent, "NAT_AVAILABLE", False)
    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    validate(output, "LogicOutput")
    opinion = _opinion_for(output, "cand-t")
    assert "NAT를 불러오지 못했다" in opinion["reason"]


def test_workflow_config_loads_with_registered_tools():
    pytest.importorskip("nat")
    from nat.runtime.loader import load_config
    config = load_config(nat_agent.CONFIG_PATH)
    assert set(config.functions) == set(nat_agent.TOOL_NAMES)


@pytest.mark.skipif(os.getenv("RUN_LIVE_NAT") != "1", reason="실제 Nemotron 호출은 RUN_LIVE_NAT=1에서만")
def test_live_agent_reviews_experimental_candidate(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "nat")
    output, flow = run_flow(_request(tmp_path), client=ScriptedClient())
    trace = flow.agent_traces["cand-t"]
    assert trace[0]["tool"] == "check_input"
    assert flow.states["cand-t"].status == "completed"
