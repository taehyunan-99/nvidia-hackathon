import { useState } from "react";
import type { ReviewInput } from "./scenario-file";

type CandidateDraft = { name: string; heavy: string; light: string; file: File | null; role: "complex" | "context"; sourceTitle: string; sourceUrl: string };
const emptyCandidate = (): CandidateDraft => ({ name: "", heavy: "", light: "", file: null, role: "complex", sourceTitle: "", sourceUrl: "" });

function validFasta(value: string): boolean {
  const lines = value.trim().split(/\r?\n/);
  const sequence = (lines[0]?.startsWith(">") ? lines.slice(1) : lines).join("").replace(/\s/g, "");
  return Boolean(sequence) && /^[ACDEFGHIKLMNPQRSTVWYBXZUO]+$/i.test(sequence);
}

export function PersistentInput({ busy, error, mode, onStart }: { busy: boolean; error: string; mode: "mock" | "live" | null; onStart: (input: ReviewInput, files: Map<string, File>) => void }) {
  const [targetId, setTargetId] = useState("");
  const [targetFasta, setTargetFasta] = useState("");
  const [candidates, setCandidates] = useState<CandidateDraft[]>([emptyCandidate(), emptyCandidate()]);
  const [confirmed, setConfirmed] = useState(false);
  const [fieldError, setFieldError] = useState("");
  function update(index: number, change: Partial<CandidateDraft>) {
    setCandidates((old) => old.map((item, i) => i === index ? { ...item, ...change } : item));
  }
  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!targetId.trim() && !validFasta(targetFasta)) return setFieldError("표적 ID 또는 올바른 FASTA 서열을 입력하세요.");
    if (targetFasta.trim() && !validFasta(targetFasta)) return setFieldError("표적 FASTA 서열을 확인하세요.");
    for (const [index, candidate] of candidates.entries()) {
      if (!candidate.name.trim() || !validFasta(candidate.heavy) || !validFasta(candidate.light)) return setFieldError(`${index + 1}번 후보의 이름·중쇄·경쇄 FASTA를 확인하세요.`);
      if (candidate.file && (!/\.(pdb|cif|mmcif)$/i.test(candidate.file.name) || !candidate.sourceTitle.trim() || !/^https?:\/\/\S+$/.test(candidate.sourceUrl))) return setFieldError(`${index + 1}번 후보의 구조 파일 형식과 출처 제목·URL을 확인하세요.`);
    }
    if (!confirmed) return setFieldError("공개 자료 사용 확인이 필요합니다.");
    const files = new Map<string, File>();
    const uploads: ReviewInput["uploads"] = [];
    candidates.forEach((candidate, index) => {
      if (!candidate.file) return;
      const key = `structure_${index + 1}`;
      files.set(key, candidate.file);
      uploads.push({ upload_key: key, file_name: candidate.file.name, format: /\.pdb$/i.test(candidate.file.name) ? "pdb" : "mmcif", candidate_id: `candidate-${index + 1}`, role: candidate.role, source: { title: candidate.sourceTitle.trim(), url: candidate.sourceUrl.trim(), record_id: null } });
    });
    const input: ReviewInput = {
      schema_version: "0.1.0", example_id: null, public_data_confirmed: true,
      target: { identifier: targetId.trim() || null, fasta: targetFasta.trim() || null, analysis_range: null, sources: [] },
      candidates: candidates.map((candidate, index) => ({ candidate_id: `candidate-${index + 1}`, name: candidate.name.trim(), antibody_format: null, heavy_chain_fasta: candidate.heavy.trim(), light_chain_fasta: candidate.light.trim(), heavy_analysis_range: null, light_analysis_range: null, sources: [] })),
      uploads,
    };
    setFieldError("");
    onStart(input, files);
  }
  return <section className="analysis-launcher review-launcher" aria-label="새 검토 입력">
    <div className="launcher-heading">
      <div><span className="eyebrow">NEW REVIEW</span><h2>표적과 후보 입력</h2></div>
      <span className="tag">{mode === "live" ? "저장형 실제 실행" : mode === "mock" ? "저장형 모의 실행" : "저장형 검토"}</span>
    </div>
    <p className="review-intro">표적과 후보 2~3개를 입력하세요. 구조 파일은 선택 사항입니다. {mode === "live" ? "실제 분석이 실행되며 결과는 같은 실행에 저장됩니다." : mode === "mock" ? "결과는 모의 데이터이며 실제 분석은 수행하지 않습니다." : "서비스 실행 모드를 확인하는 중입니다."}</p>
    <form className="review-form" onSubmit={submit}>
      <section className="review-target" aria-labelledby="review-target-title">
        <div className="review-section-heading"><h3 id="review-target-title">표적</h3><span>ID 또는 FASTA 중 하나는 필수</span></div>
        <div className="review-target-fields">
          <label>HER2 표적 ID<input value={targetId} onChange={(event) => setTargetId(event.target.value)} placeholder="예: UniProt ID" /></label>
          <span className="review-or" aria-hidden="true">또는</span>
          <label>표적 FASTA<textarea value={targetFasta} onChange={(event) => setTargetFasta(event.target.value)} placeholder={">target\nACDE..."} /></label>
        </div>
      </section>
      {candidates.map((candidate, index) => <fieldset key={index} className="review-candidate">
        <legend>항체 후보 {index + 1}</legend>
        <div className="review-candidate-fields">
          <label>후보 이름<input value={candidate.name} onChange={(event) => update(index, { name: event.target.value })} required /></label>
          <div className="review-form-grid">
            <label>중쇄 FASTA<textarea value={candidate.heavy} onChange={(event) => update(index, { heavy: event.target.value })} required /></label>
            <label>경쇄 FASTA<textarea value={candidate.light} onChange={(event) => update(index, { light: event.target.value })} required /></label>
          </div>
          <label><span>구조 파일 <span className="review-optional">선택 · PDB/mmCIF</span></span><input type="file" accept=".pdb,.cif,.mmcif" onChange={(event) => update(index, { file: event.target.files?.[0] ?? null })} /></label>
          {candidate.file && <div className="review-form-grid review-file-details">
            <label>파일 역할<select value={candidate.role} onChange={(event) => update(index, { role: event.target.value as CandidateDraft["role"] })}><option value="complex">복합체</option><option value="context">주변 구조</option></select></label>
            <label>출처 제목<input value={candidate.sourceTitle} onChange={(event) => update(index, { sourceTitle: event.target.value })} required /></label>
            <label className="review-full-width">출처 URL<input type="url" value={candidate.sourceUrl} onChange={(event) => update(index, { sourceUrl: event.target.value })} required /></label>
          </div>}
        </div>
      </fieldset>)}
      <div className="review-add-row">
        {candidates.length < 3 ? <button type="button" className="secondary" onClick={() => setCandidates((old) => [...old, emptyCandidate()])}>+ 세 번째 후보 추가</button>
          : <button type="button" className="secondary" onClick={() => setCandidates((old) => old.slice(0, 2))}>세 번째 후보 제거</button>}
      </div>
      <div className="review-submit">
        <label className="review-confirm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />입력 자료를 사용할 권한과 공개 자료 여부를 확인했습니다.</label>
        {(fieldError || error) && <p role="alert" className="notice">{fieldError || error}</p>}
        <button className="primary" type="submit" disabled={busy || mode === null}>{busy ? "접수 중…" : mode === "live" ? "실제 검토 시작 →" : "모의 검토 시작 →"}</button>
      </div>
    </form>
  </section>;
}
