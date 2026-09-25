---
name: handoff
description: "명시 호출된 init, next, done, pause, start, inspect로 검증된 작업을 세션 사이에 인계한다. 별도 Codex 앱 작업을 명시 요청한 경우에만 병렬 인수인계를 운영한다."
---

# Handoff

## Repository portability

This copy uses bundled `scripts/worktree_guard.py` and `scripts/managed_check.py`; no company safety checkout is required. Read [runtime-portability.md](references/runtime-portability.md) before parallel execution.
Sequential handoff also works in Claude Code. When an app-title tool is unavailable, preserve and validate the receipt and report that title synchronization was unavailable; never invent a tool call or block the receipt solely on that UI feature. Parallel transport remains Codex-app-only and requires the explicit separate-task authorization below.
Resolve resources from this canonical skill folder, even when invoked through a Claude wrapper. Python 3.11+ is the team baseline. A committed Git baseline is required for parallel work; the empty initial repository is not ready for parallel execution yet.

Create an execution-ready cross-session receipt and resume it safely. Treat
durable project documents as design authority, repository state as factual
evidence, `docs/plan.md` as the long-term project plan, and `docs/HANDOFF.md`
as a compact cross-session receipt. The receipt never replaces the project plan.

## Local storage

Share this skill and its helpers through Git, but keep `docs/HANDOFF.md`,
`docs/HANDOFF.html`, `docs/HANDOFF.md.parallel.lock`, and `docs/handoff-runs/`
local and ignored. Never include these artifacts in commits or PRs. Team members
use their own clones; keep one current receipt per project scope and checkout,
with only one main session writing it. Ignoring files does not isolate concurrent
tasks in the same checkout.

Resume from the same local checkout. Git does not transfer the receipt or its
evidence to another clone, machine, or worktree; do not assume they exist there
or consume another person's receipt. Team-shared progress and decisions are
managed separately from this personal checkpoint.

## Parallel means separate app sessions

In this skill, orchestration means a main Codex desktop app session controlling
separate, user-visible Codex app sessions. Each sub-session is an independent app
task with its own actual threadId, hostId, conversation and assigned workspace.
The main creates or registers those sessions, sends instructions, reads their
status/results, requests stop, reviews their work and integrates accepted results.
`worker` in the helper's existing field/command names means this app sub-session.
It never means a `spawn_agent` child. Do not use `spawn_agent`, `followup_task`,
`send_message`, `list_agents` or `interrupt_agent` to create, identify, bind,
message, observe, stop or replace a Handoff worker. This transport restriction is
not a blanket ban on native subagents. When current host rules allow them, the
main or an app worker may autonomously use native subagents for bounded internal
assistance when task size, independent subtasks or verification value justify the
coordination cost. This does not require a separate user instruction to use
subagents. The owning app session remains accountable for its assigned scope,
validates their work and termination, and reports only through the app-task and
evidence protocol. An internal subagent never receives a Handoff worker ID,
separate worktree ownership, receipt authority or a direct reporting route to the
main in place of its owning app session.
The only legacy exception is observing/stopping an existing old run with its
original runtime for recovery; it does not authorize new subagent execution.
Do not infer a three-session total limit from subagent slots. Planned task count
and the approved `max_parallel` concurrent app turns are separate quantities.

Creating separate app tasks needs an explicit user request covering those tasks;
invoking Handoff or approving generic parallelism alone does not supply it.
Reuse an existing explicit request for the same concrete sessions and scope.
A concrete user-requested set of independent app tasks is explicit app-task
creation, not agent-inferred internal decomposition, even when those tasks all
contribute to the current request. Do not reclassify it as an internal subtask
merely because the app sessions are coordinated by the same main session.
Check the current app tool rules before execution: a skill cannot override a
real host restriction on explicitly requested app-task creation. A general rule
that prefers native subagents for ordinary implicit decomposition does not cancel
the user's explicit request for these separate, user-visible app tasks. Treat it
as a conflict only when a higher-priority rule explicitly prohibits `create_thread`
for the requested app sessions, or when the required app tool/capability is absent.
In that case report the exact capability/authority gap and leave the plan
unstarted. Never silently substitute subagents or claim orchestration ran.
Read the app capability and workspace preflight in
[parallel-workflow.md](references/parallel-workflow.md) before proposing execution.
For new automatic writers, use the existing saved parent project in app worktree
mode, then register its actual checkout with the shared safety helper. Approve
the baseline and isolation conditions before creation; record the returned path
after verification. Handoff calls shared scripts directly without requiring the
task-workflow skill. Preserve already approved/running plans with their original
workspace protocol; do not migrate them during execution.
New plans default to `notification_mode:direct`: after dispatch, end the main
turn while the run remains ACTIVE. Workers send validated result or urgent report
references to the actual main with `send_message_to_thread`, then end their turn.
Follow [parallel-wait.md](references/parallel-wait.md) on each notification: reuse
message deduplication, verify actual sender and execution termination, and review
normal results together once the batch is ready. A notification may arrive before
its sender stops; it never authorizes Git by itself. Each worker can wake the main,
so do not promise one model wake per batch. Keep the collector and manual idle as
explicit `tools`/`user` alternatives; preserve existing plans' waiting mode. A lost
notice or a worker that stops before sending requires manual recovery.

New plans use **one session per bounded task, with at most one correction execution
in that session**. Registration and result reporting belong to that same task.
Freeze its goal, write scope and checks; do not append new requirements to an
existing worker. After review/integration, create a fresh app task from the current
approved parent commit for the next requirement. Pass a compact task packet and
file references, not old conversation history. Do not fork for new work: a fork
copies completed history. A same-directory fork is only an unfinished-task recovery
route, not a context reset. Preserve existing approved runs' lifetime policy.

## Use explicit commands

Accept these forms only:

- `$handoff start` — consume the scoped receipt in a fresh session, verify its
  state, and begin the first unfinished development stage.
- `$handoff init [next-work context]` — create the first normal receipt when
  a completed work unit was already committed before `docs/HANDOFF.md` existed.
- `$handoff pause` — checkpoint unfinished `ACTIVE` or `BLOCKED` development
  work for a later new session.
- `$handoff next [next-work context]` — before committing a completed work
  unit, write a local receipt for the next actual development stage and
  print only its model and reasoning recommendation.
- `$handoff done` — before committing a completed work unit with no known next
  stage, write and validate a final `COMPLETE` receipt with its result summary.
- `$handoff inspect` — inspect receipt readiness without mutation (`INSPECT`).

`$handoff` without one of these commands is not a mode selection. Ask the user
to choose `start`, `init`, `next`, `done`, `pause`, or `inspect`. Pre-existing
handoff-v2, handoff-v3, handoff-v4, handoff-v5, and handoff-v6 receipts remain readable.

`start` verifies the receipt and begins actual work directly; it never creates a
new receipt or a copyable prompt. Do not start a receipt whose work status is
`COMPLETE`.

For unfinished work, `pause` or `next` ends only after validating the receipt.
`next` and `done` must run before the outgoing work unit is committed; keep
their `HANDOFF.md` local and excluded from that commit and PR. `next` records a real next
development stage, while `done` records that no next stage is currently known.
The user selects the recommended model and reasoning when creating the new
session, then runs `$handoff start` after `next`.

## Select the project scope

Determine scope from the task before looking for a receipt. Prefer, in order:

1. the nearest explicit project root jointly supported by the current working
   directory, applicable instructions, manifests, relevant documentation, and
   the task's changed files;
2. the Git top-level when no narrower boundary is supported or the task
   intentionally spans sibling projects;
3. the current working directory when no Git repository exists.

After selecting that scope, use only that project's `docs/plan.md` and
`docs/HANDOFF.md`; never substitute documents from the Git root or an ancestor
project. An ancestor receipt is a candidate only when its recorded `Project scope` exactly matches
the selected scope. Never infer a boundary from a folder name alone or let a
monorepo-root receipt override supported project evidence. Ask once when two
candidates remain equally supported. Maintain one active receipt per selected
project scope and worktree.

## Preserve these invariants

- Preserve user changes and obey the closest `AGENTS.md` or `CLAUDE.md`.
- Use direct evidence only: current task context, source and test files, actual
  commands and results, Git status, branch, and HEAD.
- `docs/HANDOFF.md` is the sole current checkpoint. Sequential runs create no
  orchestration state. Approved Codex desktop parallel runs use only the visible
  embedded v8 state and immutable evidence described in
  [parallel-workflow.md](references/parallel-workflow.md); do not add a hidden scheduler.
- Receipt preparation and final review belong to the main. Parallel workers
  execute bounded development tasks and never prepare the main receipt.
- Sequential handoff does not create branches, worktrees or commits. The
  approved parallel protocol may create scoped child worktrees and let the main
  commit reviewed source and merge it into the parent task branch. These are
  internal implementation operations, never a handoff development goal.
- Push, PR and protected-branch merge remain separate user-owned delivery actions.
  Delivery actions must not appear as a goal, stage, first action, routing value,
  or next-session instruction. The validator rejects them in next-work fields.
- Treat `docs/plan.md` as read-only. Never create, edit, reorder, or move its
  items. Use it only as optional background; no citation, section, identifier,
  or matching entry is required in `HANDOFF.md`.
- Do not create separate app tasks, push, merge, deploy, delete, or broaden
  authority merely because Handoff was invoked. App task creation requires the
  explicit session request and permitted app tools described above.
- Keep durable decisions in their established documents. Link them from the
  receipt instead of copying their contents.
- Keep stable IDs when revising existing success criteria or stages. Clarify
  them, but never expand the goal or scope without an explicit user decision.

Record `Project scope` as a Git-top-level-relative POSIX path, or `.` for the
Git top-level or a non-Git project. Use separate status axes:

- Receipt: `READY | STALE | INVALID`
- Work: `ACTIVE | BLOCKED | COMPLETE`
- Success criterion or stage gate: `PASS | FAIL | UNVERIFIED`
- Documentation alignment: `ALIGNED | CONFLICT | UNVERIFIED | NOT_APPLICABLE`

`READY` means another session can continue safely, not that the work is
complete. A bounded, accurately recorded blocker may have
`Receipt: READY` and `Work status: BLOCKED`. Use `INVALID` when authority,
scope, or the first safe action cannot be determined. Use `COMPLETE` only when
every required global criterion has current `PASS` evidence and no unfinished
stage remains. A `COMPLETE` record must also have `Receipt: READY`; retain no
stages in that current receipt.

Treat one session as one meaningful feature, stage, or clear result. Prepare a
handoff when that result is complete, when the next stage changes scope, risk,
or recommended execution route, or when context exhaustion makes an accurate
mid-stage transfer necessary. Do not hand off after every small subtask. Ultra
parallelism, when justified, stays inside the selected stage and never starts a
later stage early.

### Keep the session title in sync

Treat a session-title change as a required user-visible postcondition. Call
`set_thread_title` on the current thread (omit `threadId`) for every successful
state transition; naming it in the response is not a substitute for the tool
call. Use these exact status prefixes:

- After receipt verification and before substantive `$handoff start` work:
  `Working - <Project scope> - <Goal>`.
- After a successful `$handoff pause`: `Paused - <Project scope> - <Goal>`.
- After a successful `$handoff init`, `$handoff next`, or `$handoff done`:
  `Complete - <Project scope> - <Goal>`.

Use a short, reader-friendly form of the selected-stage or completed-work
outcome for `Goal`; if it cannot be determined safely, omit the final
` - <Goal>` segment. Use only ASCII hyphens as separators; never use decorative
Unicode punctuation. When the recorded `Project scope` is `.`, display
`Repository root` in the title instead of the raw dot. Do not rename a task for
`$handoff inspect` and do not pin it.

Make the title call after the receipt update or validation required by that
transition, and before sending the terminal result to the user. If it fails,
retry once. If it still fails, report the title-update failure explicitly and
do not claim that the title changed; the receipt may remain valid, but the
session-state transition is incomplete.
### Parallel worker titles and preservation

Main titles keep the existing Working/Paused/Complete rule above. Worker titles
use `[SUB] Working|Paused|Complete - <Project scope> - S<number>[ R<attempt>] - <Task goal>`.
The immutable task order assigns S1, S2, ...; this is the worker's display number,
not the parent stage ID. Retain it when recreating that same logical task.
Omit R1 for the first worker, show R2/R3 for new attempts, and do not increment
it for same-worker instruction revisions. Display `Repository root` for scope
`.` and use ASCII hyphen separators. Identity and delivery always use actual
IDs, never a title or display number.

After bind, the generated worker prompt includes its Working title. The worker
sets its own title with `set_thread_title` (omit threadId) before ACK. The main
uses `parallel_handoff.py title --project-root <project> --app --task <id>` to
obtain the exact title and actual app thread_id for later title calls. Confirm
the tool result, and read the task when needed to verify the displayed title.
Apply Complete only after main review accepts the result (VERIFIED), even if
integration is still pending. RESULT alone must not trigger Complete.
Apply Paused after actual stop confirmation for an unfinished task; accepted
results retain Complete across main pause. A new worker starts as Working.
Title failure follows the existing one-retry/report rule; never roll back a
verified result or confuse title failure with code/integration failure.

Never automatically archive workers, retry archival, or add archive-specific
exception handling. Keep `[SUB] Complete` and `[SUB] Paused` tasks as history.
Worktree cleanup is a separate authorized lifecycle and does not archive tasks.

## Prepare the handoff

Apply these phases in order. Do not advance past a phase until its exit
conditions are satisfied or the exact blocker is recorded.

### Initialize the first handoff

Use `$handoff init [next-work context]` only when `docs/HANDOFF.md` is absent
and the current work unit was already completed and committed before Handoff
was used. It is the one-time entry path into the normal workflow; it creates a
standard handoff-v7 receipt, not an informal substitute document.

Inspect the current conversation, the completed commit, the working tree, and
the relevant source, tests, and project documents. This command alone may write
the five-line `작업 결과 요약` without an earlier `$handoff start`, but every claim
must have direct evidence from those sources. Do not guess a retrospective
summary. If the completed work or verification cannot be determined safely,
stop and name the missing evidence.

Record the supplied next-work context as the first actual development stage,
using all normal receipt, routing, checklist, and validation requirements. Do
not put commit, PR, merge, push, or branch creation in that stage. After
validation, apply the required `Complete` title update and tell the user the
receipt is saved locally for the next session in the same checkout. If a
scoped receipt already exists, reject `init` without changing files and use
`start`, `pause`, or `next` instead.

### Pause unfinished work

For `$handoff pause`, preserve the current unfinished stage rather than
inventing a new one. Capture the current branch or worktree, HEAD, and
working-tree state, and complete phases 1 through 7. A pause succeeds only
when the receipt is `READY`, the pause checklist passes, and the validator
accepts it. After a successful pause, apply the required `Paused` title update defined above. Derive `Goal` from the selected-stage outcome.

For `$handoff next`, record the next actual development unit only after the
current work is complete, its `작업 결과 요약` was saved by `$handoff start`, and
before its final commit. Preserve that five-line summary in the new
`HANDOFF.md`; do not infer, rewrite, or omit it. If the summary is missing,
stop and name the gap. Write the receipt on the outgoing branch, validate it,
and keep it locally for the next session in the same checkout;
do not create the commit, PR, merge, or branch. The receipt must name the next
code or product task, never a delivery action.
After a successful next, apply the required `Complete` title update defined above. Use the completed work-unit outcome as `Goal`; omit it rather than inventing one.

### Finalize without a next stage

For `$handoff done`, require the same completion evidence and saved five-line
`작업 결과 요약` as `$handoff next`, but do not invent or request a next-work
context. Write the receipt on the outgoing branch before its final commit,
validate it, and preserve the summary unchanged. Set `Work status: COMPLETE`,
use exactly `No remaining stages.` under `Execution plan`, omit `Next-stage
routing`, and set the top-level `First action` to exactly `No remaining work.`.
Do not create a new stage, model recommendation, or new-session setup. After a
successful `done`, apply the required `Complete` title update and tell the user
that `HANDOFF.md` is saved locally and excluded from commits. A later
`$handoff next [next-work context]` treats this completed receipt as its
outgoing work, preserves its summary and completion evidence, and replaces it
with a normal unfinished receipt. `$handoff start` then resumes that new receipt
unchanged. `$handoff start` without a preceding next-work receipt must continue
to reject `COMPLETE` work because there is no stage to begin.

### 1. Migrate factual work state

Read applicable instructions and inspect the selected project, Git snapshot,
current diffs, relevant source and tests, and commands actually run. Preserve
completed results only when evidence proves them. Record intended but unrun
checks as `UNVERIFIED`.

### 2. Reconcile durable documentation

Select only documents relevant to the objective, changed subsystem, changed
files, existing links, and documentation map. Include applicable PRDs,
architecture documents, accepted ADRs, roadmaps, specifications, and explicit
anti-pattern or project-rule documents.

For every material direction or constraint, record its authority, alignment,
evidence, and required action.

- Update the repository-designated mutable current-state authority only when
  the user explicitly confirmed the new direction in the current work, that
  document is its real authority, the change is unambiguous, and the edit is
  minimal. Depending on the project, this may be a PRD, architecture document,
  specification, roadmap, or another documented authority.
- Never update design documents merely because implementation drifted.
- Never rewrite an accepted ADR's history. Create or require a superseding ADR
  according to the project's convention.
- Never choose silently between conflicting authoritative documents.
- Treat an unrelated document conflict as out of scope.
- When a material conflict is bounded with a decision owner and first action,
  set work `BLOCKED` without inventing a direction. When authority or impact
  remains unknown, mark the receipt `INVALID`.
- Do not create a broad `PROJECT_CONTEXT.md` automatically. Record a missing
  durable decision as a required documentation action.

### 2b. Optionally consult the long-term project plan

If `<project-root>/docs/plan.md` exists and is readable, use it as read-only background
for the selected project, never the Git root's plan. It may use any structure or
language. Do not create, edit, validate, or require it for any handoff command.

A missing, malformed, stale, or unrelated plan never blocks `next`, `pause`,
`start`, or `inspect`. Do not copy a plan identifier into `HANDOFF.md` merely to
make the receipt valid. The user and the normal project workflow own plan changes.
### 3. Update global success criteria

Assign stable IDs `C1`, `C2`, and so on. For each criterion record whether it is
required, its `PASS | FAIL | UNVERIFIED` status, and direct evidence. Preserve
the original user outcome. Add a new criterion only for an explicit decision,
an applicable durable constraint, or a necessary verification of that outcome.

### 4. Review the remaining plan

Apply the lightweight Ultracode lens internally; do not invoke or depend on a
separate Ultracode skill.

- Remove work already proved complete and discard stale steps.
- Map every unfinished required criterion to at least one remaining stage.
- Record dependencies, stage boundaries, owned paths, and whether any stages
  are safely parallel. In the Codex desktop app, use the approved parallel
  protocol below when independent work warrants it or the user requests it.
- Assign at most one planned writer to a file at a time.
- Prefer executable verification and direct artifact inspection.
- Expose missing dependencies, unsafe authority, and documentation conflicts
  instead of hiding them in optimistic plan text.

Use `docs/plan.md` only when it adds useful context to the selected execution
stage. Do not record or require a `Plan item` field. If the plan and requested
work disagree, keep the plan unchanged and follow the current user direction or
ask for clarification when that direction is genuinely ambiguous.
Select an evidence-based route for the next unfinished stage. This route is an
execution hint, not a fixed command. First confirm that authority, scope,
completion conditions, and verification are usable; a stronger model must not
compensate for a missing execution contract.

Select the first `ACTIVE` or `BLOCKED` stage, or otherwise the first non-`PASS`
stage in execution-plan order. Do not skip ahead to a later stage.

- Exploration, mechanical edits, and clearly specified test execution with all
  decisions already settled: `Luna + Medium` or `Luna + High`. Use High for
  denser mechanical work. Do not route implementation, interpretation,
  synthesis, or unresolved decisions to Luna; never use Luna Extra High.
- Implementation with a settled design that requires precise contract, API,
  type, or multi-file fidelity: `Sol + Light`.
- Any implementation requiring judgment or integration: `Sol + Medium`.
- Context-heavy, read-heavy, very long, or specialized-domain work retains
  the separate `Terra + Medium`, `Terra + High`, or `Terra + Extra High` lane.
- Research, planning, architecture, and project foundations: `Astra + Medium`.
  Astra is active. Use `Astra + High` for conflicting directions, high-risk
  decisions, or designs that are difficult to reverse.
- Codex reasoning values in this policy are exactly `Light`, `Medium`, `High`,
  and `Extra High`; do not emit `Max`.
- Use Ultra only when at least two work items are actually independent, have
  non-overlapping write ownership, can be verified separately, and save more
  time than coordination costs. Ultra is a parallel execution topology, not a
  reasoning level and not the removed Ultracode runtime.

Prefer the lightest route that can complete the stage with direct
verification. Use same-repository observed evidence before generic benchmark
rankings, and escalate for the observed failure cause rather than stepping
mechanically through reasoning levels.

Name an observable condition that would require route escalation and an
evidence-producing checkpoint where the route should next be reviewed. Use
`Escalate when` in v7, naming the appropriate target and observable condition.
At Astra High, record the condition requiring renewed user direction or scope
review instead of inventing a higher route.

### 5. Create bounded stage gates

Use stable IDs `S1`, `S2`, and so on. Each remaining stage must name mapped
global criteria, outcome, owned scope, verification, and first executable
action.

Use exactly these six common gates:

1. `deliverable`
2. `scope`
3. `documentation`
4. `verification`
5. `evidence`
6. `next-input`

Add only one to three observable stage-specific criteria. A common gate may
pass with an explicit no-impact reason, but a `PASS` always requires evidence.
Do not mark a stage complete while a required gate is `FAIL` or `UNVERIFIED`.

### 6. Write the canonical receipt

Write or replace `<project-root>/docs/HANDOFF.md`; sequential receipt preparation writes no other state. Never modify `<project-root>/docs/plan.md`. Maintain one current receipt,
not a chronological diary. Use this required order and exact section names so
the validator can validate the document:

```md
# HANDOFF

Format: handoff-v7
Receipt: READY | STALE | INVALID
Work status: ACTIVE | BLOCKED | COMPLETE
Project scope: Git-relative POSIX path or .
Last verified: ISO 8601 timestamp with timezone
Baseline commit: commit or not-available
Branch or worktree: value
First action: exact executable action, blocker-resolution action, or `No remaining work.` for COMPLETE work

## Resume instructions
### 작업 결과 요약
## Strategic alignment
## Documentation alignment
## Global success criteria
## Plan review
## Execution plan
### S1 — Stage name
## Evidence
## State verification
## Risks and open questions
## Required context
## New-session prompt
```

The validator intentionally uses a strict schema. Use these exact table columns
in this order:

- Documentation alignment:
  `Topic or decision | Authority | Alignment | Action | Evidence`
- Global success criteria:
  `ID | Criterion | Required | Status | Evidence`
- Plan review:
  `Change | Previous | Revised | Reason | Documentation impact`
- Evidence: `ID | Kind | Result | Summary | Reference`
- Every stage: `Gate or criterion | Status | Evidence`

Use evidence IDs `E1`, `E2`, and so on. Evidence `Result` is exactly
`PASS | FAIL | UNVERIFIED`. A `PASS` or `ALIGNED` claim may reference only
`PASS` evidence. Use `yes | no` for a criterion's `Required` field. Include one
plan-review row even when the reviewed plan did not change, and state why.

For every newly prepared handoff-v7 or handoff-v8 receipt, finish `Resume instructions` with
this exact plain-language summary. It describes completed work from the session
that ran `$handoff start`; `$handoff next` preserves it unchanged.

```md
### 작업 결과 요약

- 한 줄 결과: 사용자 관점의 완료 결과
- 바뀐 점: 사용자나 운영 관점에서 달라진 점
- 이제 가능한 것: 이 작업으로 가능해진 일
- 확인한 내용: 정상 동작을 확인한 방법이나 범위
- 남은 사항: 아직 하지 않은 일 또는 다음 실제 개발 작업
```

Write this in clear Korean. Do not use criterion IDs, stage IDs, branch names,
file paths, internal abbreviations, or unexplained technical jargon. Translate
necessary technical detail into its user-visible effect. Do not write merely
`완료했습니다`.

Every stage heading is `### S1 — Stage name` and has exactly these metadata
lines before its table:

```md
State: PENDING | ACTIVE | BLOCKED | PASS
Maps to: comma-separated global criterion IDs
Outcome: observable stage outcome
Scope: owned paths or bounded responsibility
Verification: executable check or direct inspection
First action: exact executable action
```

The stage table contains the six common gate names exactly once and one to
three additional names prefixed with that stage ID, such as
`S1-render-invalid-input`. Escape a literal table-cell pipe as `\|`.

For unfinished work, include only the files, documents, and constraints needed
by the next session. If `docs/plan.md` was useful context, mention its relevant
heading or idea in free text; otherwise omit it. No plan identifier or plan
format is required. Use the selected non-`PASS` stage. `Goal` must equal that
stage's `Outcome`, `Change scope` must equal its `Scope`, and the top-level
`First action` must equal the selected stage's `First action`.
```md
### Next-stage routing

- Goal: observable next-stage outcome
- Completion condition: observable condition that makes the stage PASS
- Current stage: S1 — Stage name
- Change scope: exact selected-stage Scope
- Recommended model: Luna | Terra | Sol | Astra
- Recommended reasoning: Light | Medium | High | Extra High
- Use Ultra: yes | no
- Escalate when: observable escalation condition
- Next checkpoint: observable verification or decision boundary
```

Do not add a continuation decision. The receipt is sufficient for `$handoff
start`; delivery actions such as committing, opening or merging a PR, and
creating a branch stay outside this plan and routing block. The validator rejects
commit, push, PR, merge, and branch-creation language in next-work goals,
stage names, first actions, and all routing values.

When `Use Ultra` is `yes`, add this line immediately before the routing
heading:

```md
- Ultra evidence: E3
```

The referenced evidence must be `PASS`, and at least one referenced evidence
summary must begin `Ultra independence:` and directly prove two or more
independent work items, non-overlapping write ownership, and separate
verification. Omit `Ultra evidence` when `Use Ultra` is `no`.

Use only these model/reasoning combinations:
`Luna + Medium`, `Luna + High`, `Terra + Medium`,
`Terra + High`, `Terra + Extra High`, `Sol + Light`, `Sol + Medium`,
`Astra + Medium`, or `Astra + High`.
Do not use `Light` with Luna, Terra, or Astra, and never use `Max`.

All listed routes are active. Do not include availability or fallback fields.
Map `Light` to the host effort `low` and `Extra High` to `xhigh`.

A routing-less legacy `handoff-v2` receipt remains valid, and existing
`handoff-v3`, `handoff-v4`, `handoff-v5`, and `handoff-v6` receipts remain readable. Every
newly prepared sequential receipt uses `handoff-v7`; a parallel receipt uses `handoff-v8`; the validator requires its completion
checklist and `작업 결과 요약` before it can be `READY`. Before normal `start`
validation of an older receipt, read its raw routing fields and recompute the
current nine-field recommendation in memory from current evidence. Do not
rewrite the older receipt merely to migrate its format; the next `pause` or
`next` writes the v7 form. Treat any unsupported combination as invalid rather
than migrating it silently.
The route must be supported by the current stage, scope, risks, documentation,
and evidence. Do not add routing fields to top metadata or stage metadata. A
legacy `handoff-v2` receipt may lack this subsection, but every newly prepared
unfinished receipt includes the complete block.

For `ACTIVE` or `BLOCKED` work, include at least one remaining stage. For
`COMPLETE` work, set `First action` to exactly `No remaining work.`, use exactly
`No remaining stages.` under `Execution plan`, keep all required global criteria
at `PASS`, omit `Next-stage routing`, and use this exact marker under
`New-session prompt`:

```text
No copyable prompt: start reads this receipt directly.
```

Use that same exact marker for every unfinished handoff-v7 receipt. It is a
validator marker, not user-facing output: never display a fenced copyable
prompt. The model recommendation remains only in `Next-stage routing`.

Every newly prepared `pause`, `next`, or `done` receipt must put this exact final
subsection in `State verification`. Every item needs `PASS` evidence; a check
means that its state was accurately recorded, not that unfinished product work
has passed.

```md
### Handoff completion checklist

- repository-snapshot: PASS; E1
- work-state: PASS; E2
- documentation: PASS; E3
- evidence: PASS; E4
- resume-ready: PASS; E5
```

For unfinished work, use exactly those five item names. `State verification`
must also include exact `Branch or worktree` and `HEAD` lines matching the
metadata, plus a `Working tree` line. For completed work, replace
`resume-ready` with `completion`. The validator rejects a current `$handoff
start` receipt with a missing, non-PASS, unknown, or unsupported checklist
item. Every `handoff-v7` or `handoff-v8` receipt, including completed work, is rejected when this checklist is absent.
For root scope, the receipt line is `Receipt: docs/HANDOFF.md`. Keep evidence
IDs stable and link to the smallest relevant document section or path. Never
include raw transcripts, hidden instructions, unresolved placeholders,
invented values, secrets, or long command output.

### 7. Validate and present

Re-read the saved Markdown and confirm:

- the repository snapshot and documentation references are current;
- every required unfinished criterion maps to a remaining stage;
- every completed claim and `PASS` has evidence;
- each stage has all six common gates and one to three specific criteria;
- `State verification` cites current `PASS` evidence for every `READY` receipt
  and contains the complete, all-PASS handoff completion checklist;
- the first action is executable or resolves the exact blocker;
- for unfinished work, all twelve next-stage routing values are complete, match
  the selected stage, and use a permitted model/reasoning combination;
- Ultra is `yes` only for verified independent work with non-overlapping write
  ownership, matching `Ultra independence:` PASS evidence, and separate
  verification; the escalation condition and next checkpoint are observable;

Validate the receipt without generating a report:

```text
Windows: py -3 <skill-dir>/scripts/validate_handoff.py --project-root <project-root>
macOS/Linux: python3 <skill-dir>/scripts/validate_handoff.py --project-root <project-root>
```

After a successful unfinished `init`, `pause`, or `next`, print only `Recommended
new-session setup`: preferred model, reasoning, Use Ultra, escalation condition, and next checkpoint from
`Next-stage routing`. State that `HANDOFF.md` is saved locally and the new
session must use the same checkout. State that
the user should select the recommended model and reasoning before creating the
new session, then run `$handoff start`. Do not print a copyable prompt.
After a successful `done`, show the saved `작업 결과 요약`, state that validation
passed, and state that `HANDOFF.md` is saved locally and excluded from commits.
Do not print a model recommendation or new-session setup.
If validation fails, preserve both documents, name the exact gap, and do not
claim a successful handoff.
## Start the handoff

Read `docs/HANDOFF.md`, applicable instructions, required context, and cited
authoritative document sections. If `docs/plan.md` exists, consult it only as
non-blocking background. Verify the branch, HEAD, working tree, relevant
documents, and recorded evidence against current repository state.

After receipt verification succeeds, apply the required `Working` title update defined above before substantive work. Derive `Goal` from the selected stage outcome; omit it rather than inventing one.

- If the snapshot matches, re-evaluate the global criteria and remaining
  stages, including the recorded branch/worktree, HEAD, working tree, and completion checklist; restate the objective and first action, and
  start that action.
- Revalidate the recorded route against current repository evidence, available
  models, stage complexity, escalation conditions, and actual task
  independence. Prefer the recommendation when it still fits. Otherwise use
  the appropriate route under the current v7 policy and state why. Ignore
  historical v6 availability and fallback values when selecting today's route.
  Apply the host effort mapping above. The recommendation
  does not expand scope or authority, and changing it during `RESUME` does not
  rewrite an older receipt merely to change its format.
- If the same checkout retains the local `HANDOFF.md` but has a different HEAD
  because the outgoing work was committed, reviewed, merged, or branched,
  verify that transition against Git history, current files, and recorded
  evidence. Only after confirming the recorded scope and completion evidence
  still hold, treat it as an expected delivery transition and begin the recorded stage;
  never recreate commit, PR, merge, or branch work. Any other factual conflict
  makes the receipt `STALE`; report it without changing `docs/plan.md`.
- If a product or design decision changed or conflicts, stop implementation
  and resolve or request that decision.
- Never broaden the authority recorded in the receipt.
- When the recorded development stage reaches its completion condition, update
  the existing receipt's `### 작업 결과 요약` with the five required Korean
  fields. Then show the same `## 작업 결과 요약` to the user as the final result
  of this start-run task. Write for a reader who did not follow the session:
  explain what was done, what changed, what is now possible, how it was checked,
  and what remains. Do not substitute IDs, paths, branch names, or unexplained
  technical shorthand for that explanation. Keep the current `Working` title; this session may continue with additional work.
- Do not generate another receipt or copyable prompt during this start
  invocation. Sequential runs update only that summary. Parallel runs also
  maintain their embedded state and evidence through the helper; finish still
  requires the same plain-language Korean summary.

## Codex desktop parallel execution

Use [parallel-workflow.md](references/parallel-workflow.md) and
[parallel-messages.md](references/parallel-messages.md) whenever preparing or
resuming a parallel stage. These references override the sequential-only
restrictions above only within the approved parallel scope.

- During `next`/initial preparation, consider at least two independent tasks
  inside the selected stage, or evaluate the user's explicit parallel request.
  Explain dependencies that prevent parallelism. Writers must have disjoint
  write scopes and must not read another worker's changing outputs.
- Propose each task's goal, criteria, inputs, write ownership, worktree/branch,
  model and reasoning, main integration checks, internal Git authority, and
  rework limit. Reuse explicit authorization already supplied for that scope.
  The concrete plan must be approved, and separate app task creation explicitly
  requested, before creating sub-sessions.
- Use `handoff-v8` only when an embedded parallel plan exists. Preserve v7
  behavior for sequential work. A `Use Ultra: yes` recommendation alone does
  not create workers or establish permission.
- `start`: verify the current main workspace and plan first, claim once, create
  only explicitly requested unfinished app sub-sessions, and review retained
  reports before redispatch.
  A new main always creates new workers for unfinished work; it reuses their
  worktrees and evidence, never the previous worker session.
- `pause`: request stop, collect checkpoints, observe actual terminal turns and
  stop all managed processes. Save PAUSED only after this barrier; then refresh
  the ordinary snapshot/evidence/checklist and validate READY. Unknown execution
  leaves STOPPING and STALE. Do not claim a successful pause.
- `next` cannot bypass an unfinished run. `done` requires reviewed, integrated
  results and passing integration checks. An already COMPLETE run creates no workers.
- This runtime uses separate Codex desktop app tasks only. Do not substitute
  native subagents, Codex CLI, Claude, or an alternate backend for its workers
  or transport. Native subagents may still be selected autonomously inside the
  main or a worker under the scoped rule above; their owning app session remains
  responsible for scope, validation, termination and protocol reporting. When
  app task creation or exact workspace selection is unavailable, report the missing
  capability. Use user-created app sessions only under an explicitly selected
  manual protocol with the same IDs, artifacts and checks.

## Inspect without mutation

For a readiness-only request, inspect the receipt, repository
snapshot, documentation alignment, criteria-to-stage coverage, evidence, and
first action. Name exact gaps without modifying files.
