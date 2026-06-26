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
 * - Right-click a node: context menu (展开 / 收藏 / 解释).
 *
 * Performance: the Graph is only created/destroyed when the data or layout
 * changes. Selecting a node updates element *states* (setElementState) and the
 * view, which G6 re-renders cheaply without rebuilding the canvas — so there
 * is no flicker.
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

  // --- create / destroy the graph only on data or layout change ---
  useEffect(() => {
    if (!containerRef.current) return;
    graphRef.current?.destroy();
    graphRef.current = null;

    const graph = new Graph({
      container: containerRef.current,
      data: toG6Data(nodes, edges),
      node: {
        type: "circle",
        style: {
          size: 34,
          fill: (d: { data?: { node_type?: string } }) =>
            styleFor(d.data?.node_type ?? "").color,
          stroke: "#ffffff",
          lineWidth: 1,
          cursor: "pointer",
          icon: true,
          iconText: (d: { data?: { node_type?: string; img?: string } }) =>
            d.data?.img ? "" : styleFor(d.data?.node_type ?? "").icon,
          iconSrc: (d: { data?: { img?: string } }) => d.data?.img ?? "",
          iconWidth: 22,
          iconHeight: 22,
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
        // State-driven styles: selecting a node flips these on without a rebuild.
        state: {
          selected: {
            size: 44,
            stroke: "#fa541c",
            lineWidth: 3,
            iconWidth: 30,
            iconHeight: 30,
            labelFontWeight: "bold",
          },
          highlight: {
            stroke: "#fa8c16",
            lineWidth: 2,
          },
          dim: {
            opacity: 0.35,
          },
        },
      },
      edge: {
        style: {
          stroke: "#bfbfbf",
          lineWidth: 1.5,
          // Arrow at the target end — relations (供应/上游/竞争...) are directed.
          endArrow: true,
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
        state: {
          highlight: { stroke: "#fa541c", lineWidth: 3 },
          dim: { opacity: 0.25 },
        },
      },
      layout: layoutConfig(layout),
      behaviors: ["drag-element-force", "drag-canvas", "zoom-canvas", "click-select"],
      plugins: [
        {
          type: "contextmenu",
          trigger: "contextmenu",
          getItems: () =>
            [
              { name: "节点拓展", value: "expand" },
              { name: "节点收藏", value: "favorite" },
              { name: "实体解释", value: "explain" },
            ],
          onClick: (value: string, _target: unknown, current: { id?: string }) => {
            const node = nodesRef.current.find((n) => n.id === current.id);
            if (node) onContextRef.current?.(value as ContextAction, node);
          },
        },
      ],
    });

    // Left-click only selects (handled by the selection effect). No auto-expand.
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
      }, 500);
    });

    return () => {
      graph.destroy();
      graphRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, layout]);

  // --- update selection highlight WITHOUT rebuilding the graph ---
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    const neighborSet = highlightedNeighborIds ?? new Set<string>();
    const allNodes = nodesRef.current;
    const allEdges = edges;

    // Node states: selected / highlight (neighbor) / dim (unrelated).
    for (const n of allNodes) {
      if (selectedId != null && n.id === selectedId) {
        void graph.setElementState(n.id, "selected");
      } else if (neighborSet.has(n.id)) {
        void graph.setElementState(n.id, "highlight");
      } else if (selectedId != null) {
        void graph.setElementState(n.id, "dim");
      } else {
        void graph.setElementState(n.id, []);
      }
    }

    // Edge states: highlight incident edges, dim the rest when something is selected.
    for (const e of allEdges) {
      const incident =
        selectedId != null &&
        (e.source_id === selectedId || e.target_id === selectedId);
      if (incident) {
        void graph.setElementState(e.id, "highlight");
      } else if (selectedId != null) {
        void graph.setElementState(e.id, "dim");
      } else {
        void graph.setElementState(e.id, []);
      }
    }

    // Center on the selected node. Disable the animation so it doesn't fight
    // with the force simulation ticking underneath.
    if (selectedId) {
      try {
        void graph.focusElement?.(selectedId, { animation: false } as never);
      } catch {
        /* focusElement may be unavailable in some versions */
      }
    }
  }, [selectedId, highlightedNeighborIds, edges]);

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
        // Converge fast so the layout stops ticking quickly; otherwise the
        // ongoing simulation moves nodes around after we focus one, and G6
        // re-fits the view on convergence — which looks like the canvas
        // shrinking a few seconds after clicking a node.
        alphaDecay: 0.05,
        alphaMin: 0.05,
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
