import { useState } from "react";
import publicReferenceInput from "../../docs/frontend-hosting/fixtures/public-reference-input.json";
import type { ReviewInput } from "./scenario-file";
import { PersistentInput } from "./PersistentInput";
export function BioSymbol({ large = false }: { large?: boolean }) {
  return (
    <svg
      className={large ? "bio-symbol bio-symbol-large" : "bio-symbol"}
      viewBox="0 0 240 180"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient
          id={large ? "bio-large" : "bio-small"}
          x1="30"
          y1="20"
          x2="210"
          y2="160"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#b4e958" />
          <stop offset="1" stopColor="#76b900" />
        </linearGradient>
      </defs>
      <g
        stroke={`url(#${large ? "bio-large" : "bio-small"})`}
        strokeWidth="9"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M36 32C107 13 42 92 110 74S58 151 123 145" />
        <path d="M62 28C127 22 63 99 128 84S84 156 145 146" opacity=".45" />
        <path
          d="M39 46L68 52M47 73L78 76M83 92L111 100M87 121L115 126"
          strokeWidth="4"
        />
        <path d="M166 125V88L143 65M166 88L194 60" />
        <path d="M176 131V93L206 66M153 58L177 81" strokeWidth="6" />
      </g>
      <g stroke="currentColor" strokeWidth="1.5" opacity=".3">
        <path d="M119 54L142 52M128 68L144 77" strokeDasharray="3 5" />
        <circle cx="36" cy="32" r="13" />
        <circle cx="194" cy="60" r="13" />
      </g>
    </svg>
  );
}
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
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow">BIOLOGY × AGENTIC AI</div>
          <h1>
            더 명확한 근거.
            <br />더 나은 다음 질문.
          </h1>
          <p>
            HER2 항체 후보를 구조와 근거로 검토하는
            <br />
            해커톤 연구 에이전트 프로젝트입니다.
          </p>
          <div className="actions">
            <button className="primary" onClick={onStart}>
              분석 화면 열기 →
            </button>
          </div>
        </div>
        <div className="about-bio">
          <BioSymbol large />
          <p>단백질·항체 상호작용 개념 그래픽 · 실제 구조 아님</p>
        </div>
      </section>
      <section className="intro-grid">
        {[
          [
            "01",
            "자료를 연결하고",
            "공개 서열·구조·출처를 같은 후보와 조건에 연결합니다.",
          ],
          [
            "02",
            "필요한 분석을 선택하고",
            "기존 구조를 먼저 확인하고, 부족한 근거와 보류 이유를 남깁니다.",
          ],
          [
            "03",
            "다음 검토로 이어갑니다",
            "근거·검토 의견·후속 질문을 함께 살펴봅니다.",
          ],
        ].map(([n, title, desc]) => (
          <article key={n}>
            <span className="index">{n}</span>
            <h3>{title}</h3>
            <p>{desc}</p>
          </article>
        ))}
      </section>
      <section className="about-scope">
        <div>
          <span className="eyebrow">RESEARCH, WITH CONTEXT</span>
          <h2>
            무엇을 알고 있는지,
            <br />
            무엇이 아직 부족한지.
          </h2>
        </div>
        <p>
          후보의 결합 부위·구조 조건·미확인 근거를 비교하는 것이 목표입니다.
          구조 신뢰도를 실제 결합력이나 치료 효과로 해석하지 않습니다.
          NVIDIA Boltz-2 호출과 공개 구조 분석은 실제로 실행되며, 충돌·표면
          노출 지표는 아직 계산하지 않습니다.
        </p>
      </section>
    </div>
  );
}

export function Team() {
  return (
    <section className="about-team">
      <div className="section-heading">
        <div>
          <span className="eyebrow">THE PEOPLE & THE PROJECT</span>
          <h2>함께 만드는 연구 도구</h2>
        </div>
        <span className="tag">3인 팀 프로젝트</span>
      </div>
      <div className="team-grid">
        {["01", "02", "03"].map((n) => (
          <article key={n}>
            <span className="team-avatar">{n}</span>
            <h3>팀원 {n}</h3>
            <p>프로필 준비 중</p>
            <small>함께하는 사람들을 곧 소개합니다.</small>
          </article>
        ))}
      </div>
      <div className="repository-link">
        <div>
          <strong>프로젝트 GitHub</strong>
          <p>코드와 개발 기록을 확인하세요.</p>
        </div>
        <a
          href="https://github.com/taehyunan-99/nvidia-hackathon"
          target="_blank"
          rel="noreferrer"
        >
          taehyunan-99/nvidia-hackathon ↗
        </a>
      </div>
    </section>
  );
}
