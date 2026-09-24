"""Lost check-launch replies must not disappear from the stop barrier."""
import subprocess
from pathlib import Path
import unittest
from unittest.mock import patch
import test_parallel_git_review as git_review
from test_parallel_contract import state_fixture, runtime, memory_mutator, running_task, observation
import parallel_checks as checks
from parallel_contract import ParallelError


class CheckLaunchReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.safe_run = git_review.ParallelGitReviewTests.safety("-Action", "New")
        cls.base = Path(cls.safe_run["path"])

    @classmethod
    def tearDownClass(cls):
        git_review.ParallelGitReviewTests.safety("-Action", "Remove", "-RunId", cls.safe_run["runId"])

    def test_lost_start_reply_blocks_pause_until_explicit_resolution(self):
        receipt = self.base / "lost/docs/HANDOFF.md"
        state = state_fixture()
        check = {"id": "probe", "argv": ["probe.exe"], "timeout_seconds": 10}
        with patch.object(checks, "manager_call", side_effect=subprocess.TimeoutExpired("Start", 60)):
            with self.assertRaises(subprocess.TimeoutExpired):
                checks.run_command(receipt, state, Path("worker"), check, Path("worker"))
        with self.assertRaisesRegex(ParallelError, "unresolved check start"):
            checks.assert_checks_stopped(receipt, state)
        intents = list((checks.artifact_root(receipt, state) / "processes/intents").glob("*.json"))
        self.assertEqual(len(intents), 1)
        checks.resolve_start(receipt, state, intents[0].stem, None,
                             "Fixture has no actual process; simulated Start never launched")
        checks.assert_checks_stopped(receipt, state)

    def test_retry_checks_actual_process_records_before_reusing_worker(self):
        state = state_fixture()
        task = running_task(state)
        task.update(status="STOPPED", termination=observation())
        with patch.object(runtime, "mutate", memory_mutator(state)), \
                patch.object(runtime, "assert_checks_stopped", side_effect=ParallelError("check still running")), \
                patch.object(runtime, "assert_workspace") as workspace, \
                patch.object(runtime, "workspace_snapshot", return_value={"id": "snapshot"}), \
                patch.object(runtime, "publish", return_value={"path": "assignment.json"}), \
                patch.object(runtime, "evidence_json", return_value={"controller_epoch": 1}):
            with self.assertRaisesRegex(ParallelError, "check still running"):
                runtime.retry("HANDOFF.md", 7, "main-1", 1, "a")
            workspace.assert_not_called()

    def test_completed_check_preserves_stdout_exit_and_intent_binding(self):
        receipt = self.base / "completed/docs/HANDOFF.md"
        self.base.joinpath("stdout.txt").write_text("ok")
        self.base.joinpath("stderr.txt").write_text("")
        response = {"runId": "fixture-run", "status": "Completed", "state": {"targetExitCode": 0},
                    "stdoutPath": str(self.base / "stdout.txt"), "stderrPath": str(self.base / "stderr.txt")}
        state = state_fixture()
        with patch.object(checks, "manager_call", return_value=response) as manager:
            result = checks.run_command(receipt, state, Path("worker"), {"id": "test", "argv": ["p"], "timeout_seconds": 10}, Path("worker"), task_id="a")
            checks.assert_checks_stopped(receipt, state, task_id="a")
        self.assertEqual(result, (0, b"ok", b"", "fixture-run"))
        self.assertTrue(any(call.args[1] == "Stop" for call in manager.call_args_list))
