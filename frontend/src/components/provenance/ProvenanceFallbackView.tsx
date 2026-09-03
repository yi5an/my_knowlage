import type { ProvenanceGraphResponse, TraceLayer } from "../../types/provenance";

interface ProvenanceFallbackViewProps {
  graph: ProvenanceGraphResponse;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge?: (edgeId: string) => void;
}

const LAYERS: Array<[TraceLayer, string]> = [
  ["conclusion", "结论层"],
  ["event", "事件 / 事实层"],
  ["evidence", "证据层"],
];

export function ProvenanceFallbackView({
  graph,
  onSelectNode,
  onSelectEdge,
}: ProvenanceFallbackViewProps) {
  return (
    <section className="provenance-fallback" aria-label="溯源图只读降级视图">
      <div role="alert">
        <strong>WebGL 不可用</strong>
        <span>当前显示只读三层列表，节点和证据仍可审计。</span>
      </div>
      <div className="provenance-fallback__layers">
        {LAYERS.map(([layer, label]) => (
          <section key={layer}>
            <h2>{label}</h2>
            <ul>
              {graph.nodes
                .filter((node) => node.layer === layer)
                .map((node) => (
                  <li key={node.id}>
                    <button type="button" onClick={() => onSelectNode(node.id)}>
                      {node.label}
                    </button>
                  </li>
                ))}
            </ul>
          </section>
        ))}
      </div>
      {graph.edges.length ? (
        <section>
          <h2>关系</h2>
          <ul>
            {graph.edges.map((edge) => (
              <li key={edge.id}>
                <button type="button" onClick={() => onSelectEdge?.(edge.id)}>
                  {edge.source_id} → {edge.relation_type} → {edge.target_id}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
