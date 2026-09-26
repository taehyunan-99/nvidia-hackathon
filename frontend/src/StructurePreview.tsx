import { useEffect, useRef, useState } from "react";
import type { PluginContext } from "molstar/lib/mol-plugin/context";
import type { ViewOptions } from "./molecular-viewer";
import { OpacityControl } from "./OpacityControl";
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
          {/* 이 뷰어는 분석 결과를 읽지 않는다. 자체 contacts.json만 본다.
              "모의"라고 적으면 실제 실행 중에도 모의로 읽히므로 mode와
              무관하게 참인 문구를 쓴다. */}
          <span className="caption">분석 결과와 별개</span>
        </div>
      </div>
      <div className="structure-toolbar" aria-label="3D 구조 조작">
        <div className="structure-control-group">
          <strong>공개 구조 예제</strong>
          <div className="structure-candidates" role="group" aria-label="공개 항체 선택">
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
        </div>
        <div className="structure-control-group">
          <strong>관찰 위치</strong>
          <div className="structure-views" role="group" aria-label="3D 보기 선택">
            <button disabled={!ready} aria-pressed={options.view === "overview"} onClick={() => void change({ view: "overview" }, true)}>
              전체 보기
            </button>
            <button disabled={!ready} aria-pressed={options.view === "contacts"} onClick={() => void change({ view: "contacts" }, true)}>
              접촉 부위 보기
            </button>
          </div>
        </div>
        <div className="structure-control-group">
          <strong>표현 방식</strong>
          <div className="structure-representations" role="group" aria-label="구조 표현">
            {(["mixed", "cartoon", "surface"] as const).map((value) => (
              <button key={value} aria-pressed={mode === value} onClick={() => setMode(value)}>
                {value === "mixed" ? "혼합" : value === "cartoon" ? "리본" : "표면"}
              </button>
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
        <div className="structure-controls">
          <div className="structure-camera-controls">
            <button className="rotation-toggle" disabled={!ready || options.view !== "overview"} aria-pressed={spinning} onClick={() => rotate(!spinning)}>
              {options.view !== "overview" ? "회전 정지" : spinning ? "회전 정지" : "회전 재개"}
            </button>
            <button className="viewer-button" disabled={!ready} onClick={() => void change({ view: options.view }, true)}>
              시점 초기화
            </button>
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
      </div>
      <p className="view-explanation" aria-live="polite">
        {options.view === "contacts"
          ? `4.5 Å 이내 근접 잔기 ${count}개 중 표시 중인 사슬의 원자를 선명하게 보여줍니다. 결합력·충돌 판정은 아닙니다.`
          : options.view === "context"
            ? "확보된 당·기타 성분은 자홍색, 단백질은 흐리게 표시합니다. 완전한 당쇄·세포 환경은 아닙니다."
            : "HER2 표면과 항체 리본으로 전체 배치를 확인하세요."}
        {options.hideAntibody ? " 항체는 숨겨져 있습니다." : ""}
      </p>
      <section className="structure-source" aria-label="표현·출처·표시 범위">
        <h4>표현·출처·표시 범위</h4>
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
          검토 후보·조건을 바꿔도 이 공개 구조 보기는 유지됩니다. 구조 간 정렬 비교는 아직
          제공하지 않습니다.
        </p>
      </section>
      {message && <p role="alert">{message}</p>}
    </section>
  );
}
