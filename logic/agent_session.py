"""후보 하나의 진행 상태와 에이전트 도구 (NAT 설계 nat-agent-loop.md 4·5절).

NAT에 의존하지 않는다. 규칙 경로(Flow._resume)와 에이전트 도구가 같은
세션을 읽고 쓰므로, 에이전트가 중간에 끊겨도 규칙이 그 자리부터 잇는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .structures import StructureMatch


@dataclass
class CandidateSession:
    candidate: dict[str, Any]
    input_checked: bool = False
    match: StructureMatch | None = None
    lengths: dict[str, int] = field(default_factory=dict)
    structure_id: str | None = None
    compared: bool = False
    terminal: str | None = None  # "completed" | "partial" | "failed"
    calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def cid(self) -> str:
        return self.candidate["candidate_id"]
