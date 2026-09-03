import { describe, expect, it } from "vitest";

import type { ProvenanceGraphResponse, ProvenanceNode } from "../../types/provenance";
import { LAYER_Y, computeProvenanceLayout } from "./layout";

const nodes: ProvenanceNode[] = [
  {
    id: "conclusion-1",
    layer: "conclusion",
    node_type: "research",
    backing_type: "conclusion",
    backing_id: "conclusion-1",
    label: "Conclusion",
    occurred_at: null,
    confidence: 0.8,
    review_status: "confirmed",
    validation_status: "supported",
    properties: {},
  },
  {
    id: "event-1",
    layer: "event",
    node_type: "policy",
    backing_type: "knowledge_event",
    backing_id: "event-1",
    label: "Event",
    occurred_at: null,
    confidence: 0.7,
    review_status: "pending_review",
    validation_status: "unverified",
    properties: {},
  },
  {
    id: "event-2",
    layer: "event",
    node_type: "policy",
    backing_type: "knowledge_event",
    backing_id: "event-2",
    label: "Event 2",
    occurred_at: null,
    confidence: 0.6,
    review_status: "pending_review",
    validation_status: "unverified",
    properties: {},
  },
  {
    id: "evidence-1",
    layer: "evidence",
    node_type: "text_span",
    backing_type: "evidence_anchor",
    backing_id: "evidence-1",
    label: "Evidence",
    occurred_at: null,
    confidence: 1,
    review_status: null,
    validation_status: "valid",
    properties: {},
  },
];

function graph(orderedNodes = nodes): ProvenanceGraphResponse {
  return {
    nodes: orderedNodes,
    edges: [],
    clusters: [
      { id: "policy", layer: "event", label: "Policy", node_ids: ["event-1", "event-2"], count: 2 },
    ],
    graph_version: "v1",
    degraded: false,
    degraded_reason: null,
    total_nodes: orderedNodes.length,
    returned_nodes: orderedNodes.length,
    has_more: false,
    next_cursor: null,
  };
}

describe("computeProvenanceLayout", () => {
  it("places every semantic layer on its fixed Y plane", () => {
    const result = computeProvenanceLayout(graph(), "all");
    expect(result.get("conclusion-1")?.y).toBe(LAYER_Y.conclusion);
    expect(result.get("event-1")?.y).toBe(LAYER_Y.event);
    expect(result.get("evidence-1")?.y).toBe(LAYER_Y.evidence);
  });

  it("is stable across calls and response ordering", () => {
    const first = computeProvenanceLayout(graph(), "filters=a");
    const second = computeProvenanceLayout(graph([...nodes].reverse()), "filters=a");
    expect([...second.entries()].sort()).toEqual([...first.entries()].sort());
  });

  it("uses the graph version and filter seed", () => {
    const first = computeProvenanceLayout(graph(), "filters=a");
    const second = computeProvenanceLayout(graph(), "filters=b");
    expect(second.get("event-1")).not.toEqual(first.get("event-1"));
  });

  it("produces finite, separated positions and keeps a cluster locally grouped", () => {
    const result = computeProvenanceLayout(graph(), "all");
    for (const position of result.values()) {
      expect(Number.isFinite(position.x)).toBe(true);
      expect(Number.isFinite(position.y)).toBe(true);
      expect(Number.isFinite(position.z)).toBe(true);
    }
    const event1 = result.get("event-1")!;
    const event2 = result.get("event-2")!;
    expect(Math.hypot(event1.x - event2.x, event1.z - event2.z)).toBeGreaterThan(0.65);
    expect(Math.hypot(event1.x - event2.x, event1.z - event2.z)).toBeLessThan(8);
  });
});
