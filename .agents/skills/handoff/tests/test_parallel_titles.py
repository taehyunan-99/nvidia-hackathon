"""Worker display status follows reviewed work, not self-reported completion."""
import json
import unittest
from unittest.mock import patch
from test_parallel_contract import state_fixture, running_task, observation, runtime
from test_parallel_receipt import planned_receipt


class WorkerTitleTests(unittest.TestCase):
    def setUp(self):
        self.state = state_fixture()
        self.task = running_task(self.state)
        self.state["plan"]["tasks"][0]["goal"] = "검색 API 구현"

    def title(self, scope="projects/example"):
        return runtime.worker_title(self.state, "a", scope)

    def test_working_title_and_repository_root_label(self):
        self.assertEqual(self.title(), "[SUB] Working - projects/example - S1 - 검색 API 구현")
        self.assertEqual(self.title("."), "[SUB] Working - Repository root - S1 - 검색 API 구현")

    def test_number_is_task_order_not_parent_stage(self):
        self.state["plan"]["stage_id"] = "S9"
        self.state["tasks"]["b"].update(attempt=1, instruction_revision=1, status="RUNNING")
        self.assertIn(" - S2 - ", runtime.worker_title(self.state, "b", "."))
        self.assertIn(" - S1 - ", self.title())

    def test_new_worker_attempt_keeps_number_and_adds_r2(self):
        self.task["attempt"] = 2
        self.assertEqual(self.title(), "[SUB] Working - projects/example - S1 R2 - 검색 API 구현")

    def test_same_worker_instruction_revision_does_not_add_attempt(self):
        self.task["instruction_revision"] = 3
        self.assertNotIn(" R", self.title())

    def test_reported_and_terminal_is_not_complete_before_review(self):
        self.task.update(status="REPORTED", termination=observation())
        self.assertIn("[SUB] Working", self.title())

    def test_stopped_unfinished_worker_is_paused(self):
        self.task.update(status="STOPPED", termination=observation())
        self.state["phase"] = "PAUSED"
        self.assertIn("[SUB] Paused", self.title())

    def test_main_accepted_result_is_complete_before_integration(self):
        self.task.update(status="VERIFIED", review={"verdict": "accept"})
        self.assertIn("[SUB] Complete", self.title())
        self.assertEqual(self.task["status"], "VERIFIED")

    def test_accepted_task_stays_complete_during_main_pause(self):
        self.task.update(status="VERIFIED", review={"verdict": "accept"}, termination=observation())
        self.state["phase"] = "PAUSED"
        self.assertIn("[SUB] Complete", self.title())

    def test_missing_acceptance_does_not_claim_complete(self):
        self.task.update(status="VERIFIED", review=None)
        self.assertNotIn("[SUB] Complete", self.title())

    def test_title_is_single_line_with_ascii_separators(self):
        self.state["plan"]["tasks"][0]["goal"] = "검색\nAPI — 구현"
        self.assertEqual(self.title(), "[SUB] Working - projects/example - S1 - 검색 API - 구현")

    def test_prompt_and_title_target_use_actual_worker_identity(self):
        receipt, _ = planned_receipt()
        with patch.object(runtime, "load", return_value=self.state), \
                patch.object(runtime, "read_bytes", return_value=receipt.encode()):
            info = runtime.title_info("docs/HANDOFF.md", "a")
            prompt = runtime.render_assignment("docs/HANDOFF.md", "a")
        self.assertEqual(info["thread_id"], self.task["worker_id"])
        self.assertEqual(info["thread_id"], self.task["worker_thread_id"])
        self.assertEqual(info["host_id"], "local")
        packet = json.loads(prompt.split("Packet:\n", 1)[1])
        self.assertEqual(packet["sub_title"], info["title"])
        self.assertEqual(packet["execution_backend"], "app-threads")
        self.assertEqual(packet["host_id"], "local")
        self.assertEqual(self.task["status"], "RUNNING")

    def test_prompt_declares_scoped_subagent_assistance_without_worker_substitution(self):
        receipt, _ = planned_receipt()
        with patch.object(runtime, "load", return_value=self.state), \
                patch.object(runtime, "read_bytes", return_value=receipt.encode()):
            prompt = runtime.render_assignment("docs/HANDOFF.md", "a")
        packet = json.loads(prompt.split("Packet:\n", 1)[1])
        self.assertEqual(packet["native_subagent_policy"], {
            "role": "internal-assistance-only",
            "selection": "owning-session-autonomous",
            "separate_user_instruction_required": False,
            "allowed_when": ["host-rules-allow", "coordination-benefit-exceeds-cost"],
            "decision_signals": ["task-size", "independent-subtasks", "verification-value"],
            "owning_session_responsibilities": ["scope", "validation", "termination", "app-protocol-reporting"],
            "prohibited_roles": ["handoff-worker", "worktree-owner", "receipt-authority", "direct-main-reporter"],
        })
        self.assertNotIn("spawn_agent 호출을 하지 않습니다", prompt)


if __name__ == "__main__":
    unittest.main()
