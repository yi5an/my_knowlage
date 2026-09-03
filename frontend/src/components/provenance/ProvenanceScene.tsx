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
import { PROVENANCE_PALETTE } from "./provenancePalette";
import { nodeVisual } from "./visualEncoding";

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
      <color attach="background" args={[PROVENANCE_PALETTE.stage.background]} />
      <fog attach="fog" args={[PROVENANCE_PALETTE.stage.background, 45, 100]} />
      <ambientLight intensity={0.75} />
      <directionalLight position={[12, 22, 10]} intensity={1.4} />
      <directionalLight position={[-16, 5, -12]} intensity={0.45} color="#64748b" />
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
          {Array.from(
            props.graph.nodes
              .filter((node) => node.layer === layer)
              .reduce((groups, node) => {
                const color = nodeVisual(node).color;
                const group = groups.get(color);
                if (group) group.push(node);
                else groups.set(color, [node]);
                return groups;
              }, new Map<string, typeof props.graph.nodes>()),
          ).map(([color, nodes]) => (
            <InstancedNodes
              key={`${layer}-${color}`}
              layer={layer}
              nodes={nodes}
              positions={props.positions}
              selectedNodeId={props.selectedNodeId}
              onSelectNode={props.onSelectNode}
              nodeScale={props.scenePolicy?.nodeScale}
              color={color}
            />
          ))}
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
        maxParticles={props.scenePolicy?.maxParticles}
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
