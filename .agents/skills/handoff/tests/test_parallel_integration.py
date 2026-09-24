"""Real guarded worktrees, pause/new controller, inherited files and Git recovery."""
from pathlib import Path
import json
import os
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import parallel_contract as c
import parallel_handoff as h
from test_render_handoff import current_v7_handoff


class ParallelIntegrationTests(unittest.TestCase):
    def test_real_pause_resume_review_commit_merge_recovery(self):
        temporary = tempfile.TemporaryDirectory(prefix="handoff-integration-")
        base=Path(temporary.name)
        try:
            remote, primary = base / "remote.git", base / "primary"
            remote.mkdir(); primary.mkdir()
            c.git(base, "init", "--bare", "--initial-branch=main", str(remote))
            c.git(base, "init", "--initial-branch=main", str(primary))
            c.git(primary, "config", "user.email", "fixture@example.invalid")
            c.git(primary, "config", "user.name", "Handoff Fixture")
            (primary / "src").mkdir()
            for name in ("a", "b"):
                (primary / f"src/{name}.txt").write_text("base-" + name)
            (primary / "src/deletions").mkdir()
            (primary / "src/deletions/keep.txt").write_text("kept")
            (primary / "src/deletions/remove.txt").write_text("delete")
            hooks=base / "empty-hooks";hooks.mkdir()
            c.git(primary,"config","core.hooksPath",str(hooks))
            c.git(primary,"add","--","src")
            c.git(primary, "commit", "-m", "chore(repo): 검증 기반")
            c.git(primary, "remote", "add", "origin", str(remote))
            c.git(primary, "push", "-u", "origin", "main")
            parent=base / "parent"
            c.git(primary,"worktree","add","-b","feature/repo/parent",str(parent),"HEAD")
            pinned=c.git_text(parent,"rev-parse","HEAD")
            children={}
            from worktree_guard import register as register_workspace
            for name in ("a","b"):
                child=base / ("worker-"+name)
                c.git(primary,"worktree","add","--detach",str(child),pinned)
                register_workspace(parent,child,"feature/repo/worker-"+name,"feature/repo/parent",pinned,
                                   "integration-probe","fixture-"+name,"fixture-host")
                children[name]=child
            receipt = parent / "docs/HANDOFF.md"
            receipt.parent.mkdir()
            text = current_v7_handoff().replace("Use Ultra: no", "Use Ultra: yes")
            text = text.replace("### Next-stage routing", "- Ultra evidence: E1\n\n### Next-stage routing")
            text = text.replace("Architecture direction was read directly.",
                                "Ultra independence: two work items have non-overlapping ownership and separate verification.")
            text = text.replace("abc1234", pinned).replace("Branch or worktree: main", "Branch or worktree: feature/repo/parent")
            receipt.write_text(text, encoding="utf-8")
            checks = {}
            tasks = []
            for name in ("a", "b"):
                paths = [f"src/{name}.txt"] + (["src/inherited.txt"] if name == "b" else [])
                if name == "a":
                    paths.append("src/deletions")
                command = f"from pathlib import Path; assert Path('src/{name}.txt').read_text() == 'done-{name}'"
                if name == "b":
                    command += "; assert Path('src/inherited.txt').read_text() == 'kept'"
                else:
                    command += "; assert not Path('src/deletions/remove.txt').exists()"
                checks[name] = {"id": "unit", "kind": "command", "argv": [sys.executable, "-c", command],
                                "cwd": ".", "timeout_seconds": 60}
                tasks.append({"id": name, "goal": "Implement " + name, "context": ["Preserve previous files"],
                              "write_paths": paths, "input_paths": paths, "worktree": str(children[name]),
                              "branch": "feature/repo/worker-" + name, "model": "gpt-5.6-luna", "reasoning": "medium",
                              "criteria": [{"id": "C1", "description": "Expected output", "checks": ["unit"]}],
                              "checks": [checks[name]], "depends_on": []})
            combined = "from pathlib import Path; assert Path('src/a.txt').read_text()=='done-a'; assert Path('src/b.txt').read_text()=='done-b'; assert Path('src/inherited.txt').read_text()=='kept'"
            plan = {"mode": "auto", "execution_backend": "app-threads", "max_parallel": 2, "stage_id": "S1", "goal": "Renderer behavior has direct evidence.",
                    "parent_worktree": str(parent), "parent_branch": "feature/repo/parent", "parent_commit": pinned,
                    "tasks": tasks, "rework_limit": 2,
                    "integration_checks": [{"id": "all", "kind": "command", "argv": [sys.executable, "-c", combined],
                                             "cwd": ".", "timeout_seconds": 60}]}
            h.prepare(receipt, plan)
            state = h.load(receipt)
            h.approve(receipt, state["revision"], "explicit fixture authorization", True)
            h.claim(receipt, h.load(receipt)["revision"], "main-one")

            def main(fn, *args):
                state = h.load(receipt)
                return fn(receipt, state["revision"], state["controller_id"], state["controller_epoch"], *args)

            def worker_args(tid):
                state = h.load(receipt); task = state["tasks"][tid]
                return receipt, tid, task["worker_id"], state["controller_epoch"], task["attempt"], task["instruction_revision"]

            def register(tid, worker):
                main(h.dispatch, tid)
                task = h.load(receipt)["tasks"][tid]
                with patch.dict(os.environ, {"CODEX_THREAD_ID": worker}):
                    reference = h.hello(receipt, tid, task["assignment"]["path"])
                main(h.bind, tid, reference, worker, "local")
                self.assertIn("Packet:", h.render_assignment(receipt, tid))
                ack = h.worker_message(*worker_args(tid), "ACK", {"understanding": "owned task", "first_action": "inspect"})
                main(h.receive, ack, worker)

            def terminal(tid):
                state = h.load(receipt); task = state["tasks"][tid]
                observation = {"worker_id": task["worker_id"], "attempt": task["attempt"],
                               "instruction_revision": task["instruction_revision"], "controller_epoch": state["controller_epoch"],
                               "turn_id": f"fixture-{tid}-{task['attempt']}", "status": "completed",
                               "tool": "wait_threads", "observed_at": c.stamp(), "reference": "simulated app terminal observation"}
                main(h.observe, tid, observation)

            notes = {"summary": "Outcome verified", "decisions": ["Preserve inherited output"],
                     "limitations": [], "remaining": [], "processes": []}
            register("a", "worker-a1"); register("b", "worker-b1")
            (children["a"] / "src/a.txt").write_text("done-a")
            (children["a"] / "src/deletions/remove.txt").unlink()
            result_checks = h.run_checks(*worker_args("a"))
            (children["a"] / "src/a.txt").write_text("stale")
            with self.assertRaises(c.ParallelError):
                h.worker_message(*worker_args("a"), "RESULT", notes, result_checks)
            (children["a"] / "src/a.txt").write_text("done-a")
            report_a = h.worker_message(*worker_args("a"), "RESULT", notes, result_checks)
            main(h.receive, report_a, "worker-a1")
            main(h.review, "a", "accept", "Actual output and passing command inspected")
            terminal("a")
            (children["b"] / "src/b.txt").write_text("partial")
            inherited = children["b"] / "src/inherited.txt"
            inherited.write_text("kept")
            c.git(children["b"], "add", "--", "src/inherited.txt")
            before_pause = c.workspace_snapshot(children["b"], tasks[1]["write_paths"])
            main(h.request_stop)
            with self.assertRaises(c.ParallelError):
                main(h.pause)
            checkpoint = h.worker_message(*worker_args("b"), "CHECKPOINT", {**notes, "remaining": ["Finish b output"]})
            main(h.receive, checkpoint, "worker-b1")
            old_worker = worker_args("b")
            terminal("b")
            main(h.checkpoint_main, "b", {**notes, "summary": "Main inspected retained files after termination",
                                         "remaining": ["Finish b output"]})
            main(h.pause)
            self.assertEqual(c.workspace_snapshot(children["b"], tasks[1]["write_paths"]), before_pause)
            h.claim(receipt, h.load(receipt)["revision"], "main-two")
            with self.assertRaises(c.ParallelError):
                main(h.retry, "b")
            with self.assertRaises(c.ParallelError):
                h.worker_guard(*old_worker)
            self.assertEqual(h.load(receipt)["tasks"]["a"]["status"], "VERIFIED")
            register("b", "worker-b2")
            self.assertEqual(inherited.read_text(), "kept")
            (children["b"] / "src/b.txt").write_text("done-b")
            result_checks = h.run_checks(*worker_args("b"))
            report_b = h.worker_message(*worker_args("b"), "RESULT", notes, result_checks)
            body = c.evidence_json(receipt, h.load(receipt), report_b)["payload"]
            self.assertNotIn("src/inherited.txt", body["edited_this_attempt"])
            self.assertIn("src/inherited.txt", body["delivery_files"])
            main(h.receive, report_b, "worker-b2")
            self.assertEqual(main(h.receive, report_b, "worker-b2")["result"]["status"], "ALREADY_RECEIVED")
            main(h.review, "b", "accept", "Full manifest including inherited file inspected")
            terminal("b")
            with patch.object(h, "atomic_write", side_effect=c.ParallelError("simulated interrupted receipt write")):
                with self.assertRaises(c.ParallelError):
                    main(h.commit_task, "a", "feat(repo): 첫 결과 검증")
            commit_a = c.git_text(children["a"], "rev-parse", "HEAD")
            self.assertIsNone(h.load(receipt)["tasks"]["a"]["result_commit"])
            main(h.recover_commit, "a", commit_a, "Verified actual commit after interrupted checkpoint")
            main(h.commit_task, "b", "feat(repo): 재개 결과 검증")
            with patch.object(h, "atomic_write", side_effect=c.ParallelError("simulated interrupted integration checkpoint")):
                with self.assertRaises(c.ParallelError):
                    main(h.integrate, "a")
            parent_after_merge = c.git_text(parent, "rev-parse", "HEAD")
            main(h.integrate, "a")
            self.assertEqual(c.git_text(parent, "rev-parse", "HEAD"), parent_after_merge)
            main(h.integrate, "b")
            main(h.finish)
            final = h.load(receipt)
            self.assertEqual(final["phase"], "COMPLETE")
            self.assertEqual((parent / "src/inherited.txt").read_text(), "kept")
            self.assertFalse((parent / "src/deletions/remove.txt").exists())
            self.assertTrue(c.git_text(parent, "log", "-1", "--format=%s").startswith("chore(handoff):"))
            self.assertEqual(c.git_text(primary, "rev-parse", "HEAD"), pinned)
            repeated = h.claim(receipt, final["revision"], "main-three")
            self.assertEqual(repeated["result"]["status"], "NO_REMAINING_WORK")
            self.assertEqual(h.load(receipt), final)
            renderer = c.load_renderer()
            model = renderer.parse_handoff(receipt.read_text(encoding="utf-8"))
            self.assertEqual(model["parallel"]["phase"], "COMPLETE")
            self.assertIn("병렬 작업", renderer.render_html(model, "0" * 64))
        finally:
            temporary.cleanup()
