# Workflow and output contract

## 0. Confirm the mode and mutation boundary

Use `analyze` for read-only strategy or gap review, `make` for explicitly requested test creation, `grade` for independent assessment, `enforce` for local validation administration, `migrate` for existing-router adoption, and `diagnose` for read-only failure investigation. Combine modes only when the user asks for the combined outcome.

Do not create or change files in `analyze` or `diagnose`. In those modes, stop after the requested findings and proposed next action. Do not compile a rubric, assign a score, or emit a terminal acceptance state unless grading is in scope and the evidence contract is satisfied.

## 1. Reconstruct intent

Collect evidence from product goals, user journeys, acceptance criteria, ADRs, contracts, schemas, trust boundaries, component responsibilities, persistence, messaging, providers, deployment or installer files, existing tests, CI, incidents, and recent changes. Classify important statements as `documented`, `observed`, `inferred`, or `unknown`.

Current implementation is evidence of behavior, not proof of intended behavior. If two plausible interpretations produce different assertions or criticality, stop and ask before encoding either.

## 2. Testing thesis and oracle map

Summarize who relies on the system, what must remain true, what data or actions require protection, which transitions are irreversible, and which dependency, time, ordering, or environment failures matter most.

For each critical risk record:

| Behavior | Oracle source | Invariant or forbidden outcome | Owner/confidence | Candidate test |
|---|---|---|---|---|

Prefer approved requirements, protocols, API/event/data contracts, domain invariants, database constraints, independent policy matrices, simple reference models, reviewed production outcomes, and explicit domain-owner decisions. Label implementation-derived expected values as characterization until reviewed.

## 3. Compile project profile and rubric

Follow [profile-and-criticality.md](profile-and-criticality.md). In `make` or `grade`, produce a profile JSON, run `scripts/compile_test_rubric.py`, and retain the compiled rubric for grading. In `analyze`, present only the profile decisions needed by the requested strategy and do not create intermediate JSON by default.

The compiler enforces:

- one observed delivery form;
- one to six applicable modules;
- explicit selected/omitted criterion applicability when catalog defaults do not fit;
- no hosted-deployment module for local-only delivery;
- evidence and rationale for every module;
- C0 gates outside the score;
- C1 behavior gates and module floors;
- unresolved criticality as `NEEDS_DECISION`;
- exactly 60 universal and 40 project-module points.

Show any material profile, criterion applicability, weight, or criticality ambiguity before test generation.

## 4. Risk-to-test and budget map

| Risk | Class | Failure exposed | Test and oracle | Lane/trigger | Budget | Residual risk |
|---|---|---|---|---|---:|---|

Choose the least expensive layer that observes the failure. Many deterministic unit and property tests, fewer real-boundary integrations, selected local E2E simulations, and small parity or release suites are typical, but project risk controls the shape.

Classify execution topology independently from delivery form. For `local_only`, read [local-execution-enforcement.md](local-execution-enforcement.md), omit unavailable hosted CI gates, and map agent completion, Git hooks, post-merge, and scheduled local triggers to one policy and gate.

For deterministic local E2E:

1. inject clock, scheduler, randomness, and external ports;
2. preserve required stateful semantics;
3. save seeds and event traces;
4. assert business and security invariants rather than mock choreography;
5. replay a small representative set against the relevant real boundary.

## 5. Generate artifacts and witnesses

This section applies only to `make`.

Name the intended defect before writing a test. Track only test and fixture paths created or materially modified in this run. For each C0 gate and important C1 behavior, obtain the strongest proportionate witness:

- bug revision fails and fix passes;
- mutation or seeded fault is detected;
- reference or differential implementation disagrees;
- controlled timeout, duplicate, crash, reorder, or clock advance reaches the protected invariant;
- forbidden authorization combination is rejected at the authoritative boundary;
- disposable real dependency demonstrates required semantics.

Avoid duplicated production algorithms, private call-order assertions, empty mocks, real sleeps, shared mutable fixtures, broad unreviewed snapshots, skips, or timeouts that hide failure.

## 6. Execute and diagnose

Run cheap relevant checks first, then risk-mandated broader checks. Each result is `pass`, `fail`, `blocked`, or `not_run`. A failure is classified as:

- `product_code`
- `generated_test`
- `oracle`
- `environment_dependency`
- `flaky`

Record command or test, location, evidence, oracle, remediation direction, verification, and residual risk. A correct red test that finds a product defect remains valuable; do not lower its quality score merely because the product is wrong.

For local-only enforcement, also report whether each selected lane executed or reused exact PASS evidence, whether unknown impact widened selection, whether any result exceeded its lane budget, the evidence location, policy/doctor/status findings, whether cleanup was dry-run or applied, and whether hooks or scheduled tasks are merely proposed or actually configured. Persistent local configuration requires user authorization.

For a monorepo with an existing validation router, keep changed and policy paths Git-root-relative while reporting the separate project command working directory. Preserve the owning hook/router and use its generated route/evidence contract. Report delegated evidence as `CURRENT_PASS`, `HISTORICAL_EVIDENCE`, or `NOT_RUN`; historical router cache cannot satisfy current PASS or C0/C1 evidence.

## 7. Grade and refine generated tests

Follow [generated-test-scoring.md](generated-test-scoring.md). Read [assessment-schema.md](assessment-schema.md) only when constructing or reviewing assessment JSON. A fresh-context verifier grades every compiled criterion using only the generated artifact manifest and deterministic evidence. Record distinct maker, verifier, and harness actor/context provenance; current artifact SHA-256 values; and typed harness runs. Do not give the verifier the maker's conclusions or intended scores. Run `scripts/grade_generated_tests.py`.

If a genuinely fresh verifier is unavailable, do not invent provenance or self-grade. Report grading as not performed. If the user explicitly required an acceptance decision, report completion `BLOCKED`; otherwise return the selected mode's result without a generated-test quality or completion status.

Acceptance order is non-compensatory:

1. unresolved C0/C1 → `NEEDS_DECISION`;
2. failed C0 test-quality gate → `REJECTED_TEST_OUTPUT`;
3. failed C1 behavior gate or C1 module below 90% → `REJECTED_TEST_OUTPUT`;
4. other hard-gate failure → `REJECTED_TEST_OUTPUT`;
5. total below 90 → `IMPROVE` or a bounded stop state;
6. accepted tests + product defect → `CODE_FIX_REQUIRED`;
7. accepted tests + environment unavailable → `BLOCKED`;
8. accepted tests + required execution pass → `COMPLETE`.

Refine itemized deductions for at most three rounds by default. Stop on no improvement, ambiguous oracle, missing authority, unavailable required environment, exhausted time budget, or need for an out-of-scope production change.

## 8. User-facing output

Lead with a compact mode-aware summary:

1. outcome or current mode result;
2. files created or changed, or `none`;
3. validation executed and its result;
4. decisions or blockers;
5. residual risk.

Expand only relevant evidence planes:

- `analyze`: thesis, top risks, oracle gaps, and proposed portfolio; no generated-test score or terminal acceptance state.
- `make`: created artifacts, witnesses, execution results, and grading only if completed.
- `grade`: score, C0/C1 blockers, provenance, deductions, and terminal state.
- `enforce`: policy, selection, PASS/REUSED, evidence location, cache, and hook state.
- `migrate`: before/after ownership, previewed routes, unchanged hook/router evidence, shadow status, and remaining adoption steps.
- `diagnose`: cause, evidence, smallest aligned correction, and verification; do not implement the fix unless asked.

## 9. Intermediate run artifacts

Keep transient profile, compiled-rubric, assessment, and rendered-report inputs below `<resolved-git-dir>/project-test-maker/runs/<run-id>` when local retention is needed. Use an isolated temporary directory when Git is unavailable, or a user-selected destination for durable reports. Do not place these files in the active skill directory or tracked project paths by default. Preserve user-selected output and retained evidence.

Do not call a generated-test score a project readiness, security, or compliance score.

For external pilot retention, run `scripts/normalize_pilot_status.py` on the structured status record. Report pilot work-unit `SUCCESS` separately from canonical whole-project, generated-test-quality, and execution states. Never place `SUCCESS` or a `PASS_WITH_*` operational alias in a canonical result plane.
