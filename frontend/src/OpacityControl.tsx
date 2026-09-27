import { useId } from "react";

export function OpacityControl({ value, adjustable, onChange }: {
  value: number;
  adjustable: boolean;
  onChange: (value: number) => void;
}) {
  const id = useId();
  const percent = Math.round(value * 100);
  const fill = Math.round((value - 0.1) / 0.9 * 100);

  function keepVisible() {
    window.requestAnimationFrame(() => {
      const popup = document.getElementById(id);
      if (!popup?.matches(":popover-open")) return;
      const rect = popup.getBoundingClientRect();
      if (rect.top < 16) window.scrollBy({ top: rect.top - 16, behavior: "auto" });
      else if (rect.bottom > window.innerHeight - 16) window.scrollBy({ top: rect.bottom - window.innerHeight + 16, behavior: "auto" });
    });
  }

  return <>
    <button className="viewer-button structure-opacity-trigger" popoverTarget={id} popoverTargetAction="toggle" onClick={keepVisible}>불투명도 {percent}%</button>
    <div id={id} className="structure-opacity-popover" popover="auto" role="dialog" aria-modal="false" aria-label="불투명도 조절">
      <label className="structure-opacity-control">
        <span>HER2 표면 불투명도</span><output>{percent}%</output>
        <input aria-label="HER2 표면 불투명도" type="range" min=".1" max="1" step=".05" disabled={!adjustable} value={value}
          style={{ background: `linear-gradient(to right, var(--color-accent) ${fill}%, var(--border) ${fill}%)` }}
          onChange={(event) => onChange(Number(event.target.value))} />
      </label>
      {!adjustable && <p>전체 보기의 혼합·표면 표현에서 조절할 수 있습니다.</p>}
    </div>
  </>;
}
