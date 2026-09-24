#!/usr/bin/env python3
"""Run evidence-aware local validation lanes from a project policy."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable


GATE_VERSION = "1.2.0"
POLICY_SCHEMA_VERSION = "1.1.0"
LEGACY_POLICY_SCHEMA_VERSIONS = {"1.0.0"}
EVIDENCE_SCHEMA_VERSION = "1.1.0"
DELEGATED_EVIDENCE_SCHEMA_VERSION = "1.0.0"
ALLOWED_TRIGGERS = {"worktree", "pre_commit", "pre_push", "post_merge", "scheduled"}
ALLOWED_CRITICALITY = {"C0", "C1", "C2"}
ALLOWED_IMPACT_SOURCES = {"dependency", "coverage", "history", "contract"}
ALLOWED_INTEGRATION_MODES = {"standalone", "existing_router"}
ZERO_SHA = "0" * 40
LANE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
AUTOMATIC_ENV_KEYS = (
    "PATH",
    "PATHEXT",
    "VIRTUAL_ENV",
    "CONDA_PREFIX",
    "PYTHONPATH",
    "NODE_ENV",
    "DOTNET_ENVIRONMENT",
    "LANG",
    "LC_ALL",
    "TZ",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "REQUESTS_CA_BUNDLE",
    "AWS_PROFILE",
    "AWS_DEFAULT_REGION",
    "AZURE_CONFIG_DIR",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "DOCKER_HOST",
    "KUBECONFIG",
)


class PolicyError(ValueError):
    """Raised when a local validation policy is invalid."""


class GateBlocked(RuntimeError):
    """Raised when the gate cannot prove it is validating the intended content."""


def load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise PolicyError("policy must be a JSON object")
    return value


def _non_empty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{field} must be a non-empty string")
    return value.strip()


def _string_list(value: object, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        suffix = "" if allow_empty else " and must not be empty"
        raise PolicyError(f"{field} must be a list of strings{suffix}")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_non_empty_string(item, f"{field}[{index}]"))
    return result


def _pattern(value: str, field: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or re.match(r"^[A-Za-z]:", normalized)
        or normalized.startswith("//")
        or ".." in path.parts
    ):
        raise PolicyError(f"{field} must stay within the repository")
    if normalized == ".git" or normalized.startswith(".git/"):
        raise PolicyError(f"{field} must not include the Git directory")
    return normalized


def _relative_directory(value: object, field: str) -> str:
    normalized = _non_empty_string(value, field).replace("\\", "/").rstrip("/") or "."
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or re.match(r"^[A-Za-z]:", normalized)
        or normalized.startswith("//")
        or ".." in path.parts
    ):
        raise PolicyError(f"{field} must stay within the Git root")
    if normalized == ".git" or normalized.startswith(".git/"):
        raise PolicyError(f"{field} must not be the Git directory")
    if any(character in normalized for character in "*?["):
        raise PolicyError(f"{field} must be an exact directory path")
    return path.as_posix()


def _changed_path(value: str, field: str) -> str:
    normalized = _pattern(value, field).lstrip("./")
    if not normalized or any(character in normalized for character in "*?["):
        raise PolicyError(f"{field} must be an exact Git-root-relative file path")
    return normalized


def validate_policy(policy: dict[str, object]) -> dict[str, object]:
    if policy.get("schema_version") not in {
        POLICY_SCHEMA_VERSION,
        *LEGACY_POLICY_SCHEMA_VERSIONS,
    }:
        raise PolicyError(
            f"schema_version must be {POLICY_SCHEMA_VERSION} or a supported legacy version"
        )
    if policy.get("execution_topology") != "local_only":
        raise PolicyError("execution_topology must be local_only")

    integration_mode = _non_empty_string(
        policy.get("integration_mode", "standalone"), "integration_mode"
    )
    if integration_mode not in ALLOWED_INTEGRATION_MODES:
        raise PolicyError(
            f"integration_mode must be one of: {sorted(ALLOWED_INTEGRATION_MODES)}"
        )

    normalized: dict[str, object] = {
        "schema_version": POLICY_SCHEMA_VERSION,
        "execution_topology": "local_only",
        "integration_mode": integration_mode,
        "project_working_directory": _relative_directory(
            policy.get("project_working_directory", "."),
            "project_working_directory",
        ),
        "policy_version": _non_empty_string(policy.get("policy_version"), "policy_version"),
        "ignore_change_patterns": [
            _pattern(item, "ignore_change_patterns")
            for item in _string_list(
                policy.get("ignore_change_patterns", []),
                "ignore_change_patterns",
                allow_empty=True,
            )
        ],
    }

    raw_lanes = policy.get("lanes")
    if not isinstance(raw_lanes, list) or not raw_lanes:
        raise PolicyError("lanes must be a non-empty list")

    lanes: list[dict[str, object]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_lanes):
        prefix = f"lanes[{index}]"
        if not isinstance(raw, dict):
            raise PolicyError(f"{prefix} must be an object")
        lane_id = _non_empty_string(raw.get("id"), f"{prefix}.id")
        if not LANE_ID.fullmatch(lane_id):
            raise PolicyError(f"{prefix}.id must match {LANE_ID.pattern}")
        if lane_id in seen:
            raise PolicyError(f"duplicate lane id: {lane_id}")
        seen.add(lane_id)

        triggers = _string_list(raw.get("triggers"), f"{prefix}.triggers")
        invalid_triggers = set(triggers) - ALLOWED_TRIGGERS
        if invalid_triggers:
            raise PolicyError(f"{prefix}.triggers contains unsupported values: {sorted(invalid_triggers)}")
        if len(triggers) != len(set(triggers)):
            raise PolicyError(f"{prefix}.triggers contains duplicates")

        command = _string_list(raw.get("command"), f"{prefix}.command")
        inputs = [
            _pattern(item, f"{prefix}.inputs")
            for item in _string_list(raw.get("inputs"), f"{prefix}.inputs")
        ]
        change_patterns = [
            _pattern(item, f"{prefix}.change_patterns")
            for item in _string_list(raw.get("change_patterns"), f"{prefix}.change_patterns")
        ]
        if not set(change_patterns).issubset(set(inputs)):
            raise PolicyError(
                f"{prefix}.change_patterns must also appear in inputs so matching changes invalidate evidence"
            )
        criticality = _non_empty_string(raw.get("criticality"), f"{prefix}.criticality")
        if criticality not in ALLOWED_CRITICALITY:
            raise PolicyError(f"{prefix}.criticality must be C0, C1, or C2")

        blocking = raw.get("blocking", True)
        cache = raw.get("cache", True)
        if not isinstance(blocking, bool):
            raise PolicyError(f"{prefix}.blocking must be boolean")
        if not isinstance(cache, bool):
            raise PolicyError(f"{prefix}.cache must be boolean")
        if criticality in {"C0", "C1"} and not blocking:
            raise PolicyError(f"{prefix} cannot make a {criticality} lane non-blocking")

        timeout = raw.get("timeout_seconds")
        budget = raw.get("budget_seconds")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            raise PolicyError(f"{prefix}.timeout_seconds must be a positive integer")
        if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
            raise PolicyError(f"{prefix}.budget_seconds must be a positive integer")

        max_age = raw.get("max_age_seconds")
        if max_age is not None and (
            not isinstance(max_age, int) or isinstance(max_age, bool) or max_age <= 0
        ):
            raise PolicyError(f"{prefix}.max_age_seconds must be null or a positive integer")

        lanes.append(
            {
                "id": lane_id,
                "triggers": triggers,
                "command": command,
                "inputs": inputs,
                "change_patterns": change_patterns,
                "criticality": criticality,
                "blocking": blocking,
                "timeout_seconds": timeout,
                "budget_seconds": budget,
                "cache": cache,
                "max_age_seconds": max_age,
                "fingerprint_env": sorted(
                    set(
                        _string_list(
                            raw.get("fingerprint_env", []),
                            f"{prefix}.fingerprint_env",
                            allow_empty=True,
                        )
                    )
                ),
                "toolchain": sorted(
                    set(
                        _string_list(
                            raw.get("toolchain", []),
                            f"{prefix}.toolchain",
                            allow_empty=True,
                        )
                    )
                ),
            }
        )

    normalized["lanes"] = lanes
    for required_trigger in ("worktree", "pre_push"):
        if not any(
            required_trigger in lane["triggers"] and lane["blocking"] for lane in lanes
        ):
            raise PolicyError(
                f"local_only policy requires at least one blocking {required_trigger} lane"
            )

    raw_rules = policy.get("impact_rules", [])
    if not isinstance(raw_rules, list):
        raise PolicyError("impact_rules must be a list")
    impact_rules: list[dict[str, object]] = []
    rule_ids: set[str] = set()
    lane_by_id = {lane["id"]: lane for lane in lanes}
    for index, raw in enumerate(raw_rules):
        prefix = f"impact_rules[{index}]"
        if not isinstance(raw, dict):
            raise PolicyError(f"{prefix} must be an object")
        rule_id = _non_empty_string(raw.get("id"), f"{prefix}.id")
        if not LANE_ID.fullmatch(rule_id):
            raise PolicyError(f"{prefix}.id must match {LANE_ID.pattern}")
        if rule_id in rule_ids:
            raise PolicyError(f"duplicate impact rule id: {rule_id}")
        rule_ids.add(rule_id)
        source = _non_empty_string(raw.get("source"), f"{prefix}.source")
        if source not in ALLOWED_IMPACT_SOURCES:
            raise PolicyError(
                f"{prefix}.source must be one of: {sorted(ALLOWED_IMPACT_SOURCES)}"
            )
        patterns = [
            _pattern(item, f"{prefix}.change_patterns")
            for item in _string_list(raw.get("change_patterns"), f"{prefix}.change_patterns")
        ]
        selected_lane_ids = _string_list(raw.get("lane_ids"), f"{prefix}.lane_ids")
        unknown_lanes = sorted(set(selected_lane_ids) - set(lane_by_id))
        if unknown_lanes:
            raise PolicyError(
                f"{prefix}.lane_ids contains unknown lanes: {unknown_lanes}"
            )
        evidence = [
            _pattern(item, f"{prefix}.evidence")
            for item in _string_list(raw.get("evidence"), f"{prefix}.evidence")
        ]
        if any(any(character in item for character in "*?[") for item in evidence):
            raise PolicyError(f"{prefix}.evidence must contain exact repository paths")
        for lane_id in selected_lane_ids:
            missing_evidence = sorted(set(evidence) - set(lane_by_id[lane_id]["inputs"]))
            if missing_evidence:
                raise PolicyError(
                    f"{prefix} evidence must appear in lane {lane_id} inputs: "
                    + ", ".join(missing_evidence)
                )
        impact_rules.append(
            {
                "id": rule_id,
                "source": source,
                "change_patterns": patterns,
                "lane_ids": selected_lane_ids,
                "evidence": evidence,
                "rationale": _non_empty_string(raw.get("rationale"), f"{prefix}.rationale"),
            }
        )
    normalized["impact_rules"] = impact_rules
    return normalized


def _matches(path: str, patterns: Iterable[str]) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)


def select_lanes(
    policy: dict[str, object],
    trigger: str,
    changed_files: Iterable[str],
    *,
    impact_unknown: bool = False,
    run_all: bool = False,
) -> tuple[list[dict[str, object]], bool]:
    selected, unknown, _, _ = select_lanes_detailed(
        policy,
        trigger,
        changed_files,
        impact_unknown=impact_unknown,
        run_all=run_all,
    )
    return selected, unknown


def select_lanes_detailed(
    policy: dict[str, object],
    trigger: str,
    changed_files: Iterable[str],
    *,
    impact_unknown: bool = False,
    run_all: bool = False,
) -> tuple[list[dict[str, object]], bool, list[str], dict[str, list[str]]]:
    if trigger not in ALLOWED_TRIGGERS:
        raise PolicyError(f"unsupported trigger: {trigger}")
    lanes = [lane for lane in policy["lanes"] if trigger in lane["triggers"]]
    lane_ids = {lane["id"] for lane in lanes}
    reasons: dict[str, list[str]] = {lane["id"]: [] for lane in lanes}
    if run_all or trigger == "scheduled":
        for lane in lanes:
            reasons[lane["id"]].append("run_all" if run_all else "scheduled")
        return lanes, impact_unknown, [], reasons

    selected: set[str] = {
        lane["id"] for lane in lanes if lane["criticality"] in {"C0", "C1"}
    }
    for lane_id in selected:
        reasons[lane_id].append("criticality")
    ignored = policy["ignore_change_patterns"]
    unknown = impact_unknown
    changed: list[str] = []
    for raw_path in changed_files:
        path = raw_path.replace("\\", "/").lstrip("./")
        if not path or _matches(path, ignored):
            continue
        changed.append(path)
        matched = [lane for lane in lanes if _matches(path, lane["change_patterns"])]
        if matched:
            for lane in matched:
                selected.add(lane["id"])
                reasons[lane["id"]].append(f"path:{path}")
        else:
            unknown = True

    matched_rules: list[str] = []
    for rule in policy.get("impact_rules", []):
        if any(
            _matches(path, rule["change_patterns"]) or path in rule["evidence"]
            for path in changed
        ):
            matched_rules.append(rule["id"])
            for lane_id in rule["lane_ids"]:
                if lane_id in lane_ids:
                    selected.add(lane_id)
                    reasons[lane_id].append(f"impact_rule:{rule['id']}")

    if unknown:
        for lane in lanes:
            if lane["blocking"]:
                selected.add(lane["id"])
                reasons[lane["id"]].append("unknown_impact_fallback")
    return (
        [lane for lane in lanes if lane["id"] in selected],
        unknown,
        matched_rules,
        {lane_id: values for lane_id, values in reasons.items() if lane_id in selected},
    )


def validate_impact_evidence(policy: dict[str, object], repo: Path) -> None:
    for rule in policy.get("impact_rules", []):
        for relative in rule["evidence"]:
            if not (repo / relative).is_file():
                raise PolicyError(
                    f"impact rule {rule['id']} evidence file does not exist: {relative}"
                )


def project_command_directory(policy: dict[str, object], repo: Path) -> Path:
    root = repo.resolve()
    candidate = (root / str(policy["project_working_directory"])).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PolicyError("project_working_directory escapes the Git root") from exc
    if not candidate.is_dir():
        raise PolicyError(
            f"project_working_directory does not exist or is not a directory: "
            f"{policy['project_working_directory']}"
        )
    return candidate


def _repository_files(repo: Path, patterns: Iterable[str]) -> list[Path]:
    result: dict[str, Path] = {}
    for pattern in sorted(set(patterns)):
        for path in repo.glob(pattern):
            try:
                relative = path.relative_to(repo)
            except ValueError:
                continue
            if relative.parts and relative.parts[0] == ".git":
                continue
            if path.is_file() or path.is_symlink():
                result[relative.as_posix()] = path
    return [result[key] for key in sorted(result)]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _automatic_identity(
    lane: dict[str, object],
    command_cwd: Path,
    environment: dict[str, str],
) -> dict[str, object]:
    token = lane["command"][0]
    command_path = Path(token)
    resolved: Path | None = None
    if command_path.is_absolute() and command_path.is_file():
        resolved = command_path.resolve()
    elif "/" in token or "\\" in token:
        candidate = (command_cwd / command_path).resolve()
        if candidate.is_file():
            resolved = candidate
    else:
        found = shutil.which(token, path=environment.get("PATH", ""))
        if found:
            resolved = Path(found).resolve()

    executable: dict[str, object] = {"token": token, "resolved": None, "sha256": None}
    if resolved is not None:
        executable["resolved"] = str(resolved)
        try:
            executable["sha256"] = _sha256_file(resolved)
        except OSError:
            executable["sha256"] = "UNREADABLE"
    return {
        "command_executable": executable,
        "environment": {
            key: hashlib.sha256(environment.get(key, "").encode("utf-8")).hexdigest()
            for key in AUTOMATIC_ENV_KEYS
        },
    }


def lane_fingerprint(
    policy: dict[str, object],
    lane: dict[str, object],
    repo: Path,
    environ: dict[str, str] | None = None,
    repository_files: list[Path] | None = None,
) -> tuple[str, int]:
    environment = os.environ if environ is None else environ
    command_cwd = project_command_directory(policy, repo)
    digest = hashlib.sha256()
    identity = {
        "gate_version": GATE_VERSION,
        "gate_implementation_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "policy": policy,
        "lane": lane,
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "path_basis": "git_root",
        "project_working_directory": policy["project_working_directory"],
        "automatic_identity": _automatic_identity(lane, command_cwd, environment),
        "environment": {
            key: hashlib.sha256(environment.get(key, "").encode("utf-8")).hexdigest()
            for key in lane["fingerprint_env"]
        },
    }
    digest.update(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8"))

    count = 0
    files = (
        _repository_files(repo, lane["inputs"])
        if repository_files is None
        else repository_files
    )
    for path in files:
        relative = path.relative_to(repo).as_posix()
        if not _matches(relative, lane["inputs"]):
            continue
        count += 1
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"SYMLINK\0")
            digest.update(os.readlink(path).encode("utf-8"))
        else:
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
        digest.update(b"\0")

    for pattern in lane["inputs"]:
        digest.update(b"PATTERN\0")
        digest.update(pattern.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest(), count


def _evidence_path(evidence_dir: Path, lane_id: str, fingerprint: str) -> Path:
    return evidence_dir / lane_id / f"{fingerprint}.json"


def reusable_evidence(
    evidence_dir: Path,
    lane: dict[str, object],
    fingerprint: str,
    *,
    now: float | None = None,
) -> bool:
    if not lane["cache"]:
        return False
    path = _evidence_path(evidence_dir, lane["id"], fingerprint)
    try:
        with path.open("r", encoding="utf-8") as handle:
            evidence = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(evidence, dict):
        return False
    if (
        evidence.get("schema_version") != EVIDENCE_SCHEMA_VERSION
        or evidence.get("gate_version") != GATE_VERSION
        or evidence.get("lane_id") != lane["id"]
        or evidence.get("fingerprint") != fingerprint
        or evidence.get("status") != "PASS"
    ):
        return False
    max_age = lane["max_age_seconds"]
    if max_age is not None:
        created_epoch = evidence.get("created_epoch")
        if not isinstance(created_epoch, (int, float)):
            return False
        current = time.time() if now is None else now
        if current - float(created_epoch) > max_age:
            return False
    return True


def write_pass_evidence(
    evidence_dir: Path,
    lane: dict[str, object],
    fingerprint: str,
    duration_seconds: float,
    input_count: int,
) -> None:
    destination = _evidence_path(evidence_dir, lane["id"], fingerprint)
    destination.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    record = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "gate_version": GATE_VERSION,
        "lane_id": lane["id"],
        "fingerprint": fingerprint,
        "status": "PASS",
        "created_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "created_epoch": now,
        "duration_seconds": round(duration_seconds, 3),
        "input_count": input_count,
    }
    handle, temporary = tempfile.mkstemp(prefix="evidence-", suffix=".json", dir=destination.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(record, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def execute_lane(lane: dict[str, object], command_cwd: Path) -> dict[str, object]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            lane["command"],
            cwd=command_cwd,
            text=True,
            capture_output=True,
            timeout=lane["timeout_seconds"],
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "TIMEOUT",
            "exit_code": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def run_gate(
    policy: dict[str, object],
    repo: Path,
    trigger: str,
    changed_files: Iterable[str],
    evidence_dir: Path,
    *,
    impact_unknown: bool = False,
    run_all: bool = False,
    force: bool = False,
    route_id: str | None = None,
    environ: dict[str, str] | None = None,
    executor: Callable[[dict[str, object], Path], dict[str, object]] = execute_lane,
) -> dict[str, object]:
    normalized = validate_policy(policy)
    validate_impact_evidence(normalized, repo)
    command_cwd = project_command_directory(normalized, repo)
    changed = [_changed_path(item, "changed_files") for item in changed_files]
    selected, unknown, matched_rules, selection_reasons = select_lanes_detailed(
        normalized,
        trigger,
        changed,
        impact_unknown=impact_unknown,
        run_all=run_all,
    )
    results: list[dict[str, object]] = []
    selected_patterns = [pattern for lane in selected for pattern in lane["inputs"]]
    repository_files = _repository_files(repo, selected_patterns) if selected else []
    for lane in selected:
        fingerprint, input_count = lane_fingerprint(
            normalized,
            lane,
            repo,
            environ,
            repository_files=repository_files,
        )
        if not force and reusable_evidence(evidence_dir, lane, fingerprint):
            results.append(
                {
                    "id": lane["id"],
                    "criticality": lane["criticality"],
                    "blocking": lane["blocking"],
                    "status": "REUSED",
                    "fingerprint": fingerprint,
                    "input_count": input_count,
                    "budget_seconds": lane["budget_seconds"],
                }
            )
            continue
        execution = executor(lane, command_cwd)
        status = execution.get("status")
        if status not in {"PASS", "FAIL", "TIMEOUT"}:
            raise RuntimeError(f"executor returned unsupported status for {lane['id']}: {status}")
        duration = float(execution.get("duration_seconds", 0.0))
        result = {
            "id": lane["id"],
            "criticality": lane["criticality"],
            "blocking": lane["blocking"],
            "fingerprint": fingerprint,
            "input_count": input_count,
            "budget_seconds": lane["budget_seconds"],
            "over_budget": duration > lane["budget_seconds"],
            **execution,
        }
        results.append(result)
        if status == "PASS" and lane["cache"]:
            write_pass_evidence(evidence_dir, lane, fingerprint, duration, input_count)

    failed_blocking = [
        item["id"]
        for item in results
        if item["blocking"] and item["status"] not in {"PASS", "REUSED"}
    ]
    result = {
        "schema_version": "1.0.0",
        "trigger": trigger,
        "status": "FAIL" if failed_blocking else "PASS",
        "path_basis": "git_root",
        "project_working_directory": normalized["project_working_directory"],
        "impact_unknown": unknown,
        "matched_impact_rules": matched_rules,
        "selected_lanes": [lane["id"] for lane in selected],
        "selection_reasons": selection_reasons,
        "failed_blocking_lanes": failed_blocking,
        "evidence_directory": str(evidence_dir.resolve()),
        "results": results,
    }
    if route_id is not None:
        if normalized["integration_mode"] != "existing_router":
            raise PolicyError("--route-id requires integration_mode existing_router")
        result["delegated_evidence"] = delegated_evidence_record(
            route_id, normalized, changed, result
        )
    return result


def policy_digest(policy: dict[str, object]) -> str:
    normalized = validate_policy(policy)
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def delegated_evidence_record(
    route_id: str,
    policy: dict[str, object],
    changed_files: Iterable[str],
    result: dict[str, object],
) -> dict[str, object]:
    normalized = validate_policy(policy)
    return {
        "schema_version": DELEGATED_EVIDENCE_SCHEMA_VERSION,
        "evidence_kind": "router_delegated_execution",
        "source": "project_test_maker",
        "route_id": _non_empty_string(route_id, "route_id"),
        "status": result["status"],
        "trigger": result["trigger"],
        "path_basis": "git_root",
        "project_working_directory": normalized["project_working_directory"],
        "policy_digest": policy_digest(normalized),
        "changed_files": sorted(set(changed_files)),
        "impact_unknown": result["impact_unknown"],
        "selected_lanes": result["selected_lanes"],
        "lane_results": [
            {
                "id": item["id"],
                "status": item["status"],
                "fingerprint": item["fingerprint"],
            }
            for item in result["results"]
        ],
    }


def verify_delegated_evidence(
    policy: dict[str, object],
    repo: Path,
    evidence_dir: Path,
    record: dict[str, object],
) -> dict[str, object]:
    normalized = validate_policy(policy)
    if record.get("schema_version") != DELEGATED_EVIDENCE_SCHEMA_VERSION:
        raise PolicyError(
            f"delegated evidence schema_version must be {DELEGATED_EVIDENCE_SCHEMA_VERSION}"
        )
    if record.get("evidence_kind") != "router_delegated_execution":
        raise PolicyError("delegated evidence_kind must be router_delegated_execution")
    route_id = _non_empty_string(record.get("route_id"), "route_id")
    source = _non_empty_string(record.get("source"), "source")
    status = _non_empty_string(record.get("status"), "status")
    if status not in {"PASS", "FAIL", "BLOCKED", "NOT_RUN"}:
        raise PolicyError("delegated evidence status must be PASS, FAIL, BLOCKED, or NOT_RUN")
    if status == "NOT_RUN":
        return {
            "schema_version": "1.0.0",
            "verification_status": "VALID",
            "route_id": route_id,
            "execution_status": "NOT_RUN",
            "evidence_state": "NOT_RUN",
            "current_pass": False,
        }
    if source == "existing_router_cache":
        return {
            "schema_version": "1.0.0",
            "verification_status": "VALID",
            "route_id": route_id,
            "execution_status": status,
            "evidence_state": "HISTORICAL_EVIDENCE",
            "current_pass": False,
        }
    if source != "project_test_maker":
        raise PolicyError("delegated evidence source is unsupported")
    if status != "PASS":
        return {
            "schema_version": "1.0.0",
            "verification_status": "VALID",
            "route_id": route_id,
            "execution_status": status,
            "evidence_state": "CURRENT_NONPASS",
            "current_pass": False,
        }
    if normalized["integration_mode"] != "existing_router":
        raise PolicyError("Project Test Maker delegated evidence requires existing_router mode")
    if record.get("path_basis") != "git_root":
        raise PolicyError("delegated evidence path_basis must be git_root")
    if record.get("project_working_directory") != normalized["project_working_directory"]:
        raise PolicyError("delegated evidence project_working_directory is not current")
    if record.get("policy_digest") != policy_digest(normalized):
        raise PolicyError("delegated evidence policy_digest is not current")
    trigger = _non_empty_string(record.get("trigger"), "trigger")
    changed = [
        _changed_path(item, "changed_files")
        for item in _string_list(record.get("changed_files"), "changed_files", allow_empty=True)
    ]
    impact_unknown = record.get("impact_unknown", False)
    if not isinstance(impact_unknown, bool):
        raise PolicyError("impact_unknown must be boolean")
    selected, _, _, _ = select_lanes_detailed(
        normalized, trigger, changed, impact_unknown=impact_unknown
    )
    expected_ids = [lane["id"] for lane in selected]
    if record.get("selected_lanes") != expected_ids:
        raise PolicyError("delegated evidence selected_lanes do not match current selection")
    raw_results = record.get("lane_results")
    if not isinstance(raw_results, list):
        raise PolicyError("lane_results must be a list")
    by_id: dict[str, dict[str, object]] = {}
    for index, item in enumerate(raw_results):
        if not isinstance(item, dict):
            raise PolicyError(f"lane_results[{index}] must be an object")
        lane_id = _non_empty_string(item.get("id"), f"lane_results[{index}].id")
        if lane_id in by_id:
            raise PolicyError(f"duplicate lane result: {lane_id}")
        by_id[lane_id] = item
    if set(by_id) != set(expected_ids):
        raise PolicyError("delegated evidence lane_results do not match selected lanes")
    for lane in selected:
        item = by_id[lane["id"]]
        fingerprint, _ = lane_fingerprint(normalized, lane, repo)
        if item.get("fingerprint") != fingerprint:
            raise PolicyError(f"delegated evidence fingerprint is not current for {lane['id']}")
        if lane["blocking"]:
            if item.get("status") not in {"PASS", "REUSED"}:
                raise PolicyError(f"delegated evidence blocking lane did not pass: {lane['id']}")
            if not reusable_evidence(evidence_dir, lane, fingerprint):
                raise PolicyError(
                    f"delegated evidence has no exact reusable Project Test Maker PASS for {lane['id']}"
                )
    return {
        "schema_version": "1.0.0",
        "verification_status": "VALID",
        "route_id": route_id,
        "execution_status": "PASS",
        "evidence_state": "CURRENT_PASS",
        "current_pass": True,
        "selected_lanes": expected_ids,
    }


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise GateBlocked(message)
    return completed.stdout.strip()


def worktree_changes(repo: Path) -> list[str]:
    commands = (
        ("diff", "--name-only", "HEAD"),
        ("diff", "--cached", "--name-only", "HEAD"),
        ("ls-files", "--others", "--exclude-standard"),
    )
    changed: set[str] = set()
    for command in commands:
        output = _git(repo, *command)
        changed.update(line for line in output.splitlines() if line)
    return sorted(changed)


def staged_changes(repo: Path) -> list[str]:
    output = _git(repo, "diff", "--cached", "--name-only", "HEAD")
    return sorted(line for line in output.splitlines() if line)


def pre_push_changes(repo: Path, base: str, head: str) -> tuple[list[str], bool]:
    if not head or set(head) == {"0"}:
        raise GateBlocked("deletion pushes do not require a local validation run")
    if _git(repo, "status", "--porcelain"):
        raise GateBlocked("pre-push requires a clean worktree; commit or stash local changes")
    current = _git(repo, "rev-parse", "HEAD")
    resolved_head = _git(repo, "rev-parse", head)
    if current != resolved_head:
        raise GateBlocked("outgoing revision is not checked-out HEAD; check out the pushed branch")
    if not base or set(base) == {"0"}:
        return [], True
    output = _git(repo, "diff", "--name-only", base, head)
    return sorted(line for line in output.splitlines() if line), False


def default_evidence_dir(repo: Path) -> Path:
    git_dir = Path(_git(repo, "rev-parse", "--git-dir"))
    if not git_dir.is_absolute():
        git_dir = repo / git_dir
    return git_dir.resolve() / "project-test-maker" / "evidence"


def text_report(result: dict[str, object]) -> str:
    lines = [
        f"Local validation: {result['status']}",
        f"Trigger: {result['trigger']}",
        f"Path basis: {result['path_basis']}",
        f"Project working directory: {result['project_working_directory']}",
        f"Evidence: {result['evidence_directory']}",
        f"Impact unknown: {str(result['impact_unknown']).lower()}",
    ]
    if result["matched_impact_rules"]:
        lines.append(
            "Matched impact rules: " + ", ".join(result["matched_impact_rules"])
        )
    if not result["results"]:
        lines.append("No lanes selected.")
    for item in result["results"]:
        duration = item.get("duration_seconds")
        suffix = f" ({duration}s)" if duration is not None else ""
        budget = " / OVER BUDGET" if item.get("over_budget") else ""
        reasons = result["selection_reasons"].get(item["id"], [])
        reason_suffix = f" / {', '.join(reasons)}" if reasons else ""
        lines.append(
            f"- {item['id']}: {item['status']}{suffix}{budget}{reason_suffix}"
        )
        if item.get("stderr_tail"):
            lines.append(f"  stderr: {item['stderr_tail'].strip()}")
    delegated = result.get("delegated_evidence")
    if isinstance(delegated, dict):
        lines.append(
            f"Delegated record: emitted for route {delegated['route_id']} "
            f"with execution {delegated['status']}"
        )
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--trigger", choices=sorted(ALLOWED_TRIGGERS), required=True)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--impact-unknown", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--route-id")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    try:
        repo = args.repo.resolve()
        policy = load_json(args.policy.resolve())
        changed = list(args.changed_file)
        impact_unknown = args.impact_unknown
        if not changed and not args.all and not impact_unknown:
            if args.trigger == "worktree":
                changed = worktree_changes(repo)
            elif args.trigger == "pre_commit":
                changed = staged_changes(repo)
            elif args.trigger == "pre_push":
                if not args.head or args.base is None:
                    raise GateBlocked("pre-push requires --base and --head from exactly one pushed ref")
                changed, impact_unknown = pre_push_changes(repo, args.base, args.head)
            elif args.trigger == "post_merge":
                if args.base and args.head:
                    changed, impact_unknown = pre_push_changes(repo, args.base, args.head)
                else:
                    impact_unknown = True
        evidence_dir = (
            args.evidence_dir.resolve() if args.evidence_dir else default_evidence_dir(repo)
        )
        result = run_gate(
            policy,
            repo,
            args.trigger,
            changed,
            evidence_dir,
            impact_unknown=impact_unknown,
            run_all=args.all,
            force=args.force,
            route_id=args.route_id,
        )
    except (OSError, PolicyError, GateBlocked, json.JSONDecodeError) as exc:
        error = {"status": "BLOCKED", "error": str(exc)}
        if args.format == "json":
            print(json.dumps(error, ensure_ascii=False, indent=2))
        else:
            print(f"Local validation: BLOCKED\n{exc}", file=sys.stderr)
        return 3

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(text_report(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
