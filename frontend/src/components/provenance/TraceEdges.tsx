import { Line } from "@react-three/drei";
import { type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import * as THREE from "three";

import type { ProvenanceEdge } from "../../types/provenance";
import type { ProvenancePosition } from "./layout";
import { shouldBatchSelectedEdges } from "./scenePolicy";
import { edgeVisual } from "./visualEncoding";

interface TraceEdgesProps {
  edges: ProvenanceEdge[];
  positions: Map<string, ProvenancePosition>;
  selectedEdgeIds: ReadonlySet<string>;
  onSelectEdge: (edgeId: string) => void;
}

interface EdgeBatch {
  key: string;
  edgeIds: string[];
  geometry: THREE.BufferGeometry;
  color: string;
  dashed: boolean;
  opacity: number;
}

function trimEdge(
  source: ProvenancePosition,
  target: ProvenancePosition,
): [ProvenancePosition, ProvenancePosition] {
  const distance = Math.hypot(
    target.x - source.x,
    target.y - source.y,
    target.z - source.z,
  );
  const ratio = Math.min(0.22, 0.95 / Math.max(distance, 0.001));
  const lerp = (start: number, end: number, amount: number) =>
    start + (end - start) * amount;
  return [
    {
      x: lerp(source.x, target.x, ratio),
      y: lerp(source.y, target.y, ratio),
      z: lerp(source.z, target.z, ratio),
    },
    {
      x: lerp(source.x, target.x, 1 - ratio),
      y: lerp(source.y, target.y, 1 - ratio),
      z: lerp(source.z, target.z, 1 - ratio),
    },
  ];
}

function hasNodeHit(event: ThreeEvent<MouseEvent>): boolean {
  return event.intersections.some(
    (intersection) => intersection.object instanceof THREE.InstancedMesh,
  );
}

export function TraceEdges({
  edges,
  positions,
  selectedEdgeIds,
  onSelectEdge,
}: TraceEdgesProps) {
  const { batches, selected } = useMemo(() => {
    const batchMap = new Map<string, EdgeBatch>();
    const selectedItems: ProvenanceEdge[] = [];
    const batchSelected = shouldBatchSelectedEdges(selectedEdgeIds.size);
    for (const edge of edges) {
      const source = positions.get(edge.source_id);
      const target = positions.get(edge.target_id);
      if (!source || !target) continue;
      const [lineSource, lineTarget] = trimEdge(source, target);
      if (selectedEdgeIds.has(edge.id) && !batchSelected) {
        selectedItems.push(edge);
        continue;
      }
      const visual = edgeVisual(edge, selectedEdgeIds);
      const key = `${visual.color}|${visual.dashed}|${visual.opacity}`;
      let batch = batchMap.get(key);
      if (!batch) {
        batch = {
          key,
          edgeIds: [],
          geometry: new THREE.BufferGeometry(),
          color: visual.color,
          dashed: visual.dashed,
          opacity: visual.opacity,
        };
        batchMap.set(key, batch);
      }
      batch.edgeIds.push(edge.id);
      const values = Array.from(
        batch.geometry.getAttribute("position")?.array ?? [],
      ) as number[];
      values.push(
        lineSource.x,
        lineSource.y,
        lineSource.z,
        lineTarget.x,
        lineTarget.y,
        lineTarget.z,
      );
      batch.geometry.setAttribute("position", new THREE.Float32BufferAttribute(values, 3));
      if (visual.dashed) {
        const distances = Array.from(
          batch.geometry.getAttribute("lineDistance")?.array ?? [],
        ) as number[];
        distances.push(
          0,
          Math.hypot(
            lineTarget.x - lineSource.x,
            lineTarget.y - lineSource.y,
            lineTarget.z - lineSource.z,
          ),
        );
        batch.geometry.setAttribute(
          "lineDistance",
          new THREE.Float32BufferAttribute(distances, 1),
        );
      }
    }
    return { batches: [...batchMap.values()], selected: selectedItems };
  }, [edges, positions, selectedEdgeIds]);

  useEffect(
    () => () => {
      batches.forEach((batch) => batch.geometry.dispose());
    },
    [batches],
  );

  return (
    <>
      {batches.map((batch) => (
        <lineSegments
          key={batch.key}
          geometry={batch.geometry}
          onClick={(event: ThreeEvent<MouseEvent>) => {
            if (hasNodeHit(event)) return;
            event.stopPropagation();
            const segmentIndex = Math.floor((event.index ?? 0) / 2);
            const edgeId = batch.edgeIds[segmentIndex];
            if (edgeId) onSelectEdge(edgeId);
          }}
        >
          {batch.dashed ? (
            <lineDashedMaterial
              color={batch.color}
              transparent
              opacity={batch.opacity}
              dashSize={0.32}
              gapSize={0.2}
            />
          ) : (
            <lineBasicMaterial color={batch.color} transparent opacity={batch.opacity} />
          )}
        </lineSegments>
      ))}
      {selected.map((edge) => {
        const source = positions.get(edge.source_id)!;
        const target = positions.get(edge.target_id)!;
        const [lineSource, lineTarget] = trimEdge(source, target);
        const visual = edgeVisual(edge, selectedEdgeIds);
        return (
          <Line
            key={edge.id}
            points={[
              [lineSource.x, lineSource.y, lineSource.z],
              [lineTarget.x, lineTarget.y, lineTarget.z],
            ]}
            color={visual.color}
            lineWidth={2.3}
            dashed={visual.dashed}
            dashSize={0.32}
            gapSize={0.2}
            transparent
            opacity={1}
            onClick={(event) => {
              if (hasNodeHit(event)) return;
              event.stopPropagation();
              onSelectEdge(edge.id);
            }}
          />
        );
      })}
    </>
  );
}
