import { lazy, Suspense } from "react";
const StructurePreview = lazy(() => import("./StructurePreview"));
import type { Result, ReviewInput } from "./scenario-file";
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
};
export function ReviewOverview({
  result,
  input,
  candidate,
  conditionKind,
  evidenceId,
  onSelect,
}: {
  result: Result;
  input: ReviewInput;
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
  return (
    <section className="review-overview" aria-label="시각 중심 검토 요약">
      <div className="review-context">
        <span>{live ? "공개 구조에서 꺼낸 실제 서열" : "합성 입력 · 실제 HER2 아님"}</span>
        <span>
          {conditionKind === "core" ? "HER2–항체 중심" : "당쇄·주변 구조 포함"}
        </span>
        <span>분석 구간 미정</span>
      </div>
      <div className="review-heading">
        <div>
          <div className="eyebrow">01 / COMPARE</div>
          <h2>후보별 확인 상태</h2>
        </div>
        <span className="tag">△ 동등 조건 비교 미확인</span>
      </div>
      <p className="review-lead">
        좌표와 분석 구간이 없어 후보의 우열은 판단할 수 없습니다.
      </p>
      <div className="matrix-scroll">
        <table className="review-matrix">
          <caption>
            {live ? "실제 실행" : "모의 자료"}의 준비 상태 · 후보를 선택하면 아래 근거가 함께 바뀝니다.
          </caption>
          <thead>
            <tr>
              <th scope="col">확인 항목</th>
              {input.candidates.map((c) => (
                <th scope="col" key={c.candidate_id}>
                  <button
                    aria-pressed={candidate === c.candidate_id}
                    onClick={() =>
                      onSelect(c.candidate_id, conditionKind, null)
                    }
                  >
                    {c.name}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {["조건 기록", "구조·좌표", "근거 측정", "검토 의견"].map(
              (row, index) => (
                <tr key={row}>
                  <th scope="row">{row}</th>
                  {input.candidates.map((c) => {
                    const cs = result.conditions.filter(
                      (x) =>
                        x.candidate_id === c.candidate_id &&
                        x.kind === conditionKind,
                    );
                    const es = result.evidence.filter((e) =>
                      cs.some((x) => x.condition_id === e.condition_id),
                    );
                    const os = result.opinions.filter((o) =>
                      cs.some((x) => x.condition_id === o.condition_id),
                    );
                    const label =
                      index === 0
                        ? cs.length
                          ? "기록 있음"
                          : "미제공"
                        : index === 1
                          ? "좌표 미제공"
                          : index === 2
                            ? es.length
                              ? [
                                  ...new Set(
                                    es.map(
                                      (e) =>
                                        states[e.measurement_state] ??
                                        e.measurement_state,
                                    ),
                                  ),
                                ].join(" · ")
                              : "근거 없음"
                            : os.length
                              ? [
                                  ...new Set(
                                    os.map(
                                      (o) =>
                                        decisions[o.decision] ?? o.decision,
                                    ),
                                  ),
                                ].join(" · ")
                              : "의견 없음";
                    return (
                      <td
                        key={c.candidate_id}
                        data-selected={candidate === c.candidate_id}
                      >
                        <button
                          className="matrix-state"
                          onClick={() =>
                            onSelect(
                              c.candidate_id,
                              conditionKind,
                              es[0]?.evidence_id ?? null,
                            )
                          }
                        >
                          <span aria-hidden="true">
                            {index === 0 && cs.length ? "▤" : "◇"}
                          </span>
                          {label}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
      <div className="review-heading">
        <div>
          <div className="eyebrow">02 / INSPECT</div>
          <h2>선택한 근거를 확인하세요</h2>
        </div>
        <span className="tag">
          {input.candidates.find((c) => c.candidate_id === candidate)?.name ?? "후보 미선택"}
        </span>
      </div>
      <div className="evidence-choices" aria-label="검토 근거 선택">
        {evidence.map((e) => (
          <button
            key={e.evidence_id}
            aria-pressed={selected?.evidence_id === e.evidence_id}
            onClick={() => onSelect(candidate, conditionKind, e.evidence_id)}
          >
            {topics[e.topic] ?? e.topic} ·{" "}
            {states[e.measurement_state] ?? e.measurement_state}
          </button>
        ))}
      </div>
      <div
        className="compare-grid review-focus"
        key={`${result.run_id}-${candidate}-${conditionKind}`}
      >
        <Suspense fallback={<p>3D 준비 중…</p>}>
          <StructurePreview />
        </Suspense>
        <section
          className="panel review-evidence"
          aria-live="polite"
          aria-label="선택 근거 상세"
        >
          {selected ? (
            <>
              <div className="section-heading">
                <h3>{topics[selected.topic] ?? selected.topic}</h3>
                <span className="tag">
                  {states[selected.measurement_state] ??
                    selected.measurement_state}
                </span>
              </div>
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
              <p>{selected.reason}</p>
              {opinion && (
                <div className="review-decision">
                  <strong>
                    {decisions[opinion.decision] ?? opinion.decision}
                  </strong>
                  <p>{opinion.reason}</p>
                </div>
              )}
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
