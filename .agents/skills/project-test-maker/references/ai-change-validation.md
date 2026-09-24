# Validating AI-created changes

Treat AI output as an untrusted contribution that may be plausible, internally consistent, and wrong in correlated ways. Validation should combine independent oracles with different detection mechanisms; adding more tests from the same ambiguous context is not sufficient.

## Progressive validation order

Choose relevant checks from this order and run cheap failures early:

1. format, parse, compile, strict type, and runtime schema checks;
2. focused unit, property, contract, and integration tests derived from approved behavior;
3. dependency existence and provenance, SCA and license review, secret scanning, SAST, and deployment-configuration checks;
4. local deterministic E2E for state, time, retry, duplicate, ordering, and failure behavior;
5. mutation or targeted fault injection to show that critical assertions fail for the intended defect;
6. independent human or domain review for architecture, business meaning, security boundaries, money, privacy, and irreversible state;
7. real-environment parity, staging, canary, runtime invariants, and rollback.

No individual layer is a release proof. Lint and type checks cannot validate business meaning; unit tests can copy a bad oracle; mocks cannot prove IAM or provider behavior; SAST has supported-query and false-positive limits; human review is subject to fatigue.

## AI-specific diff review

Increase risk and require explicit evidence when a change:

- adds a dependency, import, API, model, CLI flag, configuration key, or framework feature that may not exist;
- deletes tests or adds `skip`, `only`, quarantine, coverage exclusions, broad snapshots, or longer timeouts;
- weakens an assertion from a concrete outcome to mere existence or successful status;
- replaces a real integration fixture with an empty or stateless mock;
- modifies CI, lint, type, security, release, permission, or CODEOWNER policy;
- introduces broad exception handling, fallback success, disabled validation, or placeholder credentials;
- changes generated code without changing its source or generator.

For new packages, verify the official registry entry, exact name, resolved lockfile version, maintainer or repository, license, known vulnerabilities, and whether the dependency is actually needed. Compilation alone is not enough because an attacker can register a previously hallucinated package name.

For bug fixes, require a regression test that fails on the defective revision and passes on the fix when feasible. For new behavior, use an approved contract, invariant, reference model, or domain-owner decision rather than expected values copied from the implementation.

## Evidence-backed practice

- GitHub recommends compile, tests, and static analysis for AI-generated code, plus review for architectural fit, hallucinated dependencies, and deleted or skipped tests: https://docs.github.com/en/copilot/tutorials/review-ai-generated-code
- Google states that tests do not test themselves and reviewers must check whether they fail when code is broken: https://google.github.io/eng-practices/review/reviewer/looking-for.html
- Microsoft combines independent manual review with static analysis, credential scanning, component governance, fuzzing, configuration validation, and penetration testing: https://learn.microsoft.com/en-us/compliance/assurance/assurance-microsoft-security-development-lifecycle
- Meta grounds LLM-generated tests with mutants that represent intended defects and executes filters before human acceptance: https://engineering.fb.com/2025/02/05/security/revolutionizing-software-testing-llm-powered-bug-catchers-meta-ach/
- Anthropic recommends layered automated evals, production monitoring, and periodic human calibration rather than a single evaluator: https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- NIST SSDF recommends peer review, static and dynamic analysis, regression tests for prior vulnerabilities, fuzzing, and risk-based penetration testing: https://csrc.nist.gov/pubs/sp/800/218/final
