# Local-only execution enforcement

Use this mode when hosted CI is unavailable or prohibited. It provides repeatable local gates for cooperative developers and coding agents. It does not create a hostile-user security boundary: a local user can change hooks, policy, runner, repository contents, or evidence.

## 1. Confirm the execution topology

Record `local_only` independently of delivery form. A hosted SaaS can still use local-only validation. Do not create GitHub Actions, PR-required checks, hosted attestations, or deployment lanes merely because the product itself is hosted.

Inspect the repository's Git state, package and lock files, existing scripts, test timing, local mocks, C0/C1 map, and current hook manager. Prefer an existing versioned hook manager. If an existing monorepo hook/router already owns multi-ref handling, project routing, or platform command selection, use `existing_router` integration mode and do not scaffold, replace, modify, or install a Project Test Maker hook. Do not install dependencies or change `core.hooksPath`, scheduled tasks, or other persistent configuration without user authorization.

## 2. Create one policy and one gate

All agent, pre-commit, pre-push, post-merge, and scheduled triggers must call the same project-owned gate. Copy the verified `scripts/local_validation_gate.py` helper into a project-owned tools location when implementation is requested, or invoke the installed helper through a stable project wrapper.

The policy is JSON so the gate can validate it without third-party dependencies:

```json
{
  "schema_version": "1.1.0",
  "execution_topology": "local_only",
  "integration_mode": "standalone",
  "project_working_directory": ".",
  "policy_version": "2026-08-31.1",
  "ignore_change_patterns": ["docs/*"],
  "lanes": [
    {
      "id": "critical_auth",
      "triggers": ["worktree", "pre_push", "scheduled"],
      "command": ["npm", "run", "test:auth"],
      "inputs": ["src/auth/*", "tests/auth/*", "package.json", "package-lock.json"],
      "change_patterns": ["src/auth/*", "tests/auth/*", "package.json", "package-lock.json"],
      "criticality": "C0",
      "blocking": true,
      "timeout_seconds": 300,
      "budget_seconds": 120,
      "cache": true,
      "max_age_seconds": null,
      "fingerprint_env": ["NODE_ENV"],
      "toolchain": ["node=22.0.0", "npm=10.0.0"]
    }
  ]
}
```

Use Git-root-relative forward-slash patterns. Every `change_patterns` entry must also appear in `inputs`; otherwise a matching change could select a lane without invalidating its prior result. Include test and fixture files, lockfiles, build and validation configuration, local mock definitions, schemas, generators, and version files whenever they can affect the command.

`project_working_directory` is optional and defaults to `.`. It is an exact Git-root-relative directory used only as the command cwd and for relative command-executable resolution. It must exist inside the Git root and cannot contain traversal or glob syntax. Policy paths, changed files, impact evidence, Git inspection, and default evidence remain based at the Git root. A monorepo project can therefore match `projects/report-automation/src/*` while running its command from `projects/report-automation`.

`integration_mode` is `standalone` by default. Set it to `existing_router` only when the repository's current hook/router remains the pre-push owner. That mode refuses `scaffold-hook`.

Commands are argv arrays and run without a shell. Put pipes, redirection, environment setup, or multi-command behavior in a reviewed project script and call that script as one argv command. Never embed secrets in commands, policy, or reports. `fingerprint_env` hashes declared values into the fingerprint but does not store the raw values in evidence.

### Generate a reviewed policy

Do not infer commands, criticality, or cache safety from filenames. First write a reviewed lane-plan JSON containing `policy_version`, `ignore_change_patterns`, and `lanes`, plus optional evidence-backed `impact_rules`, while omitting the fixed schema and topology fields. Then generate a normalized policy:

```powershell
python <skill-folder>/scripts/local_validation_admin.py generate-policy lane-plan.json validation-policy.json --repo .
```

The command adds the fixed `schema_version` and `local_only` topology, supplies default standalone integration and Git-root command cwd when omitted, validates every lane, writes atomically, and refuses to overwrite an existing policy unless `--force` is explicit.

### Existing monorepo router contract

For repository-local placement, read [repo-local-adoption.md](repo-local-adoption.md) before generating a contract.

When `integration_mode` is `existing_router`, generate a route contract instead of a hook:

```powershell
python <skill-folder>/scripts/local_validation_admin.py create-router-contract projects/example/validation-policy.json projects/example/router-contract.json --repo . --route-id example --gate projects/example/tools/local_validation_gate.py
```

The contract records a Git-root path basis, project command cwd, current policy digest, an argv template for root-relative changed paths, evidence requirements, and the responsibility split. Creation writes only the requested contract file; it does not inspect push refs or modify the hook, router, route configuration, or Git settings. The existing router continues to own multi-ref processing, project routing, and platform command selection.

## 3. Selection and fallback

For a trigger, the gate:

1. selects matching changed-path lanes;
2. always selects trigger-applicable C0/C1 lanes;
3. selects all trigger-applicable blocking lanes when any changed path is unknown;
4. ignores a path only when it matches an explicit reviewed ignore pattern;
5. selects every scheduled lane for a scheduled run.

C0/C1 selection is non-heuristic. An exact PASS may be reused when its inputs did not change, but a critical lane is never omitted merely because a filename-based selector guessed it was unrelated.

### Evidence-backed impact rules

Add `impact_rules` only when repository evidence exists. Each rule uses this shape:

```json
{
  "id": "service_contract_dependents",
  "source": "dependency",
  "change_patterns": ["src/contracts/*"],
  "lane_ids": ["consumer_contracts"],
  "evidence": ["test-impact/dependencies.json"],
  "rationale": "The reviewed dependency export maps contract changes to consumer tests."
}
```

`source` is `dependency`, `coverage`, `history`, or `contract`. Evidence entries are exact repository files, must exist, and must appear in every selected lane's `inputs`. A matching change or a change to the evidence file itself adds the named lanes. Rules do not remove critical lanes, direct path matches, or unknown-impact fallback. Gate output reports `matched_impact_rules` and `selection_reasons` for calibration and review.

Calibrate rules against later full-run observations without executing tests:

```powershell
python <skill-folder>/scripts/local_validation_admin.py calibrate-impact validation-policy.json impact-observations.json --repo .
```

The observations file contains an `observations` array. Each item has `id`, `trigger`, `changed_files`, and `full_run_failed_lanes`. The report includes selected lanes, exact misses, and aggregate `faulty_lane_recall`. Any missed failed lane returns `FAIL` so the rule, lane inputs, or fallback can be corrected before claiming calibrated selection.

## 4. Fingerprints and evidence

The gate hashes the validated full policy, lane definition and command, matching file paths and contents, declared environment values, declared toolchain identity, Python/platform identity, and the gate implementation file. Evidence is stored atomically under `.git/project-test-maker/evidence/<lane>/<fingerprint>.json` by default.

The fingerprint also binds the Git-root path basis and project command working directory, resolves the lane's first command token from that command directory, and hashes the executable bytes when available. It hashes a fixed baseline of runtime/resolver, virtual-environment, locale/timezone, proxy/certificate, cloud-profile, container, and cluster environment values. Raw values are not stored. `toolchain` and `fingerprint_env` remain additive for project-specific identities that the baseline cannot know.

Only an exact, unexpired `PASS` record from the current evidence and gate schemas is reusable. Do not reuse `FAIL`, `BLOCKED`, `NOT_RUN`, timeout, corrupt, mismatched, or manually summarized results. Set `cache` to false for environment-sensitive checks that must execute each time. Use `max_age_seconds` only when time-dependent environment drift justifies it; content identity is the primary cache boundary.

The evidence cache prevents accidental duplicate work. It is not a cryptographic attestation because the same local user controls both the repository and evidence directory.

## 5. Agent completion gate

Add a project instruction only with the user's approval and match the repository's existing guidance structure. A concise contract is:

```markdown
Before reporting a coding task complete, run the project local validation command with the `worktree` trigger. Report FAIL, BLOCKED, timeout, and deferred lanes explicitly. Do not weaken, skip, or delete a valid failing test to obtain PASS.
```

Example invocation:

```powershell
python tools/local_validation_gate.py test-policy.json --repo . --trigger worktree
```

The after-task result and pre-push use the same fingerprint. If relevant contents are unchanged after commit, pre-push reports `REUSED` rather than running the command again.

## 6. Versioned Git hooks

Prefer a repository-owned `.githooks/` directory or the project's existing hook manager. Generate the adapter when the project uses the standard gate shape:

```powershell
python <skill-folder>/scripts/local_validation_admin.py scaffold-hook validation-policy.json --repo . --gate tools/local_validation_gate.py
```

This creates `.githooks/pre-push` by default, validates the policy and paths, and does not run `git config`. Existing files are preserved unless `--force` is explicit. Review the generated hook before separately requesting authorization to configure `core.hooksPath`.

Do not run `scaffold-hook` for `existing_router` mode; the administration CLI rejects it even with `--force`. Do not reproduce the owning router's multi-ref loop in Project Test Maker.

A minimal POSIX pre-push adapter for Git on Windows, macOS, or Linux has this shape; choose the actual Python command and paths from the project environment:

```sh
#!/bin/sh
set -eu

zero=0000000000000000000000000000000000000000
count=0
base=
head=

while read -r local_ref local_sha remote_ref remote_sha; do
  if [ "$local_sha" = "$zero" ]; then
    continue
  fi
  count=$((count + 1))
  base=$remote_sha
  head=$local_sha
done

if [ "$count" -eq 0 ]; then
  exit 0
fi
if [ "$count" -ne 1 ]; then
  echo "project-test-maker: push one non-deletion ref at a time" >&2
  exit 1
fi

repo=$(git rev-parse --show-toplevel)
python "$repo/tools/local_validation_gate.py" "$repo/test-policy.json" \
  --repo "$repo" --trigger pre_push --base "$base" --head "$head"
```

The v1 gate requires a clean worktree and the outgoing revision to equal checked-out `HEAD`. It marks a new remote ref as unknown impact and runs all applicable blocking lanes. Dirty, non-HEAD, missing-base, and unsupported multi-ref cases stop with remediation instead of testing the wrong content.

After reviewing the hook, configure it only with explicit authorization:

```powershell
git config core.hooksPath .githooks
```

State that `git push --no-verify` or configuration changes can bypass the hook.

## 7. Long local safety nets

Keep the pre-push critical path within its approved budget. Put broad local E2E, mutation, fuzz, full security scans, and full regressions in `post_merge` or `scheduled` lanes and invoke them with `--all`. On Windows, an OS Task Scheduler entry is a persistent machine change and requires authorization. Record ownership and make failures visible before the next work period.

Use later full runs to measure what change selection misses. Add an escaped failure to an earlier lane, expand its inputs, or remove an incorrect ignore rule. Do not hide slow critical evidence; make it deterministic, split it, or preserve exact-result reuse.

## 8. Reporting

Report selected lanes, `PASS` versus `REUSED`, failed or timed-out commands, unknown-impact fallback, over-budget warnings, evidence location, deferred scheduled lanes, and hook installation state. In monorepos also report Git-root path basis, project command cwd, existing-router ownership, and delegated evidence state. Keep these binary execution results outside the generated-test quality score.

Preview selection before executing a new or migrated policy:

```powershell
python <skill-folder>/scripts/local_validation_admin.py explain-selection validation-policy.json --repo . --trigger pre_push --changed-file projects/example/src/value.py
```

The result includes `commands_executed: false`, selected lanes, reasons, path basis, command cwd, and unknown-impact state.

### Delegated evidence states

An existing router may invoke the gate with repeated Git-root-relative `--changed-file` values and `--route-id`. The JSON result includes a structured `delegated_evidence` record. Verify a retained record with:

```powershell
python <skill-folder>/scripts/local_validation_admin.py verify-router-evidence projects/example/validation-policy.json delegated-result.json --repo .
```

- `CURRENT_PASS` requires the current policy digest, path basis, project cwd, selected lanes, lane fingerprints, and exact reusable Project Test Maker PASS evidence for every selected blocking lane.
- `HISTORICAL_EVIDENCE` records a router-cache result or execution hint and never satisfies current PASS or Project Test Maker C0/C1 evidence.
- `NOT_RUN` means execution did not occur and never satisfies a gate.
- stale, corrupt, mismatched, failed, or blocked Project Test Maker records do not become current PASS.

The verifier emits `verification_status: VALID` when it can classify a record. That field is not execution success. Exit code zero is reserved for `CURRENT_PASS`; valid `HISTORICAL_EVIDENCE`, `NOT_RUN`, and `CURRENT_NONPASS` return one, while malformed or blocked evidence returns three. Automation must gate on both the exit code and `evidence_state`, never on the historical execution status alone.

## 9. Doctor, status, and evidence cleanup

Use the administration CLI for read-only diagnosis and cache visibility:

```powershell
python <skill-folder>/scripts/local_validation_admin.py doctor validation-policy.json --repo .
python <skill-folder>/scripts/local_validation_admin.py status validation-policy.json --repo .
```

`doctor` validates the policy, impact evidence files, Git top-level boundary, first command token for each lane, and whether input patterns match files. It does not execute lane commands. `status` computes current lane fingerprints and reports `REUSABLE`, `MISSING`, `STALE_OR_INVALID`, or `CACHE_DISABLED`; it also does not run validation.

Garbage collection is dry-run by default:

```powershell
python <skill-folder>/scripts/local_validation_admin.py gc validation-policy.json --repo .
python <skill-folder>/scripts/local_validation_admin.py gc validation-policy.json --repo . --apply
```

Review the reported exact relative JSON paths before `--apply`. Cleanup preserves the current reusable PASS record, removes no directories, requires an evidence root named `evidence`, and never changes policy, hooks, Git configuration, or test files. Deleted cache evidence is recoverable only by rerunning the corresponding lane.
