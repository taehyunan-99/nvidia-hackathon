# Project profile and criticality compilation

Use this reference before generating tests. The profile and criticality map determine which rubric modules exist and which requirements cannot be compensated by points.

## Profile evidence

Inspect approved product documents, ADRs, manifests, entry points, deployment files, installers, APIs, data stores, queues, cloud adapters, user journeys, trust boundaries, and relevant incident history. Record a single primary delivery form:

- `hosted`
- `local`
- `hybrid`
- `library`
- `cli`
- `worker`
- `data_pipeline`
- `client`

Select one to six module IDs from `rubric-catalog.json`. Each selection needs a positive `risk_weight` and evidence-backed rationale. Do not select `hosted_deployment` for a local-only project. If the observed profile conflicts with a requested module, resolve the ambiguity rather than forcing compilation.

When every catalog criterion applies with its default relative weight, omit the module's `criteria` field. Otherwise classify every criterion in that module explicitly. A selected criterion needs `risk_weight`, `rationale`, and `evidence`; an omitted criterion needs an evidence-backed structural inapplicability rationale and must not carry a weight. At least one criterion remains selected. Omission earns no N/A points, and C1 `required_criteria` cannot reference an omitted criterion.

```json
{
  "id": "local_lifecycle",
  "risk_weight": 3,
  "rationale": "Installer and local data transitions are observed product surfaces.",
  "criteria": [
    {
      "id": "install_update_uninstall",
      "applicability": "selected",
      "risk_weight": 3,
      "rationale": "Install and upgrade transitions are release blockers.",
      "evidence": ["installer/product.wxs"]
    },
    {
      "id": "filesystem_permissions",
      "applicability": "omitted",
      "rationale": "The approved sandbox exposes no privileged filesystem boundary.",
      "evidence": ["docs/architecture.md"]
    }
  ]
}
```

The abbreviated example shows the field shape; a real override must classify every catalog criterion in the module.

## Criticality map

Classify behavior, not files:

- `C0`: authorization, privacy, money, irreversible data integrity, destructive boundary, or primary safety invariant. It becomes a binary test-quality gate outside the score.
- `C1`: primary value, compatibility, recovery, or material operational contract. Its selected module must score at least 90 percent.
- `C2`: general quality and lower-impact behavior. It participates in the weighted score.

Every entry needs a behavior statement, independent oracle, evidence, and optional selected module ID. C1 entries require a selected module and one or more `required_criteria` IDs from that module's catalog criteria. Those criteria become a behavior-level non-compensatory gate; unrelated scores in the same module cannot compensate for the behavior. C0 entries should state whether real-boundary parity is required. Do not silently downgrade uncertainty. Put unresolved candidates in `unresolved_criticality`; compilation then produces `NEEDS_DECISION`.

## Profile JSON

```json
{
  "project": "example-service",
  "delivery_form": "hosted",
  "profile_evidence": ["deploy/service.yaml", "docs/ADR.md"],
  "selected_modules": [
    {
      "id": "hosted_deployment",
      "risk_weight": 3,
      "rationale": "The service is deployed continuously and database migrations are part of releases."
    },
    {
      "id": "authorization_tenancy",
      "risk_weight": 5,
      "rationale": "Customer data is separated by tenant and role."
    }
  ],
  "criticality_map": [
    {
      "id": "tenant_isolation",
      "class": "C0",
      "behavior": "A tenant must never read or mutate another tenant's data.",
      "oracle": "Approved authorization policy and tenant data-boundary ADR.",
      "evidence": ["docs/security/authorization.md"],
      "module_id": "authorization_tenancy",
      "requires_parity": true
    },
    {
      "id": "rollback_release",
      "class": "C1",
      "behavior": "A failed release can restore the previous compatible artifact.",
      "oracle": "Release SLO and rollback runbook.",
      "evidence": ["docs/runbooks/rollback.md"],
      "module_id": "hosted_deployment",
      "required_criteria": ["rollback"]
    }
  ],
  "unresolved_criticality": []
}
```

Compile with:

```text
python <skill-folder>/scripts/compile_test_rubric.py <profile.json> --format json
```

Save the compiled output for the generated-test grader. Show the selected modules, allocated points, criticality map, and unresolved decisions to the user before disputed expectations influence test generation.
