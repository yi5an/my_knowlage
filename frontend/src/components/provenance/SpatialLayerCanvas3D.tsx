import { Canvas, type RootState } from "@react-three/fiber";
import { useCallback, useRef, useState, type KeyboardEvent } from "react";
import * as THREE from "three";

import type { ProvenanceGraphResponse } from "../../types/provenance";
import type { ProvenancePosition } from "./layout";
import { ProvenanceScene } from "./ProvenanceScene";
import type { CameraControllerHandle } from "./CameraController";
import {
  DEFAULT_CAMERA_STATE,
  applyKeyboardCameraAction,
  type ProvenanceCameraState,
} from "./cameraState";
import { scenePolicy } from "./scenePolicy";
import { useMotionPreference } from "./useMotionPreference";
import { updateProvenanceDebug } from "./debug";

const PROVENANCE_RAYCASTER_PARAMS: THREE.RaycasterParameters = {
  ...new THREE.Raycaster().params,
  Line: { threshold: 0.12 },
};

interface SpatialLayerCanvas3DProps {
  graph: ProvenanceGraphResponse;
  positions: Map<string, ProvenancePosition>;
  selectedNodeId: string | null;
  selectedEdgeIds: ReadonlySet<string>;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
  initialCameraState?: ProvenanceCameraState;
  onCameraChange?: (state: ProvenanceCameraState) => void;
  onClearSelection?: () => void;
  motionEnabled?: boolean;
}

export function SpatialLayerCanvas3D(props: SpatialLayerCanvas3DProps) {
  const [ready, setReady] = useState(false);
  const [shiftPan, setShiftPan] = useState(false);
  const cameraControllerRef = useRef<CameraControllerHandle>(null);
  const reducedMotion = useMotionPreference();
  const policy = scenePolicy({
    cameraDistance: 40,
    nodeCount: props.graph.nodes.length,
    dpr: typeof window === "undefined" ? 1 : window.devicePixelRatio,
    selectedPathEdges: props.selectedEdgeIds.size,
    reducedMotion,
  });
  const markReadyAfterRender = useCallback((state: RootState) => {
    state.invalidate();
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (state.gl.info.render.frame >= 1) {
          setReady(true);
          updateProvenanceDebug({
            frame: state.gl.info.render.frame,
            cameraPosition: state.camera.position.toArray() as [number, number, number],
            cameraQuaternion: state.camera.quaternion.toArray() as [number, number, number, number],
            geometries: state.gl.info.memory.geometries,
            textures: state.gl.info.memory.textures,
            mounted: true,
          });
        }
      });
    });
  }, []);

  const handleKeyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Shift") {
      setShiftPan(event.type === "keydown");
      return;
    }
    if (event.type !== "keydown") return;
    const current = cameraControllerRef.current?.getState() ?? DEFAULT_CAMERA_STATE;
    const action = applyKeyboardCameraAction(current, event.key);
    if (!action.handled) return;
    event.preventDefault();
    cameraControllerRef.current?.applyState(action.state);
    props.onCameraChange?.(action.state);
    if (action.clearSelection) props.onClearSelection?.();
  };

  return (
    <div
      className="provenance-canvas"
      data-provenance-canvas
      data-renderer="webgl"
      data-webgl-ready={ready ? "true" : "false"}
      role="application"
      aria-label="事件结论三层溯源 3D 画布"
      tabIndex={0}
      onContextMenu={(event) => event.preventDefault()}
      onKeyDown={handleKeyboard}
      onKeyUp={handleKeyboard}
      onBlur={() => setShiftPan(false)}
    >
      <Canvas
        frameloop="demand"
        dpr={[1, policy.dpr]}
        camera={{ fov: 48, near: 0.1, far: 600, position: [22, 18, 28] }}
        gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
        raycaster={{ params: PROVENANCE_RAYCASTER_PARAMS }}
        onCreated={markReadyAfterRender}
        onPointerMissed={(event) => {
          if (event.detail !== 2) return;
          cameraControllerRef.current?.reset();
          props.onClearSelection?.();
        }}
      >
        <ProvenanceScene
          {...props}
          cameraControllerRef={cameraControllerRef}
          initialCameraState={props.initialCameraState}
          shiftPan={shiftPan}
          motionEnabled={(props.motionEnabled ?? true) && policy.cameraTween}
          onCameraChange={props.onCameraChange}
          scenePolicy={policy}
          reducedMotion={reducedMotion}
        />
      </Canvas>
      <span className="provenance-sr-only" aria-live="polite">
        {props.selectedNodeId
          ? `已选择节点 ${props.selectedNodeId}`
          : props.selectedEdgeIds.size
            ? `已选择 ${props.selectedEdgeIds.size} 条关系`
            : "未选择溯源对象"}
      </span>
    </div>
  );
}
