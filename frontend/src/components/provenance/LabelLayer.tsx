import { Html } from "@react-three/drei";

import type { ProvenanceNode } from "../../types/provenance";
import type { ProvenancePosition } from "./layout";
import { nodeVisual } from "./visualEncoding";

interface LabelLayerProps {
  nodes: ProvenanceNode[];
  positions: Map<string, ProvenancePosition>;
  selectedNodeId: string | null;
  maxLabels?: number;
}

export function LabelLayer({
  nodes,
  positions,
  selectedNodeId,
  maxLabels = 80,
}: LabelLayerProps) {
  const visible = nodes
    .filter((node) => positions.has(node.id))
    .sort((left, right) => {
      if (left.id === selectedNodeId) return -1;
      if (right.id === selectedNodeId) return 1;
      return (right.confidence ?? 0) - (left.confidence ?? 0);
    })
    .slice(0, maxLabels);
  return (
    <>
      {visible.map((node) => {
        const position = positions.get(node.id)!;
        const visual = nodeVisual(node);
        return (
          <Html
            key={node.id}
            position={[position.x, position.y + 0.68, position.z]}
            center
            distanceFactor={18}
            style={{ pointerEvents: "none" }}
          >
            <span className="provenance-node-label" data-layer={node.layer}>
              {visual.glyph ? `${visual.glyph} ` : ""}
              {node.label}
            </span>
          </Html>
        );
      })}
    </>
  );
}
