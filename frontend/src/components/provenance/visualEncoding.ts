import type {
  ProvenanceEdge,
  ProvenanceNode,
  TraceLayer,
} from "../../types/provenance";

export interface NodeVisual {
  color: string;
  glyph: "✓" | "!" | "◷" | "?" | "";
  scale: number;
}

export interface EdgeVisual {
  color: string;
  dashed: boolean;
  marker: "arrow" | "conflict";
  opacity: number;
}

const LAYER_COLORS: Record<TraceLayer, string> = {
  conclusion: "#a855f7",
  event: "#3b82f6",
  evidence: "#14b8a6",
};

const RELATION_COLORS: Record<ProvenanceEdge["relation_type"], string> = {
  supports: "#22c55e",
  refutes: "#ef4444",
  qualifies: "#f59e0b",
  explains: "#38bdf8",
  causes: "#8b5cf6",
  derived_from: "#60a5fa",
  aggregates: "#a78bfa",
  related_unconfirmed: "#94a3b8",
};

export function nodeVisual(node: ProvenanceNode): NodeVisual {
  const conflicted = node.validation_status === "conflicted" || node.validation_status === "refuted";
  const stale = node.validation_status === "stale" || node.validation_status === "invalid";
  const confirmed = node.review_status === "confirmed";
  return {
    color: conflicted ? "#ef4444" : stale ? "#f97316" : LAYER_COLORS[node.layer],
    glyph: conflicted ? "!" : stale ? "◷" : confirmed ? "✓" : node.review_status ? "?" : "",
    scale: 0.82 + Math.max(0, Math.min(1, node.confidence ?? 0.5)) * 0.36,
  };
}

export function edgeVisual(
  edge: ProvenanceEdge,
  selectedEdgeIds?: ReadonlySet<string>,
): EdgeVisual {
  const conflict =
    edge.relation_type === "refutes" ||
    edge.validation_status === "refuted" ||
    edge.validation_status === "conflicted";
  const hasSelection = Boolean(selectedEdgeIds?.size);
  return {
    color: conflict ? "#ef4444" : RELATION_COLORS[edge.relation_type],
    dashed:
      edge.review_status === "pending_review" ||
      edge.review_status === "ai_generated" ||
      edge.relation_type === "related_unconfirmed",
    marker: conflict ? "conflict" : "arrow",
    opacity: hasSelection ? (selectedEdgeIds?.has(edge.id) ? 1 : 0.1) : 0.48,
  };
}

export function buildInstanceNodeIds(
  nodes: readonly ProvenanceNode[],
  layer: TraceLayer,
): string[] {
  return nodes
    .filter((node) => node.layer === layer)
    .map((node) => node.id)
    .sort((left, right) => left.localeCompare(right));
}
