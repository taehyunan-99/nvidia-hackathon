#!/usr/bin/env python3
"""Compile a project-specific generated-test rubric from profile evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


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


def allocate(total: float, weighted_ids: list[tuple[str, float]]) -> dict[str, float]:
    weight_sum = sum(weight for _, weight in weighted_ids)
    if weight_sum <= 0:
        raise ValueError("Allocation weights must sum to more than zero")
    result: dict[str, float] = {}
    remaining = round(total, 2)
    for index, (item_id, weight) in enumerate(weighted_ids):
        if index == len(weighted_ids) - 1:
            points = remaining
        else:
            points = round(total * weight / weight_sum, 2)
            remaining = round(remaining - points, 2)
        result[item_id] = points
    return result


def compile_rubric(profile: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    project = require_text(profile.get("project"), "project")
    delivery_form = require_text(profile.get("delivery_form"), "delivery_form")
    if delivery_form not in catalog["delivery_forms"]:
        raise ValueError(
            f"delivery_form must be one of: {', '.join(catalog['delivery_forms'])}"
        )
    profile_evidence = require_text_list(profile.get("profile_evidence"), "profile_evidence")

    selections = profile.get("selected_modules")
    if not isinstance(selections, list) or not 1 <= len(selections) <= 6:
        raise ValueError("selected_modules must contain one to six module selections")

    module_catalog = {module["id"]: module for module in catalog["modules"]}
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    weighted_modules: list[tuple[str, float]] = []
    for index, selection in enumerate(selections):
        if not isinstance(selection, dict):
            raise ValueError(f"selected_modules[{index}] must be an object")
        module_id = require_text(selection.get("id"), f"selected_modules[{index}].id")
        if module_id in selected_ids:
            raise ValueError(f"Duplicate selected module: {module_id}")
        if module_id not in module_catalog:
            raise ValueError(f"Unknown module: {module_id}")
        module = module_catalog[module_id]
        if delivery_form not in module["allowed_delivery_forms"]:
            raise ValueError(
                f"Module {module_id} is not applicable to delivery_form {delivery_form}"
            )
        risk_weight = selection.get("risk_weight")
        if not isinstance(risk_weight, (int, float)) or risk_weight <= 0:
            raise ValueError(f"selected_modules[{index}].risk_weight must be positive")
        rationale = require_text(
            selection.get("rationale"), f"selected_modules[{index}].rationale"
        )
        raw_criteria = selection.get("criteria")
        catalog_criteria = {criterion["id"]: criterion for criterion in module["criteria"]}
        criterion_selections: list[dict[str, Any]] = []
        omitted_criteria: list[dict[str, Any]] = []
        if raw_criteria is None:
            criterion_configuration = "catalog_default"
            for criterion in module["criteria"]:
                criterion_selections.append(
                    {
                        "id": criterion["id"],
                        "risk_weight": float(criterion["relative_weight"]),
                        "rationale": "Catalog default applicability and relative weight.",
                        "evidence": profile_evidence,
                    }
                )
        else:
            criterion_configuration = "project_specific"
            if not isinstance(raw_criteria, list) or not raw_criteria:
                raise ValueError(
                    f"selected_modules[{index}].criteria must be a non-empty array"
                )
            configured_ids: set[str] = set()
            for criterion_index, configured in enumerate(raw_criteria):
                field = f"selected_modules[{index}].criteria[{criterion_index}]"
                if not isinstance(configured, dict):
                    raise ValueError(f"{field} must be an object")
                criterion_id = require_text(configured.get("id"), f"{field}.id")
                if criterion_id not in catalog_criteria:
                    raise ValueError(
                        f"{field}.id is not a criterion in module {module_id}: {criterion_id}"
                    )
                if criterion_id in configured_ids:
                    raise ValueError(f"Duplicate criterion configuration: {criterion_id}")
                configured_ids.add(criterion_id)
                applicability = require_text(
                    configured.get("applicability"), f"{field}.applicability"
                )
                if applicability not in {"selected", "omitted"}:
                    raise ValueError(
                        f"{field}.applicability must be selected or omitted"
                    )
                criterion_rationale = require_text(
                    configured.get("rationale"), f"{field}.rationale"
                )
                criterion_evidence = require_text_list(
                    configured.get("evidence"), f"{field}.evidence"
                )
                if applicability == "selected":
                    criterion_weight = configured.get("risk_weight")
                    if (
                        not isinstance(criterion_weight, (int, float))
                        or isinstance(criterion_weight, bool)
                        or criterion_weight <= 0
                    ):
                        raise ValueError(f"{field}.risk_weight must be positive")
                    criterion_selections.append(
                        {
                            "id": criterion_id,
                            "risk_weight": float(criterion_weight),
                            "rationale": criterion_rationale,
                            "evidence": criterion_evidence,
                        }
                    )
                else:
                    if configured.get("risk_weight") is not None:
                        raise ValueError(
                            f"{field}.risk_weight must be omitted when applicability is omitted"
                        )
                    omitted_criteria.append(
                        {
                            "id": criterion_id,
                            "name": catalog_criteria[criterion_id]["name"],
                            "rationale": criterion_rationale,
                            "evidence": criterion_evidence,
                        }
                    )
            missing_criteria = sorted(set(catalog_criteria) - configured_ids)
            if missing_criteria:
                raise ValueError(
                    f"selected_modules[{index}].criteria must explicitly classify: "
                    + ", ".join(missing_criteria)
                )
            if not criterion_selections:
                raise ValueError(f"Module {module_id} must select at least one criterion")
        selected_ids.add(module_id)
        weighted_modules.append((module_id, float(risk_weight)))
        selected.append(
            {
                "id": module_id,
                "name": module["name"],
                "risk_weight": float(risk_weight),
                "rationale": rationale,
                "criterion_configuration": criterion_configuration,
                "criterion_selections": criterion_selections,
                "omitted_criteria": omitted_criteria,
            }
        )

    criticality = profile.get("criticality_map")
    if not isinstance(criticality, list):
        raise ValueError("criticality_map must be an array")
    criticality_out: list[dict[str, Any]] = []
    criticality_ids: set[str] = set()
    c1_modules: set[str] = set()
    c1_behavior_gates: list[dict[str, Any]] = []
    c0_gates: list[dict[str, Any]] = []
    for index, item in enumerate(criticality):
        if not isinstance(item, dict):
            raise ValueError(f"criticality_map[{index}] must be an object")
        item_id = require_text(item.get("id"), f"criticality_map[{index}].id")
        if item_id in criticality_ids:
            raise ValueError(f"Duplicate criticality ID: {item_id}")
        item_class = require_text(item.get("class"), f"criticality_map[{index}].class")
        if item_class not in {"C0", "C1", "C2"}:
            raise ValueError(f"criticality_map[{index}].class must be C0, C1, or C2")
        behavior = require_text(item.get("behavior"), f"criticality_map[{index}].behavior")
        oracle = require_text(item.get("oracle"), f"criticality_map[{index}].oracle")
        evidence = require_text_list(item.get("evidence"), f"criticality_map[{index}].evidence")
        module_id = item.get("module_id")
        if module_id is not None:
            module_id = require_text(module_id, f"criticality_map[{index}].module_id")
            if module_id not in selected_ids:
                raise ValueError(
                    f"Criticality item {item_id} references unselected module {module_id}"
                )
        if item_class == "C1":
            if module_id is None:
                raise ValueError(f"C1 item {item_id} requires module_id")
            required_criteria = require_text_list(
                item.get("required_criteria"),
                f"criticality_map[{index}].required_criteria",
            )
            selected_module = next(item for item in selected if item["id"] == module_id)
            available = {
                criterion["id"] for criterion in selected_module["criterion_selections"]
            }
            unknown_criteria = sorted(set(required_criteria) - available)
            if unknown_criteria:
                raise ValueError(
                    f"C1 item {item_id} references omitted or unknown criteria in module {module_id}: "
                    + ", ".join(unknown_criteria)
                )
            if len(required_criteria) != len(set(required_criteria)):
                raise ValueError(f"C1 item {item_id} has duplicate required_criteria")
            c1_modules.add(module_id)
            qualified_required_criteria = [
                f"module.{module_id}.{criterion_id}"
                for criterion_id in required_criteria
            ]
        else:
            required_criteria = []
            qualified_required_criteria = []
        requires_parity = bool(item.get("requires_parity", False))
        compiled_item = {
            "id": item_id,
            "class": item_class,
            "behavior": behavior,
            "oracle": oracle,
            "evidence": evidence,
            "module_id": module_id,
            "requires_parity": requires_parity,
            "required_criteria": qualified_required_criteria,
        }
        criticality_ids.add(item_id)
        criticality_out.append(compiled_item)
        if item_class == "C0":
            c0_gates.append(
                {
                    **compiled_item,
                    "required_components": [
                        "approved_oracle",
                        "required_tests",
                        "failure_witness",
                        "reproducibility",
                    ]
                    + (["real_boundary_parity"] if requires_parity else []),
                }
            )
        elif item_class == "C1":
            c1_behavior_gates.append(
                {
                    **compiled_item,
                    "required_criteria": qualified_required_criteria,
                    "required_rating": catalog["acceptance"][
                        "c1_behavior_rating_min"
                    ],
                    "required_components": [
                        "approved_oracle",
                        "required_tests",
                        "verification",
                    ],
                }
            )

    unresolved = require_text_list(
        profile.get("unresolved_criticality", []),
        "unresolved_criticality",
        allow_empty=True,
    )

    module_points = allocate(float(catalog["module_points"]), weighted_modules)
    compiled_modules: list[dict[str, Any]] = []
    criteria: list[dict[str, Any]] = []
    for item in selected:
        module = module_catalog[item["id"]]
        points = module_points[item["id"]]
        criterion_points = allocate(
            points,
            [
                (criterion["id"], float(criterion["risk_weight"]))
                for criterion in item["criterion_selections"]
            ],
        )
        module_criteria: list[dict[str, Any]] = []
        catalog_by_id = {criterion["id"]: criterion for criterion in module["criteria"]}
        for selection in item["criterion_selections"]:
            criterion = catalog_by_id[selection["id"]]
            criterion_id = f"module.{item['id']}.{selection['id']}"
            compiled_criterion = {
                "id": criterion_id,
                "name": criterion["name"],
                "points": criterion_points[selection["id"]],
                "anchor": criterion.get(
                    "anchor",
                    f"Generated tests credibly verify {criterion['name'].lower()} "
                    "against approved project evidence.",
                ),
                "group": "module",
                "module_id": item["id"],
                "risk_weight": selection["risk_weight"],
                "rationale": selection["rationale"],
                "evidence": selection["evidence"],
            }
            criteria.append(compiled_criterion)
            module_criteria.append(compiled_criterion)
        compiled_modules.append(
            {
                **item,
                "points": points,
                "criticality": "C1" if item["id"] in c1_modules else "C2",
                "criteria": module_criteria,
            }
        )

    core_criteria: list[dict[str, Any]] = []
    for criterion in catalog["core_criteria"]:
        compiled_criterion = {
            **criterion,
            "group": "core",
            "module_id": None,
        }
        core_criteria.append(compiled_criterion)
        criteria.append(compiled_criterion)

    total = round(sum(float(item["points"]) for item in criteria), 2)
    if total != float(catalog["total_points"]):
        raise ValueError(f"Compiled rubric totals {total}, expected {catalog['total_points']}")

    return {
        "schema_version": "2.0.0",
        "catalog_version": catalog["version"],
        "project": project,
        "delivery_form": delivery_form,
        "profile_evidence": profile_evidence,
        "profile_status": "NEEDS_DECISION" if unresolved else "READY",
        "unresolved_criticality": unresolved,
        "acceptance": catalog["acceptance"],
        "scoring_scale": catalog["scoring_scale"],
        "core_criteria": core_criteria,
        "modules": compiled_modules,
        "criteria": criteria,
        "criticality_map": criticality_out,
        "c0_gates": c0_gates,
        "c1_behavior_gates": c1_behavior_gates,
        "hard_gates": catalog["hard_gates"],
        "total_points": catalog["total_points"],
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path, help="Project profile JSON")
    parser.add_argument("--catalog", type=Path, help="Override rubric catalog JSON")
    parser.add_argument("--output", type=Path, help="Write compiled rubric JSON")
    parser.add_argument("--format", choices=("json",), default="json")
    args = parser.parse_args()

    catalog_path = args.catalog or (
        Path(__file__).resolve().parent.parent / "references" / "rubric-catalog.json"
    )
    try:
        result = compile_rubric(load_json(args.profile), load_json(catalog_path))
    except (KeyError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
