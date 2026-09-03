import type { ProvenanceGraphResponse, TraceLayer } from "../../types/provenance";

interface ProvenanceFallbackViewProps {
  graph: ProvenanceGraphResponse;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge?: (edgeId: string) => void;
  reason?: "webgl-unavailable" | "narrow-screen" | "user-choice";
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
  reason = "webgl-unavailable",
}: ProvenanceFallbackViewProps) {
  const notice = reason === "webgl-unavailable"
    ? ["WebGL 不可用", "当前显示只读三层列表，节点和证据仍可审计。"]
    : reason === "narrow-screen"
      ? ["小屏兼容视图", "为保证可读性，当前优先显示三层列表；可在上方手动启用 3D。"]
      : ["兼容视图", "当前显示只读三层列表，节点和证据仍可审计。"];

  return (
    <section className="provenance-fallback" aria-label="溯源图只读兼容视图">
      <div role={reason === "webgl-unavailable" ? "alert" : "status"}>
        <strong>{notice[0]}</strong>
        <span>{notice[1]}</span>
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
