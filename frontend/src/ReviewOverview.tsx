import { lazy, Suspense } from "react";
const StructurePreview = lazy(() => import("./StructurePreview"));
import type { Result, ReviewInput } from "./scenario-file";
import PredictedStructure, { type PredictedView } from "./PredictedStructure";
const decisions: Record<string, string> = {
  hold: "판단 보류",
  not_assessed: "미검토",
  needs_confirmation: "추가 확인",
  reviewable: "후속 실험 검토 가능",
};
const states: Record<string, string> = {
  unknown: "미확인",
  not_run: "미실행",
  failed: "실행 실패",
  measured: "측정됨",
  not_applicable: "해당 없음",
};
const topics: Record<string, string> = {
  contact: "접촉",
  accessibility: "접근성",
  clash: "충돌",
  confidence: "구조 신뢰도",
  interface_contact_residues: "접촉 잔기",
  atom_clash: "원자 간 충돌",
  surface_exposure: "표면 노출",
};
export function ReviewOverview({
  result,
  input,
  views,
  apiBase,
  candidate,
  conditionKind,
  evidenceId,
  onSelect,
}: {
  result: Result;
  input: ReviewInput;
  views: PredictedView[];
  apiBase: string;
  candidate: string;
  conditionKind: string;
  evidenceId: string | null;
  onSelect: (
    candidate: string,
    condition: string,
    evidence: string | null,
  ) => void;
}) {
  const live = result.data_mode === "live";
  const conditions = result.conditions.filter(
    (c) => c.candidate_id === candidate && c.kind === conditionKind,
  );
  const evidence = result.evidence.filter((e) =>
    conditions.some((c) => c.condition_id === e.condition_id),
  );
  const selected =
    evidence.find((e) => e.evidence_id === evidenceId) ?? evidence[0];
  const opinions = result.opinions.filter((o) =>
    conditions.some((c) => c.condition_id === o.condition_id),
  );
  const opinion =
    opinions.find(
      (o) => selected && o.evidence_ids.includes(selected.evidence_id),
    ) ?? opinions[0];
  const gaps = [...new Set(conditions.flatMap((c) => c.gaps))];
  const hasMeasuredEvidence = evidence.some((item) => item.measurement_state === "measured");
  const selectedView = views.find((view) => view.candidateId === candidate && conditions.some((condition) => (condition.structure_ids as string[]).includes(view.structureId)));
  const selectionControls = (
    <div className="review-workbench-controls" aria-label="검토 결과 선택">
      <div className="review-workbench-controls-title">
        <strong>검토 결과 선택</strong>
        <span>{live ? "후보와 조건에 연결된 구조·근거가 함께 바뀝니다." : "공개 3D 예제와 별개로 오른쪽 근거가 바뀝니다."}</span>
      </div>
      <div className="review-selection-pair">
        <div className="review-control-field">
          <span>검토 후보</span>
          <div className="review-candidate-options" role="group" aria-label="검토 후보 선택">
            {input.candidates.map((item) => (
              <button
                key={item.candidate_id}
                aria-label={item.name}
                title={item.name}
                aria-pressed={candidate === item.candidate_id}
                onClick={() => onSelect(item.candidate_id, conditionKind, null)}
              >
                {item.name.replace(/ · 실제 항체 아님$/, "")}
              </button>
            ))}
          </div>
        </div>
        <label className="review-control-field">
          검토 조건
          <select
            value={conditionKind}
            onChange={(event) => onSelect(candidate, event.target.value, null)}
          >
            <option value="core">HER2–항체 중심</option>
            <option value="context">당쇄·주변 구조 포함</option>
          </select>
        </label>
      </div>
      <div className="review-control-field">
        <span>확인할 근거 선택</span>
        <div className="evidence-categories" role="group" aria-label="확인할 근거 선택">
          {evidence.length ? evidence.map((item) => (
            <button
              key={item.evidence_id}
              title={`${topics[item.topic] ?? item.topic} · ${states[item.measurement_state] ?? item.measurement_state}`}
              aria-pressed={selected?.evidence_id === item.evidence_id}
              onClick={() => onSelect(candidate, conditionKind, item.evidence_id)}
            >
              {topics[item.topic] ?? item.topic}
            </button>
          )) : <span>이 조건에 연결된 근거가 없습니다.</span>}
        </div>
      </div>
    </div>
  );
  return (
    <section className="review-overview" aria-label="시각 중심 검토 요약">
      <div className="review-insight">
        <div>
          <span className="eyebrow">현재 이 결과에서 알 수 있는 것</span>
          <h2>이 화면만으로 후보 우열을 단정할 수 없습니다</h2>
          <p>
            {selectedView ? "선택한 후보와 조건의 구조 파일을 왼쪽에서 확인할 수 있습니다. " : "선택한 후보와 조건의 구조 좌표가 제공되지 않았습니다. "}
            {hasMeasuredEvidence ? "기록된 측정 근거는 오른쪽에서 확인해 주세요. " : "실제 근거 측정도 없습니다. "}
            {!live && "왼쪽 3D는 공개 실험 구조 예제이며 업로드한 후보의 분석 결과가 아닙니다."}
          </p>
        </div>
        <div className="review-insight-facts">
          <span>조건 기록 {result.conditions.length}건</span>
          <span>후보 구조 {result.structures.length ? `${result.structures.length}건 기록` : "미제공"}</span>
          <span>근거 {hasMeasuredEvidence ? "측정 기록 있음" : "실측·계산값 없음"}</span>
        </div>
      </div>
      <section className="review-workbench" aria-label="3D와 근거 탐색 작업대">
        <div className="review-workbench-heading">
          <div>
            <span className="eyebrow">01 / EXPLORE</span>
            <h2>구조를 보며 근거 확인하기</h2>
          </div>
          <span className="tag">{live ? selectedView ? "이번 실행의 구조" : "선택 조건의 구조 없음" : "공개 구조 예제 · 모의 결과와 별개"}</span>
        </div>
        {selectionControls}
      <div
        className="compare-grid review-focus"
      >
        {live ? selectedView ? <PredictedStructure key={selectedView.artifactId} view={selectedView} apiBase={apiBase} /> : <p className="panel">선택한 후보와 조건에 연결된 구조 파일이 없습니다.</p> : <Suspense fallback={<p>3D 준비 중…</p>}><StructurePreview /></Suspense>}
        <section
          className="panel review-evidence"
          aria-live="polite"
          aria-label="선택 근거 상세"
        >
          {selected ? (
            <>
              <div className="section-heading">
                <h3>{topics[selected.topic] ?? selected.topic} 근거</h3>
                <span className="tag">
                  {states[selected.measurement_state] ??
                    selected.measurement_state}
                </span>
              </div>
              <div className="review-evidence-summary">
                <span className="eyebrow">현재 확인 결과</span>
                <strong>{selected.measurement_state === "measured" ? "측정 기록이 있습니다" : selected.measurement_state === "failed" ? "이 근거는 계산하지 못했습니다" : "확인된 측정값이 없습니다"}</strong>
                <p>{selected.reason}</p>
              </div>
              {opinion && (
                <div className="review-decision">
                  <span className="eyebrow">검토 의견</span>
                  <strong>{decisions[opinion.decision] ?? opinion.decision}</strong>
                  <p>{opinion.reason}</p>
                </div>
              )}
              <dl className="evidence-facts">
                <div>
                  <dt>측정값</dt>
                  <dd>
                    {selected.value ?? "미제공"}
                    {selected.unit ? ` ${selected.unit}` : ""}
                  </dd>
                </div>
                <div>
                  <dt>출처</dt>
                  <dd>
                    {selected.sources.length
                      ? `${selected.sources.length}개`
                      : "미제공"}
                  </dd>
                </div>
                <div>
                  <dt>위치 대응</dt>
                  <dd>
                    {selected.residues.length
                      ? `${selected.residues.length}개`
                      : "미제공"}
                  </dd>
                </div>
              </dl>
              {gaps.map((g) => (
                <p className="notice" key={g}>
                  {g}
                </p>
              ))}
              {opinion && opinion.limitations.length > 0 && (
                <div className="review-limits">
                  <strong>판단의 한계</strong>
                  <ul>
                    {opinion.limitations.map((l) => (
                      <li key={l}>{l}</li>
                    ))}
                  </ul>
                </div>
              )}
              <details>
                <summary>정의·출처·실행 정보</summary>
                <p>정의: {selected.definition ?? "미제공"}</p>
                <p>근거 종류: {states[selected.kind] ?? selected.kind}</p>
                <p>
                  출처:{" "}
                  {selected.sources.length
                    ? selected.sources.map((s) => JSON.stringify(s)).join(" · ")
                    : "미제공"}
                </p>
                <p>실행: {result.run_id}</p>
                <p>근거: {selected.evidence_id}</p>
              </details>
            </>
          ) : (
            <>
              <h3>이 조건의 근거가 없습니다</h3>
              <p>자료가 없다는 뜻이며, 주변 구조가 없다는 결론은 아닙니다.</p>
              {gaps.map((g) => (
                <p className="notice" key={g}>
                  {g}
                </p>
              ))}
            </>
          )}
        </section>
      </div>
      </section>
      <details className="review-matrix-details">
        <summary>두 후보의 자료 준비 상태 비교</summary>
        <div className="matrix-scroll">
          <table className="review-matrix">
            <caption>선택한 검토 조건에 기록된 {live ? "실제 실행" : "모의 자료"}의 상태입니다.</caption>
            <thead>
              <tr>
                <th scope="col">확인 항목</th>
                {input.candidates.map((item) => <th scope="col" key={item.candidate_id}>{item.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {["조건 기록", "구조·좌표", "근거 측정", "검토 의견"].map((row, index) => (
                <tr key={row}>
                  <th scope="row">{row}</th>
                  {input.candidates.map((item) => {
                    const candidateConditions = result.conditions.filter((entry) => entry.candidate_id === item.candidate_id && entry.kind === conditionKind);
                    const candidateEvidence = result.evidence.filter((entry) => candidateConditions.some((condition) => condition.condition_id === entry.condition_id));
                    const candidateOpinions = result.opinions.filter((entry) => candidateConditions.some((condition) => condition.condition_id === entry.condition_id));
                    const value = index === 0
                      ? candidateConditions.length ? "기록 있음" : "미제공"
                      : index === 1
                        ? (result.structures as unknown as { candidate_id: string }[]).some((structure) => structure.candidate_id === item.candidate_id)
                          ? "구조 기록 있음 · 좌표 확인 필요"
                          : "좌표 미제공"
                        : index === 2
                          ? candidateEvidence.length ? [...new Set(candidateEvidence.map((entry) => states[entry.measurement_state] ?? entry.measurement_state))].join(" · ") : "근거 없음"
                          : candidateOpinions.length ? [...new Set(candidateOpinions.map((entry) => decisions[entry.decision] ?? entry.decision))].join(" · ") : "의견 없음";
                    return <td key={item.candidate_id} data-selected={candidate === item.candidate_id}>{value}</td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <section className="review-next">
        <div>
          <div className="eyebrow">03 / NEXT CHECK</div>
          <h2>다음 확인</h2>
        </div>
        {opinion?.follow_up_questions.length ? (
          <ul>
            {opinion.follow_up_questions.map((q) => (
              <li key={q}>{q}</li>
            ))}
          </ul>
        ) : (
          <p>선택 조건의 후속 확인 항목이 제공되지 않았습니다.</p>
        )}
      </section>
    </section>
  );
}
