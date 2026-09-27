import { useEffect, useRef, useState } from "react";
import type { PluginContext } from "molstar/lib/mol-plugin/context";
import type { ViewOptions } from "./molecular-viewer";
import { OpacityControl } from "./OpacityControl";
import { Vec3 } from "molstar/lib/mol-math/linear-algebra/3d/vec3";
import "./structure-preview.css";

/** 이번 실행에 연결된 구조 파일과 분석 잔기를 검증해 표시한다. */

type Residue = { label_asym_id: string | null; label_seq_id: number | null };
type ViewerActions = Awaited<ReturnType<typeof import("./molecular-viewer").loadMolecule>>;
const defaults: ViewOptions = { view: "overview", opacity: 1, hideAntibody: false, context: false };

export type PredictedView = {
  kind: "experimental" | "predicted";
  candidateId: string;
  runId: string;
  artifactId: string;
  structureId: string;
  candidateName: string;
  source: { title: string; url: string; record_id: string | null };
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
  const activePlugin = useRef<PluginContext | null>(null);
  const actions = useRef<ViewerActions | null>(null);
  const [status, setStatus] = useState("loading");
  const [count, setCount] = useState(0);
  const [retry, setRetry] = useState(0);
  const [mode, setMode] = useState("mixed");
  const [options, setOptions] = useState<ViewOptions>(defaults);
  const optionsRef = useRef(options);
  const [hasContext, setHasContext] = useState(false);
  const [message, setMessage] = useState("");
  const [spinning, setSpinning] = useState(() => !matchMedia("(prefers-reduced-motion: reduce)").matches);
  const spinRef = useRef(spinning);

  function rotate(enabled: boolean) {
    spinRef.current = enabled;
    setSpinning(enabled);
    activePlugin.current?.canvas3d?.setProps({
      trackball: { animate: enabled ? { name: "spin", params: { speed: 0.025, axis: Vec3.create(0, 1, 0) } } : { name: "off", params: {} } },
    });
  }

  async function change(patch: Partial<ViewOptions>, focus = false) {
    const next = { ...optionsRef.current, ...patch };
    optionsRef.current = next;
    setOptions(next);
    if (next.view !== "overview" || focus) rotate(false);
    try {
      await actions.current?.update(next, focus);
    } catch {
      setMessage("표시 변경에 실패했습니다. 다시 불러와 주세요.");
    }
  }

  useEffect(() => {
    let cancelled = false;
    let plugin: PluginContext | undefined;
    const abort = new AbortController();
    const element = document.createElement("canvas");
    const container = host.current!;
    element.setAttribute(
      "aria-label",
      `${view.candidateName} ${view.kind === "experimental" ? "공개 실험" : "예측"} 복합체 구조`,
    );
    container.prepend(element);
    actions.current = null;
    setStatus("loading");
    setMessage("");
    setOptions(defaults);
    optionsRef.current = defaults;

    async function start() {
      try {
        const module = await import("./molecular-viewer");
        if (cancelled) return element.remove();
        plugin = await module.createMolecularViewer(element, container);
        if (cancelled) {
          plugin.dispose();
          return element.remove();
        }
        activePlugin.current = plugin;
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
          mode,
          residues,
          view.chains,
        );
        if (cancelled) return;
        actions.current = loaded;
        await loaded.update(defaults, true);
        if (cancelled) return;
        setCount(loaded.count);
        setHasContext(loaded.hasContext);
        setStatus("ready");
        rotate(spinRef.current);
      } catch (e) {
        if (!cancelled)
          setStatus(e instanceof Error ? e.message : "구조 표시 실패");
      }
    }
    void start();
    return () => {
      cancelled = true;
      abort.abort();
      actions.current = null;
      activePlugin.current = null;
      if (plugin) {
        plugin.dispose();
        element.remove();
      }
    };
  }, [apiBase, view.runId, view.artifactId, mode, retry]);

  const ready = status === "ready";
  let sourceUrl: string | null = null;
  try {
    const parsed = new URL(view.source.url);
    if (["https:", "http:"].includes(parsed.protocol)) sourceUrl = parsed.href;
  } catch { /* Keep an invalid source as text. */ }
  return (
    <article className="structure-preview" aria-label={`${view.candidateName} ${view.kind === "experimental" ? "실험" : "예측"} 구조`}>
      <div className="section-heading">
        <div>
          <h3>{view.candidateName}</h3>
          <span className="caption">{view.kind === "experimental" ? "이번 실행에서 대응한 공개 실험 구조" : "이번 실행의 Boltz-2 예측 결과"}</span>
        </div>
      </div>
      <div className="structure-toolbar" aria-label="3D 구조 조작">
        <div className="structure-control-group">
          <strong>관찰 위치</strong>
          <div className="structure-views" role="group" aria-label="3D 보기 선택">
            <button disabled={!ready} aria-pressed={options.view === "overview"} onClick={() => void change({ view: "overview" }, true)}>전체 보기</button>
            <button disabled={!ready || count === 0} aria-pressed={options.view === "contacts"} onClick={() => void change({ view: "contacts" }, true)}>접촉 부위 보기</button>
          </div>
        </div>
        <div className="structure-control-group">
          <strong>표현 방식</strong>
          <div className="structure-representations" role="group" aria-label="구조 표현">
            {(["mixed", "cartoon", "surface"] as const).map((value) => (
              <button key={value} aria-pressed={mode === value} onClick={() => setMode(value)}>{value === "mixed" ? "혼합" : value === "cartoon" ? "리본" : "표면"}</button>
            ))}
          </div>
        </div>
        <div className="structure-control-group">
          <strong>구조 성분</strong>
          <div className="structure-components" role="group" aria-label="구조 성분 선택">
            <button className="structure-context-toggle" disabled={!ready || !hasContext} aria-pressed={options.context}
              aria-label={options.context ? "당·기타 성분 표시 중" : "당·기타 성분 보기"}
              onClick={() => void change({ context: !options.context, view: options.context ? "overview" : "context" }, true)}>
              {options.context ? "성분 표시 중" : "당·기타 성분"}
            </button>
            <button className="structure-hide-toggle" disabled={!ready} aria-pressed={options.hideAntibody} onClick={() => void change({ hideAntibody: !options.hideAntibody })}>항체 숨기기</button>
          </div>
        </div>
        <div className="structure-control-group">
          <strong>시점 조작</strong>
          <div className="structure-camera-controls">
            <button className="rotation-toggle" disabled={!ready || options.view !== "overview"} aria-pressed={spinning} onClick={() => rotate(!spinning)}>
              {options.view !== "overview" ? "회전 정지" : spinning ? "회전 정지" : "회전 재개"}
            </button>
            <button className="viewer-button" disabled={!ready} onClick={() => void change({ view: options.view }, true)}>시점 초기화</button>
          </div>
        </div>
      </div>
      <div className="structure-canvas-heading">
        <OpacityControl value={options.opacity} adjustable={ready && mode !== "cartoon" && options.view === "overview"} onChange={(value) => void change({ opacity: value })} />
        <div className="structure-legend" aria-label="구조 색상 범례">
          <span>● HER2</span>
          <span>● 항체 중쇄{options.hideAntibody ? " · 숨김" : ""}</span>
          <span>● 항체 경쇄{options.hideAntibody ? " · 숨김" : ""}</span>
          {options.context && <span>● 당·기타 성분</span>}
        </div>
      </div>
      <div ref={host} className="molecule-canvas" onPointerDown={() => rotate(false)} onWheel={() => rotate(false)}>
        {!ready && (
          <div className="structure-status" role="status">
            {status === "loading" ? "구조 파일을 불러오는 중…" : status}
            {status !== "loading" && (
              <button onClick={() => setRetry((x) => x + 1)}>
                다시 불러오기
              </button>
            )}
          </div>
        )}
      </div>
      <p className="view-explanation">
        {!ready ? "접촉 잔기 강조를 준비하고 있습니다." : view.unmeasuredReason
          ? `접촉 잔기를 계산하지 않아 강조 없이 전체 구조만 표시합니다. ${view.unmeasuredReason}`
          : `4.5 Å 이내 접촉 잔기 ${count}개를 강조했습니다. 결합력·효능 판정은 아닙니다.`}
      </p>
      {message && <p role="alert">{message}</p>}
      <p className="view-explanation">
        {view.kind === "experimental" ? "공개 실험 구조를 이번 후보 서열과 대응했습니다." : "구조 예측 결과이며 실험으로 확인한 구조가 아닙니다."} 파일을 받은 뒤
        sha256으로 실행 기록과 대조했습니다.
      </p>
      <section className="structure-source" aria-label="표현·출처·표시 범위">
        <h4>표현·출처·표시 범위</h4>
        <p>{sourceUrl ? <a href={sourceUrl} target="_blank" rel="noreferrer">{view.source.title}</a> : view.source.title}{view.source.record_id ? ` · ${view.source.record_id}` : ""} · {view.kind === "experimental" ? "실험 구조" : "예측 구조"}</p>
        <p>{options.context ? "파일에 포함된 당·기타 성분을 표시합니다." : "당·기타 성분은 숨겨져 있습니다. 없다는 뜻은 아닙니다."} 전체 IgG·세포막·완전한 당쇄를 표현하지 않습니다.</p>
        <p>이번 실행의 파일과 잔기 대응을 표시합니다. 구조 간 정렬 비교는 제공하지 않습니다.</p>
      </section>
    </article>
  );
}
