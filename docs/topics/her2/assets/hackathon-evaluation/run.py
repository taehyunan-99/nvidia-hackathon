"""Collect real implementation observations; offline by default, never calls Boltz-2.

--live-reference runs ONE normal two-candidate review through the configured NAT
model. It requires separately authorized API usage. Scoring remains evidence review.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT))

from logic import env, nat_agent, structures
from logic.agent import RuleDecider
from logic.agent_session import CandidateSession, CandidateTools
from logic.contract import now_rfc3339, validate
from logic.flow import Flow
from logic.nvidia_client import CallFailed, MissingCredentials
from score import validate_dataset


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class PredictionStub:
    def __init__(self, response=None):
        self.response = response
        self.calls = []

    def predict_complex(self, polymers, **kwargs):
        self.calls.append({"polymers": polymers, "settings": kwargs, "network": False})
        if self.response is None:
            raise CallFailed("EVALUATION: prediction timeout (stub, no network)")
        return self.response

    def chat(self, *args, **kwargs):
        raise MissingCredentials("EVALUATION: legacy chat disabled; NAT uses its own client")


def tool_path(flow, candidate, *, prediction=False, opinion=None):
    session = CandidateSession(candidate)
    tools = CandidateTools(flow, session)
    replies = [tools.check_input(), tools.lookup_public_structure()]
    replies.append(tools.predict_structure("새 예측 구조를 확인한다.") if prediction
                   else tools.use_experimental_structure("일치하는 공개 실험 구조를 사용한다."))
    replies.append(tools.compare_structure())
    if opinion:
        replies.append(tools.submit_opinion(**opinion))
    flow.agent_traces[session.cid] = session.calls
    return session, replies


def snapshot(flow, client, events, observations):
    return {"result": flow._build_result(), "status": flow.run_status(),
            "candidates": flow.candidate_progress(), "progress": events,
            "decisions": [dataclasses.asdict(d) for d in flow.decider.decisions],
            "tool_traces": flow.agent_traces, "prediction_attempts": client.calls,
            "boltz_network_calls": 0, "observations": observations}


def collect(case, folder, *, live=False):
    folder.mkdir()
    faults = read(HERE / "faults.json")
    request = {"schema_version": "0.1.0", "run_id": f"run-eval-{case['case_id'].lower()}",
               "review_id": "rev-evaluation", "input": read(HERE / case["input"]),
               "settings_version": "hackathon-v1", "work_dir": str(folder.resolve()),
               "uploads": [], "data_mode": "live"}
    # data_mode=live is the existing contract's analysis mode, not proof of API use.
    save(folder / "request.json", request)
    events, observations = [], []
    def progress(event):
        events.append(event)
        with (folder / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def new_flow():
        client = PredictionStub(faults["malformed_prediction"] if case["case_id"] == "C06" else None)
        decider = None if live else RuleDecider("EVALUATION: offline baseline", decisions=[], model="offline-no-model")
        return Flow(request, client=client, decider=decider, progress=progress), client

    flow, client = new_flow()
    started = time.monotonic()
    try:
        if case["case_id"] == "C08":
            for opinion in faults["unsupported_opinions"]:
                flow, client = new_flow()
                session, replies = tool_path(flow, request["input"]["candidates"][0], opinion=opinion)
                observations.append({"submitted": opinion, "replies": replies,
                                     "terminal": session.terminal, "stored_opinions": flow.opinions})
        elif case["case_id"] == "C06":
            session, replies = tool_path(flow, request["input"]["candidates"][0], prediction=True,
                opinion={"decision": "needs_confirmation", "reason": "추가 확인이 필요하다."})
            observations.append({"replies": replies, "terminal": session.terminal})
        elif case["case_id"] == "C10":
            def interrupted(agent_flow, session, **kwargs):
                opinion = None if session.cid == "trastuzumab" else {
                    "decision": "needs_confirmation", "reason": "추가 확인이 필요하다."}
                current, replies = tool_path(agent_flow, session.candidate, opinion=opinion)
                session.__dict__.update(current.__dict__)
                observations.append({"candidate": session.cid, "injected_after": "compare_structure", "replies": replies})
                return None if session.terminal else faults["nat_interruption"]["return_reason"]
            with patch.dict(os.environ, {"LOGIC_AGENT_MODE": "nat"}), patch.object(nat_agent, "NAT_AVAILABLE", True), patch.object(nat_agent, "run_candidate", interrupted):
                flow.run()
        else:
            with patch.dict(os.environ, {"LOGIC_AGENT_MODE": "nat" if live else "rule"}):
                flow.run()
        validate({"result": flow._build_result(), "files": []}, "LogicOutput")
    except Exception as exc:
        observations.append({"harness_or_product_error": f"{type(exc).__name__}: {exc}"})
    result = snapshot(flow, client, events, observations)
    result.update(seconds=round(time.monotonic() - started, 3), execution_mode="live_nemotron_boltz_stub" if live else "offline")
    save(folder / "observation.json", result)
    print(f"{case['case_id']}: {result['status']}; {result['seconds']}s; Boltz network=0", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--live-reference", action="store_true")
    parser.add_argument("--credentials-file", type=Path)
    args = parser.parse_args()
    data = validate_dataset()
    args.out.mkdir(parents=True, exist_ok=False)
    if args.live_reference:
        if args.credentials_file:
            values = env.parse_env(args.credentials_file.read_text(encoding="utf-8"))
            for key in env.KEY_NAMES:
                if values.get(key):
                    os.environ[key] = values[key]
        if not any(os.environ.get(key) for key in env.KEY_NAMES):
            raise SystemExit("Live review requires NVIDIA credentials; no request was sent")
    else:
        for key in env.KEY_NAMES:
            os.environ.pop(key, None)
    env.ENV_PATH = args.out / "unused.env"
    paths = sorted((ROOT / "logic").glob("*.py")) + [ROOT / "logic/nat_workflow.yml", HERE / "run.py", HERE / "cases.json"]
    save(args.out / "manifest.json", {
        "created_at": now_rfc3339(), "dataset_version": data["dataset_version"],
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "mode": "live_nemotron_boltz_stub" if args.live_reference else "offline",
        "dataset_lock_sha256": hashlib.sha256((HERE / "data-lock.json").read_bytes()).hexdigest(),
        "code_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "raw_output_note": "contract data_mode=live does not mean real API calls; consult this mode",
    })
    for case in data["cases"][:1] if args.live_reference else data["cases"]:
        collect(case, args.out / case["case_id"], live=args.live_reference)


if __name__ == "__main__":
    main()
