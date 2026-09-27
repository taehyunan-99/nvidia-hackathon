"""Offline review probes; records observed behavior, not biological ground truth.

Run from the repository root with `uv run --locked python <this file>`.
No NVIDIA client or NAT runner is invoked; temporary outputs are discarded.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = next(p for p in Path(__file__).resolve().parents if (p / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT))

from logic.agent_session import CandidateSession, CandidateTools
from logic.flow import Flow
from logic.tests.test_flow import TRASTUZUMAB, candidate, entity_sequence, make_request
from logic.tests.test_flow_decisions import ScriptedClient, _filler


def setup(path, *, matched=True, target=None):
    heavy = entity_sequence(TRASTUZUMAB, "heavy") if matched else "A" * 100
    light = entity_sequence(TRASTUZUMAB, "light") if matched else "G" * 100
    cand = candidate("audit-candidate", "Audit", heavy, light)
    request = make_request([cand, _filler()], path, target_fasta=(
        target if target is not None else entity_sequence(TRASTUZUMAB, "target")))
    flow = Flow(request, client=ScriptedClient())
    session = CandidateSession(cand)
    tools = CandidateTools(flow, session)
    return flow, session, tools


def main():
    findings = {}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        flow, session, tools = setup(path, target="A" * 607)
        findings["target_mismatch"] = {"input_check": tools.check_input()}
        tools.lookup_public_structure()
        findings["target_mismatch"].update(
            complete=session.match.complete,
            selected=tools.use_experimental_structure("공개 구조를 사용한다."))

        for key, reason in (
            ("unsupported_claim", "치료 효능이 입증되었고 부작용이 없다."),
            ("wrong_unit", "결합 친화도는 39 nM이다."),
        ):
            flow, session, tools = setup(path)
            tools.check_input()
            tools.lookup_public_structure()
            tools.use_experimental_structure("공개 구조를 사용한다.")
            tools.compare_structure()
            findings[key] = {"response": tools.submit_opinion("reviewable", reason),
                             "stored_reason": flow.opinions[-1]["reason"]}

        for key, matched in (("malformed_prediction", False), ("prediction_with_public_match", True)):
            flow, session, tools = setup(path, matched=matched)
            tools.check_input()
            tools.lookup_public_structure()
            tools.predict_structure("새로 예측해 확인한다.")
            tools.compare_structure()
            tools.submit_opinion("needs_confirmation", "추가 확인이 필요하다.")
            contact = next(e for e in flow.evidence if e["topic"] == "interface_contact_residues")
            findings[key] = {"terminal": session.terminal,
                             "structure_kind": flow.structures[0]["kind"],
                             "contact_state": contact["measurement_state"],
                             "contact_value": contact["value"],
                             "contact_sources": contact["sources"]}

    source = ROOT / "docs/topics/her2/assets/goldset/score_epitope.py"
    spec = importlib.util.spec_from_file_location("review_score_epitope", source)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    mapped = scorer.remap("ACD", "AED", {1, 2, 3})
    findings["unmapped_contact_dropped"] = {
        "input_positions": [1, 2, 3], "mapped_positions": sorted(mapped),
        "score_after_drop": scorer.f1(mapped, {1, 3}),
    }
    print(json.dumps({
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "mode": "offline_direct_tools_with_scripted_client",
        "findings": findings,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
