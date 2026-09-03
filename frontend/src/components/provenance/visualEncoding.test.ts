import { describe, expect, it } from "vitest";

import type { ProvenanceEdge, ProvenanceNode } from "../../types/provenance";
import { buildInstanceNodeIds, edgeVisual, nodeVisual } from "./visualEncoding";

const node = (layer: ProvenanceNode["layer"], id: string = layer): ProvenanceNode => ({
  id,
  layer,
  node_type: "type",
  backing_type: "type",
  backing_id: id,
  label: id,
  occurred_at: null,
  confidence: 0.8,
  review_status: "pending_review",
  validation_status: "unverified",
  properties: {},
});

const edge = (overrides: Partial<ProvenanceEdge> = {}): ProvenanceEdge => ({
  id: "edge",
  source_id: "source",
  target_id: "target",
  relation_type: "supports",
  rationale: null,
  confidence: 0.8,
  review_status: "confirmed",
  validation_status: "supported",
  origin_type: "user",
  evidence_anchor_ids: [],
  version_no: 1,
  model_metadata: {},
  ...overrides,
});

describe("semantic visual encoding", () => {
  it("uses distinct layer colors", () => {
    expect(nodeVisual(node("conclusion")).color).toBe("#a855f7");
    expect(nodeVisual(node("event")).color).toBe("#3b82f6");
    expect(nodeVisual(node("evidence")).color).toBe("#14b8a6");
  });

  it("encodes review and validation state with glyphs as well as color", () => {
    expect(nodeVisual({ ...node("event"), review_status: "confirmed" }).glyph).toBe("✓");
    expect(nodeVisual({ ...node("event"), validation_status: "conflicted" }).glyph).toBe("!");
    expect(nodeVisual({ ...node("evidence"), validation_status: "stale" }).glyph).toBe("◷");
  });

  it("maps relation semantics and selected-path opacity", () => {
    expect(edgeVisual(edge()).color).toBe("#22c55e");
    expect(edgeVisual(edge({ relation_type: "qualifies" })).color).toBe("#f59e0b");
    expect(edgeVisual(edge({ relation_type: "refutes" })).marker).toBe("conflict");
    expect(edgeVisual(edge({ review_status: "pending_review" })).dashed).toBe(true);
    expect(edgeVisual(edge(), new Set(["edge"])).opacity).toBe(1);
    expect(edgeVisual(edge({ id: "other" }), new Set(["edge"])).opacity).toBeLessThan(0.2);
  });

  it("keeps a stable instance index to node id mapping", () => {
    const ids = buildInstanceNodeIds(
      [node("event", "z"), node("conclusion", "c"), node("event", "a")],
      "event",
    );
    expect(ids).toEqual(["a", "z"]);
    expect(ids[1]).toBe("z");
  });
});
