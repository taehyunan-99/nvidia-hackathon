# Test selection and feedback budget

Time is part of test design. A test that provides excellent information too late for its trigger will be bypassed or ignored. Optimize three separate quantities:

- **time to first actionable failure**;
- **time to a merge or release decision**;
- **total compute cost**.

Do not optimize only total suite duration. Parallel jobs can consume hours of compute while giving a decision in minutes, and a fast flaky signal can be worse than a slower reliable one.

## Default lane budgets

Use repository history and team needs when available. Otherwise start with these design targets, not universal service-level guarantees:

| Lane | Default target | Suitable work |
|---|---:|---|
| Editor or watch loop | 0–10 seconds | format, syntax, incremental lint/type, one focused test |
| Local targeted loop | 10–60 seconds | changed unit/domain tests and deterministic properties |
| Local pre-push | 1–5 minutes | affected unit, contract, light integration, secret checks |
| PR first actionable failure | within 2 minutes | compile/type/lint, new or previously failing tests, cheap security gates |
| PR core decision | within 10 minutes | affected tests plus risk-mandated blocking checks |
| Extended high-risk PR | 10–30 minutes | selected migration, browser, auth matrix, mutation, or real dependency paths, preferably parallel |
| Post-merge/full regression | 30 minutes–2 hours | broad matrix and expensive integrations |
| Nightly or scheduled | up to several hours if results are owned before the next work period | full matrix, fuzz, mutation, long performance, emulator parity, restore drills |
| Staging or canary | risk, traffic, and signal-window based | use enough representative traffic and at least one relevant peak period; do not force a universal minute target |

These lanes are selected from available project infrastructure, not imposed universally. When CI is unavailable, omit PR/CI lanes and use agent completion, pre-push, post-merge, and scheduled local lanes from [local-execution-enforcement.md](local-execution-enforcement.md). Reuse only exact-input local PASS evidence; do not rerun an unchanged lane merely because a second local trigger fired.

DORA recommends automated test feedback in under ten minutes both locally and in CI. Google Cloud similarly recommends CI under ten minutes or separate rapid and comprehensive pipelines. Microsoft reports roughly 60,000 first- and second-level PR tests in under five minutes, followed by longer acceptance tests; another published Microsoft example reaches broad product validation within about two hours. These are reference points, not proof that every project needs the same scale.

- DORA test automation: https://dora.dev/capabilities/test-automation/
- DORA continuous integration: https://dora.dev/capabilities/continuous-integration/
- Google Cloud CI/CD guidance: https://cloud.google.com/solutions/best-practices-continuous-integration-delivery-kubernetes
- Microsoft release flow: https://learn.microsoft.com/en-us/devops/develop/how-microsoft-develops-devops
- Microsoft shift-left example: https://learn.microsoft.com/en-us/devops/develop/shift-left-make-testing-fast-reliable

For individual targets, Google's widely used size convention treats Small as up to 60 seconds, Medium as up to 5 minutes, and Large as 15 minutes or more. Use these as classification boundaries, not permission for every test to consume its maximum: https://testing.googleblog.com/2010/12/test-sizes.html

## Selection order

Before executing, inspect available timing history and classify the change. Prefer this order:

1. syntax, format, compile, incremental type and lint failures;
2. newly added or changed tests and tests that failed recently;
3. tests directly covering changed code;
4. tests for transitive dependents and changed contracts;
5. mandatory risk suites for auth, tenant/data boundaries, money, migrations, deletion, build, or deployment changes;
6. broader regression selected by dependency and historical failure evidence;
7. full, randomized, or scheduled safety-net suites.

Run independent lanes in parallel when resources allow, but put cheap high-probability failures early. Measure queue time separately from execution time.

Distinguish **prioritization** from **selection**. Prioritization changes order and is safer because all tests still run; use it first to reduce time to first failure. Selection excludes tests and saves compute, but introduces regression-miss risk and therefore needs calibration and safety nets.

Before excluding tests, first look for optimizations that preserve coverage:

- make tests hermetic and remove real sleeps, global state, and shared mutable fixtures;
- shard by historical duration and run independent jobs in parallel;
- cache only when all relevant inputs and tool versions are tracked;
- replace redundant service-wide E2E checks with contract tests while retaining a few critical journeys;
- run mutation only on changed or critical code rather than the entire repository.

## Safe test-impact analysis

Change-based selection can miss unexpected coupling. Require:

- a dependency map or observed coverage/history rather than filename intuition alone;
- reviewed `impact_rules` that retain their dependency, coverage, history, or contract evidence paths in selected lane fingerprints;
- all new tests, recently failing tests, and relevant critical invariants;
- full fallback when impact is unknown;
- wider suites for shared libraries, schemas, auth, build configuration, generated clients, and deployment code;
- periodic full runs to estimate selector false negatives;
- a calibrated random sample from otherwise unselected tests when the project has enough history to make that useful;
- canary and production signals for environment-only escapes;
- a feedback loop that adds any later-stage escape to an earlier appropriate lane.

Meta reports catching more than 99.9% of problematic changes while running about one third of transitively affected tests, but only after training and continuously calibrating a predictive system against historical outcomes. Microsoft Test Impact Analysis similarly includes impacted, newly added, and previously failing tests, falls back to all tests for unsupported changes, and supports periodic full runs.

- Meta predictive test selection: https://engineering.fb.com/2018/11/21/developer-tools/predictive-test-selection/
- Microsoft Test Impact Analysis: https://learn.microsoft.com/en-us/azure/devops/pipelines/test/test-impact-analysis

## When a suite takes more than an hour

Do not immediately delete tests or blindly add runners. First:

1. capture per-test duration, setup, queue, retry, and flake data;
2. identify duplicate scenarios and tests at an unnecessarily expensive layer;
3. replace wall-clock waits with fake clocks or deterministic scheduling;
4. reuse disposable environment setup safely and shard by historical duration;
5. move only tests whose information is not needed for a PR decision to post-merge or scheduled lanes;
6. preserve high-impact blockers even when expensive, but run them only for relevant changes;
7. maintain periodic full and random sampling to measure what selection misses.

A one-hour suite can be reasonable as a post-merge or scheduled safety net. It is usually an unsuitable default inner loop or blocking check for every small change. The goal is not to make every test fast; it is to deliver the necessary evidence before the decision that depends on it.

## Metrics to retain

Do not report one blended duration. Track at least:

- p50 and p95 time to first actionable failure;
- p50 and p95 blocking critical-path duration;
- queue, environment setup, and actual execution time;
- total compute minutes after parallelization;
- flaky first-failure rate, retries, and same-revision outcome changes;
- selected-suite faulty-change recall compared with later full runs;
- `calibrate-impact` missed failed lanes and faulty-lane recall by observation set;
- fallback-to-full and unknown-impact rates;
- failures found post-merge or in canary that should move to an earlier lane;
- time from a late failure to an owned, locally reproducible case.

There is no magic duration that fits every repository. Use the defaults as initial warning lines, then set project SLOs from change frequency, risk, observed p50/p95, and the cost of a missed defect. Fast but weak testing is worse than a justified slower test; slow, flaky, low-signal testing should be replaced or removed first.
