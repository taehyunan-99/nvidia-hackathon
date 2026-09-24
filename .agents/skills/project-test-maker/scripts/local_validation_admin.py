#!/usr/bin/env python3
"""Create and inspect local validation policy, hooks, and evidence safely."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

import local_validation_gate as gate


PLAN_REQUIRED_KEYS = {"policy_version", "ignore_change_patterns", "lanes"}
PLAN_KEYS = PLAN_REQUIRED_KEYS | {
    "impact_rules",
    "integration_mode",
    "project_working_directory",
}
ROUTER_CONTRACT_SCHEMA_VERSION = "1.0.0"


def load_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise gate.PolicyError(f"cannot read {label} JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise gate.PolicyError(f"{label} must be a JSON object")
    return value


def repo_relative(repo: Path, value: str, field: str) -> tuple[str, Path]:
    text = value.replace("\\", "/")
    if any(character in text for character in ('"', "\n", "\r")):
        raise gate.PolicyError(f"{field} contains unsupported shell characters")
    candidate = Path(text)
    if candidate.is_absolute() or ".." in candidate.parts or not text.strip():
        raise gate.PolicyError(f"{field} must be a repository-relative path")
    destination = (repo / candidate).resolve()
    try:
        destination.relative_to(repo)
    except ValueError as exc:
        raise gate.PolicyError(f"{field} escapes the repository") from exc
    return text, destination


def atomic_write(destination: Path, content: str, *, force: bool) -> None:
    if destination.exists() and not force:
        raise gate.PolicyError(f"refusing to overwrite existing file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def generate_policy(plan: dict[str, object]) -> dict[str, object]:
    unknown = sorted(set(plan) - PLAN_KEYS)
    missing = sorted(PLAN_REQUIRED_KEYS - set(plan))
    if missing:
        raise gate.PolicyError(f"lane plan is missing fields: {', '.join(missing)}")
    if unknown:
        raise gate.PolicyError(f"lane plan contains unknown fields: {', '.join(unknown)}")
    policy = {
        "schema_version": gate.POLICY_SCHEMA_VERSION,
        "execution_topology": "local_only",
        "integration_mode": plan.get("integration_mode", "standalone"),
        "project_working_directory": plan.get("project_working_directory", "."),
        "policy_version": plan["policy_version"],
        "ignore_change_patterns": plan["ignore_change_patterns"],
        "lanes": plan["lanes"],
        "impact_rules": plan.get("impact_rules", []),
    }
    return gate.validate_policy(policy)


def policy_json(policy: dict[str, object]) -> str:
    return json.dumps(policy, ensure_ascii=False, indent=2) + "\n"


def hook_text(policy_path: str, gate_path: str, python_command: str) -> str:
    python = shlex.quote(python_command)
    policy = f'"$repo/{policy_path}"'
    runner = f'"$repo/{gate_path}"'
    return f"""#!/bin/sh
set -eu

zero=0000000000000000000000000000000000000000
count=0
base=
head=

while read -r local_ref local_sha remote_ref remote_sha; do
  if [ \"$local_sha\" = \"$zero\" ]; then
    continue
  fi
  count=$((count + 1))
  base=$remote_sha
  head=$local_sha
done

if [ \"$count\" -eq 0 ]; then
  exit 0
fi
if [ \"$count\" -ne 1 ]; then
  echo \"project-test-maker: push one non-deletion ref at a time\" >&2
  exit 1
fi

repo=$(git rev-parse --show-toplevel)
{python} {runner} {policy} \\
  --repo \"$repo\" --trigger pre_push --base \"$base\" --head \"$head\"
"""


def scaffold_hook(
    repo: Path,
    policy_path: str,
    gate_path: str,
    output_path: str,
    python_command: str,
    *,
    force: bool,
) -> Path:
    policy_relative, policy_file = repo_relative(repo, policy_path, "policy")
    gate_relative, gate_file = repo_relative(repo, gate_path, "gate")
    _, destination = repo_relative(repo, output_path, "output")
    if not policy_file.is_file():
        raise gate.PolicyError(f"policy file does not exist: {policy_relative}")
    normalized = gate.validate_policy(gate.load_json(policy_file))
    if normalized["integration_mode"] == "existing_router":
        raise gate.PolicyError(
            "existing_router mode preserves the owning hook; create a router contract instead"
        )
    if not gate_file.is_file():
        raise gate.PolicyError(f"gate file does not exist: {gate_relative}")
    if not python_command.strip() or "\n" in python_command:
        raise gate.PolicyError("python_command must be one non-empty command token")
    atomic_write(
        destination,
        hook_text(policy_relative, gate_relative, python_command.strip()),
        force=force,
    )
    destination.chmod(destination.stat().st_mode | stat.S_IXUSR)
    return destination


def command_available(command_cwd: Path, command: str) -> bool:
    candidate = Path(command)
    if candidate.is_absolute():
        return candidate.is_file()
    if "/" in command or "\\" in command:
        return (command_cwd / candidate).is_file()
    return shutil.which(command) is not None


def doctor(policy: dict[str, object], repo: Path) -> dict[str, object]:
    normalized = gate.validate_policy(policy)
    errors: list[str] = []
    warnings: list[str] = []
    try:
        gate.validate_impact_evidence(normalized, repo)
    except gate.PolicyError as exc:
        errors.append(str(exc))
    try:
        top_level = Path(gate._git(repo, "rev-parse", "--show-toplevel")).resolve()
        if top_level != repo:
            errors.append(f"repo is not the Git top level: {top_level}")
    except gate.GateBlocked as exc:
        errors.append(f"Git repository unavailable: {exc}")

    try:
        command_cwd = gate.project_command_directory(normalized, repo)
    except gate.PolicyError as exc:
        errors.append(str(exc))
        command_cwd = repo

    lanes: list[dict[str, object]] = []
    for lane in normalized["lanes"]:
        files = gate._repository_files(repo, lane["inputs"])
        available = command_available(command_cwd, lane["command"][0])
        if not available:
            errors.append(
                f"lane {lane['id']} command is unavailable: {lane['command'][0]}"
            )
        if not files:
            warnings.append(f"lane {lane['id']} inputs match no files")
        lanes.append(
            {
                "id": lane["id"],
                "command_available": available,
                "matched_input_files": len(files),
            }
        )
    return {
        "schema_version": "1.0.0",
        "status": "BLOCKED" if errors else ("WARN" if warnings else "PASS"),
        "path_basis": "git_root",
        "project_working_directory": normalized["project_working_directory"],
        "errors": errors,
        "warnings": warnings,
        "lanes": lanes,
    }


def create_router_contract(
    policy: dict[str, object],
    repo: Path,
    route_id: str,
    policy_path: str,
    gate_path: str,
    python_command: str,
) -> dict[str, object]:
    normalized = gate.validate_policy(policy)
    if normalized["integration_mode"] != "existing_router":
        raise gate.PolicyError("router contract requires integration_mode existing_router")
    gate.project_command_directory(normalized, repo)
    policy_relative, policy_file = repo_relative(repo, policy_path, "policy")
    gate_relative, gate_file = repo_relative(repo, gate_path, "gate")
    if not policy_file.is_file():
        raise gate.PolicyError(f"policy file does not exist: {policy_relative}")
    if not gate_file.is_file():
        raise gate.PolicyError(f"gate file does not exist: {gate_relative}")
    if gate.policy_digest(gate.load_json(policy_file)) != gate.policy_digest(normalized):
        raise gate.PolicyError("policy argument does not match the policy file")
    route = gate._non_empty_string(route_id, "route_id")
    python = gate._non_empty_string(python_command, "python_command")
    if "\n" in python or "\r" in python:
        raise gate.PolicyError("python_command must be one command token")
    return {
        "schema_version": ROUTER_CONTRACT_SCHEMA_VERSION,
        "integration_mode": "existing_router",
        "route_id": route,
        "path_basis": "git_root",
        "project_working_directory": normalized["project_working_directory"],
        "policy_digest": gate.policy_digest(normalized),
        "command_contract": {
            "working_directory": "{git_root}/"
            + str(normalized["project_working_directory"]),
            "argv_template": [
                python,
                "{git_root}/" + gate_relative,
                "{git_root}/" + policy_relative,
                "--repo",
                "{git_root}",
                "--trigger",
                "pre_push",
                "--changed-file",
                "{each_git_root_relative_changed_file}",
                "--route-id",
                route,
                "--format",
                "json",
            ],
            "changed_file_cardinality": "repeat --changed-file for each routed path",
            "optional_arguments": {
                "--impact-unknown": "include when the router cannot prove the complete changed-path set"
            },
        },
        "evidence_contract": {
            "schema_version": gate.DELEGATED_EVIDENCE_SCHEMA_VERSION,
            "current_pass_requires": "exact current Project Test Maker policy and lane PASS evidence",
            "router_cache_classification": "HISTORICAL_EVIDENCE",
            "not_run_classification": "NOT_RUN",
            "verification_exit_codes": {
                "CURRENT_PASS": 0,
                "VALID_NONCURRENT": 1,
                "INVALID_OR_BLOCKED": 3,
            },
        },
        "ownership": {
            "existing_router": [
                "multi_ref_processing",
                "project_routing",
                "platform_command_selection",
                "hook_orchestration",
            ],
            "project_test_maker": [
                "policy_validation",
                "root_relative_lane_selection",
                "project_cwd_execution",
                "exact_evidence_validation",
            ],
        },
    }


def evidence_root(repo: Path, explicit: Path | None) -> Path:
    root = explicit.resolve() if explicit else gate.default_evidence_dir(repo)
    if root.name.lower() != "evidence":
        raise gate.PolicyError("evidence root directory must be named evidence")
    if root == repo or root in repo.parents:
        raise gate.PolicyError("evidence root must not be the repository or its ancestor")
    return root


def status_report(
    policy: dict[str, object], repo: Path, evidence_dir: Path
) -> dict[str, object]:
    normalized = gate.validate_policy(policy)
    lanes: list[dict[str, object]] = []
    for lane in normalized["lanes"]:
        fingerprint, input_count = gate.lane_fingerprint(normalized, lane, repo)
        current = evidence_dir / lane["id"] / f"{fingerprint}.json"
        if not lane["cache"]:
            state = "CACHE_DISABLED"
        elif gate.reusable_evidence(evidence_dir, lane, fingerprint):
            state = "REUSABLE"
        elif current.exists():
            state = "STALE_OR_INVALID"
        else:
            state = "MISSING"
        lanes.append(
            {
                "id": lane["id"],
                "criticality": lane["criticality"],
                "fingerprint": fingerprint,
                "input_count": input_count,
                "evidence_state": state,
            }
        )
    return {"schema_version": "1.0.0", "status": "PASS", "lanes": lanes}


def gc_evidence(
    policy: dict[str, object],
    repo: Path,
    evidence_dir: Path,
    *,
    apply: bool,
) -> dict[str, object]:
    normalized = gate.validate_policy(policy)
    current: dict[str, tuple[dict[str, object], str]] = {}
    for lane in normalized["lanes"]:
        fingerprint, _ = gate.lane_fingerprint(normalized, lane, repo)
        current[lane["id"]] = (lane, fingerprint)

    candidates: list[dict[str, str]] = []
    if evidence_dir.exists():
        for path in sorted(evidence_dir.rglob("*.json")):
            resolved = path.resolve()
            try:
                relative = resolved.relative_to(evidence_dir)
            except ValueError as exc:
                raise gate.PolicyError(f"evidence file escaped root: {path}") from exc
            lane_id = relative.parts[0] if len(relative.parts) >= 2 else ""
            reason = "unexpected_layout"
            if lane_id not in current:
                reason = "removed_lane"
            else:
                lane, fingerprint = current[lane_id]
                expected = f"{fingerprint}.json"
                if relative.as_posix() == f"{lane_id}/{expected}":
                    if gate.reusable_evidence(evidence_dir, lane, fingerprint):
                        continue
                    reason = "current_invalid_or_expired"
                else:
                    reason = "stale_fingerprint"
            candidates.append({"path": relative.as_posix(), "reason": reason})

    deleted: list[str] = []
    if apply:
        for item in candidates:
            target = (evidence_dir / item["path"]).resolve()
            try:
                target.relative_to(evidence_dir)
            except ValueError as exc:
                raise gate.PolicyError(f"cleanup target escaped evidence root: {target}") from exc
            if target.is_file():
                target.unlink()
                deleted.append(item["path"])
    return {
        "schema_version": "1.0.0",
        "status": "PASS",
        "mode": "APPLY" if apply else "DRY_RUN",
        "candidate_count": len(candidates),
        "deleted_count": len(deleted),
        "candidates": candidates,
        "deleted": deleted,
    }


def calibrate_impact(
    policy: dict[str, object], observations: dict[str, object]
) -> dict[str, object]:
    normalized = gate.validate_policy(policy)
    raw_observations = observations.get("observations")
    if not isinstance(raw_observations, list) or not raw_observations:
        raise gate.PolicyError("observations must be a non-empty list")
    known_lanes = {lane["id"] for lane in normalized["lanes"]}
    results: list[dict[str, object]] = []
    total_failed = 0
    total_selected_failed = 0
    for index, observation in enumerate(raw_observations):
        field = f"observations[{index}]"
        if not isinstance(observation, dict):
            raise gate.PolicyError(f"{field} must be an object")
        observation_id = gate._non_empty_string(observation.get("id"), f"{field}.id")
        trigger = gate._non_empty_string(observation.get("trigger"), f"{field}.trigger")
        changed_files = gate._string_list(
            observation.get("changed_files"), f"{field}.changed_files", allow_empty=True
        )
        failed_lanes = gate._string_list(
            observation.get("full_run_failed_lanes"),
            f"{field}.full_run_failed_lanes",
            allow_empty=True,
        )
        unknown = sorted(set(failed_lanes) - known_lanes)
        if unknown:
            raise gate.PolicyError(f"{field} contains unknown failed lanes: {unknown}")
        selected, impact_unknown, matched_rules, reasons = gate.select_lanes_detailed(
            normalized, trigger, changed_files
        )
        selected_ids = {lane["id"] for lane in selected}
        missed = sorted(set(failed_lanes) - selected_ids)
        total_failed += len(set(failed_lanes))
        total_selected_failed += len(set(failed_lanes) & selected_ids)
        results.append(
            {
                "id": observation_id,
                "selected_lanes": sorted(selected_ids),
                "full_run_failed_lanes": sorted(set(failed_lanes)),
                "missed_lanes": missed,
                "impact_unknown": impact_unknown,
                "matched_impact_rules": matched_rules,
                "selection_reasons": reasons,
            }
        )
    recall = (
        round(total_selected_failed / total_failed, 4) if total_failed else None
    )
    missed_count = total_failed - total_selected_failed
    return {
        "schema_version": "1.0.0",
        "status": "FAIL" if missed_count else "PASS",
        "faulty_lane_recall": recall,
        "observed_failed_lane_count": total_failed,
        "missed_failed_lane_count": missed_count,
        "observations": results,
    }


def explain_selection(
    policy: dict[str, object],
    repo: Path,
    trigger: str,
    changed_files: list[str],
    *,
    impact_unknown: bool,
    run_all: bool,
) -> dict[str, object]:
    normalized = gate.validate_policy(policy)
    gate.validate_impact_evidence(normalized, repo)
    gate.project_command_directory(normalized, repo)
    changed = [gate._changed_path(item, "changed_files") for item in changed_files]
    selected, unknown, matched_rules, reasons = gate.select_lanes_detailed(
        normalized,
        trigger,
        changed,
        impact_unknown=impact_unknown,
        run_all=run_all,
    )
    return {
        "schema_version": "1.0.0",
        "status": "PASS",
        "commands_executed": False,
        "integration_mode": normalized["integration_mode"],
        "path_basis": "git_root",
        "project_working_directory": normalized["project_working_directory"],
        "trigger": trigger,
        "changed_files": changed,
        "impact_unknown": unknown,
        "matched_impact_rules": matched_rules,
        "selected_lanes": [lane["id"] for lane in selected],
        "selection_reasons": reasons,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate-policy", help="validate a reviewed lane plan and write a policy"
    )
    generate.add_argument("plan", type=Path, help="reviewed lane-plan JSON")
    generate.add_argument("output", help="repository-relative policy output path")
    generate.add_argument("--repo", type=Path, default=Path.cwd(), help="Git root")
    generate.add_argument("--force", action="store_true")

    hook = subparsers.add_parser(
        "scaffold-hook", help="write but do not install a standalone pre-push hook"
    )
    hook.add_argument("policy", help="repository-relative policy path")
    hook.add_argument("--repo", type=Path, default=Path.cwd(), help="Git root")
    hook.add_argument("--gate", default="tools/local_validation_gate.py")
    hook.add_argument("--output", default=".githooks/pre-push")
    hook.add_argument("--python-command", default="python")
    hook.add_argument("--force", action="store_true")

    contract = subparsers.add_parser(
        "create-router-contract", help="write a contract for an existing router"
    )
    contract.add_argument("policy", help="repository-relative policy path")
    contract.add_argument("output", help="repository-relative contract output path")
    contract.add_argument("--repo", type=Path, default=Path.cwd(), help="Git root")
    contract.add_argument("--route-id", required=True)
    contract.add_argument("--gate", default="tools/local_validation_gate.py")
    contract.add_argument("--python-command", default="python")
    contract.add_argument("--force", action="store_true")

    verify = subparsers.add_parser(
        "verify-router-evidence",
        help="classify delegated evidence and pass only CURRENT_PASS",
    )
    verify.add_argument("policy", type=Path, help="validation policy JSON")
    verify.add_argument("record", type=Path, help="delegated result JSON")
    verify.add_argument("--repo", type=Path, default=Path.cwd(), help="Git root")
    verify.add_argument("--evidence-dir", type=Path)

    explain = subparsers.add_parser(
        "explain-selection",
        help="preview selected lanes and reasons without running commands",
    )
    explain.add_argument("policy", type=Path, help="validation policy JSON")
    explain.add_argument("--repo", type=Path, default=Path.cwd(), help="Git root")
    explain.add_argument(
        "--trigger", choices=sorted(gate.ALLOWED_TRIGGERS), required=True
    )
    explain.add_argument("--changed-file", action="append", default=[])
    explain.add_argument("--impact-unknown", action="store_true")
    explain.add_argument("--all", action="store_true")

    for name in ("doctor", "status", "gc"):
        command = subparsers.add_parser(name, help=f"{name} local validation state")
        command.add_argument("policy", type=Path)
        command.add_argument("--repo", type=Path, default=Path.cwd())
        if name in {"status", "gc"}:
            command.add_argument("--evidence-dir", type=Path)
        if name == "gc":
            command.add_argument("--apply", action="store_true")

    calibrate = subparsers.add_parser("calibrate-impact")
    calibrate.add_argument("policy", type=Path)
    calibrate.add_argument("observations", type=Path)
    calibrate.add_argument("--repo", type=Path, default=Path.cwd())

    args = parser.parse_args()
    try:
        repo = args.repo.resolve()
        if args.command == "generate-policy":
            plan = load_object(args.plan.resolve(), "lane plan")
            normalized = generate_policy(plan)
            _, destination = repo_relative(repo, args.output, "output")
            atomic_write(destination, policy_json(normalized), force=args.force)
            result: dict[str, Any] = {
                "status": "PASS",
                "output": str(destination),
                "lane_count": len(normalized["lanes"]),
            }
        elif args.command == "scaffold-hook":
            destination = scaffold_hook(
                repo,
                args.policy,
                args.gate,
                args.output,
                args.python_command,
                force=args.force,
            )
            result = {
                "status": "PASS",
                "output": str(destination),
                "git_configuration_changed": False,
            }
        elif args.command == "create-router-contract":
            policy_path, _ = repo_relative(repo, args.policy, "policy")
            policy = gate.load_json(repo / policy_path)
            generated = create_router_contract(
                policy,
                repo,
                args.route_id,
                policy_path,
                args.gate,
                args.python_command,
            )
            _, destination = repo_relative(repo, args.output, "output")
            atomic_write(destination, policy_json(generated), force=args.force)
            result = {
                "status": "PASS",
                "output": str(destination),
                "hook_or_router_changed": False,
            }
        elif args.command == "verify-router-evidence":
            policy = gate.load_json(args.policy.resolve())
            raw_record = load_object(args.record.resolve(), "delegated evidence")
            record = raw_record.get("delegated_evidence", raw_record)
            if not isinstance(record, dict):
                raise gate.PolicyError("delegated_evidence must be an object")
            root = evidence_root(repo, args.evidence_dir)
            result = gate.verify_delegated_evidence(policy, repo, root, record)
        elif args.command == "explain-selection":
            policy = gate.load_json(args.policy.resolve())
            result = explain_selection(
                policy,
                repo,
                args.trigger,
                args.changed_file,
                impact_unknown=args.impact_unknown,
                run_all=args.all,
            )
        else:
            policy = gate.load_json(args.policy.resolve())
            if args.command == "calibrate-impact":
                normalized = gate.validate_policy(policy)
                gate.validate_impact_evidence(normalized, repo)
                observations = load_object(args.observations.resolve(), "impact observations")
                result = calibrate_impact(normalized, observations)
            elif args.command == "doctor":
                result = doctor(policy, repo)
            else:
                root = evidence_root(repo, args.evidence_dir)
                if args.command == "status":
                    result = status_report(policy, repo, root)
                else:
                    result = gc_evidence(policy, repo, root, apply=args.apply)
    except (OSError, gate.PolicyError, gate.GateBlocked, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        return 3

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command == "verify-router-evidence":
        return 0 if result["current_pass"] else 1
    return 0 if result["status"] in {"PASS", "WARN"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
