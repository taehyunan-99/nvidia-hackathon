"""Validate the demo dataset or total an evidence-backed, manually reviewed scorecard.

This does not call an agent or judge scientific claims with another LLM.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_dataset():
    from jsonschema import Draft202012Validator

    lock, data = read(HERE / "data-lock.json"), read(HERE / "cases.json")
    if data["dataset_version"] != lock["dataset_version"]:
        raise ValueError("Dataset versions differ")
    for base, files in ((ROOT, lock["sources"] + [lock["source_fixture"]]), (HERE, lock["files"])):
        for item in files:
            if hashlib.sha256((base / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
                raise ValueError(f"File changed: {item['path']}")
    schema = read(ROOT / "docs/frontend-hosting/contracts/service.schema.json")
    validator = Draft202012Validator({"$ref": "#/$defs/ReviewInput", "$defs": schema["$defs"]})
    faults, ids, totals = read(HERE / "faults.json"), set(), {}
    for case in data["cases"]:
        validator.validate(read(HERE / case["input"]))
        if case["fault"] is not None and case["fault"] not in faults:
            raise ValueError(f"Unknown fault: {case['fault']}")
        for check in case["checks"]:
            if check["check_id"] in ids:
                raise ValueError("Duplicate check")
            ids.add(check["check_id"])
            totals[case["area"]] = totals.get(case["area"], 0) + 1
    if len(data["cases"]) != 10 or len(totals) != 5 or set(totals.values()) != {4}:
        raise ValueError("Expected 10 cases, 5 areas and 4 checks per area")
    return data


def score(data, card):
    if card["dataset_version"] != data["dataset_version"]:
        raise ValueError("Scorecard version differs from cases")
    if card["mode"] not in {"offline", "live_with_fault_injection"}:
        raise ValueError("Unknown execution mode")
    checks = {c["check_id"]: (case["area"], c) for case in data["cases"] for c in case["checks"]}
    rows = card["results"]
    if len(rows) != len(checks) or {r["check_id"] for r in rows} != set(checks):
        raise ValueError("Every check must appear exactly once")
    areas, critical, pending = {}, [], []
    for row in rows:
        cid, status = row["check_id"], row["status"]
        if status not in {"pass", "fail", "not_run"}:
            raise ValueError(f"Invalid status: {cid}")
        if status != "not_run":
            if not card.get("reviewer") or not card.get("evaluated_commit"):
                raise ValueError("Scored observations require reviewer and commit")
            if not isinstance(row.get("evidence"), list) or not row["evidence"] or not all(
                isinstance(v, str) and v.strip() for v in row["evidence"]
            ):
                raise ValueError(f"Scored observation requires evidence: {cid}")
        area, check = checks[cid]
        tally = areas.setdefault(area, {"passed": 0, "evaluated": 0, "maximum": 4})
        tally["passed"] += status == "pass"
        tally["evaluated"] += status != "not_run"
        if status == "not_run":
            pending.append(cid)
        elif status == "fail" and check["critical_on_fail"]:
            critical.append(cid)
    total = None if pending else sum(v["passed"] for v in areas.values())
    if critical:
        readiness = "blocked_by_critical_failure"
    elif pending:
        readiness = "incomplete"
    elif total >= 16 and all(v["passed"] >= 2 for v in areas.values()):
        readiness = "internal_target_met"
    else:
        readiness = "needs_improvement"
    return {"mode": card["mode"], "areas": areas, "score_out_of_20": total,
            "critical_failures": critical, "not_run": pending, "readiness": readiness,
            "scope": "Internal demo rubric; not a model accuracy or biological validation score"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scorecard", type=Path)
    args = parser.parse_args()
    data = validate_dataset()
    result = score(data, read(args.scorecard)) if args.scorecard else {
        "dataset": data["dataset_version"], "cases": 10, "checks": 20,
        "status": "source hashes, input schemas and case references verified"}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
