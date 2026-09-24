"""Internal merge accepts the same affected-project footer syntax as its hook."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from test_parallel_contract import runtime, contract, state_fixture, running_task, observation, memory_mutator


class FooterReviewTests(TestCase):
    def test_merge_preserves_hook_valid_monorepo_footers(self):
        for footer in ("Affected-projects: alpha, beta", "Affected-projects:alpha,beta", "Affected-projects:\talpha, beta"):
            with self.subTest(footer=footer):
                state = state_fixture()
                state["plan"]["parent_branch"] = "feature/monorepo/main"
                for task_spec in state["plan"]["tasks"]:
                    task_spec["branch"] = task_spec["branch"].replace("/repo/", "/monorepo/")
                state["approval"]["plan_hash"] = contract.plan_hash(state["plan"])
                task = running_task(state)
                task.update(status="VERIFIED", result={"path": "result"}, review={"verdict": "accept"},
                            result_commit="b" * 40, termination=observation())
                merge_messages = []
                def git(_root, *args, **_kwargs):
                    if args[0] == "merge":
                        merge_messages.append(args[args.index("-m") + 1])
                    return SimpleNamespace(returncode=1 if args[0] == "merge-base" else 0,
                                           stdout=b"src/a.py\0" if args[0] == "diff" else b"", stderr=b"")
                def git_text(_root, *args):
                    return "feat(monorepo): 통합 검증\n\n" + footer if args[0] == "show" else "c" * 40
                with patch.object(runtime, "mutate", memory_mutator(state)), \
                        patch.object(runtime, "assert_parent", return_value=Path("parent")), \
                        patch.object(runtime, "assert_checks_stopped"), patch.object(runtime, "validate_result"), \
                        patch.object(runtime, "git", side_effect=git), patch.object(runtime, "git_text", side_effect=git_text):
                    runtime.integrate("HANDOFF.md", 7, "main-1", 1, "a")
                self.assertEqual(state["tasks"]["a"]["status"], "INTEGRATED")
                self.assertEqual(merge_messages, ["chore(handoff): 병렬 작업 a 결과 통합"])
