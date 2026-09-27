"""Frozen eight-case benchmark of the real run_flow, with real/cached NVIDIA responses.

prepare -> run CASE nat -> run CASE rule -> summary. No automatic retry or fake prediction.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT))
from logic import contacts, structures
from logic.agent import DEFAULT_MODEL, RuleDecider
from logic.env import load_env
from logic.flow import run_flow
from logic.nvidia_client import NvidiaClient, MissingCredentials
from logic.tests.test_flow import candidate, make_request, entity_sequence
from logic.tests.test_flow_decisions import _filler

WORK = ROOT / "work/agent-benchmark"
MANIFEST = HERE / "generated/agent-benchmark-manifest.json"
RESULTS = HERE / "generated/agent-benchmark-results.jsonl"
SOURCES = {"8JYR": {"target": "1", "heavy": "2", "light": "3"},
           "3N85": {"target": "1", "heavy": "3", "light": "2"}}
CODE = sorted((ROOT / "logic").glob("*.py")) + [ROOT / "logic/nat_workflow.yml"]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def prepare():
    if MANIFEST.exists():
        raise SystemExit("Manifest already frozen; do not rewrite after observing outcomes.")
    cases = []
    for pid in ("1N8Z", "1S78", "8JYR", "3N85"):
        if pid in SOURCES:
            p = WORK / "sources" / f"{pid}.cif"
            entities, _ = structures.parse_entities(p.read_text())
            by_id = {e.entity_id: e for e in entities}
            seq = {role: by_id[eid].sequence for role, eid in SOURCES[pid].items()}
            source = json.loads(p.with_suffix(".source.json").read_text())
            split, route = "held_out_from_development", "predict_structure"
        else:
            p = ROOT / "frontend/public/structures" / f"{pid}.cif"
            seq = {r: entity_sequence(pid, r) for r in ("target", "heavy", "light")}
            source = {"url": f"https://files.rcsb.org/download/{pid}.cif",
                      "sha256": sha(p.read_bytes()), "retrieved_at": "existing repository snapshot"}
            split, route = "development_regression", "use_experimental_structure"
        cases.append({"id": pid, "split": split, "source": source, "sequences": seq,
                      "expected_route": route, "expected_status": "completed",
                      "expected_decision": "needs_confirmation", "model_required": True,
                      "basis": "Published sequences; local catalogue contains only 1N8Z/1S78. Missing metrics require confirmation."})
    for name, base, change in (("missing-target", "8JYR", "target"),
                               ("short-heavy", "3N85", "heavy"),
                               ("invalid-char", "8JYR", "invalid"),
                               ("invalid-range", "3N85", "range")):
        c = json.loads(json.dumps(next(c for c in cases if c["id"] == base)))
        c.update(id=name, split="derived_control", derived_from=base,
                 expected_route="hold_candidate", expected_status="partial",
                 expected_decision="hold", basis="Missing/short sequence: hold; invalid character/range: reject before inference.")
        if change == "target": c["sequences"]["target"] = ""
        if change == "heavy": c["sequences"]["heavy"] = c["sequences"]["heavy"][:20]
        if change == "invalid": c["sequences"]["heavy"] += "!"
        if change == "range": c["invalid_range"] = True
        if change in ("invalid", "range"):
            c.update(expected_route="input_rejection", expected_status="failed", model_required=False)
        cases.append(c)
    write(MANIFEST, {"frozen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "model": DEFAULT_MODEL, "code_sha256": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in CODE},
                    "cases": cases, "rules": "Primary denominator includes all attempted model-required cases, including API failures. Policy task accuracy is distinct from biological accuracy. No tuning during benchmark."})
    print("Frozen", len(cases), "cases", sha(MANIFEST.read_bytes()))


class RecordedClient(NvidiaClient):
    def __init__(self, directory, mode):
        super().__init__(directory)
        self.mode, self.network_predictions, self.cache_hits = mode, 0, 0

    def _post(self, *args, **kwargs):
        return super()._post(*args, **{**kwargs, "waits": ()})

    def predict_complex(self, polymers, **kwargs):
        key = sha(json.dumps([polymers, kwargs], sort_keys=True).encode())
        cache = WORK / "prediction-cache" / f"{key}.json"
        if cache.exists():
            self.cache_hits += 1
            return json.loads(cache.read_text())
        if self.mode == "rule":
            raise MissingCredentials("No recorded prediction; baseline must not create extra paid calls.")
        self.network_predictions += 1
        response = super().predict_complex(polymers, **kwargs)
        write(cache, response)
        return response

    def chat(self, *args, **kwargs):
        raise AssertionError("RuleDecider must never ask a model; NAT uses its real NIM client.")


def assessment(case, row):
    correct = row["status"] == case["expected_status"] and row["decision"] == case["expected_decision"]
    route_ok = row["route"] == case["expected_route"]
    return {"output_correct": correct, "route_correct": route_ok,
            "agent_task_success": correct and route_ok and not row["fallback_used"],
            "clean_success": correct and route_ok and not row["fallback_used"] and not row["agent_errors"]}


def run(case_id, mode):
    manifest = json.loads(MANIFEST.read_text())
    for name, digest in manifest["code_sha256"].items():
        assert sha((ROOT / name).read_bytes()) == digest, f"Code changed after freeze: {name}"
    if RESULTS.exists():
        assert not any(r["id"] == case_id and r["mode"] == mode for r in map(json.loads, RESULTS.read_text().splitlines())), "Already attempted; do not overwrite failure."
    c = next(c for c in manifest["cases"] if c["id"] == case_id)
    seq = c["sequences"]
    cand = candidate("subject", "Evaluation candidate", seq["heavy"], seq["light"])
    if c.get("invalid_range"):
        cand["heavy_analysis_range"] = {"start": 1, "end": len(seq["heavy"]) + 1}
    directory = WORK / "runs" / f"{case_id}-{mode}"
    request = make_request([cand, _filler()], directory, target_fasta=seq["target"] or None)
    write(directory / "request.json", request)
    load_env(ROOT.parent / "nvidia-hackathon/.env")
    client = RecordedClient(directory, mode)
    decider = RuleDecider("fixed policy baseline", decisions=[], model=DEFAULT_MODEL)
    os.environ["LOGIC_AGENT_MODE"] = mode
    started = time.monotonic()
    output, flow = run_flow(request, client=client, decider=decider)
    trace = flow.agent_traces.get("subject", [])
    decisions = [d.to_record() for d in decider.decisions]
    accepted = [t["tool"] for t in trace if t["accepted"]]
    route = next((t for t in accepted if t in ("predict_structure", "use_experimental_structure", "hold_candidate")), None)
    if not c["model_required"] and flow.states["subject"].status == "failed": route = "input_rejection"
    if mode == "rule":
        source = next((d["action"] for d in decisions if d["step"] == "structure_source"), None)
        route = {"predict": "predict_structure", "use_experimental": "use_experimental_structure", "hold": "hold_candidate"}.get(source, route)
    opinion = next(o for o in output["result"]["opinions"] if o["candidate_id"] == "subject")
    row = {"id": case_id, "mode": mode, "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "manifest_sha256": sha(MANIFEST.read_bytes()), "seconds": round(time.monotonic()-started, 3),
           "route": route, "status": flow.states["subject"].status, "decision": opinion["decision"],
           "reason": opinion["reason"], "limitations": opinion["limitations"],
           "trace": trace, "decisions": decisions, "agent_errors": flow.agent_errors,
           "fallback_used": mode == "nat" and any(d["decided_by"] == "rule" for d in decisions),
           "network_predictions": client.network_predictions, "prediction_cache_hits": client.cache_hits}
    row.update(assessment(c, row))
    write(directory / "output.json", output)
    with RESULTS.open("a") as f: f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["prepare", "run", "self-test"])
    ap.add_argument("case", nargs="?")
    ap.add_argument("mode", nargs="?", choices=["nat", "rule"])
    a = ap.parse_args()
    if a.action == "prepare": prepare()
    elif a.action == "run": run(a.case, a.mode)
    else:
        c = {"expected_status": "completed", "expected_decision": "needs_confirmation", "expected_route": "predict_structure"}
        r = {"status": "completed", "decision": "needs_confirmation", "route": None, "fallback_used": True, "agent_errors": {"subject": "429"}}
        assert assessment(c, r) == {"output_correct": True, "route_correct": False, "agent_task_success": False, "clean_success": False}
        r.update(route="predict_structure", fallback_used=False)
        assert assessment(c, r)["agent_task_success"] and not assessment(c, r)["clean_success"]
        print("Scoring self-test passed")
