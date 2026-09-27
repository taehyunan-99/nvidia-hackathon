import type { Result, ReviewInput, Scenario } from "./scenario-file";
import "./report-view.css";

type Evidence = { evidence_id: string; topic: string; kind: string; structure_id: string | null; measurement_state: string; value: number | null; unit: string | null; definition: string | null; reason: string | null; sources: Source[] };
type Opinion = Result["opinions"][number];
type Source = { title: string; url: string; record_id: string | null };

const decisions: Record<string, string> = {
  reviewable: "해당 항목 검토 가능", needs_confirmation: "추가 확인", hold: "판단 보류", not_assessed: "미검토",
};
const measurements: Record<string, string> = {
  measured: "측정됨", unknown: "미확인", not_run: "미실행", failed: "실행 실패", not_applicable: "해당 없음",
};
const evidenceKinds: Record<string, string> = { experimental: "실험 자료", computed: "계산 결과", unknown: "근거 종류 미확인" };
const topics: Record<string, string> = {
  contact: "접촉", accessibility: "접근성", clash: "충돌", confidence: "구조 신뢰도",
  surface: "관측 단백질 표면", glycan: "관측 당의 표면 영향",
  interface_contact_residues: "접촉 잔기", atom_clash: "원자 간 충돌", surface_exposure: "관측 단백질 표면적",
  buried_sasa_sum: "양쪽 매몰 면적 합",
  observed_glycan_protein_sasa_reduction: "관측 당의 표면 감소량",
  pose: "예측 간 자세 차이",
  pose_consistency: "예측 간 항체 RMSD",
  whole_range_accessibility: "전체 구간 접근성",
  interface_review: "조건별 구조 근거",
};
const conditions: Record<string, string> = { core: "HER2–항체 중심", context: "당쇄·주변 구조 포함" };
const files: Record<string, string> = { structure: "구조 파일", report_json: "결과 JSON", report_csv: "결과 CSV" };
const runStates: Record<string, string> = { queued: "대기", running: "진행 중", completed: "종료", partial: "부분 결과", failed: "실행 실패", interrupted: "실행 중단" };

function unique(items: string[]): string[] { return [...new Set(items.filter(Boolean))]; }
function sourceUrl(url: string): string | null {
  try { const parsed = new URL(url); return ["https:", "http:"].includes(parsed.protocol) ? parsed.href : null; }
  catch { return null; }
}
function SourceList({ sources }: { sources: Source[] }) {
  if (!sources.length) return <span className="report-muted">출처 기록 없음</span>;
  return <ul className="report-source-list">{sources.map((source, index) => {
    const href = sourceUrl(source.url);
    return <li key={`${source.url}-${index}`}>{href ? <a href={href} target="_blank" rel="noopener noreferrer">{source.title}</a> : source.title}{source.record_id && <span> · {source.record_id}</span>}</li>;
  })}</ul>;
}
function evidenceValue(item: Evidence): string {
  if (item.measurement_state !== "measured") return item.reason ?? "값이 제공되지 않았습니다.";
  const unit = item.unit === "angstrom^2" ? "Å²" : item.unit === "angstrom" ? "Å" : item.unit === "atom_pair" ? "원자 쌍" : item.unit;
  return `${item.value?.toLocaleString("ko-KR", { maximumFractionDigits: 2 })} ${unit}`;
}

export function ReportView({ result, input, run, persistedMock, apiBase }: {
  result: Result; input: ReviewInput; run: Scenario["run"]; persistedMock: boolean; apiBase: string;
}) {
  const evidenceItems = result.evidence as Evidence[];
  const structures = result.structures as { artifact_id: string; kind: string; candidate_id: string; structure_id: string; source: Source }[];
  const measuredCount = evidenceItems.filter((item) => item.measurement_state === "measured").length;
  const incomplete = run?.status === "partial" || run?.status === "failed" || run?.status === "interrupted";
  const comparisonStatus = result.data_mode === "mock" ? "실제 비교 불가" : incomplete ? "전체 비교 미완료" : measuredCount === 0 ? "근거 부족" : "조건 확인 필요";
  const pendingOpinions = result.opinions.filter((item) => item.decision !== "reviewable").length;
  const failedCandidates = run?.candidates.filter((item) => ["failed", "partial", "interrupted"].includes(item.status) || item.steps.some((step) => step.status === "failed")).length ?? 0;
  const mainGap = unique(result.conditions.flatMap((item) => item.gaps))[0] ?? evidenceItems.find((item) => item.measurement_state !== "measured")?.reason ?? "기록된 자료 공백이 없습니다.";
  const label = (id: string) => input.candidates.find((item) => item.candidate_id === id)?.name ?? id;
  const linkedEvidence = (opinion: Opinion) => evidenceItems.filter((item) => opinion.evidence_ids.includes(item.evidence_id));
  const linkedConflicts = (opinion: Opinion) => evidenceItems.filter((item) => (opinion.conflicting_evidence_ids as string[]).includes(item.evidence_id));
  const unlinkedEvidence = evidenceItems.filter((item) => !result.opinions.some((opinion) => opinion.evidence_ids.includes(item.evidence_id) || (opinion.conflicting_evidence_ids as string[]).includes(item.evidence_id)));
  const relatedCondition = (opinion: Opinion) => result.conditions.find((item) => item.condition_id === opinion.condition_id);
  const artifactUrl = (artifact: Result["artifacts"][number]) => {
    if (artifact.status !== "ready") return null;
    if (persistedMock) return `${apiBase}/api/runs/${encodeURIComponent(result.run_id)}/artifacts/${encodeURIComponent(artifact.artifact_id)}`;
    const predicted = structures.some((structure) => structure.artifact_id === artifact.artifact_id && ["predicted", "experimental"].includes(structure.kind));
    return result.data_mode === "live" && predicted ? `${apiBase}/api/runs/${encodeURIComponent(result.run_id)}/artifacts/${encodeURIComponent(artifact.artifact_id)}` : null;
  };

  return <div className="report-view">
    <section className="report-scope" aria-label="보고 범위">
      <div>
        <span className="eyebrow">검토 범위</span>
        <h2>{result.data_mode === "mock" ? "화면 확인용 모의 결과" : "이번 실행의 결과"}</h2>
        <p>{result.data_mode === "mock" ? "입력과 상태 표시를 확인하는 자료입니다. 구조 계산·측정·실제 항체 판정은 수행하지 않았습니다." : "아래 판단은 이 실행에 기록된 조건과 근거에만 적용됩니다. 결합력이나 치료 효과를 뜻하지 않습니다."}</p>
        {incomplete && <p className="report-alert" role="status">{run?.status === "partial" ? "일부 후보의 검토가 보류되거나 실패했습니다. 확인된 기록만 아래에 표시합니다." : "실행이 완료되지 않았습니다. 저장된 결과의 범위만 확인하세요."}</p>}
        <p className="report-key-gap"><strong>자료 공백</strong>{mainGap}</p>
        <p className="report-record-count">구조 기록 {structures.length}건 · 측정 근거 {measuredCount}건</p>
      </div>
      <dl className="report-facts">
        <div><dt>비교 판단</dt><dd>{comparisonStatus}</dd></div>
        <div><dt>추가 확인 의견</dt><dd>{pendingOpinions}건</dd></div>
        <div><dt>보류·실패 후보</dt><dd>{failedCandidates}개</dd></div>
      </dl>
    </section>

    <section className="report-section" aria-labelledby="report-comparison-title">
      <div className="report-section-heading"><span className="eyebrow">01 / COMPARE</span><h2 id="report-comparison-title">후보별 검토 현황</h2><p>한 행에 같은 후보·조건의 의견, 근거 상태와 다음 질문을 연결했습니다. 순위나 종합 점수는 없습니다.</p></div>
      <div className="report-table-wrap"><table className="report-table">
        <thead><tr><th scope="col">후보</th><th scope="col">검토 조건·항목</th><th scope="col">의견</th><th scope="col">근거 상태</th><th scope="col">다음 확인</th></tr></thead>
        <tbody>{input.candidates.flatMap((candidate) => {
          const opinions = result.opinions.filter((item) => item.candidate_id === candidate.candidate_id);
          const progress = run?.candidates.find((item) => item.candidate_id === candidate.candidate_id);
          const stepIssue = progress?.steps.find((step) => step.status === "failed" || step.status === "held");
          const issue = progress?.reason ?? stepIssue?.reason;
          return (opinions.length ? opinions : [null]).map((opinion) => <tr key={opinion?.opinion_id ?? candidate.candidate_id}>
            <th scope="row" data-label="후보">{opinion ? <a href={`#report-${encodeURIComponent(opinion.opinion_id)}`}>{candidate.name}</a> : candidate.name}<small className="report-candidate-run">실행: {runStates[progress?.status ?? ""] ?? "기록 없음"}{issue && <span> · {issue}</span>}</small></th>
            <td data-label="검토 조건·항목">{opinion ? `${conditions[relatedCondition(opinion)?.kind ?? ""] ?? "조건 미기록"} · ${topics[opinion.topic] ?? opinion.topic}` : "의견 기록 없음"}</td>
            <td data-label="의견">{opinion ? <span className="report-decision" data-decision={opinion.decision}>{decisions[opinion.decision] ?? opinion.decision}</span> : "미검토"}</td>
            <td data-label="근거 상태">{opinion ? linkedEvidence(opinion).length ? unique(linkedEvidence(opinion).map((evidence) => measurements[evidence.measurement_state] ?? evidence.measurement_state)).join(" · ") : "연결 근거 없음" : "기록 없음"}</td>
            <td data-label="다음 확인">{opinion?.follow_up_questions.length ? <ul className="report-next-list">{unique(opinion.follow_up_questions).map((question) => <li key={question}>{question}</li>)}</ul> : "기록 없음"}</td>
          </tr>);
        })}</tbody>
      </table></div>
    </section>

    <section className="report-section" aria-labelledby="report-evidence-title">
      <div className="report-section-heading"><span className="eyebrow">02 / EVIDENCE</span><h2 id="report-evidence-title">의견과 연결 근거</h2><p>의견마다 적용 조건과 근거의 측정 여부를 확인하세요.</p></div>
      <div className="report-opinion-list">{result.opinions.length ? result.opinions.map((opinion) => {
        const condition = relatedCondition(opinion);
        const evidence = linkedEvidence(opinion);
        const conflicts = linkedConflicts(opinion);
        return <article className="report-opinion" id={`report-${opinion.opinion_id}`} key={opinion.opinion_id}>
          <header><div><span className="report-kicker">{label(opinion.candidate_id)} · {conditions[condition?.kind ?? ""] ?? "조건 미기록"}</span><h3>{topics[opinion.topic] ?? opinion.topic} 검토</h3></div><span className="report-decision" data-decision={opinion.decision}>{decisions[opinion.decision] ?? opinion.decision}</span></header>
          <p className="report-reason">{opinion.reason}</p>
          {condition?.gaps.length ? <div className="report-gap"><strong>자료 공백</strong><ul>{unique(condition.gaps).map((gap) => <li key={gap}>{gap}</li>)}</ul></div> : null}
          <div className="report-evidence-grid">
            <div><h4>연결 근거</h4>{evidence.length ? <ul className="report-evidence-list">{evidence.map((item) => <li key={item.evidence_id}><strong>{topics[item.topic] ?? item.topic} · {measurements[item.measurement_state] ?? item.measurement_state}</strong><small>{item.kind === "computed" && item.structure_id ? "구조에서 계산한 값" : evidenceKinds[item.kind] ?? item.kind}</small><span>{evidenceValue(item)}</span>{item.measurement_state === "measured" && item.definition && <small>정의: {item.definition}</small>}<SourceList sources={item.sources} /></li>)}</ul> : <p className="report-muted">연결된 근거 기록이 없습니다.</p>}</div>
            <div><h4>해석 범위와 다음 확인</h4>{opinion.limitations.length ? <ul>{unique(opinion.limitations).map((item) => <li key={item}>{item}</li>)}</ul> : <p className="report-muted">기록된 한계 없음</p>}<h4>다음 질문</h4>{opinion.follow_up_questions.length ? <ul>{unique(opinion.follow_up_questions).map((item) => <li key={item}>{item}</li>)}</ul> : <p className="report-muted">기록된 질문 없음</p>}</div>
          </div>
          {conflicts.length > 0 && <div className="report-conflict"><strong>상충 근거</strong><ul>{conflicts.map((item) => <li key={item.evidence_id}>{topics[item.topic] ?? item.topic} · {evidenceValue(item)}</li>)}</ul></div>}
          {condition?.sources.length ? <div className="report-condition-sources"><strong>조건 출처</strong><SourceList sources={condition.sources} /></div> : null}
        </article>;
      }) : <p className="report-muted">이 실행에 기록된 검토 의견이 없습니다.</p>}</div>
      {unlinkedEvidence.length > 0 && <div className="report-unlinked"><h3>의견에 연결되지 않은 근거</h3><p>아래 기록은 검토 의견을 뒷받침하는 근거로 연결되지 않았습니다.</p><ul>{unlinkedEvidence.map((item) => <li key={item.evidence_id}><strong>{topics[item.topic] ?? item.topic} · {measurements[item.measurement_state] ?? item.measurement_state}</strong><span>{evidenceValue(item)}</span><SourceList sources={item.sources} /></li>)}</ul></div>}
    </section>

    <section className="report-section" aria-labelledby="report-files-title">
      <div className="report-section-heading"><span className="eyebrow">03 / FILES</span><h2 id="report-files-title">결과 파일</h2><p>준비된 파일만 열 수 있습니다. 모의 파일과 누락 파일은 생성된 결과로 표시하지 않습니다.</p></div>
      {run && <div className="actions">{(["json", "csv"] as const).map((format) => <a key={format} className="secondary" href={`${apiBase}/api/runs/${encodeURIComponent(result.run_id)}/report.${format}`} download={`report.${format}`}>{result.data_mode === "mock" ? "모의 기록" : "결과"} {format.toUpperCase()} 내려받기 ↓</a>)}</div>}
      <div className="report-file-list">{result.artifacts.length ? result.artifacts.map((artifact) => {
        const url = artifactUrl(artifact);
        return <div className="report-file" key={artifact.artifact_id}><div><strong>{files[artifact.role] ?? artifact.role}</strong><span>{artifact.file_name} · {artifact.format.toUpperCase()}</span><small>{url ? "조회 가능" : artifact.reason ?? (artifact.status === "ready" ? "파일 경로가 연결되지 않았습니다." : "파일 없음")}</small></div>{url ? <a className="secondary" href={url} download={artifact.file_name}>내려받기 ↓</a> : <span className="report-file-status">{artifact.status === "mock" ? "모의 항목" : "이용 불가"}</span>}</div>;
      }) : <p className="report-muted">등록된 결과 파일이 없습니다.</p>}</div>
    </section>

    <section className="report-provenance" aria-label="실행 기록"><h2>실행 기록</h2><dl><div><dt>실행 ID</dt><dd>{result.run_id}</dd></div><div><dt>결과 생성</dt><dd><time dateTime={result.created_at}>{new Date(result.created_at).toLocaleString("ko-KR")}</time></dd></div><div><dt>설정 버전</dt><dd>{result.settings_version}</dd></div><div><dt>실행 상태</dt><dd>{runStates[run?.status ?? ""] ?? "미확인"}</dd></div></dl>{structures.length > 0 && <div className="report-structure-sources"><h3>구조 자료 출처</h3><p>실험 구조의 출처는 이 구조에서 계산한 접촉값이나 결합력의 실험 검증을 뜻하지 않습니다.</p><ul>{structures.map((structure) => <li key={structure.structure_id}><strong>{label(structure.candidate_id)} · {structure.kind === "experimental" ? "실험 구조" : "예측 구조"}</strong><SourceList sources={[structure.source]} /></li>)}</ul></div>}</section>
  </div>;
}
