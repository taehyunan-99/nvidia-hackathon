import fixture from "../../docs/frontend-hosting/fixtures/scenarios.json";
import { parseScenarioFile, type ReviewInput, type ScenarioFile } from "./scenario-file";

export const SAVED_RUN_KEY = "her2-mock-run";

type Session = ScenarioFile["scenarios"][number]["session"];
type Run = NonNullable<ScenarioFile["scenarios"][number]["run"]>;
type Result = NonNullable<ScenarioFile["scenarios"][number]["result"]>;
let cachedSession: Session | null = null;
let lastHeartbeat = 0;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8010"}${path}`, {
    credentials: "same-origin",
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const error = new Error(body?.message ?? `서비스 응답 ${response.status}`);
    Object.assign(error, { status: response.status, code: body?.code });
    throw error;
  }
  return response.json();
}

export function isSessionExpired(error: unknown): boolean {
  return error instanceof Error && (error as Error & { code?: string }).code === "SESSION_EXPIRED";
}

export async function serviceMode(): Promise<"mock" | "live"> {
  const config = await request<{ data_mode: "mock" | "live" }>("/api/config");
  if (config.data_mode !== "mock" && config.data_mode !== "live") throw new Error("서비스 실행 모드를 확인할 수 없습니다.");
  return config.data_mode;
}

export async function startSavedRun(input: ReviewInput, files: Map<string, File>): Promise<{ session: Session; run: Run }> {
  let session: Session;
  try {
    session = await request<Session>("/api/session/heartbeat", { method: "POST" });
  } catch (error) {
    if (!(error instanceof Error) || ![401, 410].includes((error as Error & { status?: number }).status ?? 0)) throw error;
    session = await request<Session>("/api/session", { method: "POST" });
  }
  cachedSession = session;
  lastHeartbeat = Date.now();
  const form = new FormData();
  form.set("metadata", JSON.stringify(input));
  for (const [key, file] of files) form.set(key, file);
  const accepted = await request<{ review_id: string }>("/api/reviews", { method: "POST", body: form });
  const run = await request<Run>(`/api/reviews/${accepted.review_id}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_key: crypto.randomUUID() }),
  });
  localStorage.setItem(SAVED_RUN_KEY, run.run_id);
  return { session, run };
}

export async function readSavedRun(runId: string): Promise<ScenarioFile> {
  const run = await request<Run>(`/api/runs/${runId}`);
  if (run.run_id !== runId || !["mock", "live"].includes(run.data_mode)) throw new Error("저장된 실행 ID가 일치하지 않습니다.");
  const input = await request<ReviewInput>(`/api/reviews/${run.review_id}`);
  const result = run.result_available ? await request<Result>(`/api/runs/${runId}/result`) : null;
  if (result && (result.run_id !== runId || result.data_mode !== run.data_mode)) throw new Error("저장된 결과 ID가 일치하지 않습니다.");
  if (!cachedSession || Date.now() - lastHeartbeat >= 60_000) {
    cachedSession = await request<Session>("/api/session/heartbeat", { method: "POST" });
    lastHeartbeat = Date.now();
  }
  const session = cachedSession;
  return savedFrame(input, session, run, result);
}

export function savedFrame(input: ReviewInput, session: Session, run: Run, result: Result | null): ScenarioFile {
  if (session.data_mode !== run.data_mode) throw new Error("세션과 실행 모드가 일치하지 않습니다.");
  return parseScenarioFile({
    schema_version: "0.1.0",
    data_mode: run.data_mode,
    input,
    scenarios: [{ name: run.status, description: run.data_mode === "live" ? "서버에 저장된 실제 분석 실행입니다." : "서버에 저장된 모의 실행입니다. 실제 분석은 수행하지 않습니다.", session, run, result, error: null }],
  });
}

export function expiredFrame(input: ReviewInput = fixture.input, mode: "mock" | "live" = "mock"): ScenarioFile {
  return parseScenarioFile({
    schema_version: "0.1.0",
    data_mode: mode,
    input,
    scenarios: [{ name: "session-expired", description: "조회 기간이 끝났습니다.", session: { schema_version: "0.1.0", data_mode: mode, session_id: "expired", status: "expired", expires_at: new Date().toISOString() }, run: null, result: null, error: null }],
  });
}
