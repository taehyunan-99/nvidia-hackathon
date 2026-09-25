import { useEffect, useRef, useState } from "react";
import type { PluginContext } from "molstar/lib/mol-plugin/context";
import type { ViewOptions } from "./molecular-viewer";
import { Vec3 } from "molstar/lib/mol-math/linear-algebra/3d/vec3";
import "./structure-preview.css";
type ViewerActions = Awaited<
  ReturnType<typeof import("./molecular-viewer").loadMolecule>
>;
const defaults: ViewOptions = {
  view: "overview",
  opacity: 1,
  hideAntibody: false,
  context: false,
  labels: false,
};
export default function StructurePreview() {
  const host = useRef<HTMLDivElement>(null),
    activePlugin = useRef<PluginContext | null>(null),
    actions = useRef<ViewerActions | null>(null);
  const [pdb, setPdb] = useState("1N8Z"),
    [mode, setMode] = useState("mixed"),
    [retry, setRetry] = useState(0);
  const [options, setOptions] = useState<ViewOptions>(defaults),
    optionsRef = useRef(options);
  const [status, setStatus] = useState("loading"),
    [count, setCount] = useState(0),
    [hasContext, setHasContext] = useState(false),
    [message, setMessage] = useState("");
  const [spinning, setSpinning] = useState(
      () => !matchMedia("(prefers-reduced-motion: reduce)").matches,
    ),
    spinRef = useRef(spinning);
  function rotate(enabled: boolean) {
    spinRef.current = enabled;
    setSpinning(enabled);
    activePlugin.current?.canvas3d?.setProps({
      trackball: {
        animate: enabled
          ? {
              name: "spin",
              params: { speed: 0.025, axis: Vec3.create(0, 1, 0) },
            }
          : { name: "off", params: {} },
      },
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
    let cancelled = false,
      plugin: PluginContext | undefined,
      loaded: ViewerActions | undefined;
    const abort = new AbortController(),
      element = document.createElement("canvas"),
      container = host.current!;
    element.setAttribute("aria-label", `${pdb} HER2와 항체 Fab 구조`);
    container.prepend(element);
    actions.current = null;
    setStatus("loading");
    setMessage("");
    setOptions(defaults);
    optionsRef.current = defaults;
    async function start() {
      try {
        const module = await import("./molecular-viewer");
        if (cancelled) {
          element.remove();
          return;
        }
        plugin = await module.createMolecularViewer(element, container);
        if (cancelled) {
          plugin.dispose();
          element.remove();
          return;
        }
        activePlugin.current = plugin;
        const [file, metadata] = await Promise.all([
          fetch(`/structures/${pdb}.cif`, { signal: abort.signal }),
          fetch("/structures/contacts.json", { signal: abort.signal }),
        ]);
        if (!file.ok || !metadata.ok)
          throw new Error("구조 파일을 불러오지 못했습니다.");
        const text = await file.text(),
          entry = (await metadata.json())[pdb];
        const digest = Array.from(
          new Uint8Array(
            await crypto.subtle.digest(
              "SHA-256",
              new TextEncoder().encode(text),
            ),
          ),
        )
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("");
        if (digest !== entry.sha256)
          throw new Error("구조 파일 검증에 실패했습니다.");
        if (cancelled) return;
        loaded = await module.loadMolecule(
          plugin,
          text,
          pdb,
          mode,
          entry.residues,
          container,
        );
        if (cancelled) {
          loaded.dispose();
          return;
        }
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
      loaded?.dispose();
      if (plugin) {
        plugin.dispose();
        element.remove();
      }
    };
  }, [pdb, mode, retry]);
  const ready = status === "ready";
  return (
    <section
      id="structure-preview"
      className="structure-preview"
      aria-label="공개 실험 구조 미리보기"
    >
      <div className="section-heading">
        <div>
          <h3>공개 실험 구조</h3>
          <span className="caption">모의 분석 결과와 별개</span>
        </div>
      </div>
      <div className="structure-candidates" aria-label="공개 항체 선택">
        {[
          ["1N8Z", "Herceptin"],
          ["1S78", "Pertuzumab"],
        ].map(([id, name]) => (
          <button key={id} aria-pressed={pdb === id} onClick={() => setPdb(id)}>
            {name}
            <small>{id}</small>
          </button>
        ))}
      </div>
      <div className="structure-views" aria-label="3D 보기 선택">
        <button
          disabled={!ready}
          aria-pressed={options.view === "overview"}
          onClick={() => void change({ view: "overview" }, true)}
        >
          전체 보기
        </button>
        <button
          disabled={!ready}
          aria-pressed={options.view === "contacts"}
          onClick={() => void change({ view: "contacts" }, true)}
        >
          접촉 부위 보기
        </button>
      </div>
      <div className="context-action">
        <label>
          <input
            type="checkbox"
            disabled={!ready || !hasContext}
            checked={options.context}
            onChange={(e) =>
              void change(
                {
                  context: e.target.checked,
                  view: e.target.checked ? "context" : "overview",
                },
                true,
              )
            }
          />{" "}
          확보된 당·기타 성분 보기
        </label>
        {options.context && (
          <button
            disabled={!ready}
            onClick={() => void change({ view: "context" }, true)}
          >
            성분 위치 다시 보기 ↗
          </button>
        )}
      </div>
      <div
        ref={host}
        className="molecule-canvas"
        onPointerDown={() => rotate(false)}
        onWheel={() => rotate(false)}
      >
        {!ready && (
          <div className="structure-status" role="status">
            {status === "loading" ? "구조를 불러오는 중…" : status}
            {status !== "loading" && (
              <button onClick={() => setRetry((x) => x + 1)}>
                다시 불러오기
              </button>
            )}
          </div>
        )}
        <span className="canvas-mode">
          {options.view === "contacts"
            ? "접촉 부위 · 나머지 구조 흐리게"
            : options.view === "context"
              ? "당·기타 성분 · 자홍색 강조"
              : "전체 구조"}
        </span>
      </div>
      <div className="structure-legend">
        <span>● HER2</span>
        <span>● 항체 중쇄</span>
        <span>● 항체 경쇄</span>
        {options.context && <span>● 당·기타 성분</span>}
      </div>
      <p className="view-explanation" aria-live="polite">
        {options.view === "contacts"
          ? `4.5 Å 이내 근접 잔기 ${count}개 중 표시 중인 사슬의 원자를 선명하게 보여줍니다. 결합력·충돌 판정은 아닙니다.`
          : options.view === "context"
            ? "확보된 당·기타 성분은 자홍색, 단백질은 흐리게 표시합니다. 완전한 당쇄·세포 환경은 아닙니다."
            : "HER2 표면과 항체 리본으로 전체 배치를 확인하세요."}
        {options.hideAntibody ? " 항체는 숨겨져 있습니다." : ""}
      </p>
      <div className="structure-controls">
        <button
          className="rotation-toggle"
          disabled={!ready || options.view !== "overview"}
          aria-pressed={spinning}
          onClick={() => rotate(!spinning)}
        >
          {options.view !== "overview"
            ? "집중 보기 · 회전 정지"
            : spinning
              ? "자동 회전 중 · 일시정지"
              : "자동 회전 재개"}
        </button>
        <button
          className="viewer-button"
          disabled={!ready}
          onClick={() => void change({ view: options.view }, true)}
        >
          시점 초기화
        </button>
      </div>
      <div className="structure-adjustments">
        <label>
          <input
            type="checkbox"
            disabled={!ready}
            checked={options.hideAntibody}
            onChange={(e) => void change({ hideAntibody: e.target.checked })}
          />{" "}
          항체 숨기기
        </label>
        <label>
          <input
            type="checkbox"
            disabled={!ready}
            checked={options.labels}
            onChange={(e) => void change({ labels: e.target.checked })}
          />{" "}
          구조 이름 표시
        </label>
        <label className="opacity-control">
          HER2 표면 불투명도{" "}
          <output>{Math.round(options.opacity * 100)}%</output>
          <input
            aria-label="HER2 표면 불투명도"
            type="range"
            min=".1"
            max="1"
            step=".05"
            disabled={
              !ready || mode === "cartoon" || options.view !== "overview"
            }
            value={options.opacity}
            onChange={(e) => void change({ opacity: Number(e.target.value) })}
          />
        </label>
      </div>
      <section className="structure-source" aria-label="표현·출처·표시 범위">
        <h4>표현·출처·표시 범위</h4>
        <label className="representation-control">
          표현{" "}
          <select
            aria-label="구조 표현"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="mixed">혼합</option>
            <option value="cartoon">리본</option>
            <option value="surface">표면</option>
          </select>
        </label>
        <p>
          <a
            href={`https://www.rcsb.org/structure/${pdb}`}
            target="_blank"
            rel="noreferrer"
          >
            RCSB {pdb}
          </a>{" "}
          · 실험 구조 · assembly 1 · HER2 세포외 영역 + 항체 Fab
        </p>
        <p>
          {options.context
            ? "파일의 비단백질 성분을 표시하며 물은 제외합니다."
            : "당·기타 성분은 숨겨져 있습니다. 없다는 뜻은 아닙니다."}{" "}
          전체 IgG·세포막·완전한 당쇄를 표현하지 않습니다.
        </p>
        <p>
          후보 전환 시 전체 보기로 초기화합니다. 구조 간 정렬 비교는 아직
          제공하지 않습니다.
        </p>
      </section>
      {message && <p role="alert">{message}</p>}
    </section>
  );
}
