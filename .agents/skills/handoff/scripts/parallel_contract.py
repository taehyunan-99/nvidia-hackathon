"""Parallel handoff contracts. The agent drives app tools; this code runs no model.

HANDOFF.md is the only current state. Reports are immutable evidence and locks
are cooperative execution guards, not security boundaries.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import uuid

SCHEMA = "handoff-parallel/v1"
APP_BACKEND = "app-threads"
MESSAGE_SCHEMA = "handoff-parallel-message/v1"
HEADING = "### Parallel execution"
FENCE = chr(96) * 3
BLOCK = re.compile(r"(?ms)^### Parallel execution\n\n" + FENCE + r"json\n(.*?)\n" + FENCE + r"\n?")
PHASES = {"PLANNED", "ACTIVE", "STOPPING", "PAUSED", "COMPLETE"}
STATUSES = {"PLANNED", "DISPATCHING", "RUNNING", "REPORTED", "VERIFIED",
            "INTEGRATED", "STOPPED", "BLOCKED", "CHANGES_REQUESTED"}
TERMINAL = {"completed", "interrupted", "failed", "not-started"}
PROCESS_TERMINAL = {"Completed", "Stopped", "TimedOut", "Failed"}
MODEL_EFFORTS = {"gpt-5.6-luna": {"medium", "high"}, "gpt-5.6-sol": {"low", "medium"},
                "gpt-5.6-terra": {"medium", "high", "xhigh"}, "gpt-6-astra": {"medium", "high"}}
MAX_BYTES = 1_048_576


class ParallelError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ParallelError(message)


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}: expected nonempty text")
    return value


def keys(value, required, optional=(), label="object"):
    require(isinstance(value, dict), f"{label}: expected object")
    require(set(required) <= value.keys(), f"{label}: missing {sorted(set(required) - value.keys())}")
    require(value.keys() <= set(required) | set(optional), f"{label}: unknown {sorted(value.keys() - set(required) - set(optional))}")


def identifier(value, label):
    text(value, label)
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value) is not None, f"{label}: invalid ID")
    return value


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, f"{label}: expected integer >= {minimum}")


def stamp():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(text(value, "timestamp"))
        require(parsed.utcoffset() is not None, "timestamp requires timezone")
    except ValueError as exc:
        raise ParallelError("invalid timestamp") from exc


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def relative(value):
    text(value, "relative path")
    p = PurePosixPath(value.rstrip("/"))
    require(not p.is_absolute() and p.parts and all(x.casefold() not in {".", "..", ".git"} and x == x.rstrip(" .") for x in p.parts),
            f"unsafe relative path: {value}")
    require("\\" not in value and ":" not in value and not any(c in value for c in "*?[]\n\r"),
            f"literal POSIX path required: {value}")
    require(p.as_posix() == value.rstrip("/"), f"noncanonical path: {value}")
    return p.as_posix()


def covered(file, scopes):
    name = relative(file).casefold()
    return any(name == relative(s).casefold() or name.startswith(relative(s).casefold() + "/") for s in scopes)


def overlaps(left, right):
    return any(covered(x, right) for x in left) or any(covered(x, left) for x in right)


def safe_path(root, value, *, absolute=False):
    root = Path(root).absolute()
    candidate = Path(value).absolute() if absolute else root / relative(value)
    for part in (candidate, *candidate.parents):
        if sys.platform == "darwin" and str(part) in {"/var", "/tmp", "/etc"} and part.resolve() == Path("/private" + str(part)):
            continue  # macOS system aliases; user-controlled links remain forbidden.
        require(not part.is_symlink() and not (hasattr(part, "is_junction") and part.is_junction()),
                f"link/reparse path is not allowed: {part}")
        if part.exists():
            require(not (getattr(part.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT),
                    f"link/reparse path is not allowed: {part}")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ParallelError(f"path escapes allowed root: {candidate}") from exc
    return resolved


def read_bytes(path):
    path = Path(path)
    safe_path(path.parent, str(path), absolute=True)
    require(path.is_file() and path.stat().st_size <= MAX_BYTES, f"missing or oversized file: {path}")
    return path.read_bytes()


def json_read(path):
    try:
        return json.loads(read_bytes(path).decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ParallelError(f"invalid JSON: {path}") from exc


def git(root, *args, check=True):
    run = subprocess.run(["git", "--literal-pathspecs", "-C", str(root), *args], capture_output=True, timeout=60)
    if check:
        require(run.returncode == 0, f"git {' '.join(args)}: {run.stderr.decode(errors='replace').strip()}")
    return run


def git_text(root, *args):
    return git(root, *args).stdout.decode("utf-8").strip()


def repository(root):
    actual = Path(git_text(root, "rev-parse", "--show-toplevel")).resolve()
    safe_path(actual, str(actual), absolute=True)
    return actual


def common_dir(root):
    return Path(git_text(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()


def plan_hash(plan):
    return digest(plan)


def validate_checks(checks, label):
    require(isinstance(checks, list) and checks, f"{label}: checks required")
    ids = set()
    for check in checks:
        keys(check, {"id", "kind"}, {"argv", "cwd", "timeout_seconds", "instruction"}, label="check")
        cid = identifier(check["id"], "check.id")
        require(cid not in ids, f"{label}: duplicate check")
        ids.add(cid)
        require(check["kind"] in {"command", "inspection"}, "check.kind must be command or inspection")
        if check["kind"] == "command":
            require(isinstance(check.get("argv"), list) and check["argv"] and all(isinstance(x, str) and "\0" not in x for x in check["argv"]),
                    "check.argv must be a nonempty string array")
            require(check.get("cwd") == "." or bool(relative(check.get("cwd"))), "check.cwd required")
            integer(check.get("timeout_seconds"), "timeout_seconds", 1)
            require(check["timeout_seconds"] <= 3600, "check timeout exceeds one hour")
        else:
            text(check.get("instruction"), "inspection instruction")


def validate_plan(plan):
    keys(plan, {"mode", "stage_id", "goal", "parent_worktree", "parent_branch", "parent_commit",
                "tasks", "integration_checks", "rework_limit"}, {"execution_backend", "max_parallel", "app_project", "session_policy", "notification_mode"}, label="plan")
    if "notification_mode" in plan:
        require(plan["notification_mode"] in {"direct", "tools", "user"}, "unsupported notification mode")
    if "session_policy" in plan:
        require(plan["session_policy"] == "one-task-one-retry", "unsupported session lifetime policy")
    if "app_project" in plan:
        keys(plan["app_project"], {"project_id", "host_id", "path"}, label="app project")
        for field in ("project_id", "host_id", "path"):
            text(plan["app_project"][field], "app project " + field)
        require(Path(plan["app_project"]["path"]).is_absolute(), "saved project path must be absolute")
        require(plan.get("execution_backend") == APP_BACKEND and plan["mode"] == "auto", "app worktrees require automatic app tasks")
    if "execution_backend" in plan:
        require(plan["execution_backend"] == APP_BACKEND, "execution_backend must be app-threads; subagents are not supported")
        integer(plan.get("max_parallel"), "max_parallel", 1)
    else:
        require("max_parallel" not in plan, "max_parallel requires an explicit execution_backend")
    require(plan["mode"] in {"auto", "manual"}, "mode must be auto or manual")
    require(re.fullmatch(r"S[1-9][0-9]*", plan["stage_id"]) is not None, "stage_id must be S1, S2, ...")
    text(plan["goal"], "goal")
    require(Path(plan["parent_worktree"]).is_absolute(), "parent_worktree must be absolute")
    require(re.fullmatch(r"(feat|feature|fix|docs|chore|hotfix|refactor|test|ci|build|perf)/[a-z0-9-]+(?:/[a-z0-9-]+)?", plan["parent_branch"]) is not None,
            "parent_branch must be a task branch")
    require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", plan["parent_commit"]) is not None, "full parent_commit required")
    integer(plan["rework_limit"], "rework_limit")
    tasks = plan["tasks"]
    require(isinstance(tasks, list) and len(tasks) >= 2, "parallel plan requires at least two tasks")
    seen = set()
    for task in tasks:
        keys(task, {"id", "goal", "context", "write_paths", "input_paths", "worktree", "branch",
                    "model", "reasoning", "criteria", "checks", "depends_on"}, label="task")
        tid = identifier(task["id"], "task.id")
        require(tid not in seen, f"duplicate task: {tid}")
        seen.add(tid)
        text(task["goal"], f"{tid}.goal")
        require(isinstance(task["context"], list) and all(isinstance(x, str) and x.strip() for x in task["context"]),
                f"{tid}.context must be a list of decisions/references")
        require(task["model"] in MODEL_EFFORTS and task["reasoning"] in MODEL_EFFORTS[task["model"]],
                f"{tid}: unsupported model/reasoning policy")
        app_workspace = task["worktree"] is None
        if app_workspace:
            require("app_project" in plan and task["write_paths"], "unresolved worktree requires an approved app project and writer role")
        else:
            require(Path(task["worktree"]).is_absolute(), f"{tid}.worktree must be absolute")
        for field in ("write_paths", "input_paths"):
            require(isinstance(task[field], list), f"{tid}.{field} must be a list")
            normalized = [relative(x).casefold() for x in task[field]]
            require(len(set(normalized)) == len(normalized), f"{tid}.{field}: duplicate paths")
        require(task["input_paths"], f"{tid}: declare validation inputs")
        require(all(covered(x, task["input_paths"]) for x in task["write_paths"]),
                f"{tid}: validation inputs must cover write scope")
        if task["write_paths"]:
            require(app_workspace or Path(task["worktree"]).resolve() != Path(plan["parent_worktree"]).resolve(), f"{tid}: writers require an isolated worktree")
            require(re.fullmatch(r"(feat|feature|fix|docs|chore|hotfix|refactor|test|ci|build|perf)/[a-z0-9-]+(?:/[a-z0-9-]+)?", task["branch"]) is not None,
                    f"{tid}: task branch required")
            require(task["branch"] != plan["parent_branch"], f"{tid}: writer needs a distinct task branch")
        validate_checks(task["checks"], f"{tid}.checks")
        ids = {c["id"] for c in task["checks"]}
        require(isinstance(task["criteria"], list) and task["criteria"], f"{tid}: criteria required")
        criterion_ids = set()
        for criterion in task["criteria"]:
            keys(criterion, {"id", "description", "checks"}, label="criterion")
            cid = identifier(criterion["id"], "criterion.id")
            require(cid not in criterion_ids, f"{tid}: duplicate criterion")
            criterion_ids.add(cid)
            text(criterion["description"], "criterion.description")
            require(isinstance(criterion["checks"], list) and criterion["checks"] and set(criterion["checks"]) <= ids,
                    f"{tid}: criterion must reference declared checks")
        require(task["depends_on"] == [], f"{tid}: only independent tasks are supported; put dependencies in the next stage")
    for task in tasks:
        require(set(task["depends_on"]) <= seen, f"{task['id']}: unknown dependency")
    def visit(tid, stack):
        require(tid not in stack, "task dependency cycle")
        for dep in next(t for t in tasks if t["id"] == tid)["depends_on"]:
            visit(dep, stack | {tid})
    for task in tasks:
        visit(task["id"], set())
    for i, left in enumerate(tasks):
        for right in tasks[i + 1:]:
            require(not overlaps(left["write_paths"], right["write_paths"]), f"overlapping writers: {left['id']}, {right['id']}")
            require(not overlaps(left["write_paths"], right["input_paths"])
                    and not overlaps(right["write_paths"], left["input_paths"]),
                    f"cross-task read/write dependency: {left['id']}, {right['id']}")
            if left["write_paths"] and right["write_paths"]:
                require(left["branch"] != right["branch"], "writers cannot share a branch")
                if left["worktree"] is not None and right["worktree"] is not None:
                    require(Path(left["worktree"]).resolve() != Path(right["worktree"]).resolve(), "writers cannot share a worktree/index")
    validate_checks(plan["integration_checks"], "integration_checks")


TASK_FIELDS = {"attempt", "instruction_revision", "status", "worker_id", "worker_thread_id",
               "termination", "processes", "workspace_snapshot", "result", "review", "checkpoint",
               "result_commit", "assignment", "reworks"}


def validate_observation(observation, *, app_only=False):
    keys(observation, {"worker_id", "turn_id", "status", "tool", "observed_at", "reference",
                       "attempt", "instruction_revision", "controller_epoch"}, label="termination observation")
    for field in ("attempt", "instruction_revision", "controller_epoch"):
        integer(observation[field], field, 1)
    require(observation["status"] in TERMINAL, "observation is not terminal")
    require(observation["tool"] in {"read_thread", "wait_threads", "list_agents", "interrupt_agent", "dispatch-error"},
            "observation must cite an actual app/native tool")
    if app_only:
        require(observation["tool"] in {"read_thread", "wait_threads", "dispatch-error"},
                "app-threads requires app task observations; subagent tools cannot prove session termination")
    text(observation["turn_id"], "turn ID or native execution reference")
    text(observation["reference"], "tool result reference")
    timestamp(observation["observed_at"])


def stopped(task):
    if task.get("app_creation", {}).get("status") == "pending":
        return False
    execution_done = task["attempt"] == 0 or (task["termination"] is not None and task["termination"]["status"] in TERMINAL)
    return execution_done and all(p.get("status") in PROCESS_TERMINAL for p in task["processes"].values())


def spec(state, tid):
    require(tid in state["tasks"], f"unknown task: {tid}")
    planned = next(t for t in state["plan"]["tasks"] if t["id"] == tid)
    if planned["worktree"] is None:
        return {**planned, "worktree": state["tasks"][tid].get("app_creation", {}).get("worktree")}
    return planned


def validate_state(state):
    keys(state, {"schema", "run_id", "phase", "revision", "controller_epoch", "controller_id",
                 "plan", "approval", "tasks", "messages", "integration", "parent_inputs"}, {"wait_batch"}, label="parallel state")
    if "wait_batch" in state:
        from parallel_wait import validate_checkpoint
        validate_checkpoint(state["wait_batch"])
    require(state["schema"] == SCHEMA, "unsupported parallel schema")
    identifier(state["run_id"], "run_id")
    require(state["phase"] in PHASES, "invalid run phase")
    integer(state["revision"], "revision")
    integer(state["controller_epoch"], "controller_epoch")
    require(state["controller_id"] is None or isinstance(state["controller_id"], str), "invalid controller_id")
    validate_plan(state["plan"])
    require(isinstance(state["tasks"], dict) and set(state["tasks"]) == {t["id"] for t in state["plan"]["tasks"]},
            "runtime task IDs must equal planned task IDs")
    require(isinstance(state["messages"], dict), "messages must be an ID/digest index")
    require(isinstance(state["parent_inputs"], dict), "parent_inputs required")
    if state["approval"] is not None:
        keys(state["approval"], {"plan_hash", "evidence", "internal_git"}, label="approval")
        require(state["approval"]["plan_hash"] == plan_hash(state["plan"]), "approval is stale after plan change")
        text(state["approval"]["evidence"], "approval evidence")
        require(type(state["approval"]["internal_git"]) is bool, "internal_git must be boolean")
    if state["phase"] != "PLANNED":
        require(state["approval"] is not None and state["controller_id"] and state["controller_epoch"] > 0,
                "started run requires approval and controller")
    for tid, task in state["tasks"].items():
        keys(task, TASK_FIELDS, {"retired_workers", "worker_host_id", "app_creation", "session_retries"}, label=f"runtime {tid}")
        if "session_retries" in task:
            integer(task["session_retries"], "same-session corrections")
            require(task["session_retries"] <= 1, "same-session correction limit exceeded")
        if "app_creation" in task:
            creation = task["app_creation"]
            keys(creation, {"nonce", "status"}, {"worktree", "thread_id", "host_id", "evidence", "registration", "response", "controller_epoch"}, label="app creation")
            if "controller_epoch" in creation:
                integer(creation["controller_epoch"], "creation controller epoch", 1)
            if "response" in creation:
                keys(creation["response"], {"id", "id_kind", "host_id", "reference"}, label="creation response")
                require(creation["response"]["id_kind"] in {"clientThreadId", "threadId"}, "invalid creation response ID kind")
                text(creation["response"]["id"], "returned creation ID")
                text(creation["response"]["reference"], "creation tool result reference")
                require(creation["response"]["host_id"] == state["plan"]["app_project"]["host_id"], "creation response host mismatch")
            identifier(creation["nonce"], "creation nonce")
            require(creation["status"] in {"pending", "registered"}, "invalid creation status")
            require("app_project" in state["plan"], "app creation requires approved app project")
            if creation["status"] == "registered":
                require(Path(creation["worktree"]).is_absolute(), "registered worktree must be absolute")
                text(creation["thread_id"], "actual app thread ID")
                require(creation["host_id"] == state["plan"]["app_project"]["host_id"], "app host differs from approval")
                require(isinstance(creation["registration"], dict), "harness registration required")
                require(isinstance(creation["evidence"], dict), "app tool evidence required")
        retired = task.get("retired_workers", [])
        require(isinstance(retired, list) and all(isinstance(x, str) and x for x in retired)
                and len(retired) == len(set(retired)), "retired_workers must contain unique worker IDs")
        integer(task["attempt"], "attempt")
        integer(task["instruction_revision"], "instruction_revision")
        integer(task["reworks"], "reworks")
        require(task["status"] in STATUSES, f"{tid}: invalid status")
        require(isinstance(task["processes"], dict), "processes must be a RunId map")
        if task["worker_id"] is not None:
            text(task["worker_id"], "worker ID")
            require(task["attempt"] > 0, "worker requires an attempt")
            if state["plan"].get("execution_backend") == APP_BACKEND:
                require(task["worker_thread_id"] == task["worker_id"], "worker_thread_id must equal the actual app thread ID")
                text(task.get("worker_host_id"), "actual app host ID")
        if task["termination"] is not None:
            validate_observation(task["termination"], app_only=state["plan"].get("execution_backend") == APP_BACKEND)
            require(task["termination"]["worker_id"] == task["worker_id"], "termination worker mismatch")
        if task["status"] in {"REPORTED", "VERIFIED", "INTEGRATED"}:
            require(isinstance(task["result"], dict), "reported status requires result evidence")
        if task["status"] in {"VERIFIED", "INTEGRATED"}:
            require(isinstance(task["review"], dict) and task["review"].get("verdict") == "accept", "verified status requires main review")
    if state["phase"] in {"PAUSED", "COMPLETE"}:
        require(all(stopped(t) for t in state["tasks"].values()), "all previous executions/processes must be stopped")
    if state["phase"] == "COMPLETE":
        require(all(t["status"] == ("INTEGRATED" if spec(state, tid)["write_paths"] else "VERIFIED")
                    for tid, t in state["tasks"].items()), "complete run has unfinished/unintegrated tasks")
        require(isinstance(state["integration"], dict) and state["integration"].get("status") == "PASS", "complete run requires integration verification")


def extract(text_value):
    normalized = text_value.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(BLOCK.finditer(normalized))
    require(normalized.count(HEADING) == len(matches), "malformed Parallel execution block")
    require(len(matches) <= 1, "duplicate Parallel execution blocks")
    if not matches:
        return None
    try:
        state = json.loads(matches[0].group(1))
    except json.JSONDecodeError as exc:
        raise ParallelError("parallel block is not valid JSON") from exc
    validate_state(state)
    return state


def without_block(text_value):
    return BLOCK.sub("", text_value.replace("\r\n", "\n"))


def embed(text_value, state):
    validate_state(state)
    normalized = text_value.replace("\r\n", "\n")
    block = HEADING + "\n\n" + FENCE + "json\n" + json.dumps(state, ensure_ascii=False, sort_keys=True, indent=2) + "\n" + FENCE + "\n"
    if BLOCK.search(normalized):
        return BLOCK.sub(lambda _: block, normalized)
    require(HEADING not in normalized, "malformed existing parallel block")
    state_start = normalized.index("## State verification\n")
    marker_pos = normalized.find("### Handoff completion checklist", state_start)
    require(marker_pos >= 0, "parallel receipt requires the existing completion checklist")
    return normalized[:marker_pos] + block + "\n" + normalized[marker_pos:]


def load_renderer():
    file = Path(__file__).with_name("render_handoff.py")
    module_spec = importlib.util.spec_from_file_location("_parallel_renderer", file)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@contextmanager
def transaction(receipt):
    receipt = Path(receipt).absolute()
    safe_path(receipt.parent, str(receipt), absolute=True)
    lock = receipt.with_name(receipt.name + ".parallel.lock")
    token = uuid.uuid4().hex
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ParallelError(f"receipt is locked; never auto-steal a stale lock: {lock}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"token": token, "created_at": stamp(), "receipt": str(receipt)}, stream)
        before = read_bytes(receipt)
        yield before
    finally:
        if lock.is_file() and not lock.is_symlink() and json_read(lock).get("token") == token:
            lock.unlink()


def atomic_write(receipt, before, after):
    receipt = Path(receipt)
    require(read_bytes(receipt) == before, "receipt changed concurrently")
    require(len(after) <= MAX_BYTES, "receipt exceeds size limit; reduce context and reference artifacts")
    fd, name = tempfile.mkstemp(prefix=".handoff-write-", dir=receipt.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        require(read_bytes(receipt) == before, "receipt changed before replace")
        os.replace(temporary, receipt)
    finally:
        if temporary.exists():
            temporary.unlink()


def input_snapshot(root, paths):
    root = repository(root)
    records = {}
    for raw in paths:
        rel = relative(raw)
        target = safe_path(root, rel)
        if target.is_dir():
            names = git(root, "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", rel).stdout
            files = sorted(set(x.decode("utf-8") for x in names.split(b"\0") if x))
            # Missing index entries are deletions, not current directory content.
            # Staging/committing a deletion must not invalidate source evidence.
            files = [name for name in files if safe_path(root, name).is_file()]
            if not files:
                records[rel] = {"kind": "missing"}
        else:
            files = [rel]
        for name in files:
            item = safe_path(root, name)
            records[name] = {"kind": "file", "sha256": sha(item.read_bytes())} if item.is_file() else {"kind": "missing"}
    return {"id": digest(records), "files": records}


def dirty_paths(root):
    tracked = git(root, "diff", "--no-renames", "--name-only", "-z", "HEAD").stdout
    staged = git(root, "diff", "--cached", "--no-renames", "--name-only", "-z").stdout
    untracked = git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout
    return sorted(set(x.decode("utf-8") for x in (tracked + staged + untracked).split(b"\0") if x))


def workspace_snapshot(root, paths):
    root = repository(root)
    require(not git_text(root, "diff", "--name-only", "--diff-filter=U"), "unmerged files in worktree")
    selected = [p for p in dirty_paths(root) if covered(p, paths)]
    index = git(root, "ls-files", "--stage", "-z", "--", *paths).stdout.decode("utf-8") if paths else ""
    data = {"head": git_text(root, "rev-parse", "HEAD"), "branch": git_text(root, "branch", "--show-current"),
            "dirty_paths": selected, "index": index, "inputs": input_snapshot(root, paths)}
    return {**data, "id": digest(data)}


def artifact_root(receipt, state):
    return Path(receipt).parent / "handoff-runs" / state["run_id"]


def write_artifact(receipt, state, filename, value):
    root = artifact_root(receipt, state)
    file = safe_path(Path(receipt).parent, str(root / relative(filename)), absolute=True)
    file.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    require(len(raw) <= MAX_BYTES, "artifact too large")
    with file.open("xb") as stream:
        stream.write(raw)
    return {"path": str(file), "sha256": sha(raw)}


def evidence_json(receipt, state, reference):
    keys(reference, {"path", "sha256"}, label="evidence reference")
    file = safe_path(artifact_root(receipt, state), reference["path"], absolute=True)
    raw = read_bytes(file)
    require(sha(raw) == reference["sha256"], "evidence file changed")
    return json.loads(raw.decode("utf-8-sig"))
