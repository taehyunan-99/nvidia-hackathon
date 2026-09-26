import { useEffect, useState } from "react";
import { AgentStart, About, Team } from "./AgentStart";
import { ReviewOverview } from "./ReviewOverview";
import { parseScenarioFile, type Scenario, type ScenarioFile } from "./scenario-file";
import "./review-overview.css";
import { createRoot } from "react-dom/client";
import "./tokens.css";
import "./style.css";
import "./nvidia-theme.css";
import "./agent-experience.css";

const pages = ["검토 입력", "분석 진행", "구조 비교", "결과 보고"];
const labels: Record<string, string> = {
  queued: "대기",
  running: "진행 중",
  completed: "종료",
  partial: "부분 결과",
  failed: "실행 실패",
  interrupted: "실행 중단",
  pending: "대기",
  skipped: "생략",
  held: "판단 보류",
  "scientific-hold": "판단 보류",
  "session-expired": "세션 만료",
  "input-invalid": "입력 오류",
  input_mapping: "입력·자료 대응",
  evidence_review: "근거 검토",
  prediction: "필요한 구조 예측",
  structure_comparison: "구조 비교",
  reporting: "보고서 정리",
  not_assessed: "미검토",
  hold: "보류",
  needs_confirmation: "추가 확인",
  reviewable: "후속 실험 검토 가능",
  unknown: "미확인",
  not_run: "미실행",
  measured: "측정됨",
  not_applicable: "해당 없음",
};
type RunCandidate = NonNullable<Scenario["run"]>["candidates"][number];

function CandidateProgress({ candidate, name }: { candidate: RunCandidate; name: string }) {
  const focus = candidate.steps.find((step) => step.status === "failed" || step.status === "held")
    ?? candidate.steps.find((step) => step.step_id === candidate.current_step)
    ?? candidate.steps.find((step) => step.status === "skipped")
    ?? candidate.steps.slice().reverse().find((step) => step.status === "completed");
  const notableSteps = candidate.steps.filter((step) => step.status === "failed" || step.status === "held" || step.status === "skipped");
  const stagePosition = candidate.status === "completed"
    ? `${candidate.steps.length}단계 기록 종료`
    : focus
      ? `${candidate.steps.findIndex((step) => step.step_id === focus.step_id) + 1} / ${candidate.steps.length} 단계`
      : "시작 전";
  const statusLine = candidate.status === "queued"
    ? "분석 대기 중"
    : candidate.status === "interrupted"
      ? `${focus ? labels[focus.step_id] : "분석"} · 실행 중단`
      : focus?.status === "held"
        ? `${labels[focus.step_id]} · 판단 보류`
        : focus?.status === "failed"
          ? `${labels[focus.step_id]} · 실행 실패`
          : candidate.status === "completed"
            ? "검토 기록 종료"
            : focus
              ? `${labels[focus.step_id]} · ${labels[focus.status]}`
              : labels[candidate.status];

  return (
    <section className="panel candidate-progress" data-status={candidate.status}>
      <div className="candidate-progress-heading">
        <h3>{name}</h3>
        <span className="tag">{labels[candidate.status]}</span>
      </div>
      <div className="stage-track" aria-hidden="true">
        {candidate.steps.map((step) => <span key={step.step_id} data-status={candidate.status === "interrupted" && step.status === "running" ? "interrupted" : step.status} />)}
      </div>
      <div className="progress-status" role="status" aria-live="polite">
        <div className="progress-status-head">
          <span className="progress-position">{stagePosition}</span>
          <strong>{statusLine}</strong>
        </div>
        <p>{candidate.reason ?? (focus?.status === "held" || focus?.status === "failed" || focus?.status === "skipped" ? focus.reason : null) ?? (candidate.status === "completed"
          ? "기록된 단계가 끝났습니다. 결과에서 근거와 한계를 확인해 주세요."
          : candidate.status === "queued"
            ? "아직 시작된 단계가 없습니다."
            : focus?.reason ?? "다음 기록에서 단계 상태가 바뀝니다.")}</p>
      </div>
      {notableSteps.some((step) => step !== focus) && (
        <div className="progress-exceptions">
          {notableSteps.filter((step) => step !== focus).map((step) => (
            <p key={step.step_id}><strong>{labels[step.step_id]} · {labels[step.status]}</strong>{step.reason && ` — ${step.reason}`}</p>
          ))}
        </div>
      )}
      <details className="progress-details">
        <summary>전체 단계 기록 보기</summary>
        <ol>
          {candidate.steps.map((step, index) => (
            <li key={step.step_id}>
              <strong>{index + 1}. {labels[step.step_id]} · {candidate.status === "interrupted" && step.status === "running" ? "중단 시점" : labels[step.status]}</strong>
              {step.reason && <span>{step.reason}</span>}
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
}
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
  const [page, setPage] = useState(0),
    [scenarioFile, setScenarioFile] = useState<ScenarioFile | null>(null),
    [fileName, setFileName] = useState(""),
    [fileError, setFileError] = useState(""),
    [frameIndex, setFrameIndex] = useState(0),
    [playing, setPlaying] = useState(false),
    [candidate, setCandidate] = useState(""),
    [conditionKind, setConditionKind] = useState("core"),
    [expanded, setExpanded] = useState<string | null>(null);
  const scenario = scenarioFile?.scenarios[frameIndex];
  const result = scenario?.result;
  const expired = scenario?.session.status === "expired";
  function go(n: number) {
    setSection("analysis");
    if (n === 0) setPlaying(false);
    setPage(n >= 2 && (playing || !result || expired) ? 1 : n);
    setExpanded(null);
  }
  async function loadFile(file: File) {
    setFileError("");
    setScenarioFile(null);
    setPlaying(false);
    if (file.size > 2_000_000) {
      setFileError("2MB 이하의 시나리오 JSON을 선택해 주세요.");
      return;
    }
    try {
      const parsed = parseScenarioFile(JSON.parse(await file.text()));
      setScenarioFile(parsed);
      setFileName(file.name);
      setFrameIndex(0);
      setCandidate(parsed.input.candidates[0].candidate_id);
      setConditionKind("core");
      setPage(0);
    } catch (error) {
      setFileError(error instanceof Error ? error.message : "JSON 파일을 읽지 못했습니다.");
    }
  }
  function advance() {
    if (!scenarioFile || frameIndex >= scenarioFile.scenarios.length - 1) return;
    setFrameIndex(frameIndex + 1);
    setExpanded(null);
    setConditionKind("core");
    setPage(1);
  }
  useEffect(() => {
    if (!playing || !scenarioFile) return;
    if (frameIndex >= scenarioFile.scenarios.length - 1) {
      setPlaying(false);
      return;
    }
    const timeout = window.setTimeout(advance, 1800);
    return () => window.clearTimeout(timeout);
  }, [playing, scenarioFile, frameIndex]);
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
          <span className="brand-symbol">✳</span> HER2
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
          NVIDIA HACKATHON · TEAM PROJECT <span>모의 데이터</span>
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
                disabled={i >= 2 && (playing || !result || expired)}
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
                  input={scenarioFile?.input ?? null}
                  fileName={fileName}
                  error={fileError}
                  onFile={(file) => void loadFile(file)}
                  onStart={() => {
                    setFrameIndex(0);
                    setPlaying(true);
                    go(1);
                  }}
                />
              ) : scenario && scenarioFile ? (
                <>
                  <div className="request-context">
                    <span>업로드한 검토</span>
                    <p>{fileName}</p>
                    <small>모의 재생 · 실제 분석 아님</small>
                  </div>
                  <div className="workspace-title">
                    <div>
                      <div className="eyebrow">HER2 REVIEW / 0{page + 1}</div>
                      <h1>
                        {page === 1
                          ? "분석 진행 현황"
                          : page === 2
                            ? "구조와 근거 살펴보기"
                            : "근거를 다음 질문으로."}
                      </h1>
                      <p>
                        {page === 1
                          ? "후보별 현재 단계와 결과를 확인할 수 있는지 살펴보세요."
                          : page === 2
                            ? "후보·조건을 바꾸며 확인 가능한 근거와 부족한 자료를 살펴보세요."
                            : "검토 의견과 미확인 사항을 함께 확인하세요."}
                      </p>
                    </div>
                    <span className="tag">기록 {frameIndex + 1} / {scenarioFile.scenarios.length}{playing ? " · 모의 재생 중" : ""}</span>
                  </div>
                  <div className="notice">
                    <span className="tag">모의 재생 · {labels[scenario.name] ?? scenario.name}</span>{" "}
                    {scenario.description}
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
                          <div className="section-heading progress-heading">
                            <div>
                              <h2>후보별 진행</h2>
                              <p>막대는 단계의 기록 상태를 나타냅니다. 완료율이나 남은 시간을 뜻하지 않습니다.</p>
                            </div>
                            <div className="progress-heading-status">
                              <span className="tag">{labels[scenario.run.status]}</span>
                              <span className="tag">{scenario.run.result_available ? "비교 결과 있음" : "비교 결과 없음"}</span>
                            </div>
                          </div>
                          <div className="candidate-progress-list">
                            {scenario.run.candidates.map((c) => (
                              <CandidateProgress
                                key={c.candidate_id}
                                candidate={c}
                                name={scenarioFile.input.candidates.find((item) => item.candidate_id === c.candidate_id)?.name ?? c.candidate_id}
                              />
                            ))}
                          </div>
                          {scenario.run.error && (
                            <p role="alert" className="notice">
                              {scenario.run.error.message} · 자동 재실행하지
                              않습니다.
                            </p>
                          )}
                          <div className="actions end">
                            <span className="caption">저장된 상태를 보여줍니다. 실제 분석은 실행되지 않습니다.</span>
                            {frameIndex < scenarioFile.scenarios.length - 1 ? (
                              <button className="primary" onClick={advance}>다음 기록 보기 →</button>
                            ) : (
                              <button className="primary" disabled={playing || !scenario.run.result_available} onClick={() => go(2)}>비교 결과 보기 ↗</button>
                            )}
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
                      <section className="report-intro">
                        <div>
                          <span className="eyebrow">REVIEW SUMMARY</span>
                          <h2>
                            검토의 끝은,
                            <br />더 명확한 다음 질문.
                          </h2>
                        </div>
                        <p>
                          실험에서 확인한 사실, 계산 결과, 미확인을 구분합니다.
                          <br />
                          현재 의견은 화면 검토용이며 실제 후보 판정이 아닙니다.
                        </p>
                      </section>
                      <div className="two-col">
                        {result.opinions.map((o) => (
                          <article className="panel" key={o.opinion_id}>
                            <div className="section-heading">
                              <h3>{scenarioFile.input.candidates.find((item) => item.candidate_id === o.candidate_id)?.name ?? o.candidate_id}</h3>
                              <span className="tag">
                                {labels[o.decision] ?? o.decision}
                              </span>
                            </div>
                            <p>{o.reason}</p>
                            <h4>다음 확인 항목</h4>
                            <ul>
                              {o.follow_up_questions.map((q) => (
                                <li key={q}>{q}</li>
                              ))}
                            </ul>
                            <details>
                              <summary>근거와 해석 범위</summary>
                              <p>연결 근거: {o.evidence_ids.join(", ")}</p>
                              {o.limitations.map((l) => (
                                <p key={l}>{l}</p>
                              ))}
                            </details>
                          </article>
                        ))}
                      </div>
                      <section className="download-row">
                        <div>
                          <h3>결과를 이어서 검토하기</h3>
                          <p>실제 파일이 생성되면 내려받을 수 있습니다.</p>
                        </div>
                        <div className="actions">
                          {result.artifacts.map((a) => (
                            <button
                              className="secondary"
                              disabled
                              key={a.artifact_id}
                              title={a.reason ?? "파일 미제공"}
                            >
                              {a.format.toUpperCase()} ↓
                            </button>
                          ))}
                        </div>
                      </section>
                    </>
                  )}
                </>
              ) : null}
            </>
          )}
        </main>
        <footer>
          <span>HER2 · Evidence-led antibody review</span>
          <span>독립 해커톤 프로젝트 · 모의 화면 · NVIDIA 공식 제품 아님</span>
        </footer>
      </div>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
