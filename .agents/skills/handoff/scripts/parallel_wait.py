"""Visible wait checkpoints; app tools still run in the main's functions.exec cell."""
import json
from pathlib import Path
import time
import re
import sys
import uuid
from parallel_contract import require, keys, text, integer, plan_hash, MESSAGE_SCHEMA, json_read, ParallelError


def validate_checkpoint(value):
    keys(value, {"id", "binding", "targets", "cursors", "completed", "status", "reason",
                 "calls", "mode", "review_on", "deadline_ms", "evidence"}, label="wait checkpoint")
    text(value["id"], "batch ID")
    require(value["mode"] in {"tools", "user"}, "unsupported wait mode")
    require(value["review_on"] in {"batch", "first"}, "unsupported review policy")
    require(value["status"] in {"waiting", "ready", "attention"}, "invalid wait status")
    text(value["evidence"], "wait policy/turn identification evidence")
    integer(value["calls"], "wait tool calls")
    integer(value["deadline_ms"], "wait deadline", 1)
    require(isinstance(value["targets"], list) and value["targets"], "wait targets required")
    ids = []
    for target in value["targets"]:
        keys(target, {"task_id", "thread_id", "host_id", "turn_id", "attempt", "instruction_revision"}, label="wait target")
        for field in ("task_id", "thread_id", "host_id", "turn_id"):
            text(target[field], field)
        integer(target["attempt"], "attempt", 1)
        integer(target["instruction_revision"], "instruction revision", 1)
        ids.append(target["task_id"])
    require(len(set(ids)) == len(ids), "duplicate wait target")
    require(isinstance(value["cursors"], dict) and value["cursors"].keys() <= set(ids), "invalid cursor targets")
    require(all(isinstance(v, str) and v for v in value["cursors"].values()), "invalid opaque cursor")
    require(isinstance(value["completed"], list) and len(set(value["completed"])) == len(value["completed"])
            and set(value["completed"]) <= set(ids), "invalid completion candidates")
    if value["status"] == "ready":
        require(value["completed"] and (value["review_on"] == "first" or set(value["completed"]) == set(ids)), "batch is not ready")
    if value["status"] == "attention":
        text(value["reason"], "wait attention reason")


def binding(state):
    return {"run_id": state["run_id"], "controller_id": state["controller_id"],
            "epoch": state["controller_epoch"], "plan_hash": plan_hash(state["plan"])}


def assert_current(state, checkpoint):
    validate_checkpoint(checkpoint)
    require(state["phase"] == "ACTIVE" and checkpoint["binding"] == binding(state), "stale wait controller/run/plan")
    for target in checkpoint["targets"]:
        task = state["tasks"][target["task_id"]]
        require(task["worker_id"] == target["thread_id"] and task["worker_host_id"] == target["host_id"]
                and task["attempt"] == target["attempt"] and task["instruction_revision"] == target["instruction_revision"], "wait target assignment changed")


def begin(state, request):
    keys(request, {"turns", "deadline_ms", "evidence"}, {"mode", "review_on"}, label="wait request")
    targets = []
    for tid, turn in request["turns"].items():
        task = state["tasks"][tid]
        require(task["worker_id"] and task["status"] in {"RUNNING", "BLOCKED", "REPORTED"}, "wait only on dispatched app executions")
        targets.append({"task_id": tid, "thread_id": task["worker_id"], "host_id": task["worker_host_id"],
                        "turn_id": turn, "attempt": task["attempt"], "instruction_revision": task["instruction_revision"]})
    result = {"id": uuid.uuid4().hex, "binding": binding(state), "targets": targets, "cursors": {},
              "completed": [], "status": "waiting", "reason": None, "calls": 0,
              "mode": request.get("mode", "tools"), "review_on": request.get("review_on", "batch"),
              "deadline_ms": request["deadline_ms"], "evidence": request["evidence"]}
    assert_current(state, result)
    require(result["deadline_ms"] > int(time.time() * 1000), "wait deadline has expired")
    if any(state["tasks"][t["task_id"]]["status"] == "BLOCKED" for t in targets):
        result.update(status="attention", reason="a selected worker is already blocked")
    return result


def save(receipt, state, proposed):
    old = state["wait_batch"]
    assert_current(state, proposed)
    for field in ("id", "binding", "targets", "mode", "review_on", "deadline_ms", "evidence"):
        require(old[field] == proposed[field], "wait checkpoint identity/policy changed")
    require(set(old["completed"]) <= set(proposed["completed"]) and proposed["calls"] >= old["calls"], "wait checkpoint regressed")
    require(old["status"] == "waiting" or old == proposed, "wait outcome already delivered; inspect before a new batch")
    # A worker's immutable QUESTION/BLOCKED report is a wake hint, never acceptance.
    for target in proposed["targets"]:
        directory = Path(receipt).parent / "handoff-runs" / state["run_id"] / target["task_id"] / str(target["attempt"])
        for path in directory.glob("*.json"):
            if not re.fullmatch(r"[0-9a-f]{32}\.json", path.name):
                continue
            try:
                msg = json_read(path)
            except (OSError, ParallelError):
                continue  # A report may still be publishing; source review never relies on this hint.
            if (msg.get("schema") == MESSAGE_SCHEMA and msg.get("type") == "UPDATE"
                    and msg.get("run_id") == state["run_id"] and msg.get("sender") == target["thread_id"]
                    and msg.get("task_id") == target["task_id"] and msg.get("attempt") == target["attempt"]
                    and msg.get("controller_epoch") == state["controller_epoch"]
                    and msg.get("instruction_revision") == target["instruction_revision"]
                    and msg.get("message_id") not in state["messages"]
                    and msg.get("payload", {}).get("kind") in {"QUESTION", "BLOCKED"}):
                proposed = {**proposed, "status": "attention", "reason": "inspect worker request: " + str(path)}
    return proposed


def script(state, project_root, helper):
    checkpoint = state["wait_batch"]
    assert_current(state, checkpoint)
    require(checkpoint["mode"] == "tools", "manual wait stays ACTIVE and resumes only on explicit user input")
    project_root = Path(project_root).resolve()
    # Checkpoint JSON is base64 data, never shell source. Only the supported tools are invoked.
    command = "& '" + sys.executable.replace("'", "''") + "' -X utf8 '" + str(helper).replace("'", "''") + "' wait-save --app --project-root '" + str(project_root).replace("'", "''") + "'"
    js = Path(__file__).with_suffix(".js").read_text(encoding="utf-8")
    return '// @exec: {"yield_time_ms": 60000, "max_output_tokens": 1500}\n' + "const module = {exports:{}};\n" + js + "\n" + f"let revision = {state['revision']};\nconst checkpoint = {json.dumps(checkpoint)};\n" + r'''
function base64(value) {
  const raw = JSON.stringify(value).replace(/[\u007f-\uffff]/g, c => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0"));
  const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  let result = "";
  for (let i=0; i<raw.length; i+=3) {
    const n=(raw.charCodeAt(i)<<16)|((raw.charCodeAt(i+1)||0)<<8)|(raw.charCodeAt(i+2)||0);
    result += chars[(n>>>18)&63]+chars[(n>>>12)&63]+(i+1<raw.length?chars[(n>>>6)&63]:"=")+(i+2<raw.length?chars[n&63]:"=");
  }
  return result;
}
''' + f"const command = {json.dumps(command)};\n" + r'''
text(await module.exports.waitForBatch(checkpoint, {
  wait: args => tools.mcp__codex_app__wait_threads(args),
  save: async next => {
    const controller = "'" + checkpoint.binding.controller_id.replace(/'/g, "''") + "'";
    let result = await tools.exec_command({cmd: command + " --revision " + revision + " --controller " + controller + " --epoch " + checkpoint.binding.epoch + " --checkpoint-base64 " + base64(next), max_output_tokens: 5000});
    let output = result.output || "";
    while (result.session_id && result.exit_code == null) {
      result = await tools.write_stdin({session_id: result.session_id, chars: "", yield_time_ms: 50000, max_output_tokens: 5000});
      output += result.output || "";
    }
    if (result.exit_code !== 0) throw new Error("Checkpoint save did not finish successfully; reconcile its actual command before retry.");
    const saved = JSON.parse(output);
    revision = saved.revision;
    return saved.checkpoint;
  }
}));
'''
