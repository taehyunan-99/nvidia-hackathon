---
name: project-test-maker
description: Analyze project intent and risk to design, create, diagnose, enforce, migrate, or independently grade a trustworthy test portfolio. Use when explicitly invoked for project-wide test strategy, test generation, local validation, router migration, or generated-test assessment. Not for certification or unauthorized production testing.
---

# Project Test Maker

Build the smallest trustworthy test portfolio for the project that exists and the product it is intended to become. Start from approved intent, independent oracles, and costly failure modes rather than a generic checklist or test count.

## Choose the mode

Select the narrowest mode supported by the user's request. Combine modes only when explicitly requested.

- `analyze`: inspect direction, risks, or test gaps and propose a portfolio. Read-only and the default when mutation is not explicit.
- `make`: create or materially modify requested tests and fixtures, then execute proportionate checks.
- `grade`: independently grade an existing current-run generated-test artifact scope.
- `enforce`: create or update a reviewed local validation policy, standalone adapter, or evidence workflow.
- `migrate`: map existing hooks or routers to Project Test Maker without replacing their ownership.
- `diagnose`: determine why tests or validation failed. Read-only unless the user separately requests a fix.

Do not create tests, policies, hooks, contracts, project instructions, or persistent configuration in `analyze` or `diagnose`. An ambiguous request stays read-only while you surface the decision that would authorize a wider mode.

## Read only what the mode needs

- For `analyze` and `make`, read [workflow-and-output.md](references/workflow-and-output.md) and [profile-and-criticality.md](references/profile-and-criticality.md).
- Read [test-budget.md](references/test-budget.md) for architecture-wide strategy, selection, local simulation, CI, or slow suites.
- Read [ai-change-validation.md](references/ai-change-validation.md) when validating AI-created or AI-modified code.
- For `grade`, read [generated-test-scoring.md](references/generated-test-scoring.md); read [assessment-schema.md](references/assessment-schema.md) only when constructing or reviewing assessment JSON.
- For `enforce`, read [local-execution-enforcement.md](references/local-execution-enforcement.md).
- For repo-local deployment or `migrate`, read [repo-local-adoption.md](references/repo-local-adoption.md) and the relevant enforcement sections.

Use `references/rubric-catalog.json`, `scripts/compile_test_rubric.py`, and `scripts/grade_generated_tests.py` only when compilation or grading is in scope. Run scripts from the active skill folder; do not assume a personal `%CODEX_HOME%` installation.

## Shared decision flow

1. Read applicable project instructions, product evidence, ADRs, contracts, architecture, relevant code, existing tests, and current validation topology.
2. Separate `documented`, `observed`, `inferred`, and `unknown` claims. Stop before encoding an ambiguity that changes an oracle or criticality.
3. Form the testing thesis, oracle map, project profile, and C0/C1/C2 map only to the depth needed by the selected mode.
4. Map each prioritized failure to the least expensive credible test and execution lane. Prefer coverage-preserving speedups before excluding tests.
5. In `make`, record only created or materially modified tests and fixtures, obtain proportionate failure witnesses, execute relevant checks, and classify failures.
6. In `grade`, compile and grade the exact artifact scope with deterministic evidence and a genuinely fresh verifier.

Execution status is binary and separate from generated-test quality. Never weaken a valid test to make it green, treat implementation-derived output as an independent oracle, or let points compensate for a C0/C1 failure.

## Non-compensatory acceptance

- C0 critical invariants are binary generated-test quality gates outside the score.
- Every selected C1 module must score at least 90 percent, and every compiled C1 behavior must independently pass its required anchored criteria and structured evidence gate.
- C2 items may participate in the weighted average but cannot compensate for C0/C1 failure.
- Total generated-test quality must be at least 90/100.
- All other hard gates must pass.
- A valid C0 test that exposes a product defect can be accepted as a test artifact; report `TESTS_ACCEPTED / CODE_FIX_REQUIRED` until an authorized fix makes required execution green.
- Do not invent maker, verifier, or harness identities. If fresh-context verification is unavailable, do not self-grade or emit a generated-test acceptance state. Report grading as not performed; use `BLOCKED` only when the user explicitly required an acceptance decision.

## Test selection rules

- Pure domain rules: focused unit tests plus properties or tables for boundary-rich logic.
- API, event, and schema boundaries: contract tests and runtime validation.
- Database behavior: use the same engine and relevant major version when engine-specific constraints, isolation, extensions, or migrations matter.
- Time, retry, queues, leases, expiry, billing, and schedules: injected clocks, deterministic schedulers, stateful fakes, saved seeds, and invariant assertions.
- Managed cloud behavior: fast local fakes or emulators plus a small approved real-environment parity suite for identity, configuration, triggers, limits, and provider semantics.
- Authorization and isolation: executable actor-resource-action matrices covering positive, horizontal, vertical, cross-boundary, cache, export, file, search, and background paths.
- Parsers and broad input spaces: property-based, metamorphic, differential, or fuzz tests.
- Release-only failures: staging smoke, canary, observable invariants, and rollback tests only for projects with those surfaces.
- Static checks: select formatter, lint, compile/type, runtime schemas, SAST, SCA, secret, IaC, container, and artifact checks by their actual detection models.

## Trust, scope, and safety

- A separate AI tester is useful but not an independent oracle when it shares the same ambiguous specification or model bias.
- Score only the current run's created or materially modified test artifacts. Report broader project risks without points.
- Mocks model only required semantics. Local simulation does not prove IAM, quotas, deployment configuration, network behavior, or managed-service parity.
- Test selection introduces false-negative risk. Use dependency, coverage, history, or contract impact rules only with repository evidence; rules add lanes and never suppress critical, direct, or unknown-impact fallback selection.
- Local hooks reduce accidental omissions but remain bypassable. Preserve an existing monorepo hook/router: use `existing_router`, preview selection, create a route contract, and verify delegated evidence instead of scaffolding a hook. Existing router cache is `HISTORICAL_EVIDENCE`; only exact Project Test Maker evidence can become `CURRENT_PASS`. Do not count execution enforcement in the generated-test score.
- In external pilot retention, keep pilot work-unit status separate from canonical whole-project, generated-test-quality, and execution states. Use `scripts/normalize_pilot_status.py`; `SUCCESS` and supported `PASS_WITH_*` aliases belong only to the work-unit plane, while canonical execution keeps `PASS`, failures, blocked, flaky, and `NOT_RUN` distinct.
- Only requested tests, fixtures, reviewed policies, and route contracts belong in tracked project paths. Put transient profile, rubric, assessment, and rendered-report inputs under the resolved Git directory at `project-test-maker/runs/<run-id>`, an isolated temporary directory, or a user-selected destination. Never write run artifacts into the skill folder.
- Never install tools, provision cloud resources, modify production, or run DAST, load, fuzz, destructive, quota-exhaustion, or penetration tests against a live service without explicit authorization.
- Redact secrets and sensitive payloads. Preserve unrelated user changes.

## Adaptive output

Lead with only the relevant parts:

1. outcome or current mode result;
2. files created or changed, or `none`;
3. validation executed and its result;
4. decisions or blockers;
5. residual risk.

Add thesis, oracle, profile, C0/C1, rubric, provenance, cache, router, migration, or pilot detail only when that plane was used or materially affects the outcome. Analysis-only work has no generated-test score or terminal acceptance state. Never present a score as proof of correctness, security, compliance, or production readiness.
