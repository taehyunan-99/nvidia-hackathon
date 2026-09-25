export type ScenarioFile = typeof import("../../docs/frontend-hosting/fixtures/scenarios.json");
export type Scenario = ScenarioFile["scenarios"][number];
export type ReviewInput = ScenarioFile["input"];
export type Result = NonNullable<Scenario["result"]>;

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalid(): never {
  throw new Error("v0.1.0 모의 시나리오 JSON 형식을 확인해 주세요.");
}

function records(value: unknown): value is Record<string, unknown>[] {
  return Array.isArray(value) && value.every(record);
}

export function parseScenarioFile(value: unknown): ScenarioFile {
  if (!record(value) || value.schema_version !== "0.1.0" || value.data_mode !== "mock") invalid();
  const input = value.input;
  const frames = value.scenarios;
  if (!record(input) || !record(input.target) || !records(input.candidates) || input.candidates.length < 2 || input.candidates.length > 3 || !records(frames) || frames.length < 1) invalid();
  const ids = input.candidates.map((candidate) => {
    if (typeof candidate.candidate_id !== "string" || typeof candidate.name !== "string") invalid();
    return candidate.candidate_id;
  });
  if (new Set(ids).size !== ids.length) invalid();
  let runId: string | null = null;
  for (const frame of frames) {
    if (typeof frame.name !== "string" || typeof frame.description !== "string" || !record(frame.session) || frame.session.data_mode !== "mock") invalid();
    const run = frame.run;
    const result = frame.result;
    if (frame.session.status === "expired" && (run !== null || result !== null)) invalid();
    if (run !== null) {
      if (!record(run) || run.data_mode !== "mock" || typeof run.run_id !== "string" || !records(run.candidates) || typeof run.result_available !== "boolean") invalid();
      if (runId !== null && runId !== run.run_id) invalid();
      runId = run.run_id;
      if (run.result_available !== (result !== null)) invalid();
      if (run.candidates.length !== ids.length || run.candidates.some((candidate) => !ids.includes(candidate.candidate_id as string) || !records(candidate.steps) || candidate.steps.some((step) => typeof step.step_id !== "string" || typeof step.status !== "string"))) invalid();
      if (run.error !== null && (!record(run.error) || typeof run.error.message !== "string")) invalid();
    } else if (result !== null) invalid();
    if (result !== null) {
      if (!record(result) || result.data_mode !== "mock" || result.run_id !== runId || !records(result.conditions) || !records(result.evidence) || !records(result.opinions) || !records(result.artifacts) || !records(result.structures)) invalid();
      if (result.conditions.some((condition) => !Array.isArray(condition.gaps)) || result.evidence.some((item) => !Array.isArray(item.sources) || !Array.isArray(item.residues)) || result.opinions.some((opinion) => !Array.isArray(opinion.evidence_ids) || !Array.isArray(opinion.limitations) || !Array.isArray(opinion.follow_up_questions)) || result.artifacts.some((artifact) => typeof artifact.format !== "string")) invalid();
    }
    if (frame.error !== null && (!record(frame.error) || frame.error.data_mode !== "mock" || typeof frame.error.message !== "string")) invalid();
  }
  return value as ScenarioFile;
}
