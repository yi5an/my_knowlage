import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ProvenanceGraphResponse } from "../../types/provenance";
import { GraphLegend } from "./GraphLegend";
import { ProvenanceFallbackView } from "./ProvenanceFallbackView";
import { TraceModeToolbar } from "./TraceModeToolbar";

const graph: ProvenanceGraphResponse = {
  nodes: [
    { id: "c", layer: "conclusion", node_type: "research", backing_type: "conclusion", backing_id: "c", label: "结论 C", occurred_at: null, confidence: 0.8, review_status: "confirmed", validation_status: "supported", properties: {} },
    { id: "e", layer: "event", node_type: "event", backing_type: "event", backing_id: "e", label: "事件 E", occurred_at: null, confidence: 0.7, review_status: "pending_review", validation_status: "unverified", properties: {} },
    { id: "a", layer: "evidence", node_type: "text", backing_type: "evidence", backing_id: "a", label: "证据 A", occurred_at: null, confidence: 1, review_status: null, validation_status: "valid", properties: {} },
  ],
  edges: [],
  clusters: [],
  graph_version: "v1",
  degraded: false,
  degraded_reason: null,
  total_nodes: 3,
  returned_nodes: 3,
  has_more: false,
  next_cursor: null,
};

describe("provenance fallback and controls", () => {
  it("shows a labeled read-only three-layer fallback and supports selection", () => {
    const onSelectNode = vi.fn();
    render(<ProvenanceFallbackView graph={graph} onSelectNode={onSelectNode} />);
    expect(screen.getByText(/WebGL 不可用/)).toBeInTheDocument();
    expect(screen.getByText("结论层")).toBeInTheDocument();
    expect(screen.getByText("事件 / 事实层")).toBeInTheDocument();
    expect(screen.getByText("证据层")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "结论 C" }));
    expect(onSelectNode).toHaveBeenCalledWith("c");
  });

  it("does not claim WebGL failed when a narrow screen chooses the list view", () => {
    render(
      <ProvenanceFallbackView
        graph={graph}
        onSelectNode={vi.fn()}
        reason="narrow-screen"
      />,
    );
    expect(screen.getByText("小屏兼容视图")).toBeInTheDocument();
    expect(screen.queryByText("WebGL 不可用")).not.toBeInTheDocument();
  });

  it("offers both trace modes and a complete semantic legend", () => {
    const onChange = vi.fn();
    render(
      <>
        <TraceModeToolbar mode="down" onChange={onChange} />
        <GraphLegend />
      </>,
    );
    fireEvent.click(screen.getByRole("button", { name: "向上追结论" }));
    expect(onChange).toHaveBeenCalledWith("up");
    expect(screen.getByText("已确认")).toBeInTheDocument();
    expect(screen.getByText("待审核 / AI 推断")).toBeInTheDocument();
    expect(screen.getByText("反驳 / 冲突")).toBeInTheDocument();
    expect(screen.getByText("限定条件")).toBeInTheDocument();
    expect(screen.getByText("证据过期")).toBeInTheDocument();
  });
});
