"""A past worker or observation cannot be reused to replace a checkpoint."""
from unittest import TestCase
from unittest.mock import patch
from test_parallel_contract import state_fixture, running_task, observation, memory_mutator, runtime, contract


class IdentityReviewTests(TestCase):
    def test_third_attempt_cannot_reuse_first_attempt_worker(self):
        state = state_fixture()
        task = running_task(state)
        task.update(attempt=3, status="DISPATCHING", worker_id=None, retired_workers=["first-worker", "second-worker"])
        registration = {"worker_id": "first-worker", "run_id": state["run_id"], "task_id": "a", "attempt": 3,
                        "controller_epoch": 1, "assignment_sha256": task["assignment"]["sha256"]}
        with patch.object(runtime, "mutate", memory_mutator(state)), \
                patch.object(runtime, "evidence_json", side_effect=[registration, {"payload": {"resume": {"previous_worker": "second-worker"}}}]), \
                patch.object(runtime, "assert_workspace") as workspace:
            with self.assertRaisesRegex(contract.ParallelError, "retired"):
                runtime.bind("HANDOFF.md", 7, "main-1", 1, "a", {}, "first-worker", "local")
            workspace.assert_not_called()

    def test_repeated_terminal_observation_does_not_resnapshot_workspace(self):
        state = state_fixture()
        task = running_task(state)
        task.update(status="STOPPED", termination=observation())
        before = task["workspace_snapshot"].copy()
        with patch.object(runtime, "mutate", memory_mutator(state)), \
                patch.object(runtime, "workspace_snapshot") as snapshot:
            result = runtime.observe("HANDOFF.md", 7, "main-1", 1, "a", observation())
            snapshot.assert_not_called()
        self.assertEqual(result["result"]["status"], "ALREADY_OBSERVED")
        self.assertEqual(state["tasks"]["a"]["workspace_snapshot"], before)

    def test_observe_cannot_refresh_a_paused_checkpoint(self):
        state = state_fixture("PAUSED")
        task = running_task(state)
        task.update(status="STOPPED", termination=observation())
        with patch.object(runtime, "mutate", memory_mutator(state)), \
                patch.object(runtime, "workspace_snapshot") as snapshot:
            with self.assertRaisesRegex(contract.ParallelError, "checkpoint"):
                runtime.observe("HANDOFF.md", 7, "main-1", 1, "a", observation())
            snapshot.assert_not_called()
