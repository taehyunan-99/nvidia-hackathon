"""Validate provisional UI fixtures, not scientific results or a running service."""

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "contracts/service.schema.json").read_text())
FIXTURES = json.loads((ROOT / "fixtures/scenarios.json").read_text())
Draft202012Validator.check_schema(SCHEMA)
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def index(items, key):
    mapped = {item[key]: item for item in items}
    require(len(mapped) == len(items), f"duplicate {key}")
    return mapped


def validate(payload):
    VALIDATOR.validate(payload)
    candidates = index(payload["input"]["candidates"], "candidate_id")
    index(payload["input"]["uploads"], "upload_key")
    for upload in payload["input"]["uploads"]:
        require(upload["candidate_id"] in candidates, "upload candidate missing")
    ranges = [payload["input"]["target"]["analysis_range"]]
    for candidate in candidates.values():
        ranges += [candidate["heavy_analysis_range"], candidate["light_analysis_range"]]
    require(all(r is None or r["start"] <= r["end"] for r in ranges), "reversed range")
    index(payload["scenarios"], "name")
    for case in payload["scenarios"]:
        run, result, error = case["run"], case["result"], case["error"]
        for response in (case["session"], run, result, error):
            require(response is None or response["data_mode"] == "mock", "fixture mode leaked")
        if case["session"]["status"] != "active":
            require(run is None and result is None, "expired session leaked content")
        if run is None:
            require(result is None, "result without run")
            continue
        require(set(index(run["candidates"], "candidate_id")) == set(candidates), "run candidate mismatch")
        require(run["result_available"] == (result is not None), "result availability mismatch")
        if run["status"] in ("completed", "partial"):
            require(result is not None and run["finished_at"] is not None, "terminal result missing")
        if run["status"] in ("queued", "failed"):
            require(result is None, "unexpected result")
        if run["status"] in ("partial", "failed", "interrupted"):
            require(run["error"] is not None, "failure reason missing")
        if run["error"]:
            require(run["error"]["run_id"] == run["run_id"], "error run mismatch")
            require(run["error"]["candidate_id"] in (None, *candidates), "error candidate missing")
        for candidate in run["candidates"]:
            steps = index(candidate["steps"], "step_id")
            require(candidate["current_step"] is None or candidate["current_step"] in steps, "step missing")
            for step in steps.values():
                if step["status"] in ("skipped", "held", "failed"):
                    require(bool(step["reason"]), "step reason missing")
        if result is None:
            continue
        require(result["run_id"] == run["run_id"] and result["review_id"] == run["review_id"], "result ID mismatch")
        require(result["settings_version"] == run["settings_version"], "settings mismatch")
        require(set(result["candidate_ids"]) == set(candidates), "result candidate mismatch")
        structures = index(result["structures"], "structure_id")
        conditions = index(result["conditions"], "condition_id")
        evidence = index(result["evidence"], "evidence_id")
        artifacts = index(result["artifacts"], "artifact_id")
        index(result["opinions"], "opinion_id")
        for structure in structures.values():
            require(structure["candidate_id"] in candidates, "structure candidate missing")
            artifact = artifacts.get(structure["artifact_id"])
            require(artifact is not None and artifact["role"] == "structure", "structure artifact missing")
            if structure["alignment"]:
                alignment = structure["alignment"]
                require(alignment["reference_structure_id"] in structures, "alignment reference missing")
                require(len(alignment["reference_residues"]) == len(alignment["mobile_residues"]), "alignment pairs mismatch")
        for condition in conditions.values():
            require(condition["candidate_id"] in candidates, "condition candidate missing")
            for sid in condition["structure_ids"]:
                require(sid in structures and structures[sid]["candidate_id"] == condition["candidate_id"], "condition structure mismatch")
        for item in [*evidence.values(), *result["opinions"]]:
            condition = conditions.get(item["condition_id"])
            require(condition is not None and condition["candidate_id"] == item["candidate_id"], "condition scope mismatch")
        for item in evidence.values():
            sid = item["structure_id"]
            require(sid is None or sid in conditions[item["condition_id"]]["structure_ids"], "evidence structure mismatch")
            require(sid is not None or not item["residues"], "residues without structure")
            require(item["value"] is None, "UI fixture contains a fabricated measurement")
        for opinion in result["opinions"]:
            for eid in opinion["evidence_ids"] + opinion["conflicting_evidence_ids"]:
                require(eid in evidence and evidence[eid]["condition_id"] == opinion["condition_id"], "opinion evidence mismatch")


def rejects(label, mutate):
    bad = copy.deepcopy(FIXTURES)
    mutate(bad)
    try:
        validate(bad)
    except (ValidationError, ValueError):
        return label
    raise AssertionError(f"accepted invalid fixture: {label}")


def scenario(payload, name):
    return next(case for case in payload["scenarios"] if case["name"] == name)


if __name__ == "__main__":
    validate(FIXTURES)
    checks = [
        rejects("duplicate candidate", lambda x: x["input"]["candidates"][1].update(candidate_id="mock-candidate-a")),
        rejects("wrong result run", lambda x: scenario(x, "completed")["result"].update(run_id="wrong-run")),
        rejects("cross-candidate evidence", lambda x: scenario(x, "completed")["result"]["evidence"][0].update(condition_id="mock-core-2")),
        rejects("missing opinion evidence", lambda x: scenario(x, "completed")["result"]["opinions"][0].update(evidence_ids=["missing"])),
        rejects("failed with result flag", lambda x: scenario(x, "failed")["run"].update(result_available=True)),
        rejects("null changed to zero", lambda x: scenario(x, "completed")["result"]["evidence"][0].update(value=0)),
        rejects("mock marked live", lambda x: scenario(x, "completed")["result"].update(data_mode="live")),
        rejects("expired content leak", lambda x: scenario(x, "session-expired").update(run=scenario(x, "running")["run"])),
        rejects("missing hold reason", lambda x: scenario(x, "scientific-hold")["run"]["candidates"][1]["steps"][3].update(reason=None)),
    ]
    # A real measured zero must remain valid; only unmeasured fixture zeros are rejected.
    measured = copy.deepcopy(scenario(FIXTURES, "completed")["result"]["evidence"][0])
    measured.update(kind="computed", measurement_state="measured", value=0, unit="test-unit", definition="Synthetic schema validation only", reason=None)
    Draft202012Validator({**SCHEMA, "$ref": "#/$defs/Evidence"}).validate(measured)
    print(f"Validated schema and {len(FIXTURES['scenarios'])} mock scenarios; {len(checks)} invalid variants rejected; measured zero preserved.")
