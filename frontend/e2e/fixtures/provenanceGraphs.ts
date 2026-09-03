import type {
  ProvenanceEdge,
  ProvenanceGraphResponse,
  ProvenanceNode,
  TraceEdgeDetail,
  TraceLayer,
} from "../../src/types/provenance";

const LAYERS: TraceLayer[] = ["evidence", "event", "conclusion"];

function node(index: number): ProvenanceNode {
  const layer = LAYERS[index % LAYERS.length];
  return {
    id: `${layer}-${index}`,
    layer,
    node_type: layer === "event" ? "policy" : layer,
    backing_type: layer === "event" ? "knowledge_event" : layer,
    backing_id: `${layer}-${index}`,
    label: `${layer === "conclusion" ? "结论" : layer === "event" ? "事件" : "证据"} ${index}`,
    occurred_at: null,
    confidence: 0.65 + (index % 30) / 100,
    review_status: layer === "evidence" ? null : index % 2 ? "pending_review" : "confirmed",
    validation_status: layer === "evidence" ? "valid" : "supported",
    properties: {},
  };
}

function edges(nodes: ProvenanceNode[]): ProvenanceEdge[] {
  const result: ProvenanceEdge[] = [];
  for (let index = 0; index + 2 < nodes.length; index += 3) {
    result.push(
      {
        id: `edge-evidence-event-${index}`,
        source_id: nodes[index].id,
        target_id: nodes[index + 1].id,
        relation_type: "derived_from",
        rationale: "证据提取为事件",
        confidence: 0.86,
        review_status: "confirmed",
        validation_status: "supported",
        origin_type: "ai",
        evidence_anchor_ids: [nodes[index].id],
        version_no: 1,
        model_metadata: { model: "e2e-fixture", prompt_version: "1" },
      },
      {
        id: `edge-event-conclusion-${index}`,
        source_id: nodes[index + 1].id,
        target_id: nodes[index + 2].id,
        relation_type: index % 6 === 0 ? "qualifies" : "supports",
        rationale: "事件支持结论",
        confidence: 0.8,
        review_status: "pending_review",
        validation_status: "unverified",
        origin_type: "ai",
        evidence_anchor_ids: [nodes[index].id],
        version_no: 1,
        model_metadata: { model: "e2e-fixture", prompt_version: "1" },
      },
    );
  }
  return result;
}

export function provenanceGraph(size: 100 | 500 | 2000): ProvenanceGraphResponse {
  const nodes = Array.from({ length: size }, (_, index) => node(index));
  const graphEdges = edges(nodes);
  return {
    nodes,
    edges: graphEdges,
    clusters: LAYERS.map((layer) => ({
      id: `cluster-${layer}`,
      layer,
      label: layer,
      node_ids: nodes.filter((item) => item.layer === layer).map((item) => item.id),
      count: nodes.filter((item) => item.layer === layer).length,
    })),
    graph_version: `fixture-${size}`,
    degraded: false,
    degraded_reason: null,
    total_nodes: size,
    returned_nodes: size,
    has_more: false,
    next_cursor: null,
  };
}

export function provenanceTrace(
  graph: ProvenanceGraphResponse,
  nodeId: string,
): ProvenanceGraphResponse {
  const nodeIds = new Set([nodeId]);
  let changed = true;
  while (changed) {
    changed = false;
    graph.edges.forEach((edge) => {
      if (nodeIds.has(edge.source_id) || nodeIds.has(edge.target_id)) {
        const before = nodeIds.size;
        nodeIds.add(edge.source_id);
        nodeIds.add(edge.target_id);
        changed ||= nodeIds.size !== before;
      }
    });
  }
  const nodes = graph.nodes.filter((item) => nodeIds.has(item.id));
  const traceEdges = graph.edges.filter(
    (edge) => nodeIds.has(edge.source_id) && nodeIds.has(edge.target_id),
  );
  return {
    ...graph,
    nodes,
    edges: traceEdges,
    clusters: graph.clusters
      .map((cluster) => ({
        ...cluster,
        node_ids: cluster.node_ids.filter((id) => nodeIds.has(id)),
        count: cluster.node_ids.filter((id) => nodeIds.has(id)).length,
      }))
      .filter((cluster) => cluster.count > 0),
    total_nodes: nodes.length,
    returned_nodes: nodes.length,
  };
}

export function edgeDetail(edge: ProvenanceEdge): TraceEdgeDetail {
  return {
    ...edge,
    review_history: [],
    evidence: [],
  };
}
