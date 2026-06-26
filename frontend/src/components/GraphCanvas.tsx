import { useEffect, useRef } from "react";
import { Graph } from "@antv/g6";

import {
  nodeImageUrl,
  nodeZhName,
  type GraphEdge,
  type GraphNode,
} from "../services/graphApi";
import { relationLabel } from "../utils/relationLabels";

export type LayoutKind = "force" | "radial" | "grid";

export interface GraphCanvasProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId?: string | null;
  /** ids of nodes connected to the selected node (for edge highlight). */
  highlightedNeighborIds?: Set<string>;
  layout?: LayoutKind;
  onSelectNode?: (node: GraphNode) => void;
  /** Right-click actions. */
  onContextAction?: (action: ContextAction, node: GraphNode) => void;
}

export type ContextAction = "expand" | "favorite" | "explain";

const NODE_STYLE: Record<
  string,
  { color: string; icon: string; label: string }
> = {
  organization: { color: "#722ed1", icon: "🏢", label: "公司" },
  company: { color: "#722ed1", icon: "🏢", label: "公司" },
  person: { color: "#eb2f96", icon: "👤", label: "人物" },
  technology: { color: "#52c41a", icon: "⚙️", label: "技术" },
  concept: { color: "#fa8c16", icon: "💡", label: "概念" },
  financial_metric: { color: "#faad14", icon: "📊", label: "财务" },
  document: { color: "#8c8c8c", icon: "📄", label: "文档" },
  entity: { color: "#1677ff", icon: "🔵", label: "实体" },
  entity_type: { color: "#bfbfbf", icon: "🏷️", label: "类型" },
  chunk: { color: "#d9d9d9", icon: "📝", label: "片段" },
};

function styleFor(type: string) {
  return NODE_STYLE[type] ?? NODE_STYLE.entity;
}

/**
 * Knowledge-graph renderer (AntV G6 v5).
 *
 * Interaction model:
 * - Left-click a node: select it (highlight + center), do NOT auto-expand.
 *   Expansion only happens via the right-click menu.
 * - Right-click a node: context menu (展开 / 收藏 / 解释).
 * - Selecting highlights the node and its incident edges.
 */
export function GraphCanvas({
  nodes,
  edges,
  selectedId,
  highlightedNeighborIds,
  layout = "force",
  onSelectNode,
  onContextAction,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const onSelectRef = useRef(onSelectNode);
  onSelectRef.current = onSelectNode;
  const onContextRef = useRef(onContextAction);
  onContextRef.current = onContextAction;
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;

  useEffect(() => {
    if (!containerRef.current) return;
    graphRef.current?.destroy();
    graphRef.current = null;

    const neighborSet = highlightedNeighborIds ?? new Set<string>();
    const isHighlightedEdge = (src: string, tgt: string) =>
      selectedId != null &&
      (src === selectedId || tgt === selectedId) &&
      (neighborSet.has(src) || src === selectedId) &&
      (neighborSet.has(tgt) || tgt === selectedId);

    const graph = new Graph({
      container: containerRef.current,
      autoFit: "view",
      data: toG6Data(nodes, edges),
      node: {
        type: "circle",
        style: {
          size: (d: { id?: string }) =>
            selectedId != null && d.id === selectedId ? 44 : 34,
          fill: (d: { data?: { node_type?: string } }) =>
            styleFor(d.data?.node_type ?? "").color,
          // Selected node: dark border + thicker; neighbors slightly emphasized.
          stroke: (d: { id?: string }) => {
            if (selectedId != null && d.id === selectedId) return "#fa541c";
            if (neighborSet.has(d.id ?? "")) return "#fa8c16";
            return "#ffffff";
          },
          lineWidth: (d: { id?: string }) => {
            if (selectedId != null && d.id === selectedId) return 3;
            if (neighborSet.has(d.id ?? "")) return 2;
            return 1;
          },
          cursor: "pointer",
          icon: true,
          iconText: (d: { data?: { node_type?: string; img?: string } }) =>
            d.data?.img ? "" : styleFor(d.data?.node_type ?? "").icon,
          iconSrc: (d: { data?: { img?: string } }) => d.data?.img ?? "",
          iconWidth: (d: { id?: string }) =>
            selectedId != null && d.id === selectedId ? 30 : 22,
          iconHeight: (d: { id?: string }) =>
            selectedId != null && d.id === selectedId ? 30 : 22,
          labelText: (d: { data?: { zh?: string; label?: string } }) => {
            const zh = d.data?.zh;
            const orig = d.data?.label ?? "";
            return zh ?? orig;
          },
          labelFontSize: 11,
          labelFill: "#262626",
          labelPosition: "bottom",
          labelOffsetY: 6,
        },
      },
      edge: {
        style: {
          stroke: (d: { source?: string; target?: string }) =>
            isHighlightedEdge(d.source ?? "", d.target ?? "") ? "#fa541c" : "#bfbfbf",
          lineWidth: (d: { source?: string; target?: string }) =>
            isHighlightedEdge(d.source ?? "", d.target ?? "") ? 3 : 1.5,
          label: true,
          labelText: (d: { data?: { relation_type?: string } }) =>
            relationLabel(d.data?.relation_type ?? ""),
          labelFontSize: 10,
          labelFill: "#595959",
          labelBackground: true,
          labelBackgroundFill: "#fff",
          labelBackgroundOpacity: 0.85,
          labelPadding: [2, 4],
        },
      },
      layout: layoutConfig(layout),
      behaviors: ["drag-element-force", "drag-canvas", "zoom-canvas", "click-select"],
      plugins: [
        {
          type: "contextmenu",
          trigger: "contextmenu",
          getContent: () =>
            [
              { key: "expand", label: "节点拓展" },
              { key: "favorite", label: "节点收藏" },
              { key: "explain", label: "实体解释" },
            ],
          onClick: (key: string, _target: unknown, current: { id?: string }) => {
            const node = nodesRef.current.find((n) => n.id === current.id);
            if (node) onContextRef.current?.(key as ContextAction, node);
          },
        },
      ],
    });

    // Left-click only selects (highlight + center). No auto-expand.
    graph.on("node:click", (evt: unknown) => {
      const id = (evt as { target?: { id?: string } }).target?.id;
      const node = nodesRef.current.find((n) => n.id === id);
      if (node) onSelectRef.current?.(node);
    });

    graphRef.current = graph;
    void graph.render().then(() => {
      setTimeout(() => {
        try {
          void graph.fitView();
        } catch {
          /* destroyed */
        }
        // Center on the selected node if any.
        if (selectedId) {
          try {
            void graph.focusElement?.(selectedId);
          } catch {
            /* focusElement may be unavailable in some versions */
          }
        }
      }, 500);
    });

    return () => {
      graph.destroy();
      graphRef.current = null;
    };
  }, [nodes, edges, selectedId, layout, highlightedNeighborIds]);

  return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
}

function toG6Data(nodes: GraphNode[], edges: GraphEdge[]) {
  return {
    nodes: nodes.map((n) => ({
      id: n.id,
      data: {
        label: n.label,
        node_type: n.node_type,
        zh: nodeZhName(n),
        img: nodeImageUrl(n),
      },
    })),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source_id,
      target: e.target_id,
      data: { relation_type: e.relation_type },
    })),
  };
}

function layoutConfig(kind: LayoutKind) {
  switch (kind) {
    case "radial":
      return { type: "radial", unitRadius: 110 };
    case "grid":
      return { type: "grid" };
    case "force":
    default:
      return {
        type: "d3-force",
        preventOverlap: true,
        nodeSize: 50,
        link: { distance: 170 },
        manyBody: { strength: -250 },
      };
  }
}

export function NodeTypeLegend() {
  const common = ["organization", "person", "technology", "concept", "financial_metric"];
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {common.map((t) => {
        const s = styleFor(t);
        return (
          <span
            key={t}
            style={{
              color: s.color,
              border: `1px solid ${s.color}`,
              borderRadius: 4,
              padding: "1px 6px",
              fontSize: 12,
            }}
          >
            {s.icon} {s.label}
          </span>
        );
      })}
    </div>
  );
}
