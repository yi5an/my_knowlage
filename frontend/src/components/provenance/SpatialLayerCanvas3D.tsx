import { Canvas, type RootState } from "@react-three/fiber";
import { useCallback, useState } from "react";

import type { ProvenanceGraphResponse } from "../../types/provenance";
import type { ProvenancePosition } from "./layout";
import { ProvenanceScene } from "./ProvenanceScene";

interface SpatialLayerCanvas3DProps {
  graph: ProvenanceGraphResponse;
  positions: Map<string, ProvenancePosition>;
  selectedNodeId: string | null;
  selectedEdgeIds: ReadonlySet<string>;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
}

export function SpatialLayerCanvas3D(props: SpatialLayerCanvas3DProps) {
  const [ready, setReady] = useState(false);
  const markReadyAfterRender = useCallback((state: RootState) => {
    state.invalidate();
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (state.gl.info.render.frame >= 1) setReady(true);
      });
    });
  }, []);

  return (
    <div
      className="provenance-canvas"
      data-provenance-canvas
      data-renderer="webgl"
      data-webgl-ready={ready ? "true" : "false"}
    >
      <Canvas
        frameloop="demand"
        dpr={[1, 1.75]}
        camera={{ fov: 48, near: 0.1, far: 600, position: [22, 18, 28] }}
        gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
        onCreated={markReadyAfterRender}
      >
        <ProvenanceScene {...props} />
      </Canvas>
    </div>
  );
}
