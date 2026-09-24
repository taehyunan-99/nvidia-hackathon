"""Interactions between delivery/index separation and legacy process records."""
from pathlib import Path
import unittest
import os
from unittest.mock import patch
import test_parallel_git_review as git_review
from test_parallel_contract import contract as c, runtime as h, state_fixture, running_task, observation, memory_mutator
import parallel_checks as checks


class ChainReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.safe_run = git_review.ParallelGitReviewTests.safety("-Action", "New")
        cls.base = Path(cls.safe_run["path"])

    @classmethod
    def tearDownClass(cls):
        git_review.ParallelGitReviewTests.safety("-Action", "Remove", "-RunId", cls.safe_run["runId"])

    setUp = git_review.ParallelGitReviewTests.setUp

    def test_reverted_worktree_with_stale_owned_index_completes_without_commit(self):
        path = self.root / "owned/keep.txt"
        baseline = path.read_bytes()
        path.write_bytes(b"old staged attempt\n")
        c.git(self.root, "add", "--", "owned/keep.txt")
        path.write_bytes(baseline)
        state = state_fixture()
        state["plan"]["parent_commit"] = self.head
        planned = state["plan"]["tasks"][0]
        planned.update(worktree=str(self.root), write_paths=["owned"], input_paths=["owned"])
        state["approval"]["plan_hash"] = c.plan_hash(state["plan"])
        task = running_task(state)
        task.update(status="VERIFIED", result={"path": "result.json"}, review={"verdict": "accept"}, termination=observation())
        body = {"remaining": [], "validation_snapshot": c.input_snapshot(self.root, ["owned"]),
                "delivery_files": h.delivery_paths(state, "a"),
                "criteria": {"C1": {"status": "PASS", "checks": ["unit"]}}, "checks": {}}
        report = {"type": "RESULT", "task_id": "a", "attempt": 1, "instruction_revision": 1, "payload": body}
        with patch.object(h, "mutate", memory_mutator(state)), \
                patch.object(h, "assert_workspace", return_value=self.root), \
                patch.object(h, "assert_parent", return_value=self.root), \
                patch.object(h, "assert_checks_stopped"), \
                patch.object(h, "evidence_json", return_value=report), patch.object(h, "validate_checks_evidence"):
            result = h.commit_task(self.root / "docs/HANDOFF.md", 7, "main-1", 1, "a", "fix(repo): 최종 작업본 유지")
            self.assertEqual(result["result"]["status"], "NO_CHANGES")
            h.validate_result(self.root / "docs/HANDOFF.md", state, "a", task["result"])
            h.integrate(self.root / "docs/HANDOFF.md", state["revision"], "main-1", 1, "a")
        self.assertEqual(c.git_text(self.root, "rev-parse", "HEAD"), self.head)
        self.assertEqual(c.dirty_paths(self.root), [])
        self.assertEqual(state["tasks"]["a"]["status"], "INTEGRATED")

    def legacy_record(self, folder, *, task_id=None):
        state = state_fixture()
        state["plan"]["tasks"][0]["worktree"] = self.root.as_posix()
        receipt = self.root / folder / "docs/HANDOFF.md"
        record = {"run_id": "legacy-run", "root": str(self.root).upper() if os.name == "nt" else str(self.root / ".." / self.root.name), "check_id": "unit"}
        if task_id is not None:
            record["task_id"] = task_id
        c.write_artifact(receipt, state, "processes/legacy.json", record)
        return receipt, state

    def test_legacy_windows_root_alias_still_blocks_live_check(self):
        receipt, state = self.legacy_record("alias")
        with patch.object(checks, "manager_call", return_value={"status": "Running"}):
            with self.assertRaisesRegex(c.ParallelError, "live or unknown"):
                checks.assert_checks_stopped(receipt, state, task_id="a")

    def test_legacy_root_alias_does_not_block_a_stopped_check(self):
        receipt, state = self.legacy_record("stopped")
        with patch.object(checks, "manager_call", return_value={"status": "Stopped"}) as manager:
            checks.assert_checks_stopped(receipt, state, task_id="a")
        manager.assert_called_once()

    def test_named_other_worker_check_does_not_block_target(self):
        receipt, state = self.legacy_record("other", task_id="b")
        with patch.object(checks, "manager_call") as manager:
            checks.assert_checks_stopped(receipt, state, task_id="a")
        manager.assert_not_called()
