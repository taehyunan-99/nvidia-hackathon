"""Separate, mock-only worker for persisted review runs."""

from __future__ import annotations

import argparse
import copy
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from psycopg.types.json import Jsonb

from logic.contract import validate

from .db import connect, require_schema
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
            conn.execute(
                "UPDATE sessions SET status = %s, cleaned_at = now() WHERE id = %s",
                ("deleted" if session["status"] == "deleting" else "expired", session["id"]),
            )
            count += 1
    return count


def claim(dsn: str, owner: str) -> dict | None:
    now = _now()
    with connect(dsn) as conn:
        row = conn.execute(
            """SELECT r.id, r.state_json, v.input_json FROM runs r
               JOIN reviews v ON v.id = r.review_id
               JOIN sessions s ON s.id = r.session_id
               WHERE r.state_json->>'status' = 'queued' AND r.lease_owner IS NULL
                 AND s.status = 'active' AND s.expires_at > now()
               ORDER BY r.created_at, r.id LIMIT 1 FOR UPDATE OF r, s SKIP LOCKED"""
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


def process_one(dsn: str, scenario: str = "scientific-hold", *, data_root: Path | None = None, after_claim=None) -> str | None:
    if scenario not in SCENARIOS:
        raise ValueError("지원하지 않는 mock 시나리오입니다.")
    reap(dsn)
    if data_root is not None:
        cleanup_sessions(dsn, data_root)
    owner = uuid.uuid4().hex
    job = claim(dsn, owner)
    if job is None:
        return None
    if after_claim is not None:
        after_claim(job)
    if not heartbeat(dsn, job["id"], owner):
        return job["id"]
    state, result = _mock_output(job["state"], job["input"], scenario)
    finish(dsn, job["id"], owner, state, result)
    return job["id"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="scientific-hold")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    dsn = os.environ["DATABASE_URL"]
    root = Path(os.environ["SERVICE_DATA_ROOT"])
    require_schema(dsn)
    while True:
        job = process_one(dsn, args.scenario, data_root=root)
        if args.once:
            return
        if job is None:
            time.sleep(2)


if __name__ == "__main__":
    main()
