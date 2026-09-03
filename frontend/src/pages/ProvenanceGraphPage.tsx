import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { EvidenceAuditDrawer } from "../components/provenance/EvidenceAuditDrawer";
import { filterProvenanceGraph } from "../components/provenance/graphVisibility";
import { GraphLegend } from "../components/provenance/GraphLegend";
import { ProvenanceFallbackView } from "../components/provenance/ProvenanceFallbackView";
import { SpatialLayerCanvas3D } from "../components/provenance/SpatialLayerCanvas3D";
import { TraceModeToolbar } from "../components/provenance/TraceModeToolbar";
import { parseCameraState, serializeCameraState } from "../components/provenance/cameraState";
import { useProvenanceLayout } from "../components/provenance/useProvenanceLayout";
import { supportsWebGL } from "../components/provenance/webglSupport";
import { provenanceApi } from "../services/provenanceApi";
import type {
  ProvenanceGraphResponse,
  ProvenanceOverviewFilters,
  ReviewAction,
  TraceDirection,
  TraceEdgeDetail,
  TraceLayer,
} from "../types/provenance";

const WORKSPACE_ID = "ws_default";
const EMPTY_GRAPH: ProvenanceGraphResponse = {
  nodes: [],
  edges: [],
  clusters: [],
  graph_version: "empty",
  degraded: false,
  degraded_reason: null,
  total_nodes: 0,
  returned_nodes: 0,
  has_more: false,
  next_cursor: null,
};

interface PageState {
  graph: ProvenanceGraphResponse | null;
  edge: TraceEdgeDetail | null;
  loading: boolean;
  error: string | null;
  mode: TraceDirection;
  filters: ProvenanceOverviewFilters;
  showSameLayerRelations: boolean;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
}

type PageAction =
  | { type: "loading" }
  | { type: "loaded"; graph: ProvenanceGraphResponse }
  | { type: "failed"; error: string }
  | { type: "mode"; mode: TraceDirection }
  | { type: "filter"; filters: ProvenanceOverviewFilters }
  | { type: "same_layer"; visible: boolean }
  | { type: "select_node"; nodeId: string | null }
  | { type: "select_edge"; edgeId: string | null }
  | { type: "edge_loaded"; edge: TraceEdgeDetail | null };

function parseInitialState(search: string): PageState {
  const params = new URLSearchParams(search);
  const layer = params.get("layer");
  const minConfidence = Number(params.get("min_confidence"));
  return {
    graph: null,
    edge: null,
    loading: true,
    error: null,
    mode: params.get("mode") === "up" ? "up" : "down",
    filters: {
      layer: ["conclusion", "event", "evidence"].includes(layer ?? "")
        ? (layer as TraceLayer)
        : undefined,
      display_status: params.get("status") ?? undefined,
      min_confidence: Number.isFinite(minConfidence) && minConfidence > 0 ? minConfidence : undefined,
      cursor: params.get("cursor") ?? undefined,
    },
    showSameLayerRelations: params.get("same_layer") === "1",
    selectedNodeId: params.get("node"),
    selectedEdgeId: params.get("edge"),
  };
}

function reducer(state: PageState, action: PageAction): PageState {
  switch (action.type) {
    case "loading":
      return { ...state, loading: true, error: null };
    case "loaded":
      return { ...state, loading: false, error: null, graph: action.graph };
    case "failed":
      return { ...state, loading: false, error: action.error };
    case "mode":
      return { ...state, mode: action.mode };
    case "filter":
      return { ...state, filters: action.filters, selectedNodeId: null };
    case "same_layer":
      return { ...state, showSameLayerRelations: action.visible };
    case "select_node":
      return { ...state, selectedNodeId: action.nodeId, selectedEdgeId: null, edge: null };
    case "select_edge":
      return { ...state, selectedEdgeId: action.edgeId, edge: null };
    case "edge_loaded":
      return { ...state, edge: action.edge };
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "未知错误";
}

export function ProvenanceGraphPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, dispatch] = useReducer(reducer, searchParams.toString(), (search) =>
    parseInitialState(search ? `?${search}` : ""),
  );
  const [viewMode, setViewMode] = useState<"auto" | "3d" | "fallback">("auto");
  const [narrowScreen, setNarrowScreen] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(max-width: 760px)").matches : false,
  );
  const webglAvailable = useMemo(() => supportsWebGL(), []);
  const graphRequest = useRef(0);
  const edgeRequest = useRef(0);
  const searchParamsRef = useRef(searchParams);
  const observedSearchRef = useRef(searchParams.toString());
  const observedSearch = searchParams.toString();
  if (observedSearchRef.current !== observedSearch) {
    observedSearchRef.current = observedSearch;
    searchParamsRef.current = searchParams;
  }

  useEffect(() => {
    const query = window.matchMedia("(max-width: 760px)");
    const update = () => setNarrowScreen(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  const updateUrl = useCallback(
    (changes: Record<string, string | null>) => {
      const next = new URLSearchParams(searchParamsRef.current);
      Object.entries(changes).forEach(([key, value]) => {
        if (value) next.set(key, value);
        else next.delete(key);
      });
      searchParamsRef.current = next;
      setSearchParams(next, { replace: true });
    },
    [setSearchParams],
  );

  useEffect(() => {
    const requestId = ++graphRequest.current;
    const controller = new AbortController();
    dispatch({ type: "loading" });
    const request = state.selectedNodeId
      ? provenanceApi.traceNode(
          state.selectedNodeId,
          state.mode,
          WORKSPACE_ID,
          500,
          controller.signal,
        )
      : provenanceApi.overview(state.filters, WORKSPACE_ID, controller.signal);
    void request
      .then((graph) => {
        if (!controller.signal.aborted && requestId === graphRequest.current) {
          dispatch({ type: "loaded", graph });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && requestId === graphRequest.current) {
          dispatch({ type: "failed", error: errorMessage(error) });
        }
      });
    return () => controller.abort();
  }, [state.filters, state.mode, state.selectedNodeId]);

  const loadEdge = useCallback(async () => {
    if (!state.selectedEdgeId) {
      dispatch({ type: "edge_loaded", edge: null });
      return;
    }
    const requestId = ++edgeRequest.current;
    const edge = await provenanceApi.edge(state.selectedEdgeId, WORKSPACE_ID);
    if (requestId === edgeRequest.current) dispatch({ type: "edge_loaded", edge });
  }, [state.selectedEdgeId]);

  useEffect(() => {
    void loadEdge();
    return () => {
      edgeRequest.current += 1;
    };
  }, [loadEdge]);

  const rawGraph = state.graph ?? EMPTY_GRAPH;
  const visibility = useMemo(
    () =>
      filterProvenanceGraph(rawGraph, {
        showSameLayerRelations: state.showSameLayerRelations,
        preserveNodeIds: state.selectedNodeId ? [state.selectedNodeId] : [],
      }),
    [rawGraph, state.selectedNodeId, state.showSameLayerRelations],
  );
  const graph = visibility.graph;
  const serializedFilters = useMemo(
    () => JSON.stringify({ ...state.filters, mode: state.mode }),
    [state.filters, state.mode],
  );
  const positions = useProvenanceLayout(graph, serializedFilters);
  const selectedEdgeIds = useMemo(
    () =>
      new Set(
        state.selectedEdgeId
          ? [state.selectedEdgeId]
          : state.selectedNodeId
            ? graph.edges.map((edge) => edge.id)
            : [],
      ),
    [graph.edges, state.selectedEdgeId, state.selectedNodeId],
  );

  const selectNode = (nodeId: string) => {
    dispatch({ type: "select_node", nodeId });
    updateUrl({ node: nodeId, edge: null });
  };
  const selectEdge = (edgeId: string) => {
    dispatch({ type: "select_edge", edgeId });
    updateUrl({ edge: edgeId });
  };
  const clearSelection = () => {
    dispatch({ type: "select_node", nodeId: null });
    updateUrl({ node: null, edge: null });
  };
  const setMode = (mode: TraceDirection) => {
    dispatch({ type: "mode", mode });
    updateUrl({ mode });
  };
  const setLayer = (value: string) => {
    const layer = value ? (value as TraceLayer) : undefined;
    const filters = { ...state.filters, layer };
    delete filters.cursor;
    dispatch({ type: "filter", filters });
    updateUrl({ layer: value || null, node: null, cursor: null });
  };
  const setSameLayerRelations = (visible: boolean) => {
    dispatch({ type: "same_layer", visible });
    updateUrl({ same_layer: visible ? "1" : null });
  };

  const reviewEdge = async (action: ReviewAction, version: number, note: string) => {
    if (!state.selectedEdgeId) return;
    await provenanceApi.reviewEdge(
      state.selectedEdgeId,
      { action, version_no: version, reviewer_id: "local-user", note },
      WORKSPACE_ID,
    );
    await loadEdge();
  };

  const initialCamera = useRef(parseCameraState(searchParams)).current;
  const showFallback =
    !webglAvailable || viewMode === "fallback" || (viewMode === "auto" && narrowScreen);
  const fallbackReason = !webglAvailable
    ? "webgl-unavailable" as const
    : viewMode === "auto" && narrowScreen
      ? "narrow-screen" as const
      : "user-choice" as const;

  return (
    <main className="provenance-page">
      <header className="provenance-page__header">
        <div>
          <p className="provenance-page__eyebrow">AUDITABLE KNOWLEDGE GRAPH</p>
          <h1>事件结论溯源</h1>
          <p>从结论穿过事件与事实，一直回到可定位、可复核的原始证据。</p>
        </div>
        <div className="provenance-page__stats" aria-label="图统计">
          <span><strong>{graph.returned_nodes}</strong> 已显示</span>
          <span><strong>{graph.edges.length}</strong> 关系</span>
          <button
            type="button"
            onClick={() => setViewMode(showFallback && webglAvailable ? "3d" : "fallback")}
          >
            {showFallback && webglAvailable ? "启用 3D 视图" : "使用兼容视图"}
          </button>
        </div>
      </header>

      <section className="provenance-stage">
        <div className="provenance-stage__toolbar">
          <TraceModeToolbar mode={state.mode} onChange={setMode} />
          <label>
            层级
            <select aria-label="层级筛选" value={state.filters.layer ?? ""} onChange={(event) => setLayer(event.target.value)}>
              <option value="">全部层级</option>
              <option value="conclusion">结论层</option>
              <option value="event">事件 / 事实层</option>
              <option value="evidence">证据层</option>
            </select>
          </label>
          {visibility.hiddenSameLayerEdgeCount > 0 || state.showSameLayerRelations ? (
            <button
              type="button"
              aria-pressed={state.showSameLayerRelations}
              onClick={() => setSameLayerRelations(!state.showSameLayerRelations)}
            >
              {state.showSameLayerRelations
                ? "隐藏同层关系"
                : `显示同层关系 (${visibility.hiddenSameLayerEdgeCount})`}
            </button>
          ) : null}
          {state.selectedNodeId || state.selectedEdgeId ? (
            <button type="button" onClick={clearSelection}>返回全图</button>
          ) : null}
        </div>

        {graph.degraded ? (
          <div className="provenance-banner provenance-banner--warning" role="alert">
            图存储不可用，当前为 PostgreSQL 有界降级结果：{graph.degraded_reason ?? "未知原因"}
          </div>
        ) : null}
        {rawGraph.has_more ? (
          <div className="provenance-banner" role="status">
            结果较大，接口返回 {rawGraph.returned_nodes}/{rawGraph.total_nodes} 个节点；选中节点可查看完整聚焦路径。
          </div>
        ) : null}
        {state.error ? (
          <div className="provenance-state provenance-state--error" role="alert">
            <strong>加载溯源图失败</strong>
            <span>{state.error}</span>
          </div>
        ) : state.loading && !state.graph ? (
          <div className="provenance-state">正在构建三层空间…</div>
        ) : graph.nodes.length === 0 && visibility.hiddenSameLayerEdgeCount > 0 ? (
          <div className="provenance-state provenance-state--empty" role="status">
            <strong>暂无跨层溯源关系</strong>
            <span>
              当前数据只有 {visibility.hiddenSameLayerEdgeCount} 条同层关系，已默认隐藏。
            </span>
            <button type="button" onClick={() => setSameLayerRelations(true)}>
              显示同层关系
            </button>
          </div>
        ) : graph.nodes.length === 0 ? (
          <div className="provenance-state">暂无可展示的溯源数据</div>
        ) : showFallback ? (
          <ProvenanceFallbackView
            graph={graph}
            onSelectNode={selectNode}
            onSelectEdge={selectEdge}
            reason={fallbackReason}
          />
        ) : (
          <SpatialLayerCanvas3D
            graph={graph}
            positions={positions}
            selectedNodeId={state.selectedNodeId}
            selectedEdgeIds={selectedEdgeIds}
            onSelectNode={selectNode}
            onSelectEdge={selectEdge}
            onClearSelection={clearSelection}
            initialCameraState={initialCamera}
            onCameraChange={(camera) => {
              const cameraValue = new URLSearchParams(serializeCameraState(camera)).get("camera");
              updateUrl({ camera: cameraValue });
            }}
          />
        )}
        <GraphLegend />
      </section>

      <EvidenceAuditDrawer
        open={Boolean(state.selectedEdgeId)}
        edge={state.edge}
        onClose={() => {
          dispatch({ type: "select_edge", edgeId: null });
          updateUrl({ edge: null });
        }}
        onReview={reviewEdge}
        onReload={loadEdge}
      />
    </main>
  );
}
