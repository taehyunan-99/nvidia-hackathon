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
    def _post(self, url: str, payload: dict[str, Any], kind: str, summary: dict[str, Any]) -> dict[str, Any]:
        key = self.require_key()
        headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        started = time.monotonic()
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            elapsed = time.monotonic() - started
            self._record(CallRecord(kind, url, None, elapsed, False, summary, str(exc)))
            raise CallFailed(f"{kind} 호출이 전송 단계에서 실패했다: {exc}", elapsed_s=elapsed) from exc
        elapsed = time.monotonic() - started
        if response.status_code != 200:
            body = response.text[:500]
            self._record(
                CallRecord(kind, url, response.status_code, elapsed, False, summary, body)
            )
            raise CallFailed(
                f"{kind} 호출이 HTTP {response.status_code}로 실패했다: {body}",
                status=response.status_code,
                elapsed_s=elapsed,
            )
        self._record(CallRecord(kind, url, 200, elapsed, True, summary))
        return response.json()

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
        return self._post(f"{LLM_BASE}/chat/completions", payload, "nemotron.chat", summary)

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
