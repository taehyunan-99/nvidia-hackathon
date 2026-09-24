"""Git boundary regressions using repositories owned by the safety harness."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import uuid
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import parallel_contract as c
import parallel_handoff as h


class ParallelGitReviewTests(unittest.TestCase):
    _temporary_runs = {}
    @classmethod
    def safety(cls, *args):
        values=dict(zip(args[::2],args[1::2]))
        if values["-Action"] == "New":
            run=uuid.uuid4().hex
            temp=tempfile.TemporaryDirectory(prefix="handoff-test-")
            cls._temporary_runs[run]=temp
            return {"runId":run,"path":temp.name}
        cls._temporary_runs.pop(values["-RunId"]).cleanup()
        return {"removed":True}

    @classmethod
    def setUpClass(cls):
        cls.safe_run = cls.safety("-Action", "New")
        cls.base = Path(cls.safe_run["path"])

    @classmethod
    def tearDownClass(cls):
        cls.safety("-Action", "Remove", "-RunId", cls.safe_run["runId"])

    def setUp(self):
        self.root = self.base / self._testMethodName
        self.root.mkdir()
        c.git(self.root, "init", "--initial-branch=feature/repo/fixture")
        c.git(self.root, "config", "user.email", "fixture@example.invalid")
        c.git(self.root, "config", "user.name", "Handoff Git Fixture")
        hooks = self.root / "empty-hooks"
        hooks.mkdir()
        c.git(self.root, "config", "core.hooksPath", str(hooks))
        c.git(self.root, "config", "diff.renames", "true")
        self.files = ["src/keep.txt", "src/remove.txt", "other/old.txt", "owned/keep.txt"]
        for name in self.files:
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text("original " + name + "\n", encoding="utf-8")
        c.git(self.root, "add", "--", *self.files)
        c.git(self.root, "commit", "-m", "chore(repo): 검증 기반")
        self.head = c.git_text(self.root, "rev-parse", "HEAD")

    def writer_state(self):
        return {"plan": {"parent_commit": self.head, "tasks": [
            {"id": "a", "worktree": str(self.root), "write_paths": ["owned"]}]},
            "tasks": {"a": {}}}

    def test_directory_snapshot_survives_staging_a_deletion(self):
        (self.root / "src/remove.txt").unlink()
        before = c.input_snapshot(self.root, ["src"])
        c.git(self.root, "add", "--", "src/remove.txt")
        self.assertEqual(c.input_snapshot(self.root, ["src"]), before,
                         "Staging must not change evidence for unchanged source bytes and deletions")

    def test_staged_rename_reports_both_changed_paths(self):
        c.git(self.root, "mv", "other/old.txt", "owned/new.txt")
        self.assertEqual(c.dirty_paths(self.root), ["other/old.txt", "owned/new.txt"])

    def test_staged_rename_cannot_delete_an_unowned_source(self):
        c.git(self.root, "mv", "other/old.txt", "owned/new.txt")
        with self.assertRaisesRegex(c.ParallelError, "out-of-scope"):
            h.delivery_paths(self.writer_state(), "a")

    def test_committed_rename_cannot_hide_an_unowned_source(self):
        c.git(self.root, "mv", "other/old.txt", "owned/new.txt")
        c.git(self.root, "commit", "-m", "chore(repo): 이동 검증")
        with self.assertRaisesRegex(c.ParallelError, "out-of-scope"):
            h.delivery_paths(self.writer_state(), "a")

    def test_index_change_is_visible_when_worktree_matches_head(self):
        path = self.root / "other/old.txt"
        original = path.read_bytes()
        path.write_bytes(b"staged unrelated change\n")
        c.git(self.root, "add", "--", "other/old.txt")
        path.write_bytes(original)
        self.assertIn("other/old.txt", c.dirty_paths(self.root))
        state = {"plan": {"parent_worktree": str(self.root),
                          "parent_branch": "feature/repo/fixture", "parent_commit": self.head}}
        with self.assertRaisesRegex(c.ParallelError, "non-handoff changes"):
            h.assert_parent(self.root / "docs/HANDOFF.md", state)


class ParallelCommitMessageReviewTests(unittest.TestCase):
    def test_monorepo_commit_accepts_required_affected_projects_footer(self):
        message = "feat(monorepo): 공통 계약 변경\n\nAffected-projects: alpha, beta"
        # Isolate message validation; no receipt or Git mutation should occur here.
        with patch.object(h, "mutate", return_value={"accepted": True}) as mutation:
            result = h.commit_task(Path("unused-HANDOFF.md"), 1, "main", 1, "a", message)
        self.assertEqual(result, {"accepted": True})
        mutation.assert_called_once()


if __name__ == "__main__":
    unittest.main()
