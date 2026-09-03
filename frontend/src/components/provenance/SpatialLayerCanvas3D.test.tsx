import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ProvenanceGraphResponse } from "../../types/provenance";
import { SpatialLayerCanvas3D } from "./SpatialLayerCanvas3D";

vi.mock("@react-three/fiber", () => ({
  Canvas: ({ camera }: { camera: Record<string, unknown>; children: ReactNode }) => (
    <div data-testid="r3f-canvas" data-camera={JSON.stringify(camera)} />
  ),
}));

const graph: ProvenanceGraphResponse = {
  nodes: [],
  edges: [],
  clusters: [],
  graph_version: "v1",
  degraded: false,
  degraded_reason: null,
  total_nodes: 0,
  returned_nodes: 0,
  has_more: false,
  next_cursor: null,
};

describe("SpatialLayerCanvas3D", () => {
  it("constructs an R3F perspective scene instead of a CSS perspective", () => {
    const { container } = render(
      <SpatialLayerCanvas3D
        graph={graph}
        positions={new Map()}
        selectedNodeId={null}
        selectedEdgeIds={new Set()}
        onSelectNode={vi.fn()}
        onSelectEdge={vi.fn()}
      />,
    );

    expect(screen.getByTestId("r3f-canvas").dataset.camera).toContain('"fov":48');
    const wrapper = container.querySelector('[data-renderer="webgl"]');
    expect(wrapper).toBeTruthy();
    expect((wrapper as HTMLElement).style.perspective).toBe("");
  });
});
