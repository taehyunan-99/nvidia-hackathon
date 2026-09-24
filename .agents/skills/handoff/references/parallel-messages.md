# Parallel message contract

Use the helper to generate headers and snapshots. Keep prose self-contained:
the next main/worker may have none of the previous conversation. File references
must be absolute, and evidence references contain `path` and `sha256`.

## Plan input

The following is a skeleton; replace paths, actual baseline and checks before
prepare. Use approved available host model names and tool reasoning values
(`low` for the user-facing Sol Light). Model policy remains SKILL.md's policy.

~~~json
{
  "mode": "auto",
  "execution_backend": "app-threads",
  "session_policy": "one-task-one-retry",
  "notification_mode": "direct",
  "max_parallel": 2,
  "stage_id": "S1",
  "goal": "Exact selected stage outcome",
  "parent_worktree": "C:/worktrees/nvidia-hackathon/feature--repo--example",
  "parent_branch": "feature/repo/example",
  "parent_commit": "FULL_40_CHARACTER_SHA",
  "rework_limit": 1,
  "integration_checks": [
    {"id": "integration", "kind": "command", "argv": ["node.exe", "tests/integration.mjs"], "cwd": ".", "timeout_seconds": 300}
  ],
  "tasks": [
    {
      "id": "T1", "goal": "A specific independent outcome",
      "context": ["Decisions, constraints, contracts and precise source references"],
      "write_paths": ["src/a", "tests/a"],
      "input_paths": ["src/a", "tests/a", "package.json"],
      "worktree": "C:/worktrees/nvidia-hackathon/feature--repo--example-a",
      "branch": "feature/repo/example-a",
      "model": "gpt-5.6-sol", "reasoning": "medium", "depends_on": [],
      "criteria": [{"id": "C1", "description": "Observable behavior", "checks": ["unit"]}],
      "checks": [{"id": "unit", "kind": "command", "argv": ["node.exe", "tests/a/test.mjs"], "cwd": ".", "timeout_seconds": 120}]
    }
  ]
}
~~~

Add a second independent task with different write paths and worktree. At least
two tasks are required. Paths are literal repository-relative POSIX paths, never
globs or `.`; a check's cwd may be `.`. Read-only tasks use write_paths=[].
For source-independent human checks use
`{"id":"review","kind":"inspection","instruction":"What must be inspected"}`;
run-checks receives a map from that ID to immutable evidence reference and note.
An inspection without evidence stays UNVERIFIED.

### App-created worktrees

For automatic new writers add `app_project` to the plan:

~~~json
{"project_id":"actual-list-projects-ID","host_id":"actual-host-ID","path":"C:/path/to/saved-parent-project"}
~~~

Set each new writer's `worktree` to JSON `null`; retain its approved task branch.
The saved parent project may serve any number of independent tasks; concurrency
is still bounded by max_parallel. Branches, write paths and input dependencies
must be independent. Creation uses the full approved parent_commit as its ref.
Do not hash a guessed child path into the plan. `reserve-app` records a nonce and
pending creation; `app-hello` reports the actual cwd Git root, HEAD and
CODEX_THREAD_ID without editing source. Pending creation blocks pause, integration
and another reservation for that role until its original result is reconciled.
`record-app` durably stores the immediate creation tool response:
`{"id":"returned-ID","id_kind":"clientThreadId","host_id":"actual-host","reference":"actual-tool-result"}`.
Use `id_kind:"threadId"` only when the tool returned an actual thread ID.
It never binds a clientThreadId as an execution identity.

After reading the hello from the actual task and observing its registration turn
completed, pass this input to `register-app`:

~~~json
{"hello":{"path":"absolute-hello.json","sha256":"actual-hash"},
 "thread_id":"actual-threadId","host_id":"actual-hostId",
 "creation_reference":"actual create/list/read app result reference",
 "terminal":{"tool":"wait_threads","status":"completed","turn_id":"actual-registration-turn",
             "reference":"actual terminal app result reference"}}
~~~

For a direct creation failure proving no task started, `recover-app` accepts:

~~~json
{"nonce":"reserved-nonce","tool":"create_thread","status":"not-started",
 "reference":"actual explicit creation failure result"}
~~~

Never use this for a timeout or ambiguous response. It archives the pending
creation and failure evidence before releasing the reservation. In STOPPING,
successful setup still uses `register-app` after the actual registration turn
ends; source assignment remains blocked until a later claim.

The runtime `app_creation` stores nonce, controller_epoch, status, actual worktree, thread_id,
host_id, app evidence and safety-helper registration. `spec` resolves that runtime
path for checks/assignment/review/integration without mutating the approved plan.
The subsequent ASSIGN/hello/bind flow binds the same task on its first attempt
under the creating main. A new main or replacement attempt uses dispatch's
`registration_fork_thread_id` with a same-directory fork, then verifies and binds
the new actual task. The retained worktree needs no saved child project.
Registration-turn completion never substitutes for execution-turn completion.

## Envelope and meanings

New prepare proposals default to `notification_mode:direct`. After publishing a
RESULT, actionable QUESTION/BLOCKED UPDATE or stop CHECKPOINT, the worker runs
`notify --input <emit-reference.json>` with its current identity arguments. The
output is the exact `send_message_to_thread` argument object (`threadId`, `prompt`)
for the current main. The message includes run/task/worker/epoch/attempt/instruction,
message_id and the absolute evidence reference with SHA256. It is a wake hint;
main verifies the source app response and uses the existing `receive` command to
deduplicate and validate it. The helper never writes parent execution state or
claims sender turn completion. ACK/routine progress do not wake the main.
Direct-mode BLOCKED diagnostics can report a broken workspace while retaining
the current execution identity checks, including during STOPPING. Notification
packaging is also report-only and does not require a healthy workspace. Neither
operation permits source work or turns a diagnostic into a verified result.

The main remains ACTIVE with the same controller epoch while its turn is idle.
It verifies original turn/command/process termination after waking, then ends its
turn again if other results are pending. Explicit `tools`/`user` notification modes
and already approved plans retain the procedures in parallel-wait.md. Direct
notification is per worker; five results may send five prompts, while main source
review can still happen once after all results arrive.

Every message has schema, message_id, type, run_id, task_id, attempt,
instruction_revision, controller_epoch, reply_to, sender, created_at and payload.
Main and worker IDs are actual execution identities; task_id is the logical work.
For app-threads, worker_id and worker_thread_id both contain the verified actual
app threadId; worker_host_id contains its actual hostId. The old field name is
retained for receipt compatibility, not for native subagent handles. Neither a
clientThreadId nor a display title is a bound execution identity.

| Type | Author | Required content / action |
| --- | --- | --- |
| ASSIGN | Main/dispatch | Full task spec, starting workspace snapshot, previous checkpoint/result/review/worker |
| ACK | Worker/emit | Understanding, first action; snapshot must still match assignment |
| UPDATE | Worker/emit | CHECKPOINT/BLOCKED/QUESTION, summary, remaining, optional question/process RunIds |
| DECISION | Main/retry | Decision, authority, updated instruction revision and current context |
| RESULT | Worker/emit | Outcome, decisions, limitations, no remaining work, criteria/checks, whole delivery manifest |
| REVIEW | Main/review and retry | Accept or concrete reproduction, desired correction and re-verification |
| STOP | Main/request-stop | Stop source writes, stop managed processes, emit CHECKPOINT |
| CHECKPOINT | Worker/emit or main/checkpoint-main | Actual incomplete state, remaining work, decisions, limitations, processes and snapshots; main recovery identifies source=main-observation |

The helper derives RESULT/CHECKPOINT edited_this_attempt from content changes
since ASSIGN. delivery_files covers all changes from the pinned baseline,
including inherited untracked files. validation_snapshot hashes declared inputs;
workspace_snapshot additionally captures HEAD, branch, index and dirty paths.
Staging may change workspace state without changing validation inputs.

## Worker notes inputs

Pass notes via `--input notes.json`; the helper adds identity and generated data.

~~~json
{"understanding":"What I will deliver and its boundaries","first_action":"Concrete first inspection"}
~~~

~~~json
{"kind":"QUESTION","summary":"What is known and the exact obstacle","remaining":["Pending action"],"question":"Decision needed, options and recommendation","processes":[]}
~~~

~~~json
{"summary":"Actual outcome or preserved incomplete state","decisions":["Decision and reason"],"limitations":[],"remaining":[],"processes":[]}
~~~

The last template is RESULT (remaining must be empty, provide --checks reference)
or CHECKPOINT (state what is unfinished; checks may be partial or absent).
Use `emit --type ACK|UPDATE|RESULT|CHECKPOINT --task T1 --worker ACTUAL_ID
--epoch E --attempt A --instruction-revision I`.
Do not count the worker's self-assessment as independent main acceptance.

## Main observations

`observe --input observation.json` requires a fresh actual execution observation:

~~~json
{"worker_id":"actual-worker-id","attempt":1,"instruction_revision":1,"controller_epoch":1,
 "turn_id":"execution-turn-reference","status":"completed","tool":"wait_threads",
 "observed_at":"2026-09-14T12:00:00+09:00","reference":"actual tool result reference"}
~~~

Status is completed/interrupted/failed. not-started with worker_id=null is allowed
only for a directly evidenced dispatch failure. For app-threads the tool must be read_thread, wait_threads or dispatch-error.
Native list_agents/interrupt_agent observations are accepted only when reading
or stopping legacy runs; they never prove a new app sub-session has stopped.
A previous registration turn is not evidence that the work turn ended.

`process --input process.json` records a managed process:

~~~json
{"run_id":"harness-issued-RunId","status":"Stopped","observed_at":"2026-09-14T12:00:00+09:00","reference":"managed-process Status/Stop result"}
~~~

Review evidence must explain what was inspected, how success criteria were
checked, any reproduction, the needed correction, and the next verification.
State logs contain IDs; user-facing summaries explain outcomes in plain Korean.

## Display title

ASSIGN's generated execution prompt also carries sub_title. Apply it before ACK
and include any unresolved title failure in the worker's report. Main acceptance
and pause use the helper's read-only title action plus set_thread_title.
Display number S1/S2 is the immutable task-list ordinal; R2/R3 is attempt.
Neither is a routing identity. RESULT is still only a review candidate and must
not cause a worker to claim [SUB] Complete. Never archive a worker automatically.
