import { useState } from "react";
import { AgentStart, About, Team } from "./AgentStart";
import { ReviewOverview } from "./ReviewOverview";
import "./review-overview.css";
import { createRoot } from "react-dom/client";
import fixtures from "../../docs/frontend-hosting/fixtures/scenarios.json";
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
function App() {
  const [section, setSection] = useState<"analysis" | "about" | "team">(
    "analysis",
  );
  const [reviewQuestion, setReviewQuestion] = useState("");
  const [page, setPage] = useState(
      new URLSearchParams(location.search).get("view") === "compare" ? 2 : 0,
    ),
    [comparisonLayout, setComparisonLayout] = useState<"original" | "proposed">(
      "proposed",
    ),
    [scenarioName, setScenarioName] = useState("completed"),
    [candidate, setCandidate] = useState("mock-candidate-a"),
    [conditionKind, setConditionKind] = useState("core"),
    [expanded, setExpanded] = useState<string | null>(null),
    [inputOpen, setInputOpen] = useState(false),
    [confirmed, setConfirmed] = useState(false),
    [message, setMessage] = useState("");
  const scenario = fixtures.scenarios.find((s) => s.name === scenarioName)!;
  const result = scenario.result;
  const expired = scenario.session.status === "expired";
  const conditions =
    result?.conditions.filter(
      (c) => c.candidate_id === candidate && c.kind === conditionKind,
    ) ?? [];
  const evidence =
    result?.evidence.filter((e) =>
      conditions.some((c) => c.condition_id === e.condition_id),
    ) ?? [];
  function go(n: number) {
    setSection("analysis");
    setPage(n);
    setMessage("");
    setExpanded(null);
  }
  function chooseScenario(name: string) {
    setScenarioName(name);
    setExpanded(null);
    setConditionKind("core");
    setCandidate("mock-candidate-a");
  }
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
                <>
                  <AgentStart
                    onInput={() => setInputOpen(!inputOpen)}
                    onStart={(question, scenario) => {
                      setReviewQuestion(question);
                      chooseScenario(scenario);
                      go(1);
                    }}
                  />
                  {inputOpen && (
                    <section className="panel input-panel">
                      <div className="section-heading">
                        <div>
                          <div className="eyebrow">REVIEW INPUT</div>
                          <h2>검토할 자료를 준비하세요</h2>
                        </div>
                        <span className="tag">입력 UI 미리보기</span>
                      </div>
                      <p>
                        입력값은 전송·분석되지 않습니다. 예제 탐색에는 별도의
                        합성 자료만 사용합니다.
                      </p>
                      <form
                        onSubmit={(e) => {
                          e.preventDefault();
                          setMessage(
                            "입력 형식을 확인했습니다. 실제 접수·분석 연결은 준비 중입니다.",
                          );
                        }}
                      >
                        <label>
                          HER2 식별자 또는 FASTA
                          <textarea
                            required
                            placeholder="공개 표적 식별자 또는 FASTA"
                          />
                        </label>
                        <div className="two-col">
                          {[1, 2].map((n) => (
                            <fieldset key={n}>
                              <legend>후보 {n}</legend>
                              <label>
                                후보 이름
                                <input required />
                              </label>
                              <label>
                                중쇄 FASTA
                                <textarea required placeholder=">heavy_chain" />
                              </label>
                              <label>
                                경쇄 FASTA
                                <textarea required placeholder=">light_chain" />
                              </label>
                            </fieldset>
                          ))}
                        </div>
                        <label className="check">
                          <input
                            type="checkbox"
                            checked={confirmed}
                            onChange={(e) => setConfirmed(e.target.checked)}
                            required
                          />
                          공개 자료만 사용합니다.
                        </label>
                        <div className="actions">
                          <button className="primary" type="submit">
                            입력 확인
                          </button>
                          <span className="caption">
                            파일 업로드·세 번째 후보 추가는 후속 구현
                          </span>
                        </div>
                        <p role="status">{message}</p>
                      </form>
                    </section>
                  )}
                </>
              ) : (
                <>
                  {reviewQuestion && (
                    <div className="request-context">
                      <span>선택한 검토</span>
                      <p>{reviewQuestion}</p>
                      <small>모의 예제 · 실제 분석 아님</small>
                    </div>
                  )}
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
                    <label className="scenario-picker">
                      미리보기 상태
                      <select
                        value={scenarioName}
                        onChange={(e) => chooseScenario(e.target.value)}
                      >
                        {fixtures.scenarios.map((s) => (
                          <option key={s.name} value={s.name}>
                            {labels[s.name]}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <div className="notice">
                    <span className="tag">모의 데이터</span>{" "}
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
                          chooseScenario("completed");
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
                              setInputOpen(true);
                            }}
                          >
                            입력 화면으로
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
                            {scenario.run.candidates.map((c, i) => (
                              <section className="panel" key={c.candidate_id}>
                                <div className="section-heading">
                                  <h3>모의 후보 {i + 1}</h3>
                                  <span className="caption">
                                    실제 항체 아님
                                  </span>
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
                            <span className="caption">
                              상태 선택으로 시나리오를 탐색합니다. 실제 분석은
                              실행되지 않습니다.
                            </span>
                            <button
                              className="primary"
                              disabled={!scenario.run.result_available}
                              onClick={() => go(2)}
                            >
                              비교 결과 보기 ↗
                            </button>
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
                      <section
                        className="layout-comparison"
                        aria-label="화면 구성 비교"
                      >
                        <div>
                          <strong>어떤 방식이 더 이해하기 쉬운가요?</strong>
                          <p>
                            같은 모의 자료로 기존 화면과 새 제안을 비교하세요.
                          </p>
                        </div>
                        <div className="segmented">
                          <button
                            aria-pressed={comparisonLayout === "original"}
                            onClick={() => setComparisonLayout("original")}
                          >
                            A · 기존: 구조 먼저
                          </button>
                          <button
                            aria-pressed={comparisonLayout === "proposed"}
                            onClick={() => setComparisonLayout("proposed")}
                          >
                            B · 제안: 쟁점 먼저
                          </button>
                        </div>
                      </section>
                      <div className="comparison-toolbar">
                        <div className="segmented" aria-label="후보 선택">
                          {fixtures.input.candidates.map((c, i) => (
                            <button
                              key={c.candidate_id}
                              aria-pressed={candidate === c.candidate_id}
                              onClick={() => {
                                setCandidate(c.candidate_id);
                                setExpanded(null);
                              }}
                            >
                              모의 후보 {i + 1}
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
                      {comparisonLayout === "proposed" && (
                        <ReviewOverview
                          result={result}
                          candidate={candidate}
                          conditionKind={conditionKind}
                          onSelect={(id, kind, evidenceId) => {
                            setCandidate(id);
                            setConditionKind(kind);
                            setExpanded(evidenceId);
                          }}
                        />
                      )}
                      <div className="compare-grid">
                        <section className="viewer">
                          <div className="section-heading">
                            <span className="eyebrow">STRUCTURE VIEW</span>
                            <span className="tag">구조 미제공</span>
                          </div>
                          <div className="viewer-empty">
                            <span className="outline-icon">◇</span>
                            <h2>구조가 연결될 자리입니다</h2>
                            <p>
                              이 모의 자료에는 실제 좌표가 없습니다.
                              <br />
                              구조가 제공되면 선택한 근거의 위치를 함께
                              확인합니다.
                            </p>
                          </div>
                          <span className="caption">
                            현재 3D 렌더링·잔기 강조는 제공하지 않습니다.
                          </span>
                        </section>
                        <section className="panel evidence-panel">
                          <div className="eyebrow">EVIDENCE</div>
                          <h2>확인된 것과 남은 것</h2>
                          <p className="caption">
                            수치만으로 후보의 우열을 정하지 않습니다.
                          </p>
                          {conditions.length === 0 ? (
                            <div className="empty">
                              <h3>이 조건의 자료가 없습니다</h3>
                              <p>
                                주변 구조가 없다는 뜻이 아닙니다. 자료 보완이
                                필요합니다.
                              </p>
                            </div>
                          ) : (
                            evidence.map((e) => (
                              <div className="evidence" key={e.evidence_id}>
                                <button
                                  className="evidence-toggle"
                                  aria-expanded={expanded === e.evidence_id}
                                  onClick={() =>
                                    setExpanded(
                                      expanded === e.evidence_id
                                        ? null
                                        : e.evidence_id,
                                    )
                                  }
                                >
                                  <span>
                                    접촉 근거{" "}
                                    <small>{labels[e.kind] ?? e.kind}</small>
                                  </span>
                                  <span>
                                    {labels[e.measurement_state] ??
                                      e.measurement_state}{" "}
                                    ＋
                                  </span>
                                </button>
                                {expanded === e.evidence_id && (
                                  <div className="evidence-detail">
                                    <p>{e.reason}</p>
                                    <p>측정값: {e.value ?? "미제공"}</p>
                                    <p>
                                      출처:{" "}
                                      {e.sources.length
                                        ? "제공된 출처"
                                        : "미제공"}{" "}
                                      · 대응 좌표: 미제공
                                    </p>
                                  </div>
                                )}
                              </div>
                            ))
                          )}
                          {conditions
                            .flatMap((c) => c.gaps)
                            .map((g, i) => (
                              <p className="notice" key={i}>
                                {g}
                              </p>
                            ))}
                        </section>
                      </div>
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
                        {result.opinions.map((o, i) => (
                          <article className="panel" key={o.opinion_id}>
                            <div className="section-heading">
                              <h3>모의 후보 {i + 1}</h3>
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
              )}
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
