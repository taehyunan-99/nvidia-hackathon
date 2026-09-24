# Direct notifications and optional tool waiting

## Supported boundary (verified 2026-09-15)

[App Server](https://learn.chatgpt.com/docs/app-server) documents streaming
`turn/completed`, item completion and token-usage events on an initialized client
transport. That does not expose an event subscription through every desktop tool.
The callable `send_message_to_thread` tool provides a separate supported route:
a worker can send a follow-up prompt directly to the actual main task. This
resumes an idle main without an event subscription or open collector. New plans
default to `notification_mode:direct`. Preserve existing approved plans; do not
rewrite their waiting mode during execution. `tools` retains the collector below,
and `user` retains explicit manual resumption. Do not add a heartbeat, service,
scheduler or direct App Server connection to reduce token use.

## Direct notification procedure

1. Before dispatch, record the actual main task identity and host evidence.
   Retain the run, controller epoch, assignment and each original execution turn
   identity. Dispatch includes the direct notification instructions. Once all
   currently available work is assigned and the main has no action to perform,
   end its turn. Leave the run ACTIVE and retain controller ownership; do not
   pause, claim again or send a stop request merely to make the main idle.
2. The worker finishes commands and managed processes, then emits an immutable
   RESULT using the existing helper. QUESTION/BLOCKED and a requested stop's
   CHECKPOINT also need timely notification. Use `notify` with the emitted
   reference to obtain validated `send_message_to_thread` arguments, send those
   arguments through the actual app tool, and end the worker turn immediately.
   Do not send ordinary ACK/progress messages to wake the main. The worker never
   edits the parent's receipt, accepts its own work or grants Git authority.
   If workspace validation itself fails, a still-bound direct-mode worker may
   publish a BLOCKED diagnostic and package its notification without passing that
   same workspace check again. Run/worker/epoch/attempt/instruction and live-phase
   checks still apply. This exception permits immutable report artifacts only;
   source edits, checks, RESULT creation and main result acceptance keep their
   workspace validation. It also permits a BLOCKED report during STOPPING when a
   normal snapshot-based checkpoint cannot be produced.
3. On wake, inspect the current receipt and actual app sender evidence. Feed the
   immutable report into existing `receive`; it validates the bound worker,
   run/epoch/attempt/instruction and assignment, verifies the artifact hash, and
   deduplicates its message ID. A late or duplicate prompt does not authorize a
   second review, retry or integration. A notice for a retired main/attempt is
   stale evidence, not an instruction to reclaim or modify the current run.
4. A sender is normally still in its execution turn when its notification reaches
   the main. Confirm the **original execution turn**, asynchronous commands and
   managed processes have actually ended using fresh app/harness observations.
   A brief bounded `wait_threads` for this final tail is allowed; a report alone
   never supplies terminal evidence. If termination remains unknown, leave the
   result unintegrated and report the specific recovery need. Never infer it from
   a notification timestamp, an earlier registration turn or elapsed time.
5. Handle questions/failures promptly. For ordinary results, receive the reports
   and return to idle while other workers are executing. Review normal results
   together when the batch is ready, then use the existing source/input checks
   and reviewed Git integration barriers. Refilling a slot or starting another
   approved wave remains a main action under the same plan limits.

This is per-worker delivery: five workers can send five normal completion
prompts. Reports arriving while the main is active may be handled within that
turn; do not assume exactly one wake per batch or guaranteed queuing semantics.
Deduplication prevents repeated state transitions, not token consumption from
receiving the same prompt again. Do not add an ad hoc cross-worker election or
mutable completion counter to suppress these notifications.

There is no independent failure watcher. A worker that crashes, is stopped, or
loses transport before notifying cannot guarantee a main wake. If a send fails
or its outcome is ambiguous, preserve the report and app evidence for manual
recovery; do not repeatedly resend or claim delivery without a successful result.
On user resumption, reconcile actual app state and retained artifacts before
choosing further action. This fallback does not require a new approval for
routine recovery already inside the approved scope.

### Real app transport verification

On 2026-09-15 receiver `01a0a352-8650-7863-a33a-a520e7c1e460` ended its initial
turn `01a0a352-8b37-75c0-bf2c-770e1d55168e` at Unix time 1789446515 and was idle
for 86 seconds. Sender `01a0a353-99ad-7b82-b22d-78cc964fb721` then sent event
`notify-probe-20260915-01` twice with the supported app tool. Receiver turn
`01a0a354-3adb-77b3-8d92-d1ebd469d1ed` started at 1789446601 and ended at
1789446620. It accepted the first event while the sender was `inProgress` and
recognized the second as a duplicate in the same active receiver turn.
The sender's execution turn `01a0a353-9e8a-7a93-b065-239ae9aa9160` ended later,
at 1789446646. This verifies idle resumption and demonstrates why receiving a
notification cannot prove sender termination. It does not establish an
exactly-once transport guarantee, unattended crash recovery or token savings.

## Explicit tool-wait procedure (`notification_mode:tools`)

The optional collector runs inside the main's existing `functions.exec` tool
cell, invokes the supported wait tool and saves visible cursor checkpoints.
It is an open tool wait, not an idle main or independent notification service.

1. Finish identity binding and send the approved assignment. Identify each
   **original execution turn ID** with app evidence. Do not use the earlier
   registration turn or a later reporting follow-up. When an execution finishes
   before observation, use read_thread to locate the actual assignment turn.
2. Save a `wait-begin --input` request with actual task IDs/turn IDs, a bounded
   absolute Unix deadline in milliseconds, and the observation reference:

   ```json
   {"turns":{"T1":"actual-execution-turn-1","T2":"actual-execution-turn-2"},
    "deadline_ms":1789444800000,"evidence":"actual app turn-identification evidence",
    "mode":"tools","review_on":"batch"}
   ```

   Replace the example deadline with a future bound appropriate to the approved
   work. Deadline expiry requests main attention; it does not stop workers.
   Use the normal project-root/app/revision/controller/epoch arguments. The helper
   reuses run ID, plan hash, bound app IDs/hosts, attempts and controller epoch.
3. Run `wait-script --project-root <project> --app` from the actual main. Execute
   its generated JavaScript in functions.exec. The collector absorbs ordinary
   completions and progress, reuses opaque cursors and rotates groups of at most
   eight with waits no longer than 50 seconds. It returns when the batch needs
   review, an urgent condition occurs, the user interrupts, or the bound expires.
4. If functions.exec yields a running cell ID, resume **that same cell** with
   functions.wait within host limits. Do not start another collector, interpret
   every ordinary completion, poll timeoutMs:0, reread unchanged task details, or
   narrate unchanged waits. Native waiting is different from model sampling.
   Transport yields can still require lightweight model/tool continuation; this
   fallback does not claim a completely idle model or zero token use.
5. On `ready`, read the completed execution results once and perform existing
   source review, input-hash checks, exact turn/command completion and managed
   process checks. A completion candidate never sets VERIFIED/INTEGRATED or
   authorizes Git changes. On `attention`, inspect only the named problem first.
6. On disconnect or a lost checkpoint response, reconcile the actual command and
   inspect the latest receipt. A new wait-begin may replace the collector using
   the same verified original turn IDs and fresh snapshots. The old checkpoint is
   preserved as evidence; stale batch ID/revision/epoch writes fail. Never infer
   termination from elapsed time or missing events.

`wait_batch` is the visible resume checkpoint in HANDOFF.md, not another task
list. The run remains ACTIVE. Duplicate completion candidates are retained once;
late reports from other turns require explicit resolution. QUESTION/BLOCKED
artifacts matching the current identity cause attention at the next native return
(bounded by the wait interval); app approval/failure signals return earlier.
This is bounded event waiting, not an instantaneous push notification guarantee.

## Review timing and explicit manual idle

Within the collector, default to `review_on:batch`. Approved tasks waiting for a slot are dispatched in
the next wave after batch review. Use `review_on:first` only when early review or
refilling capacity materially helps the actual workflow; retain the reason in
the request evidence. It changes review timing, not scope/model/Git authority.

If the user explicitly chooses `notification_mode:user`, use `mode:user`
and record that choice in evidence. The main may end its turn while workers and
the run stay ACTIVE. Explain that the user must resume the same main task; no
automatic wake is installed. On return, inspect the retained checkpoint and use
fresh app observations before a new collector. Do not claim, pause, stop workers,
or transfer controller ownership merely because the main was idle.

## Measurement

[Pricing](https://learn.chatgpt.com/docs/pricing) describes tokens read/written,
including prompts, history and tool results, with separate input/cache/output
rates. Do not multiply waiting seconds by a token price. In direct mode the main
does not hold an execution cell open while idle; each delivered notification and
the resulting validation/review can still incur model tokens. No controlled
token reduction has been measured for this mode.

The 2026-09-15 local replay sent five ordinary completions through five app-tool
calls and returned one model-visible batch result; a per-completion return would
produce five. Duplicate/progress, pre-subscription completion, wrong-turn,
failure/approval, disconnect, deadline and checkpoint races have local tests.
This measures callback/return counts, not a measured billing reduction.
The same collector was also run read-only against the five completed real app
tasks: five actual wait_threads calls produced one final `ready` return. No new
worker model turn or receipt mutation was needed for that check.

The earlier live run's five-worker execution window (129 seconds) contained four
main `token_usage_record` entries and three literal status-tool call sites in the
main's tool scripts. The two-worker window (886 seconds) contained 26 usage
entries and 13 such call sites. These windows also include implementation and
review; looped tool invocations can exceed literal call sites. They are not a
controlled before/after cost experiment. Do not infer savings percentages from
them. Preserve input, cached-input and output metrics separately if reporting
actual usage; a tool wait alone is not another model generation.
