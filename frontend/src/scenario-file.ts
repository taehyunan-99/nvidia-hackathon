export type ScenarioFile = typeof import("../../docs/frontend-hosting/fixtures/scenarios.json");
export type Scenario = ScenarioFile["scenarios"][number];
export type ReviewInput = {
  schema_version: string;
  example_id: string | null;
  public_data_confirmed: boolean;
  target: { identifier: string | null; fasta: string | null; analysis_range: { start: number; end: number } | null; sources: { title: string; url: string; record_id: string | null }[] };
  candidates: { candidate_id: string; name: string; antibody_format: string | null; heavy_chain_fasta: string; light_chain_fasta: string; heavy_analysis_range: { start: number; end: number } | null; light_analysis_range: { start: number; end: number } | null; sources: { title: string; url: string; record_id: string | null }[] }[];
  uploads: { upload_key: string; file_name: string; format: "pdb" | "mmcif"; candidate_id: string; role: "complex" | "context"; source: { title: string; url: string; record_id: string | null } }[];
};
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

export type DataMode = "mock" | "live";

// 파일 전체가 같은 mode여야 한다. 모의 결과와 실제 결과가 한 파일에 섞이면
// 화면에서 어느 쪽이 실제인지 구분할 수 없다.
function sameMode(value: unknown, mode: DataMode): boolean {
  return value === mode;
}

export function parseScenarioFile(value: unknown): ScenarioFile {
  if (!record(value) || value.schema_version !== "0.1.0") invalid();
  if (value.data_mode !== "mock" && value.data_mode !== "live") invalid();
  const mode = value.data_mode as DataMode;
  const input = value.input;
  const frames = value.scenarios;
  if (!record(input) || !record(input.target) || !records(input.candidates) || input.candidates.length < 2 || input.candidates.length > 3 || !records(frames) || frames.length < 1) invalid();
  const ids = input.candidates.map((candidate) => {
    if (typeof candidate.candidate_id !== "string" || typeof candidate.name !== "string") invalid();
    return candidate.candidate_id;
  });
  if (new Set(ids).size !== ids.length) invalid();
  for (const frame of frames) {
    if (typeof frame.name !== "string" || typeof frame.description !== "string" || !record(frame.session) || !sameMode(frame.session.data_mode, mode)) invalid();
    const run = frame.run;
    const result = frame.result;
    if (frame.session.status === "expired" && (run !== null || result !== null)) invalid();
    if (run !== null) {
      if (!record(run) || !sameMode(run.data_mode, mode) || typeof run.run_id !== "string" || !records(run.candidates) || typeof run.result_available !== "boolean") invalid();
      if (run.result_available !== (result !== null)) invalid();
      if (run.candidates.length !== ids.length || run.candidates.some((candidate) => !ids.includes(candidate.candidate_id as string) || !records(candidate.steps) || candidate.steps.some((step) => typeof step.step_id !== "string" || typeof step.status !== "string"))) invalid();
      if (run.error !== null && (!record(run.error) || typeof run.error.message !== "string")) invalid();
    } else if (result !== null) invalid();
    if (result !== null) {
      if (!record(result) || !sameMode(result.data_mode, mode) || result.run_id !== run?.run_id || !records(result.conditions) || !records(result.evidence) || !records(result.opinions) || !records(result.artifacts) || !records(result.structures)) invalid();
      if (result.conditions.some((condition) => !Array.isArray(condition.gaps)) || result.evidence.some((item) => !Array.isArray(item.sources) || !Array.isArray(item.residues)) || result.opinions.some((opinion) => !Array.isArray(opinion.evidence_ids) || !Array.isArray(opinion.limitations) || !Array.isArray(opinion.follow_up_questions)) || result.artifacts.some((artifact) => typeof artifact.format !== "string")) invalid();
    }
    if (frame.error !== null && (!record(frame.error) || !sameMode(frame.error.data_mode, mode) || typeof frame.error.message !== "string")) invalid();
  }
  return value as ScenarioFile;
}
