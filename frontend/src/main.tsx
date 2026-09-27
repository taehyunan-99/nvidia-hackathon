import { useEffect, useState } from "react";
import { runFromSearch, runUrl } from "./run-location";
import { AgentStart, About, Team } from "./AgentStart";
import { AgentActivity } from "./AgentActivity";
import { ReviewOverview } from "./ReviewOverview";
import { ReportView } from "./ReportView";
import { parseScenarioFile, type ReviewInput, type ScenarioFile } from "./scenario-file";
import PredictedStructure, { type PredictedView } from "./PredictedStructure";
import { expiredFrame, isSessionExpired, savedFrame, readSavedRun, SAVED_RUN_KEY, serviceMode, startSavedRun } from "./persistent-mock";

// 개발 중에는 vite와 실행부가 다른 포트에 뜬다. 배포 시 같은 출처면 빈 문자열로 둔다.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8010";
import "./review-overview.css";
import { createRoot } from "react-dom/client";
import "./tokens.css";
import "./style.css";
import "./nvidia-theme.css";
import "./agent-experience.css";

/**
 * 이번 실행에 연결된 실험·예측 구조를 검증된 파일 참조로 표시한다.
 *
 * 사슬 대응이나 파일 해시가 없으면 그 구조는 건너뛴다. 3D로 띄울 때
 * 무엇을 어느 색으로 칠할지 정할 수 없기 때문이다. 짐작해서 칠하면
 * 틀린 잔기를 강조하게 된다.
 */
function resultViews(result: any, candidates: any[]): PredictedView[] {
  const views: PredictedView[] = [];
  for (const s of result.structures ?? []) {
    if (s.kind !== "predicted" && s.kind !== "experimental") continue;
    const artifact = (result.artifacts ?? []).find(
      (a: any) => a.artifact_id === s.artifact_id,
    );
    if (artifact?.status !== "ready" || !artifact.sha256) continue;
    const byRole = (role: string) =>
      (s.chain_mapping ?? []).find((c: any) => c.role === role)?.label_asym_id;
    const chains = [byRole("target"), byRole("heavy"), byRole("light")];
    if (chains.some((c) => !c)) continue;
    const contact = (result.evidence ?? []).find(
      (e: any) =>
        e.structure_id === s.structure_id &&
        e.topic === "interface_contact_residues",
    );
    views.push({
      kind: s.kind,
      candidateId: s.candidate_id,
      runId: result.run_id,
      artifactId: s.artifact_id,
      structureId: s.structure_id,
      candidateName:
        candidates.find((c) => c.candidate_id === s.candidate_id)?.name ??
        s.candidate_id,
      source: s.source,
      sha256: artifact.sha256,
      chains: chains as string[],
      contextChains: (s.chain_mapping ?? []).filter((c: any) => c.role === "context").map((c: any) => c.label_asym_id).filter(Boolean),
      residues: contact?.residues ?? [],
      unmeasuredReason:
        contact && contact.measurement_state === "measured"
          ? null
          : (contact?.reason ?? "접촉 잔기 근거가 결과에 없습니다."),
    });
  }
  return views;
}

const pages = ["검토 입력", "분석 진행", "구조 비교", "결과 보고"];
function ThemeSelector() {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme);
  function chooseTheme(next: string) {
    document.documentElement.dataset.theme = next;
    setTheme(next);
    try {
      localStorage.setItem("her2-theme", next);
    } catch {
      // Theme selection still works when browser storage is unavailable.
    }
  }
  return (
    <div className="theme-selector" role="group" aria-label="화면 테마">
      {(["light", "dark"] as const).map((value) => (
        <button
          key={value}
          aria-pressed={theme === value}
          onClick={() => chooseTheme(value)}
        >
          {value === "light" ? "라이트" : "다크"}
        </button>
      ))}
    </div>
  );
}

function App() {
  const [section, setSection] = useState<"analysis" | "about" | "team">(
    "analysis",
  );
  const [savedRunId, setSavedRunId] = useState(() => {
    const fromUrl = runFromSearch(location.search);
    return new URLSearchParams(location.search).has("run") ? fromUrl.runId : localStorage.getItem(SAVED_RUN_KEY);
  });
  const [page, setPage] = useState(savedRunId ? 1 : 0),
    [scenarioFile, setScenarioFile] = useState<ScenarioFile | null>(null),
    [fileName, setFileName] = useState(""),
    [liveBusy, setLiveBusy] = useState(""),
    [liveError, setLiveError] = useState(""),
    [mockBusy, setMockBusy] = useState(false),
    [mockError, setMockError] = useState(() => runFromSearch(location.search).error),
    [savedMode, setSavedMode] = useState<"mock" | "live" | null>(null),
    [candidate, setCandidate] = useState(""),
    [conditionKind, setConditionKind] = useState("core"),
    [expanded, setExpanded] = useState<string | null>(null);
  const scenario = scenarioFile?.scenarios[0];
  const live = scenarioFile?.data_mode === "live" || (!scenarioFile && savedMode === "live" && import.meta.env.VITE_PERSISTENT_SERVICE === "1");
  const connecting = import.meta.env.VITE_PERSISTENT_SERVICE === "1" && !scenarioFile && savedMode === null;
  const persistedRun = fileName.startsWith("저장형 ");
  const result = scenario?.result;
  const expired = scenario?.session.status === "expired";
  function go(n: number) {
    setSection("analysis");
    setPage(n >= 2 && (!result || expired) ? 1 : n);
    setExpanded(null);
  }
  function apply(parsed: ScenarioFile, label: string) {
    setScenarioFile(parsed);
    setFileName(label);
    setCandidate(parsed.input.candidates[0].candidate_id);
    setConditionKind("core");
    setPage(0);
  }
  async function runLive(preset: string) {
    localStorage.removeItem(SAVED_RUN_KEY);
    const url = new URL(location.href);
    url.searchParams.delete("run");
    history.replaceState(null, "", url);
    setSavedRunId(null);
    setLiveError("");
    setScenarioFile(null);
    setLiveBusy(preset);
    try {
      const response = await fetch(`${API_BASE}/api/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset }),
      });
      if (!response.ok) {
        // 실패를 성공한 분석으로 보이지 않게 한다. 본문을 그대로 보여준다.
        throw new Error(`실행부가 ${response.status}로 응답했습니다. ${await response.text()}`.slice(0, 400));
      }
      apply(parseScenarioFile(await response.json()), `실제 실행 · ${preset}`);
      // 실제 실행은 프레임이 하나다. 모의 시나리오처럼 자동 재생하지 않고
      // 방금 돌아간 단계를 바로 보여준다.
      setSection("analysis");
      setPage(1);
    } catch (error) {
      setLiveError(
        error instanceof Error
          ? `${error.message} (실행부가 ${API_BASE}에서 떠 있는지 확인하세요.)`
          : "실행부를 부르지 못했습니다.",
      );
    } finally {
      setLiveBusy("");
    }
  }
  async function runSaved(input: ReviewInput, files: Map<string, File>) {
    setMockError("");
    setMockBusy(true);
    try {
      const { session, run } = await startSavedRun(input, files);
      setSavedMode(run.data_mode as "mock" | "live");
      apply(savedFrame(input, session, run, null), run.data_mode === "live" ? "저장형 실제 실행" : "저장형 모의 실행");
      setPage(1);
      history.pushState(null, "", runUrl(location.href, run.run_id));
      setSavedRunId(run.run_id);
    } catch (error) {
      setMockError(error instanceof Error ? error.message : "검토 실행을 접수하지 못했습니다.");
    } finally {
      setMockBusy(false);
    }
  }
  useEffect(() => {
    if (import.meta.env.VITE_PERSISTENT_SERVICE !== "1") return;
    void serviceMode().then(setSavedMode).catch(() => setMockError("서비스 실행 모드를 확인하지 못했습니다."));
  }, []);
  useEffect(() => {
    function navigate() {
      const target = runFromSearch(location.search);
      setScenarioFile(null);
      setCandidate("");
      setMockError(target.error);
      setSavedRunId(target.runId);
      setPage(target.runId ? 1 : 0);
    }
    window.addEventListener("popstate", navigate);
    return () => window.removeEventListener("popstate", navigate);
  }, []);
  useEffect(() => {
    if (!savedRunId) return;
    history.replaceState(null, "", runUrl(location.href, savedRunId));
    let active = true;
    async function refresh() {
      try {
        const current = await readSavedRun(savedRunId!);
        if (!active) return;
        setScenarioFile(current);
        setMockError("");
        setSavedMode(current.data_mode as "mock" | "live");
        setFileName(current.data_mode === "live" ? "저장형 실제 실행" : "저장형 모의 실행");
        setCandidate((previous) => previous || current.input.candidates[0].candidate_id);
      } catch (error) {
        if (!active) return;
        if (isSessionExpired(error)) {
          setScenarioFile((previous) => previous ? expiredFrame(previous.input, previous.data_mode === "live" ? "live" : "mock") : null);
          setFileName(savedMode === "live" ? "저장형 실제 실행" : "저장형 모의 실행");
          setMockError("조회 기간이 끝났습니다. 새 검토를 시작하세요.");
          localStorage.removeItem(SAVED_RUN_KEY);
          setPage(0);
        } else {
          setMockError(error instanceof Error ? error.message : "저장된 실행을 조회하지 못했습니다.");
        }
        if (isSessionExpired(error)) setSavedRunId(null);
        if (error instanceof Error && (error as Error & { status?: number }).status === 404) {
          setScenarioFile(null);
          setSavedRunId(null);
          setMockError("이 세션에서 조회할 수 없는 실행 주소입니다.");
          setPage(0);
        }
        if (error instanceof Error && (error as Error & { status?: number }).status === 401) {
          localStorage.removeItem(SAVED_RUN_KEY);
          setSavedRunId(null);
          setScenarioFile(null);
          setMockError("이 실행을 조회하려면 원래 브라우저 세션이 필요합니다.");
          setPage(0);
        }
      }
    }
    void refresh();
    const interval = window.setInterval(() => void refresh(), 2000);
    return () => { active = false; window.clearInterval(interval); };
  }, [savedRunId]);
  return (
    <>
      <a className="skip" href="#main">
        본문으로 이동
      </a>
      <header>
        <button
          className="brand"
          onClick={() => go(0)}
          aria-label="검토 입력으로"
        >
          <span className="brand-symbol">✳</span> Bio-3
          <span className="brand-divider" />{" "}
          <span className="brand-sub">항체 후보 검토</span>
        </button>
        <nav className="site-tabs" aria-label="주 메뉴">
          <button
            aria-current={section === "analysis" ? "page" : undefined}
            onClick={() => setSection("analysis")}
          >
            분석
          </button>
          <button
            aria-current={section === "about" ? "page" : undefined}
            onClick={() => setSection("about")}
          >
            소개
          </button>
          <button
            aria-current={section === "team" ? "page" : undefined}
            onClick={() => setSection("team")}
          >
            팀
          </button>
        </nav>
        <span className="prototype">
          NVIDIA HACKATHON · TEAM PROJECT <span>{connecting ? "연결 확인 중" : live ? "실제 실행" : "모의 데이터"}</span>
        </span>
        <ThemeSelector />
      </header>
      <div
        className={`shell ${section === "about" ? "landing-shell" : page === 0 ? "agent-shell" : "workspace-shell"}`}
      >
        {section === "analysis" && page > 0 && (
          <nav aria-label="검토 단계">
            {pages.map((p, i) => (
              <button
                key={p}
                onClick={() => go(i)}
                disabled={i >= 2 && (!result || expired)}
                aria-current={page === i ? "page" : undefined}
              >
                <span>0{i + 1}</span>
                {p}
              </button>
            ))}
          </nav>
        )}
        <main id="main">
          {section === "about" ? (
            <About onStart={() => go(0)} />
          ) : section === "team" ? (
            <Team />
          ) : (
            <>
              {page === 0 ? (
                <AgentStart
                  onRunLive={(preset) => void runLive(preset)}
                  onRunMock={(input, files) => void runSaved(input, files)}
                  savedMode={savedMode}
                  mockBusy={mockBusy}
                  mockError={mockError}
                  liveBusy={liveBusy}
                  liveError={liveError}
                />
              ) : scenario && scenarioFile ? (
                <>
                  <div className="request-context">
                    <span>{live ? "실제 실행" : persistedRun ? "저장된 검토" : "업로드한 검토"}</span>
                    <p>{fileName}</p>
                    <small>{live ? "실제 분석 결과" : persistedRun ? "저장형 모의 실행 · 실제 분석 아님" : "모의 재생 · 실제 분석 아님"}</small>
                  </div>
                  {persistedRun && mockError && <p role="alert" className="notice">{mockError}</p>}
                  <div className="workspace-title">
                    <div>
                      <div className="eyebrow">Bio-3 REVIEW / 0{page + 1}</div>
                      <h1>
                        {page === 1
                          ? "분석 진행 현황"
                          : page === 2
                            ? "구조와 근거 살펴보기"
                            : "후보 검토 결과"}
                      </h1>
                      <p>
                        {page === 1
                          ? "후보별 현재 단계와 결과를 확인할 수 있는지 살펴보세요."
                          : page === 2
                            ? "후보·조건을 바꾸며 확인 가능한 근거와 부족한 자료를 살펴보세요."
                            : "실행 범위와 후보별 의견, 근거·한계·다음 질문을 확인하세요."}
                      </p>
                    </div>
                    <span className="tag">기록 {1} / {scenarioFile.scenarios.length}{live ? " · 실제 실행" : persistedRun ? " · 저장형 모의 실행" : ""}</span>
                  </div>
                  {expired ? (
                    <section className="empty panel">
                      <h2>임시 조회 기간이 끝났습니다</h2>
                      <p>
                        이전 입력과 결과는 표시하지 않습니다. 새 검토를
                        시작해주세요.
                      </p>
                      <button
                        className="primary"
                        onClick={() => {
                          go(0);
                        }}
                      >
                        새 검토로 돌아가기 ↗
                      </button>
                    </section>
                  ) : page === 1 ? (
                    <>
                      {scenario.error && (
                        <div className="notice" role="alert">
                          {scenario.error.message}
                          <button
                            onClick={() => {
                              go(0);
                            }}
                          >
                            파일 입력으로
                          </button>
                        </div>
                      )}
                      {scenario.run && (
                        <>
                          <AgentActivity key={scenario.run.run_id} run={scenario.run} input={scenarioFile.input} readError={mockError} />
                          {scenario.run.error && (
                            <p role="alert" className="notice">
                              {scenario.run.error.message} · 자동 재실행하지
                              않습니다.
                            </p>
                          )}
                          <div className="actions end">
                            <span className="caption">{live ? "실제 분석을 실행한 결과입니다." : "저장된 상태를 보여줍니다. 실제 분석은 실행되지 않습니다."}</span>
                            <button className="primary" disabled={!scenario.run.result_available} onClick={() => go(2)}>비교 결과 보기 ↗</button>
                          </div>
                        </>
                      )}
                    </>
                  ) : !result ? (
                    <section className="empty panel">
                      <h2>아직 확인할 결과가 없습니다</h2>
                      <p>
                        {scenario.error?.message ??
                          "진행 상태와 미완료 이유를 먼저 확인하세요."}
                      </p>
                      <button className="secondary" onClick={() => go(1)}>
                        진행 상태 보기
                      </button>
                    </section>
                  ) : page === 2 ? (
                    <>
                      <ReviewOverview
                        result={result}
                        input={scenarioFile.input}
                        views={resultViews(result, scenarioFile.input.candidates)}
                        apiBase={API_BASE}
                        candidate={candidate}
                        conditionKind={conditionKind}
                        evidenceId={expanded}
                        onSelect={(id, kind, evidenceId) => {
                          setCandidate(id);
                          setConditionKind(kind);
                          setExpanded(evidenceId);
                        }}
                      />
                      <div className="actions end">
                        <button className="primary" onClick={() => go(3)}>
                          검토 보고 보기 ↗
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <ReportView result={result} input={scenarioFile.input} run={scenario.run} persistedMock={persistedRun} apiBase={API_BASE} />
                      {(() => {
                        const views = resultViews(
                          result,
                          scenarioFile.input.candidates,
                        ).filter((view) => view.kind === "predicted");
                        if (!views.length) return null;
                        return (
                          <section aria-label="예측 구조 3D">
                            <div className="section-heading">
                              <div>
                                <h3>이번 실행이 만든 예측 구조</h3>
                                <span className="caption">
                                  NVIDIA Boltz-2 응답을 그대로 표시합니다
                                </span>
                              </div>
                            </div>
                            <div className="two-col">
                              {views.map((v) => (
                                <PredictedStructure
                                  key={v.artifactId}
                                  apiBase={API_BASE}
                                  view={v}
                                />
                              ))}
                            </div>
                          </section>
                        );
                      })()}
                    </>
                  )}
                </>
              ) : <p className="notice" role="status">저장된 검토를 불러오는 중입니다.</p>}
            </>
          )}
        </main>
        <footer>
          <span>Bio-3 · Evidence-led antibody review</span>
          <span>독립 해커톤 프로젝트 · {connecting ? "연결 확인 중" : live ? "실제 분석 결과" : "모의 화면"} · NVIDIA 공식 제품 아님</span>
        </footer>
      </div>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
