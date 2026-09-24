# Repository-local adoption and existing-router migration

Read this reference only when deploying Project Test Maker inside a repository or migrating an existing validation hook/router.

## Deployment boundary

The maintained source is the project `skill/` directory. A repository-local deployment is an exact generated copy at:

```text
<repo>/.agents/skills/project-test-maker/
├── SKILL.md
├── agents/openai.yaml
├── references/
└── scripts/
```

Resolve runtime resources from the directory containing the active `SKILL.md`. Do not assume `%CODEX_HOME%` or a personal installation. When displaying commands, replace `<skill-folder>` with the resolved repository-relative or absolute path.

Codex can discover both personal and repository-local skills with the same `name`; it does not merge them. Before declaring migration complete, identify any active personal `project-test-maker` copy and ask the user whether to disable or remove it. Do not delete or disable it without an explicit request. Record which copy is authoritative for the current run.

Do not place project-maintenance docs, regression tests, installer scripts, run outputs, `__pycache__`, or `.pyc` files in the deployed skill directory. Compare the complete file list and SHA-256 values with the maintained `skill/` source after deployment.

## Run workspace

Only requested tests, fixtures, reviewed validation policies, and route contracts belong in tracked project paths. Store transient profile, compiled-rubric, assessment, and rendered-report inputs under:

```text
<resolved-git-dir>/project-test-maker/runs/<run-id>/
```

Use an isolated temporary directory when Git is unavailable, or a user-selected destination when they request durable reports. Never write run artifacts into `.agents/skills/project-test-maker` or another deployed skill copy. Do not delete retained evidence or user-selected output without authorization.

## Existing-router migration

Preserve the existing hook, router, route definitions, platform dispatch, and multi-ref processing. Migrate one project route at a time:

1. **Inventory, read-only:** record the existing route ID, Git-root-relative match patterns, project working directory, platform commands, triggers, cache identity, and hook/router file hashes.
2. **Propose:** map the route to a reviewed Project Test Maker lane plan. Label inferred commands, criticality, or cache safety and request confirmation before writing policy.
3. **Preview:** generate the policy in the approved destination and run `explain-selection` with representative root-relative paths. It must report `commands_executed: false`.
4. **Contract:** create the router contract. Recheck that existing hook/router hashes are unchanged.
5. **Shadow:** let the existing route remain authoritative while comparing selected lanes, duration, failures, and unknown-impact fallback. Existing router cache remains `HISTORICAL_EVIDENCE`.
6. **Delegate:** only after reviewed shadow evidence, let the route command use Project Test Maker. Incomplete change knowledge must pass `--impact-unknown`.
7. **Verify:** require `verify-router-evidence` exit code zero and `CURRENT_PASS`. Exit code one is a valid but non-passing classification; exit code three is invalid or blocked evidence.

Do not remove the prior route command or cache until the user explicitly authorizes cleanup. Do not claim migration from a generated contract alone.

## Read-only selection preview

```powershell
python <skill-folder>/scripts/local_validation_admin.py explain-selection validation-policy.json --repo <git-root> --trigger pre_push --changed-file projects/example/src/value.py
```

Report path basis, project working directory, selected lanes, per-lane reasons, matched impact rules, and whether unknown impact widened selection. The command validates policy and impact evidence but never executes a lane.
