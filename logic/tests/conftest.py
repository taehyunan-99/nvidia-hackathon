"""테스트 전역 기본값.

logic.flow.run은 인계 이후 기본 모드가 nat이다. 개별 후보 판단 로직을
검증하는 테스트 대부분은 규칙 경로를 확인하는 것이 목적이고 NAT(실제
Nemotron 호출)와는 무관하므로, 환경변수 LOGIC_AGENT_MODE가 없을 때
기본을 rule로 고정해 테스트를 환경(NAT 설치 여부, API 키)과 독립적으로
유지한다. nat 경로를 직접 확인하는 테스트(logic/tests/test_nat_agent.py)는
자체적으로 monkeypatch.setenv("LOGIC_AGENT_MODE", "nat") 등으로 재정의한다.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_rule_mode(monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "rule")
