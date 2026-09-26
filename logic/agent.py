"""분기를 모델이 고르게 하는 판단부 (계획서 B-05).

설계 문서는 "Nemotron은 상태에 따른 작업 선택과 결과 설명을 맡는다"이고,
"단계가 고정 파이프라인이 되지 않게 할 분기"를 따로 절로 두고 있다.
[agent-design.md](../docs/topics/her2/agent-design.md)

그런데 흐름부는 그 분기를 전부 `if`로 박아 두고 모델을 한 번도 부르지
않았다. 이 모듈이 그 자리를 채운다.

경계 — 모델에게 허용하는 것과 허용하지 않는 것을 나눈다.

허용: 주어진 행동 목록 중 하나를 고르는 것, 그리고 고른 이유를 쓰는 것.
불허: 숫자를 만드는 것. 접촉 잔기 수·신뢰도·서열 길이는 전부 코드가
      계산해서 사실로 넣어 준다. 모델은 그 값을 **읽고 고를** 뿐이다.

지키는 방법은 셋이다.
1. 고른 행동이 목록에 없으면 버린다.
2. 설명에 사실 목록에 없는 숫자가 나오면 버린다. 지어낸 것이다.
3. 버렸거나 모델을 못 불렀으면 기존 규칙으로 되돌아가되, 규칙으로
   정했다는 사실과 이유를 결정 기록에 남긴다. 조용히 대체하지 않는다.

실측(2026-09-26): 이 계정에서 부를 수 있는 Nemotron은 사실상 하나다.
`nvidia/nemotron-3-super-120b-a12b`가 6.2초에 답했고,
`nvidia/nemotron-3.5-lightning-30b-a3b`는 60.6초가 걸리고 사고 과정이
답변에 섞여 나왔다. 목록에 보이는 나머지(`nemotron-nano-3-30b-a3b`,
`llama-3.1-nemotron-70b-instruct` 등)는 404였다. 설계 문서가 고른
`nvidia/nemotron-3-nano-30b-a3b`는 목록에 아예 없다.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from .nvidia_client import CallFailed, MissingCredentials, NvidiaClient

# 위 실측에서 유일하게 쓸 만했던 모델. .env의 NEMOTRON_MODEL로 바꿀 수 있다.
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"

# 판단 한 건에 주는 시간. 시연 중 화면이 멈춘 것처럼 보이지 않게 둔다.
DECISION_TIMEOUT = 60

# 숫자로 읽히는 토막. 설명이 사실에 없는 값을 만들어내는지 볼 때 쓴다.
_NUMBER = re.compile(r"\d+(?:\.\d+)?")

# 글자·숫자·하이픈이 이어진 토막. 그 중 글자와 숫자를 모두 포함하는 것만
# "식별자로 보이는 토큰" 후보다("HER2", "Boltz-2", "1N8Z", "92kDa" 등).
# 한글·공백·문장부호가 나오면 토큰이 끊긴다.
_IDENTIFIER_TOKEN = re.compile(r"[A-Za-z0-9-]+")

# 프롬프트(시스템 프롬프트·도구 설명)에 고정으로 등장하는 식별자.
# 사실 텍스트에 그대로 없어도 예외로 인정한다.
PROMPT_IDENTIFIERS = {"HER2", "Boltz-2"}


def _identifier_tokens(text: str) -> set[str]:
    """text 안에서 글자와 숫자를 모두 포함하는 토큰만 뽑는다."""
    tokens = set()
    for m in _IDENTIFIER_TOKEN.finditer(text):
        token = m.group()
        if any(c.isalpha() for c in token) and any(c.isdigit() for c in token):
            tokens.add(token)
    return tokens


def _identifier_spans(text: str, allowed: set[str]) -> list[tuple[int, int]]:
    """text 안에서 allowed에 속하는 식별자 토큰들의 (start, end) 구간."""
    spans = []
    for m in _IDENTIFIER_TOKEN.finditer(text):
        if m.group() in allowed:
            spans.append((m.start(), m.end()))
    return spans

SYSTEM_PROMPT = (
    "너는 항체 후보 검토 실행의 판단부다. 아래 '확인된 사실'만 근거로 "
    "'선택지' 중 정확히 하나를 고른다.\n"
    "규칙:\n"
    "1. 확인된 사실에 없는 수치를 쓰지 마라. 추정치도 안 된다.\n"
    "2. 결합력·치료 효능을 판정하지 마라. 구조상 검토 범위만 말한다.\n"
    "3. JSON 객체 하나만 출력한다. 설명·코드블록·사고 과정을 붙이지 마라.\n"
    '   {"action": "<선택지의 action 중 하나>", "reason": "<두 문장 이내 한국어>"}'
)


@dataclass(frozen=True)
class Option:
    """모델에게 허용하는 행동 하나."""

    action: str
    summary: str


@dataclass(frozen=True)
class Decision:
    """분기 한 번의 결과. 누가 정했는지를 값과 같은 급으로 남긴다."""

    step: str
    action: str
    reason: str
    decided_by: str  # "model" | "rule"
    model: str | None = None
    fallback_reason: str | None = None
    facts: list[str] = field(default_factory=list)

    def to_record(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action,
            "reason": self.reason,
            "decided_by": self.decided_by,
            "model": self.model,
            "fallback_reason": self.fallback_reason,
            "facts": list(self.facts),
        }


def invented_numbers(reason: str, facts: list[str]) -> list[str]:
    """설명에 있지만 사실에는 없는 숫자를 돌려준다.

    모델이 "접촉 잔기 42개"처럼 없는 값을 만들어 오면 여기서 잡는다.

    값으로 비교한다. 사실 쪽 숫자를 문자열로만 모아 두고 대조하면
    "39"와 "39.0"처럼 같은 값의 다른 표기가 서로 달라 보여 오탐이
    난다(`analysis.contact_measurement`가 `value=float(len(residues))`로
    저장해 문장이 "39.0residue"가 되는 경우가 실제로 있었다). 느슨한
    검사이지만 없는 수치를 그대로 보고서에 싣는 것보다 낫다.

    식별자 예외는 "글자 옆 숫자는 전부 봐준다"가 아니라 훨씬 좁다.
    숫자가 "식별자로 보이는 토큰 전체"(글자·숫자·하이픈이 이어지고 글자와
    숫자를 모두 포함하는 덩어리, 예: "HER2", "Boltz-2", "1N8Z")의 일부일
    때만, 그리고 그 토큰이 고정 상수 `PROMPT_IDENTIFIERS`에 있거나 사실
    텍스트에 그 토큰이 통째로 그대로 나타날 때만 예외로 본다. 그 밖의
    글자 옆 숫자("3nM", "KD 5nM", "92kDa", "pLDDT-85", "42residue")는
    전부 값 주장으로 보고 사실의 숫자와 대조한다 — 이전 버전은 "글자
    바로 옆 숫자면 전부 식별자"로 봐서 이런 지어낸 단위 주장을 놓쳤다.

    사실 쪽은 식별자 안에 있는 숫자까지 포함해 전부 모은다. 그래야
    "1N8Z"의 "1"·"8"처럼 식별자 안에 있던 값이 알려진 값 목록에서
    빠지지 않는다(모델이 그 값을 나중에 다시 쓸 수 있다).
    """
    facts_text = "\n".join(facts)
    known = {float(m.group()) for m in _NUMBER.finditer(facts_text)}

    allowed = PROMPT_IDENTIFIERS | _identifier_tokens(facts_text)
    spans = _identifier_spans(reason, allowed)

    invented = []
    for m in _NUMBER.finditer(reason):
        if any(s <= m.start() < e for s, e in spans):
            continue
        if float(m.group()) not in known:
            invented.append(m.group())
    return invented


def parse_choice(text: str, allowed: set[str]) -> tuple[str, str] | None:
    """모델 답에서 (action, reason)을 꺼낸다. 형식이 어긋나면 None."""
    # 코드블록·사고 과정이 섞여 와도 첫 JSON 객체만 본다.
    start = text.find("{")
    while start != -1:
        for end in range(len(text), start, -1):
            if text[end - 1] != "}":
                continue
            try:
                parsed = json.loads(text[start:end])
            except json.JSONDecodeError:
                continue
            if not isinstance(parsed, dict):
                break
            action = parsed.get("action")
            reason = parsed.get("reason")
            if action in allowed and isinstance(reason, str) and reason.strip():
                return action, reason.strip()
            return None
        start = text.find("{", start + 1)
    return None


class Decider:
    """분기마다 모델에게 물어본다. 못 물어보면 규칙으로 간다."""

    def __init__(self, client: NvidiaClient, *, model: str | None = None):
        self.client = client
        self.model = model or os.getenv("NEMOTRON_MODEL") or DEFAULT_MODEL
        self.decisions: list[Decision] = []

    def choose(
        self,
        step: str,
        *,
        question: str,
        facts: list[str],
        options: list[Option],
        default: str,
    ) -> Decision:
        """하나를 고른다. default는 모델을 쓸 수 없을 때의 기존 규칙 결과다."""
        assert any(o.action == default for o in options), "default가 선택지에 없다"
        decision, why = self._ask(step, question, facts, options)
        if decision is None:
            decision = Decision(
                step=step,
                action=default,
                reason="코드에 정해 둔 규칙대로 진행했다.",
                decided_by="rule",
                model=None,
                fallback_reason=why,
                facts=facts,
            )
        self.decisions.append(decision)
        return decision

    # ------------------------------------------------------------ 내부
    def _ask(
        self, step: str, question: str, facts: list[str], options: list[Option]
    ) -> tuple[Decision | None, str | None]:
        """(결정, 못 쓴 이유). 둘 중 하나만 채워진다."""
        prompt = "\n".join(
            [
                f"## 판단할 것\n{question}",
                "\n## 확인된 사실",
                *(f"- {f}" for f in facts),
                "\n## 선택지",
                *(f'- action "{o.action}": {o.summary}' for o in options),
            ]
        )
        try:
            response = self.client.chat(
                self.model,
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=512,
                timeout=DECISION_TIMEOUT,
            )
        except (MissingCredentials, CallFailed) as exc:
            return None, f"모델 호출이 실패했다: {exc}"

        try:
            text = response["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            return None, "모델 응답을 읽을 수 없는 형식이었다."

        picked = parse_choice(text, {o.action for o in options})
        if picked is None:
            return None, "모델이 선택지에 없는 답을 하거나 형식을 지키지 않았다."

        action, reason = picked
        invented = invented_numbers(reason, facts)
        if invented:
            # 고른 행동이 맞더라도 설명을 믿을 수 없으면 통째로 버린다.
            # 반쪽만 쓰면 어디까지가 근거인지 구분할 수 없게 된다.
            return None, (
                f"모델 설명에 근거에 없는 숫자가 있어 쓰지 않았다: {', '.join(invented)}"
            )

        return (
            Decision(
                step=step,
                action=action,
                reason=reason,
                decided_by="model",
                model=self.model,
                facts=facts,
            ),
            None,
        )


class RuleDecider:
    """모델을 부르지 않고 규칙 결과를 기록한다.

    에이전트가 끊긴 뒤 규칙으로 마무리할 때 쓴다. 다시 모델을 부르면
    방금 실패한 호출을 되풀이하게 된다. 끊긴 이유를 결정마다 남긴다.
    """

    def __init__(self, why: str, *, decisions: list[Decision], model: str):
        self.why = why
        self.decisions = decisions
        self.model = model

    def choose(self, step: str, *, question: str, facts: list[str],
               options: list[Option], default: str) -> Decision:
        del question
        assert any(o.action == default for o in options), "default가 선택지에 없다"
        decision = Decision(
            step=step, action=default, reason="코드에 정해 둔 규칙대로 진행했다.",
            decided_by="rule", model=None, fallback_reason=self.why, facts=facts,
        )
        self.decisions.append(decision)
        return decision
