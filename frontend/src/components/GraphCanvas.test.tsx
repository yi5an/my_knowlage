import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";

import { GraphCanvas } from "./GraphCanvas";

/**
 * G6 v5 renders to canvas/webgl, which jsdom doesn't support, so we can't
 * assert on drawn pixels here. We instead guard the contract that matters for
 * integration: the component mounts a container div, doesn't throw, and
 * accepts the layout/data props without crashing. Visual verification happens
 * in the browser via the dev server.
 */
describe("GraphCanvas", () => {
  it("mounts a container div without crashing", () => {
    const nodes = [
      { id: "n1", label: "英伟达", node_type: "entity" },
      { id: "n2", label: "HBM", node_type: "technology" },
    ];
    const edges = [
      { id: "e1", source_id: "n1", target_id: "n2", relation_type: "develops" },
    ];

    const { container } = render(
      <GraphCanvas nodes={nodes} edges={edges} layout="force" />,
    );

    // The container div that G6 binds to must exist.
    expect(container.querySelector("div")).not.toBeNull();
  });

  it("accepts all layout kinds without throwing", () => {
    const nodes = [{ id: "n1", label: "x", node_type: "entity" }];
    const edges: never[] = [];
    for (const layout of ["force", "radial", "grid"] as const) {
      expect(() =>
        render(<GraphCanvas nodes={nodes} edges={edges} layout={layout} />),
      ).not.toThrow();
    }
  });
});
