# NVIDIA runtime skill

`boltz2-nim/` contains unmodified instruction and reference files from NVIDIA-BioNeMo/bionemo-agent-toolkit at
`061bec95a9a19370a13d0cea1fddc0a355471999`. The manifest records provenance, licensing and SHA-256 per instruction file; upstream notices and license text are retained (the final extra blank line in CC-BY-4.0 is normalized).

NAT reads the pinned SKILL.md and validation reference into its candidate prompt before choosing tools. `runtime_skill.load_boltz_skill` checks all reference hashes; the prediction adapter checks them again before invoking the existing hosted Boltz-2 client. Source instructions do not grant new shell, Docker, API or file permissions to the seven registered tools.

Only Boltz-2 is connected. MSA-Search is not enabled without input-specific evidence of necessity. Public-structure reuse emits a skipped skill event; prediction emits selected / running / response-received and separate verification results. API success is not coordinate, sequence, binding or efficacy validation. Coordinate/chain/format checks do not change the analysis team's scientific decision thresholds.

Events record skill revision, validated short selection reason, execution state, explicit check results and the actual next available tool. No internal model reasoning or raw prompt is exposed. Tests use scripted transports for success, refusal and failure; live NVIDIA verification must be reported separately.
