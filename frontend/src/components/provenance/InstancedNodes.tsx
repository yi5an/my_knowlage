import { type ThreeEvent } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import type { ProvenanceNode, TraceLayer } from "../../types/provenance";
import type { ProvenancePosition } from "./layout";
import { buildInstanceNodeIds, nodeVisual } from "./visualEncoding";

interface InstancedNodesProps {
  layer: TraceLayer;
  nodes: ProvenanceNode[];
  positions: Map<string, ProvenancePosition>;
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
}

export function InstancedNodes({
  layer,
  nodes,
  positions,
  selectedNodeId,
  onSelectNode,
}: InstancedNodesProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const instanceNodeIds = useMemo(() => buildInstanceNodeIds(nodes, layer), [layer, nodes]);
  const nodesById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;
    const object = new THREE.Object3D();
    const color = new THREE.Color();
    instanceNodeIds.forEach((nodeId, index) => {
      const node = nodesById.get(nodeId);
      const position = positions.get(nodeId);
      if (!node || !position) return;
      const visual = nodeVisual(node);
      object.position.set(position.x, position.y, position.z);
      const selectionScale = selectedNodeId === nodeId ? 1.45 : 1;
      object.scale.setScalar(visual.scale * selectionScale);
      object.updateMatrix();
      mesh.setMatrixAt(index, object.matrix);
      mesh.setColorAt(index, color.set(visual.color));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [instanceNodeIds, nodesById, positions, selectedNodeId]);

  return (
    <instancedMesh
      ref={meshRef}
      args={[undefined, undefined, instanceNodeIds.length]}
      onClick={(event: ThreeEvent<MouseEvent>) => {
        event.stopPropagation();
        const nodeId =
          event.instanceId === undefined ? undefined : instanceNodeIds[event.instanceId];
        if (nodeId) onSelectNode(nodeId);
      }}
    >
      <sphereGeometry args={[0.42, 16, 12]} />
      <meshStandardMaterial vertexColors transparent roughness={0.32} metalness={0.18} />
    </instancedMesh>
  );
}
