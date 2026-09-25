import fixtures from "../../docs/frontend-hosting/fixtures/scenarios.json";
type Result = NonNullable<(typeof fixtures.scenarios)[number]["result"]>;
const decisions: Record<string, string> = {
  hold: "판단 보류",
  not_assessed: "미검토",
  needs_confirmation: "추가 확인",
  reviewable: "후속 실험 검토 가능",
};
export function ReviewOverview({
  result,
  candidate,
  conditionKind,
  onSelect,
}: {
  result: Result;
  candidate: string;
  conditionKind: string;
  onSelect: (
    candidate: string,
    condition: string,
    evidence: string | null,
  ) => void;
}) {
  const opinions = result.opinions.filter((o) =>
    result.conditions.some(
      (c) => c.condition_id === o.condition_id && c.kind === conditionKind,
    ),
  );
  const selected = opinions.find((o) => o.candidate_id === candidate);
  const selectedEvidence = result.evidence.filter((e) =>
    selected?.evidence_ids.includes(e.evidence_id),
  );
  const name = (id: string) =>
    fixtures.input.candidates.find((c) => c.candidate_id === id)?.name ?? id;
  return (
    <section className="review-overview" aria-label="제안 화면의 검토 요약">
      <div className="review-context">
        <span>표적: 합성 입력 · 실제 HER2 아님</span>
        <span>분석 구간: 미정</span>
        <span>
          {conditionKind === "core" ? "HER2–항체 중심" : "당쇄·주변 구조 포함"}
        </span>
        <span>실행: {result.run_id}</span>
      </div>
      <div className="review-heading">
        <div>
          <div className="eyebrow">01 / CHECK COMPARABILITY</div>
          <h2>같은 기준으로 비교할 수 있을까요?</h2>
        </div>
        <span className="tag">비교 가능 여부 · 확인 필요</span>
      </div>
      <p className="review-lead">
        구조와 분석 구간이 확인되지 않아 동등한 조건의 비교인지 판단할 수
        없습니다.
      </p>
      <div className="matrix-scroll">
        <table className="review-matrix">
          <caption>
            모의 후보의 자료 준비 상태 · 과학적 적합성 판정 아님
          </caption>
          <thead>
            <tr>
              <th scope="col">확인할 항목</th>
              {fixtures.input.candidates.map((c, i) => (
                <th scope="col" key={c.candidate_id}>
                  <button
                    aria-pressed={candidate === c.candidate_id}
                    onClick={() =>
                      onSelect(c.candidate_id, conditionKind, null)
                    }
                  >
                    모의 후보 {i + 1} <span>↙ 검토</span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              "분석 구간",
              "선택 조건의 자료",
              "구조·좌표",
              "근거 측정",
              "검토 의견",
            ].map((row, index) => (
              <tr key={row}>
                <th scope="row">{row}</th>
                {fixtures.input.candidates.map((c) => {
                  const conditions = result.conditions.filter(
                    (x) =>
                      x.candidate_id === c.candidate_id &&
                      x.kind === conditionKind,
                  );
                  const ev = result.evidence.filter((e) =>
                    conditions.some((x) => x.condition_id === e.condition_id),
                  );
                  const op = opinions.find(
                    (o) => o.candidate_id === c.candidate_id,
                  );
                  return (
                    <td
                      key={c.candidate_id}
                      data-selected={candidate === c.candidate_id}
                    >
                      {index === 0
                        ? "미정"
                        : index === 1
                          ? conditions.length
                            ? "조건 기록 있음 · 구조 미제공"
                            : "조건 자료 미제공"
                          : index === 2
                            ? "실제 좌표 미제공"
                            : index === 3
                              ? ev.length
                                ? ev.map((e) => e.reason).join(" / ")
                                : "선택 조건의 근거 없음"
                              : op
                                ? (decisions[op.decision] ?? op.decision)
                                : "의견 없음"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="review-heading">
        <div>
          <div className="eyebrow">02 / REVIEW OPEN QUESTIONS</div>
          <h2>지금 확인해야 할 쟁점</h2>
        </div>
        <span className="caption">
          쟁점을 선택하면 아래 구조·근거의 후보도 함께 바뀝니다.
        </span>
      </div>
      <div className="issue-grid">
        <div className="issue-list">
          {opinions.length ? (
            opinions.map((o) => (
              <button
                key={o.opinion_id}
                className="issue-card"
                aria-pressed={candidate === o.candidate_id}
                onClick={() =>
                  onSelect(
                    o.candidate_id,
                    conditionKind,
                    o.evidence_ids[0] ?? null,
                  )
                }
              >
                <span className="issue-meta">
                  {name(o.candidate_id)}{" "}
                  <span>{decisions[o.decision] ?? o.decision}</span>
                </span>
                <strong>{o.reason}</strong>
                <span className="caption">
                  근거 {o.evidence_ids.length}개 · 다음 확인{" "}
                  {o.follow_up_questions.length}개 →
                </span>
              </button>
            ))
          ) : (
            <div className="panel">
              <h3>이 조건은 자료부터 필요합니다</h3>
              <p>
                당쇄·주변 구조의 존재 여부를 결론낼 수 없습니다. 중심 조건으로
                돌아가 제공된 근거를 확인하세요.
              </p>
            </div>
          )}
        </div>
        <aside className="issue-detail panel" aria-live="polite">
          <span className="eyebrow">SELECTED QUESTION</span>
          {selected ? (
            <>
              <h3>{name(selected.candidate_id)}</h3>
              <h4>왜 아직 판단할 수 없나요?</h4>
              <p>{selected.reason}</p>
              <h4>연결된 근거</h4>
              {selectedEvidence.map((e) => (
                <p key={e.evidence_id}>
                  {e.reason} · 출처 {e.sources.length ? "제공됨" : "미제공"} ·
                  좌표 {e.residues.length ? "대응 정보 있음" : "미제공"}
                </p>
              ))}
              <h4>다음 확인 질문</h4>
              <ul>
                {selected.follow_up_questions.map((q) => (
                  <li key={q}>{q}</li>
                ))}
              </ul>
              <details>
                <summary>해석 범위</summary>
                {selected.limitations.map((l) => (
                  <p key={l}>{l}</p>
                ))}
              </details>
            </>
          ) : (
            <p>선택 조건에 연결된 검토 의견이 없습니다.</p>
          )}
        </aside>
      </div>
      <div className="review-heading">
        <div>
          <div className="eyebrow">03 / INSPECT THE EVIDENCE</div>
          <h2>선택한 후보의 구조와 근거</h2>
        </div>
      </div>
    </section>
  );
}
