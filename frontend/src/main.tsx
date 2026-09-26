import { useEffect, useState } from "react";
import { AgentStart, About, Team } from "./AgentStart";
import { ReviewOverview } from "./ReviewOverview";
import { parseScenarioFile, type ScenarioFile } from "./scenario-file";
import PredictedStructure, { type PredictedView } from "./PredictedStructure";

// 개발 중에는 vite와 실행부가 다른 포트에 뜬다. 배포 시 같은 출처면 빈 문자열로 둔다.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8010";
import "./review-overview.css";
import { createRoot } from "react-dom/client";
import "./tokens.css";
import "./style.css";
import "./nvidia-theme.css";
import "./agent-experience.css";

/**
 * 이번 실행이 만든 예측 구조만 골라 화면에 넘길 모양으로 맞춘다.
 *
 * 공개 실험 구조는 여기서 다루지 않는다. 프런트가 이미 파일을 가지고
 * 있어서 받아올 필요가 없다.
 *
 * 사슬 대응이나 파일 해시가 없으면 그 구조는 건너뛴다. 3D로 띄울 때
 * 무엇을 어느 색으로 칠할지 정할 수 없기 때문이다. 짐작해서 칠하면
 * 틀린 잔기를 강조하게 된다.
 */
function predictedViews(result: any, candidates: any[]): PredictedView[] {
  const views: PredictedView[] = [];
  for (const s of result.structures ?? []) {
    if (s.kind !== "predicted") continue;
    const artifact = (result.artifacts ?? []).find(
      (a: any) => a.artifact_id === s.artifact_id,
    );
    if (!artifact?.sha256) continue;
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
      runId: result.run_id,
      artifactId: s.artifact_id,
      structureId: s.structure_id,
      candidateName:
        candidates.find((c) => c.candidate_id === s.candidate_id)?.name ??
        s.candidate_id,
      sha256: artifact.sha256,
      chains: chains as string[],
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
    [liveBusy, setLiveBusy] = useState(""),
    [liveError, setLiveError] = useState(""),
    [frameIndex, setFrameIndex] = useState(0),
    [playing, setPlaying] = useState(false),
    [candidate, setCandidate] = useState(""),
    [conditionKind, setConditionKind] = useState("core"),
    [expanded, setExpanded] = useState<string | null>(null);
  const scenario = scenarioFile?.scenarios[frameIndex];
  const live = scenarioFile?.data_mode === "live";
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
      apply(parseScenarioFile(JSON.parse(await file.text())), file.name);
    } catch (error) {
      setFileError(error instanceof Error ? error.message : "JSON 파일을 읽지 못했습니다.");
    }
  }
  function apply(parsed: ScenarioFile, label: string) {
    setScenarioFile(parsed);
    setFileName(label);
    setFrameIndex(0);
    setCandidate(parsed.input.candidates[0].candidate_id);
    setConditionKind("core");
    setPage(0);
  }
  async function runLive(preset: string) {
    setLiveError("");
    setFileError("");
    setScenarioFile(null);
    setPlaying(false);
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
      setPlaying(false);
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
          NVIDIA HACKATHON · TEAM PROJECT <span>{live ? "실제 실행" : "모의 데이터"}</span>
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
                  onRunLive={(preset) => void runLive(preset)}
                  liveBusy={liveBusy}
                  liveError={liveError}
                  onStart={() => {
                    setFrameIndex(0);
                    setPlaying(true);
                    go(1);
                  }}
                />
              ) : scenario && scenarioFile ? (
                <>
                  <div className="request-context">
                    <span>{live ? "실제 실행" : "업로드한 검토"}</span>
                    <p>{fileName}</p>
                    <small>{live ? "실제 분석 결과" : "모의 재생 · 실제 분석 아님"}</small>
                  </div>
                  <div className="workspace-title">
                    <div>
                      <div className="eyebrow">HER2 REVIEW / 0{page + 1}</div>
                      <h1>
                        {page === 1
                          ? "어디까지 확인했을까요?"
                          : page === 2
                            ? "구조와 근거, 함께 살펴보기."
                            : "근거를 다음 질문으로."}
                      </h1>
                      <p>
                        {page === 1
                          ? "후보별로 진행한 단계와 아직 확인하지 못한 이유를 살펴보세요."
                          : page === 2
                            ? "후보와 구조 조건을 선택하고, 각 근거의 확인 범위를 살펴보세요."
                            : "검토 의견과 미확인 사항을 함께 확인하세요."}
                      </p>
                    </div>
                    <span className="tag">기록 {frameIndex + 1} / {scenarioFile.scenarios.length}{playing ? " · 모의 재생 중" : ""}{live ? " · 실제 실행" : ""}</span>
                  </div>
                  <div className="notice">
                    <span className="tag">{live ? "실제 실행" : "모의 재생"} · {labels[scenario.name] ?? scenario.name}</span>{" "}
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
                          <div className="section-heading">
                            <h2>후보별 진행</h2>
                            <span className="tag">
                              {labels[scenario.run.status]}
                            </span>
                          </div>
                          <div className="two-col">
                            {scenario.run.candidates.map((c) => (
                              <section className="panel" key={c.candidate_id}>
                                <div className="section-heading">
                                  <h3>{scenarioFile.input.candidates.find((item) => item.candidate_id === c.candidate_id)?.name ?? c.candidate_id}</h3>
                                  {!live && (
                                    <span className="caption">
                                      실제 항체 아님
                                    </span>
                                  )}
                                </div>
                                <ol className="timeline">
                                  {c.steps.map((s) => (
                                    <li key={s.step_id} data-status={s.status}>
                                      <span className="step-dot" />
                                      <div>
                                        {labels[s.step_id]}
                                        {s.reason && <small>{s.reason}</small>}
                                      </div>
                                      <span className="caption">
                                        {labels[s.status]}
                                      </span>
                                    </li>
                                  ))}
                                </ol>
                                {c.reason && <p>{c.reason}</p>}
                              </section>
                            ))}
                          </div>
                          {scenario.run.error && (
                            <p role="alert" className="notice">
                              {scenario.run.error.message} · 자동 재실행하지
                              않습니다.
                            </p>
                          )}
                          <div className="actions end">
                            <span className="caption">{live ? "실제 분석을 실행한 결과입니다." : "저장된 상태를 보여줍니다. 실제 분석은 실행되지 않습니다."}</span>
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
                      <div className="comparison-toolbar">
                        <div className="segmented" aria-label="후보 선택">
                          {scenarioFile.input.candidates.map((c) => (
                            <button
                              key={c.candidate_id}
                              aria-pressed={candidate === c.candidate_id}
                              onClick={() => {
                                setCandidate(c.candidate_id);
                                setExpanded(null);
                              }}
                            >
                              {c.name}
                            </button>
                          ))}
                        </div>
                        <label>
                          구조 조건
                          <select
                            value={conditionKind}
                            onChange={(e) => {
                              setConditionKind(e.target.value);
                              setExpanded(null);
                            }}
                          >
                            <option value="core">HER2–항체 중심</option>
                            <option value="context">당쇄·주변 구조 포함</option>
                          </select>
                        </label>
                      </div>
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
                      {(() => {
                        const views = predictedViews(
                          result,
                          scenarioFile.input.candidates,
                        );
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
                      <section className="download-row">
                        <div>
                          <h3>결과를 이어서 검토하기</h3>
                          <p>
                            이번 실행이 만든 예측 구조만 내려받을 수 있습니다.
                            공개 실험 구조는 RCSB에서 직접 받으세요.
                          </p>
                        </div>
                        <div className="actions">
                          {result.artifacts.map((a: any) => {
                            // 운영부가 내보내는 것은 work_dir에 쓴 예측 구조뿐이다.
                            // 공개 실험 구조는 저장소 파일이라 그 경로로 나가지 않는다.
                            const predicted = (result.structures ?? []).some(
                              (s: any) =>
                                s.artifact_id === a.artifact_id &&
                                s.kind === "predicted",
                            );
                            if (!predicted)
                              return (
                                <button
                                  className="secondary"
                                  disabled
                                  key={a.artifact_id}
                                  title="공개 실험 구조는 RCSB에서 받으세요."
                                >
                                  {a.format.toUpperCase()} ↓
                                </button>
                              );
                            return (
                              <a
                                className="secondary"
                                key={a.artifact_id}
                                href={`${API_BASE}/api/runs/${result.run_id}/artifacts/${a.artifact_id}`}
                                download={a.file_name ?? `${a.artifact_id}.cif`}
                              >
                                {a.format.toUpperCase()} ↓
                              </a>
                            );
                          })}
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
          <span>독립 해커톤 프로젝트 · {live ? "실제 분석 결과" : "모의 화면"} · NVIDIA 공식 제품 아님</span>
        </footer>
      </div>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
