"""Direct app notifications are authenticated wake hints, never completion state."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from test_parallel_contract import state_fixture, running_task, memory_mutator, observation, contract, runtime


class DirectNotificationTests(unittest.TestCase):
    def setup_state(self):
        state = state_fixture()
        state["plan"]["notification_mode"] = "direct"
        state["approval"]["plan_hash"] = contract.plan_hash(state["plan"])
        running_task(state)
        return state

    def prepare_message(self, receipt, state, kind="RESULT", payload=None):
        assignment = runtime.envelope(state, "a", "ASSIGN", "main-1", {})
        state["tasks"]["a"]["assignment"] = runtime.publish(receipt, state, assignment)
        message = runtime.envelope(state, "a", kind, "worker-1", payload or {}, assignment["message_id"])
        return message

    def call(self, receipt, state, reference):
        with patch.object(runtime, "load", return_value=state), patch.object(runtime, "assert_workspace"), \
                patch.dict(os.environ, {"CODEX_THREAD_ID": "worker-1"}):
            return runtime.notification(receipt, "a", "worker-1", 1, 1, 1, reference)

    def test_result_generates_direct_main_message_without_mutating_execution_or_acceptance(self):
        state = self.setup_state()
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "docs" / "HANDOFF.md"
            message = self.prepare_message(receipt, state)
            reference = runtime.publish(receipt, state, message)
            before = copy.deepcopy(state)
            files = sorted(Path(directory).rglob("*.json"))
            result = self.call(receipt, state, reference)
            self.assertEqual(result["threadId"], "main-1")
            self.assertIn(message["message_id"], result["prompt"])
            self.assertIn(reference["sha256"], result["prompt"])
            self.assertIn("종료", result["prompt"])
            self.assertEqual(self.call(receipt, state, reference), result)
            self.assertEqual(state, before)
            self.assertIsNone(state["tasks"]["a"]["termination"])
            self.assertIsNone(state["tasks"]["a"]["review"])
            self.assertEqual(sorted(Path(directory).rglob("*.json")), files)

    def test_foreign_or_stale_notification_and_changed_evidence_are_rejected(self):
        state = self.setup_state()
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "HANDOFF.md"
            message = self.prepare_message(receipt, state)
            for field, value in (("run_id", "old-run"), ("task_id", "b"), ("sender", "other-worker"),
                                 ("controller_epoch", 2), ("attempt", 2), ("instruction_revision", 2),
                                 ("reply_to", "another-assignment")):
                bad = {**message, field: value, "message_id": uuid.uuid4().hex}
                reference = runtime.publish(receipt, state, bad)
                with self.subTest(field=field), self.assertRaises(contract.ParallelError):
                    self.call(receipt, state, reference)
            reference = runtime.publish(receipt, state, message)
            Path(reference["path"]).write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(contract.ParallelError, "evidence file changed"):
                self.call(receipt, state, reference)

    def test_only_result_question_blocker_or_stop_checkpoint_wakes_main(self):
        for kind, payload, allowed in (("RESULT", {}, True), ("UPDATE", {"kind": "QUESTION"}, True),
                                       ("UPDATE", {"kind": "BLOCKED"}, True), ("CHECKPOINT", {}, True),
                                       ("UPDATE", {"kind": "CHECKPOINT"}, False), ("ACK", {}, False)):
            state = self.setup_state()
            if kind == "CHECKPOINT": state["phase"] = "STOPPING"
            with tempfile.TemporaryDirectory() as directory:
                receipt = Path(directory) / "HANDOFF.md"
                reference = runtime.publish(receipt, state, self.prepare_message(receipt, state, kind, payload))
                with self.subTest(kind=kind, payload=payload):
                    if allowed:
                        self.assertEqual(self.call(receipt, state, reference)["threadId"], "main-1")
                    else:
                        with self.assertRaisesRegex(contract.ParallelError, "notify only"):
                            self.call(receipt, state, reference)

    def test_existing_plan_and_foreign_caller_do_not_gain_notification_authority(self):
        state = self.setup_state()
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "HANDOFF.md"
            reference = runtime.publish(receipt, state, self.prepare_message(receipt, state))
            with patch.object(runtime, "load", return_value=state), patch.object(runtime, "assert_workspace"), \
                    patch.dict(os.environ, {"CODEX_THREAD_ID": "another-task"}):
                with self.assertRaisesRegex(contract.ParallelError, "actual assigned"):
                    runtime.notification(receipt, "a", "worker-1", 1, 1, 1, reference)
            del state["plan"]["notification_mode"]
            with self.assertRaisesRegex(contract.ParallelError, "not included"):
                self.call(receipt, state, reference)

    def test_execution_packet_only_instructs_direct_notifications_when_approved(self):
        from test_parallel_receipt import planned_receipt
        raw, _ = planned_receipt()
        for mode in (None, "direct", "tools", "user"):
            state = self.setup_state()
            if mode is None:
                del state["plan"]["notification_mode"]
            else:
                state["plan"]["notification_mode"] = mode
            before = copy.deepcopy(state)
            with self.subTest(mode=mode), patch.object(runtime, "load", return_value=state), \
                    patch.object(runtime, "read_bytes", return_value=raw.encode()):
                prompt = runtime.render_assignment("docs/HANDOFF.md", "a")
            packet = json.loads(prompt.split("Packet:\n", 1)[1])
            self.assertEqual("notify" in packet["command_argv"], mode == "direct")
            self.assertEqual("send_message_to_thread" in prompt, mode == "direct")
            self.assertEqual(state, before)

    def test_invalid_workspace_can_report_blocker_without_authorizing_source_work(self):
        for phase in ("ACTIVE", "STOPPING"):
            state = self.setup_state()
            state["phase"] = phase
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                receipt = Path(directory) / "HANDOFF.md"
                self.prepare_message(receipt, state)
                before = copy.deepcopy(state)
                with patch.object(runtime, "load", return_value=state), \
                        patch.object(runtime, "assert_workspace", side_effect=contract.ParallelError("workspace invalid")), \
                        patch.dict(os.environ, {"CODEX_THREAD_ID": "worker-1"}):
                    with self.assertRaises(contract.ParallelError):
                        runtime.worker_guard(receipt, "a", "worker-1", 1, 1, 1)
                    ref = runtime.worker_message(receipt, "a", "worker-1", 1, 1, 1, "UPDATE",
                                                 {"kind": "BLOCKED", "summary": "workspace invalid", "remaining": ["inspect ownership"]})
                    notice = runtime.notification(receipt, "a", "worker-1", 1, 1, 1, ref)
                    self.assertEqual(notice["threadId"], "main-1")
                    self.assertEqual(state, before)
                    with patch.object(runtime, "mutate", memory_mutator(state)):
                        runtime.receive(receipt, 7, "main-1", 1, ref, "worker-1")
                    self.assertEqual(state["tasks"]["a"]["status"], "BLOCKED")
                    self.assertIsNone(state["tasks"]["a"]["termination"])
                    with self.assertRaises(contract.ParallelError):
                        runtime.worker_message(receipt, "a", "worker-1", 1, 1, 1, "RESULT", {})

    def test_blocker_reporting_exception_rejects_retired_or_stale_execution_and_keeps_legacy_guard(self):
        for case in ("worker", "epoch", "attempt", "instruction", "retired", "paused", "legacy"):
            state = self.setup_state()
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                receipt = Path(directory) / "HANDOFF.md"
                self.prepare_message(receipt, state)
                args = [receipt, "a", "worker-1", 1, 1, 1]
                if case in {"worker", "epoch", "attempt", "instruction"}:
                    index = {"worker": 2, "epoch": 3, "attempt": 4, "instruction": 5}[case]
                    args[index] = "other-worker" if case == "worker" else 2
                if case == "retired": state["tasks"]["a"]["termination"] = observation()
                if case == "paused": state["phase"] = "PAUSED"
                if case == "legacy": del state["plan"]["notification_mode"]
                files = sorted(Path(directory).rglob("*.json"))
                with patch.object(runtime, "load", return_value=state), \
                        patch.object(runtime, "assert_workspace", side_effect=contract.ParallelError("workspace invalid")):
                    with self.assertRaises(contract.ParallelError):
                        runtime.worker_message(*args, "UPDATE", {"kind": "BLOCKED", "summary": "blocked", "remaining": []})
                self.assertEqual(sorted(Path(directory).rglob("*.json")), files)


if __name__ == "__main__":
    unittest.main()
