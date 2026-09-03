import type { TraceLayer } from "../../types/provenance";

export const PROVENANCE_PALETTE = {
  stage: {
    background: "#eef2f6",
    surface: "#f8fafc",
    border: "#cbd5e1",
    text: "#172033",
    muted: "#475569",
  },
  layers: {
    conclusion: { node: "#5b21b6", plane: "#c4b5fd", edge: "#6d28d9" },
    event: { node: "#1d4ed8", plane: "#93c5fd", edge: "#1e40af" },
    evidence: { node: "#0f766e", plane: "#99f6e4", edge: "#115e59" },
  },
  statuses: {
    conflict: "#b91c1c",
    stale: "#c2410c",
    confirmed: "#15803d",
    inference: "#475569",
    qualified: "#b45309",
  },
} as const;

export function layerPalette(layer: TraceLayer) {
  return PROVENANCE_PALETTE.layers[layer];
}
