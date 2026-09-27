"""NAT streaming NIM transport: bounded 429 recovery and request-level pacing."""
import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import math
import threading
import time

from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from langchain_nvidia_ai_endpoints import ChatNVIDIA, Model
from langchain_nvidia_ai_endpoints._statics import MODEL_TABLE
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.llm import LLMProviderInfo
from nat.cli.register_workflow import register_llm_client, register_llm_provider
from nat.llm.nim_llm import NIMModelConfig
from pydantic import Field

log = logging.getLogger(__name__)
_lock = threading.Lock()
_next_request = 0.0
MAX_ATTEMPTS = 3
MAX_WAIT_SECONDS = 120.0
# 한 회차의 시도 기록. 측정기가 실행 뒤에 가져가 429 복구와 빈 응답을 센다.
_attempts: list[dict] = []


def plan_retry(status, attempt, emitted, retry_after):
    """(전역 대기 초, 재시도 여부). 상한을 넘는 요구는 재시도하지 않는다.

    요구한 대기를 그대로 전역에 심으면 뒤따르는 후보가 기록 한 줄 없이 몇
    시간을 잘 수 있다(서버가 Retry-After를 크게 주는 경우). 그래서 전역
    대기는 MAX_WAIT_SECONDS까지만 심고, 서버가 요구한 값은 로그에 남긴다.
    """
    if status != 429:
        return 0.0, False
    wanted = max(float(30 * 2 ** attempt), retry_after or 0.0)
    retry = not emitted and attempt < MAX_ATTEMPTS - 1 and wanted <= MAX_WAIT_SECONDS
    return (wanted if retry else min(wanted, MAX_WAIT_SECONDS)), retry


def record_attempt(*, status, attempt, emitted, started_at, headers):
    """요청 한 번의 결과를 남기고 그 기록을 돌려준다(로그와 같은 내용)."""
    _attempts.append({"started_at": started_at, "attempt": attempt, "status": status,
                      "emitted": emitted, "headers": headers})
    del _attempts[:-200]
    return _attempts[-1]


def take_attempts():
    """마지막 호출 이후의 시도 기록을 돌려주고 비운다."""
    taken, _attempts[:] = list(_attempts), []
    return taken


async def _pace(interval):
    # ponytail: process-wide budget; multi-worker deployment needs a shared limiter.
    global _next_request
    while True:
        with _lock:
            delay = _next_request - time.monotonic()
            if delay <= 0:
                _next_request = time.monotonic() + interval
                return
        await asyncio.sleep(delay)


def _cooldown(seconds):
    global _next_request
    with _lock:
        _next_request = max(_next_request, time.monotonic() + seconds)


def _retry_after(value):
    try:
        seconds = float(value)
        return max(0.0, seconds) if math.isfinite(seconds) else 0.0
    except (TypeError, ValueError):
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0.0


class PacedNIM(ChatNVIDIA):
    request_interval: float = Field(default=15.0, ge=0, exclude=True)

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        # Nemotron 3 defaults can spend the entire 1024-token response on reasoning,
        # truncating before any tool call. Use its documented direct-response mode.
        kwargs.setdefault('chat_template_kwargs', {'enable_thinking': False})
        from .nat_agent import _CURRENT
        tools = _CURRENT.get(None)
        if tools is not None and tools.s.terminal:
            # Accepted terminal state only: refused submit/hold must still reach the model.
            log.info("nim_terminal_no_request")
            yield ChatGenerationChunk(message=AIMessageChunk(content="검토를 끝냈다."))
            return
        if tools is not None and hasattr(tools, 'model_tool_schemas'):
            kwargs['tools'] = tools.model_tool_schemas(kwargs.get('tools', []))
            kwargs['tool_choice'] = 'required'
            recent = tools.s.calls[-2:]
            if len(recent) == 2 and all(c.get('accepted') is False for c in recent) and \
                    (recent[0].get('tool'), recent[0].get('note')) == (recent[1].get('tool'), recent[1].get('note')):
                from .nvidia_client import CallFailed
                raise CallFailed('동일한 도구 요청이 같은 사유로 두 번 거부되어 추가 모델 호출을 중단했다: '
                                 + str(recent[-1].get('note', ''))[:200])
        for attempt in range(MAX_ATTEMPTS):
            await _pace(self.request_interval)
            if tools is not None and hasattr(tools, 'flow'):
                from .call_budget import reserve
                reserve('nemotron', tools.flow.work_dir)
            started = datetime.now(timezone.utc).isoformat()
            emitted = False
            self._async_client.last_response = None
            try:
                async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
                    emitted = True
                    yield chunk
                return
            except Exception:
                response = self._async_client.last_response
                status = getattr(response, "status", None)
                headers = getattr(response, "headers", {})
                delay, retry = plan_retry(status, attempt, emitted,
                                          _retry_after(headers.get("Retry-After")))
                if delay:
                    _cooldown(delay)
                # Never replay partial output or wait indefinitely for an exhausted quota.
                if not retry:
                    raise
            finally:
                response = self._async_client.last_response
                headers = getattr(response, "headers", {})
                safe_headers = {k: v for k, v in headers.items() if k.lower() in
                                {"retry-after", "x-request-id", "request-id"} or "ratelimit" in k.lower()}
                log.info("nim_http %s", json.dumps(record_attempt(
                    status=getattr(response, "status", None), attempt=attempt + 1,
                    emitted=emitted, started_at=started, headers=safe_headers)))


class PacedNIMConfig(NIMModelConfig, name="her2_paced_nim"):
    request_interval: float = Field(default=15.0, ge=0)


@register_llm_provider(config_type=PacedNIMConfig)
async def _provider(config, _builder):
    yield LLMProviderInfo(config=config, description="HER2 paced NVIDIA NIM")


@register_llm_client(config_type=PacedNIMConfig, wrapper_type=LLMFrameworkEnum.LANGCHAIN)
async def _client(config, _builder):
    # Same model registration used by NAT's NIM adapter; avoids a discovery HTTP call.
    MODEL_TABLE.setdefault(config.model_name, Model(id=config.model_name, model_type="chat", client="ChatNVIDIA"))
    yield PacedNIM(**config.model_dump(exclude={"type", "max_tokens", "thinking", "api_type"},
                                      by_alias=True, exclude_none=True, exclude_unset=True),
                   max_completion_tokens=config.max_tokens)
