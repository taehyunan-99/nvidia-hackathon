"""테스트 전역 기본값.

logic.flow.run은 인계 이후 기본 모드가 nat이다. `service/tests`·`logic/tests`
(pyproject.toml의 testpaths) 양쪽 모두 대부분의 테스트가 규칙 경로 검증이
목적이고 NAT(실제 Nemotron 호출)와는 무관하므로, 이 fixture가 매 테스트마다
환경변수 LOGIC_AGENT_MODE를 rule로 무조건 고정해 테스트를 환경(NAT 설치
여부, API 키)과 독립적으로 유지한다. 이 파일이 저장소 루트에 있어야 두
testpaths 모두에 적용된다 — `logic/tests/`에만 두면 `service/tests/`는
적용받지 못하고, nat이 설치된 환경에서 `LOGIC_AGENT_MODE`를 지정하지 않은
service 테스트가 실제 Nemotron을 호출하게 된다. nat 경로를 직접 확인해야
하는 테스트(logic/tests/test_nat_agent.py)는 이 fixture가 이미 설정한 값을
자체적으로 monkeypatch.setenv("LOGIC_AGENT_MODE", "nat") 등으로 덮어쓴다.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_rule_mode(monkeypatch):
    monkeypatch.setenv("LOGIC_AGENT_MODE", "rule")
