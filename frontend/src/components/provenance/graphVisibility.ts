import type {
  ProvenanceGraphResponse,
  ProvenanceNode,
} from "../../types/provenance";

export interface GraphVisibilityOptions {
  /** Show relationships whose source and target are on the same semantic layer. */
  showSameLayerRelations?: boolean;
  /** Keep selected nodes visible even when their only relationships are hidden. */
  preserveNodeIds?: Iterable<string>;
}

export interface GraphVisibilityResult {
  graph: ProvenanceGraphResponse;
  hiddenSameLayerEdgeCount: number;
}

function isSameLayer(source: ProvenanceNode | undefined, target: ProvenanceNode | undefined): boolean {
  return Boolean(source && target && source.layer === target.layer);
}

/**
 * Build the semantic view used by the provenance canvas.
 *
 * The API contains every registered provenance object and relationship. The
 * default view deliberately keeps only cross-layer relationships so a same-
 * layer aggregation (for example fact -> signal) cannot masquerade as an
 * evidence -> event -> conclusion path. Nodes that do not participate in the
 * visible view are omitted to avoid presenting an unconnected cloud.
 */
export function filterProvenanceGraph(
  graph: ProvenanceGraphResponse,
  options: GraphVisibilityOptions = {},
): GraphVisibilityResult {
  const showSameLayerRelations = options.showSameLayerRelations ?? false;
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const preserveNodeIds = new Set(options.preserveNodeIds ?? []);
  let hiddenSameLayerEdgeCount = 0;

  const edges = graph.edges.filter((edge) => {
    const sameLayer = isSameLayer(nodeById.get(edge.source_id), nodeById.get(edge.target_id));
    if (sameLayer && !showSameLayerRelations) {
      hiddenSameLayerEdgeCount += 1;
      return false;
    }
    return Boolean(nodeById.has(edge.source_id) && nodeById.has(edge.target_id));
  });

  const visibleNodeIds = new Set<string>(preserveNodeIds);
  edges.forEach((edge) => {
    visibleNodeIds.add(edge.source_id);
    visibleNodeIds.add(edge.target_id);
  });
  // A focused response can legitimately contain a standalone node. Preserve
  // that node when the response has no relationships at all; when hidden
  // same-layer relationships exist, the empty state below is more honest than
  // rendering an unconnected cloud.
  if (graph.edges.length === 0) {
    graph.nodes.forEach((node) => visibleNodeIds.add(node.id));
  }
  const nodes = graph.nodes.filter((node) => visibleNodeIds.has(node.id));
  const nodeIds = new Set(nodes.map((node) => node.id));
  const visibleEdges = edges.filter(
    (edge) => nodeIds.has(edge.source_id) && nodeIds.has(edge.target_id),
  );
  const clusters = graph.clusters
    .map((cluster) => {
      const node_ids = cluster.node_ids.filter((nodeId) => nodeIds.has(nodeId));
      return { ...cluster, node_ids, count: node_ids.length };
    })
    .filter((cluster) => cluster.node_ids.length > 0);
  return {
    hiddenSameLayerEdgeCount,
    graph: {
      ...graph,
      nodes,
      edges: visibleEdges,
      clusters,
      total_nodes: graph.total_nodes,
      returned_nodes: nodes.length,
      has_more: graph.has_more,
      next_cursor: graph.next_cursor,
    },
  };
}
