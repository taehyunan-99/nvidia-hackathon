import { useEffect, useRef, useState } from "react";
import type { PluginContext } from "molstar/lib/mol-plugin/context";
import "./structure-preview.css";

/**
 * 이번 실행에서 Boltz-2가 만든 구조를 그대로 띄운다.
 *
 * 아래 StructurePreview와 다르다. 저쪽은 프런트가 미리 가지고 있는 공개
 * 실험 구조를 보여주고 분석 결과를 읽지 않는다. 이쪽은 **이번 실행의
 * 산출물**이라 실행할 때마다 파일이 다르고, 강조할 잔기도 분석이 계산한
 * 값을 그대로 쓴다.
 *
 * 받은 내용은 공개 구조에 하던 것과 똑같이 sha256으로 대조한다. 계약이
 * 적어 둔 해시와 다르면 띄우지 않는다.
 */

type Residue = { label_asym_id: string | null; label_seq_id: number | null };

export type PredictedView = {
  runId: string;
  artifactId: string;
  structureId: string;
  candidateName: string;
  sha256: string;
  /** chain_mapping에서 뽑은 표적·중쇄·경쇄 순서. null이 있으면 넘겨받지 않는다. */
  chains: string[];
  residues: Residue[];
  /** 접촉 잔기를 계산하지 못한 경우의 이유. 있으면 강조 없이 전체만 띄운다. */
  unmeasuredReason: string | null;
};

async function sha256(text: string) {
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export default function PredictedStructure({
  apiBase,
  view,
}: {
  apiBase: string;
  view: PredictedView;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("loading");
  const [count, setCount] = useState(0);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let plugin: PluginContext | undefined;
    const abort = new AbortController();
    const element = document.createElement("canvas");
    const container = host.current!;
    element.setAttribute(
      "aria-label",
      `${view.candidateName} 예측 복합체 구조`,
    );
    container.prepend(element);
    setStatus("loading");

    async function start() {
      try {
        const module = await import("./molecular-viewer");
        if (cancelled) return element.remove();
        plugin = await module.createMolecularViewer(element, container);
        if (cancelled) {
          plugin.dispose();
          return element.remove();
        }
        const response = await fetch(
          `${apiBase}/api/runs/${view.runId}/artifacts/${view.artifactId}`,
          { signal: abort.signal },
        );
        if (!response.ok)
          throw new Error("예측 구조 파일을 불러오지 못했습니다.");
        const text = await response.text();
        // 공개 구조와 같은 기준으로 대조한다. 계약이 적어 둔 값과 달라지면
        // 다른 파일을 보고 있는 것이므로 띄우지 않는다.
        if ((await sha256(text)) !== view.sha256)
          throw new Error("예측 구조 파일 검증에 실패했습니다.");
        if (cancelled) return;

        // 대응되지 않은 사슬이 있거나 접촉 잔기를 계산하지 못했으면
        // 강조 없이 전체 구조만 띄운다. 없는 것을 그린 척하지 않는다.
        const residues = view.unmeasuredReason
          ? []
          : view.residues
              .filter((r) => r.label_asym_id && r.label_seq_id)
              .map((r) => ({
                chain: r.label_asym_id as string,
                seq: r.label_seq_id as number,
              }));
        const loaded = await module.loadMolecule(
          plugin,
          text,
          view.structureId,
          "cartoon",
          residues,
          view.chains,
        );
        if (cancelled) return;
        setCount(residues.length);
        setStatus("ready");
      } catch (e) {
        if (!cancelled)
          setStatus(e instanceof Error ? e.message : "구조 표시 실패");
      }
    }
    void start();
    return () => {
      cancelled = true;
      abort.abort();
      if (plugin) {
        plugin.dispose();
        element.remove();
      }
    };
  }, [apiBase, view.runId, view.artifactId, retry]);

  const ready = status === "ready";
  return (
    <article className="structure-preview" aria-label={`${view.candidateName} 예측 구조`}>
      <div className="section-heading">
        <div>
          <h3>{view.candidateName}</h3>
          <span className="caption">이번 실행의 Boltz-2 예측 결과</span>
        </div>
      </div>
      <div ref={host} className="molecule-canvas">
        {!ready && (
          <div className="structure-status" role="status">
            {status === "loading" ? "예측 구조를 불러오는 중…" : status}
            {status !== "loading" && (
              <button onClick={() => setRetry((x) => x + 1)}>
                다시 불러오기
              </button>
            )}
          </div>
        )}
      </div>
      <div className="structure-legend">
        <span>● HER2</span>
        <span>● 항체 중쇄</span>
        <span>● 항체 경쇄</span>
      </div>
      <p className="view-explanation">
        {view.unmeasuredReason
          ? `접촉 잔기를 계산하지 않아 강조 없이 전체 구조만 표시합니다. ${view.unmeasuredReason}`
          : `4.5 Å 이내 접촉 잔기 ${count}개를 강조했습니다. 결합력·효능 판정은 아닙니다.`}
      </p>
      <p className="view-explanation">
        구조 예측 결과이며 실험으로 확인한 구조가 아닙니다. 파일을 받은 뒤
        sha256으로 실행 기록과 대조했습니다.
      </p>
    </article>
  );
}
