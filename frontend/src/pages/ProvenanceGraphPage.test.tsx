import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { provenanceApi } from "../services/provenanceApi";
import type { ProvenanceGraphResponse } from "../types/provenance";
import { ProvenanceGraphPage } from "./ProvenanceGraphPage";

vi.mock("../services/provenanceApi", () => ({
  provenanceApi: {
    overview: vi.fn(),
    traceNode: vi.fn(),
    edge: vi.fn(),
    reviewEdge: vi.fn(),
    rebuild: vi.fn(),
    job: vi.fn(),
  },
}));
vi.mock("../components/provenance/webglSupport", () => ({ supportsWebGL: () => true }));
vi.mock("../components/provenance/SpatialLayerCanvas3D", () => ({
  SpatialLayerCanvas3D: ({ onSelectNode, onSelectEdge }: { onSelectNode: (id: string) => void; onSelectEdge: (id: string) => void }) => (
    <div data-testid="mock-webgl">
      <button type="button" onClick={() => onSelectNode("event-1")}>选择事件节点</button>
      <button type="button" onClick={() => onSelectEdge("edge-1")}>选择关系</button>
    </div>
  ),
}));

const graph: ProvenanceGraphResponse = {
  nodes: [
    { id: "event-1", layer: "event", node_type: "event", backing_type: "knowledge_event", backing_id: "event-1", label: "政策收紧", occurred_at: null, confidence: 0.8, review_status: "pending_review", validation_status: "unverified", properties: {} },
  ],
  edges: [],
  clusters: [],
  graph_version: "v1",
  degraded: false,
  degraded_reason: null,
  total_nodes: 1,
  returned_nodes: 1,
  has_more: false,
  next_cursor: null,
};

const api = vi.mocked(provenanceApi);

function renderPage(path = "/provenance") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/provenance" element={<ProvenanceGraphPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProvenanceGraphPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.overview.mockResolvedValue(graph);
    api.traceNode.mockResolvedValue(graph);
    api.edge.mockResolvedValue({
      id: "edge-1", source_id: "a", target_id: "event-1", relation_type: "supports", rationale: "支持", confidence: 0.8, review_status: "pending_review", validation_status: "supported", origin_type: "ai", evidence_anchor_ids: [], version_no: 1, model_metadata: {}, review_history: [], evidence: [],
    });
    api.reviewEdge.mockResolvedValue({
      edge: { id: "edge-1", source_id: "a", target_id: "event-1", relation_type: "supports", rationale: "支持", confidence: 0.8, review_status: "confirmed", validation_status: "supported", origin_type: "ai", evidence_anchor_ids: [], version_no: 2, model_metadata: {} },
      previous_review_status: "pending_review",
      reviewed_at: "2026-09-03T00:00:00Z",
    });
  });

  it("loads the overview and renders the WebGL scene", async () => {
    renderPage();
    expect(screen.getByRole("heading", { name: "事件结论溯源" })).toBeInTheDocument();
    await waitFor(() => expect(api.overview).toHaveBeenCalled());
    expect(await screen.findByTestId("mock-webgl")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "使用兼容视图" }));
    expect(screen.getByText("兼容视图")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "政策收紧" }));
    await waitFor(() => expect(api.traceNode).toHaveBeenCalled());
  });

  it("restores URL mode, filters, and selection then fetches the focused path", async () => {
    renderPage("/provenance?mode=up&layer=event&status=pending_review&node=event-1");
    await waitFor(() =>
      expect(api.traceNode).toHaveBeenCalledWith("event-1", "up", "ws_default", 500, expect.any(AbortSignal)),
    );
    expect(screen.getByRole("button", { name: "向上追结论" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("层级筛选")).toHaveValue("event");
  });

  it("fetches both path directions when mode changes and a node is selected", async () => {
    renderPage();
    await screen.findByTestId("mock-webgl");
    fireEvent.click(screen.getByRole("button", { name: "选择事件节点" }));
    await waitFor(() => expect(api.traceNode).toHaveBeenCalledWith("event-1", "down", "ws_default", 500, expect.any(AbortSignal)));
    const downSignal = api.traceNode.mock.calls.at(-1)?.[4];
    fireEvent.click(screen.getByRole("button", { name: "向上追结论" }));
    await waitFor(() => expect(api.traceNode).toHaveBeenCalledWith("event-1", "up", "ws_default", 500, expect.any(AbortSignal)));
    expect(downSignal?.aborted).toBe(true);
  });

  it("surfaces degraded and partial-result warnings", async () => {
    api.overview.mockResolvedValue({
      ...graph,
      degraded: true,
      degraded_reason: "graph_store_unavailable",
      has_more: true,
      total_nodes: 900,
      returned_nodes: 500,
    });
    renderPage();
    expect(await screen.findByText(/图存储不可用/)).toBeInTheDocument();
    expect(screen.getByText(/仅显示 500\/900/)).toBeInTheDocument();
  });

  it("shows empty and error states", async () => {
    api.overview.mockResolvedValueOnce({ ...graph, nodes: [], total_nodes: 0, returned_nodes: 0 });
    const view = renderPage();
    expect(await screen.findByText("暂无可展示的溯源数据")).toBeInTheDocument();
    view.unmount();

    api.overview.mockRejectedValueOnce(new Error("offline"));
    renderPage();
    expect(await screen.findByText(/加载溯源图失败/)).toBeInTheDocument();
  });

  it("opens edge audit without unmounting the canvas", async () => {
    renderPage();
    await screen.findByTestId("mock-webgl");
    fireEvent.click(screen.getByRole("button", { name: "选择关系" }));
    expect(await screen.findByRole("complementary", { name: "关系审计" })).toBeInTheDocument();
    expect(screen.getByTestId("mock-webgl")).toBeInTheDocument();
  });
});
