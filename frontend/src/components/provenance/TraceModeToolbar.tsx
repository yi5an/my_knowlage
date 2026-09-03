import type { TraceDirection } from "../../types/provenance";

interface TraceModeToolbarProps {
  mode: TraceDirection;
  onChange: (mode: TraceDirection) => void;
}

export function TraceModeToolbar({ mode, onChange }: TraceModeToolbarProps) {
  return (
    <div className="provenance-mode-toolbar" role="toolbar" aria-label="溯源方向">
      <button
        type="button"
        aria-pressed={mode === "down"}
        onClick={() => onChange("down")}
      >
        向下追证据
      </button>
      <button type="button" aria-pressed={mode === "up"} onClick={() => onChange("up")}>
        向上追结论
      </button>
    </div>
  );
}
