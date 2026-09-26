import type { ReviewInput } from "./scenario-file";
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
  input,
  fileName,
  error,
  onFile,
  onStart,
  onRunLive,
  liveBusy,
  liveError,
}: {
  input: ReviewInput | null;
  fileName: string;
  error: string;
  onFile: (file: File) => void;
  onStart: () => void;
  onRunLive: (preset: string) => void;
  liveBusy: string;
  liveError: string;
}) {
  return (
    <section className="agent-start">
      <div className="agent-heading">
        <BioSymbol />
        <span className="agent-kicker">HER2 RESEARCH AGENT</span>
        <h1>
          후보를 준비하세요.
          <br />
          <span>근거를 함께 살펴봅니다.</span>
        </h1>
        <p>실제 분석을 실행하거나, 검토 시나리오 파일을 올려 확인하세요.</p>
      </div>
      <section className="analysis-launcher" aria-label="실제 분석 실행">
        <div className="launcher-heading">
          <div>
            <span className="eyebrow">LIVE RUN</span>
            <h2>실제 분석 실행</h2>
          </div>
          <span className="tag">NVIDIA · 실제 호출</span>
        </div>
        <p>
          공개 구조(1N8Z·1S78)에서 꺼낸 실제 서열로 분석합니다. 모의 재생이 아닙니다.
        </p>
        <div className="launcher-action">
          <span>
            {liveBusy
              ? "실행 중입니다. 예측 경로는 10초 이상 걸립니다."
              : "예측 경로는 NVIDIA API 키가 있어야 합니다."}
          </span>
          <span className="live-buttons">
            <button
              className="primary"
              disabled={Boolean(liveBusy)}
              onClick={() => onRunLive("experimental")}
            >
              {liveBusy === "experimental" ? "분석 중…" : "공개 구조 경로"}
            </button>
            <button
              className="primary"
              disabled={Boolean(liveBusy)}
              onClick={() => onRunLive("prediction")}
            >
              {liveBusy === "prediction" ? "예측 중…" : "Boltz-2 예측 경로"}
            </button>
          </span>
        </div>
        {liveError && <p role="alert" className="notice">{liveError}</p>}
      </section>
      <section className="analysis-launcher" aria-label="검토 파일 업로드">
        <div className="launcher-heading">
          <div>
            <span className="eyebrow">REVIEW INPUT</span>
            <h2>시나리오 파일 업로드</h2>
          </div>
          <span className="tag">JSON · 모의 재생</span>
        </div>
        <label className="scenario-upload">
          검토 시나리오 JSON
          <input type="file" accept=".json,application/json" onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onFile(file);
          }} />
        </label>
        {error && <p role="alert" className="notice">{error}</p>}
        {input && (
          <div className="uploaded-input" aria-label="업로드한 입력 미리보기">
            <strong>{fileName}</strong>
            <p>표적: {input.target.identifier ?? input.target.fasta?.split("\n")[0] ?? "미제공"}</p>
            <ul>{input.candidates.map((candidate) => <li key={candidate.candidate_id}>{candidate.name}</li>)}</ul>
          </div>
        )}
        <div className="launcher-action">
          <span>파일은 이 브라우저에서만 읽습니다.</span>
          <button
            className="primary"
            disabled={!input}
            onClick={onStart}
          >
            검토 흐름 시작 →
          </button>
        </div>
      </section>
      <p className="agent-disclosure">
        업로드한 시나리오는 기록된 상태를 재생할 뿐 분석·모델 호출을 실행하지 않습니다.
        실제 호출은 위의 “실제 분석 실행”에서 합니다.
      </p>
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
