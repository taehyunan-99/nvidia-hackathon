import { useId, type CSSProperties } from "react";
import type { ReviewInput, Scenario } from "./scenario-file";
import "./agent-activity.css";

import { displayEvents, actorLabel, followUp, type ActivityEvent } from "./activity-state";
type Run = NonNullable<Scenario["run"]> & { activity_events?: ActivityEvent[] };
const tools = [
  { id: "check_input", label: "입력 검사", icon: "sequence", x: 180, y: 100 },
  { id: "lookup_public_structure", label: "공개 구조 조회", icon: "search", x: 130, y: 285 },
  { id: "use_experimental_structure", label: "실험 구조 선택", icon: "structure", x: 210, y: 465 },
  { id: "predict_structure", label: "Boltz-2 NIM", icon: "spark", x: 740, y: 100 },
  { id: "compare_structure", label: "구조 비교", icon: "compare", x: 790, y: 285 },
  { id: "submit_opinion", label: "의견 기록", icon: "report", x: 710, y: 465 },
  { id: "hold_candidate", label: "검토 보류", icon: "pause", x: 460, y: 535 },
];
const phases: Record<string, string> = { idle: "대기", running: "실행", completed: "완료", held: "보류", failed: "실패", rejected: "거부", skipped: "생략", loaded: "스킬 읽음", selected: "선택" };
const statuses: Record<string, string> = { queued: "대기", running: "분석 중", completed: "검토 종료", partial: "부분 결과", failed: "실행 실패", interrupted: "실행 중단" };
function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    sequence: "M-12 -12L12 12M12 -12L-12 12M-8 -8H8M-4 -3H4M-4 3H4M-8 8H8",
    search: "M7 7L17 17M10 -3A13 13 0 1 1 -16 -3A13 13 0 1 1 10 -3",
    structure: "M0 -15L14 -7V9L0 17L-14 9V-7ZM-14 -7L0 1L14 -7M0 1V17",
    spark: "M0 -18L5 -5L18 0L5 5L0 18L-5 5L-18 0L-5 -5Z",
    compare: "M-17 -6H17L10 -13M17 6H-17L-10 13M-8 -6V6M8 -6V6",
    report: "M-11 -16H6L13 -9V16H-11ZM6 -16V-9H13M-5 -2H7M-5 5H7M-5 11H3",
    pause: "M-7 -12V12M7 -12V12",
  };
  return <path d={paths[name]} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />;
}

const colors = ["#5b9400", "#2879ce", "#9460cf", "#d17a20"];
const colorFor = (index: number) => colors[index] ?? `hsl(${(index * 137.5) % 360} 60% 43%)`;
const colorStyle = (color: string) => ({ "--candidate-color": color }) as CSSProperties;
const actionLabel = (name: string) => tools.find((tool) => tool.id === name)?.label ?? ({
  "boltz2-nim": "Boltz-2 NIM", next_action: "다음 도구 선택", continue_by_rule: "규칙 처리",
  input_mapping: "입력·자료 대응", evidence_review: "근거 확인", prediction: "구조 예측", structure_comparison: "구조 비교", reporting: "결과 정리",
}[name] ?? name);
const toolFor = (event?: ActivityEvent) => event?.activity.kind === "tool" ? event.activity.name
  : ["skill", "verification"].includes(event?.activity.kind ?? "") && event?.activity.phase !== "loaded" ? "predict_structure" : null;
function routePath(x: number, y: number, lane = 0): string {
  const dx = x - 460, dy = y - 285;
  const length = Math.hypot(dx, dy);
  const nx = -dy / length, ny = dx / length;
  const bend = dy < 0 ? -18 : 18;
  return `M${460 + nx * lane} ${285 + ny * lane} Q${(460 + x) / 2 + nx * (bend + lane)} ${(285 + y) / 2 + ny * (bend + lane)} ${x + nx * lane} ${y + ny * lane}`;
}
function Pulse({ radius, active }: { radius: number; active: boolean }) {
  return <g className="motion-pulse" data-active={active} aria-hidden="true"><circle r={radius} className="motion-ripple" /><circle r={radius} className="motion-ripple echo" /></g>;
}
export function AgentActivity({ run, input, readError }: { run: Run; input: ReviewInput; readError: string }) {
  const gridId = useId();
  const events = displayEvents(run.activity_events ?? []);
  const activeRun = ["queued", "running"].includes(run.status);
  const candidates = input.candidates.map((candidate, index) => {
    const progress = run.candidates.find((c) => c.candidate_id === candidate.candidate_id);
    const mine = events.filter((event) => event.candidate_id === candidate.candidate_id);
    const latest = mine.at(-1);
    const activity = latest?.activity;
    const moving = !readError && activeRun && progress?.status === "running";
    const last = (predicate: (event: ActivityEvent) => boolean) => mine.slice().reverse().find(predicate);
    const decision = last((e) => e.activity.kind === "skill" && ["selected", "skipped", "held"].includes(e.activity.phase));
    const execution = last((e) => e.activity.kind === "skill" && ["running", "completed", "failed"].includes(e.activity.phase));
    const verification = last((e) => Boolean(e.activity.verification));
    const next = followUp(mine, tools.map((tool) => tool.id));
    const actor = actorLabel(latest);
    const liveStatus = statuses[progress?.status ?? "queued"];
    const state = activeRun && latest && progress?.status === "running" ? actionLabel(activity!.name) : liveStatus;
    return { ...candidate, index, color: colorFor(index), progress, mine, latest, activity, moving, decision, execution, verification, next, state, actor };
  });
  const moving = candidates.some((c) => c.moving);
  const focused = candidates.find((c) => c.latest?.activity.event_id === events.at(-1)?.activity.event_id);
  return <section className="agent-activity" aria-label="에이전트 동작">
    <div className="motion-toolbar">
      <div className="motion-legend" aria-label="후보별 진행과 색상 범례">{candidates.map((candidate) => <div className="motion-legend-item" key={candidate.candidate_id} style={colorStyle(candidate.color)}>
        <span className="candidate-dot">{candidate.index + 1}</span><strong>{candidate.name}</strong><span className="legend-state">{candidate.state} · {candidate.actor}</span>
      </div>)}</div>
      <div className="motion-controls"><span className="motion-status">후보 순차 처리</span><span className="motion-status" role="status">{readError ? "연결 확인 필요" : statuses[run.status]}</span></div>
    </div>
    <svg className="agent-map" viewBox="0 0 920 640" role="img" aria-label="모든 후보의 도구 선택과 실행 경로">
      <defs><pattern id={gridId} width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="currentColor" /></pattern></defs>
      <rect width="920" height="640" fill={`url(#${gridId})`} className="motion-grid" />
      <circle cx="460" cy="285" r="150" className="motion-orbit" />
      {tools.map((tool) => <g key={tool.id} className="motion-tool">
        <path d={routePath(tool.x, tool.y)} className="motion-link" />
        {candidates.map((candidate) => {
          const last = candidate.mine.slice().reverse().find((e) => toolFor(e) === tool.id);
          const phase = last?.activity.verification?.status === "failed" ? "failed" : last?.activity.phase ?? "idle";
          const offset = (candidate.index - (candidates.length - 1) / 2) * 6;
          const d = routePath(tool.x, tool.y, offset);
          const signalStyle = { ...colorStyle(candidate.color), "--signal-duration": `${Math.max(1.2, Math.hypot(tool.x - 460, tool.y - 285) / 230)}s` } as CSSProperties;
          const flowing = toolFor(candidate.latest) === tool.id && candidate.moving && candidate.activity?.phase === "running";
          return <g key={candidate.candidate_id} style={signalStyle} className="motion-route" data-phase={phase} data-visited={Boolean(last)} data-candidate={candidate.candidate_id}>
            <path d={d} className="motion-visited" />
            <g className="motion-signal" data-active={flowing} aria-hidden="true">
              <path d={d} pathLength="100" className="motion-streak tail" />
              <path d={d} pathLength="100" className="motion-streak" />
            </g>
          </g>;
        })}
        <g transform={`translate(${tool.x} ${tool.y})`}>
          <circle r="34" className="motion-node" /><Icon name={tool.icon} />
          {candidates.map((candidate) => {
            const last = candidate.mine.slice().reverse().find((e) => toolFor(e) === tool.id);
            const phase = last?.activity.verification?.status === "failed" ? "failed" : last?.activity.phase ?? "idle";
            const radius = 42 + candidate.index * 8;
            return <g key={candidate.candidate_id} className="motion-candidate-ring" style={colorStyle(candidate.color)} data-phase={phase} data-visited={Boolean(last)}>
              <title>{candidate.name} · {tool.label} · {phases[phase] ?? phase}</title><circle r={radius} className="motion-halo" /><Pulse radius={radius} active={toolFor(candidate.latest) === tool.id && candidate.moving && candidate.activity?.phase === "running"} />
            </g>;
          })}
          <text y={Math.max(72, 48 + candidates.length * 8)} className="motion-label">{tool.label}</text>{tool.id === "check_input" && <text y={Math.max(88, 64 + candidates.length * 8)} className="motion-skill-label">사전 코드 검사</text>}{tool.id === "predict_structure" && <text y={Math.max(88, 64 + candidates.length * 8)} className="motion-skill-label">NVIDIA SKILL</text>}
        </g>
      </g>)}
      <g className="motion-core" data-moving={moving} transform="translate(460 285)">
        {candidates.map((candidate) => <g key={candidate.candidate_id} style={colorStyle(candidate.color)}><circle r={78 + candidate.index * 7} className="motion-core-ring" /><Pulse radius={78 + candidate.index * 7} active={candidate.moving && (candidate.activity?.kind === "agent" || candidate.activity?.kind === "stage" && candidate.activity?.actor === "rule" && candidate.activity?.phase === "running")} /></g>)}
        <circle r="67" className="motion-core-body" />
        <g className="motion-neural" transform="translate(0 -17)"><path d="M-24 0L0 -16L24 0L0 16ZM-24 0H24M0 -16V16" /><circle cx="-24" r="4" /><circle cy="-16" r="4" /><circle cx="24" r="4" /><circle cy="16" r="4" /><circle r="5" /></g>
        <text y="21" className="motion-core-title">Bio-3 AGENT</text><text y="41" className="motion-core-caption">{readError ? "연결 대기" : moving && focused ? focused.actor : statuses[run.status]}</text>
      </g>
    </svg>
    <div className="motion-evidence" aria-label="스킬 선택과 검증">{candidates.map((candidate) => {
      const skipped = candidate.decision?.activity.phase === "skipped";
      const terminal = !["queued", "running"].includes(candidate.progress?.status ?? "queued");
      const reason = candidate.decision?.activity.reason ?? candidate.progress?.reason ?? candidate.progress?.steps.find((step) => ["failed", "held"].includes(step.status))?.reason;
      const check = candidate.verification?.activity.verification;
      return <article className="motion-evidence-card" key={candidate.candidate_id} style={colorStyle(candidate.color)}>
        <div className="motion-card-heading"><span className="candidate-dot">{candidate.index + 1}</span><h3>{candidate.name}</h3><span className="motion-decision">{candidate.decision ? `Boltz-2 ${phases[candidate.decision.activity.phase]}` : terminal ? "스킬 선택 없음" : "선택 대기"}</span></div>
        <p className="motion-reason">{reason ?? "아직 기록된 선택 이유가 없습니다."}</p>
        <dl className="motion-checks"><div><dt>실행</dt><dd>{candidate.execution ? candidate.execution.activity.phase === "completed" ? "응답 수신" : phases[candidate.execution.activity.phase] : skipped ? "생략" : terminal ? "호출 없음" : "호출 전"}</dd></div>
          <div><dt>검증</dt><dd data-check={check?.status}>{check ? ({passed: "확인 통과", failed: "확인 실패", unverified: "미확인 있음"}[check.status] ?? "미확인") : skipped ? "해당 없음" : "미실행"}</dd></div>
          <div><dt>{candidate.next.label}</dt><dd>{candidate.next.actions.length ? candidate.next.actions.map(actionLabel).join(" · ") : "대기"}</dd></div></dl>
      </article>;
    })}</div>
    <details className="motion-details"><summary>상세 동작 기록 · {events.length}건</summary><ol>{events.slice().reverse().map((event) => {
      const candidate = candidates.find((c) => c.candidate_id === event.candidate_id);
      const eventReason = event.activity.reason ?? event.reason;
      return <li key={event.activity.event_id} style={colorStyle(candidate?.color ?? colors[0])}><span className="motion-event-name">{candidate?.name} · {actorLabel(event)} · {actionLabel(event.activity.name)}</span><span>{phases[event.activity.phase] ?? event.activity.phase}</span>{eventReason && <p>{eventReason}</p>}{event.activity.skill && <small>NVIDIA {event.activity.skill.id} · {event.activity.skill.revision.slice(0, 8)}</small>}{event.activity.verification && <ul>{event.activity.verification.checks.map((check) => <li key={check.name}>{check.name} · {({passed: "통과", failed: "실패", unverified: "미확인"}[check.status])}</li>)}</ul>}</li>;
    })}</ol>{!events.length && <p>이 실행에 저장된 도구 호출 기록이 없습니다.</p>}</details>
  </section>;
}
