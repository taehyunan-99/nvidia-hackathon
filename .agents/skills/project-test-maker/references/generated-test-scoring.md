# Generated-test grading and refinement

Use this reference in `grade`, or in `make` when independent grading is part of the requested outcome. The numeric score applies only to tests and supporting fixtures created or materially modified in the current run.

## Artifact and provenance boundary

Create a manifest containing every scored path. Allowed changes are `created` and `modified`. Each artifact identifies the maker and its current lowercase SHA-256. Criterion, gate, and harness evidence must resolve to manifest paths and matching digests.

The maker, fresh-context verifier, and harness have distinct actor IDs. Maker and verifier context IDs differ, and the verifier attests that maker conclusions and intended scores were not supplied. This is local consistency validation, not hostile-user-resistant attestation.

If a fresh verifier is unavailable, do not fabricate identities or self-grade. Report grading as not performed. Use `BLOCKED` only when the user explicitly required an acceptance decision; otherwise return the ungraded result of the selected mode.

Read [assessment-schema.md](assessment-schema.md) only when constructing or reviewing the assessment JSON.

## Execution and quality are separate

Executable checks report `pass`, `fail`, `blocked`, or `not_run`. A failure uses one cause:

- `product_code`
- `generated_test`
- `oracle`
- `environment_dependency`
- `flaky`

A correct generated test that finds a product defect can still be accepted as a test artifact. Do not weaken it. Report `TESTS_ACCEPTED / CODE_FIX_REQUIRED` until an authorized code fix makes required execution green.

## Cross-validation

Include every compiled criterion, C0 gate, C1 behavior gate, and hard gate exactly once. Do not submit aggregate caller-controlled C0 or C1 pass states.

- C0 components link the compiled oracle and evidence, generated tests, passing harness runs, a defect-detecting witness, reproducibility, and required real-boundary parity.
- C1 behavior components link the approved oracle, generated tests, successful verification, and every required compiled criterion.
- Reproducibility uses at least two distinct passing `test_execution` runs with identical input fingerprints and outcome digests.
- Passing failure witnesses use an allowed typed run with `defect_detected: true`.
- Criterion ratings are only `missing`, `weak`, `strong`, or `complete`; catalog mappings derive percentages.
- `--artifact-root` hashes current files before grading, so stale manifest or harness digests are invalid.

Grade with the active skill folder:

```text
python <skill-folder>/scripts/grade_generated_tests.py <compiled-rubric.json> <assessment.json> --artifact-root <target-project-root> --format markdown
```

## Acceptance order

1. unresolved criticality or C0/C1 oracle → `NEEDS_DECISION`;
2. failed C0 component → `REJECTED_TEST_OUTPUT`;
3. failed C1 behavior or C1 module below 90% → `REJECTED_TEST_OUTPUT`;
4. other hard-gate, oracle, generated-test, or flaky failure → `REJECTED_TEST_OUTPUT`;
5. valid score below 90 → `IMPROVE` or a bounded stop state;
6. accepted tests plus product defect → `CODE_FIX_REQUIRED`;
7. accepted tests plus unavailable environment or required not-run execution → `BLOCKED`;
8. accepted tests plus required execution PASS → `COMPLETE`.

Use itemized deductions to improve only generated or materially modified test artifacts for at most three rounds by default. Stop on no progress, ambiguous oracle, missing authority, unavailable required environment, exhausted budget, or need for an out-of-scope product change. Report broader project risks separately without points.

## Adaptive report

Lead with score and terminal state only when grading actually ran. Then show C0/C1 blockers, execution failures, highest-impact deductions, and residual risks. Omit empty sections and do not repeat full machine evidence in the user-facing response; link retained artifacts when the user requested durable output.
