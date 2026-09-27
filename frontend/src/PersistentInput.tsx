import { useState } from "react";
import publicReferenceInput from "../../docs/frontend-hosting/fixtures/public-reference-input.json";
import type { ReviewInput } from "./scenario-file";

type CandidateDraft = { name: string; heavy: string; light: string; pdb: string };
const emptyCandidate = (): CandidateDraft => ({ name: "", heavy: "", light: "", pdb: "" });

function validFasta(value: string): boolean {
  const lines = value.trim().split(/\r?\n/);
  const body = lines[0]?.startsWith(">") ? lines.slice(1) : lines;
  return body.length > 0 && body.every((line) => /^[ACDEFGHIKLMNPQRSTVWYBXZUO]+$/i.test(line.trim())) && !body.some((line) => line.includes(">"));
}

export function PersistentInput({ busy, error, mode, onStart }: { busy: boolean; error: string; mode: "mock" | "live" | null; onStart: (input: ReviewInput, files: Map<string, File>) => void }) {
  const [candidates, setCandidates] = useState<CandidateDraft[]>([emptyCandidate(), emptyCandidate()]);
  const [confirmed, setConfirmed] = useState(false);
  const [fieldError, setFieldError] = useState("");
  function update(index: number, change: Partial<CandidateDraft>) {
    setCandidates((old) => old.map((item, i) => i === index ? { ...item, ...change } : item));
  }
  function submit(event: React.FormEvent) {
    event.preventDefault();
    for (const [index, candidate] of candidates.entries()) {
      if (!candidate.name.trim() || !validFasta(candidate.heavy) || !validFasta(candidate.light)) return setFieldError(`${index + 1}번 후보의 이름·중쇄·경쇄 FASTA를 확인하세요.`);
      if (candidate.pdb.trim() && !/^[1-9][A-Z0-9]{3}$/i.test(candidate.pdb.trim())) return setFieldError(`${index + 1}번 후보의 공개 구조 번호를 확인하세요. 예: 6ATT`);
    }
    if (!confirmed) return setFieldError("공개 자료 사용 확인이 필요합니다.");
    const input: ReviewInput = {
      schema_version: "0.1.0", example_id: null, public_data_confirmed: true,
      target: publicReferenceInput.target,
      candidates: candidates.map((candidate, index) => {
        const pdb = candidate.pdb.trim().toUpperCase();
        return { candidate_id: `candidate-${index + 1}`, name: candidate.name.trim(), antibody_format: null, heavy_chain_fasta: candidate.heavy.trim(), light_chain_fasta: candidate.light.trim(), heavy_analysis_range: null, light_analysis_range: null, sources: pdb ? [{ title: `RCSB PDB ${pdb}`, url: `https://www.rcsb.org/structure/${pdb}`, record_id: pdb }] : [] };
      }),
      uploads: [],
    };
    setFieldError("");
    onStart(input, new Map());
  }
  return <section className="analysis-launcher review-launcher" aria-label="새 검토 입력">
    <div className="launcher-heading">
      <div><span className="eyebrow">NEW REVIEW</span><h2>표적과 후보 입력</h2></div>
      <span className="tag">{mode === "live" ? "저장형 실제 실행" : mode === "mock" ? "저장형 모의 실행" : "저장형 검토"}</span>
    </div>
    <p className="review-intro">HER2 표적은 검증된 세포외 구간으로 고정됩니다. 후보 2~4개의 공개 Fab 중쇄·경쇄 서열을 입력하세요. 50잔기 미만이거나 예측 모델이 받지 않는 문자는 예측을 보류할 수 있습니다. {mode === "live" ? "실제 분석이 실행되며 결과는 같은 실행에 저장됩니다." : mode === "mock" ? "결과는 모의 데이터이며 실제 분석은 수행하지 않습니다." : "서비스 실행 모드를 확인하는 중입니다."}</p>
    <form className="review-form" onSubmit={submit}>
      <section className="review-target" aria-labelledby="review-target-title">
        <div className="review-section-heading"><h3 id="review-target-title">표적</h3><span>HER2 고정</span></div>
        <p>HER2 (UniProt P04626), 세포외 구간 23–629 · {publicReferenceInput.target.fasta.split("\n")[1].length}잔기. <a href="https://www.uniprot.org/uniprotkb/P04626" target="_blank" rel="noreferrer">표적 서열 출처 ↗</a></p>
      </section>
      {candidates.map((candidate, index) => <fieldset key={index} className="review-candidate">
        <legend>항체 후보 {index + 1}</legend>
        <div className="review-candidate-fields">
          <label>후보 이름<input value={candidate.name} onChange={(event) => update(index, { name: event.target.value })} required /></label>
          <label>공개 구조 번호 (선택)<input value={candidate.pdb} onChange={(event) => update(index, { pdb: event.target.value })} placeholder="예: 6ATT" maxLength={4} /></label>
          <p>번호를 비우면 서열로 공개 구조를 찾습니다. 표적·후보 서열과 사슬이 맞는 구조만 사용하며, 부모 항체의 출처는 변이 후보의 실험 근거가 아닙니다.</p>
          <div className="review-form-grid">
            <label>중쇄 FASTA<textarea value={candidate.heavy} onChange={(event) => update(index, { heavy: event.target.value })} required /></label>
            <label>경쇄 FASTA<textarea value={candidate.light} onChange={(event) => update(index, { light: event.target.value })} required /></label>
          </div>
        </div>
      </fieldset>)}
      <div className="review-add-row">
        {candidates.length < 4 && <button type="button" className="secondary" onClick={() => setCandidates((old) => [...old, emptyCandidate()])}>+ {candidates.length + 1}번째 후보 추가</button>}
        {candidates.length > 2 && <button type="button" className="secondary" onClick={() => setCandidates((old) => old.slice(0, -1))}>마지막 후보 제거</button>}
      </div>
      <div className="review-submit">
        <label className="review-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />입력 자료를 사용할 권한과 공개 자료 여부를 확인했습니다.</label>
        {(fieldError || error) && <p role="alert" className="notice">{fieldError || error}</p>}
        <button className="primary" type="submit" disabled={busy || mode === null}>{busy ? "접수 중…" : mode === "live" ? "실제 검토 시작 →" : "모의 검토 시작 →"}</button>
      </div>
    </form>
  </section>;
}
