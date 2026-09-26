"""Persistent intake API. The demo-only synchronous API remains in service.app."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import gemmi
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from starlette.datastructures import UploadFile

from logic.contract import ContractError, SCHEMA_VERSION, now_rfc3339, validate

from .db import connect, require_schema

COOKIE_NAME = "her2_session"
SESSION_LIFETIME = timedelta(minutes=30)
STEPS = ("input_mapping", "evidence_review", "prediction", "structure_comparison", "reporting")
FASTA_LETTERS = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYBXZUO]+$", re.I)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _api_error(code: str, message: str, retry: str = "none") -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "data_mode": "mock",  # replaced by the app error handler
        "code": code,
        "message": message,
        "run_id": None,
        "candidate_id": None,
        "step_id": None,
        "field_errors": [],
        "retry_action": retry,
    }


def _fail(status: int, code: str, message: str, retry: str = "none") -> None:
    raise HTTPException(status, detail=_api_error(code, message, retry))


def _sequence(fasta: str) -> str:
    lines = [line.strip() for line in fasta.splitlines() if line.strip()]
    if lines and lines[0].startswith(">"):
        lines = lines[1:]
    sequence = "".join(lines)
    if not sequence or not FASTA_LETTERS.fullmatch(sequence):
        _fail(422, "INPUT_INVALID", "서열 형식을 확인하세요.", "fix_input")
    return sequence


def _check_input(body: dict[str, Any]) -> None:
    try:
        validate(body, "ReviewInput")
    except ContractError:
        _fail(422, "INPUT_INVALID", "입력 필드가 임시 계약에 맞지 않습니다.", "fix_input")
    candidates = body["candidates"]
    ids = [item["candidate_id"] for item in candidates]
    if len(set(ids)) != len(ids):
        _fail(422, "INPUT_INVALID", "후보 식별자가 중복됩니다.", "fix_input")
    keys = [item["upload_key"] for item in body["uploads"]]
    if len(set(keys)) != len(keys):
        _fail(422, "INPUT_INVALID", "업로드 식별자가 중복됩니다.", "fix_input")
    if any(item["candidate_id"] not in ids for item in body["uploads"]):
        _fail(422, "INPUT_INVALID", "업로드의 후보 식별자를 확인하세요.", "fix_input")
    for item in candidates:
        for chain in ("heavy", "light"):
            seq = _sequence(item[f"{chain}_chain_fasta"])
            region = item[f"{chain}_analysis_range"]
            if region and not (1 <= region["start"] <= region["end"] <= len(seq)):
                _fail(422, "INPUT_INVALID", "후보 분석 구간을 확인하세요.", "fix_input")
    target = body["target"]
    if target["fasta"]:
        seq = _sequence(target["fasta"])
        region = target["analysis_range"]
        if region and not (1 <= region["start"] <= region["end"] <= len(seq)):
            _fail(422, "INPUT_INVALID", "표적 분석 구간을 확인하세요.", "fix_input")


def _new_run(review_id: str, candidates: list[dict[str, Any]], mode: str) -> dict[str, Any]:
    now = now_rfc3339()
    run = {
        "schema_version": SCHEMA_VERSION,
        "data_mode": mode,
        "run_id": _id("run"),
        "review_id": review_id,
        "status": "queued",
        "settings_version": f"service-{SCHEMA_VERSION}",
        "candidates": [
            {
                "candidate_id": item["candidate_id"],
                "status": "queued",
                "current_step": None,
                "steps": [{"step_id": step, "status": "pending", "reason": None} for step in STEPS],
                "reason": None,
            }
            for item in candidates
        ],
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "updated_at": now,
        "result_available": False,
        "error": None,
    }
    validate(run, "Run")
    return run


def create_app(
    dsn: str,
    data_root: Path,
    *,
    mode: str = "mock",
    secure_cookie: bool = False,
    allowed_origins: tuple[str, ...] = (),
    max_upload_bytes: int = 20 * 1024 * 1024,
) -> FastAPI:
    if mode != "mock" or max_upload_bytes <= 0 or not dsn:
        raise ValueError("DATABASE_URL, DATA_MODE, MAX_UPLOAD_BYTES 설정을 확인하세요.")
    api = FastAPI(title="HER2 후보 검토 서비스", version=SCHEMA_VERSION)
    data_root = Path(data_root).resolve()

    @api.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else _api_error("INTERNAL_ERROR", "요청을 처리하지 못했습니다.")
        detail["data_mode"] = mode
        validate(detail, "ApiError")
        return JSONResponse(detail, status_code=exc.status_code)

    @api.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        detail = _api_error("INPUT_INVALID", "입력 형식을 확인하세요.", "fix_input")
        detail["data_mode"] = mode
        return JSONResponse(detail, status_code=422)

    @api.middleware("http")
    async def origin_check(request: Request, call_next):
        if request.method in {"POST", "DELETE", "PUT", "PATCH"}:
            origin = request.headers.get("origin")
            if origin and origin not in allowed_origins:
                detail = _api_error("SESSION_REQUIRED", "허용되지 않은 요청 출처입니다.")
                detail["data_mode"] = mode
                return JSONResponse(detail, status_code=403)
        return await call_next(request)

    def current_session(request: Request) -> dict[str, Any]:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            _fail(401, "SESSION_REQUIRED", "세션이 필요합니다.")
        digest = hashlib.sha256(token.encode()).hexdigest()
        with connect(dsn) as conn:
            row = conn.execute("SELECT * FROM sessions WHERE token_hash = %s", (digest,)).fetchone()
            if not row or row["status"] in {"deleting", "deleted"}:
                _fail(401, "SESSION_REQUIRED", "세션이 필요합니다.")
            if row["status"] == "expired" or row["expires_at"] <= datetime.now(timezone.utc):
                conn.execute("UPDATE sessions SET status = 'expired' WHERE id = %s", (row["id"],))
                conn.commit()
                _fail(410, "SESSION_EXPIRED", "세션이 만료되었습니다.")
        return row

    def session_body(row: dict[str, Any]) -> dict[str, Any]:
        body = {
            "schema_version": SCHEMA_VERSION,
            "data_mode": mode,
            "session_id": row["id"],
            "status": row["status"],
            "expires_at": _timestamp(row["expires_at"]),
        }
        validate(body, "Session")
        return body

    @api.post("/api/session", status_code=201)
    def create_session(response: Response):
        token = secrets.token_urlsafe(32)
        row = {
            "id": _id("sess"),
            "status": "active",
            "expires_at": datetime.now(timezone.utc) + SESSION_LIFETIME,
        }
        with connect(dsn) as conn:
            conn.execute(
                "INSERT INTO sessions(id, token_hash, status, expires_at) VALUES (%s, %s, %s, %s)",
                (row["id"], hashlib.sha256(token.encode()).hexdigest(), row["status"], row["expires_at"]),
            )
        response.set_cookie(COOKIE_NAME, token, httponly=True, secure=secure_cookie, samesite="lax", path="/api")
        response.headers["Cache-Control"] = "no-store"
        return session_body(row)

    @api.post("/api/session/heartbeat")
    def heartbeat(request: Request):
        row = current_session(request)
        with connect(dsn) as conn:
            row["expires_at"] = datetime.now(timezone.utc) + SESSION_LIFETIME
            conn.execute("UPDATE sessions SET expires_at = %s WHERE id = %s", (row["expires_at"], row["id"]))
        return session_body(row)

    @api.delete("/api/session", status_code=202)
    def delete_session(request: Request, response: Response):
        row = current_session(request)
        with connect(dsn) as conn:
            conn.execute("UPDATE sessions SET status = 'deleting' WHERE id = %s", (row["id"],))
        row["status"] = "deleting"
        response.delete_cookie(COOKIE_NAME, path="/api")
        response.headers["Cache-Control"] = "no-store"
        return session_body(row)

    @api.post("/api/reviews", status_code=201)
    async def create_review(request: Request):
        session = current_session(request)
        form = await request.form()
        metadata = form.get("metadata")
        if not isinstance(metadata, str) or len(form.getlist("metadata")) != 1:
            _fail(422, "INPUT_INVALID", "metadata가 필요합니다.", "fix_input")
        try:
            body = json.loads(metadata)
        except (ValueError, TypeError):
            _fail(422, "INPUT_INVALID", "metadata JSON을 확인하세요.", "fix_input")
        if not isinstance(body, dict):
            _fail(422, "INPUT_INVALID", "metadata 형식을 확인하세요.", "fix_input")
        _check_input(body)
        manifest = {item["upload_key"]: item for item in body["uploads"]}
        parts = [(key, value) for key, value in form.multi_items() if key != "metadata"]
        if len(parts) != len(manifest) or {key for key, _ in parts} != set(manifest) or any(not isinstance(value, UploadFile) for _, value in parts):
            _fail(422, "INPUT_INVALID", "파일과 업로드 목록이 일치하지 않습니다.", "fix_input")
        review_id = _id("rev")
        saved: list[Path] = []
        stored: dict[str, tuple[str, str, int]] = {}
        temporary_paths: list[Path] = []
        try:
            for key, upload in parts:
                item = manifest[key]
                suffix = ".pdb" if item["format"] == "pdb" else ".cif"
                target = data_root / "uploads" / review_id / f"{key}{suffix}"
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
                    temp_path = Path(temporary.name)
                    temporary_paths.append(temp_path)
                    size = 0
                    digest = hashlib.sha256()
                    while chunk := await upload.read(1024 * 1024):
                        size += len(chunk)
                        if size > max_upload_bytes:
                            _fail(413, "INPUT_TOO_LARGE", "파일 크기 제한을 넘었습니다.")
                        digest.update(chunk)
                        temporary.write(chunk)
                try:
                    structure = gemmi.read_structure(str(temp_path), format=gemmi.CoorFormat.Pdb if suffix == ".pdb" else gemmi.CoorFormat.Mmcif)
                    if not structure or not structure[0]:
                        raise ValueError("empty structure")
                except (RuntimeError, ValueError):
                    _fail(422, "INPUT_INVALID", "구조 파일을 읽을 수 없습니다.", "fix_input")
                temp_path.replace(target)
                saved.append(target)
                stored[key] = (str(target.relative_to(data_root)), digest.hexdigest(), size)
            with connect(dsn) as conn:
                active = conn.execute(
                    "SELECT 1 FROM sessions WHERE id = %s AND status = 'active' AND expires_at > now() FOR SHARE",
                    (session["id"],),
                ).fetchone()
                if not active:
                    _fail(410, "SESSION_EXPIRED", "세션이 만료되었습니다.")
                conn.execute("INSERT INTO reviews(id, session_id, input_json) VALUES (%s, %s, %s)", (review_id, session["id"], Jsonb(body)))
                for key in manifest:
                    relative, digest, size = stored[key]
                    conn.execute(
                        "INSERT INTO uploads(id, review_id, upload_key, relative_path, sha256, size_bytes) VALUES (%s, %s, %s, %s, %s, %s)",
                        (_id("upl"), review_id, key, relative, digest, size),
                    )
        except Exception:
            for path in saved:
                path.unlink(missing_ok=True)
            raise
        finally:
            for path in temporary_paths:
                path.unlink(missing_ok=True)
        result = {"schema_version": SCHEMA_VERSION, "data_mode": mode, "review_id": review_id}
        validate(result, "ReviewAccepted")
        return result

    @api.post("/api/reviews/{review_id}/runs", status_code=202)
    async def create_run(review_id: str, request: Request):
        session = current_session(request)
        try:
            body = await request.json()
            validate(body, "RunRequest")
        except (ValueError, ContractError, TypeError):
            _fail(422, "INPUT_INVALID", "실행 접수 키를 확인하세요.", "fix_input")
        if len(body["request_key"]) > 128:
            _fail(422, "INPUT_INVALID", "실행 접수 키가 너무 깁니다.", "fix_input")
        with connect(dsn) as conn:
            active = conn.execute(
                "SELECT 1 FROM sessions WHERE id = %s AND status = 'active' AND expires_at > now() FOR SHARE",
                (session["id"],),
            ).fetchone()
            if not active:
                _fail(410, "SESSION_EXPIRED", "세션이 만료되었습니다.")
            review = conn.execute("SELECT input_json FROM reviews WHERE id = %s AND session_id = %s", (review_id, session["id"])).fetchone()
            if not review:
                _fail(404, "NOT_FOUND", "검토를 찾을 수 없습니다.")
            run = _new_run(review_id, review["input_json"]["candidates"], mode)
            inserted = conn.execute(
                "INSERT INTO runs(id, review_id, session_id, request_key, state_json) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (session_id, review_id, request_key) DO NOTHING RETURNING state_json",
                (run["run_id"], review_id, session["id"], body["request_key"], Jsonb(run)),
            ).fetchone()
            if not inserted:
                inserted = conn.execute(
                    "SELECT state_json FROM runs WHERE session_id = %s AND review_id = %s AND request_key = %s",
                    (session["id"], review_id, body["request_key"]),
                ).fetchone()
        return inserted["state_json"]

    @api.get("/api/reviews/{review_id}")
    def get_review(review_id: str, request: Request):
        session = current_session(request)
        with connect(dsn) as conn:
            row = conn.execute("SELECT input_json FROM reviews WHERE id = %s AND session_id = %s", (review_id, session["id"])).fetchone()
        if not row:
            _fail(404, "NOT_FOUND", "검토를 찾을 수 없습니다.")
        return JSONResponse(row["input_json"], headers={"Cache-Control": "no-store"})

    @api.get("/api/runs/{run_id}")
    def get_run(run_id: str, request: Request, response: Response):
        session = current_session(request)
        with connect(dsn) as conn:
            row = conn.execute("SELECT state_json FROM runs WHERE id = %s AND session_id = %s", (run_id, session["id"])).fetchone()
        if not row:
            _fail(404, "NOT_FOUND", "실행을 찾을 수 없습니다.")
        response.headers["Cache-Control"] = "no-store"
        return row["state_json"]

    @api.get("/api/runs/{run_id}/result")
    def get_result(run_id: str, request: Request):
        session = current_session(request)
        with connect(dsn) as conn:
            row = conn.execute("SELECT result_json FROM runs WHERE id = %s AND session_id = %s", (run_id, session["id"])).fetchone()
        if not row:
            _fail(404, "NOT_FOUND", "실행을 찾을 수 없습니다.")
        if row["result_json"] is None:
            _fail(409, "RESULT_NOT_READY", "결과가 아직 없습니다.", "check_run")
        return JSONResponse(row["result_json"], headers={"Cache-Control": "no-store"})

    @api.get("/api/artifacts/{artifact_id}")
    def get_artifact(artifact_id: str, request: Request):
        session = current_session(request)
        with connect(dsn) as conn:
            row = conn.execute(
                """SELECT f.relative_path, r.result_json FROM artifact_files f
                   JOIN runs r ON r.id = f.run_id
                   WHERE f.artifact_id = %s AND r.session_id = %s""",
                (artifact_id, session["id"]),
            ).fetchone()
        if not row or not row["result_json"]:
            _fail(404, "NOT_FOUND", "산출물을 찾을 수 없습니다.")
        matches = [item for item in row["result_json"].get("artifacts", []) if item.get("artifact_id") == artifact_id]
        if len(matches) != 1 or matches[0].get("status") != "ready":
            _fail(404, "NOT_FOUND", "준비된 산출물이 없습니다.")
        artifact = matches[0]
        relative = Path(row["relative_path"])
        artifact_root = (data_root / "artifacts").resolve()
        path = (data_root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(artifact_root) or not path.is_file():
            _fail(404, "NOT_FOUND", "산출물 파일을 찾을 수 없습니다.")
        content = path.read_bytes()
        if len(content) != artifact["size_bytes"] or hashlib.sha256(content).hexdigest() != artifact["sha256"]:
            _fail(404, "NOT_FOUND", "산출물 무결성을 확인할 수 없습니다.")
        media = {"pdb": "chemical/x-pdb", "mmcif": "chemical/x-mmcif", "json": "application/json", "csv": "text/csv"}.get(artifact["format"])
        if not media:
            _fail(404, "NOT_FOUND", "산출물 형식을 확인할 수 없습니다.")
        filename = Path(artifact["file_name"]).name
        return Response(content, media_type=media, headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"})

    return api


def from_environment() -> FastAPI:
    dsn = os.environ.get("DATABASE_URL", "")
    root = os.environ.get("SERVICE_DATA_ROOT", "")
    if not dsn or not root:
        raise RuntimeError("DATABASE_URL과 SERVICE_DATA_ROOT가 필요합니다.")
    require_schema(dsn)
    return create_app(
        dsn,
        Path(root),
        mode=os.environ.get("DATA_MODE", "mock"),
        secure_cookie=os.environ.get("SECURE_COOKIE", "false").lower() == "true",
        allowed_origins=tuple(filter(None, os.environ.get("ALLOWED_ORIGINS", "").split(","))),
        max_upload_bytes=int(os.environ.get("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024))),
    )
