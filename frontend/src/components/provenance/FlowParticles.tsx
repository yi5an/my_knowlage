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
  maxParticles?: number;
}

export function FlowParticles({
  edges,
  positions,
  selectedEdgeIds,
  enabled,
  maxParticles = 120,
}: FlowParticlesProps) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const particles = useMemo(
    () =>
      edges
        .filter((edge) => selectedEdgeIds.has(edge.id))
        .filter((_, index, selected) =>
          selected.length <= maxParticles || index % Math.ceil(selected.length / maxParticles) === 0
        )
        .slice(0, maxParticles)
        .flatMap((edge) => {
          const source = positions.get(edge.source_id);
          const target = positions.get(edge.target_id);
          if (!source || !target) return [];
          return [{ edge, source, target }];
        }),
    [edges, maxParticles, positions, selectedEdgeIds],
  );
  const particleColors = useMemo(() => {
    const values = new Float32Array(particles.length * 3);
    const color = new THREE.Color();
    particles.forEach(({ edge }, index) => {
      color.set(edgeVisual(edge).color).toArray(values, index * 3);
    });
    return values;
  }, [particles]);

  useFrame(({ clock, invalidate }) => {
    const mesh = meshRef.current;
    if (!enabled || !mesh || particles.length === 0) return;
    const object = new THREE.Object3D();
    particles.forEach(({ source, target }, index) => {
      const progress = (clock.elapsedTime * 0.28 + index / particles.length) % 1;
      object.position.set(
        THREE.MathUtils.lerp(source.x, target.x, progress),
        THREE.MathUtils.lerp(source.y, target.y, progress),
        THREE.MathUtils.lerp(source.z, target.z, progress),
      );
      object.updateMatrix();
      mesh.setMatrixAt(index, object.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
    invalidate();
  });

  if (!enabled || particles.length === 0) return null;
  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, particles.length]}>
      <instancedBufferAttribute attach="instanceColor" args={[particleColors, 3]} />
      <sphereGeometry args={[0.105, 8, 6]} />
      <meshBasicMaterial vertexColors toneMapped={false} />
    </instancedMesh>
  );
}
