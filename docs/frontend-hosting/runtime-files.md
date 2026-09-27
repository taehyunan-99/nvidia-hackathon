# Runtime file review

2026-09-27. This is the file-level companion to [runtime-audit.md](runtime-audit.md). Call sites, dynamic loading, configuration and tests were cross-checked; a file being listed does not certify every possible input or scientific claim.

| File | Purpose | Entry / consumer | Verification boundary |
|---|---|---|---|
| [logic/__init__.py](../../logic/__init__.py) | package | Python package | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/agent.py](../../logic/agent.py) | model choice and rule fallback | flow / agent_session | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/agent_session.py](../../logic/agent_session.py) | tool ordering and candidate state | flow / nat_agent | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/analysis.py](../../logic/analysis.py) | coordinate evidence and independent reference contact comparison | flow; contact_measurement is regression-only | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/check_key.py](../../logic/check_key.py) | development credential diagnosis | explicit CLI; excluded from image | development only |
| [logic/contacts.py](../../logic/contacts.py) | atom parsing and contact geometry | analysis / flow | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/contract.py](../../logic/contract.py) | JSON schema and timestamps | logic / API / worker | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/env.py](../../logic/env.py) | server credentials and local env loading | nvidia_client / nat_agent | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/flow.py](../../logic/flow.py) | candidate orchestration and result assembly | run / service.app | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/measure_agent.py](../../logic/measure_agent.py) | development benchmark using test input builders | explicit CLI; excluded from image | development only |
| [logic/nat_agent.py](../../logic/nat_agent.py) | NAT tool registration and fallback boundary | flow | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/nat_model.py](../../logic/nat_model.py) | paced model transport and bounded retries | nat_agent / YAML registry | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/nvidia_client.py](../../logic/nvidia_client.py) | NVIDIA HTTP requests and call records | flow / agent | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/prediction_validation.py](../../logic/prediction_validation.py) | sequence-chain-coordinate checks | flow | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/review_policy.py](../../logic/review_policy.py) | evidence-specific bounded opinions | flow | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/run.py](../../logic/run.py) | subprocess CLI | service.live | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/runtime_skill.py](../../logic/runtime_skill.py) | pinned skill integrity and content | nat_agent / flow | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/structure_sources.py](../../logic/structure_sources.py) | explicit source and bounded automatic search | flow | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/structures.py](../../logic/structures.py) | local public catalog and sequence match | flow / analysis / demo_input | static path review; product tests; persisted public image run (reachable branch only) |
| [logic/surface_analysis.py](../../logic/surface_analysis.py) | shared coordinate surface/glycan calculation | flow; dynamic A-02 metrics | static path review; product tests; persisted public image run (reachable branch only) |
| [service/__init__.py](../../service/__init__.py) | package | Python package | static path review; product tests; persisted public image run (reachable branch only) |
| [service/app.py](../../service/app.py) | nonpersistent development demo API | manual uvicorn only | development only |
| [service/db.py](../../service/db.py) | connection and explicit migration CLI | operational / worker / Compose migrate | static path review; product tests; persisted public image run (reachable branch only) |
| [service/demo_input.py](../../service/demo_input.py) | public input and labeled synthetic variant | demo API / verification scripts | static path review; product tests; persisted public image run (reachable branch only) |
| [service/live.py](../../service/live.py) | analysis subprocess, timeout and artifact boundary | worker | static path review; product tests; persisted public image run (reachable branch only) |
| [service/operational.py](../../service/operational.py) | persistent session/input/run/report/file API | Docker CMD / Caddy | static path review; product tests; persisted public image run (reachable branch only) |
| [service/reports.py](../../service/reports.py) | same-snapshot JSON and CSV export | operational / app | static path review; product tests; persisted public image run (reachable branch only) |
| [service/worker.py](../../service/worker.py) | mode-specific ownership, completion and cleanup | Compose / CLI | static path review; product tests; persisted public image run (reachable branch only) |
| [scripts/check_live_flow.py](../../scripts/check_live_flow.py) | live public input/result/file integration check | explicit CLI; not model success proof | development only |
| [scripts/check_mock_flow.py](../../scripts/check_mock_flow.py) | mock persisted contract check | CI / explicit CLI | development only |
| [scripts/check_server_config.py](../../scripts/check_server_config.py) | safe loopback configuration check | rehearsal CLI | development only |
| [scripts/check_server_flow.py](../../scripts/check_server_flow.py) | mock HTTPS create/reload/ownership check | rehearsal CLI | development only |
| [scripts/check_server_storage.py](../../scripts/check_server_storage.py) | restored DB/file checksum check | rehearsal container CLI | development only |
| [scripts/check_surface_examples.py](../../scripts/check_surface_examples.py) | coordinate diagnostic export | explicit development CLI | development only |
| [scripts/compare_review_outputs.py](../../scripts/compare_review_outputs.py) | before/after evidence-topic comparison | explicit development CLI | development only |
| [frontend/src/AgentActivity.tsx](../../frontend/src/AgentActivity.tsx) | actual events and explicitly initiated replay; activity-state tests | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/AgentStart.tsx](../../frontend/src/AgentStart.tsx) | public input/direct entry and mock/live notice | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/OpacityControl.tsx](../../frontend/src/OpacityControl.tsx) | viewer opacity input | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/PersistentInput.tsx](../../frontend/src/PersistentInput.tsx) | fixed HER2 and 2-4 candidates; source entry | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/PredictedStructure.tsx](../../frontend/src/PredictedStructure.tsx) | per-run structure/hash validation and selected evidence highlighting | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/ReportView.tsx](../../frontend/src/ReportView.tsx) | same result opinions/sources and authenticated downloads | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/ReviewOverview.tsx](../../frontend/src/ReviewOverview.tsx) | candidate/condition/evidence selection; selected residues forwarded to 3D | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/StructurePreview.tsx](../../frontend/src/StructurePreview.tsx) | separate public example for mock mode; not candidate analysis | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/activity-state.ts](../../frontend/src/activity-state.ts) | event ordering and honest next-action status | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/agent-activity.css](../../frontend/src/agent-activity.css) | active stylesheet; imports and build checked | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/agent-experience.css](../../frontend/src/agent-experience.css) | active stylesheet; imports and build checked | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/main.tsx](../../frontend/src/main.tsx) | application state and persisted polling; obsolete scenario playback removed | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/molecular-viewer.ts](../../frontend/src/molecular-viewer.ts) | Mol* rendering; explicit chain/residue/context selection | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/nvidia-theme.css](../../frontend/src/nvidia-theme.css) | active stylesheet; imports and build checked | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/persistent-mock.ts](../../frontend/src/persistent-mock.ts) | persistent client for BOTH live and mock; historical name retained | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/report-view.css](../../frontend/src/report-view.css) | active stylesheet; imports and build checked | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/review-overview.css](../../frontend/src/review-overview.css) | active stylesheet; imports and build checked | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/scenario-file.ts](../../frontend/src/scenario-file.ts) | display input types/parser; not scientific validation | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/structure-preview.css](../../frontend/src/structure-preview.css) | active stylesheet; imports and build checked | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/style.css](../../frontend/src/style.css) | active stylesheet; imports and build checked | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/tokens.css](../../frontend/src/tokens.css) | active stylesheet; imports and build checked | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |
| [frontend/src/vite-env.d.ts](../../frontend/src/vite-env.d.ts) | build environment declarations | main/component imports | type build; selected UI paths in browser; no exhaustive visual certification |

Additional runtime data: `logic/nat_workflow.yml`, `logic/skills/boltz2-nim/` manifest and referenced documents, `service/migrations/001..004`, `service/mock_scenarios.json`, `docs/frontend-hosting/contracts/service.schema.json`, `frontend/public/structures/`, verified structure catalog, `docs/topics/her2/assets/a02/metrics.py`. The API image includes these dependencies and excludes test modules, model benchmarks and historical research outputs.

Development-only families retained: `logic/tests`, `service/tests`, `frontend/tests`, `test/*.json`, scripts above, research generators/tests under A-01/A-02/A-03/goldset/hackathon-evaluation, and `.agents/.claude/.codex/.github`. Research tests are outside the default product suite; their current failures are recorded separately. Root Docker/Compose/Caddy/env and CI paths were reviewed against actual image startup. No runtime code imports tests; the development benchmark explicitly does.

Removed after caller verification: main scenario playback timer/state/next-record branch, unused `analysis.pending_measurements`, unused main Scenario import and viewer options variable. Preserved: explicit sync demo, mock worker, public preview, independent contact oracle, manual model benchmark, runtime dynamic metrics and pinned skill.

2026-09-27 local-readiness additions: `service/limits.py` is the production request/storage guard; migration 005 adds the shared request budget. `frontend/src/run-location.ts` handles execution URLs with same-session ownership remaining on the API. `frontend/tests/run-location.test.mjs` and new API limit cases are development-only verification. The expired-frame helper no longer supplies synthetic fixture input. Research tests generate only temporary outputs and preserve archived artifacts.
