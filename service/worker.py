"""Separate, mock-only worker for persisted review runs."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from psycopg.types.json import Jsonb

from logic.contract import validate

from .db import connect, require_schema
from .live import request_for_job, run_process, verified_files
from .operational import _timestamp

LEASE = timedelta(seconds=30)
SCENARIOS = {"completed", "scientific-hold", "partial", "failed"}
FIXTURES = Path(__file__).resolve().parent / "mock_scenarios.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _interrupt(state: dict, reason: str) -> dict:
    state = copy.deepcopy(state)
    stamp = _timestamp(_now())
    state.update(status="interrupted", finished_at=stamp, updated_at=stamp)
    for candidate in state["candidates"]:
        if candidate["status"] in {"queued", "running"}:
            candidate.update(status="interrupted", current_step=None, reason=reason)
            for step in candidate["steps"]:
                if step["status"] == "running":
                    step.update(status="failed", reason=reason)
    validate(state, "Run")
    return state


def reap(dsn: str) -> int:
    """Revoke expired leases; interrupted runs are never automatically claimed again."""
    count = 0
    with connect(dsn) as conn:
        rows = conn.execute(
            "SELECT id, state_json FROM runs WHERE lease_owner IS NOT NULL AND lease_until <= now() FOR UPDATE SKIP LOCKED"
        ).fetchall()
        for row in rows:
            state = _interrupt(row["state_json"], "worker 생존 확인 시간이 지났습니다.")
            conn.execute(
                "UPDATE runs SET state_json = %s, lease_owner = NULL, lease_until = NULL WHERE id = %s",
                (Jsonb(state), row["id"]),
            )
            count += 1
    return count


def cleanup_sessions(dsn: str, data_root: Path) -> int:
    """Remove expired/deleted session uploads only after every lease is released."""
    root = data_root.resolve()
    count = 0
    with connect(dsn) as conn:
        sessions = conn.execute(
            """SELECT id, status FROM sessions
               WHERE cleaned_at IS NULL AND (status = 'deleting' OR expires_at <= now())
               FOR UPDATE SKIP LOCKED"""
        ).fetchall()
        for session in sessions:
            live = conn.execute(
                "SELECT 1 FROM runs WHERE session_id = %s AND lease_owner IS NOT NULL LIMIT 1",
                (session["id"],),
            ).fetchone()
            if live:
                continue
            paths = conn.execute(
                """SELECT u.relative_path FROM uploads u JOIN reviews v ON v.id = u.review_id
                   WHERE v.session_id = %s""", (session["id"],)
            ).fetchall()
            for item in paths:
                path = (root / item["relative_path"]).resolve()
                if not path.is_relative_to(root):
                    raise RuntimeError("저장 경로가 데이터 루트 밖입니다.")
                path.unlink(missing_ok=True)
            run_ids = conn.execute("SELECT id FROM runs WHERE session_id = %s", (session["id"],)).fetchall()
            for run in run_ids:
                for folder in ("runs", "artifacts"):
                    path = (root / folder / run["id"]).resolve()
                    if path.is_relative_to(root / folder):
                        shutil.rmtree(path, ignore_errors=True)
            conn.execute(
                "UPDATE sessions SET status = %s, cleaned_at = now() WHERE id = %s",
                ("deleted" if session["status"] == "deleting" else "expired", session["id"]),
            )
            count += 1
    return count


def claim(dsn: str, owner: str, mode: str | None = None) -> dict | None:
    now = _now()
    with connect(dsn) as conn:
        if mode == "live":
            conn.execute("SELECT pg_advisory_xact_lock(2172)")
            active = conn.execute(
                "SELECT 1 FROM runs WHERE lease_owner IS NOT NULL AND lease_until > now() "
                "AND state_json->>'data_mode' = 'live' LIMIT 1"
            ).fetchone()
            if active:
                return None
        row = conn.execute(
            """SELECT r.id, r.state_json, v.input_json FROM runs r
               JOIN reviews v ON v.id = r.review_id
               JOIN sessions s ON s.id = r.session_id
               WHERE r.state_json->>'status' = 'queued' AND r.lease_owner IS NULL
                 AND (%s::text IS NULL OR r.state_json->>'data_mode' = %s)
                 AND s.status = 'active' AND s.expires_at > now()
               ORDER BY r.created_at, r.id LIMIT 1 FOR UPDATE OF r, s SKIP LOCKED"""
            , (mode, mode)
        ).fetchone()
        if not row:
            return None
        state = row["state_json"]
        stamp = _timestamp(now)
        state.update(status="running", started_at=stamp, updated_at=stamp)
        for candidate in state["candidates"]:
            candidate.update(status="running", current_step="input_mapping")
            candidate["steps"][0]["status"] = "running"
        validate(state, "Run")
        conn.execute(
            "UPDATE runs SET state_json = %s, lease_owner = %s, lease_until = %s, heartbeat_at = %s WHERE id = %s",
            (Jsonb(state), owner, now + LEASE, now, row["id"]),
        )
        return {"id": row["id"], "state": state, "input": row["input_json"]}


def heartbeat(dsn: str, run_id: str, owner: str) -> bool:
    now = _now()
    with connect(dsn) as conn:
        row = conn.execute(
            """UPDATE runs r SET lease_until = %s, heartbeat_at = %s
               FROM sessions s WHERE r.id = %s AND r.session_id = s.id
                 AND r.lease_owner = %s AND r.lease_until > %s
                 AND s.status = 'active' AND s.expires_at > %s
               RETURNING r.id""",
            (now + LEASE, now, run_id, owner, now, now),
        ).fetchone()
    return row is not None


def _mock_output(run: dict, review_input: dict, scenario: str) -> tuple[dict, dict | None]:
    validate(review_input, "ReviewInput")
    if [item["candidate_id"] for item in review_input["candidates"]] != [item["candidate_id"] for item in run["candidates"]]:
        raise ValueError("저장된 입력과 실행의 후보가 일치하지 않습니다.")
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    template = next(item for item in fixtures["scenarios"] if item["name"] == scenario)
    stamp = _timestamp(_now())
    state = copy.deepcopy(run)
    state.update(status=template["run"]["status"], updated_at=stamp, finished_at=stamp,
                 result_available=template["run"]["result_available"], error=template["run"]["error"])
    if state["error"] is not None:
        state["error"]["run_id"] = run["run_id"]
        source_id = state["error"]["candidate_id"]
        source_ids = [item["candidate_id"] for item in template["run"]["candidates"]]
        if source_id in source_ids:
            state["error"]["candidate_id"] = state["candidates"][source_ids.index(source_id)]["candidate_id"]
    for index, candidate in enumerate(state["candidates"]):
        source = template["run"]["candidates"][min(index, 1)]
        candidate.update(status=source["status"], current_step=None,
                         steps=copy.deepcopy(source["steps"]), reason=source["reason"])
    result = None
    if template["result"] is not None:
        result = copy.deepcopy(template["result"])
        result.update(run_id=run["run_id"], review_id=run["review_id"],
                      candidate_ids=[c["candidate_id"] for c in state["candidates"]],
                      created_at=stamp, settings_version=run["settings_version"])
        for field in ("conditions", "evidence", "opinions", "artifacts"):
            originals = template["result"][field]
            result[field] = []
            for index, candidate in enumerate(state["candidates"]):
                item = copy.deepcopy(originals[min(index, 1)])
                suffix = str(index + 1)
                for key in ("condition_id", "evidence_id", "opinion_id", "artifact_id"):
                    if key in item:
                        item[key] = f"mock-{key}-{suffix}"
                if "candidate_id" in item:
                    item["candidate_id"] = candidate["candidate_id"]
                if "condition_id" in item and field != "conditions":
                    item["condition_id"] = f"mock-condition_id-{suffix}"
                if "evidence_ids" in item:
                    item["evidence_ids"] = [f"mock-evidence_id-{suffix}"]
                result[field].append(item)
        validate(result, "Result")
    validate(state, "Run")
    return state, result


def finish(dsn: str, run_id: str, owner: str, state: dict, result: dict | None) -> bool:
    now = _now()
    with connect(dsn) as conn:
        row = conn.execute(
            """UPDATE runs r SET state_json = %s, result_json = %s,
                 lease_owner = NULL, lease_until = NULL
               FROM sessions s WHERE r.id = %s AND r.session_id = s.id
                 AND r.lease_owner = %s AND r.lease_until > %s
                 AND s.status = 'active' AND s.expires_at > %s
               RETURNING r.id""",
            (Jsonb(state), Jsonb(result) if result is not None else None, run_id, owner, now, now),
        ).fetchone()
    return row is not None


def save_progress(dsn: str, run_id: str, owner: str, update: dict) -> bool:
    validate(update, "ProgressUpdate")
    if update["run_id"] != run_id:
        raise ValueError("진행 이벤트의 실행 ID가 일치하지 않습니다.")
    with connect(dsn) as conn:
        row = conn.execute(
            "SELECT state_json FROM runs WHERE id = %s AND lease_owner = %s AND lease_until > now() FOR UPDATE",
            (run_id, owner),
        ).fetchone()
        if not row:
            return False
        state = row["state_json"]
        candidate_id = update["candidate_id"]
        if candidate_id is None:
            return True
        candidate = next((item for item in state["candidates"] if item["candidate_id"] == candidate_id), None)
        if candidate is None:
            raise ValueError("진행 이벤트의 후보 ID가 일치하지 않습니다.")
        activity = update.get("activity")
        if activity:
            events = state.setdefault("activity_events", [])
            if any(event.get("activity", {}).get("event_id") == activity["event_id"] for event in events):
                return True
            events.append(update)
            state["activity_events"] = events[-200:]
        if not activity or activity["kind"] == "stage":
            step = next(item for item in candidate["steps"] if item["step_id"] == update["step_id"])
            step.update(status=update["status"], reason=update["reason"])
            candidate["current_step"] = update["step_id"] if update["status"] == "running" else None
            if update["status"] == "running":
                candidate["status"] = "running"
            elif update["step_id"] == "reporting":
                statuses = {item["status"] for item in candidate["steps"]}
                candidate["status"] = "completed" if update["status"] == "completed" else "partial" if "held" in statuses else "failed"
            if update["reason"] and update["status"] in {"held", "failed"}:
                candidate["reason"] = update["reason"]
        state["updated_at"] = update["updated_at"]
        validate(state, "Run")
        conn.execute("UPDATE runs SET state_json = %s WHERE id = %s", (Jsonb(state), run_id))
    return True


def finish_live(dsn: str, run_id: str, owner: str, output: dict, data_root: Path) -> bool:
    validate(output, "LogicOutput")
    result = output["result"]
    if result["run_id"] != run_id or result["data_mode"] != "live":
        raise ValueError("분석 결과의 실행 ID 또는 모드가 일치하지 않습니다.")
    files = verified_files(output, data_root / "runs" / run_id)
    saved: list[Path] = []
    try:
        for artifact_id, _source, content in files:
            target = data_root / "artifacts" / run_id / artifact_id
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            saved.append(target)
        with connect(dsn) as conn:
            row = conn.execute(
                "SELECT r.state_json FROM runs r JOIN sessions s ON s.id = r.session_id "
                "WHERE r.id = %s AND r.lease_owner = %s AND r.lease_until > now() "
                "AND s.status = 'active' AND s.expires_at > now() FOR UPDATE OF r",
                (run_id, owner),
            ).fetchone()
            if not row:
                return False
            state = row["state_json"]
            if (result["review_id"] != state["review_id"] or result["settings_version"] != state["settings_version"]
                    or result["candidate_ids"] != [c["candidate_id"] for c in state["candidates"]]):
                raise ValueError("분석 결과가 저장된 입력과 일치하지 않습니다.")
            for candidate in state["candidates"]:
                if candidate["status"] in {"queued", "running"}:
                    candidate.update(status="failed", current_step=None, reason="분석이 완료됐지만 후보 진행 상태가 끝나지 않았습니다.")
            statuses = {c["status"] for c in state["candidates"]}
            stamp = _timestamp(_now())
            state.update(
                status="completed" if statuses == {"completed"} else "partial" if statuses & {"completed", "partial"} else "failed",
                finished_at=stamp, updated_at=stamp, result_available=True,
            )
            validate(state, "Run")
            for artifact_id, _, _ in files:
                relative = str((Path("artifacts") / run_id / artifact_id))
                conn.execute(
                    "INSERT INTO artifact_files(artifact_id, run_id, relative_path) VALUES (%s, %s, %s)",
                    (artifact_id, run_id, relative),
                )
            conn.execute(
                "UPDATE runs SET state_json = %s, result_json = %s, lease_owner = NULL, lease_until = NULL WHERE id = %s",
                (Jsonb(state), Jsonb(result), run_id),
            )
        saved.clear()
        return True
    finally:
        for path in saved:
            path.unlink(missing_ok=True)


def fail_live(dsn: str, run_id: str, owner: str, message: str) -> bool:
    with connect(dsn) as conn:
        row = conn.execute(
            "SELECT r.state_json FROM runs r JOIN sessions s ON s.id = r.session_id "
            "WHERE r.id = %s AND r.lease_owner = %s AND r.lease_until > now() "
            "AND s.status = 'active' AND s.expires_at > now() FOR UPDATE OF r",
            (run_id, owner),
        ).fetchone()
        if not row:
            return False
        state = row["state_json"]
        stamp = _timestamp(_now())
        for candidate in state["candidates"]:
            if candidate["status"] in {"queued", "running"}:
                candidate.update(status="failed", current_step=None, reason=message)
                running = [step for step in candidate["steps"] if step["status"] == "running"]
                for step in running or candidate["steps"][:1]:
                    step.update(status="failed", reason=message)
        state.update(status="failed", finished_at=stamp, updated_at=stamp,
                     error={"schema_version": state["schema_version"], "data_mode": "live", "code": "ANALYSIS_FAILED",
                            "message": message, "run_id": run_id, "candidate_id": None, "step_id": None,
                            "field_errors": [], "retry_action": "new_run"})
        validate(state, "Run")
        updated = conn.execute(
            "UPDATE runs SET state_json = %s, lease_owner = NULL, lease_until = NULL "
            "WHERE id = %s AND lease_owner = %s RETURNING id",
            (Jsonb(state), run_id, owner),
        ).fetchone()
        return updated is not None


def process_one(dsn: str, scenario: str = "scientific-hold", *, data_root: Path | None = None, after_claim=None, mode: str = "mock") -> str | None:
    if mode == "mock" and scenario not in SCENARIOS:
        raise ValueError("지원하지 않는 mock 시나리오입니다.")
    if mode == "live" and data_root is None:
        raise ValueError("실제 분석에는 데이터 폴더가 필요합니다.")
    reap(dsn)
    if data_root is not None:
        cleanup_sessions(dsn, data_root)
    owner = uuid.uuid4().hex
    job = claim(dsn, owner, mode)
    if job is None:
        return None
    if after_claim is not None:
        after_claim(job)
    if mode == "live":
        try:
            request = request_for_job(dsn, job, data_root)
            last_heartbeat = 0.0

            def alive():
                nonlocal last_heartbeat
                if time.monotonic() - last_heartbeat < 5:
                    return True
                last_heartbeat = time.monotonic()
                return heartbeat(dsn, job["id"], owner)

            def progress(update):
                if not save_progress(dsn, job["id"], owner, update):
                    raise InterruptedError("작업 점유권이 종료되었습니다.")

            output = run_process(request, progress, alive)
            finish_live(dsn, job["id"], owner, output, data_root)
        except InterruptedError:
            pass
        except Exception as exc:
            fail_live(dsn, job["id"], owner, f"분석 실행 실패: {type(exc).__name__}"[:180])
        return job["id"]
    if not heartbeat(dsn, job["id"], owner):
        return job["id"]
    state, result = _mock_output(job["state"], job["input"], scenario)
    finish(dsn, job["id"], owner, state, result)
    return job["id"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("mock", "live"), default=os.environ.get("DATA_MODE", "mock"))
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="scientific-hold")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    dsn = os.environ["DATABASE_URL"]
    root = Path(os.environ["SERVICE_DATA_ROOT"])
    require_schema(dsn)
    while True:
        job = process_one(dsn, args.scenario, data_root=root, mode=args.mode)
        if args.once:
            return
        if job is None:
            time.sleep(2)


if __name__ == "__main__":
    main()
