# Standalone runtime

This repository copy keeps the receipt, evidence, identity, scope and termination checks from the supplied Handoff skill.

## Requirements and authority

Python 3.11+ and Git are required. Parallel transport additionally needs the Codex desktop app tools and an explicit request for the concrete app tasks. Claude supports sequential receipts; it does not emulate those app tools.
Use the actual interpreter path in command checks. Never assume a user-specific Python installation.
The committed baseline, actual app identity, disjoint write scope and independent verification conditions still apply. Installing the skill does not create sessions or authorize commits.

## Worktree registration

`../scripts/worktree_guard.py` verifies linked checkout membership, shared Git directory, exact parent branch/baseline, clean child, distinct task branch and persisted run/thread/host ownership.
It records ownership before creating a branch so an interrupted registration can be reconciled. It never adopts an unrelated branch, deletes worktrees, resets files or updates main.
Manual worktrees require an explicitly selected path, a detached checkout at the pinned SHA, and the same registration. Main is the team PR base; internal task branches may use `feat/name` or scoped legacy names.

## Command supervision

`../scripts/managed_check.py` stores request, status and output under the repository common Git directory in `handoff-processes/<RunId>/`.
Start launches a separate supervisor; Status reads its durable state; Stop requests termination and waits for evidence. Unknown state blocks integration and pause completion. A lost Start reply still requires the existing explicit intent reconciliation.
On macOS/Linux, a dedicated process-group launcher holds its PGID until cleanup. On Windows, a suspended process is attached to a kill-on-close Job Object before resuming; its children remain in that job.
Commands must stay in the managed process tree: no daemonizing, POSIX setsid/double-fork, WMI launch, scheduler/service launch or other detached work. These are cooperative validation commands, not an adversarial sandbox. Observe any separately authorized service with its own lifecycle evidence.

Implementation references: [Python subprocess](https://docs.python.org/3/library/subprocess.html), [Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

## Verification boundary

The copied regression suite uses owned temporary repositories instead of company hooks or external safety scripts. Run `python -m unittest discover -s .agents/skills/handoff/tests -p 'test_*.py'` from the repository root.
Local macOS execution can check receipts, real worktrees, timeout/stop, child process cleanup and integration recovery. Windows code requires execution on Windows to confirm native behavior. Actual Codex app dispatch is not proven by simulated tool evidence in unit tests.
