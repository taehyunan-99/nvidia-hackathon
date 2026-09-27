"""예선 시연용 최소 운영부.

계획서 S-02의 전체 범위(DB·작업 점유·재접속·worker)가 아니다. 프런트가
실제 분석 결과를 화면에 띄울 수 있게 하는 얇은 층이다. 본선에서 S-02로
키울 때 이 파일을 늘리지 말고 정식 운영부로 옮긴다.

    uvicorn service.app:app --reload --port 8000

경계:
- 분석 판단은 로직 B(`logic/flow.py`)에만 있다. 여기서 지표를 만들지 않는다.
- 실행은 동기다. 실측 12초 기준으로 시연에는 충분하고, 중단·재접속은
  다루지 않는다. 그 책임은 정식 운영부(S-02)의 몫이다.
- 내보내기 전에 계약으로 검증한다. 검증에 실패하면 결과 대신 500을 낸다.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from logic import env
from logic.contract import SCHEMA_VERSION, ContractError, now_rfc3339, validate
from logic.flow import run_flow

from . import demo_input

DATA_MODE = "live"
WORK_ROOT = Path(tempfile.gettempdir()) / "her2-review-runs"

app = FastAPI(title="HER2 후보 검토 — 시연용 운영부", version=SCHEMA_VERSION)
app.add_middleware(
    CORSMiddleware,
    # 개발 중 프런트(vite)만 허용한다. 배포 시 실제 출처로 좁힌다.
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ReviewRequest(BaseModel):
    preset: str | None = Field(
        default=None, description="demo_input.PRESETS의 이름. input을 주면 무시한다."
    )
    input: dict[str, Any] | None = Field(default=None, description="ReviewInput")


@app.get("/api/health")
def health() -> dict[str, Any]:
    """키 상태를 값 노출 없이 알린다. 예측 경로 사용 가능 여부 판단에 쓴다."""
    key, source = env.find_key()
    return {
        "schema_version": SCHEMA_VERSION,
        "data_mode": DATA_MODE,
        "key_present": bool(key),
        "key_source": source,
        "key_summary": env.describe_key(),
        "presets": sorted(demo_input.PRESETS),
    }


@app.get("/api/presets/{name}")
def preset(name: str) -> dict[str, Any]:
    builder = demo_input.PRESETS.get(name)
    if builder is None:
        raise HTTPException(404, f"모르는 preset: {name}")
    review_input = builder()
    validate(review_input, "ReviewInput")
    return review_input


# run_id·artifact_id는 URL에서 온다. 우리가 만든 모양만 받아들인다.
# 느슨하게 두면 ../로 work_dir 밖 파일을 읽어갈 수 있다.
_RUN_ID = re.compile(r"^run-[0-9a-f]{12}$")
_ARTIFACT_ID = re.compile(r"^af-(st-[A-Za-z0-9_-]{1,64})$")


@app.get("/api/runs/{run_id}/artifacts/{artifact_id}")
def artifact(run_id: str, artifact_id: str) -> Response:
    """실행에서 검증·보존한 실험 또는 예측 구조 mmCIF를 내보낸다.

    실험 구조도 실행 폴더에 보존하며 공개 구조 목록 밖의 출처를 함께 지원한다.

    sha256을 헤더로 같이 보낸다. 프런트는 공개 구조에 하던 것과 똑같이
    받은 내용을 직접 해시해서 대조할 수 있다.
    """
    match = _ARTIFACT_ID.match(artifact_id)
    if not _RUN_ID.match(run_id) or not match:
        raise HTTPException(404, "모르는 실행 또는 산출물이다.")

    run_dir = (WORK_ROOT / run_id).resolve()
    path = (run_dir / f"{match.group(1)}.cif").resolve()
    # resolve 뒤에도 확인한다. 심볼릭 링크로도 밖으로 나갈 수 있다.
    if not path.is_file() or run_dir not in path.parents:
        raise HTTPException(404, "산출물 파일이 없다.")

    data = path.read_bytes()
    return Response(
        content=data,
        media_type="chemical/x-mmcif",
        headers={
            "X-Artifact-Sha256": hashlib.sha256(data).hexdigest(),
            "Access-Control-Expose-Headers": "X-Artifact-Sha256",
        },
    )


@app.post("/api/review")
def review(body: ReviewRequest) -> dict[str, Any]:
    """분석을 실행하고 프런트가 읽는 모양으로 돌려준다."""
    review_input = body.input
    if review_input is None:
        builder = demo_input.PRESETS.get(body.preset or "experimental")
        if builder is None:
            raise HTTPException(404, f"모르는 preset: {body.preset}")
        review_input = builder()

    run_id = f"run-{uuid.uuid4().hex[:12]}"
    review_id = f"rev-{uuid.uuid4().hex[:8]}"
    work_dir = WORK_ROOT / run_id
    work_dir.mkdir(parents=True, exist_ok=True)

    request = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "review_id": review_id,
        "input": review_input,
        "settings_version": f"service-{SCHEMA_VERSION}",
        "work_dir": str(work_dir),
        "uploads": [],
        "data_mode": DATA_MODE,
    }

    created = now_rfc3339()
    started = time.monotonic()
    try:
        output, flow = run_flow(request)
    except ContractError as exc:
        # 계약 위반 입력은 실행하지 않는다. 어디가 틀렸는지 그대로 전달한다.
        raise HTTPException(422, str(exc)) from exc
    elapsed = time.monotonic() - started
    finished = now_rfc3339()

    run = {
        "schema_version": SCHEMA_VERSION,
        "data_mode": DATA_MODE,
        "run_id": run_id,
        "review_id": review_id,
        "status": flow.run_status(),
        "settings_version": request["settings_version"],
        "candidates": flow.candidate_progress(),
        "created_at": created,
        "started_at": created,
        "finished_at": finished,
        "updated_at": finished,
        "result_available": True,
        "error": None,
    }
    session = {
        "schema_version": SCHEMA_VERSION,
        "data_mode": DATA_MODE,
        "session_id": f"sess-{uuid.uuid4().hex[:8]}",
        "status": "active",
        "expires_at": finished,
    }

    scenario_file = {
        "schema_version": SCHEMA_VERSION,
        "data_mode": DATA_MODE,
        "description": (
            f"실제 실행 결과. 소요 {elapsed:.1f}초. 모의 시나리오가 아니다."
        ),
        "input": review_input,
        "scenarios": [
            {
                "name": "실제 실행",
                "description": f"{created} 실행. 실행 상태 {run['status']}.",
                "session": session,
                "run": run,
                "result": output["result"],
                "error": None,
            }
        ],
    }

    try:
        validate(run, "Run")
        validate(session, "Session")
        validate(output, "LogicOutput")
    except ContractError as exc:
        # 계약을 어긴 결과를 화면으로 내보내지 않는다.
        raise HTTPException(500, f"결과가 계약을 어겼다:\n{exc}") from exc

    return scenario_file
