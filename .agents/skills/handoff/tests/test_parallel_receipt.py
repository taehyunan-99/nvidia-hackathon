"""v8 preserves core receipt validation while checking the parallel block."""
import copy
import unittest
from test_parallel_contract import state_fixture, contract
from test_render_handoff import current_v7_handoff, RENDERER


def planned_receipt():
    state = state_fixture("PLANNED")
    state["plan"]["goal"] = "Renderer behavior has direct evidence."
    state["approval"] = None
    text = current_v7_handoff().replace("Use Ultra: no", "Use Ultra: yes")
    text = text.replace("### Next-stage routing", "- Ultra evidence: E1\n\n### Next-stage routing")
    text = text.replace("Architecture direction was read directly.",
                        "Ultra independence: two separate scopes with independent verification.")
    return contract.embed(text, state).replace("Format: handoff-v7", "Format: handoff-v8"), state


class ParallelReceiptTests(unittest.TestCase):
    def test_v8_plan_round_trip_keeps_core_checklist(self):
        text, state = planned_receipt()
        model = RENDERER.parse_handoff(text)
        self.assertEqual(model["parallel"], state)
        self.assertIsNotNone(model["checklist"])
        self.assertNotIn("controller_epoch", "\n".join(model["sections"]["State verification"]))

    def test_v7_cannot_hide_runtime_state(self):
        text, _ = planned_receipt()
        with self.assertRaises(RENDERER.HandoffError):
            RENDERER.parse_handoff(text.replace("Format: handoff-v8", "Format: handoff-v7"))

    def test_v8_requires_exactly_one_block(self):
        text, _ = planned_receipt()
        with self.assertRaises(RENDERER.HandoffError):
            RENDERER.parse_handoff(contract.without_block(text))

    def test_live_run_cannot_claim_ready(self):
        text, state = planned_receipt()
        state["phase"] = "ACTIVE"
        state["approval"] = {"plan_hash": contract.plan_hash(state["plan"]), "evidence": "approved", "internal_git": True}
        with self.assertRaises(RENDERER.HandoffError):
            RENDERER.parse_handoff(contract.embed(text, state))
        self.assertEqual(RENDERER.parse_handoff(contract.embed(text, state).replace("Receipt: READY", "Receipt: STALE"))["parallel"]["phase"], "ACTIVE")

    def test_selected_stage_must_match_plan(self):
        text, state = planned_receipt()
        state["plan"]["goal"] = "Different task"
        with self.assertRaises(RENDERER.HandoffError):
            RENDERER.parse_handoff(contract.embed(text, state))

    def test_runtime_block_cannot_move_outside_state_verification(self):
        text, _ = planned_receipt()
        block = contract.BLOCK.search(text).group(0)
        text = contract.without_block(text).replace("## Risks and open questions", "## Risks and open questions\n\n" + block)
        with self.assertRaises(RENDERER.HandoffError):
            RENDERER.parse_handoff(text)
