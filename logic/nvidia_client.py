"""NVIDIA 호스팅 NIM 호출부 (계획서 B-01·B-02).

엔드포인트·요청 형식의 근거는 NVIDIA-BioNeMo/bionemo-agent-toolkit의
nim-skills/boltz2-nim/references/api.md와 build.nvidia.com의 OpenAI 호환 경로다.

이 모듈은 실제 호출만 한다. 키가 없으면 MissingCredentials를 올리고,
응답이 없을 때 그럴듯한 값을 만들어 돌려주지 않는다. 호출 성공·실패와
요청·응답은 work_dir에 그대로 남겨 나중에 대조할 수 있게 한다.

주의: 이 파일의 어떤 함수도 아직 실제 계정으로 검증되지 않았다.
실행 기록이 call_log.jsonl에 남기 전까지 "호출된다"고 보고하지 않는다.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from . import env

LLM_BASE = "https://integrate.api.nvidia.com/v1"
BIO_BASE = "https://health.api.nvidia.com/v1/biology"

DEFAULT_TIMEOUT = 600

# 실측(2026-09-26): Boltz-2는 한도를 넘기면 Retry-After 없이 429를 즉시(0.2초)
# 돌려준다. 동시 20건에서 10건이 막혔고, **순차 호출에서도** 6건 중 2건이
# 막혔다. 시연 중 충분히 밟을 수 있다는 뜻이다.
# 같은 실측에서 9~15초 뒤 재시도는 성공했다. 아래 간격은 그 관측에서 나온
# 값이며 공식 문서에 근거한 값이 아니다. [확인 필요: 공식 한도 수치]
RETRY_STATUS = frozenset({429, 503})
RETRY_WAITS = (5, 10, 20)
MAX_RETRIES = len(RETRY_WAITS)

# 판단 호출은 같은 간격을 쓰면 안 된다. 실측(2026-09-26)에서 Nemotron은
# 예측과 다른 이유로 막힌다 — 한도가 아니라 HTTP 503 "Service temporarily
# overloaded"이고, 잠깐 지나가는 혼잡이다. 위 간격(합 35초)을 그대로 쓰면
# 판단 한 번에 35초가 붙어 후보 2건 실행이 57초에서 105초까지 늘어났다.
# 짧게 여러 번 두드리는 편이 맞다. 합 7초다.
CHAT_RETRY_WAITS = (1, 2, 4)


def _retry_after(response: "requests.Response") -> float | None:
    """서버가 대기 시간을 알려주면 그쪽을 따른다. 실측에서는 없었다."""
    raw = response.headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


class MissingCredentials(RuntimeError):
    """NVIDIA_API_KEY가 없다. 호출을 시도하지 않는다."""


class CallFailed(RuntimeError):
    """호출은 했지만 실패했다. 실패로 기록하고 성공으로 표시하지 않는다."""

    def __init__(self, message: str, *, status: int | None = None, elapsed_s: float = 0.0):
        super().__init__(message)
        self.status = status
        self.elapsed_s = elapsed_s


def read_api_key() -> str | None:
    """`.env`를 먼저 올린 뒤 환경변수에서 찾는다. 값은 로그에 남기지 않는다."""
    key, _ = env.find_key()
    return key


@dataclass
class CallRecord:
    """호출 한 건의 기록. 비밀키는 담지 않는다."""

    kind: str
    url: str
    status: int | None
    elapsed_s: float
    ok: bool
    request_summary: dict[str, Any]
    error: str | None = None


class NvidiaClient:
    """Boltz-2와 Nemotron 호출. work_dir에 요청 요약·응답·소요 시간을 남긴다."""

    def __init__(self, work_dir: Path, *, api_key: str | None = None, timeout: int = DEFAULT_TIMEOUT):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._key = api_key if api_key is not None else read_api_key()
        self.timeout = timeout
        self.records: list[CallRecord] = []

    @property
    def available(self) -> bool:
        return bool(self._key)

    def require_key(self) -> str:
        if not self._key:
            raise MissingCredentials(
                "NVIDIA_API_KEY가 없어 호출하지 않았다. "
                "build.nvidia.com에서 키를 발급해 환경변수로 넣어야 예측 경로를 검증할 수 있다."
            )
        return self._key

    # ------------------------------------------------------------ 공통
    def _post(
        self,
        url: str,
        payload: dict[str, Any],
        kind: str,
        summary: dict[str, Any],
        *,
        timeout: int | None = None,
        waits: tuple[int, ...] = RETRY_WAITS,
    ) -> dict[str, Any]:
        key = self.require_key()
        headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        # 판단 호출은 구조 예측보다 훨씬 짧아야 한다. 기본값(10분)을 그대로
        # 쓰면 모델이 멈췄을 때 시연이 그만큼 멈춘다.
        limit = self.timeout if timeout is None else timeout
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=limit)
            except requests.RequestException as exc:
                elapsed = time.monotonic() - started
                self._record(CallRecord(kind, url, None, elapsed, False, summary, str(exc)))
                raise CallFailed(
                    f"{kind} 호출이 전송 단계에서 실패했다: {exc}", elapsed_s=elapsed
                ) from exc
            elapsed = time.monotonic() - started
            if response.status_code == 200:
                self._record(CallRecord(kind, url, 200, elapsed, True, summary))
                return response.json()

            body = response.text[:500]
            # 429도 실패로 그대로 기록한다. 재시도로 성공했다고 해서 한도를
            # 밟은 사실을 지우면, 나중에 시연이 왜 느렸는지 알 수 없다.
            self._record(
                CallRecord(kind, url, response.status_code, elapsed, False, summary, body)
            )
            if response.status_code in RETRY_STATUS and attempt < len(waits):
                wait = _retry_after(response) or waits[attempt]
                time.sleep(wait)
                attempt += 1
                continue
            raise CallFailed(
                f"{kind} 호출이 HTTP {response.status_code}로 실패했다: {body}",
                status=response.status_code,
                elapsed_s=elapsed,
            )

    def _record(self, record: CallRecord) -> None:
        self.records.append(record)
        log = self.work_dir / "call_log.jsonl"
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------ Boltz-2
    def predict_complex(
        self,
        polymers: list[dict[str, str]],
        *,
        recycling_steps: int = 3,
        sampling_steps: int = 50,
        diffusion_samples: int = 1,
    ) -> dict[str, Any]:
        """HER2 분석 구간과 항체 사슬의 복합체를 예측한다.

        polymers는 [{"id": "A", "molecule_type": "protein", "sequence": "..."}] 형태다.
        반환값은 NVIDIA 응답 원본이다. 여기서 지표를 만들어 넣지 않는다.
        """
        payload = {
            "polymers": polymers,
            "recycling_steps": recycling_steps,
            "sampling_steps": sampling_steps,
            "diffusion_samples": diffusion_samples,
        }
        summary = {
            "polymers": [{"id": p["id"], "length": len(p["sequence"])} for p in polymers],
            "recycling_steps": recycling_steps,
            "sampling_steps": sampling_steps,
            "diffusion_samples": diffusion_samples,
        }
        result = self._post(f"{BIO_BASE}/mit/boltz2/predict", payload, "boltz2.predict", summary)
        (self.work_dir / "boltz2_response.json").write_text(
            json.dumps(_without_structures(result), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result

    # ------------------------------------------------------------ Nemotron
    def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        summary = {"model": model, "messages": len(messages), "tools": len(tools or [])}
        return self._post(
            f"{LLM_BASE}/chat/completions",
            payload,
            "nemotron.chat",
            summary,
            timeout=timeout,
            waits=CHAT_RETRY_WAITS,
        )

    def list_models(self) -> list[str]:
        key = self.require_key()
        started = time.monotonic()
        response = requests.get(
            f"{LLM_BASE}/models", headers={"Authorization": f"Bearer {key}"}, timeout=60
        )
        elapsed = time.monotonic() - started
        ok = response.status_code == 200
        self._record(
            CallRecord(
                "models.list",
                f"{LLM_BASE}/models",
                response.status_code,
                elapsed,
                ok,
                {},
                None if ok else response.text[:500],
            )
        )
        if not ok:
            raise CallFailed(f"모델 목록 조회 실패 HTTP {response.status_code}", status=response.status_code)
        return [m["id"] for m in response.json()["data"]]


def _without_structures(result: dict[str, Any]) -> dict[str, Any]:
    """구조 문자열은 따로 파일로 저장하므로 응답 기록에서는 길이만 남긴다."""
    trimmed = dict(result)
    if isinstance(trimmed.get("structures"), list):
        trimmed["structures"] = [
            {k: (f"<{len(v)} chars>" if k == "structure" and isinstance(v, str) else v)
             for k, v in s.items()}
            for s in trimmed["structures"]
        ]
    return trimmed
