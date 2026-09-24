"""Contract and controller invariants; no real Git/process/app mutations."""
from contextlib import contextmanager
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import parallel_contract as contract
import parallel_handoff as runtime


def plan_fixture():
    root = Path(__file__).resolve().parents[1]
    check = {"id": "unit", "kind": "command", "argv": ["fixture-command"],
             "cwd": ".", "timeout_seconds": 10}
    tasks = []
    for name in ("a", "b"):
        tasks.append({"id": name, "goal": "Implement " + name, "context": ["Independent source files"],
                      "write_paths": ["src/" + name + ".py"], "input_paths": ["src/" + name + ".py"],
                      "worktree": str(root / ("worker-" + name)), "branch": "feature/repo/worker-" + name,
                      "model": "gpt-5.6-luna", "reasoning": "medium",
                      "criteria": [{"id": "C1", "description": "Behavior passes", "checks": ["unit"]}],
                      "checks": [copy.deepcopy(check)], "depends_on": []})
    return {"mode": "auto", "execution_backend": "app-threads", "max_parallel": 2, "stage_id": "S1", "goal": "Implement independent components",
            "parent_worktree": str(root / "main"), "parent_branch": "feature/repo/main",
            "parent_commit": "a" * 40, "tasks": tasks, "integration_checks": [check], "rework_limit": 2}


def state_fixture(phase="ACTIVE"):
    plan = plan_fixture()
    empty = {"attempt": 0, "instruction_revision": 0, "status": "PLANNED", "worker_id": None,
             "worker_thread_id": None, "termination": None, "processes": {}, "workspace_snapshot": None,
             "result": None, "review": None, "checkpoint": None, "result_commit": None,
             "assignment": None, "reworks": 0}
    return {"schema": contract.SCHEMA, "run_id": "run1", "phase": phase, "revision": 7,
            "controller_epoch": 1, "controller_id": "main-1", "plan": plan,
            "approval": {"plan_hash": contract.plan_hash(plan), "evidence": "user approved plan", "internal_git": True},
            "tasks": {x: copy.deepcopy(empty) for x in ("a", "b")}, "messages": {}, "integration": None,
            "parent_inputs": {"a": {"id": "base-a", "files": {}}, "b": {"id": "base-b", "files": {}}}}


def observation(worker="worker-1"):
    return {"worker_id": worker, "turn_id": "turn-1", "status": "completed", "tool": "wait_threads",
            "observed_at": "2026-09-14T10:00:00+00:00", "reference": "tool-result-1",
            "attempt": 1, "instruction_revision": 1, "controller_epoch": 1}


def running_task(state):
    state["tasks"]["a"].update(attempt=1, instruction_revision=1, status="RUNNING", worker_id="worker-1",
                               worker_thread_id="worker-1", worker_host_id="local", workspace_snapshot={"id": "workspace-1"},
                               assignment={"path": "assign.json", "sha256": "assignment-sha"})
    return state["tasks"]["a"]


def memory_mutator(state):
    """Retain the production transition while replacing only receipt I/O."""
    def mutate(receipt, revision, controller, epoch, action, *, claim=False):
        if revision != state["revision"]:
            raise contract.ParallelError("stale revision")
        if not claim and (controller != state["controller_id"] or epoch != state["controller_epoch"]):
            raise contract.ParallelError("stale controller")
        proposed = copy.deepcopy(state)
        result, changed = action(proposed)
        if changed:
            proposed["revision"] += 1
            contract.validate_state(proposed)
            state.clear()
            state.update(proposed)
        return {"state": copy.deepcopy(state), "result": result}
    return mutate


class PlanContractTests(unittest.TestCase):
    def test_independent_plan_is_valid(self):
        contract.validate_plan(plan_fixture())

    def test_overlapping_case_insensitive_writer_scopes_rejected(self):
        plan = plan_fixture()
        plan["tasks"][0]["write_paths"] = ["SRC"]
        plan["tasks"][0]["input_paths"] = ["SRC"]
        with self.assertRaises(contract.ParallelError):
            contract.validate_plan(plan)

    def test_different_file_prefixes_are_not_overlapping(self):
        self.assertFalse(contract.overlaps(["src/a"], ["src/ab"]))

    def test_writers_cannot_share_index(self):
        plan = plan_fixture()
        plan["tasks"][1]["worktree"] = plan["tasks"][0]["worktree"]
        with self.assertRaises(contract.ParallelError):
            contract.validate_plan(plan)

    def test_parent_branch_cannot_be_reused_by_writer(self):
        plan = plan_fixture()
        plan["tasks"][1]["branch"] = plan["parent_branch"]
        with self.assertRaises(contract.ParallelError):
            contract.validate_plan(plan)

    def test_write_paths_must_be_validation_inputs(self):
        plan = plan_fixture()
        plan["tasks"][0]["input_paths"] = ["tests/a.py"]
        with self.assertRaises(contract.ParallelError):
            contract.validate_plan(plan)

    def test_dependent_work_must_be_a_later_stage(self):
        plan = plan_fixture()
        plan["tasks"][1]["depends_on"] = ["a"]
        with self.assertRaises(contract.ParallelError):
            contract.validate_plan(plan)

    def test_path_traversal_and_git_control_paths_rejected(self):
        for path in ("../src", "src/../x", "/src", ".git/config", ".GIT/config", ".git./config",
                     "src /a", "src/*", "C:/src", "src\\a"):
            with self.subTest(path=path), self.assertRaises(contract.ParallelError):
                contract.relative(path)

    def test_unknown_criterion_check_cannot_claim_coverage(self):
        plan = plan_fixture()
        plan["tasks"][0]["criteria"][0]["checks"] = ["missing"]
        with self.assertRaises(contract.ParallelError):
            contract.validate_plan(plan)

    def test_approval_invalidated_by_model_change(self):
        state = state_fixture()
        state["plan"]["tasks"][0]["reasoning"] = "high"
        with self.assertRaisesRegex(contract.ParallelError, "approval"):
            contract.validate_state(state)

    def test_parallel_block_round_trip_and_duplicate_rejected(self):
        state = state_fixture()
        core = "## State verification\n\n### Handoff completion checklist\n\n- [x] done\n"
        receipt = contract.embed(core, state)
        self.assertEqual(contract.extract(receipt), state)
        self.assertNotIn(contract.HEADING, contract.without_block(receipt))
        with self.assertRaisesRegex(contract.ParallelError, "duplicate"):
            contract.extract(receipt + receipt)


class PauseAndOwnershipTests(unittest.TestCase):
    def test_pause_requires_terminal_worker_even_when_task_claims_stopped(self):
        state = state_fixture("PAUSED")
        task = running_task(state)
        task["status"] = "STOPPED"
        with self.assertRaisesRegex(contract.ParallelError, "stopped"):
            contract.validate_state(state)

    def test_terminal_worker_with_unknown_managed_process_is_not_stopped(self):
        state = state_fixture()
        task = running_task(state)
        task["termination"] = observation()
        task["processes"] = {"managed-1": {"status": "Unknown"}}
        self.assertFalse(contract.stopped(task))
        task["processes"]["managed-1"]["status"] = "Stopped"
        self.assertTrue(contract.stopped(task))

    def test_live_run_cannot_be_claimed_by_second_main(self):
        state = state_fixture()
        with patch.object(runtime, "mutate", memory_mutator(state)), self.assertRaises(contract.ParallelError):
            runtime.claim("HANDOFF.md", 7, "main-2")
        self.assertEqual(state["controller_id"], "main-1")

    def test_claim_paused_retains_completed_task_and_advances_epoch(self):
        state = state_fixture("PAUSED")
        task = running_task(state)
        task.update(status="INTEGRATED", result={"path": "result.json"}, review={"verdict": "accept"},
                    result_commit="b" * 40, termination=observation())
        with patch.object(runtime, "mutate", memory_mutator(state)), patch.object(runtime, "assert_parent"), \
                patch.object(runtime, "assert_workspace"):
            result = runtime.claim("HANDOFF.md", 7, "main-2")
        self.assertEqual(state["controller_epoch"], 2)
        self.assertEqual(state["tasks"]["a"]["status"], "INTEGRATED")
        self.assertNotIn("a", result["result"]["unfinished"])

    def test_old_epoch_worker_cannot_continue_writes(self):
        state = state_fixture()
        running_task(state)
        state["controller_epoch"] = 2
        with patch.object(runtime, "load", return_value=state), patch.object(runtime, "assert_workspace") as workspace:
            with self.assertRaises(contract.ParallelError):
                runtime.worker_guard("HANDOFF.md", "a", "worker-1", 1, 1, 1)
            workspace.assert_not_called()

    def test_new_main_cannot_follow_up_with_previous_main_worker(self):
        state = state_fixture()
        task = running_task(state)
        task.update(status="STOPPED", termination=observation())
        state["controller_id"] = "main-2"
        state["controller_epoch"] = 2
        with patch.object(runtime, "mutate", memory_mutator(state)), \
                patch.object(runtime, "assert_workspace"), \
                patch.object(runtime, "evidence_json", return_value={"controller_epoch": 1}), \
                patch.object(runtime, "publish") as publish:
            with self.assertRaises(contract.ParallelError):
                runtime.retry("HANDOFF.md", 7, "main-2", 2, "a", "Resume unfinished work")
            publish.assert_not_called()

    def test_old_turn_completion_cannot_retire_new_instruction(self):
        state = state_fixture()
        task = running_task(state)
        task["instruction_revision"] = 2
        with patch.object(runtime, "mutate", memory_mutator(state)), \
                patch.object(runtime, "workspace_snapshot") as snapshot:
            with self.assertRaises(contract.ParallelError):
                runtime.observe("HANDOFF.md", 7, "main-1", 1, "a", observation())
            snapshot.assert_not_called()
        self.assertIsNone(state["tasks"]["a"]["termination"])

    def test_dispatch_never_retries_uncertain_creation(self):
        state = state_fixture()
        task = running_task(state)
        task.update(status="DISPATCHING", worker_id=None, worker_thread_id=None)
        with patch.object(runtime, "mutate", memory_mutator(state)), patch.object(runtime, "publish") as publish:
            with self.assertRaises(contract.ParallelError):
                runtime.dispatch("HANDOFF.md", 7, "main-1", 1, "a")
            publish.assert_not_called()

    def test_next_attempt_uses_new_worker_and_preserves_checkpoint(self):
        state = state_fixture()
        task = running_task(state)
        checkpoint = {"path": "checkpoint.json", "sha256": "checkpoint-sha"}
        task.update(status="STOPPED", termination=observation(), checkpoint=checkpoint)
        with patch.object(runtime, "mutate", memory_mutator(state)), \
                patch.object(runtime, "assert_workspace", return_value=Path("worker-a")), \
                patch.object(runtime, "workspace_snapshot", return_value={"id": "preserved-index"}), \
                patch.object(runtime, "publish", return_value={"path": "new-assignment.json"}) as publish:
            runtime.dispatch("HANDOFF.md", 7, "main-1", 1, "a")
        assigned = publish.call_args.args[2]
        self.assertEqual(assigned["payload"]["resume"]["checkpoint"], checkpoint)
        self.assertEqual(assigned["payload"]["resume"]["previous_worker"], "worker-1")
        self.assertEqual(state["tasks"]["a"]["attempt"], 2)
        self.assertIsNone(state["tasks"]["a"]["worker_id"])


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.state = state_fixture()
        running_task(self.state)
        self.assignment = {"message_id": "assignment-1", "controller_epoch": 1}
        self.message = runtime.envelope(self.state, "a", "ACK", "worker-1",
                                       {"status": "READY", "workspace_snapshot": {"id": "workspace-1"}},
                                       "assignment-1")
        self.reference = {"path": "report.json", "sha256": "report-sha"}

    def receive(self):
        def evidence(_receipt, _state, ref):
            return self.assignment if ref == self.state["tasks"]["a"]["assignment"] else self.message
        with patch.object(runtime, "mutate", memory_mutator(self.state)), \
                patch.object(runtime, "evidence_json", side_effect=evidence):
            return runtime.receive("HANDOFF.md", self.state["revision"], "main-1", 1, self.reference, "worker-1")

    def test_valid_report_accepted_once_without_duplicate_revision(self):
        self.receive()
        revision = self.state["revision"]
        result = self.receive()
        self.assertEqual(result["result"]["status"], "ALREADY_RECEIVED")
        self.assertEqual(self.state["revision"], revision)

    def test_same_id_different_content_rejected(self):
        self.receive()
        self.reference["sha256"] = "altered"
        with self.assertRaises(contract.ParallelError):
            self.receive()

    def test_old_attempt_epoch_or_instruction_report_rejected(self):
        for field in ("attempt", "controller_epoch", "instruction_revision"):
            with self.subTest(field=field):
                saved = self.message[field]
                self.message[field] = 0
                with self.assertRaises(contract.ParallelError):
                    self.receive()
                self.message[field] = saved
        self.assertFalse(self.state["messages"])

    def test_reply_to_other_assignment_rejected(self):
        self.message["reply_to"] = "previous-assignment"
        with self.assertRaises(contract.ParallelError):
            self.receive()

    def test_result_without_current_validation_evidence_not_recorded(self):
        self.message["type"] = "RESULT"
        with patch.object(runtime, "validate_result", side_effect=contract.ParallelError("stale inputs")):
            with self.assertRaises(contract.ParallelError):
                self.receive()
        self.assertEqual(self.state["tasks"]["a"]["status"], "RUNNING")
        self.assertIsNone(self.state["tasks"]["a"]["result"])

    def test_entire_delivery_includes_inherited_untracked_file(self):
        self.state["plan"]["tasks"][0]["write_paths"] = ["src"]
        with patch.object(runtime, "git", side_effect=[Mock(stdout=b"src/a.py\0"), Mock(stdout=b"src/inherited.py\0")]), \
                patch.object(runtime, "dirty_paths", return_value=["src/inherited.py", "src/a.py"]):
            self.assertEqual(runtime.delivery_paths(self.state, "a"), ["src/a.py", "src/inherited.py"])

    def test_delivery_does_not_hide_unrelated_dirty_files(self):
        with patch.object(runtime, "git", return_value=Mock(stdout=b"")), \
                patch.object(runtime, "dirty_paths", return_value=["src/b.py"]):
            with self.assertRaises(contract.ParallelError):
                runtime.delivery_paths(self.state, "a")


class ReceiptCompareAndSwapTests(unittest.TestCase):
    def test_stale_revision_does_not_call_transition_or_replace_receipt(self):
        state = state_fixture()
        raw = contract.embed("## State verification\n\n### Handoff completion checklist\n", state).encode()
        @contextmanager
        def transaction(_receipt):
            yield raw
        action = Mock()
        with patch.object(runtime, "transaction", transaction), patch.object(runtime, "atomic_write") as write:
            with self.assertRaisesRegex(contract.ParallelError, "stale revision"):
                runtime.mutate("HANDOFF.md", 6, "main-1", 1, action)
            action.assert_not_called()
            write.assert_not_called()


    def test_stale_controller_cannot_mutate_current_state(self):
        state = state_fixture()
        raw = contract.embed("## State verification\n\n### Handoff completion checklist\n", state).encode()
        @contextmanager
        def transaction(_receipt):
            yield raw
        action = Mock()
        with patch.object(runtime, "transaction", transaction), patch.object(runtime, "atomic_write") as write:
            with self.assertRaisesRegex(contract.ParallelError, "ownership"):
                runtime.mutate("HANDOFF.md", 7, "main-old", 1, action)
            action.assert_not_called()
            write.assert_not_called()


class ReadOnlyWorkspaceTests(unittest.TestCase):
    def test_readonly_worker_cannot_change_source_then_validate_it(self):
        state = state_fixture()
        planned = state["plan"]["tasks"][0]
        planned["write_paths"] = []
        root = Path(planned["worktree"]).resolve()
        with patch.object(runtime, "repository", return_value=root), \
                patch.object(runtime, "common_dir", return_value=root / "common"), \
                patch.object(runtime, "git_text", return_value=planned["branch"]), \
                patch.object(runtime, "git", return_value=Mock(returncode=0)), \
                patch.object(runtime, "input_snapshot", return_value={"id": "changed-input", "files": {}}), \
                patch.object(runtime, "dirty_paths", return_value=["src/a.py"]):
            with self.assertRaises(contract.ParallelError):
                runtime.assert_workspace(state, "a")

    def test_readonly_worker_cannot_hide_out_of_input_source_change(self):
        state = state_fixture()
        planned = state["plan"]["tasks"][0]
        planned["write_paths"] = []
        root = Path(planned["worktree"]).resolve()
        with patch.object(runtime, "repository", return_value=root), \
                patch.object(runtime, "common_dir", return_value=root / "common"), \
                patch.object(runtime, "git_text", return_value=planned["branch"]), \
                patch.object(runtime, "git", return_value=Mock(returncode=0)), \
                patch.object(runtime, "input_snapshot", return_value=state["parent_inputs"]["a"]), \
                patch.object(runtime, "dirty_paths", return_value=["other-project/source.py"]):
            with self.assertRaises(contract.ParallelError):
                runtime.assert_workspace(state, "a")

class ReparseCompatibilityTests(unittest.TestCase):
    def test_reparse_attributes_rejected_without_junction_api(self):
        from types import SimpleNamespace
        root = Path(__file__).resolve().parent
        with patch.object(Path, "is_symlink", return_value=False), \
                patch.object(Path, "exists", return_value=True), \
                patch.object(Path, "lstat", return_value=SimpleNamespace(st_file_attributes=1024)), \
                patch.object(Path, "is_junction", return_value=False, create=True):
            with self.assertRaises(contract.ParallelError):
                contract.safe_path(root, "example.txt")


if __name__ == "__main__":
    unittest.main()
