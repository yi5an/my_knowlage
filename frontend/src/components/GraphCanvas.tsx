import { useMemo } from "react";
import { Tag, Tooltip } from "antd";

import type { GraphEdge, GraphNode } from "../services/graphApi";

export interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId?: string | null;
  onSelectNode?: (node: GraphNode) => void;
}

const NODE_COLORS: Record<string, string> = {
  entity: "#1677ff",
  organization: "#722ed1",
  product: "#13c2c2",
  person: "#eb2f96",
  technology: "#52c41a",
  concept: "#fa8c16",
  document: "#8c8c8c",
  entity_type: "#bfbfbf",
  chunk: "#d9d9d9",
};

const VIEWBOX = 600;

/**
 * A lightweight SVG graph renderer. Nodes are placed on concentric circles
 * around the selected node (or the centroid) so no physics engine is needed.
 * Keeps the bundle small while making the knowledge graph explorable.
 */
export function GraphCanvas({ nodes, edges, selectedId, onSelectNode }: GraphCanvasProps) {
  const positions = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    const center = { x: VIEWBOX / 2, y: VIEWBOX / 2 };
    if (nodes.length === 0) return map;

    if (selectedId && nodes.some((n) => n.id === selectedId)) {
      map.set(selectedId, center);
      const others = nodes.filter((n) => n.id !== selectedId);
      others.forEach((n, i) => {
        const angle = (i / others.length) * 2 * Math.PI;
        const radius = 180;
        map.set(n.id, {
          x: center.x + Math.cos(angle) * radius,
          y: center.y + Math.sin(angle) * radius,
        });
      });
    } else {
      nodes.forEach((n, i) => {
        const angle = (i / nodes.length) * 2 * Math.PI;
        const radius = nodes.length > 1 ? 200 : 0;
        map.set(n.id, {
          x: center.x + Math.cos(angle) * radius,
          y: center.y + Math.sin(angle) * radius,
        });
      });
    }
    return map;
  }, [nodes, selectedId]);

  if (nodes.length === 0) {
    return null;
  }

  return (
    <svg viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`} style={{ width: "100%", height: "100%" }}>
      {edges.map((e) => {
        const s = positions.get(e.source_id);
        const t = positions.get(e.target_id);
        if (!s || !t) return null;
        return (
          <g key={e.id}>
            <line x1={s.x} y1={s.y} x2={t.x} y2={t.y} stroke="#d9d9d9" strokeWidth={1.5} />
          </g>
        );
      })}
      {nodes.map((n) => {
        const pos = positions.get(n.id);
        if (!pos) return null;
        const color = NODE_COLORS[n.node_type] ?? "#1677ff";
        const isSelected = n.id === selectedId;
        return (
          <g
            key={n.id}
            transform={`translate(${pos.x},${pos.y})`}
            onClick={() => onSelectNode?.(n)}
            style={{ cursor: "pointer" }}
          >
            <Tooltip title={`${n.node_type}: ${n.label}`}>
              <circle r={isSelected ? 22 : 16} fill={color} opacity={isSelected ? 1 : 0.8} />
              <text
                textAnchor="middle"
                y={isSelected ? 38 : 30}
                fontSize={11}
                fill="#262626"
              >
                {n.label.length > 18 ? n.label.slice(0, 17) + "…" : n.label}
              </text>
            </Tooltip>
          </g>
        );
      })}
    </svg>
  );
}

export function NodeTypeLegend() {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
      {Object.entries(NODE_COLORS).map(([type, color]) => (
        <Tag key={type} style={{ color, borderColor: color }}>
          {type}
        </Tag>
      ))}
    </div>
  );
}
