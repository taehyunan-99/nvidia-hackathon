#!/usr/bin/env python3
"""Validate external pilot status planes and normalize bounded work-unit aliases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0.0"
WORK_UNIT_ALIASES = {
    "SUCCESS": "SUCCESS",
    "PASS_WITH_LIMITED_SCOPE": "SUCCESS",
    "PASS_WITH_UNSCORED_RESIDUAL_RISKS": "SUCCESS",
}
PROJECT_STATES = {
    "NEEDS_DECISION",
    "REJECTED_TEST_OUTPUT",
    "IMPROVE",
    "STOPPED_MAX_ITERATIONS",
    "STOPPED_NO_PROGRESS",
    "CODE_FIX_REQUIRED",
    "BLOCKED",
    "COMPLETE",
}
GENERATED_TEST_QUALITY_STATES = {
    "NEEDS_DECISION",
    "REJECTED_TEST_OUTPUT",
    "IMPROVE",
    "STOPPED_MAX_ITERATIONS",
    "STOPPED_NO_PROGRESS",
    "TESTS_ACCEPTED",
}
EXECUTION_STATES = {
    "PASS",
    "FAIL_PRODUCT_CODE",
    "FAIL_TEST",
    "FAIL_ORACLE",
    "BLOCKED_ENVIRONMENT",
    "FLAKY",
    "NOT_RUN",
}


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _canonical(value: Any, field: str, allowed: set[str]) -> str:
    text = _text(value, field)
    if text not in allowed:
        raise ValueError(f"{field} must be one of: {', '.join(sorted(allowed))}")
    return text


def normalize(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    pilot_id = _text(record.get("pilot_id"), "pilot_id")
    operational = _text(record.get("operational_status"), "operational_status")
    if operational not in WORK_UNIT_ALIASES:
        raise ValueError(
            "operational_status must be SUCCESS or a supported bounded-pilot alias"
        )
    project = _canonical(
        record.get("whole_project_status"), "whole_project_status", PROJECT_STATES
    )
    quality = _canonical(
        record.get("generated_test_quality_status"),
        "generated_test_quality_status",
        GENERATED_TEST_QUALITY_STATES,
    )
    execution = _canonical(
        record.get("execution_status"), "execution_status", EXECUTION_STATES
    )
    score = record.get("diagnostic_score")
    if score is not None and (
        not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not 0 <= score <= 100
    ):
        raise ValueError("diagnostic_score must be null or a number from 0 to 100")
    return {
        "schema_version": SCHEMA_VERSION,
        "pilot_id": pilot_id,
        "work_unit_status": WORK_UNIT_ALIASES[operational],
        "operational_status_original": operational,
        "whole_project_status": project,
        "generated_test_quality_status": quality,
        "execution_status": execution,
        "diagnostic_score": score,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path)
    args = parser.parse_args()
    try:
        value = json.loads(args.record.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("pilot record must be a JSON object")
        result = normalize(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
