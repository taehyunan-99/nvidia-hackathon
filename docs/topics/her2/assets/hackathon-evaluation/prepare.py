"""Build frozen demo inputs; independently cross-check contacts without logic imports."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import gemmi
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "pyproject.toml").exists())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sequence(text):
    return "".join(line.strip() for line in text.splitlines() if not line.startswith(">"))


def independent_contacts(block, target, antibody):
    fields = ["label_asym_id", "label_seq_id", "type_symbol", "Cartn_x", "Cartn_y", "Cartn_z", "pdbx_PDB_model_num"]
    groups = [[], []]
    for row in block.find(["_atom_site." + key for key in fields]):
        chain, seq, element, x, y, z, model = list(row)
        if model != "1" or element in {"H", "D"} or not seq.isdigit():
            continue
        group = 0 if chain in target else 1 if chain in antibody else None
        if group is not None:
            groups[group].append(((chain, int(seq)), (float(x), float(y), float(z))))
    left, right = groups
    if not left or not right:
        raise ValueError("Missing reference chains")
    xyz = np.array([pos for _, pos in right])
    selected = set()
    for start in range(0, len(left), 128):
        part = left[start:start + 128]
        delta = np.array([pos for _, pos in part])[:, None, :] - xyz[None, :, :]
        a, b = np.where(np.sum(delta * delta, axis=2) <= 4.5 ** 2)
        selected.update(part[int(i)][0] for i in set(a))
        selected.update(right[int(i)][0] for i in set(b))
    return [{"chain": c, "seq": n} for c, n in sorted(selected)]


def main():
    fixture = ROOT / "docs/frontend-hosting/fixtures/public-reference-input.json"
    original = json.loads(fixture.read_text())
    locked = json.loads((ROOT / "docs/topics/her2/assets/a01/source-lock.json").read_text())
    expected_hashes = {Path(s["path"]).name: s["sha256"] for s in locked["sources"]}
    stored_contacts = json.loads((ROOT / "frontend/public/structures/contacts.json").read_text())
    refs, sources = {}, []
    for pid, index, heavy_id, light_id, target, antibody in (
        ("1N8Z", 0, "2", "1", {"C"}, {"A", "B"}),
        ("1S78", 1, "3", "2", {"A"}, {"C", "D"}),
    ):
        path = ROOT / "frontend/public/structures" / f"{pid}.cif"
        if sha(path) != expected_hashes[path.name]:
            raise ValueError(f"Reference changed: {pid}")
        block = gemmi.cif.read_file(str(path)).sole_block()
        entities = {r[0]: "".join(gemmi.cif.as_string(r[1]).split()) for r in block.find(
            ["_entity_poly.entity_id", "_entity_poly.pdbx_seq_one_letter_code_can"])}
        candidate = original["candidates"][index]
        for field, eid in (("heavy_chain_fasta", heavy_id), ("light_chain_fasta", light_id)):
            if sequence(candidate[field]) != entities[eid]:
                raise ValueError(f"Sequence mismatch: {pid}/{field}")
        if pid == "1N8Z" and sequence(original["target"]["fasta"]) != entities["3"]:
            raise ValueError("Reference target sequence mismatch")
        contacts = independent_contacts(block, target, antibody)
        saved = sorted(stored_contacts[pid]["residues"], key=lambda r: (r["chain"], r["seq"]))
        if contacts != saved or len(contacts) != {"1N8Z": 39, "1S78": 56}[pid]:
            raise ValueError(f"Independent contact cross-check failed: {pid}")
        refs[pid] = {"source_sha256": sha(path), "model_number": 1,
                     "coordinate_file": "asymmetric_unit", "numbering": "label",
                     "target_chains": sorted(target), "antibody_chains": sorted(antibody),
                     "cutoff_angstrom": 4.5, "contact_count_both_sides": len(contacts),
                     "contact_residues": contacts}
        sources.append({"path": str(path.relative_to(ROOT)), "sha256": sha(path),
                        "url": f"https://files.rcsb.org/download/{pid}.cif",
                        "entry_url": f"https://www.rcsb.org/structure/{pid}",
                        "original_retrieved_at": locked["retrieved_at"]})

    base = copy.deepcopy(original)
    base["example_id"] = None
    inputs = {"reference": base}
    wrong = copy.deepcopy(base)
    wrong["target"]["fasta"] = ">SYNTHETIC_TARGET_MISMATCH\n" + "A" * 607
    wrong["target"]["sources"] = []
    inputs["wrong-target"] = wrong
    invalid = copy.deepcopy(base)
    invalid["candidates"][1].update(name="SYNTHETIC invalid characters", heavy_chain_fasta=">invalid\nQVQL123", sources=[])
    inputs["invalid-chain"] = invalid
    variant = copy.deepcopy(base)
    c = variant["candidates"][1]
    heavy = sequence(c["heavy_chain_fasta"])
    replacement = "A" if heavy[30] != "A" else "G"
    c.update(candidate_id="synthetic-variant", name="SYNTHETIC pertuzumab variant",
             heavy_chain_fasta=">synthetic_variant_heavy\n" + heavy[:30] + replacement + heavy[31:], sources=[])
    inputs["variant"] = variant
    for name, data in inputs.items():
        save(HERE / "inputs" / f"{name}.json", data)
    save(HERE / "expected-contacts.json", refs)
    save(HERE / "faults.json", {
        "malformed_prediction": {"structures": [{"structure": "data_invalid\n#\n"}], "confidence_scores": [0.99]},
        "unsupported_opinions": [
            {"decision": "reviewable", "reason": "치료 효능이 입증되었고 부작용이 없다."},
            {"decision": "reviewable", "reason": "결합 친화도는 39 nM이다."}],
        "prediction_timeout": {"inject_at": "NvidiaClient.predict_complex", "exception": "logic.nvidia_client.CallFailed",
                               "message": "EVALUATION: prediction timeout", "status": None, "elapsed_s": 0.0},
        "nat_interruption": {"inject_at": "nat_agent.run_candidate", "after": "compare_structure for trastuzumab",
                             "return_reason": "EVALUATION: interrupted after comparison"}})
    files = [HERE / "expected-contacts.json", HERE / "faults.json", HERE / "cases.json",
             HERE / "scorecard-template.json", *sorted((HERE / "inputs").glob("*.json"))]
    save(HERE / "data-lock.json", {
        "dataset_version": "hackathon-v1", "prepared_on": "2026-09-27",
        "base_commit": "7c5cf2dfcaf2e9be5f10f1da7ea57e89fd3a8f48",
        "purpose": "demo regression; not independent biological benchmark",
        "source_fixture": {"path": str(fixture.relative_to(ROOT)), "sha256": sha(fixture)},
        "sources": sources,
        "generation": {"script_sha256": sha(Path(__file__)), "gemmi": gemmi.__version__, "numpy": np.__version__,
                       "contact_oracle": "Gemmi mmCIF parser + NumPy all-pairs distance; no logic imports"},
        "transformations": {"wrong-target": "Keep identifier P04626; replace target with synthetic A x 607; clear target citations",
                            "invalid-chain": "Replace second heavy chain with QVQL123; clear candidate citations",
                            "variant": f"Second candidate heavy-chain deposited position 31: {heavy[30]} -> {replacement}; synthetic, not measured binding"},
        "files": [{"path": str(p.relative_to(HERE)), "sha256": sha(p)} for p in files]})
    print("Prepared 4 inputs, fault fixtures and 2 independently cross-checked contact references (39/56 residues).")


if __name__ == "__main__":
    main()
