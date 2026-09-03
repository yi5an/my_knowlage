import { Html } from "@react-three/drei";

import type { ProvenanceGraphResponse, TraceLayer } from "../../types/provenance";
import type { CameraControllerHandle } from "./CameraController";
import { CameraController } from "./CameraController";
import type { ProvenanceCameraState } from "./cameraState";
import type { ProvenancePosition } from "./layout";
import { LAYER_Y } from "./layout";
import { InstancedNodes } from "./InstancedNodes";
import { LabelLayer } from "./LabelLayer";
import { LayerPlane } from "./LayerPlane";
import { TraceEdges } from "./TraceEdges";
import { FlowParticles } from "./FlowParticles";
import type { ProvenanceScenePolicy } from "./scenePolicy";
import { DebugSceneProbe } from "./DebugSceneProbe";

const LAYERS: TraceLayer[] = ["conclusion", "event", "evidence"];
const LABELS: Record<TraceLayer, string> = {
  conclusion: "结论层",
  event: "事件 / 事实层",
  evidence: "证据层",
};

interface ProvenanceSceneProps {
  graph: ProvenanceGraphResponse;
  positions: Map<string, ProvenancePosition>;
  selectedNodeId: string | null;
  selectedEdgeIds: ReadonlySet<string>;
  onSelectNode: (nodeId: string) => void;
  onSelectEdge: (edgeId: string) => void;
  cameraControllerRef?: React.Ref<CameraControllerHandle>;
  initialCameraState?: ProvenanceCameraState;
  shiftPan?: boolean;
  motionEnabled?: boolean;
  onCameraChange?: (state: ProvenanceCameraState) => void;
  scenePolicy?: ProvenanceScenePolicy;
  reducedMotion?: boolean;
}

export function ProvenanceScene(props: ProvenanceSceneProps) {
  return (
    <>
      <color attach="background" args={["#07111f"]} />
      <fog attach="fog" args={["#07111f", 45, 100]} />
      <ambientLight intensity={0.75} />
      <directionalLight position={[12, 22, 10]} intensity={1.4} />
      <directionalLight position={[-16, 5, -12]} intensity={0.45} color="#7dd3fc" />
      <CameraController
        ref={props.cameraControllerRef}
        initialState={props.initialCameraState}
        focusPosition={
          props.selectedNodeId ? props.positions.get(props.selectedNodeId) : undefined
        }
        shiftPan={props.shiftPan ?? false}
        motionEnabled={props.motionEnabled}
        onCameraChange={props.onCameraChange}
      />
      <DebugSceneProbe
        graph={props.graph}
        positions={props.positions}
        selectedNodeId={props.selectedNodeId}
        selectedEdgeCount={props.selectedEdgeIds.size}
        reducedMotion={props.reducedMotion ?? false}
      />
      {LAYERS.map((layer) => (
        <group key={layer}>
          <LayerPlane layer={layer} />
          <Html position={[-15, LAYER_Y[layer] + 0.3, -13]} style={{ pointerEvents: "none" }}>
            <span className={`provenance-layer-label provenance-layer-label--${layer}`}>
              {LABELS[layer]}
            </span>
          </Html>
          <InstancedNodes
            layer={layer}
            nodes={props.graph.nodes}
            positions={props.positions}
            selectedNodeId={props.selectedNodeId}
            onSelectNode={props.onSelectNode}
          />
        </group>
      ))}
      <TraceEdges
        edges={props.graph.edges}
        positions={props.positions}
        selectedEdgeIds={props.selectedEdgeIds}
        onSelectEdge={props.onSelectEdge}
      />
      <FlowParticles
        edges={props.graph.edges}
        positions={props.positions}
        selectedEdgeIds={props.selectedEdgeIds}
        enabled={props.scenePolicy?.particles ?? false}
      />
      <LabelLayer
        nodes={props.graph.nodes}
        positions={props.positions}
        selectedNodeId={props.selectedNodeId}
        maxLabels={props.scenePolicy?.maxLabels}
      />
    </>
  );
}
