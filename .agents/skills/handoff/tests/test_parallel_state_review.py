"""Completion regressions using production transitions and in-memory evidence."""
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from test_parallel_contract import (
    contract, runtime, memory_mutator, observation, running_task, state_fixture,
)


class CompletionRegressionTests(unittest.TestCase):
    def test_finish_rejects_source_changed_outside_inputs_by_passing_check(self):
        state = state_fixture()
        for tid, task in state["tasks"].items():
            task.update(attempt=1, instruction_revision=1, worker_id="worker-" + tid, worker_thread_id="worker-" + tid, worker_host_id="local",
                        status="INTEGRATED", result={"path": "result-" + tid},
                        review={"verdict": "accept"}, termination=observation("worker-" + tid),
                        result_commit="b" * 40)
        root = Path(state["plan"]["parent_worktree"])
        receipt = root / "docs/HANDOFF.md"
        changed = []
        evidence = {}
        reference = {"path": "checks.json", "sha256": "checks-sha"}
        snapshot = {"id": "unchanged-declared-inputs", "files": {}}

        def command(*_args, **_kwargs):
            changed.append("src/unowned.py")
            return 0, b"passed", b"", "check-run-1"

        def write_artifact(_receipt, _state, _filename, payload):
            evidence.update(payload)
            return reference

        def git_text(_root, *args):
            if args[0] == "branch":
                return state["plan"]["parent_branch"]
            return "" if args[0] == "diff" else "b" * 40

        with patch.object(runtime, "mutate", memory_mutator(state)), \
                patch.object(runtime, "assert_checks_stopped"), \
                patch.object(runtime, "repository", return_value=root), \
                patch.object(runtime, "git_text", side_effect=git_text), \
                patch.object(runtime, "git", return_value=Mock(returncode=0)), \
                patch.object(runtime, "dirty_paths", side_effect=lambda _root: list(changed)), \
                patch.object(runtime, "input_snapshot", return_value=snapshot), \
                patch.object(runtime, "run_command", side_effect=command), \
                patch.object(runtime, "write_artifact", side_effect=write_artifact), \
                patch.object(runtime, "evidence_json", return_value=evidence):
            with self.assertRaisesRegex(contract.ParallelError, "non-handoff changes"):
                runtime.finish(receipt, 7, "main-1", 1)

        self.assertEqual(evidence["checks"]["unit"]["status"], "PASS")
        self.assertEqual(changed, ["src/unowned.py"])
        self.assertEqual(state["phase"], "ACTIVE")
        self.assertEqual(state["revision"], 7)
        self.assertIsNone(state["integration"])

    def test_verified_writer_without_changes_can_record_and_integrate_baseline(self):
        state = state_fixture()
        task = running_task(state)
        task.update(status="VERIFIED", result={"path": "result.json"},
                    review={"verdict": "accept"}, termination=observation())
        baseline = state["plan"]["parent_commit"]
        root = Path(state["plan"]["parent_worktree"])
        with patch.object(runtime, "mutate", memory_mutator(state)), \
                patch.object(runtime, "assert_checks_stopped"), \
                patch.object(runtime, "validate_result"), \
                patch.object(runtime, "assert_parent", return_value=root), \
                patch.object(runtime, "dirty_paths", return_value=[]), \
                patch.object(runtime, "git_text", return_value=baseline), \
                patch.object(runtime, "workspace_snapshot", return_value={"id": "clean-baseline"}), \
                patch.object(runtime, "git", return_value=Mock(stdout=b"", returncode=0)) as git:
            recorded = runtime.commit_task("HANDOFF.md", 7, "main-1", 1, "a", "fix(repo): 기존 동작 검증")
            self.assertEqual(recorded["result"]["status"], "NO_CHANGES")
            self.assertEqual(state["tasks"]["a"]["result_commit"], baseline)
            self.assertEqual(state["tasks"]["a"]["status"], "VERIFIED")

            revision = state["revision"]
            repeated = runtime.commit_task("HANDOFF.md", revision, "main-1", 1, "a", "fix(repo): 기존 동작 검증")
            self.assertEqual(repeated["result"]["status"], "ALREADY_COMMITTED")
            self.assertEqual(state["revision"], revision)

            runtime.integrate("HANDOFF.md", revision, "main-1", 1, "a")
            self.assertEqual(state["tasks"]["a"]["status"], "INTEGRATED")
            self.assertTrue(all(call.args[1] in {"diff", "ls-files", "merge-base"} for call in git.call_args_list))


if __name__ == "__main__":
    unittest.main()
