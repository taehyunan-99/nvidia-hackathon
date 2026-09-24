"""App session identity, capacity and legacy recovery without live app mutations."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import json
import subprocess
import tempfile
from test_parallel_contract import (
    plan_fixture, state_fixture, running_task, observation, memory_mutator, runtime, contract,
)


class AppSessionTests(unittest.TestCase):
    def app_state(self):
        state = state_fixture()
        state["plan"]["app_project"] = {"project_id": "saved-parent", "host_id": "local", "path": state["plan"]["parent_worktree"]}
        for task in state["plan"]["tasks"]:
            task["worktree"] = None
        state["approval"]["plan_hash"] = contract.plan_hash(state["plan"])
        return state

    def test_app_paths_are_resolved_without_rewriting_approval(self):
        state = self.app_state()
        approved = contract.plan_hash(state["plan"])
        with patch.object(runtime, "mutate", memory_mutator(state)), patch.object(runtime, "assert_parent"):
            runtime.reserve_app("HANDOFF.md", 7, "main-1", 1, "a")
        self.assertFalse(contract.stopped(state["tasks"]["a"]))
        self.assertIsNone(contract.spec(state, "a")["worktree"])
        self.assertEqual(approved, contract.plan_hash(state["plan"]))
        with patch.object(runtime, "mutate", memory_mutator(state)):
            with self.assertRaisesRegex(contract.ParallelError, "already reserved"):
                runtime.reserve_app("HANDOFF.md", 8, "main-1", 1, "a")

    def test_pending_app_creation_uses_capacity_and_blocks_pause(self):
        state = self.app_state()
        state["plan"]["max_parallel"] = 1
        state["approval"]["plan_hash"] = contract.plan_hash(state["plan"])
        with patch.object(runtime, "mutate", memory_mutator(state)), patch.object(runtime, "assert_parent"):
            runtime.reserve_app("HANDOFF.md", 7, "main-1", 1, "a")
            with self.assertRaisesRegex(contract.ParallelError, "concurrency"):
                runtime.reserve_app("HANDOFF.md", 8, "main-1", 1, "b")
        state["phase"] = "PAUSED"
        with self.assertRaisesRegex(contract.ParallelError, "stopped"):
            contract.validate_state(state)

    def test_creation_response_survives_pending_setup_and_rejects_replacement(self):
        state = self.app_state()
        state["tasks"]["a"]["app_creation"] = {"nonce": "request-a", "status": "pending"}
        response = {"id": "client-new-thread:pending-a", "id_kind": "clientThreadId", "host_id": "local", "reference": "create-result"}
        with patch.object(runtime, "mutate", memory_mutator(state)):
            runtime.record_app("HANDOFF.md", 7, "main-1", 1, "a", response)
            self.assertIsNone(state["tasks"]["a"]["worker_id"])
            repeated = runtime.record_app("HANDOFF.md", 8, "main-1", 1, "a", response)
            self.assertEqual(repeated["result"]["status"], "ALREADY_RECORDED")
            with self.assertRaisesRegex(contract.ParallelError, "response changed"):
                runtime.record_app("HANDOFF.md", 8, "main-1", 1, "a", {**response, "id": "another-client"})

    def test_register_checks_app_identity_before_calling_harness(self):
        for mismatch in ("thread", "host", "baseline", "nonce", "terminal", "stopping", None):
            state = self.app_state()
            state["tasks"]["a"]["app_creation"] = {"nonce": "request-a", "status": "pending"}
            root = Path(state["plan"]["parent_worktree"]).parent / "actual-app-path"
            hello = {"nonce": "request-a", "run_id": "run1", "task_id": "a", "worker_id": "worker-1", "worktree": str(root), "head": "a" * 40}
            evidence = {"hello": {}, "thread_id": "worker-1", "host_id": "local", "creation_reference": "create-tool-result",
                        "terminal": {"tool": "wait_threads", "status": "completed", "turn_id": "registration-turn", "reference": "wait-result"}}
            if mismatch == "thread": evidence["thread_id"] = "pending-client"
            if mismatch == "host": evidence["host_id"] = "other-host"
            if mismatch == "baseline": hello["head"] = "b" * 40
            if mismatch == "nonce": hello["nonce"] = "other-creation"
            if mismatch == "terminal": evidence["terminal"]["status"] = "running"
            if mismatch == "stopping": state["phase"] = "STOPPING"
            output = {"action": "Registered", "baseSha": "a" * 40, "worktreePath": str(root)}
            with self.subTest(mismatch=mismatch), patch.object(runtime, "mutate", memory_mutator(state)), \
                    patch.object(runtime, "evidence_json", return_value=hello), \
                    patch.object(runtime, "input_snapshot", return_value=state["parent_inputs"]["a"]), \
                    patch.object(runtime, "common_dir", return_value=root.parent / ".git"), \
                    patch.object(runtime, "assert_workspace"), \
                    patch.object(runtime.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(output).encode(), b"")) as run:
                if mismatch and mismatch != "stopping":
                    with self.assertRaises(contract.ParallelError):
                        runtime.register_app("HANDOFF.md", 7, "main-1", 1, "a", evidence)
                    run.assert_not_called()
                else:
                    runtime.register_app("HANDOFF.md", 7, "main-1", 1, "a", evidence)
                    self.assertEqual(contract.spec(state, "a")["worktree"], str(root))
                    self.assertIsNone(state["plan"]["tasks"][0]["worktree"])
                    self.assertIn("-RegisterAppWorktree", run.call_args.args[0])
                    contract.validate_state(state)
                    if mismatch == "stopping":
                        with patch.object(runtime, "assert_checks_stopped"), patch.object(runtime, "assert_parent"):
                            runtime.pause("HANDOFF.md", 8, "main-1", 1)
                        self.assertEqual(state["phase"], "PAUSED")
                        continue
                    with patch.object(runtime, "assert_checks_stopped"), \
                            patch.object(runtime, "workspace_snapshot", return_value={}), \
                            patch.object(runtime, "publish", return_value={"path": "assignment", "sha256": "hash"}):
                        dispatched = runtime.dispatch("HANDOFF.md", 8, "main-1", 1, "a")["result"]
                    self.assertEqual(dispatched["registration_thread_id"], "worker-1")
                    self.assertEqual(dispatched["registration_host_id"], "local")

    def test_failed_creation_recovery_preserves_evidence_and_releases_only_confirmed_reservation(self):
        state = self.app_state()
        state["phase"] = "STOPPING"
        creation = {"nonce": "request-a", "status": "pending"}
        state["tasks"]["a"]["app_creation"] = creation
        evidence = {"nonce": "request-a", "tool": "create_thread", "status": "not-started", "reference": "explicit tool failure"}
        with patch.object(runtime, "mutate", memory_mutator(state)), patch.object(runtime, "write_artifact", return_value={}) as write:
            for invalid in ({"status": "timeout"}, {"nonce": "old-request"}, {"tool": "wait_threads"}):
                with self.assertRaises(contract.ParallelError):
                    runtime.recover_app("HANDOFF.md", 7, "main-1", 1, "a", {**evidence, **invalid})
                self.assertFalse(contract.stopped(state["tasks"]["a"]))
            write.assert_not_called()
            runtime.recover_app("HANDOFF.md", 7, "main-1", 1, "a", evidence)
            self.assertEqual(write.call_args.args[-1], {"creation": creation, "evidence": evidence})
            self.assertTrue(contract.stopped(state["tasks"]["a"]))
            with patch.object(runtime, "assert_checks_stopped"), patch.object(runtime, "assert_parent"):
                runtime.pause("HANDOFF.md", 8, "main-1", 1)
        self.assertEqual(state["phase"], "PAUSED")

    def test_resumed_app_dispatch_forks_stopped_task_without_saved_child_project(self):
        for previous_attempt in (0, 1):
            state = self.app_state()
            state["plan"]["session_policy"] = "one-task-one-retry"
            state["approval"]["plan_hash"] = contract.plan_hash(state["plan"])
            state.update(controller_id="main-2", controller_epoch=2)
            task = state["tasks"]["a"]
            if previous_attempt:
                task = running_task(state)
                task.update(status="STOPPED", termination=observation(), session_retries=1, reworks=1)
            task["app_creation"] = {"nonce": "request-a", "status": "registered", "controller_epoch": 1,
                                    "worktree": str(Path(state["plan"]["parent_worktree"]).parent / "app-child"),
                                    "thread_id": "worker-1", "host_id": "local", "registration": {}, "evidence": {}}
            with self.subTest(attempt=previous_attempt), patch.object(runtime, "mutate", memory_mutator(state)), \
                    patch.object(runtime, "assert_checks_stopped"), patch.object(runtime, "assert_workspace"), \
                    patch.object(runtime, "input_snapshot", return_value=state["parent_inputs"]["a"]), \
                    patch.object(runtime, "workspace_snapshot", return_value={}), \
                    patch.object(runtime, "publish", return_value={"path": "assignment", "sha256": "hash"}):
                dispatched = runtime.dispatch("HANDOFF.md", 7, "main-2", 2, "a")["result"]
                self.assertIsNone(dispatched["registration_thread_id"])
                self.assertEqual(dispatched["registration_fork_thread_id"], "worker-1")
                self.assertEqual(dispatched["registration_fork_host_id"], "local")
                self.assertEqual(state["tasks"]["a"]["session_retries"], 0)
                self.assertEqual(state["tasks"]["a"]["reworks"], previous_attempt)
                for worker in ("worker-1", "fork-worker"):
                    hello = {"worker_id": worker, "run_id": "run1", "task_id": "a", "attempt": previous_attempt + 1,
                             "controller_epoch": 2, "assignment_sha256": "hash"}
                    with patch.object(runtime, "evidence_json", side_effect=[hello, {"payload": {"resume": {"previous_worker": "worker-1"}}}]):
                        if worker == "worker-1":
                            with self.assertRaisesRegex(contract.ParallelError, "new task"):
                                runtime.bind("HANDOFF.md", 8, "main-2", 2, "a", {}, worker, "local")
                        else:
                            runtime.bind("HANDOFF.md", 8, "main-2", 2, "a", {}, worker, "local")
                self.assertEqual(state["tasks"]["a"]["worker_id"], "fork-worker")

    def test_session_limit_survives_receipt_reload_and_failed_preparation_does_not_consume_it(self):
        from test_parallel_receipt import planned_receipt
        raw, state = planned_receipt()
        state["phase"] = "ACTIVE"
        state["plan"]["session_policy"] = "one-task-one-retry"
        state["approval"] = {"plan_hash": contract.plan_hash(state["plan"]), "evidence": "approved", "internal_git": True}
        running_task(state).update(status="CHANGES_REQUESTED", termination=observation())
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "HANDOFF.md"
            receipt.write_text(contract.embed(raw, state).replace("Receipt: READY", "Receipt: STALE"), encoding="utf-8")
            original = receipt.read_bytes()
            with patch.object(runtime, "assert_checks_stopped"), \
                    patch.object(runtime, "evidence_json", return_value={"controller_epoch": 1}), \
                    patch.object(runtime, "assert_workspace", side_effect=contract.ParallelError("workspace changed")):
                with self.assertRaisesRegex(contract.ParallelError, "workspace changed"):
                    runtime.retry(receipt, 7, "main-1", 1, "a", "same task correction")
            self.assertEqual(receipt.read_bytes(), original)
            self.assertEqual(list(Path(directory).rglob("handoff-runs/*")), [])
            with patch.object(runtime, "assert_checks_stopped"), patch.object(runtime, "assert_workspace"), \
                    patch.object(runtime, "evidence_json", return_value={"controller_epoch": 1}), \
                    patch.object(runtime, "workspace_snapshot", return_value={}):
                runtime.retry(receipt, 7, "main-1", 1, "a", "same task correction")
                self.assertEqual(runtime.load(receipt)["tasks"]["a"]["session_retries"], 1)
                runtime.observe(receipt, 8, "main-1", 1, "a", {**observation(), "instruction_revision": 2})
                saved = receipt.read_bytes()
                artifacts = sorted(Path(directory).rglob("*.json"))
                with self.assertRaisesRegex(contract.ParallelError, "one correction"):
                    runtime.retry(receipt, 9, "main-1", 1, "a", "another correction")
                self.assertEqual(receipt.read_bytes(), saved)
                self.assertEqual(sorted(Path(directory).rglob("*.json")), artifacts)

    def test_fixed_task_changes_invalidate_approval_and_completed_worker_cannot_restart(self):
        state = state_fixture()
        state["plan"]["session_policy"] = "one-task-one-retry"
        state["approval"]["plan_hash"] = contract.plan_hash(state["plan"])
        for field, value in (("goal", "Another task"), ("write_paths", []),
                             ("checks", [{"id": "unit", "kind": "inspection", "instruction": "Different acceptance"}])):
            changed = copy.deepcopy(state)
            changed["plan"]["tasks"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(contract.ParallelError, "approval is stale"):
                contract.validate_state(changed)
        task = running_task(state)
        task.update(status="VERIFIED", result={}, review={"verdict": "accept"}, termination=observation(), session_retries=1)
        with patch.object(runtime, "mutate", memory_mutator(state)), patch.object(runtime, "load", return_value=state), \
                patch.object(runtime, "assert_workspace") as workspace:
            for operation, arguments in ((runtime.retry, ("HANDOFF.md", 7, "main-1", 1, "a")),
                                         (runtime.dispatch, ("HANDOFF.md", 7, "main-1", 1, "a")),
                                         (runtime.worker_guard, ("HANDOFF.md", "a", "worker-1", 1, 1, 1))):
                with self.assertRaises(contract.ParallelError):
                    operation(*arguments)
            workspace.assert_not_called()

    def test_recover_creation_can_retry_after_evidence_saved_but_receipt_write_lost(self):
        state = self.app_state()
        state["tasks"]["a"]["app_creation"] = {"nonce": "request-a", "status": "pending"}
        evidence = {"nonce": "request-a", "tool": "create_thread", "status": "not-started", "reference": "explicit failure"}
        def lost_save(receipt, revision, controller, epoch, action):
            action(copy.deepcopy(state))
            raise OSError("receipt write interrupted")
        with tempfile.TemporaryDirectory() as directory:
            receipt = Path(directory) / "HANDOFF.md"
            with patch.object(runtime, "mutate", lost_save), self.assertRaisesRegex(OSError, "interrupted"):
                runtime.recover_app(receipt, 7, "main-1", 1, "a", evidence)
            self.assertFalse(contract.stopped(state["tasks"]["a"]))
            with patch.object(runtime, "mutate", memory_mutator(state)):
                runtime.recover_app(receipt, 7, "main-1", 1, "a", evidence)
            self.assertTrue(contract.stopped(state["tasks"]["a"]))
            self.assertEqual(len(list(Path(directory).rglob("app-failure-*.json"))), 2)

    def test_single_task_policy_limits_followup_execution_without_changing_old_plans(self):
        for policy in (None, "one-task-one-retry"):
            state = state_fixture()
            if policy:
                state["plan"]["session_policy"] = policy
                state["approval"]["plan_hash"] = contract.plan_hash(state["plan"])
            running_task(state).update(status="CHANGES_REQUESTED", termination=observation())
            with self.subTest(policy=policy), patch.object(runtime, "mutate", memory_mutator(state)), \
                    patch.object(runtime, "assert_checks_stopped"), patch.object(runtime, "assert_workspace"), \
                    patch.object(runtime, "evidence_json", return_value={"controller_epoch": 1}), \
                    patch.object(runtime, "workspace_snapshot", return_value={}), \
                    patch.object(runtime, "publish", return_value={"path": "assignment", "sha256": "hash"}):
                runtime.retry("HANDOFF.md", 7, "main-1", 1, "a", "same goal correction")
                state["tasks"]["a"].update(status="CHANGES_REQUESTED", termination={**observation(), "instruction_revision": 2})
                if policy:
                    with self.assertRaisesRegex(contract.ParallelError, "one correction"):
                        runtime.retry("HANDOFF.md", 8, "main-1", 1, "a", "another correction")
                    self.assertEqual(state["revision"], 8)
                else:
                    runtime.retry("HANDOFF.md", 8, "main-1", 1, "a", "existing approved behavior")

    def legacy(self, state):
        del state["plan"]["execution_backend"]
        del state["plan"]["max_parallel"]
        if state["approval"]:
            state["approval"]["plan_hash"] = contract.plan_hash(state["plan"])
        return state

    def test_subagent_backend_rejected_for_both_modes(self):
        for mode in ("auto", "manual"):
            for backend in ("spawn_agent", "subagents", None):
                plan = plan_fixture()
                plan.update(mode=mode, execution_backend=backend)
                with self.subTest(mode=mode, backend=backend), self.assertRaisesRegex(contract.ParallelError, "app-threads"):
                    contract.validate_plan(plan)

    def test_concurrency_must_be_explicit_positive_integer(self):
        for value in (None, 0, -1, True, 1.5):
            plan = plan_fixture()
            plan["max_parallel"] = value
            with self.subTest(value=value), self.assertRaises(contract.ParallelError):
                contract.validate_plan(plan)

    def test_more_than_three_planned_and_live_sessions_allowed(self):
        state = state_fixture()
        state["plan"]["max_parallel"] = 5
        template = state["plan"]["tasks"][0]
        for name in ("c", "d", "e"):
            task = copy.deepcopy(template)
            task.update(id=name, write_paths=["src/" + name], input_paths=["src/" + name],
                        worktree=str(Path(template["worktree"]).parent / name), branch="feature/repo/" + name)
            state["plan"]["tasks"].append(task)
            state["tasks"][name] = copy.deepcopy(state["tasks"]["b"])
        contract.validate_plan(state["plan"])
        for name in ("a", "b", "c", "d"):
            state["tasks"][name].update(attempt=1, status="DISPATCHING")
        runtime.require_capacity(state)
        state["tasks"]["e"].update(attempt=1, status="DISPATCHING")
        with self.assertRaisesRegex(contract.ParallelError, "concurrency"):
            runtime.require_capacity(state)
        state["tasks"]["a"]["termination"] = observation()
        runtime.require_capacity(state)

    def test_full_capacity_blocks_dispatch_and_retry_before_side_effects(self):
        for action in (runtime.dispatch, runtime.retry):
            state = state_fixture()
            running_task(state)
            state["plan"]["max_parallel"] = 1
            with patch.object(runtime, "mutate", memory_mutator(state)), patch.object(runtime, "assert_workspace") as workspace:
                with self.assertRaisesRegex(contract.ParallelError, "concurrency"):
                    action("HANDOFF.md", 7, "main-1", 1, "b")
                workspace.assert_not_called()

    def test_new_plan_requires_explicit_backend_before_receipt_io(self):
        plan = self.legacy(state_fixture())["plan"]
        with patch.object(runtime, "repository") as repository:
            with self.assertRaisesRegex(contract.ParallelError, "legacy"):
                runtime.prepare("HANDOFF.md", plan)
            repository.assert_not_called()

    def test_legacy_can_be_read_and_stopped_but_not_resumed(self):
        state = self.legacy(state_fixture())
        task = running_task(state)
        task["worker_thread_id"] = "/root/legacy"
        task["termination"] = dict(observation(), tool="list_agents")
        task["status"] = "STOPPED"
        contract.validate_state(state)
        with patch.object(runtime, "load", return_value=state), patch.object(runtime, "assert_workspace"):
            task["termination"] = None
            task["status"] = "RUNNING"
            runtime.worker_guard("HANDOFF.md", "a", "worker-1", 1, 1, 1, stopping=True)
            with self.assertRaisesRegex(contract.ParallelError, "legacy"):
                runtime.worker_guard("HANDOFF.md", "a", "worker-1", 1, 1, 1)
        with self.assertRaisesRegex(contract.ParallelError, "legacy"):
            runtime.internal_git(state)
        for action, args in ((runtime.finish, ("main-1", 1)),
                             (runtime.claim, ("main-1",)),
                             (runtime.approve, ("explicit request", True)),
                             (runtime.dispatch, ("main-1", 1, "b")),
                             (runtime.retry, ("main-1", 1, "a"))):
            with patch.object(runtime, "mutate", memory_mutator(state)):
                with self.assertRaisesRegex(contract.ParallelError, "legacy"):
                    action("HANDOFF.md", 7, *args)

    def test_native_observation_cannot_retire_app_session(self):
        for tool in ("list_agents", "interrupt_agent"):
            state = state_fixture()
            task = running_task(state)
            task["termination"] = dict(observation(), tool=tool)
            with self.subTest(tool=tool), self.assertRaisesRegex(contract.ParallelError, "app-threads"):
                contract.validate_state(state)

    def test_binding_requires_actual_app_identity_and_host(self):
        for handle, host, valid in (("/root/a", "local", False), ("pending-client", "local", False),
                                    ("worker-1", None, False), ("worker-1", "verified-host", True)):
            state = state_fixture()
            task = running_task(state)
            task.update(status="DISPATCHING", worker_id=None)
            hello = {"worker_id": "worker-1", "run_id": state["run_id"], "task_id": "a", "attempt": 1,
                     "controller_epoch": 1, "assignment_sha256": task["assignment"]["sha256"]}
            with self.subTest(handle=handle, host=host), patch.object(runtime, "mutate", memory_mutator(state)), \
                    patch.object(runtime, "evidence_json", side_effect=[hello, {"payload": {"resume": {"previous_worker": None}}}]), \
                    patch.object(runtime, "assert_workspace"):
                if valid:
                    runtime.bind("HANDOFF.md", 7, "main-1", 1, "a", {}, handle, host)
                    self.assertEqual(state["tasks"]["a"]["worker_host_id"], host)
                else:
                    with self.assertRaises(contract.ParallelError):
                        runtime.bind("HANDOFF.md", 7, "main-1", 1, "a", {}, handle, host)
                    self.assertIsNone(state["tasks"]["a"]["worker_id"])
