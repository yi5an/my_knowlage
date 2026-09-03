import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";

import type { ProvenanceGraphResponse } from "../../types/provenance";
import { provenanceDebugEnabled, updateProvenanceDebug } from "./debug";
import type { ProvenancePosition } from "./layout";

interface DebugSceneProbeProps {
  graph: ProvenanceGraphResponse;
  positions: Map<string, ProvenancePosition>;
  selectedNodeId: string | null;
  selectedEdgeCount: number;
  reducedMotion: boolean;
}

export function DebugSceneProbe(props: DebugSceneProbeProps) {
  const { camera, gl } = useThree();
  const renderedFrames = useRef(0);

  useEffect(() => {
    updateProvenanceDebug({ mounted: true });
    return () => {
      updateProvenanceDebug({
        mounted: false,
        geometries: 0,
        textures: 0,
        selectedNodeId: null,
        selectedEdgeCount: 0,
      });
    };
  }, []);

  useFrame(() => {
    if (!provenanceDebugEnabled()) return;
    renderedFrames.current += 1;
    const rect = gl.domElement.getBoundingClientRect();
    const project = (position: ProvenancePosition): [number, number] => {
      const projected = new THREE.Vector3(position.x, position.y, position.z).project(camera);
      return [
        rect.left + ((projected.x + 1) / 2) * rect.width,
        rect.top + ((1 - projected.y) / 2) * rect.height,
      ];
    };
    const nodeScreenPositions: Record<string, [number, number]> = {};
    props.graph.nodes.forEach((node) => {
      const position = props.positions.get(node.id);
      if (position) nodeScreenPositions[node.id] = project(position);
    });
    const edgeScreenPositions: Record<string, [number, number]> = {};
    props.graph.edges.forEach((edge) => {
      const source = props.positions.get(edge.source_id);
      const target = props.positions.get(edge.target_id);
      if (!source || !target) return;
      edgeScreenPositions[edge.id] = project({
        x: (source.x + target.x) / 2,
        y: (source.y + target.y) / 2,
        z: (source.z + target.z) / 2,
      });
    });
    updateProvenanceDebug({
      frame: renderedFrames.current,
      cameraPosition: camera.position.toArray() as [number, number, number],
      cameraQuaternion: camera.quaternion.toArray() as [number, number, number, number],
      selectedNodeId: props.selectedNodeId,
      selectedEdgeCount: props.selectedEdgeCount,
      geometries: gl.info.memory.geometries,
      textures: gl.info.memory.textures,
      mounted: true,
      reducedMotion: props.reducedMotion,
      nodeScreenPositions,
      edgeScreenPositions,
    });
  });

  return null;
}
