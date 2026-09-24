# Generated-test assessment schema

Read this reference only when constructing or reviewing the machine-readable assessment consumed by `grade_generated_tests.py`.

## Required shape

```json
{
  "schema_version": "2.0.0",
  "run_id": "run-2026-09-04-001",
  "iteration": 1,
  "previous_score": null,
  "provenance": {
    "maker": {"role": "maker", "actor_id": "maker-1", "context_id": "maker-context"},
    "verifier": {
      "role": "verifier",
      "actor_id": "verifier-1",
      "context_id": "fresh-verifier-context",
      "fresh_context": true,
      "maker_conclusions_shared": false
    },
    "harness": {"role": "harness", "actor_id": "harness-1", "context_id": "local-runner"}
  },
  "artifacts": [
    {
      "path": "tests/authorization.test.ts",
      "kind": "test",
      "change": "created",
      "producer_id": "maker-1",
      "sha256": "<64 lowercase hex characters>"
    }
  ],
  "harness_runs": [
    {
      "id": "focused-1",
      "harness_id": "harness-1",
      "kind": "test_execution",
      "status": "pass",
      "command": ["npm", "test", "--", "authorization.test.ts"],
      "artifact_paths": ["tests/authorization.test.ts"],
      "artifact_digests": {"tests/authorization.test.ts": "<manifest SHA-256>"},
      "input_fingerprint": "<64 lowercase hex characters>",
      "outcome_digest": "<64 lowercase hex characters>",
      "defect_detected": false
    }
  ],
  "criterion_assessments": {
    "core.traceability": {
      "rating": "complete",
      "artifact_paths": ["tests/authorization.test.ts"],
      "harness_run_ids": ["focused-1"],
      "verified_by": "verifier-1",
      "evidence": ["Cases map to the approved tenant-isolation policy."],
      "finding": "Traceability is explicit.",
      "fix": ""
    }
  },
  "c0_gate_results": {
    "tenant_isolation": {
      "approved_oracle": {
        "status": "pass",
        "verified_by": "verifier-1",
        "oracle": "Approved tenant policy.",
        "evidence_sources": ["docs/security.md"]
      },
      "required_tests": {
        "status": "pass",
        "verified_by": "verifier-1",
        "artifact_paths": ["tests/authorization.test.ts"],
        "harness_run_ids": ["focused-1"]
      },
      "failure_witness": {
        "status": "pass",
        "verified_by": "verifier-1",
        "kind": "seeded_fault",
        "artifact_paths": ["tests/authorization.test.ts"],
        "harness_run_ids": ["seeded-fault-1"]
      },
      "reproducibility": {
        "status": "pass",
        "verified_by": "verifier-1",
        "harness_run_ids": ["focused-1", "focused-2"]
      }
    }
  },
  "c1_behavior_results": {},
  "hard_gate_results": {
    "artifacts_load_and_execute": {
      "status": "pass",
      "verified_by": "verifier-1",
      "evidence": ["The harness loaded and reached assertions."]
    }
  },
  "execution_results": [],
  "residual_project_risks": []
}
```

The example abbreviates repeated criteria, harness runs, C0/C1 behaviors, and hard gates. Include every compiled criterion and gate exactly once.

## Cross-validation rules

- Artifact paths are repository-relative forward-slash paths and current file SHA-256 values must match the manifest.
- Maker, verifier, and harness actor IDs are distinct; maker and verifier context IDs differ.
- The verifier has fresh context and receives no maker conclusions or intended score.
- Every referenced harness run exists and carries matching artifact digests.
- Reproducibility uses at least two distinct passing `test_execution` runs with identical input fingerprints and outcome digests.
- A passing failure witness references `seeded_fault`, `mutation`, `red_green`, `differential`, `controlled_failure`, or `real_boundary` evidence with `defect_detected: true`.
- Required parity references a passing `real_boundary_parity` run.
- Criterion ratings are only `missing`, `weak`, `strong`, or `complete`; raw percentage inputs are invalid.

If a fresh-context verifier is unavailable, do not create fictional provenance or run the grader. Report grading as not performed. If the user explicitly required an acceptance decision, completion is `BLOCKED`; otherwise return the selected mode's ungraded result without inventing a generated-test status.
