#!/usr/bin/env python3
"""Grade generated tests with non-compensatory C0/C1 acceptance rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


EXECUTION_CAUSES = {
    "product_code",
    "generated_test",
    "oracle",
    "environment_dependency",
    "flaky",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
HARNESS_RUN_KINDS = {
    "test_execution",
    "seeded_fault",
    "mutation",
    "red_green",
    "differential",
    "controlled_failure",
    "real_boundary",
    "real_boundary_parity",
}
FAILURE_WITNESS_KINDS = HARNESS_RUN_KINDS - {
    "test_execution",
    "real_boundary_parity",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def require_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def require_text_list(value: Any, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{field} must be an array of non-empty strings")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    return [item.strip() for item in value]


def exact_keys(actual: dict[str, Any], expected: set[str], field: str) -> None:
    missing = sorted(expected - set(actual))
    unknown = sorted(set(actual) - expected)
    if missing:
        raise ValueError(f"Missing {field} IDs: {', '.join(missing)}")
    if unknown:
        raise ValueError(f"Unknown {field} IDs: {', '.join(unknown)}")


def require_sha256(value: Any, field: str) -> str:
    text = require_text(value, field).lower()
    if not SHA256.fullmatch(text):
        raise ValueError(f"{field} must be a lowercase SHA-256 hex digest")
    return text


def validate_provenance(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("provenance must be an object")
    exact_keys(value, {"maker", "verifier", "harness"}, "provenance role")
    result: dict[str, dict[str, Any]] = {}
    for role in ("maker", "verifier", "harness"):
        item = value[role]
        if not isinstance(item, dict):
            raise ValueError(f"provenance.{role} must be an object")
        if item.get("role") != role:
            raise ValueError(f"provenance.{role}.role must be {role}")
        result[role] = {
            "role": role,
            "actor_id": require_text(item.get("actor_id"), f"provenance.{role}.actor_id"),
            "context_id": require_text(
                item.get("context_id"), f"provenance.{role}.context_id"
            ),
        }
    actor_ids = [result[role]["actor_id"] for role in result]
    if len(set(actor_ids)) != len(actor_ids):
        raise ValueError("maker, verifier, and harness actor_id values must be distinct")
    if result["maker"]["context_id"] == result["verifier"]["context_id"]:
        raise ValueError("maker and verifier context_id values must be distinct")
    verifier = value["verifier"]
    if verifier.get("fresh_context") is not True:
        raise ValueError("provenance.verifier.fresh_context must be true")
    if verifier.get("maker_conclusions_shared") is not False:
        raise ValueError(
            "provenance.verifier.maker_conclusions_shared must be false"
        )
    result["verifier"].update(
        {"fresh_context": True, "maker_conclusions_shared": False}
    )
    return result


def validate_artifacts(
    value: Any, maker_id: str
) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    if not isinstance(value, list) or not value:
        raise ValueError("artifacts must be a non-empty array")
    artifacts: list[dict[str, str]] = []
    by_path: dict[str, dict[str, str]] = {}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"artifacts[{index}] must be an object")
        path = require_text(item.get("path"), f"artifacts[{index}].path")
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts or "\\" in path:
            raise ValueError(
                f"artifacts[{index}].path must be a repository-relative forward-slash path"
            )
        if path in by_path:
            raise ValueError(f"Duplicate artifact path: {path}")
        kind = require_text(item.get("kind"), f"artifacts[{index}].kind")
        if kind not in {"test", "fixture"}:
            raise ValueError(f"artifacts[{index}].kind must be test or fixture")
        change = require_text(item.get("change"), f"artifacts[{index}].change")
        if change not in {"created", "modified"}:
            raise ValueError(f"artifacts[{index}].change must be created or modified")
        producer_id = require_text(
            item.get("producer_id"), f"artifacts[{index}].producer_id"
        )
        if producer_id != maker_id:
            raise ValueError(f"artifacts[{index}].producer_id must identify the maker")
        digest = require_sha256(item.get("sha256"), f"artifacts[{index}].sha256")
        artifact = {
            "path": path,
            "kind": kind,
            "change": change,
            "producer_id": producer_id,
            "sha256": digest,
        }
        by_path[path] = artifact
        artifacts.append(artifact)
    return artifacts, by_path


def verify_artifact_files(
    artifact_root: Path, artifacts: dict[str, dict[str, str]]
) -> None:
    root = artifact_root.resolve()
    for path, artifact in artifacts.items():
        candidate = (root / path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Artifact path escapes artifact_root: {path}") from exc
        if not candidate.is_file():
            raise ValueError(f"Artifact file does not exist under artifact_root: {path}")
        digest = hashlib.sha256()
        with candidate.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != artifact["sha256"]:
            raise ValueError(f"Artifact SHA-256 does not match current file: {path}")


def validate_harness_runs(
    value: Any,
    harness_id: str,
    artifacts: dict[str, dict[str, str]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("harness_runs must be a non-empty array")
    runs: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"harness_runs[{index}] must be an object")
        run_id = require_text(item.get("id"), f"harness_runs[{index}].id")
        if run_id in runs:
            raise ValueError(f"Duplicate harness run ID: {run_id}")
        if item.get("harness_id") != harness_id:
            raise ValueError(
                f"harness_runs[{index}].harness_id must identify the harness"
            )
        kind = require_text(item.get("kind"), f"harness_runs[{index}].kind")
        if kind not in HARNESS_RUN_KINDS:
            raise ValueError(f"harness_runs[{index}].kind is unsupported")
        status = require_text(item.get("status"), f"harness_runs[{index}].status")
        if status not in {"pass", "fail", "blocked"}:
            raise ValueError(
                f"harness_runs[{index}].status must be pass, fail, or blocked"
            )
        command = require_text_list(item.get("command"), f"harness_runs[{index}].command")
        paths = require_text_list(
            item.get("artifact_paths"), f"harness_runs[{index}].artifact_paths"
        )
        outside = sorted(set(paths) - set(artifacts))
        if outside:
            raise ValueError(
                f"harness_runs[{index}] references artifacts outside scope: "
                + ", ".join(outside)
            )
        raw_digests = item.get("artifact_digests")
        if not isinstance(raw_digests, dict):
            raise ValueError(f"harness_runs[{index}].artifact_digests must be an object")
        exact_keys(raw_digests, set(paths), f"harness_runs[{index}] artifact digest")
        digests: dict[str, str] = {}
        for path in paths:
            digest = require_sha256(
                raw_digests[path], f"harness_runs[{index}].artifact_digests.{path}"
            )
            if digest != artifacts[path]["sha256"]:
                raise ValueError(
                    f"harness_runs[{index}] digest does not match manifest for {path}"
                )
            digests[path] = digest
        detected = item.get("defect_detected", False)
        if not isinstance(detected, bool):
            raise ValueError(f"harness_runs[{index}].defect_detected must be boolean")
        runs[run_id] = {
            "id": run_id,
            "harness_id": harness_id,
            "kind": kind,
            "status": status,
            "command": command,
            "artifact_paths": paths,
            "artifact_digests": digests,
            "input_fingerprint": require_sha256(
                item.get("input_fingerprint"),
                f"harness_runs[{index}].input_fingerprint",
            ),
            "outcome_digest": require_sha256(
                item.get("outcome_digest"), f"harness_runs[{index}].outcome_digest"
            ),
            "defect_detected": detected,
        }
    return runs


def _component(
    value: Any,
    field: str,
    verifier_id: str,
) -> tuple[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    status = require_text(value.get("status"), f"{field}.status")
    if status not in {"pass", "fail", "blocked", "unknown"}:
        raise ValueError(f"{field}.status must be pass, fail, blocked, or unknown")
    if value.get("verified_by") != verifier_id:
        raise ValueError(f"{field}.verified_by must identify the verifier")
    if status != "pass":
        require_text_list(value.get("evidence"), f"{field}.evidence")
    return status, value


def _artifact_paths(
    value: Any,
    field: str,
    artifacts: dict[str, dict[str, str]],
    *,
    tests_only: bool = True,
) -> list[str]:
    paths = require_text_list(value, field)
    outside = sorted(set(paths) - set(artifacts))
    if outside:
        raise ValueError(f"{field} references artifacts outside scope: {', '.join(outside)}")
    if tests_only and not any(artifacts[path]["kind"] == "test" for path in paths):
        raise ValueError(f"{field} must include at least one generated test")
    return paths


def _run_ids(
    value: Any,
    field: str,
    runs: dict[str, dict[str, Any]],
) -> list[str]:
    run_ids = require_text_list(value, field)
    missing = sorted(set(run_ids) - set(runs))
    if missing:
        raise ValueError(f"{field} references unknown harness runs: {', '.join(missing)}")
    return run_ids


def _validate_oracle_component(
    component: dict[str, Any], gate: dict[str, Any], field: str
) -> None:
    if require_text(component.get("oracle"), f"{field}.oracle") != gate["oracle"]:
        raise ValueError(f"{field}.oracle does not match the compiled oracle")
    sources = require_text_list(component.get("evidence_sources"), f"{field}.evidence_sources")
    missing = sorted(set(gate["evidence"]) - set(sources))
    if missing:
        raise ValueError(
            f"{field}.evidence_sources omits compiled evidence: {', '.join(missing)}"
        )


def _validate_test_component(
    component: dict[str, Any],
    field: str,
    artifacts: dict[str, dict[str, str]],
    runs: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    paths = _artifact_paths(component.get("artifact_paths"), f"{field}.artifact_paths", artifacts)
    run_ids = _run_ids(component.get("harness_run_ids"), f"{field}.harness_run_ids", runs)
    for run_id in run_ids:
        run = runs[run_id]
        if run["status"] != "pass":
            raise ValueError(f"{field} references non-passing harness run {run_id}")
        missing = sorted(set(paths) - set(run["artifact_paths"]))
        if missing:
            raise ValueError(
                f"{field} run {run_id} omits artifacts: {', '.join(missing)}"
            )
    return paths, run_ids


def validate_gate_results(
    value: Any,
    expected: set[str],
    field: str,
    verifier_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    exact_keys(value, expected, field)
    result: dict[str, dict[str, Any]] = {}
    for gate_id, gate in value.items():
        if not isinstance(gate, dict):
            raise ValueError(f"{field}.{gate_id} must be an object")
        status = require_text(gate.get("status"), f"{field}.{gate_id}.status")
        if status not in {"pass", "fail", "blocked", "unknown"}:
            raise ValueError(
                f"{field}.{gate_id}.status must be pass, fail, blocked, or unknown"
            )
        evidence = require_text_list(gate.get("evidence"), f"{field}.{gate_id}.evidence")
        if verifier_id is not None and gate.get("verified_by") != verifier_id:
            raise ValueError(f"{field}.{gate_id}.verified_by must identify the verifier")
        result[gate_id] = {
            "status": status,
            "evidence": evidence,
            "verified_by": verifier_id,
        }
    return result


def validate_c0_results(
    value: Any,
    gates: list[dict[str, Any]],
    verifier_id: str,
    artifacts: dict[str, dict[str, str]],
    runs: dict[str, dict[str, Any]],
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("c0_gate_results must be an object")
    by_id = {gate["id"]: gate for gate in gates}
    exact_keys(value, set(by_id), "c0_gate_result")
    statuses: dict[str, str] = {}
    for gate_id, gate in by_id.items():
        raw = value[gate_id]
        if not isinstance(raw, dict):
            raise ValueError(f"c0_gate_results.{gate_id} must be an object")
        exact_keys(raw, set(gate["required_components"]), f"C0 {gate_id} component")
        component_statuses: list[str] = []
        for component_id in gate["required_components"]:
            field = f"c0_gate_results.{gate_id}.{component_id}"
            status, component = _component(raw[component_id], field, verifier_id)
            component_statuses.append(status)
            if status != "pass":
                continue
            if component_id == "approved_oracle":
                _validate_oracle_component(component, gate, field)
            elif component_id == "required_tests":
                _validate_test_component(component, field, artifacts, runs)
            elif component_id == "failure_witness":
                _, run_ids = _validate_test_component(component, field, artifacts, runs)
                kind = require_text(component.get("kind"), f"{field}.kind")
                if kind not in FAILURE_WITNESS_KINDS:
                    raise ValueError(f"{field}.kind must be a failure-witness kind")
                if not any(
                    runs[run_id]["kind"] == kind
                    and runs[run_id]["defect_detected"]
                    for run_id in run_ids
                ):
                    raise ValueError(
                        f"{field} has no matching harness run that detected the defect"
                    )
            elif component_id == "reproducibility":
                run_ids = _run_ids(
                    component.get("harness_run_ids"), f"{field}.harness_run_ids", runs
                )
                if len(set(run_ids)) < 2:
                    raise ValueError(f"{field} requires at least two distinct harness runs")
                selected = [runs[run_id] for run_id in run_ids]
                if any(
                    run["kind"] != "test_execution" or run["status"] != "pass"
                    for run in selected
                ):
                    raise ValueError(f"{field} requires passing test_execution runs")
                if len({run["input_fingerprint"] for run in selected}) != 1 or len(
                    {run["outcome_digest"] for run in selected}
                ) != 1:
                    raise ValueError(
                        f"{field} runs must have identical input and outcome digests"
                    )
            elif component_id == "real_boundary_parity":
                _, run_ids = _validate_test_component(component, field, artifacts, runs)
                if not any(runs[run_id]["kind"] == "real_boundary_parity" for run_id in run_ids):
                    raise ValueError(f"{field} requires a real_boundary_parity run")
        if any(status in {"unknown", "blocked"} for status in component_statuses):
            statuses[gate_id] = "unknown"
        elif any(status == "fail" for status in component_statuses):
            statuses[gate_id] = "fail"
        else:
            statuses[gate_id] = "pass"
    return statuses


def validate_c1_behavior_results(
    value: Any,
    gates: list[dict[str, Any]],
    verifier_id: str,
    artifacts: dict[str, dict[str, str]],
    runs: dict[str, dict[str, Any]],
    criterion_ratings: dict[str, str],
    rating_scores: dict[str, float],
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("c1_behavior_results must be an object")
    by_id = {gate["id"]: gate for gate in gates}
    exact_keys(value, set(by_id), "c1_behavior_result")
    statuses: dict[str, str] = {}
    for gate_id, gate in by_id.items():
        raw = value[gate_id]
        if not isinstance(raw, dict):
            raise ValueError(f"c1_behavior_results.{gate_id} must be an object")
        exact_keys(raw, set(gate["required_components"]), f"C1 {gate_id} component")
        component_statuses: list[str] = []
        for component_id in gate["required_components"]:
            field = f"c1_behavior_results.{gate_id}.{component_id}"
            status, component = _component(raw[component_id], field, verifier_id)
            component_statuses.append(status)
            if status != "pass":
                continue
            if component_id == "approved_oracle":
                _validate_oracle_component(component, gate, field)
            elif component_id == "required_tests":
                _validate_test_component(component, field, artifacts, runs)
            elif component_id == "verification":
                _validate_test_component(component, field, artifacts, runs)
                criterion_ids = require_text_list(
                    component.get("criterion_ids"), f"{field}.criterion_ids"
                )
                if set(criterion_ids) != set(gate["required_criteria"]):
                    raise ValueError(
                        f"{field}.criterion_ids must exactly match compiled C1 criteria"
                    )
        if any(status in {"unknown", "blocked"} for status in component_statuses):
            statuses[gate_id] = "unknown"
        elif any(status == "fail" for status in component_statuses):
            statuses[gate_id] = "fail"
        else:
            minimum = rating_scores[gate["required_rating"]]
            if any(
                rating_scores[criterion_ratings[criterion_id]] < minimum
                for criterion_id in gate["required_criteria"]
            ):
                statuses[gate_id] = "fail"
            else:
                statuses[gate_id] = "pass"
    return statuses


def validate_execution_results(
    value: Any, runs: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("execution_results must be an array")
    results: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"execution_results[{index}] must be an object")
        result_id = require_text(item.get("id"), f"execution_results[{index}].id")
        if result_id in ids:
            raise ValueError(f"Duplicate execution result ID: {result_id}")
        ids.add(result_id)
        kind = require_text(item.get("kind"), f"execution_results[{index}].kind")
        status = require_text(item.get("status"), f"execution_results[{index}].status")
        if status not in {"pass", "fail", "blocked", "not_run"}:
            raise ValueError(
                f"execution_results[{index}].status must be pass, fail, blocked, or not_run"
            )
        cause = item.get("cause")
        if status == "fail":
            cause = require_text(cause, f"execution_results[{index}].cause")
            if cause not in EXECUTION_CAUSES:
                raise ValueError(
                    f"execution_results[{index}].cause must be one of: "
                    + ", ".join(sorted(EXECUTION_CAUSES))
                )
        elif cause is not None and cause not in EXECUTION_CAUSES:
            raise ValueError(f"execution_results[{index}].cause is invalid")
        harness_run_id = item.get("harness_run_id")
        if status == "not_run":
            if harness_run_id is not None:
                raise ValueError(
                    f"execution_results[{index}].harness_run_id must be null when not_run"
                )
        else:
            harness_run_id = require_text(
                harness_run_id, f"execution_results[{index}].harness_run_id"
            )
            if harness_run_id not in runs:
                raise ValueError(
                    f"execution_results[{index}] references unknown harness run {harness_run_id}"
                )
            expected = {"pass": "pass", "fail": "fail", "blocked": "blocked"}[status]
            if runs[harness_run_id]["status"] != expected:
                raise ValueError(
                    f"execution_results[{index}] status does not match harness run {harness_run_id}"
                )
        evidence = require_text_list(
            item.get("evidence", []),
            f"execution_results[{index}].evidence",
            allow_empty=status in {"not_run"},
        )
        location = item.get("location", "")
        oracle = item.get("oracle", "")
        remediation = item.get("remediation", "")
        verification = item.get("verification", "")
        if status == "fail":
            location = require_text(location, f"execution_results[{index}].location")
            oracle = require_text(oracle, f"execution_results[{index}].oracle")
            remediation = require_text(
                remediation, f"execution_results[{index}].remediation"
            )
            verification = require_text(
                verification, f"execution_results[{index}].verification"
            )
        results.append(
            {
                "id": result_id,
                "kind": kind,
                "status": status,
                "cause": cause,
                "harness_run_id": harness_run_id,
                "location": location,
                "oracle": oracle,
                "evidence": evidence,
                "remediation": remediation,
                "verification": verification,
            }
        )
    return results


def execution_status(results: list[dict[str, Any]]) -> str:
    if not results or any(item["status"] == "not_run" for item in results):
        return "NOT_RUN"
    causes = {item["cause"] for item in results if item["status"] == "fail"}
    if "oracle" in causes:
        return "FAIL_ORACLE"
    if "generated_test" in causes:
        return "FAIL_TEST"
    if "flaky" in causes:
        return "FLAKY"
    if "environment_dependency" in causes:
        return "BLOCKED_ENVIRONMENT"
    if "product_code" in causes:
        return "FAIL_PRODUCT_CODE"
    if any(item["status"] == "blocked" for item in results):
        return "BLOCKED_ENVIRONMENT"
    return "PASS"


def grade(
    compiled: dict[str, Any],
    assessment: dict[str, Any],
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    if compiled.get("schema_version") != "2.0.0":
        raise ValueError("Unsupported compiled rubric schema_version")
    if assessment.get("schema_version") != "2.0.0":
        raise ValueError("Unsupported assessment schema_version")
    run_id = require_text(assessment.get("run_id"), "run_id")
    provenance = validate_provenance(assessment.get("provenance"))
    maker_id = provenance["maker"]["actor_id"]
    verifier_id = provenance["verifier"]["actor_id"]
    harness_id = provenance["harness"]["actor_id"]
    artifacts, artifacts_by_path = validate_artifacts(
        assessment.get("artifacts"), maker_id
    )
    if artifact_root is not None:
        verify_artifact_files(artifact_root, artifacts_by_path)
    harness_runs = validate_harness_runs(
        assessment.get("harness_runs"), harness_id, artifacts_by_path
    )

    raw_scale = compiled.get("scoring_scale")
    if not isinstance(raw_scale, list) or not raw_scale:
        raise ValueError("compiled scoring_scale must be a non-empty array")
    rating_scores: dict[str, float] = {}
    for index, item in enumerate(raw_scale):
        if not isinstance(item, dict):
            raise ValueError(f"scoring_scale[{index}] must be an object")
        rating = require_text(item.get("rating"), f"scoring_scale[{index}].rating")
        score = item.get("score_percent")
        if rating in rating_scores:
            raise ValueError(f"Duplicate scoring rating: {rating}")
        if not isinstance(score, (int, float)) or not 0 <= score <= 100:
            raise ValueError(f"scoring_scale[{index}].score_percent must be 0 to 100")
        require_text(item.get("anchor"), f"scoring_scale[{index}].anchor")
        rating_scores[rating] = float(score)

    max_rounds = int(compiled["acceptance"]["max_refinement_rounds"])
    iteration = assessment.get("iteration")
    if not isinstance(iteration, int) or not 1 <= iteration <= max_rounds:
        raise ValueError(f"iteration must be between 1 and {max_rounds}")
    previous_score = assessment.get("previous_score")
    if previous_score is not None and (
        not isinstance(previous_score, (int, float)) or not 0 <= previous_score <= 100
    ):
        raise ValueError("previous_score must be null or a number from 0 to 100")

    criteria = {item["id"]: item for item in compiled["criteria"]}
    raw_assessments = assessment.get("criterion_assessments")
    if not isinstance(raw_assessments, dict):
        raise ValueError("criterion_assessments must be an object")
    exact_keys(raw_assessments, set(criteria), "criterion_assessment")

    criterion_results: list[dict[str, Any]] = []
    earned_total = 0.0
    group_earned: dict[str, float] = {"core": 0.0}
    group_points: dict[str, float] = {"core": 0.0}
    module_earned: dict[str, float] = {}
    module_points: dict[str, float] = {}
    criterion_ratings: dict[str, str] = {}
    for criterion_id, criterion in criteria.items():
        value = raw_assessments[criterion_id]
        if not isinstance(value, dict):
            raise ValueError(f"criterion_assessments.{criterion_id} must be an object")
        if "score_percent" in value:
            raise ValueError(
                f"criterion_assessments.{criterion_id}.score_percent is not allowed; use rating"
            )
        rating = require_text(
            value.get("rating"), f"criterion_assessments.{criterion_id}.rating"
        )
        if rating not in rating_scores:
            raise ValueError(
                f"criterion_assessments.{criterion_id}.rating must be one of: "
                + ", ".join(rating_scores)
            )
        score = rating_scores[rating]
        criterion_ratings[criterion_id] = rating
        if value.get("verified_by") != verifier_id:
            raise ValueError(
                f"criterion_assessments.{criterion_id}.verified_by must identify the verifier"
            )
        evidence = require_text_list(
            value.get("evidence"), f"criterion_assessments.{criterion_id}.evidence"
        )
        finding = require_text(
            value.get("finding"), f"criterion_assessments.{criterion_id}.finding"
        )
        fix = value.get("fix", "")
        if not isinstance(fix, str):
            raise ValueError(f"criterion_assessments.{criterion_id}.fix must be a string")
        if score < 100:
            fix = require_text(fix, f"criterion_assessments.{criterion_id}.fix")
        paths = require_text_list(
            value.get("artifact_paths"),
            f"criterion_assessments.{criterion_id}.artifact_paths",
        )
        outside = sorted(set(paths) - set(artifacts_by_path))
        if outside:
            raise ValueError(
                f"criterion_assessments.{criterion_id} references artifacts outside scope: "
                + ", ".join(outside)
            )
        raw_run_ids = value.get("harness_run_ids", [])
        run_ids = require_text_list(
            raw_run_ids,
            f"criterion_assessments.{criterion_id}.harness_run_ids",
            allow_empty=True,
        )
        missing_runs = sorted(set(run_ids) - set(harness_runs))
        if missing_runs:
            raise ValueError(
                f"criterion_assessments.{criterion_id} references unknown harness runs: "
                + ", ".join(missing_runs)
            )
        points = float(criterion["points"])
        earned = round(points * float(score) / 100.0, 4)
        earned_total += earned
        if criterion["group"] == "core":
            group_earned["core"] += earned
            group_points["core"] += points
        else:
            module_id = criterion["module_id"]
            module_earned[module_id] = module_earned.get(module_id, 0.0) + earned
            module_points[module_id] = module_points.get(module_id, 0.0) + points
        criterion_results.append(
            {
                "id": criterion_id,
                "name": criterion["name"],
                "anchor": criterion.get("anchor", ""),
                "points": points,
                "rating": rating,
                "score_percent": score,
                "earned_points": round(earned, 2),
                "artifact_paths": paths,
                "evidence": evidence,
                "finding": finding,
                "fix": fix,
                "verified_by": verifier_id,
                "harness_run_ids": run_ids,
                "lost_points": round(points - earned, 2),
            }
        )

    total_score = round(earned_total, 1)
    core_score = round(group_earned["core"] / group_points["core"] * 100.0, 1)
    module_scores: list[dict[str, Any]] = []
    for module in compiled["modules"]:
        module_id = module["id"]
        score = round(module_earned[module_id] / module_points[module_id] * 100.0, 1)
        module_scores.append(
            {
                "id": module_id,
                "name": module["name"],
                "criticality": module["criticality"],
                "points": module["points"],
                "score_percent": score,
            }
        )

    c0_statuses = validate_c0_results(
        assessment.get("c0_gate_results", {}),
        compiled["c0_gates"],
        verifier_id,
        artifacts_by_path,
        harness_runs,
    )
    c1_behavior_statuses = validate_c1_behavior_results(
        assessment.get("c1_behavior_results", {}),
        compiled["c1_behavior_gates"],
        verifier_id,
        artifacts_by_path,
        harness_runs,
        criterion_ratings,
        rating_scores,
    )
    hard_gate_results = validate_gate_results(
        assessment.get("hard_gate_results"),
        {item["id"] for item in compiled["hard_gates"]},
        "hard_gate_result",
        verifier_id,
    )
    execution_results = validate_execution_results(
        assessment.get("execution_results"), harness_runs
    )
    run_status = execution_status(execution_results)

    c0_unknown = sorted(
        gate_id for gate_id, status in c0_statuses.items() if status == "unknown"
    )
    c0_failed = sorted(
        gate_id for gate_id, status in c0_statuses.items() if status == "fail"
    )
    c1_behavior_unknown = sorted(
        gate_id for gate_id, status in c1_behavior_statuses.items() if status == "unknown"
    )
    c1_behavior_failed = sorted(
        gate_id for gate_id, status in c1_behavior_statuses.items() if status == "fail"
    )
    hard_failed = sorted(
        gate_id for gate_id, value in hard_gate_results.items() if value["status"] != "pass"
    )
    c1_floor = float(compiled["acceptance"]["c1_module_score_min"])
    c1_failed = sorted(
        item["id"]
        for item in module_scores
        if item["criticality"] == "C1" and item["score_percent"] < c1_floor
    )

    if (
        compiled["profile_status"] == "NEEDS_DECISION"
        or c0_unknown
        or c1_behavior_unknown
    ):
        quality_status = "NEEDS_DECISION"
    elif c0_failed or c1_behavior_failed or c1_failed or hard_failed or run_status in {
        "FAIL_ORACLE",
        "FAIL_TEST",
        "FLAKY",
    }:
        quality_status = "REJECTED_TEST_OUTPUT"
    elif total_score < float(compiled["acceptance"]["total_score_min"]):
        if iteration >= max_rounds:
            quality_status = "STOPPED_MAX_ITERATIONS"
        elif previous_score is not None and total_score <= float(previous_score):
            quality_status = "STOPPED_NO_PROGRESS"
        else:
            quality_status = "IMPROVE"
    else:
        quality_status = "TESTS_ACCEPTED"

    if quality_status != "TESTS_ACCEPTED":
        completion_status = quality_status
    elif run_status == "PASS":
        completion_status = "COMPLETE"
    elif run_status == "FAIL_PRODUCT_CODE":
        completion_status = "CODE_FIX_REQUIRED"
    elif run_status in {"BLOCKED_ENVIRONMENT", "NOT_RUN"}:
        completion_status = "BLOCKED"
    else:
        completion_status = "REJECTED_TEST_OUTPUT"

    deductions = sorted(
        (item for item in criterion_results if item["lost_points"] > 0),
        key=lambda item: (-item["lost_points"], item["id"]),
    )[:8]
    residual = require_text_list(
        assessment.get("residual_project_risks", []),
        "residual_project_risks",
        allow_empty=True,
    )

    return {
        "schema_version": "2.0.0",
        "run_id": run_id,
        "project": compiled["project"],
        "delivery_form": compiled["delivery_form"],
        "catalog_version": compiled["catalog_version"],
        "iteration": iteration,
        "artifacts": artifacts,
        "provenance": provenance,
        "harness_runs": list(harness_runs.values()),
        "total_score": total_score,
        "core_score": core_score,
        "module_scores": module_scores,
        "quality_status": quality_status,
        "execution_status": run_status,
        "completion_status": completion_status,
        "profile_unresolved": compiled["unresolved_criticality"],
        "c0_unknown": c0_unknown,
        "c0_failed": c0_failed,
        "c0_gate_statuses": c0_statuses,
        "c1_behavior_unknown": c1_behavior_unknown,
        "c1_behavior_failed": c1_behavior_failed,
        "c1_behavior_statuses": c1_behavior_statuses,
        "c1_failed": c1_failed,
        "hard_gates_failed": hard_failed,
        "top_deductions": deductions,
        "criterion_results": criterion_results,
        "execution_results": execution_results,
        "residual_project_risks": residual,
    }


def markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# {result['project']} generated-test assessment",
        "",
        f"- Score: **{result['total_score']}/100**",
        f"- Generated-test quality: **{result['quality_status']}**",
        f"- Execution: **{result['execution_status']}**",
        f"- Completion: **{result['completion_status']}**",
        f"- Delivery form: {result['delivery_form']}",
        f"- Iteration: {result['iteration']}",
        "",
        "## Module scores",
        "",
        f"- Universal core: {result['core_score']}%",
    ]
    for module in result["module_scores"]:
        lines.append(
            f"- {module['name']} ({module['criticality']}): {module['score_percent']}%"
        )

    if (
        result["profile_unresolved"]
        or result["c0_unknown"]
        or result["c1_behavior_unknown"]
    ):
        lines.extend(["", "## Needs decision", ""])
        for value in result["profile_unresolved"]:
            lines.append(f"- {value}")
        for value in result["c0_unknown"]:
            lines.append(f"- C0 gate unresolved: {value}")
        for value in result["c1_behavior_unknown"]:
            lines.append(f"- C1 behavior unresolved: {value}")

    blockers = (
        result["c0_failed"]
        + result["c1_behavior_failed"]
        + result["c1_failed"]
        + result["hard_gates_failed"]
    )
    if blockers:
        lines.extend(["", "## Non-compensatory blockers", ""])
        for value in blockers:
            lines.append(f"- {value}")

    lines.extend(["", "## Highest-impact deductions", ""])
    if not result["top_deductions"]:
        lines.append("No rubric deductions.")
    for item in result["top_deductions"]:
        lines.append(f"- **{item['id']}**: -{item['lost_points']} points — {item['finding']}")
        if item["fix"]:
            lines.append(f"  Fix: {item['fix']}")

    if result["execution_results"]:
        lines.extend(["", "## Execution results", ""])
        for item in result["execution_results"]:
            cause = f" / {item['cause']}" if item["cause"] else ""
            lines.append(f"- {item['id']}: {item['status']}{cause}")
            if item["remediation"]:
                lines.append(f"  Direction: {item['remediation']}")

    if result["residual_project_risks"]:
        lines.extend(["", "## Residual project risks — unscored", ""])
        for value in result["residual_project_risks"]:
            lines.append(f"- {value}")

    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiled_rubric", type=Path)
    parser.add_argument("assessment", type=Path)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        required=True,
        help="Target project root used to verify current artifact SHA-256 values",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args()

    try:
        result = grade(
            load_json(args.compiled_rubric),
            load_json(args.assessment),
            args.artifact_root,
        )
    except (KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
