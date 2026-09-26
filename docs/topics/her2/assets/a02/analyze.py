import argparse
import copy
import csv
import hashlib
import json
import platform
import sys
import time
from collections import Counter
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import numpy as np
from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from jsonschema import Draft202012Validator, FormatChecker

from metrics import CONTACT_CUTOFF, PROBE_RADIUS, RADII, Coordinate, fit, interface, surface, validate_atoms

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
A01 = HERE.parent / "a01"
sys.path.insert(0, str(A01))
import build_inputs as inputs

PDBS = ("1N8Z", "1S78")
SERVICE_KEYS = ("model_number", "label_asym_id", "auth_asym_id", "label_seq_id", "auth_seq_id",
                "insertion_code", "sequence_position", "has_coordinates")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def residue(row):
    return {**{key: row[key] for key in SERVICE_KEYS}, "operator_id": "1"}


@dataclass
class Reference:
    pdb: str
    structure: dict
    artifact: dict
    path: Path
    mapping: dict
    selected: dict
    atoms: list
    target: list
    antibody: list
    coverage: list
    exclusions: dict
    gaps: list
    missing_atoms: list


def load_reference(pdb):
    if pdb not in PDBS:
        raise ValueError("Only the two approved reference entries are supported")
    lock = read_json(A01 / "source-lock.json")
    for item in lock["sources"]:
        source_path = ROOT / item["path"]
        if source_path.stat().st_size != item["bytes"] or digest(source_path) != item["sha256"]:
            raise ValueError(f"Source hash mismatch: {source_path.name}")
    canonical = "".join((A01 / "sources/P04626.fasta").read_text().splitlines()[1:])
    cif, _, mapping, chains, polymers, _ = inputs.inspect_entry(pdb, canonical)
    review = read_json(A01 / "generated/review-input.json")
    if "".join(review["target"]["fasta"].splitlines()[1:]) != canonical:
        raise ValueError("Reference FASTA mismatch")
    if review["target"]["analysis_range"] != {"start": 23, "end": 629}:
        raise ValueError("Approved target range changed")
    structure = copy.deepcopy(next(s for s in read_json(A01 / "generated/structures.json")
                                  if s["structure_id"] == f"{pdb.lower()}-assembly-1"))
    artifact = next(a for a in read_json(A01 / "generated/artifacts.json")
                    if a["artifact_id"] == structure["artifact_id"])
    path = A01 / "sources" / artifact["file_name"]
    if digest(path) != artifact["sha256"]:
        raise ValueError("Artifact and source hash differ")
    assembly = next(a for a in inputs.rows(cif, "_pdbx_struct_assembly_gen") if a["assembly_id"] == "1")
    if assembly["oper_expression"] != "1":
        raise ValueError("Unsupported assembly transform")
    selected_chains = set(assembly["asym_id_list"].split(","))
    mapped = [r for r in mapping if r["label_asym_id"] in selected_chains]
    if structure["residue_mapping"] != [residue(r) for r in mapped]:
        raise ValueError("A-01 residue mapping differs from source")
    roles = {c["label_asym_id"]: c["role"] for c in chains if c["label_asym_id"] in selected_chains}
    expected_chains = [{"role": c["role"], "model_number": 1, "label_asym_id": c["label_asym_id"],
                        "auth_asym_id": c["auth_asym_id"], "operator_id": "1"}
                       for c in chains if c["label_asym_id"] in selected_chains]
    if structure["chain_mapping"] != expected_chains:
        raise ValueError("A-01 chain mapping differs from source")
    candidate = next(c for c in review["candidates"] if c["candidate_id"] == structure["candidate_id"])
    bounds = {"target": review["target"]["analysis_range"]}
    for role in ("heavy", "light"):
        chain = next(c for c in chains if c["label_asym_id"] in selected_chains and c["role"] == role)
        sequence = "".join(candidate[f"{role}_chain_fasta"].splitlines()[1:])
        bounds[role] = candidate[f"{role}_analysis_range"]
        if sequence != polymers[chain["entity_id"]] or bounds[role] != {"start": 1, "end": len(sequence)}:
            raise ValueError("Approved Fab input changed")
    protein_mapping = {(r["label_asym_id"], r["label_seq_id"]): r for r in mapped if r["label_seq_id"] is not None}
    selected = {key: row for key, row in protein_mapping.items()
                if roles[key[0]] in bounds
                and bounds[roles[key[0]]]["start"] <= row["sequence_position"] <= bounds[roles[key[0]]]["end"]}
    raw = inputs.rows(MMCIF2Dict(str(path)), "_atom_site")
    expected_raw = [a for a in inputs.rows(cif, "_atom_site") if a["label_asym_id"] in selected_chains]
    if Counter(map(inputs.atom_signature, raw)) != Counter(map(inputs.atom_signature, expected_raw)):
        raise ValueError("Assembly does not match source coordinates")
    exclusions = Counter()
    atoms = []
    for item in raw:
        if int(item["pdbx_PDB_model_num"]) != 1:
            raise ValueError("Multiple models not supported")
        key = (item["label_asym_id"], inputs.number(item["label_seq_id"]))
        if key not in selected:
            exclusions["nonpolymer" if key[1] is None else "outside_analysis_range"] += 1
            continue
        if item["type_symbol"] in ("H", "D"):
            exclusions["hydrogen_deuterium"] += 1
            continue
        if float(item["occupancy"]) <= 0 or inputs.nullable(item["label_alt_id"]) is not None:
            raise ValueError("Zero occupancy or alternate conformer requires explicit handling")
        if float(item["occupancy"]) != 1:
            raise ValueError("Partial occupancy requires explicit handling")
        if (inputs.number(item["auth_seq_id"]), item["auth_asym_id"], inputs.nullable(item["pdbx_PDB_ins_code"])) != (
                selected[key]["auth_seq_id"], selected[key]["auth_asym_id"], selected[key]["insertion_code"]):
            raise ValueError("Coordinate author identity mismatch")
        atoms.append(Coordinate(key[0], key[1], item["label_atom_id"], item["type_symbol"],
                                tuple(float(item[f"Cartn_{axis}"]) for axis in "xyz")))
    validate_atoms(atoms)
    observed = {a.residue_key for a in atoms}
    if observed != {key for key, row in selected.items() if row["has_coordinates"]}:
        raise ValueError("Missing-coordinate flags do not match usable atoms")
    coverage = []
    gaps = []
    for role in ("target", "heavy", "light"):
        group = [r for key, r in selected.items() if roles[key[0]] == role]
        missing = [r["sequence_position"] for r in group if not r["has_coordinates"]]
        coverage.append({"role": role, "range": bounds[role], "selected_residues": len(group),
                         "observed_residues": len(group) - len(missing), "missing_residues": len(missing),
                         "missing_sequence_ranges": inputs.ranges(missing)})
        if missing:
            gaps.append(f"{role}: {len(missing)} residues lack coordinates at input positions {inputs.ranges(missing)}")
    partial_annotations = inputs.rows(cif, "_pdbx_unobs_or_zero_occ_atoms")
    exclusions["unobserved_atom_annotation_rows_asu"] = len(partial_annotations)
    missing_atoms = []
    atom_keys = {(a.chain, a.label, a.name) for a in atoms}
    for annotation in partial_annotations:
        key = (annotation["label_asym_id"], inputs.number(annotation["label_seq_id"]))
        if key not in selected or int(annotation["PDB_model_num"]) != 1:
            continue
        if (key[0], key[1], annotation["label_atom_id"]) in atom_keys:
            raise ValueError("An unobserved atom annotation has usable coordinates")
        missing_atoms.append({"residue": residue(selected[key]), "atom_name": annotation["label_atom_id"],
                              "component": annotation["label_comp_id"], "annotation": annotation})
    if missing_atoms:
        affected = sorted({(a["residue"]["label_asym_id"], a["residue"]["sequence_position"]) for a in missing_atoms})
        gaps.append(f"{len(missing_atoms)} explicitly unobserved atoms in selected residues (chain, input position): {affected}")
    gaps.extend(["Observed atoms only; complete side chains and missing regions are not reconstructed.",
                 "Glycans, water, ions, membrane and other environment are excluded from this core calculation.",
                 "Whole-range accessibility and absence of clashes cannot be concluded."])
    target = [a for a in atoms if roles[a.chain] == "target"]
    antibody = [a for a in atoms if roles[a.chain] in ("heavy", "light")]
    return Reference(pdb, structure, artifact, path, protein_mapping, selected, atoms, target, antibody,
                     coverage, dict(exclusions), gaps, missing_atoms)


def evidence(ref, topic, value, unit, definition, residues=(), state="measured", reason=None):
    condition = f"a02-{ref.pdb.lower()}-core"
    return {"evidence_id": f"{condition}-{topic}", "candidate_id": ref.structure["candidate_id"],
            "condition_id": condition, "structure_id": ref.structure["structure_id"], "topic": topic,
            "kind": "computed" if state == "measured" else "unknown", "measurement_state": state,
            "value": value, "unit": unit, "definition": definition, "reason": reason,
            "residues": list(residues), "sources": [ref.structure["source"]]}


def calculate(ref, points=(960, 1920)):
    contact = interface(ref.target, ref.antibody)
    if contact["state"] != "measured":
        raise ValueError("Reference lacks a coordinate partner")
    target_keys = {ref.target[i].residue_key for i, _, _, _ in contact["pairs"]}
    antibody_keys = {ref.antibody[j].residue_key for _, j, _, _ in contact["pairs"]}
    pair_keys = {(ref.target[i].residue_key, ref.antibody[j].residue_key) for i, j, _, _ in contact["pairs"]}
    contact_residues = [residue(ref.selected[key]) for key in sorted(target_keys | antibody_keys)]
    summaries = []
    per_residue = []
    for count in points:
        result = surface(ref.target, ref.antibody, count)
        summaries.append({k: v for k, v in result.items() if k not in ("complex_residues", "isolated_residues")})
        if count == points[0]:
            for key, area in sorted(result["complex_residues"].items()):
                per_residue.append({**residue(ref.selected[key]), "complex_sasa_angstrom2": area,
                                    "isolated_sasa_angstrom2": result["isolated_residues"][key],
                                    "buried_sasa_angstrom2": result["isolated_residues"][key] - area})
    delta = {name: {"absolute_angstrom2": abs(summaries[-1][name] - summaries[0][name]),
                    "relative_to_high_resolution": abs(summaries[-1][name] - summaries[0][name]) / summaries[-1][name]
                    if summaries[-1][name] else None}
             for name in ("complex_sasa", "buried_sasa_sum")}
    conditions = {"condition_id": f"a02-{ref.pdb.lower()}-core", "candidate_id": ref.structure["candidate_id"],
                  "kind": "core", "structure_ids": [ref.structure["structure_id"]],
                  "included_components": ["observed HER2 heavy atoms", "observed Fab heavy/light-chain heavy atoms"],
                  "gaps": ref.gaps, "sources": [ref.structure["source"]]}
    evidence_rows = [
        evidence(ref, "interface_contact_residues", len(contact_residues), "residue",
                 "Both partners' unique observed residues with heavy-atom distance <=4.5 angstrom; not affinity.", contact_residues),
        evidence(ref, "minimum_interpartner_distance", contact["minimum_distance"], "angstrom",
                 "Minimum observed target-Fab heavy-atom distance; no safety threshold."),
        evidence(ref, "maximum_interpartner_vdw_overlap", contact["maximum_overlap"], "angstrom",
                 "max(0, max(element radii sum - distance)); no hydrogen-bond classification; NOT clashscore."),
        evidence(ref, "surface_exposure", summaries[0]["complex_sasa"], "angstrom^2",
                 "Observed protein-only Shrake-Rupley complex SASA; 1.4 angstrom probe, 960 points/atom; incomplete environment."),
        evidence(ref, "buried_sasa_sum", summaries[0]["buried_sasa_sum"], "angstrom^2",
                 "SASA(target alone)+SASA(Fab alone)-SASA(complex), same coordinates; BOTH sides, not divided by 2."),
        evidence(ref, "atom_clash", None, None, None, state="not_run",
                 reason="Validated all-atom clash classification with hydrogen-bond/bonded exclusions is not implemented."),
        evidence(ref, "whole_range_accessibility", None, None, None, state="unknown",
                 reason="Missing coordinates and incomplete glycans/environment prevent a whole-range conclusion.")]
    summary = {"pdb_id": ref.pdb, "candidate_id": ref.structure["candidate_id"], "structure_id": ref.structure["structure_id"],
               "source_sha256": ref.artifact["sha256"], "coverage": ref.coverage, "included_atoms": len(ref.atoms),
               "excluded": ref.exclusions, "gaps": ref.gaps,
               "missing_atom_annotations": ref.missing_atoms,
               "contact": {"atom_pairs": len(contact["pairs"]), "residue_pairs": len(pair_keys),
                           "target_residues": len(target_keys), "antibody_residues": len(antibody_keys),
                           "total_residues": len(contact_residues)},
               "minimum_interpartner_distance_angstrom": contact["minimum_distance"],
               "maximum_interpartner_vdw_overlap_angstrom": contact["maximum_overlap"],
               "sasa": summaries, "sasa_resolution_difference": delta, "overall_interpretation": "needs_confirmation"}
    pairs = []
    for i, j, distance, overlap in contact["pairs"]:
        row = {"distance_angstrom": distance, "vdw_overlap_angstrom": overlap}
        for prefix, atom in (("target", ref.target[i]), ("antibody", ref.antibody[j])):
            row.update({f"{prefix}_{key}": value for key, value in residue(ref.selected[atom.residue_key]).items()})
            row[f"{prefix}_atom"] = atom.name
            row[f"{prefix}_element"] = atom.element
        pairs.append(row)
    return summary, conditions, evidence_rows, pairs, per_residue


def align_references(reference, mobile):
    def anchors(ref):
        return {ref.selected[a.residue_key]["sequence_position"]: a for a in ref.target if a.name == "CA"}
    fixed, moving = anchors(reference), anchors(mobile)
    positions = sorted(fixed.keys() & moving.keys())
    matrix, rmsd = fit([fixed[p].xyz for p in positions], [moving[p].xyz for p in positions])
    alignment = {"reference_structure_id": reference.structure["structure_id"],
                 "reference_residues": [residue(reference.selected[fixed[p].residue_key]) for p in positions],
                 "mobile_residues": [residue(mobile.selected[moving[p].residue_key]) for p in positions],
                 "matrix": matrix.ravel().tolist(), "applied": False, "coordinate_unit": "angstrom"}
    return alignment, {"reference": reference.pdb, "mobile": mobile.pdb, "common_ca_count": len(positions),
                       "rmsd_angstrom": rmsd, "reference_positions": positions,
                       "definition": "Global HER2 shared-position CA least-squares fit; not antibody pose accuracy",
                       "matrix_convention": "row-major, column vector, mobile to reference", "applied": False}


def validate_fragments(fragments):
    schema = read_json(ROOT / "docs/frontend-hosting/contracts/service.schema.json")
    for field, definition in (("structures", "Structure"), ("conditions", "Condition"),
                              ("evidence", "Evidence"), ("artifacts", "Artifact")):
        validator = Draft202012Validator({**schema, "$ref": f"#/$defs/{definition}"}, format_checker=FormatChecker())
        for item in fragments[field]:
            validator.validate(item)
    structures = {s["structure_id"]: s for s in fragments["structures"]}
    conditions = {c["condition_id"]: c for c in fragments["conditions"]}
    artifacts = {a["artifact_id"]: a for a in fragments["artifacts"]}
    if len(structures) != len(fragments["structures"]) or len(conditions) != len(fragments["conditions"]):
        raise ValueError("Duplicate structure or condition identity")
    for row in fragments["evidence"]:
        structure, condition = structures[row["structure_id"]], conditions[row["condition_id"]]
        if row["candidate_id"] != structure["candidate_id"] or row["candidate_id"] != condition["candidate_id"]:
            raise ValueError("Cross-candidate evidence")
        if row["structure_id"] not in condition["structure_ids"]:
            raise ValueError("Evidence refers to another condition's structure")
        if any(r not in structure["residue_mapping"] or not r["has_coordinates"] for r in row["residues"]):
            raise ValueError("Measured residue absent from structure")
    for structure in structures.values():
        artifact = artifacts[structure["artifact_id"]]
        file = next(f for f in fragments["files"] if f["artifact_id"] == artifact["artifact_id"])
        if digest(ROOT / file["repository_path"]) != artifact["sha256"]:
            raise ValueError("Artifact content differs")


def run(output):
    started = time.perf_counter()
    refs = [load_reference(p) for p in PDBS]
    output.mkdir(parents=True, exist_ok=True)
    fragments = {"schema_version": "0.1.0", "purpose": "A-02 contract fragments; not a live Result",
                 "structures": [], "conditions": [], "evidence": [], "artifacts": [], "files": []}
    summaries = []
    for ref in refs:
        summary, condition, evidence_rows, pairs, per_residue = calculate(ref)
        summaries.append(summary)
        fragments["structures"].append(copy.deepcopy(ref.structure))
        fragments["conditions"].append(condition)
        fragments["evidence"].extend(evidence_rows)
        fragments["artifacts"].append(ref.artifact)
        fragments["files"].append({"artifact_id": ref.artifact["artifact_id"], "repository_path": ref.path.relative_to(ROOT).as_posix()})
        write_csv(output / f"{ref.pdb.lower()}-contact-pairs.csv", pairs, list(pairs[0]))
        write_csv(output / f"{ref.pdb.lower()}-residue-sasa.csv", per_residue, list(per_residue[0]))
    alignment, alignment_summary = align_references(*refs)
    fragments["structures"][1]["alignment"] = alignment
    fragments["evidence"].append(evidence(refs[1], "her2_common_ca_rmsd", alignment_summary["rmsd_angstrom"], "angstrom",
                                          alignment_summary["definition"], alignment["mobile_residues"]))
    validate_fragments(fragments)
    write_json(output / "service-fragments.json", fragments)
    summary = {"format": "a02-1", "scope": "two approved assembly-1 observed protein cores",
               "parameters": {"contact_cutoff_angstrom": CONTACT_CUTOFF, "probe_radius_angstrom": PROBE_RADIUS,
                              "atomic_radii_angstrom": RADII, "sasa_points": [960, 1920]},
               "entries": summaries, "alignment": alignment_summary,
               "limits": ["No candidate efficacy ranking or validated clash classification",
                          "No full-glycan comparison, prediction input support or live consumer integration"],
               "runtime": {"python": platform.python_version(), "biopython": version("biopython"),
                           "numpy": version("numpy"), "jsonschema": version("jsonschema")}}
    write_json(output / "summary.json", summary)
    files = [A01 / "source-lock.json", A01 / "generated/review-input.json", A01 / "generated/structures.json",
             A01 / "generated/artifacts.json", HERE / "metrics.py", HERE / "analyze.py"]
    write_json(output / "provenance.json", {"inputs_and_implementation": [
        {"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)} for p in files],
        "source_files": read_json(A01 / "source-lock.json")["sources"],
        "output_files": [{"path": p.name, "sha256": digest(p)} for p in sorted(output.iterdir())
                         if p.suffix in (".csv", ".json") and p.name not in ("provenance.json", "validation.json")],
        "elapsed_seconds": round(time.perf_counter() - started, 3)})
    print(json.dumps({"status": "calculated", "contacts": [s["contact"] for s in summaries],
                      "alignment_ca_count": alignment_summary["common_ca_count"],
                      "rmsd_angstrom": round(alignment_summary["rmsd_angstrom"], 4),
                      "seconds": round(time.perf_counter() - started, 2)}))
    return summary, fragments


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=HERE / "generated")
    run(parser.parse_args().out)
