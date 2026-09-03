import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import type { ProvenanceEdge } from "../../types/provenance";
import type { ProvenancePosition } from "./layout";
import { edgeVisual } from "./visualEncoding";

interface FlowParticlesProps {
  edges: ProvenanceEdge[];
  positions: Map<string, ProvenancePosition>;
  selectedEdgeIds: ReadonlySet<string>;
  enabled: boolean;
}

export function FlowParticles({
  edges,
  positions,
  selectedEdgeIds,
  enabled,
}: FlowParticlesProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const particles = useMemo(
    () =>
      edges
        .filter((edge) => selectedEdgeIds.has(edge.id))
        .flatMap((edge) => {
          const source = positions.get(edge.source_id);
          const target = positions.get(edge.target_id);
          if (!source || !target) return [];
          return [{ edge, source, target }];
        }),
    [edges, positions, selectedEdgeIds],
  );

  useFrame(({ clock, invalidate }) => {
    const mesh = meshRef.current;
    if (!enabled || !mesh || particles.length === 0) return;
    const object = new THREE.Object3D();
    const color = new THREE.Color();
    particles.forEach(({ edge, source, target }, index) => {
      const progress = (clock.elapsedTime * 0.28 + index / particles.length) % 1;
      object.position.set(
        THREE.MathUtils.lerp(source.x, target.x, progress),
        THREE.MathUtils.lerp(source.y, target.y, progress),
        THREE.MathUtils.lerp(source.z, target.z, progress),
      );
      object.updateMatrix();
      mesh.setMatrixAt(index, object.matrix);
      mesh.setColorAt(index, color.set(edgeVisual(edge).color));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    invalidate();
  });

  if (!enabled || particles.length === 0) return null;
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, particles.length]}>
      <sphereGeometry args={[0.105, 8, 6]} />
      <meshBasicMaterial vertexColors toneMapped={false} />
    </instancedMesh>
  );
}
