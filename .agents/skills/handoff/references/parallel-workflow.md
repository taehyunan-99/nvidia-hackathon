# Parallel workflow (Codex desktop)

Read this together with SKILL.md and parallel-messages.md. The Python helper
validates files and state; the main session calls permitted app task tools itself.
It does not launch models, call app-server APIs, or create a persistent scheduler.
This is a cooperative workflow, not a security boundary against another process
with the same user's filesystem access.

## State and scope

- Keep one JSON block under `State verification / Parallel execution` in
  `docs/HANDOFF.md`. The helper creates v8; all other v7 sections remain required.
- Store immutable messages, checks and snapshots under
  `docs/handoff-runs/<run_id>/`. These are evidence, not another current task list.
- The receipt, evidence, HTML report and adjacent lock remain local and Git-ignored.
  Workers access the main checkout's artifacts through the assigned paths;
  do not rely on commits to transfer these artifacts into worker worktrees.
- The main alone changes the receipt. Workers use `emit` to write evidence and
  report its absolute path and SHA256. Never construct their own identity headers.
- Main mutation commands require the latest `--revision`, `--controller` and
  `--epoch`. Inspect after every mutation; do not predict revision numbers.
  The adjacent exclusive lock serializes updates and byte comparison rejects
  concurrent edits. Never steal a lock based on elapsed time.
- Run phases: PLANNED → ACTIVE → STOPPING → PAUSED → ACTIVE, or ACTIVE → COMPLETE.
  Worker RESULT means REPORTED. Main acceptance means VERIFIED. Source merge
  means INTEGRATED. A worker's “done” message does not prove either later state.
- After a COMPLETE run, next may replace it with the next parallel proposal.
  For a sequential next stage, omit the completed parallel block and use v7;
  retain immutable old run evidence. Never discard an unfinished run this way.
- Only independent tasks are supported: `depends_on: []`, disjoint write scopes,
  and no worker reading another worker's mutable output. Put dependent work in
  the next main stage. Shared stable inputs are allowed.
- Writers require separate worktrees. Read-only tasks can share the main when
  their inputs stay unchanged. Each app session must use and verify its own
  assigned workspace before editing.

## App capabilities, authority and workspace preflight

Execution backend is `app-threads`. Automatic mode creates separate app tasks;
manual mode registers user-created app tasks. Both use the same app-session
identity and receipt protocol. Native subagents are not an execution mode and
cannot be registered as workers, but the main or a worker may select them
autonomously for bounded internal assistance when task size, independent
subtasks or verification value justify the coordination cost and host rules
allow it. No separate user instruction to use subagents is required. The owning
app session keeps its scope and remains responsible for validation, subagent
termination and reporting through the app-session protocol.

Before approval, inspect the currently callable tools and their schemas:

| Operation | App tool / required evidence |
| --- | --- |
| Find the parent project | `list_projects`; actual project ID, host, saved path and Git repository flag |
| Create a requested session | `create_thread`; confirmed actual threadId and hostId |
| Resume in an existing app worktree | `fork_thread` with `environment.type=same-directory`; new actual threadId and hostId |
| Send assignment, correction or STOP | `send_message_to_thread` to that threadId/hostId |
| Read result and observe a terminal turn | `read_thread`, `wait_threads` |
| Apply display status | `set_thread_title` with the actual threadId |

The user must explicitly request separate app tasks for the concrete scope.
Reuse that request across the approved run. One approval covers the named app
tasks, model/reasoning, pinned parent commit, independent write scopes, maximum
concurrency, checks, rework limit and internal Git authority. For new app worktrees,
approve the saved parent project and isolation conditions; the actual child paths
are discovered after creation. Routine preparation and bounded retries within
these conditions do not require another confirmation. Report scope changes or
unresolved permission/tool constraints separately.
A user-specified set of independent app tasks remains an explicit app-task
request even though all of them contribute to the current request. Do not
reclassify those named sessions as agent-inferred internal decomposition.
Follow each tool's creation and model-override rules; recommendations alone do
not authorize overriding a model. If current higher-priority host rules prohibit
app tasks for the proposed work, stop before dispatch and explain the conflict.
An ordinary preference for native subagents when the model decomposes work on its
own is not such a conflict after the user explicitly requested the concrete app
tasks. A conflict requires an explicit prohibition on the requested app-task
creation or a missing required capability. Do not route around a real conflict
with a CLI, hidden API, or `spawn_agent`.

All sessions must run on the verified parent host; this file protocol does not
synchronize hosts. For new automatic writers, use the existing Git project from
`list_projects` with `environment.type=worktree` and the explicitly approved
full parent SHA as `startingState={type:branch, branchName:<SHA>}`. Do not ask the
user to register child directories as saved projects. Verify the actual checkout
after app setup and register it with the shared safety helper before assignment.
If this host cannot resolve the approved ref, stop and report that exact constraint;
never silently use the default branch or include the parent's working changes.
Manual/existing exact workspaces retain the previous guarded path protocol.
Never migrate an approved/active old plan in place to the new app creation flow.
`handoff` owns this orchestration and calls shared scripts directly; invoking
`task-workflow` is not a dependency. Git ownership/path/base validation remains
in the bundled `scripts/worktree_guard.py`, with pinned HEAD and persisted task ownership.

A create result containing only `clientThreadId` means setup is pending. Do not
bind it or pass it to tools requiring threadId. Resolve the actual task through
app listing/reading and its registration evidence. Keep the creation response as
evidence; do not issue another creation after a timeout or ambiguous response.
Run `record-app --task T1 --input response.json` immediately with the returned
ID, ID kind, host and tool-result reference, even while setup is pending.
Host IDs come from actual app results, never from an assumed `local` default.
If listing lags, a hello artifact matching the reserved nonce can provide a
candidate ID; confirm it with `read_thread` and its own app response before binding.
If hello failed before producing evidence, a read-only correlation of that exact
client ID in the host's app setup logs may identify a candidate actual ID. Confirm
it with `read_thread`; logs alone never authorize binding or prove termination.
An artifact alone does not prove app identity or terminal status. When a worker
cannot write the parent evidence directory under its sandbox, retry the same
approved artifact operation through the normal permission mechanism. Do not
broaden source ownership or request the same execution-plan approval again.

A STOP message requests cooperation; it does not prove interruption. Discover
an app task stop tool if one is available and permitted. Otherwise request STOP
and wait for the actual work turn to finish, or have the user stop that exact
task in the app. Never use `interrupt_agent` on an app task, archive it to stop
it, or misuse handoff/move tools as interruption. Unknown termination remains
STOPPING/STALE and prevents pause completion, reuse and integration.
An app turn can finish while an asynchronous command still has a session ID.
Require completion of its command/tool execution as well as the turn and managed
RunIds; an empty initial command response is not a completed result. Workers must
wait on returned command sessions before their final report.

Record `max_parallel` in the approved plan from the user's resource constraint
and actual app availability. The helper limits live dispatched turns to that
value, including registration and turns awaiting termination evidence. It does
not impose a total task limit of three. `wait_threads`' per-call target limit is
a polling batch limit, not a total session limit. Wait with returned host IDs
and cursors (`afterCursor`), in bounded batches; do not poll unchanged results.
New plans use `notification_mode:direct`: after dispatch, the main ends its turn
while the run stays ACTIVE. Workers send result/urgent-question notifications to
the actual main with `send_message_to_thread`; see [parallel-wait.md](parallel-wait.md).
The existing batch collector remains an explicit tools-mode or legacy fallback.
Avoid repeated status snapshots while workers do substantive work.

## next and approval

1. Complete normal handoff preparation. The selected stage must describe actual
   development, contain PASS Ultra independence evidence, and have Use Ultra: yes.
2. Prepare a plan JSON using the message reference below. Include at least two
   bounded tasks, actual app-session model/tool availability, inspection/test criteria,
   explicit input files/directories, write paths, and a small rework limit.
   Include source, tests, configuration and dependencies that affect validation.
   Avoid the runtime receipt/report directory in validation inputs.
3. Show a compact task table: goal, write ownership, new/reused worktree and
   branch, model, reasoning, success criteria. Also show baseline SHA, integration
   checks, execution backend/mode, notification mode and main idle/resume procedure,
   max_parallel, saved parent app project and isolation conditions,
   stop method, internal source commit/merge authority, and rework limit. Reuse prior
   explicit authorization when it covers this concrete plan.
4. `prepare --input plan.json` stores an unapproved PLANNED proposal. During
   next, leave it unapproved: the outgoing source commit has not happened
   yet. After start verifies the delivered parent, prepare again at its actual
   SHA, then `approve --evidence <user-message-reference> --internal-git` binds
   the concrete execution plan. Reuse earlier authorization if it covers those
   same tasks. Omit internal-git for a read-only plan.
5. Preparing the handoff does not create app sessions. New main `start` verifies the
   actual delivered parent. An unapproved PLANNED plan can be prepared again at
   the current parent commit before approval/worktree creation. An approved or
   started plan is immutable: changed scope/baseline requires an explicit revised
   plan and preserved old evidence, not silently editing its JSON.

## start, registration and automatic work

All commands below are:

`python <skill>/scripts/parallel_handoff.py <action> --project-root <project>
--app [arguments]`. Inspect omits --app. Use the actual Python interpreter for the target project on Windows and macOS; no company recovery runner is required.

1. Inspect and verify ordinary receipt evidence and current Git state. COMPLETE
   means no remaining worker creation. For PAUSED, preserve existing worktrees,
   tracked/staged/untracked files and report references.
2. For PLANNED, finish the baseline preparation and approval described above.
   `claim --revision N --controller <actual-main-ID>` acquires a new epoch.
   A live ACTIVE/STOPPING run cannot be claimed. First verify retained REPORTED
   results; do not rerun accepted or integrated work.
3. For new automatic app writers, set task `worktree:null` and plan `app_project`
   to the verified saved project ID, host and path. Run `reserve-app --task T1`
   with controller/revision/epoch before calling `create_thread`. The persisted
   nonce reserves concurrency and prevents duplicate creation after ambiguous
   responses. Create one task on that existing project in app worktree mode at
   the approved SHA. Its first prompt runs only `app-hello --task T1 --nonce N`
   using the approved helper and parent receipt, from its actual assigned cwd.
   It reports the evidence path/hash and ends without source edits.

   Resolve the actual threadId/hostId through app tools, match CODEX_THREAD_ID
   and nonce in its hello, and observe that registration turn completed. Save the
   `register-app` input described in parallel-messages.md, then run `register-app`.
   This invokes the bundled worktree guard using the active Python interpreter with
   `-RegisterAppWorktree <actual-path> -AppThreadId <actual-ID> -AppHostId <host>`
   and the approved parent/child/run arguments. The helper checks repository,
   path, clean pinned HEAD, ownership and branch; it creates the approved branch
   only on an unregistered detached checkout. It never renames an unrelated branch.
   The runtime records actual path, ID, host, registration and app evidence without
   changing the approved plan. Prepare local dependencies within approved scope,
   then dispatch; input matching remains mandatory. If setup modifies inputs,
   restore the approved inputs or revise the plan explicitly before dispatch.

   For manual writers, explicitly approve an exact child path and task branch.
   Create a detached linked worktree at the approved parent SHA with Git, then register it:
   `python <skill-dir>/scripts/worktree_guard.py -Branch <child-branch>
   -ParentBranch <parent-branch> -ParentCommit <full-SHA>
   -ParentWorktree <parent-worktree> -RunId <run_id>
   -RegisterAppWorktree <child-path> -AppThreadId <actual-ID> -AppHostId <actual-host>`.
   Reuse the registered child path after pause. Do not create another worktree
   merely because the worker changed. Unrelated main updates belong to PR preparation.
4. `dispatch --task T1 --revision N --controller MAIN --epoch E` writes
   DISPATCHING and returns ASSIGN after app worktree registration (before session
   creation only for legacy/manual exact workspaces).
   The helper enforces approved `max_parallel`; dispatch only sessions that
   can start now after the capability and exact-workspace preflight.
5. Follow the dispatch result for a registered app-created worktree. If it returns
   `registration_thread_id`, send ASSIGN/hello to that recorded task. If it returns
   `registration_fork_thread_id`, use `fork_thread` on that stopped task with
   `environment={type:same-directory}`. Confirm the new actual ID and host, then
   send ASSIGN/hello to the new task; retain the approved model/reasoning on the
   follow-up. A fork only carries completed history and needs that new prompt to
   start. Do not replay an inherited old assignment. This preserves the registered
   checkout without adding a saved child project. If same-directory fork is not
   available, report that specific resume constraint before starting a worker.
   For legacy/manual mode,
   call `create_thread` only for the explicitly requested separate app session
   using the verified exact child workspace target. Supply a registration-only
   prompt with the receipt/project and ASSIGN artifact path. Ask the sub-session
   to run `hello --task T1 --assignment <path>`, return the reference and finish
   without source edits. Set model/thinking only when explicitly requested and
   allowed by the tool. Manual mode uses a user-created app session instead.
6. Read the created task through its actual threadId/hostId, verify the hello
   sender and require its CODEX_THREAD_ID to equal that actual threadId. Main
   runs `bind --task T1 --input hello-reference.json --handle <actual-threadId>
   --host-id <actual-hostId> --revision N --controller MAIN --epoch E`.
   Verify the registration turn ended with `wait_threads` or `read_thread`;
   a hello in commentary alone is insufficient. `prompt --task T1` generates
   the full execution packet. Send it with `send_message_to_thread` using
   the bound threadId/hostId. The sub-session applies its [SUB] Working title
   before ACK. This two-turn registration prevents edits before identity binding.
7. Worker runs worker-check, emits ACK before edits, edits only its paths, runs
   declared checks, and emits RESULT with the generated checks reference. In a
   direct-notification plan, the worker saves the emit reference, runs `notify`
   with that reference as `--input` and its normal worker/epoch/attempt/instruction
   arguments, then passes the returned threadId/prompt to `send_message_to_thread`
   unchanged. It reports delivery status and ends its turn. ACK and routine
   progress do not notify. QUESTION/BLOCKED and stop CHECKPOINT use the same route.
   The helper does not call app tools or mutate the main's receipt; it verifies
   the actual sender, current assignment and immutable artifact before generating
   the notification. Main
   reads the sub-session's own app response containing each artifact path/SHA256
   with `read_thread`/`wait_threads`, then records it with
   `receive --input reference.json --worker ACTUAL_ID`. Workers report in their
   own app task; native agent mailboxes are not part of this protocol.
8. Use `wait_threads` / `read_thread` to obtain terminal status for the **execution
   turn**, not the earlier registration turn. Record `observe --task T1 --input
   observation.json` with attempt, instruction_revision, epoch, turn reference,
   tool and timestamp. Idle/completed means the turn ended; it does not delete
   the session. Do not reuse that terminal observation for a later follow-up.

Before each worker source edit or verification, worker-check must succeed with
its worker ID, epoch, attempt and instruction revision. This cooperative check
detects stale assignments; actual stop confirmation is still required.

## Review, questions and integration

### One bounded task per session

New `prepare` proposals record `session_policy:one-task-one-retry`. It is included
in the approval hash. Each worker owns one fixed goal, write scope and set of
checks. App registration/hello and result collection do not count as corrections;
`retry` permits one follow-up execution in that session, including a decision that
restarts execution. Further execution requires a stopped checkpoint and review
of the remaining work. The overall approved rework limit still applies; session
replacement never expands it. Recommend an overall rework limit of one.

New requirements, changed acceptance criteria and the next independent task never
go to the old worker. First review/integrate the current result, then approve the
next bounded plan at the resulting parent commit and create a fresh app worktree
task from the saved parent project. Keep the new packet to goal, constraints,
owned files, checks and necessary decisions/references. Do not copy transcripts.
Keep the completed old task as history; archive only when explicitly requested.

`fork_thread` preserves completed conversation history. Use the dispatch fork
route solely to recover the same unfinished task in its retained checkout, never
to promise a clean context or run a new requirement. If that unfinished task needs
a clean context too, stop at its checkpoint and resolve a fresh workspace/input
plan before dispatch; do not silently reset or drop uncommitted work. Existing
approved plans without session_policy retain their previous retry behavior.

Workers send UPDATE with QUESTION/BLOCKED plus concrete context when they need a
decision. Main resolves within existing authority and sends a generated DECISION
using `retry --evidence <decision-and-authority>` only after that turn stopped.
Same-main corrections can keep the same worker/attempt; instruction_revision
increments. After a new main claims, retry of an old worker is rejected: dispatch
a new attempt instead.

Main reviews actual files/diffs and validation evidence:

- `review --task T1 --verdict accept --evidence <review-findings>` rechecks input
  hashes, criteria and the whole delivery manifest, then records VERIFIED.
  Now run `title --task T1` and call set_thread_title with its returned
  `thread_id` and `title` to apply [SUB] Complete. Use the actual app ID,
  never the native handle. Complete means the main accepted this worker's
  result; INTEGRATED remains a separate recorded state.
- `review --verdict changes` records concrete reproduction/fix/verification and
  consumes a rework allowance. Stop confirmation precedes retry or new dispatch.
  Exceeding scope, capability or rework authority requires a revised user decision.
- Wait for all workers and managed processes to stop before any internal Git.
  Main first inspects the reviewed working content and owned pending index paths.
  Synchronize those owned paths with explicit `git add -- <paths>`, then read both
  `git diff --cached --name-only` and `git diff --cached`, including inherited files.
  Never include unrelated index entries. Verify repository hooks normally; do not use --no-verify.
  `commit --task T1 --message "feat(scope): 한국어 요약"` repeats the scoped
  synchronization and verifies the staged manifest against delivery_files.
  Main must inspect the intended working and staged diffs first and follow
  repository hook/commit rules. Workers never commit.
- `integrate --task T1` validates the result range and merges it into the parent
  task branch. Only controlled handoff metadata may be dirty in the parent.
  No shared develop update, push, PR, destructive reset or branch cleanup occurs.
- `finish` runs integration checks against the actual merged inputs and records
  COMPLETE only when every task is reviewed and every writer integrated.
  Then update the ordinary Korean work summary. next/done refresh normal
  evidence, stage gates and the final checklist before setting READY.

Command checks use bundled `managed_check.py` and persist each
RunId before waiting. Pause/recovery also checks these records; a lost worker
reply cannot hide a still-running verification process. Other worker-started
managed processes must be reported immediately via UPDATE and recorded by the
main with `process`, including terminal Status/Stop evidence.

## pause and new main

1. `request-stop` stores STOPPING and produces STOP messages. Send them to live
   workers. Stop dispatching and source writes; collect CHECKPOINT if feasible.
   Pending app setup reserves a slot even before ASSIGN. Reconcile its recorded
   creation response and actual registration turn. `register-app` remains allowed
   in STOPPING after that turn completes; it records the verified checkout without
   dispatching work. If creation explicitly failed before a task started, use
   `recover-app` with the reserved nonce and direct `create_thread` failure evidence.
   A timeout, missing reply, or a known actual task ID is not proof of non-start.
2. Use a supported app stop action or the cooperative STOP/manual app stop
   procedure above, then observe each actual work turn as terminal.
   Stop every managed RunId and record the result with `process`.
3. Main checks files directly even if interruption prevented CHECKPOINT. Preserve
   dirty index/files, tests already valid, decisions and remaining work. Run
   `checkpoint-main --task T1 --input notes.json` after termination observation
   to preserve the main's direct findings and remaining work in a generated
   CHECKPOINT for the next ASSIGN. Never
   invent a completed result after interruption.
4. `pause` checks the stop barrier, snapshots workspaces and stores PAUSED.
   For each stopped unfinished task, run `title --task T1` and set its title
   to the returned [SUB] Paused value. Already accepted tasks retain Complete.
   Run ordinary pause preparation: refresh core Git/evidence/checklist and render
   or validate READY. Do not overwrite the embedded state.
5. New main `start` claims a new epoch, keeps completed artifacts, and dispatches
   **new** workers for unfinished tasks. ASSIGN carries previous checkpoint,
   result, review, preserved workspace and prior worker ID. Worker IDs may not
   be reused. Inherited untracked files remain part of the full delivery manifest.
   For app-created worktrees, use the same-directory fork route returned by
   dispatch. This also applies when the old main registered the checkout but
   paused before the first assignment. Same-main corrections still use `retry`.

If execution is unknown, leave STOPPING and Receipt: STALE. In uncertain
DISPATCHING, reconcile registration and actual app task identity before observing
termination. A failed app task creation is “not-started” only with direct failure evidence;
timeouts alone are insufficient. Do not create another worker.

## Failure recovery and manual fallback

- Duplicate received messages with identical ID/hash are no-ops. Stale epoch,
  attempt, instruction, mismatched sender or changed evidence is rejected.
- `recover-app --task T1 --input failure.json` releases only a pending reservation
  proven not started. It preserves the creation response/nonce and failure evidence
  as an immutable artifact before allowing a fresh reservation. Successful or
  ambiguous app creation must be reconciled with its existing actual task instead.
- A completed commit whose receipt write was interrupted requires explicit
  `recover-commit --commit SHA --evidence <inspection>`; it verifies clean task
  HEAD, ancestry, source scope, result and checks. Never blindly recommit.
- Integration checks whether the result commit is already an ancestor before
  merging. Repeating after a missing receipt update records existing integration.
  Conflicts preserve files and branches; resolve under normal rules or abort
  that merge, then revalidate. No automatic destructive rollback.
- A crash can leave the receipt lock. Inspect the exact operation/worker/process
  evidence and stop all possible writers. Only then remove that single verified
  lock file and inspect Git plus receipt before an explicit recovery action.
  No timestamp-based automatic lock theft or automatic app-restart recovery.
- Select manual mode explicitly before approval when app task creation or exact
  workspace targeting is unavailable but app read/message tools are usable. Do not
  rewrite an approved running plan's mode. A mid-run transport failure requires
  pause and explicit recovery of actual task identities before proceeding.
  Manual mode uses the same prepare/approve/claim/dispatch/hello/bind sequence.
  Print registration and execution prompts for the user to copy into newly
  created Codex app tasks in the exact assigned workspace. Automatic and manual
  modes both use independent app sessions, never native workers. Bind actual
  threadId/hostId values only after registration.
  Wait for the registration-only turn to finish before posting the execution
  packet as a new turn. Once the user reports completion, inspect each task's real turn status with
  available app read/wait tools and the result artifacts; never mark PASS solely
  from “all done.” Missing read/status capabilities keep verification blocked.
- No automatic CLI/Claude fallback. No session deletion is required: old tasks
  remain historical evidence and receive no resumed source work.

## Existing receipts

v7/v8 identify receipt formats, not installed skill releases. New parallel plans
must record `execution_backend: app-threads` and `max_parallel`. Old v8 plans
without a backend remain readable for inspection and stop/checkpoint recovery;
prepare/approve/claim/dispatch/retry, source execution and integration/finish
reject that ambiguity.
Never relabel an approved or live old plan as app-threads. Stop the old execution
using its original runtime and preserve its receipt/artifacts before explicitly
preparing a replacement app-session plan. An unfinished old run is not discarded
or automatically migrated; report the required recovery when it blocks a start.

## Worker display and retained tasks

Titles follow `[SUB] Working/Paused/Complete - <Project scope> - S1 - <Task goal>`.
S1/S2/S3 follow immutable task order, independently of the parent stage ID.
For the same logical task's second worker use S1 R2; keep S1 and increment R
only when attempt changes. Same-worker follow-up keeps the attempt label.
Scope `.` displays as Repository root; separators are ASCII hyphens.
The helper's `title` action is read-only and produces title metadata, not an
app mutation. Actual title calls and verification are the main/worker's duty.

Titles are display only. Route messages and later title updates with the
recorded actual worker ID. A worker never labels itself Complete on RESULT:
main review must accept it first. On a title tool failure, retry once and
report the remaining failure, preserving the verified code and integration state.
Keep completed and paused worker tasks visible in history. There is no automatic
archive step, archive retry, or archive failure workflow. Worktree cleanup has
its own authorization and does not alter task retention.

## Review hardening

- Scope inspection includes the index and both rename paths, even when working
  files match HEAD. Directory input hashes describe existing content; staging a
  deletion must not change validation evidence.
- A reviewed writer with no source changes records the existing baseline with
  status NO_CHANGES instead of creating an empty commit. It still passes the
  normal integrated/finish gates.
- Internal merge messages follow the repository commit hook format. Monorepo
  source messages may include the required Affected-projects footer; merge
  messages retain that footer.
- Finish rechecks parent cleanliness after integration commands. A command's
  zero exit code cannot hide changes outside its declared inputs.
- If a managed Start response is lost, the unresolved intent blocks pause,
  reclaim and the affected worker's redispatch/retry. After observing every
  worker turn stopped, identify the exact harness-issued RunId from its original
  launch evidence and stop it. Run recover-check-start with an input JSON
  containing intent_id, run_id and evidence. Use run_id=null only when direct
  evidence proves that no process was launched; a timeout alone is insufficient.
  Never delete the intent or resolve it merely because time passed.
- A new attempt cannot reuse any retired worker from the same run. Repeating an
  identical terminal observation is a no-op; it cannot replace a checkpoint's
  workspace snapshot. Paused/completed checkpoints reject new terminal writes.
When an earlier staged change has been reverted in the final working tree, the
delivery manifest excludes that cancelled change. The index still participates in
ownership checks and is synchronized only for owned paths during approved commit
preparation. This permits NO_CHANGES without retaining an obsolete staged result.
Legacy process records without task_id match canonical worktree paths,
including slash and letter-case variants, before their live status is checked.
