"""Run declared checks with the bundled cross-platform process supervisor."""
from __future__ import annotations
import base64
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from parallel_contract import require, write_artifact, artifact_root, json_read, PROCESS_TERMINAL, identifier, text, stamp, spec


from managed_check import manager_call


def run_command(receipt, state, root, check, cwd, task_id=None):
    intent_id = uuid.uuid4().hex
    intent = {"intent_id": intent_id, "root": str(root), "check_id": check["id"],
              "task_id": task_id, "created_at": stamp()}
    # A lost Start response must remain visible even before a RunId is available.
    write_artifact(receipt, state, f"processes/intents/{intent_id}.json", intent)
    started = manager_call(root, "Start", FilePath=check["argv"][0],
                           ArgumentList=check["argv"][1:], WorkingDirectory=str(cwd),
                           TimeoutSeconds=check["timeout_seconds"])
    run_id = started["runId"]
    try:
        # Persist before waiting; pause/recovery discovers this even if worker output is lost.
        write_artifact(receipt, state, f"processes/{run_id}.json",
                       {**intent, "run_id": run_id})
        deadline = time.monotonic() + check["timeout_seconds"] + 30
        result = started
        while result["status"] not in PROCESS_TERMINAL:
            require(time.monotonic() < deadline, "managed check termination is unknown")
            time.sleep(0.3)
            result = manager_call(root, "Status", RunId=run_id)
        stdout = Path(result["stdoutPath"]).read_bytes()
        stderr = Path(result["stderrPath"]).read_bytes()
        code = result.get("state", {}).get("targetExitCode") if result["status"] == "Completed" else None
        return code, stdout, stderr, run_id
    finally:
        manager_call(root, "Stop", RunId=run_id)


def same_workspace(left, right):
    try:
        return Path(left).samefile(right)
    except OSError:
        return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))


def assert_checks_stopped(receipt, state, task_id=None):
    directory = artifact_root(receipt, state) / "processes"
    if not directory.exists():
        return
    records = [json_read(path) for path in directory.glob("*.json")]
    intents = [json_read(path) for path in (directory / "intents").glob("*.json")]
    selected = lambda record: task_id is None or record.get("task_id") == task_id or (
        record.get("task_id") is None and spec(state, task_id)["worktree"] is not None and
        same_workspace(record["root"], spec(state, task_id)["worktree"]))
    for intent in intents:
        if selected(intent):
            require(any(record.get("intent_id") == intent["intent_id"] for record in records),
                    f"unresolved check start {intent['intent_id']}; reconcile the actual harness result before continuing")
    for record in records:
        if not selected(record):
            continue
        if record.get("run_id") is None:
            require(record.get("status") == "not-started" and record.get("evidence"), "unverified check launch resolution")
            continue
        result = manager_call(record["root"], "Status", RunId=record["run_id"])
        require(result["status"] in PROCESS_TERMINAL,
                f"check process {record['run_id']} is live or unknown; stop it by RunId")


def resolve_start(receipt, state, intent_id, run_id, evidence):
    identifier(intent_id, "intent_id")
    text(evidence, "actual launch/termination evidence")
    directory = artifact_root(receipt, state) / "processes"
    intent = json_read(directory / "intents" / f"{intent_id}.json")
    require(not any(json_read(p).get("intent_id") == intent_id for p in directory.glob("*.json")),
            "check start is already resolved")
    if run_id is not None:
        text(run_id, "actual harness RunId")
        result = manager_call(intent["root"], "Status", RunId=run_id)
        require(result["status"] in PROCESS_TERMINAL, "stop the actual check RunId before recovery")
    return write_artifact(receipt, state, f"processes/resolved-{intent_id}.json",
                          {**intent, "run_id": run_id, "status": "not-started" if run_id is None else result["status"],
                           "evidence": evidence})
