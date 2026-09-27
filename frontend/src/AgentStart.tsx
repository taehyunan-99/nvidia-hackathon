import { useState } from "react";
import publicReferenceInput from "../../docs/frontend-hosting/fixtures/public-reference-input.json";
import type { ReviewInput } from "./scenario-file";
import { PersistentInput } from "./PersistentInput";
import "./about-page.css";
import "./team-page.css";
export function AgentStart({
  onRunLive,
  onRunMock,
  mockBusy,
  mockError,
  liveBusy,
  liveError,
  savedMode,
}: {
  onRunLive: (preset: string) => void;
  onRunMock: (input: ReviewInput, files: Map<string, File>) => void;
  mockBusy: boolean;
  mockError: string;
  liveBusy: string;
  liveError: string;
  savedMode: "mock" | "live" | null;
}) {
  const [inputMode, setInputMode] = useState<"test" | "direct">("test");
  const persistent = import.meta.env.VITE_PERSISTENT_SERVICE === "1";
  const busy = mockBusy || Boolean(liveBusy);
  return (
    <section className="agent-start">
      <div className="agent-heading">
        <span className="agent-kicker">HER2 RESEARCH AGENT</span>
        <h1>HER2 항체 검토를 시작하세요</h1>
        <p>준비된 테스트 데이터로 시작하거나, 직접 자료를 입력하세요.</p>
      </div>
      <div className="input-mode-switch" role="group" aria-label="입력 방식 선택">
        <button type="button" aria-pressed={inputMode === "test"} disabled={busy} onClick={() => setInputMode("test")}>테스트 데이터 선택</button>
        <button type="button" aria-pressed={inputMode === "direct"} disabled={busy} onClick={() => setInputMode("direct")}>직접 입력</button>
      </div>
      <div hidden={inputMode !== "test"}>
        <section className="analysis-launcher test-data-card" aria-label="테스트 데이터 소개">
          <div className="launcher-heading">
            <div><span className="eyebrow">공개 실험 데이터 · 항체 2종</span><h2>두 항체는 HER2의 어디에 결합할까요?</h2></div>
          </div>
          <p className="test-intro">같은 표적에 서로 다르게 결합하는 두 항체를 비교해 보세요.<br />검증된 공개 서열과 구조가 준비되어 있어, 파일 없이 시작할 수 있습니다.</p>
          <div className="test-candidates">
            <article><span className="test-site">막 인접 부위</span><h3>Trastuzumab <small>Fab</small></h3><p>HER2의 세포막 가까운 영역에 결합</p><a href="https://www.rcsb.org/structure/1N8Z" target="_blank" rel="noreferrer">구조 출처 · 1N8Z ↗</a></article>
            <article><span className="test-site">도메인 II</span><h3>Pertuzumab <small>Fab</small></h3><p>HER2의 다른 결합 부위를 인식</p><a href="https://www.rcsb.org/structure/1S78" target="_blank" rel="noreferrer">구조 출처 · 1S78 ↗</a></article>
          </div>
          <div className="test-data-guide"><h3>검토 후 확인할 수 있어요</h3><ol>
            <li><strong>결합 위치 비교</strong><span>두 항체의 접촉 잔기를 3D 구조에서 살펴봅니다.</span></li>
            <li><strong>판단에 사용한 근거</strong><span>어떤 실험 구조를 썼고, 왜 새 예측을 생략했는지 확인합니다.</span></li>
            <li><strong>다음에 확인할 질문</strong><span>당쇄·주변 환경에서 알려진 것과 부족한 자료를 구분합니다.</span></li>
          </ol></div>
          <p className="test-boundary">이 테스트는 구조 근거를 비교합니다. 항체의 결합력이나 치료 효과 순위를 정하지 않습니다.</p>
          {(persistent ? mockError : liveError) && <p role="alert" className="notice">{persistent ? mockError : liveError}</p>}
          <div className="launcher-action test-start-action">
            <span>{persistent && savedMode === null ? "서비스 연결을 확인하는 중입니다." : persistent && savedMode === "mock" ? "현재는 모의 실행 환경입니다. 실제 분석은 수행하지 않습니다." : "준비된 입력으로 새 검토를 실행합니다."}</span>
            <button type="button" className="primary" disabled={busy || (persistent && savedMode === null)} onClick={() => persistent ? onRunMock(publicReferenceInput, new Map()) : onRunLive("public-reference")}>
              {busy ? "접수·분석 중…" : persistent && savedMode === "mock" ? "테스트 데이터로 모의 검토 →" : "테스트 데이터로 검토 시작 →"}
            </button>
          </div>
          <details className="test-data-details"><summary>데이터 범위와 분석 한계</summary>
            <p>표적 입력은 HER2 세포외 구간(P04626 23–629), 항체 입력은 전체 항체 중 결합을 담당하는 Fab의 기탁 서열입니다. 1N8Z는 2.52 Å, 1S78은 3.25 Å 해상도의 X선 결정 구조입니다.</p>
            <p>관측된 당 성분은 전체 세포 환경을 대신하지 않습니다. 표면 노출·충돌 계산은 현재 연결되지 않아 미실행으로 표시되며, 결과에 추가 확인 의견이 나올 수 있습니다.</p>
          </details>
        </section>
      </div>
      <div className="direct-input-panel" hidden={inputMode !== "direct"}>
        {persistent ? <PersistentInput busy={mockBusy} error={mockError} mode={savedMode} onStart={onRunMock} />
          : <p className="notice">직접 입력은 저장형 서비스에서 사용할 수 있습니다. 이 개발용 미리보기에서는 테스트 데이터로 분석을 시작하세요.</p>}
      </div>
    </section>
  );
}
export function About({ onStart }: { onStart: () => void }) {
  return (
    <div className="about-page">
      <section className="about-hero" aria-labelledby="about-title">
        <div className="about-hero-copy">
          <span className="about-label">HER2 항체 후보 검토 에이전트 · 해커톤 데모</span>
          <h1 id="about-title"><span>HER2 항체 후보를</span><span><em>근거부터 검토합니다</em></span></h1>
          <p>서열과 구조가 같은 후보를 가리키는지 확인하고, 자료에 맞는 분석 도구를 선택합니다. 3D 비교에서 확인한 근거와 보류 이유를 다음 확인 질문까지 연결합니다.</p>
          <button type="button" className="primary" onClick={onStart}>공개 구조 예제로 시작 <span aria-hidden="true">↗</span></button>
        </div>
        <div className="about-summary" aria-label="서비스 흐름 요약">
          <div><span>입력</span><strong>HER2 · 항체 후보 서열</strong></div>
          <span className="about-summary-arrow" aria-hidden="true">→</span>
          <div><span>에이전트 판단</span><strong>구조 확인 · 필요한 도구 선택</strong></div>
          <span className="about-summary-arrow" aria-hidden="true">→</span>
          <div><span>결과</span><strong>3D 근거 · 보류 · 다음 질문</strong></div>
        </div>
      </section>
      <section className="about-section about-problem" aria-labelledby="about-problem-title">
        <div className="about-section-heading"><span className="about-label">01 / 해결하려는 문제</span><h2 id="about-problem-title"><span>흩어진 근거는</span><span><em>다음 질문을 흐립니다</em></span></h2><p>서열·구조·출처와 빠진 정보를 같은 후보의 검토 기록으로 연결하는 것이 이 프로젝트의 출발점입니다.</p></div>
        <div className="about-problem-grid">
          <article><span>01 / 대응</span><h3>이 구조가 해당 후보의 것인가?</h3><p>표적·항체 서열, 사슬과 분석 구간이 맞지 않으면 같은 조건의 비교가 아닙니다.</p></article>
          <article><span>02 / 근거</span><h3>관측과 예측이 섞이지 않았나?</h3><p>실험 구조에서 확인한 사실과 모델이 만든 구조의 계산 결과를 구분해야 합니다.</p></article>
          <article><span>03 / 공백</span><h3>어느 판단을 보류해야 하나?</h3><p>관측되지 않은 당쇄·주변 환경과 미계산 항목을 0이나 ‘문제없음’으로 채우지 않습니다.</p></article>
        </div>
        <div className="about-reference-case">
          <div><span className="about-label">공개 실험 구조 예제</span><strong>같은 HER2, 다른 결합 위치</strong></div>
          <a href="https://www.rcsb.org/structure/1N8Z" target="_blank" rel="noreferrer"><span>Trastuzumab Fab</span><strong>막 인접 부위</strong><small>실험 구조 · 1N8Z ↗</small></a>
          <a href="https://www.rcsb.org/structure/1S78" target="_blank" rel="noreferrer"><span>Pertuzumab Fab</span><strong>도메인 II</strong><small>실험 구조 · 1S78 ↗</small></a>
        </div>
        <p className="about-research-note">관련 연구 <a href="https://arxiv.org/html/1907.04112" target="_blank" rel="noreferrer">복합체 시각 탐색 ↗</a> <a href="https://pubmed.ncbi.nlm.nih.gov/38073135/" target="_blank" rel="noreferrer">항체–항원 구조 예측 평가 ↗</a></p>
      </section>
      <section className="about-section about-workflow" aria-labelledby="about-workflow-title">
        <div className="about-section-heading"><span className="about-label">02 / 에이전트의 역할</span><h2 id="about-workflow-title"><span>자료에 맞는</span><span><em>도구를 선택합니다</em></span></h2></div>
        <div className="about-agent-core"><span className="about-label">Nemotron 3 Super + NeMo Agent Toolkit</span><strong>후보별로 다음 행동을 고르는 에이전트</strong><p>모델은 허용된 도구 중 다음 행동을 고릅니다. 코드는 입력·도구 순서를 확인하고 좌표 근거를 계산합니다.</p></div>
        <div className="about-flow" aria-label="후보 검토의 판단 분기">
          <div className="about-flow-step"><span>01</span><div><strong>입력과 출처 확인</strong><p>HER2·항체 서열과 사슬·구간이 맞는지 확인</p></div></div>
          <p className="about-flow-branch-label">자료 상태에 따라 후보마다 한 경로를 선택</p>
          <div className="about-flow-paths">
            <div><span>일치하는 실험 구조</span><strong>RCSB 구조 재사용</strong><small>새 예측을 생략한 이유를 기록</small></div>
            <div><span>새 구조가 필요함</span><strong>Boltz-2 예측</strong><small>실험 구조와 다른 근거로 표시</small></div>
            <div><span>자료가 불충분함</span><strong>판단 보류</strong><small>빠진 입력과 이유를 기록</small></div>
          </div>
          <div className="about-flow-step about-flow-result"><span>02</span><div><strong>근거와 다음 질문 제시</strong><p>확보한 좌표의 접촉·표면·관측 당 근거를 3D와 연결하고, 부족한 정보는 보류 이유로 표시</p></div></div>
        </div>
        <p className="about-flow-footnote">검토 의견은 해당 구조와 계산 항목에 한정됩니다. 결합력·치료 효능의 순위가 아닙니다.</p>
      </section>
      <section className="about-section about-validation" aria-labelledby="about-validation-title">
        <div className="about-section-heading"><span className="about-label">03 / 내부 검증</span><h2 id="about-validation-title"><span>완주와 정확도를</span><span><em>구분해 검증합니다</em></span></h2></div>
        <div className="about-validation-grid">
          <article className="about-validation-run"><span className="about-label">에이전트 실행 경로</span><div className="about-validation-value"><strong>6/6</strong><span>고정 사례 완료</span></div><div className="about-case-dots" aria-hidden="true"><i /><i /><i /><i /><i /><i /></div><p>실제 Nemotron 호출의 재시도 후, 여섯 사례 모두 규칙 대체 없이 정해진 종료 상태에 도달했습니다. HTTP 429 일곱 건은 복구했습니다.</p></article>
          <article className="about-validation-prediction"><span className="about-label">새 항체 구조 예측</span><strong>예측 접촉 위치 불일치</strong><div className="about-prediction-cases"><span>8JYR <b>F1 0</b></span><span>3N85 <b>F1 0</b></span></div><p>실제 Boltz-2 예측을 에이전트에 주지 않은 공개 실험 구조와 대조한 두 사례입니다. 모델 신뢰도만으로 정확도를 판단하지 않습니다.</p></article>
        </div>
        <p className="about-validation-source">2026.09.27 소규모 내부 평가. 실행 경로 검사는 기존 Boltz-2 응답을 재사용했습니다. 이 결과로 연구자 효용이나 새 항체의 일반화 성능을 주장하지 않습니다.</p>
      </section>
      <section className="about-closing"><div><span className="about-label">공개 구조 예제</span><h2><span>두 HER2 항체의 근거를</span><span>직접 살펴보세요</span></h2></div><button type="button" className="primary" onClick={onStart}>분석 화면 열기 <span aria-hidden="true">↗</span></button></section>
    </div>
  );
}

export function Team() {
  const members = [
    {
      name: "안태현",
      handle: "taehyunan-99",
      role: "서비스 개발",
      summary: "화면과 백엔드 흐름을 만들고, 분석 결과 연결과 배포 준비를 맡았습니다.",
      avatar: "https://avatars.githubusercontent.com/u/219608216?v=4",
    },
    {
      name: "김희태",
      handle: "kimheetae0104",
      role: "에이전트 개발",
      summary: "NAT 에이전트와 NVIDIA 모델 호출을 구현하고, 오류 복구와 성능을 검증했습니다.",
      avatar: "https://avatars.githubusercontent.com/u/79716614?v=4",
    },
    {
      name: "조수빈",
      handle: "kongbeankong",
      role: "구조 분석",
      summary: "공개 구조의 서열·잔기 대응을 확인하고, 접촉·표면·관측 당 분석을 구현했습니다.",
      avatar: "https://avatars.githubusercontent.com/u/242176701?v=4",
    },
  ];
  return (
    <section className="team-page" aria-labelledby="team-title">
      <div className="team-heading">
        <span className="team-eyebrow">THE TEAM / HER2 RESEARCH AGENT</span>
        <h1 id="team-title">HER2 항체 검토 에이전트를 만든 세 사람</h1>
        <p>서비스와 분석 로직을 나누어 개발하고 하나의 검토 흐름으로 연결했습니다.</p>
      </div>
      <div className="team-member-grid">
        {members.map((member, index) => (
          <article className="team-member" key={member.handle}>
            <div className="team-member-top">
              <img src={member.avatar} alt={`${member.name}의 GitHub 프로필 사진`} width="88" height="88" referrerPolicy="no-referrer" />
              <span>{String(index + 1).padStart(2, "0")}</span>
            </div>
            <div className="team-member-copy">
              <span className="team-member-role">{member.role}</span>
              <h2>{member.name}</h2>
              <p>{member.summary}</p>
            </div>
            <a className="team-member-profile" href={`https://github.com/${member.handle}`} target="_blank" rel="noreferrer">@{member.handle} <span aria-hidden="true">↗</span></a>
          </article>
        ))}
      </div>
      <div className="team-repository">
        <div>
          <span className="team-eyebrow">PROJECT REPOSITORY</span>
          <h2>프로젝트 코드와 개발 기록</h2>
        </div>
        <a
          className="team-repository-button"
          href="https://github.com/taehyunan-99/nvidia-hackathon"
          target="_blank"
          rel="noreferrer"
        >
          프로젝트 GitHub <span aria-hidden="true">↗</span>
        </a>
      </div>
    </section>
  );
}
