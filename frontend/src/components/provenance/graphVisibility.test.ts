import { describe, expect, it } from "vitest";

import type { ProvenanceGraphResponse } from "../../types/provenance";
import { filterProvenanceGraph } from "./graphVisibility";

const graph: ProvenanceGraphResponse = {
  nodes: [
    {
      id: "conclusion-1",
      layer: "conclusion",
      node_type: "conclusion",
      backing_type: "conclusion",
      backing_id: "conclusion-1",
      label: "结论",
      occurred_at: null,
      confidence: 0.9,
      review_status: "confirmed",
      validation_status: "supported",
      properties: {},
    },
    {
      id: "event-1",
      layer: "event",
      node_type: "event",
      backing_type: "knowledge_event",
      backing_id: "event-1",
      label: "事件",
      occurred_at: null,
      confidence: 0.8,
      review_status: "pending_review",
      validation_status: "unverified",
      properties: {},
    },
    {
      id: "event-2",
      layer: "event",
      node_type: "fact",
      backing_type: "investment_fact",
      backing_id: "event-2",
      label: "事实",
      occurred_at: null,
      confidence: 0.7,
      review_status: "pending_review",
      validation_status: "unverified",
      properties: {},
    },
    {
      id: "evidence-1",
      layer: "evidence",
      node_type: "evidence",
      backing_type: "evidence_anchor",
      backing_id: "evidence-1",
      label: "原文证据",
      occurred_at: null,
      confidence: 1,
      review_status: "confirmed",
      validation_status: "valid",
      properties: {},
    },
    {
      id: "orphan-1",
      layer: "event",
      node_type: "fact",
      backing_type: "investment_fact",
      backing_id: "orphan-1",
      label: "未连接事实",
      occurred_at: null,
      confidence: 0.5,
      review_status: "pending_review",
      validation_status: "unverified",
      properties: {},
    },
  ],
  edges: [
    {
      id: "edge-supports",
      source_id: "event-1",
      target_id: "conclusion-1",
      relation_type: "supports",
      rationale: null,
      confidence: 0.8,
      review_status: "confirmed",
      validation_status: "supported",
      origin_type: "ai",
      evidence_anchor_ids: [],
      version_no: 1,
      model_metadata: {},
    },
    {
      id: "edge-derived",
      source_id: "evidence-1",
      target_id: "event-1",
      relation_type: "derived_from",
      rationale: null,
      confidence: 0.9,
      review_status: "confirmed",
      validation_status: "supported",
      origin_type: "ai",
      evidence_anchor_ids: ["evidence-1"],
      version_no: 1,
      model_metadata: {},
    },
    {
      id: "edge-aggregate",
      source_id: "event-2",
      target_id: "event-1",
      relation_type: "aggregates",
      rationale: null,
      confidence: 0.6,
      review_status: "pending_review",
      validation_status: "unverified",
      origin_type: "rule",
      evidence_anchor_ids: [],
      version_no: 1,
      model_metadata: {},
    },
  ],
  clusters: [
    { id: "event", layer: "event", label: "事件", node_ids: ["event-1", "event-2", "orphan-1"], count: 3 },
  ],
  graph_version: "v1",
  degraded: false,
  degraded_reason: null,
  total_nodes: 5,
  returned_nodes: 5,
  has_more: false,
  next_cursor: null,
};

describe("filterProvenanceGraph", () => {
  it("hides same-layer relationships and unconnected nodes by default", () => {
    const result = filterProvenanceGraph(graph);

    expect(result.hiddenSameLayerEdgeCount).toBe(1);
    expect(result.graph.edges.map((edge) => edge.id)).toEqual(["edge-supports", "edge-derived"]);
    expect(result.graph.nodes.map((node) => node.id)).toEqual([
      "conclusion-1",
      "event-1",
      "evidence-1",
    ]);
    expect(result.graph.returned_nodes).toBe(3);
    expect(result.graph.has_more).toBe(false);
  });

  it("restores same-layer relationships when explicitly requested", () => {
    const result = filterProvenanceGraph(graph, { showSameLayerRelations: true });

    expect(result.hiddenSameLayerEdgeCount).toBe(0);
    expect(result.graph.edges).toHaveLength(3);
    expect(result.graph.nodes.map((node) => node.id)).toEqual([
      "conclusion-1",
      "event-1",
      "event-2",
      "evidence-1",
    ]);
  });

  it("preserves a selected node even when its only relationships are hidden", () => {
    const result = filterProvenanceGraph(graph, { preserveNodeIds: ["event-2"] });

    expect(result.graph.nodes.map((node) => node.id)).toContain("event-2");
    expect(result.graph.edges).toHaveLength(2);
  });

  it("keeps server pagination metadata after narrowing the visible node set", () => {
    const result = filterProvenanceGraph({
      ...graph,
      total_nodes: 50,
      returned_nodes: 5,
      has_more: true,
      next_cursor: "5",
    });

    expect(result.graph.total_nodes).toBe(50);
    expect(result.graph.returned_nodes).toBe(3);
    expect(result.graph.has_more).toBe(true);
    expect(result.graph.next_cursor).toBe("5");
  });
});
