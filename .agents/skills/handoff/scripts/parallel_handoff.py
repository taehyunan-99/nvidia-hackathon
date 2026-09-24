"""Stateful helpers for the Codex-app-only handoff parallel workflow."""
from __future__ import annotations
import argparse
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import base64
import parallel_wait
from parallel_checks import run_command, assert_checks_stopped, resolve_start
from parallel_contract import (
    ParallelError, SCHEMA, APP_BACKEND, MESSAGE_SCHEMA, MAX_BYTES, PHASES, PROCESS_TERMINAL,
    require, text, keys, identifier, stamp, timestamp, digest, sha, relative, covered, overlaps,
    safe_path, read_bytes, json_read, git, git_text, repository, common_dir, plan_hash, validate_plan,
    validate_state, validate_observation, stopped, spec, extract, embed, load_renderer, transaction,
    atomic_write, input_snapshot, workspace_snapshot, dirty_paths, artifact_root, write_artifact, evidence_json,
)

WORKER_TYPES = {"ACK", "UPDATE", "RESULT", "CHECKPOINT"}
MAIN_TYPES = {"ASSIGN", "DECISION", "REVIEW", "STOP"}


def load(receipt):
    state = extract(read_bytes(receipt).decode("utf-8-sig"))
    require(state is not None, "receipt has no parallel execution plan")
    return state


def metadata_paths(receipt, state):
    root = repository(state["plan"]["parent_worktree"])
    return [Path(receipt).resolve().relative_to(root).as_posix(),
            (Path(receipt).parent / "handoff-runs").resolve().relative_to(root).as_posix(),
            Path(receipt).resolve().relative_to(root).as_posix() + ".parallel.lock"]


def assert_workspace(state, tid, *, unchanged=False):
    task, planned = state["tasks"][tid], spec(state, tid)
    require(planned["worktree"] is not None, "register the actual app worktree before dispatch")
    root = repository(planned["worktree"])
    parent = Path(state["plan"]["parent_worktree"]).resolve()
    require(root == Path(planned["worktree"]).resolve(), "task worktree must be its Git root")
    require(common_dir(root) == common_dir(parent), "task belongs to another repository")
    require(git_text(root, "branch", "--show-current") == planned["branch"], "task branch changed")
    expected_head = task["result_commit"] or state["plan"]["parent_commit"]
    if planned["write_paths"]:
        require(git_text(root, "rev-parse", "HEAD") == expected_head, "task HEAD differs from assigned/result commit")
    else:
        require(git(root, "merge-base", "--is-ancestor", expected_head, "HEAD", check=False).returncode == 0,
                "readonly task lost its baseline")
        require(input_snapshot(root, planned["input_paths"]) == state["parent_inputs"][tid],
                "readonly validation inputs changed")
        if root != parent:
            require(not dirty_paths(root), "readonly worktree has source changes")
    if planned["write_paths"]:
        require(root != parent, "writer cannot use integration worktree")
        require(all(covered(p, planned["write_paths"]) for p in dirty_paths(root)),
                "worktree contains changes outside assigned write scope")
    if unchanged and task["workspace_snapshot"] is not None:
        actual, previous = workspace_snapshot(root, planned["write_paths"]), task["workspace_snapshot"]
        if not planned["write_paths"]:
            actual = {k: v for k, v in actual.items() if k not in {"head", "id"}}
            previous = {k: v for k, v in previous.items() if k not in {"head", "id"}}
        require(actual == previous,
                "paused workspace/index differs from checkpoint")
    return root


def assert_parent(receipt, state):
    plan = state["plan"]
    root = repository(plan["parent_worktree"])
    require(git_text(root, "branch", "--show-current") == plan["parent_branch"], "integration branch changed")
    require(git(root, "merge-base", "--is-ancestor", plan["parent_commit"], "HEAD", check=False).returncode == 0,
            "integration branch no longer contains parent baseline")
    require(all(covered(p, metadata_paths(receipt, state)) for p in dirty_paths(root)),
            "integration worktree has non-handoff changes")
    require(not git_text(root, "diff", "--name-only", "--diff-filter=U"), "unresolved integration conflict")
    return root


def mutate(receipt, revision, controller, epoch, action, *, claim=False):
    with transaction(receipt) as before:
        raw = before.decode("utf-8-sig")
        state = extract(raw)
        require(state is not None, "missing parallel execution state")
        require(state["revision"] == revision, "stale revision; inspect current receipt before retry")
        if not claim:
            require(state["controller_id"] == controller and state["controller_epoch"] == epoch,
                    "controller/epoch lost ownership")
        response, changed = action(state)
        if not changed:
            return {"state": state, "result": response}
        state["revision"] += 1
        validate_state(state)
        updated = embed(raw, state)
        # A live run is not a receipt that a different main may resume.
        # The normal handoff preparation refreshes evidence and READY after pause/done.
        if state["phase"] in {"ACTIVE", "STOPPING"}:
            updated = re.sub(r"(?m)^Receipt: (READY|STALE|INVALID)$", "Receipt: STALE", updated, count=1)
        load_renderer().parse_handoff(updated)
        atomic_write(receipt, before, updated.encode("utf-8"))
        return {"state": state, "result": response}


def require_app_plan(plan):
    require(plan.get("execution_backend") == APP_BACKEND,
            "legacy parallel backend cannot execute; preserve evidence and prepare an explicitly approved app-threads plan")


def require_capacity(state):
    require_app_plan(state["plan"])
    live = sum(not stopped(task) for task in state["tasks"].values())
    require(live < state["plan"]["max_parallel"], "approved app session concurrency is full; wait for a terminal turn")


def prepare(receipt, plan):
    plan = {"session_policy": "one-task-one-retry", "notification_mode": "direct", **plan}
    validate_plan(plan)
    require_app_plan(plan)
    root = repository(plan["parent_worktree"])
    if "app_project" in plan:
        require(common_dir(plan["app_project"]["path"]) == common_dir(root), "saved app project belongs to another repository")
    require(root == Path(plan["parent_worktree"]).resolve(), "parent_worktree must be the Git root")
    require(git_text(root, "branch", "--show-current") == plan["parent_branch"], "parent branch mismatch")
    require(git_text(root, "rev-parse", "HEAD") == plan["parent_commit"], "prepare from current parent HEAD")
    with transaction(receipt) as before:
        raw = before.decode("utf-8-sig")
        core = load_renderer().parse_handoff(raw)
        old = extract(raw)
        require(old is None or old["phase"] == "COMPLETE" or
                (old["phase"] == "PLANNED" and old["approval"] is None),
                "existing approved/started run must be resumed")
        require(core["metadata"]["Format"] in {"handoff-v7", "handoff-v8"}, "prepare a current v7 receipt first")
        require(core["metadata"]["Work status"] != "COMPLETE", "next must name an actual development stage")
        selected = core["routing"]
        require(selected and selected["Current stage"].split(" ", 1)[0] == plan["stage_id"], "plan must target selected stage")
        require(plan["goal"] == selected["Goal"], "plan goal must equal selected stage outcome")
        require(selected["Use Ultra"] == "yes", "record independent-task evidence and Use Ultra: yes first")
        project_root = Path(receipt).resolve().parent.parent
        project_scope = project_root.relative_to(root).as_posix()
        require(project_scope == core["metadata"]["Project scope"], "receipt project scope does not match its location")
        control = [Path(receipt).resolve().relative_to(root).as_posix(),
                   (Path(receipt).resolve().parent / "handoff-runs").relative_to(root).as_posix()]
        for task in plan["tasks"]:
            require(not overlaps(task["input_paths"], control), "validation inputs cannot include runtime receipt/reports")
            if project_scope != ".":
                require(all(covered(p, [project_scope]) for p in task["write_paths"]), "task writes outside selected project")
        initial = {
            "attempt": 0, "instruction_revision": 0, "status": "PLANNED", "worker_id": None,
            "worker_thread_id": None, "termination": None, "processes": {},
            "workspace_snapshot": None, "result": None, "review": None, "checkpoint": None,
            "result_commit": None, "assignment": None, "reworks": 0,
        }
        state = {"schema": SCHEMA, "run_id": uuid.uuid4().hex, "phase": "PLANNED", "revision": 0,
                 "controller_epoch": 0, "controller_id": None, "plan": copy.deepcopy(plan), "approval": None,
                 "tasks": {t["id"]: copy.deepcopy(initial) for t in plan["tasks"]}, "messages": {},
                 "integration": None, "parent_inputs": {t["id"]: input_snapshot(root, t["input_paths"]) for t in plan["tasks"]}}
        updated = re.sub(r"(?m)^Format: handoff-v7$", "Format: handoff-v8", embed(raw, state), count=1)
        load_renderer().parse_handoff(updated)
        atomic_write(receipt, before, updated.encode("utf-8"))
        return {"state": state}


def approve(receipt, revision, evidence, internal_git):
    text(evidence, "user approval reference")
    def action(state):
        require_app_plan(state["plan"])
        require(state["phase"] == "PLANNED", "approve before claim")
        state["approval"] = {"plan_hash": plan_hash(state["plan"]), "evidence": evidence, "internal_git": internal_git}
        return {"approved": True}, True
    return mutate(receipt, revision, None, 0, action, claim=True)


def claim(receipt, revision, controller):
    text(controller, "controller ID")
    def action(state):
        if state["phase"] == "COMPLETE":
            return {"status": "NO_REMAINING_WORK"}, False
        require_app_plan(state["plan"])
        require(state["phase"] in {"PLANNED", "PAUSED"}, "a live main owns this run; pause it before takeover")
        require(state["approval"] is not None, "confirm the concrete plan with the user before execution")
        assert_parent(receipt, state)
        assert_checks_stopped(receipt, state)
        require(all(stopped(t) for t in state["tasks"].values()), "previous execution or process status is unknown/live")
        if state["phase"] == "PAUSED":
            for tid in state["tasks"]:
                if state["tasks"][tid]["attempt"]:
                    assert_workspace(state, tid, unchanged=True)
        state["controller_epoch"] += 1
        state["controller_id"] = controller
        state["phase"] = "ACTIVE"
        return {"controller_epoch": state["controller_epoch"],
                "review_first": [k for k, t in state["tasks"].items() if t["status"] == "REPORTED"],
                "unfinished": [k for k, t in state["tasks"].items() if t["status"] not in {"VERIFIED", "INTEGRATED"}]}, True
    return mutate(receipt, revision, controller, 0, action, claim=True)


def envelope(state, tid, kind, sender, payload, reply_to=None):
    task = state["tasks"][tid]
    return {"schema": MESSAGE_SCHEMA, "message_id": uuid.uuid4().hex, "type": kind,
            "run_id": state["run_id"], "task_id": tid, "attempt": task["attempt"],
            "instruction_revision": task["instruction_revision"], "controller_epoch": state["controller_epoch"],
            "reply_to": reply_to, "sender": sender, "created_at": stamp(), "payload": payload}


def publish(receipt, state, message):
    return write_artifact(receipt, state, f"{message['task_id']}/{message['attempt']}/{message['message_id']}.json", message)


def wait_begin(receipt, revision, controller, epoch, request):
    def action(state):
        require_app_plan(state["plan"])
        if "wait_batch" in state:
            write_artifact(receipt, state, f"wait/{uuid.uuid4().hex}.json", state["wait_batch"])
        state["wait_batch"] = parallel_wait.begin(state, request)
        return state["wait_batch"], True
    return mutate(receipt, revision, controller, epoch, action)


def wait_save(receipt, revision, controller, epoch, checkpoint):
    def action(state):
        updated = parallel_wait.save(receipt, state, checkpoint)
        changed = updated != state["wait_batch"]
        state["wait_batch"] = updated
        return updated, changed
    return mutate(receipt, revision, controller, epoch, action)


def reserve_app(receipt, revision, controller, epoch, tid):
    def action(state):
        require(state["phase"] == "ACTIVE", "app creation requires an active approved run")
        task = state["tasks"][tid]
        planned = next(t for t in state["plan"]["tasks"] if t["id"] == tid)
        require(planned["worktree"] is None and task["attempt"] == 0, "reserve only a new app worktree")
        require("app_creation" not in task, "creation already reserved; reconcile its app response instead of creating again")
        require_capacity(state)
        assert_parent(receipt, state)
        task["app_creation"] = {"nonce": uuid.uuid4().hex, "status": "pending", "controller_epoch": epoch}
        return {"nonce": task["app_creation"]["nonce"], "project": state["plan"]["app_project"],
                "starting_commit": state["plan"]["parent_commit"],
                "instruction": "Create one requested app worktree task with a registration-only prompt. Run app-hello from its actual cwd, return evidence and end the turn before source edits."}, True
    return mutate(receipt, revision, controller, epoch, action)


def record_app(receipt, revision, controller, epoch, tid, response):
    def action(state):
        require(state["phase"] in {"ACTIVE", "STOPPING"}, "creation response requires a live run")
        creation = state["tasks"][tid].get("app_creation", {})
        require(creation.get("status") == "pending", "no pending creation response")
        if "response" in creation:
            require(creation["response"] == response, "creation response changed; reconcile the original request")
            return {"status": "ALREADY_RECORDED"}, False
        creation["response"] = response
        return {"status": "RECORDED"}, True
    return mutate(receipt, revision, controller, epoch, action)


def app_hello(receipt, tid, nonce):
    state = load(receipt)
    creation = state["tasks"][tid].get("app_creation", {})
    require(state["phase"] in {"ACTIVE", "STOPPING"} and creation.get("status") == "pending"
            and creation.get("nonce") == nonce, "stale app creation request")
    root = repository(Path.cwd())
    return write_artifact(receipt, state, f"{tid}/app-hello-{uuid.uuid4().hex}.json",
                          {"nonce": nonce, "run_id": state["run_id"], "task_id": tid,
                           "worker_id": text(os.environ.get("CODEX_THREAD_ID"), "CODEX_THREAD_ID"),
                           "worktree": str(root), "head": git_text(root, "rev-parse", "HEAD")})


def recover_app(receipt, revision, controller, epoch, tid, evidence):
    def action(state):
        require(state["phase"] in {"ACTIVE", "STOPPING"}, "recover creation only in a live run")
        task = state["tasks"][tid]
        creation = task.get("app_creation", {})
        require(creation.get("status") == "pending" and task["attempt"] == 0, "no pending creation to recover")
        require(creation.get("response", {}).get("id_kind") != "threadId", "an actual created task must be reconciled, not declared unstarted")
        keys(evidence, {"nonce", "tool", "status", "reference"}, label="failed app creation evidence")
        require(evidence["nonce"] == creation["nonce"] and evidence["tool"] == "create_thread"
                and evidence["status"] == "not-started", "require direct creation failure, never a timeout or unknown execution")
        text(evidence["reference"], "actual creation failure reference")
        reference = write_artifact(receipt, state, f"{tid}/app-failure-{creation['nonce']}-{uuid.uuid4().hex}.json",
                                   {"creation": creation, "evidence": evidence})
        del task["app_creation"]
        return {"status": "NOT_STARTED", "evidence": reference}, True
    return mutate(receipt, revision, controller, epoch, action)


def register_app(receipt, revision, controller, epoch, tid, evidence):
    def action(state):
        require(state["phase"] in {"ACTIVE", "STOPPING"}, "app registration requires a live run")
        task, planned = state["tasks"][tid], spec(state, tid)
        creation = task.get("app_creation", {})
        require(creation.get("status") == "pending", "no pending app creation")
        keys(evidence, {"hello", "thread_id", "host_id", "creation_reference", "terminal"}, label="app registration evidence")
        terminal = evidence["terminal"]
        keys(terminal, {"tool", "status", "turn_id", "reference"}, label="registration turn")
        require(terminal["tool"] in {"read_thread", "wait_threads"} and terminal["status"] == "completed", "observe the actual registration turn completion")
        text(terminal["turn_id"], "registration turn ID")
        text(terminal["reference"], "terminal app tool reference")
        text(evidence["creation_reference"], "creation app tool reference")
        hello_info = evidence_json(receipt, state, evidence["hello"])
        require(hello_info["nonce"] == creation["nonce"] and hello_info["run_id"] == state["run_id"]
                and hello_info["task_id"] == tid, "app hello belongs to another creation")
        worker = text(evidence["thread_id"], "actual app thread ID")
        if creation.get("response", {}).get("id_kind") == "threadId":
            require(creation["response"]["id"] == worker, "actual thread differs from creation response")
        require(worker == hello_info["worker_id"] and worker != controller, "actual app ID must match CODEX_THREAD_ID")
        require(evidence["host_id"] == state["plan"]["app_project"]["host_id"], "app host differs from approved parent host")
        require(hello_info["head"] == state["plan"]["parent_commit"], "app was created at another baseline")
        root = Path(hello_info["worktree"]).resolve()
        for other_id, other in state["tasks"].items():
            if other_id == tid:
                continue
            require(other.get("app_creation", {}).get("thread_id") != worker, "app task already belongs to another role")
            other_root = spec(state, other_id)["worktree"]
            require(other_root is None or Path(other_root).resolve() != root, "app writers cannot share a worktree")
        require(input_snapshot(root, planned["input_paths"]) == state["parent_inputs"][tid], "app inputs differ from approved parent")
        helper = Path(__file__).with_name("worktree_guard.py")
        plan = state["plan"]
        command = [sys.executable, str(helper),
                   "-Branch", planned["branch"], "-ParentBranch", plan["parent_branch"],
                   "-ParentCommit", plan["parent_commit"], "-ParentWorktree", plan["parent_worktree"],
                   "-RunId", state["run_id"], "-RegisterAppWorktree", str(root),
                   "-AppThreadId", worker, "-AppHostId", evidence["host_id"]]
        result = subprocess.run(command, cwd=common_dir(plan["parent_worktree"]).parent,
                                capture_output=True, timeout=120)
        require(result.returncode == 0, "app worktree registration failed: " + result.stderr.decode(errors="replace"))
        registration = json.loads(result.stdout.decode("utf-8-sig"))
        require(registration["action"] == "Registered" and registration["baseSha"] == plan["parent_commit"]
                and Path(registration["worktreePath"]).resolve() == root, "unexpected safety registration result")
        task["app_creation"] = {**creation, "status": "registered", "worktree": str(root),
                                "thread_id": worker, "host_id": evidence["host_id"],
                                "evidence": evidence, "registration": registration}
        assert_workspace(state, tid)
        return {"worktree": str(root), "thread_id": worker, "host_id": evidence["host_id"]}, True
    return mutate(receipt, revision, controller, epoch, action)


def dispatch(receipt, revision, controller, epoch, tid):
    def action(state):
        require_capacity(state)
        require(state["phase"] == "ACTIVE", "dispatch requires ACTIVE run")
        task, planned = state["tasks"][tid], spec(state, tid)
        require(task["status"] in {"PLANNED", "STOPPED", "BLOCKED", "CHANGES_REQUESTED"}, "task is already dispatched, reported or complete")
        require(stopped(task), "confirm previous execution/process termination before a new attempt")
        assert_checks_stopped(receipt, state, task_id=tid)
        root = assert_workspace(state, tid, unchanged=task["attempt"] > 0)
        if task["attempt"] == 0:
            require(input_snapshot(root, planned["input_paths"]) == state["parent_inputs"][tid],
                    "child inputs differ from approved parent, including uncommitted parent inputs")
        task["attempt"] += 1
        if state["plan"].get("session_policy") == "one-task-one-retry":
            task["session_retries"] = 0
        task["instruction_revision"] += 1
        previous_worker = task["worker_id"]
        retired = task.setdefault("retired_workers", [])
        if previous_worker and previous_worker not in retired:
            retired.append(previous_worker)
        task["worker_id"] = None
        task["worker_thread_id"] = None
        task["worker_host_id"] = None
        task["termination"] = None
        task["processes"] = {}
        task["workspace_snapshot"] = workspace_snapshot(root, planned["write_paths"])
        task["status"] = "DISPATCHING"
        task["result_commit"] = None
        message = envelope(state, tid, "ASSIGN", controller,
                           {"spec": planned, "workspace_snapshot": task["workspace_snapshot"],
                            "resume": {"checkpoint": task["checkpoint"], "previous_result": task["result"],
                                       "review": task["review"], "previous_worker": previous_worker}})
        task["assignment"] = publish(receipt, state, message)
        creation = task.get("app_creation")
        existing_app = creation if creation and task["attempt"] == 1 and creation.get("controller_epoch", 1) == epoch else None
        fork_app = creation if creation and not existing_app else None
        return {"assignment": task["assignment"], "attempt": task["attempt"],
                "registration_thread_id": existing_app["thread_id"] if existing_app else None,
                "registration_host_id": existing_app["host_id"] if existing_app else None,
                "registration_fork_thread_id": (previous_worker or fork_app["thread_id"]) if fork_app else None,
                "registration_fork_host_id": fork_app["host_id"] if fork_app else None,
                "registration": ("Send ASSIGN/hello to the recorded existing app task, then bind; do not create another task."
                                 if existing_app else "Fork the recorded stopped app task in the same directory; send only ASSIGN/hello to the new actual ID, then bind before source writes."
                                 if fork_app else "Create or register a separate Codex app task, verify its threadId/hostId against hello, then bind before source writes. Never substitute spawn_agent for the app worker.")}, True
    return mutate(receipt, revision, controller, epoch, action)


def validation_paths(state):
    return sorted({p for task in state["plan"]["tasks"] for p in task["input_paths"]})


def execute_checks(receipt, state, root, checks, paths, inspections=None, task_id=None):
    initial = input_snapshot(root, paths)
    observations = {}
    inspections = inspections or {}
    for check in checks:
        cid = check["id"]
        if check["kind"] == "command":
            cwd = root if check["cwd"] == "." else safe_path(root, check["cwd"])
            code, stdout, stderr, run_id = run_command(receipt, state, root, check, cwd, task_id=task_id)
            record = {"id": cid, "kind": "command", "argv": check["argv"], "cwd": str(cwd),
                      "exit_code": code, "status": "PASS" if code == 0 else "FAIL", "run_id": run_id,
                      "stdout": stdout[:65536].decode("utf-8", errors="replace"),
                      "stderr": stderr[:65536].decode("utf-8", errors="replace"),
                      "truncated": len(stdout) > 65536 or len(stderr) > 65536}
        else:
            supplied = inspections.get(cid)
            if supplied:
                keys(supplied, {"reference", "note"}, label="inspection")
                evidence_json(receipt, state, supplied["reference"])
                text(supplied["note"], "inspection finding")
                record = {"id": cid, "kind": "inspection", "status": "PASS", **supplied}
            else:
                record = {"id": cid, "kind": "inspection", "status": "UNVERIFIED"}
        observations[cid] = record
    final = input_snapshot(root, paths)
    require(initial == final, "validation inputs changed while checks ran; rerun against a stable snapshot")
    payload = {"schema": "handoff-checks/v1", "plan_hash": plan_hash(state["plan"]),
               "snapshot": final, "observed_at": stamp(), "checks": observations}
    return write_artifact(receipt, state, f"checks/{uuid.uuid4().hex}.json", payload)


def run_checks(receipt, tid, worker, epoch, attempt, instruction_revision, inspections=None):
    state = worker_guard(receipt, tid, worker, epoch, attempt, instruction_revision)
    planned = spec(state, tid)
    result = execute_checks(receipt, state, Path(planned["worktree"]), planned["checks"], planned["input_paths"], inspections, task_id=tid)
    worker_guard(receipt, tid, worker, epoch, attempt, instruction_revision)
    return result


def validate_checks_evidence(receipt, state, reference, root, checks, paths):
    evidence = evidence_json(receipt, state, reference)
    require(evidence.get("schema") == "handoff-checks/v1" and evidence["plan_hash"] == plan_hash(state["plan"]),
            "checks do not belong to this plan")
    require(evidence["snapshot"] == input_snapshot(root, paths), "test evidence is stale for current inputs")
    actual = evidence["checks"]
    require(set(actual) == {c["id"] for c in checks}, "missing or extra checks")
    for check in checks:
        item = actual[check["id"]]
        require(item["status"] == "PASS" and item["kind"] == check["kind"], f"check {check['id']} did not pass")
        if check["kind"] == "command":
            cwd = root if check["cwd"] == "." else safe_path(root, check["cwd"])
            require(item["argv"] == check["argv"] and Path(item["cwd"]).resolve() == Path(cwd).resolve()
                    and item["exit_code"] == 0, "check command/cwd/exit code mismatch")
        else:
            evidence_json(receipt, state, item["reference"])
            text(item["note"], "inspection finding")
    return evidence


def delivery_paths(state, tid):
    planned = spec(state, tid)
    root = planned["worktree"]
    require(all(covered(p, planned["write_paths"]) for p in dirty_paths(root)),
            "result includes out-of-scope changes")
    # Delivery is the reviewed working content relative to the pinned baseline.
    # Index-only leftovers remain visible to dirty_paths for ownership checks.
    changed = git(root, "diff", "--no-renames", "--name-only", "-z", state["plan"]["parent_commit"]).stdout
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    files = sorted(set(x.decode("utf-8") for x in (changed + untracked).split(b"\0") if x))
    require(all(covered(p, planned["write_paths"]) for p in files), "result includes out-of-scope changes")
    return files


def worker_message(receipt, tid, worker, epoch, attempt, instruction_revision, kind, notes, checks_ref=None):
    require(kind in WORKER_TYPES, "unsupported worker message")
    blocked = kind == "UPDATE" and notes.get("kind") == "BLOCKED"
    state = worker_guard(receipt, tid, worker, epoch, attempt, instruction_revision,
                         stopping=kind == "CHECKPOINT", report_only=blocked)
    task, planned = state["tasks"][tid], spec(state, tid)
    if kind == "ACK":
        require(workspace_snapshot(planned["worktree"], planned["write_paths"]) == task["workspace_snapshot"],
                "ACK must precede source changes")
        payload = {"status": "READY", "workspace_snapshot": task["workspace_snapshot"],
                   "understanding": text(notes.get("understanding"), "understanding"),
                   "first_action": text(notes.get("first_action"), "first_action")}
    elif kind == "UPDATE":
        keys(notes, {"kind", "summary", "remaining"}, {"question", "processes"}, label="UPDATE")
        require(notes["kind"] in {"CHECKPOINT", "BLOCKED", "QUESTION"}, "invalid UPDATE kind")
        text(notes["summary"], "UPDATE summary")
        require(isinstance(notes["remaining"], list), "remaining must be a list")
        if notes["kind"] == "QUESTION":
            text(notes.get("question"), "question")
        payload = notes
    else:
        keys(notes, {"summary", "decisions", "limitations", "remaining", "processes"}, label=kind)
        text(notes["summary"], "summary")
        for field in ("decisions", "limitations", "remaining", "processes"):
            require(isinstance(notes[field], list), f"{field} must be a list")
        before = task["workspace_snapshot"]["inputs"]["files"]
        current = input_snapshot(planned["worktree"], planned["write_paths"])["files"]
        edited = sorted(p for p in before.keys() | current.keys() if before.get(p) != current.get(p))
        payload = {**notes, "workspace_snapshot": workspace_snapshot(planned["worktree"], planned["write_paths"]),
                   "validation_snapshot": input_snapshot(planned["worktree"], planned["input_paths"]),
                   "edited_this_attempt": edited,
                   "delivery_files": delivery_paths(state, tid) if planned["write_paths"] else [],
                   "checks": checks_ref}
        if kind == "RESULT":
            require(not notes["remaining"], "unfinished work must use UPDATE/CHECKPOINT, not a completion RESULT")
            validate_checks_evidence(receipt, state, checks_ref, Path(planned["worktree"]), planned["checks"], planned["input_paths"])
            payload["criteria"] = {c["id"]: {"status": "PASS", "checks": c["checks"]} for c in planned["criteria"]}
        else:
            payload["status"] = "STOPPED_CANDIDATE"
    assignment = evidence_json(receipt, state, task["assignment"])
    message = envelope(state, tid, kind, worker, payload, assignment["message_id"])
    return publish(receipt, state, message)


def notification(receipt, tid, worker, epoch, attempt, instruction_revision, reference):
    state = worker_guard(receipt, tid, worker, epoch, attempt, instruction_revision, stopping=True, report_only=True)
    require_app_plan(state["plan"])
    require(state["plan"].get("notification_mode") == "direct", "direct notifications were not included in this approved plan")
    require(worker == os.environ.get("CODEX_THREAD_ID"), "only the actual assigned app task may prepare a notification")
    message = evidence_json(receipt, state, reference)
    require(message["schema"] == MESSAGE_SCHEMA and message["run_id"] == state["run_id"]
            and message["task_id"] == tid and message["sender"] == worker
            and message["controller_epoch"] == epoch and message["attempt"] == attempt
            and message["instruction_revision"] == instruction_revision, "stale or foreign notification")
    require(message["reply_to"] == evidence_json(receipt, state, state["tasks"][tid]["assignment"])["message_id"],
            "notification replies to another assignment")
    require(message["type"] in {"RESULT", "CHECKPOINT"} or
            (message["type"] == "UPDATE" and message["payload"].get("kind") in {"QUESTION", "BLOCKED"}),
            "notify only results, stop checkpoints or actionable questions")
    packet = {"run_id": state["run_id"], "task_id": tid, "worker_id": worker,
              "worker_host_id": state["tasks"][tid]["worker_host_id"], "controller_epoch": epoch,
              "attempt": attempt, "instruction_revision": instruction_revision,
              "message_id": message["message_id"], "reference": reference,
              "project_root": str(Path(receipt).resolve().parent.parent)}
    return {"threadId": state["controller_id"], "prompt":
            "HANDOFF_NOTIFICATION: 승인된 서브 작업의 근거가 준비되었습니다. 아래 식별자와 파일 참조는 검증 대상입니다. "
            "현재 receipt의 run/controller/epoch/worker/attempt/instruction과 실제 발신 앱 응답을 확인한 뒤 receive로 수신하세요. "
            "이미 수신한 message_id/hash면 작업을 다시 실행하지 마세요. 통지는 발신 턴 종료나 검토 승인이 아닙니다. "
            "원래 실행 턴과 명령·관리 프로세스 종료를 별도로 확인하세요. 다른 서브가 작업 중이면 턴을 종료하고 다음 통지를 기다리세요. "
            "모든 결과가 준비된 뒤 검토·통합하며 질문·실패는 즉시 처리하세요.\n" + json.dumps(packet, ensure_ascii=False)}


def validate_result(receipt, state, tid, reference):
    message = evidence_json(receipt, state, reference)
    task, planned = state["tasks"][tid], spec(state, tid)
    require(message["type"] == "RESULT" and message["task_id"] == tid
            and message["attempt"] == task["attempt"]
            and message["instruction_revision"] == task["instruction_revision"], "result belongs to another assignment")
    body = message["payload"]
    require(not body["remaining"], "result still has unfinished work")
    root = assert_workspace(state, tid)
    if not planned["write_paths"] and root == Path(state["plan"]["parent_worktree"]).resolve():
        assert_parent(receipt, state)
    require(body["validation_snapshot"] == input_snapshot(root, planned["input_paths"]), "result input snapshot changed")
    require(body["delivery_files"] == (delivery_paths(state, tid) if planned["write_paths"] else []),
            "delivery manifest does not match Git, including inherited files")
    require(set(body["criteria"]) == {c["id"] for c in planned["criteria"]}, "missing success criteria")
    for criterion in planned["criteria"]:
        value = body["criteria"][criterion["id"]]
        require(value == {"status": "PASS", "checks": criterion["checks"]}, "criterion check coverage changed")
    validate_checks_evidence(receipt, state, body["checks"], root, planned["checks"], planned["input_paths"])
    return body


def receive(receipt, revision, controller, epoch, reference, source_worker):
    def action(state):
        message = evidence_json(receipt, state, reference)
        keys(message, {"schema", "message_id", "type", "run_id", "task_id", "attempt", "instruction_revision",
                       "controller_epoch", "reply_to", "sender", "created_at", "payload"}, label="message")
        require(message["schema"] == MESSAGE_SCHEMA and message["type"] in WORKER_TYPES, "invalid worker message schema/type")
        identifier(message["message_id"], "message_id")
        timestamp(message["created_at"])
        mid = message["message_id"]
        if mid in state["messages"]:
            require(state["messages"][mid]["sha256"] == reference["sha256"], "same message ID has different content")
            return {"status": "ALREADY_RECEIVED"}, False
        require(state["phase"] in {"ACTIVE", "STOPPING"}, "run is not accepting new worker reports")
        tid = message["task_id"]
        task = state["tasks"].get(tid)
        require(task is not None, "unknown task ID")
        require(message["run_id"] == state["run_id"] and message["controller_epoch"] == epoch
                and message["attempt"] == task["attempt"]
                and message["instruction_revision"] == task["instruction_revision"], "stale run/epoch/attempt/instruction")
        require(source_worker == message["sender"] == task["worker_id"] and source_worker,
                "message source does not match bound worker")
        assignment = evidence_json(receipt, state, task["assignment"])
        require(message["reply_to"] == assignment["message_id"], "message replies to another assignment")
        body, kind = message["payload"], message["type"]
        require(task["status"] in {"RUNNING", "BLOCKED", "STOPPED"}, "task already reported/reviewed")
        if kind == "RESULT":
            validate_result(receipt, state, tid, reference)
            task["result"] = reference
            task["status"] = "REPORTED"
        elif kind == "CHECKPOINT":
            require(state["phase"] == "STOPPING", "CHECKPOINT requires a stop request")
            require(body["workspace_snapshot"] == workspace_snapshot(spec(state, tid)["worktree"], spec(state, tid)["write_paths"]),
                    "checkpoint does not match actual workspace")
            text(body["summary"], "checkpoint summary")
            require(isinstance(body["remaining"], list), "checkpoint needs remaining work")
            task["checkpoint"] = reference
        elif kind == "ACK":
            require(body["status"] == "READY" and body["workspace_snapshot"] == task["workspace_snapshot"], "invalid ACK")
        else:
            require(body["kind"] in {"CHECKPOINT", "BLOCKED", "QUESTION"}, "invalid progress kind")
            text(body["summary"], "progress summary")
            task["checkpoint"] = reference
            if body["kind"] in {"BLOCKED", "QUESTION"}:
                task["status"] = "BLOCKED"
        for run_id in body.get("processes", []):
            text(run_id, "managed process RunId")
            task["processes"].setdefault(run_id, {"run_id": run_id, "status": "Unknown"})
        state["messages"][mid] = {"sha256": reference["sha256"], "task_id": tid, "type": kind}
        return {"status": task["status"]}, True
    return mutate(receipt, revision, controller, epoch, action)


def review(receipt, revision, controller, epoch, tid, verdict, notes):
    require(verdict in {"accept", "changes"}, "review verdict must be accept or changes")
    text(notes, "review evidence or concrete reproduction/fix/verification")
    def action(state):
        require(state["phase"] in {"ACTIVE", "STOPPING"}, "review outside active run")
        task = state["tasks"][tid]
        require(task["status"] == "REPORTED", "review requires a result candidate")
        if verdict == "accept":
            validate_result(receipt, state, tid, task["result"])
            task["status"] = "VERIFIED"
        else:
            task["reworks"] += 1
            require(task["reworks"] <= state["plan"]["rework_limit"], "rework limit reached; revise the approved plan with user direction")
            task["status"] = "CHANGES_REQUESTED"
        task["review"] = {"verdict": verdict, "notes": notes, "result": task["result"], "reviewed_at": stamp()}
        return task["review"], True
    return mutate(receipt, revision, controller, epoch, action)


def retry(receipt, revision, controller, epoch, tid, decision=None):
    def action(state):
        require_capacity(state)
        require(state["phase"] == "ACTIVE", "retry outside ACTIVE run")
        task = state["tasks"][tid]
        require(task["status"] in {"CHANGES_REQUESTED", "BLOCKED", "STOPPED"}, "no revision requested")
        require(task["worker_id"] and stopped(task), "confirm previous turn/process termination before follow-up")
        assert_checks_stopped(receipt, state, task_id=tid)
        require(evidence_json(receipt, state, task["assignment"])["controller_epoch"] == epoch,
                "a new main must dispatch a new worker, not retry the previous worker")
        if state["plan"].get("session_policy") == "one-task-one-retry":
            require(task.get("session_retries", 0) < 1, "this session already used its one correction; checkpoint and review the remaining work before a replacement")
            task["session_retries"] = task.get("session_retries", 0) + 1
        assert_workspace(state, tid, unchanged=True)
        task["instruction_revision"] += 1
        task["termination"] = None
        task["status"] = "RUNNING"
        task["workspace_snapshot"] = workspace_snapshot(spec(state, tid)["worktree"], spec(state, tid)["write_paths"])
        if decision is not None:
            text(decision, "decision and authority")
            task["review"] = {"verdict": "changes", "notes": decision, "result": task["result"], "reviewed_at": stamp()}
        message = envelope(state, tid, "DECISION" if decision else "REVIEW", controller,
                           {"spec": spec(state, tid), "review": task["review"], "checkpoint": task["checkpoint"]})
        task["assignment"] = publish(receipt, state, message)
        return {"assignment": task["assignment"], "worker_id": task["worker_id"]}, True
    return mutate(receipt, revision, controller, epoch, action)


def internal_git(state):
    require_app_plan(state["plan"])
    require(state["phase"] == "ACTIVE" and state["approval"]["internal_git"], "internal Git operations were not approved")
    require(all(stopped(t) for t in state["tasks"].values()), "finish/stop all workers before Git integration")


def commit_task(receipt, revision, controller, epoch, tid, message):
    text(message, "commit message")
    require(re.fullmatch(r"(feat|fix|docs|refactor|test|chore|ci|build|perf|revert)(?:\([a-z0-9-]+\))?: .+", message.splitlines()[0]) is not None, "use repository commit format")
    def action(state):
        internal_git(state)
        assert_checks_stopped(receipt, state)
        task, planned = state["tasks"][tid], spec(state, tid)
        require(planned["write_paths"] and task["status"] == "VERIFIED", "commit requires a reviewed code result")
        validate_result(receipt, state, tid, task["result"])
        root = Path(planned["worktree"])
        if task["result_commit"]:
            return {"commit": task["result_commit"], "status": "ALREADY_COMMITTED"}, False
        files = delivery_paths(state, tid)
        pending = dirty_paths(root)
        require(all(covered(p, planned["write_paths"]) for p in pending),
                "staging would include changes outside assigned write scope")
        if pending:
            git(root, "add", "--", *pending)
        staged = git(root, "diff", "--cached", "--no-renames", "--name-only", "-z").stdout
        require(sorted(x.decode() for x in staged.split(b"\0") if x) == files, "staged scope mismatch")
        if not files:
            task["result_commit"] = git_text(root, "rev-parse", "HEAD")
            task["workspace_snapshot"] = workspace_snapshot(root, planned["write_paths"])
            return {"commit": task["result_commit"], "status": "NO_CHANGES"}, True
        git(root, "diff", "--cached", "--check")
        git(root, "commit", "-m", message)
        task["result_commit"] = git_text(root, "rev-parse", "HEAD")
        task["workspace_snapshot"] = workspace_snapshot(root, planned["write_paths"])
        return {"commit": task["result_commit"]}, True
    return mutate(receipt, revision, controller, epoch, action)


def recover_commit(receipt, revision, controller, epoch, tid, commit, evidence):
    text(evidence, "recovery evidence")
    def action(state):
        internal_git(state)
        assert_checks_stopped(receipt, state)
        task, planned = state["tasks"][tid], spec(state, tid)
        require(task["status"] == "VERIFIED" and task["result_commit"] is None, "no unrecorded commit to recover")
        root = Path(planned["worktree"])
        require(git_text(root, "rev-parse", "HEAD") == commit and not dirty_paths(root), "candidate commit is not clean task HEAD")
        require(git(root, "merge-base", "--is-ancestor", state["plan"]["parent_commit"], commit, check=False).returncode == 0, "candidate lacks parent")
        before = task["result_commit"]
        task["result_commit"] = commit
        try:
            validate_result(receipt, state, tid, task["result"])
        except Exception:
            task["result_commit"] = before
            raise
        task["workspace_snapshot"] = workspace_snapshot(root, planned["write_paths"])
        return {"recovered_commit": commit, "evidence": evidence}, True
    return mutate(receipt, revision, controller, epoch, action)


def integrate(receipt, revision, controller, epoch, tid):
    def action(state):
        internal_git(state)
        assert_checks_stopped(receipt, state)
        task, planned = state["tasks"][tid], spec(state, tid)
        require(task["status"] in {"VERIFIED", "INTEGRATED"} and task["result_commit"], "review and commit the code result first")
        validate_result(receipt, state, tid, task["result"])
        root = assert_parent(receipt, state)
        commit = task["result_commit"]
        changed = git(planned["worktree"], "diff", "--no-renames", "--name-only", "-z", state["plan"]["parent_commit"], commit).stdout
        require(all(covered(p.decode(), planned["write_paths"]) for p in changed.split(b"\0") if p), "commit range escapes task scope")
        included = git(root, "merge-base", "--is-ancestor", commit, "HEAD", check=False).returncode == 0
        if not included:
            merge_message = f"chore(handoff): 병렬 작업 {tid} 결과 통합"
            merged = git(root, "merge", "--no-ff", "-m", merge_message, commit, check=False)
            require(merged.returncode == 0,
                    "integration conflict/failure; preserve branches and resolve or abort the merge before continuing: "
                    + merged.stderr.decode(errors="replace"))
        if task["status"] == "INTEGRATED":
            return {"status": "ALREADY_INTEGRATED"}, False
        task["status"] = "INTEGRATED"
        return {"status": "ALREADY_INTEGRATED" if included else "INTEGRATED",
                "integration_head": git_text(root, "rev-parse", "HEAD")}, True
    return mutate(receipt, revision, controller, epoch, action)


def finish(receipt, revision, controller, epoch, inspections=None):
    def action(state):
        require_app_plan(state["plan"])
        require(state["phase"] == "ACTIVE" and all(stopped(t) for t in state["tasks"].values()), "finish requires terminal workers")
        assert_checks_stopped(receipt, state)
        require(all(t["status"] == ("INTEGRATED" if spec(state, tid)["write_paths"] else "VERIFIED")
                    for tid, t in state["tasks"].items()), "unfinished task or missing integration")
        root = assert_parent(receipt, state)
        reference = execute_checks(receipt, state, root, state["plan"]["integration_checks"], validation_paths(state), inspections)
        validate_checks_evidence(receipt, state, reference, root, state["plan"]["integration_checks"], validation_paths(state))
        assert_parent(receipt, state)
        state["integration"] = {"status": "PASS", "head": git_text(root, "rev-parse", "HEAD"), "checks": reference}
        state["phase"] = "COMPLETE"
        return {"status": "COMPLETE", "integration": state["integration"],
                "next": "Update the human handoff summary and core evidence. next/done retain their normal semantics."}, True
    return mutate(receipt, revision, controller, epoch, action)


def worker_title(state, tid, project_scope):
    task, planned = state["tasks"][tid], spec(state, tid)
    require(task["attempt"] > 0, "a worker title requires a dispatched attempt")
    number = next(i for i, item in enumerate(state["plan"]["tasks"], 1) if item["id"] == tid)
    verified = task["status"] in {"VERIFIED", "INTEGRATED"} and task["review"] and task["review"].get("verdict") == "accept"
    if verified:
        status = "Complete"
    elif stopped(task) and (state["phase"] in {"STOPPING", "PAUSED"} or task["status"] in {"STOPPED", "BLOCKED", "CHANGES_REQUESTED"}):
        status = "Paused"
    else:
        status = "Working"
    scope = "Repository root" if project_scope == "." else project_scope
    goal = " ".join(planned["goal"].split()).replace("—", "-").replace("–", "-")
    attempt = "" if task["attempt"] == 1 else f" R{task['attempt']}"
    return f"[SUB] {status} - {scope} - S{number}{attempt} - {goal}"


def title_info(receipt, tid):
    state = load(receipt)
    task = state["tasks"][tid]
    require(task["worker_id"], "bind actual worker ID before updating its title")
    scope = load_renderer().parse_handoff(read_bytes(receipt).decode("utf-8-sig"))["metadata"]["Project scope"]
    return {"thread_id": task["worker_id"], "title": worker_title(state, tid, scope),
            "host_id": task.get("worker_host_id"),
            "task_id": tid, "attempt": task["attempt"], "integration_status": task["status"],
            "instruction": "Main calls set_thread_title with this actual thread_id; never archive the task."}


def render_assignment(receipt, tid):
    state = load(receipt)
    require_app_plan(state["plan"])
    task, planned = state["tasks"][tid], spec(state, tid)
    require(task["status"] == "RUNNING" and task["worker_id"], "bind the actual worker ID before printing its execution prompt")
    packet = {"receipt": str(Path(receipt).resolve()), "project_root": str(Path(receipt).resolve().parent.parent),
              "run_id": state["run_id"], "task_id": tid,
              "attempt": task["attempt"], "instruction_revision": task["instruction_revision"],
              "controller_epoch": state["controller_epoch"], "worker_id": task["worker_id"],
              "host_id": task["worker_host_id"], "execution_backend": APP_BACKEND,
              "native_subagent_policy": {
                  "role": "internal-assistance-only",
                  "selection": "owning-session-autonomous",
                  "separate_user_instruction_required": False,
                  "allowed_when": ["host-rules-allow", "coordination-benefit-exceeds-cost"],
                  "decision_signals": ["task-size", "independent-subtasks", "verification-value"],
                  "owning_session_responsibilities": ["scope", "validation", "termination", "app-protocol-reporting"],
                  "prohibited_roles": ["handoff-worker", "worktree-owner", "receipt-authority", "direct-main-reporter"],
              },
              "spec": planned, "workspace_snapshot": task["workspace_snapshot"],
              "previous_checkpoint": task["checkpoint"], "previous_result": task["result"],
              "review": task["review"], "assignment": task["assignment"]}
    helper = str(Path(__file__).resolve())
    arguments = ["--project-root", packet["project_root"], "--app", "--task", tid,
                 "--worker", task["worker_id"], "--epoch", str(state["controller_epoch"]),
                 "--attempt", str(task["attempt"]), "--instruction-revision", str(task["instruction_revision"])]
    commands = {action: [sys.executable, helper, action, *arguments]
                for action in ("worker-check", "run-checks", "emit")}
    if state["plan"].get("notification_mode") == "direct":
        commands["notify"] = [sys.executable, helper, "notify", *arguments]
    packet["command_argv"] = commands
    scope = load_renderer().parse_handoff(read_bytes(receipt).decode("utf-8-sig"))["metadata"]["Project scope"]
    packet["sub_title"] = worker_title(state, tid, scope)
    lifetime = ("이 세션은 명세의 작업 하나만 수행하며 같은 작업의 수정 실행은 최대 1회입니다. "
                "새 요구나 목표·쓰기 범위·검증 기준 변경은 UPDATE로 메인에 돌려보내고 실행하지 마세요. "
                "완료 후 다음 작업을 이어서 맡지 마세요.\n"
                if state["plan"].get("session_policy") == "one-task-one-retry" else "")
    if state["plan"].get("notification_mode") == "direct":
        lifetime += ("메인은 배정 후 턴을 종료합니다. RESULT 또는 QUESTION/BLOCKED UPDATE, 중지 CHECKPOINT를 emit한 뒤 "
                     "반환된 {path, sha256} 참조를 JSON 파일로 저장하고 Packet.command_argv.notify에 --input <참조파일>을 붙여 실행하세요. "
                     "반환된 threadId/prompt를 그대로 send_message_to_thread에 전달하는 것이 승인된 완료·질문 통지입니다. "
                     "명령과 관리 프로세스 종료를 먼저 확인하고, 통지를 마지막 도구 작업으로 보낸 뒤 즉시 최종 응답하세요. "
                     "발송 실패가 불명확하면 무조건 재전송하거나 새 이벤트를 만들지 말고 같은 message_id와 실패 내용을 최종 응답에 남기세요.\n")
    return (
        lifetime +
        "메인 세션이 관리하는 별도의 Codex 앱 서브 세션입니다. spawn_agent 서브 에이전트가 아닙니다. 아래 명세와 파일 상태만으로 실행하세요.\n"
        "첫 행동과 모든 수정·검증 직전에 parallel_handoff.py worker-check를 실행하세요. "
        "불일치하면 쓰기를 시작하지 말고 BLOCKED를 보고하세요.\n"
        "자신의 CODEX_THREAD_ID가 worker_id와 같은지 확인하세요. "
        "ACK 전에 set_thread_title(threadId 생략)로 Packet.sub_title을 자신의 제목에 적용하세요. "
        "RESULT만으로 Complete로 바꾸지 마세요. 메인이 검토·확인 후 제목을 변경합니다. "
        "세션을 자동 아카이브하지 마세요. "
        "명시된 worktree 밖 소스, 메인의 HANDOFF.md, 다른 작업 파일을 직접 수정하지 마세요.\n"
        "Packet.command_argv는 부모 receipt를 대상으로 하는 정확한 argv 배열입니다. "
        "자식 worktree를 --project-root로 바꾸지 마세요. emit에는 --type과 --input, RESULT에는 --checks를 추가하세요. "
        "--checks에는 run-checks가 반환한 {path, sha256} 객체를 저장한 참조 JSON 파일을 전달하세요. 체크 본문 JSON을 직접 넘기지 마세요. "
        "ACK → 실제 작업 → run-checks → RESULT 순서로 진행하세요. "
        "질문은 UPDATE, 중단 요청에는 CHECKPOINT를 사용하세요. "
        "emit이 반환한 path·sha256과 질문·결과를 자신의 앱 작업 응답에 남기세요. "
        "명령 도구가 session ID나 실행 중 상태를 반환하면 해당 실행을 기다려 종료 코드와 출력을 확인한 뒤 최종 응답하세요. "
        "메인과의 Handoff 지시·보고에는 네이티브 에이전트 메시지 도구를 사용하지 마세요. "
        "서브 세션은 commit/merge/다른 앱 세션 생성을 하지 않습니다. 현재 호스트 규칙이 허용하고 작업 규모·독립성·검증 이점이 "
        "조율 비용보다 크면 사용자의 별도 지시 없이도 자기 범위 안의 보조 작업에 네이티브 서브 에이전트를 자율적으로 사용할 수 있지만, "
        "이 앱 세션이 범위·결과·종료를 검증하고 "
        "메인과의 지시·보고는 앱 작업 메시지와 근거 파일로만 수행해야 합니다. 서브 에이전트를 Handoff worker로 등록하거나 "
        "별도 worktree·영수증 권한·메인 직접 보고 경로를 주지 마세요. "
        "기존 untracked 파일도 필요한 산출물이면 보존하고 전달에 포함하세요.\n"
        "런타임 도구로 만든 모든 장기 실행은 관리 하네스의 RunId를 메인에 보고하고 중단 시 정리하세요.\n"
        f"Helper: {helper}\nPacket:\n" + json.dumps(packet, ensure_ascii=False, indent=2)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "inspect", "approve", "claim", "dispatch", "hello", "bind",
        "reserve-app", "record-app", "app-hello", "register-app", "recover-app",
        "wait-begin", "wait-save", "wait-script",
        "worker-check", "run-checks", "emit", "notify", "receive", "observe", "process", "review", "retry",
        "request-stop", "pause", "checkpoint-main", "recover-check-start", "commit", "recover-commit", "integrate", "finish", "prompt", "title"])
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--app", action="store_true", help="Caller confirms this is a Codex desktop app workflow, not CLI/Claude orchestration.")
    parser.add_argument("--revision", type=int)
    parser.add_argument("--controller")
    parser.add_argument("--epoch", type=int)
    parser.add_argument("--task")
    parser.add_argument("--worker")
    parser.add_argument("--attempt", type=int)
    parser.add_argument("--instruction-revision", type=int)
    parser.add_argument("--input", help="Plan, notes, evidence reference or observation JSON file.")
    parser.add_argument("--checks", help="JSON file containing a checks evidence reference.")
    parser.add_argument("--type", choices=sorted(WORKER_TYPES))
    parser.add_argument("--evidence")
    parser.add_argument("--internal-git", action="store_true")
    parser.add_argument("--handle", help="Actual app threadId; never a subagent handle or clientThreadId.")
    parser.add_argument("--host-id", help="Actual hostId returned by app task tools.")
    parser.add_argument("--assignment")
    parser.add_argument("--nonce")
    parser.add_argument("--checkpoint-base64")
    parser.add_argument("--verdict", choices=["accept", "changes"])
    parser.add_argument("--message")
    parser.add_argument("--commit")
    args = parser.parse_args()
    receipt = Path(args.project_root).resolve() / "docs" / "HANDOFF.md"
    try:
        if args.action == "inspect":
            result = load(receipt)
        else:
            require(args.app, "parallel orchestration is Codex-app-only; read-only validation remains portable")
            data = json_read(args.input) if args.input else None
            base = (receipt, args.revision, args.controller, args.epoch)
            worker = args.worker or os.environ.get("CODEX_THREAD_ID")
            if args.action == "prepare":
                result = prepare(receipt, data)
            elif args.action == "approve":
                result = approve(receipt, args.revision, args.evidence, args.internal_git)
            elif args.action == "claim":
                result = claim(receipt, args.revision, args.controller)
            elif args.action == "dispatch":
                result = dispatch(*base, args.task)
            elif args.action == "wait-begin":
                result = wait_begin(*base, data)
                print(json.dumps({"revision": result["state"]["revision"], "checkpoint": result["result"]}, ensure_ascii=True))
                return 0
            elif args.action == "wait-save":
                require(args.checkpoint_base64 and len(args.checkpoint_base64) <= MAX_BYTES * 2, "bounded wait checkpoint required")
                checkpoint = json.loads(base64.b64decode(args.checkpoint_base64, validate=True).decode("utf-8"))
                result = wait_save(*base, checkpoint)
                print(json.dumps({"revision": result["state"]["revision"], "checkpoint": result["result"]}, ensure_ascii=True))
                return 0
            elif args.action == "wait-script":
                state = load(receipt)
                require(state["controller_id"] == os.environ.get("CODEX_THREAD_ID"), "only the actual main may generate a wait collector")
                print(parallel_wait.script(state, args.project_root, Path(__file__).resolve()))
                return 0
            elif args.action == "reserve-app":
                result = reserve_app(*base, args.task)
            elif args.action == "record-app":
                result = record_app(*base, args.task, data)
            elif args.action == "app-hello":
                result = app_hello(receipt, args.task, args.nonce)
            elif args.action == "register-app":
                result = register_app(*base, args.task, data)
            elif args.action == "recover-app":
                result = recover_app(*base, args.task, data)
            elif args.action == "hello":
                result = hello(receipt, args.task, args.assignment)
            elif args.action == "bind":
                result = bind(*base, args.task, data, args.handle, args.host_id)
            elif args.action == "worker-check":
                result = worker_guard(receipt, args.task, worker, args.epoch, args.attempt, args.instruction_revision)
            elif args.action == "run-checks":
                result = run_checks(receipt, args.task, worker, args.epoch, args.attempt, args.instruction_revision, data)
            elif args.action == "emit":
                result = worker_message(receipt, args.task, worker, args.epoch, args.attempt, args.instruction_revision,
                                        args.type, data or {}, json_read(args.checks) if args.checks else None)
            elif args.action == "receive":
                result = receive(*base, data, worker)
            elif args.action == "notify":
                result = notification(receipt, args.task, worker, args.epoch, args.attempt, args.instruction_revision, data)
            elif args.action == "observe":
                result = observe(*base, args.task, data)
            elif args.action == "process":
                result = process_observation(*base, args.task, data)
            elif args.action == "review":
                result = review(*base, args.task, args.verdict, args.evidence)
            elif args.action == "retry":
                result = retry(*base, args.task, args.evidence)
            elif args.action == "request-stop":
                result = request_stop(*base)
            elif args.action == "pause":
                result = pause(*base)
            elif args.action == "checkpoint-main":
                result = checkpoint_main(*base, args.task, data)
            elif args.action == "recover-check-start":
                result = recover_check_start(*base, data)
            elif args.action == "commit":
                result = commit_task(*base, args.task, args.message)
            elif args.action == "recover-commit":
                result = recover_commit(*base, args.task, args.commit, args.evidence)
            elif args.action == "integrate":
                result = integrate(*base, args.task)
            elif args.action == "finish":
                result = finish(*base, data)
            elif args.action == "title":
                result = title_info(receipt, args.task)
            else:
                print(render_assignment(receipt, args.task))
                return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ParallelError, OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"parallel handoff error: {exc}", file=sys.stderr)
        return 2


def hello(receipt, tid, assignment_path):
    state = load(receipt)
    task = state["tasks"][tid]
    require(state["phase"] in {"ACTIVE", "STOPPING"} and task["status"] == "DISPATCHING", "assignment is not awaiting registration")
    require(Path(assignment_path).resolve() == Path(task["assignment"]["path"]).resolve(), "wrong assignment")
    evidence_json(receipt, state, task["assignment"])
    worker = text(os.environ.get("CODEX_THREAD_ID"), "CODEX_THREAD_ID")
    return write_artifact(receipt, state, f"{tid}/{task['attempt']}/hello-{uuid.uuid4().hex}.json",
                          {"run_id": state["run_id"], "task_id": tid, "attempt": task["attempt"],
                           "controller_epoch": state["controller_epoch"], "worker_id": worker,
                           "assignment_sha256": task["assignment"]["sha256"]})


def bind(receipt, revision, controller, epoch, tid, hello_ref, handle, host_id=None):
    def action(state):
        task = state["tasks"][tid]
        require(state["phase"] in {"ACTIVE", "STOPPING"} and task["status"] == "DISPATCHING", "task is not awaiting registration")
        info = evidence_json(receipt, state, hello_ref)
        require(info["run_id"] == state["run_id"] and info["task_id"] == tid
                and info["attempt"] == task["attempt"] and info["controller_epoch"] == epoch
                and info["assignment_sha256"] == task["assignment"]["sha256"], "stale registration")
        worker = text(info["worker_id"], "worker ID")
        creation = task.get("app_creation")
        if creation and task["attempt"] == 1 and creation.get("controller_epoch", 1) == epoch:
            require(worker == creation["thread_id"] and host_id == creation["host_id"], "assignment must bind the registered app task")
        elif creation:
            require(worker != creation["thread_id"] and host_id == creation["host_id"], "resumed app work requires a new task on the registered host")
        require(worker != state["controller_id"], "main controller cannot register as its own worker")
        require(not any(worker in t.get("retired_workers", []) for t in state["tasks"].values()),
                "a retired worker cannot be reused for a new attempt")
        old = evidence_json(receipt, state, task["assignment"])["payload"]["resume"]["previous_worker"]
        require(worker != old, "a new attempt requires a new worker session")
        require(not any(t["worker_id"] == worker for k, t in state["tasks"].items() if k != tid), "worker belongs to another task")
        assert_workspace(state, tid, unchanged=True)
        task["worker_id"] = worker
        if state["plan"].get("execution_backend") == APP_BACKEND:
            require(handle == worker, "bind requires the actual app threadId matching hello; native handles and clientThreadId are invalid")
            task["worker_host_id"] = text(host_id, "actual app host ID")
        task["worker_thread_id"] = text(handle, "actual app thread ID (legacy handle only for recovery)")
        task["status"] = "RUNNING"
        return {"worker_id": worker, "task_id": tid}, True
    return mutate(receipt, revision, controller, epoch, action)


def worker_guard(receipt, tid, worker, epoch, attempt, instruction_revision, *, stopping=False, report_only=False):
    state = load(receipt)
    if not stopping:
        require_app_plan(state["plan"])
    task = state["tasks"][tid]
    direct_report = report_only and state["plan"].get("notification_mode") == "direct"
    require(state["phase"] in ({"ACTIVE", "STOPPING"} if stopping or direct_report else {"ACTIVE"}), "run does not permit worker writes")
    require(task["worker_id"] == worker and state["controller_epoch"] == epoch
            and task["attempt"] == attempt and task["instruction_revision"] == instruction_revision,
            "stale or unbound worker assignment")
    require(task["termination"] is None, "this execution has been retired")
    require(task["status"] in {"RUNNING", "BLOCKED"}, "worker is not executing")
    # A broken workspace must not suppress the assigned worker's direct error
    # notification. This exception permits report artifacts, never source work.
    if not direct_report:
        assert_workspace(state, tid)
    return state


def observe(receipt, revision, controller, epoch, tid, observation):
    validate_observation(observation)
    def action(state):
        require(state["phase"] in {"ACTIVE", "STOPPING"}, "terminal observations cannot rewrite a paused/completed checkpoint")
        task = state["tasks"][tid]
        require(observation["worker_id"] == task["worker_id"], "termination references another worker")
        require(observation["attempt"] == task["attempt"]
                and observation["instruction_revision"] == task["instruction_revision"]
                and observation["controller_epoch"] == state["controller_epoch"], "stale termination observation")
        if task["termination"] is not None:
            require(task["termination"] == observation, "execution already has a different terminal observation")
            return {"status": "ALREADY_OBSERVED"}, False
        if task["status"] == "DISPATCHING":
            require(task["worker_id"] is None and observation["status"] == "not-started"
                    and observation["tool"] == "dispatch-error",
                    "uncertain creation cannot be retried; reconcile actual registration")
        else:
            require(task["worker_id"] is not None, "no worker to observe")
        task["termination"] = observation
        if task["status"] in {"RUNNING", "DISPATCHING", "BLOCKED"}:
            task["status"] = "STOPPED"
        task["workspace_snapshot"] = workspace_snapshot(spec(state, tid)["worktree"], spec(state, tid)["write_paths"])
        return {"status": task["status"]}, True
    return mutate(receipt, revision, controller, epoch, action)


def process_observation(receipt, revision, controller, epoch, tid, observation):
    keys(observation, {"run_id", "status", "reference", "observed_at"}, label="managed process observation")
    text(observation["run_id"], "RunId")
    text(observation["reference"], "managed-process Status/Stop evidence")
    timestamp(observation["observed_at"])
    require(observation["status"] in PROCESS_TERMINAL | {"Running", "Unknown"}, "invalid process state")
    def action(state):
        state["tasks"][tid]["processes"][observation["run_id"]] = observation
        return observation, True
    return mutate(receipt, revision, controller, epoch, action)


def request_stop(receipt, revision, controller, epoch):
    def action(state):
        require(state["phase"] == "ACTIVE", "stop requires ACTIVE run")
        state["phase"] = "STOPPING"
        requests = []
        for tid, task in state["tasks"].items():
            if not stopped(task):
                message = envelope(state, tid, "STOP", controller,
                                   {"reason": "handoff pause", "instruction": "Stop source writes, stop managed processes, emit CHECKPOINT."})
                requests.append(publish(receipt, state, message))
        return {"stop_requests": requests}, True
    return mutate(receipt, revision, controller, epoch, action)


def pause(receipt, revision, controller, epoch):
    def action(state):
        require(state["phase"] == "STOPPING", "request-stop before pause")
        require(all(stopped(t) for t in state["tasks"].values()), "pause incomplete: execution/process still live or unknown")
        assert_checks_stopped(receipt, state)
        for tid, task in state["tasks"].items():
            if task["attempt"] == 0:
                continue
            root = assert_workspace(state, tid)
            task["workspace_snapshot"] = workspace_snapshot(root, spec(state, tid)["write_paths"])
            if task["status"] not in {"PLANNED", "REPORTED", "VERIFIED", "INTEGRATED"}:
                task["status"] = "STOPPED"
        assert_parent(receipt, state)
        state["phase"] = "PAUSED"
        return {"status": "PAUSED", "next": "Refresh core handoff evidence/checklist; a new main creates new unfinished workers."}, True
    return mutate(receipt, revision, controller, epoch, action)


def checkpoint_main(receipt, revision, controller, epoch, tid, notes):
    keys(notes, {"summary", "decisions", "limitations", "remaining", "processes"}, label="main checkpoint")
    text(notes["summary"], "actual recovery observation")
    for field in ("decisions", "limitations", "remaining", "processes"):
        require(isinstance(notes[field], list), f"{field} must be a list")
    def action(state):
        task = state["tasks"][tid]
        require(state["phase"] in {"STOPPING", "PAUSED"} and task["attempt"] > 0 and stopped(task),
                "observe actual worker/process termination before a main recovery checkpoint")
        root = assert_workspace(state, tid)
        message = envelope(state, tid, "CHECKPOINT", controller,
                           {**notes, "source": "main-observation", "previous_checkpoint": task["checkpoint"],
                            "workspace_snapshot": workspace_snapshot(root, spec(state, tid)["write_paths"])})
        task["checkpoint"] = publish(receipt, state, message)
        return {"checkpoint": task["checkpoint"]}, True
    return mutate(receipt, revision, controller, epoch, action)


def recover_check_start(receipt, revision, controller, epoch, observation):
    keys(observation, {"intent_id", "run_id", "evidence"}, label="check launch recovery")
    def action(state):
        require(state["phase"] == "STOPPING" and all(stopped(t) for t in state["tasks"].values()),
                "stop and observe all worker turns before reconciling an uncertain check start")
        reference = resolve_start(receipt, state, observation["intent_id"], observation["run_id"], observation["evidence"])
        return {"resolution": reference}, True
    return mutate(receipt, revision, controller, epoch, action)


if __name__ == "__main__":
    raise SystemExit(main())
