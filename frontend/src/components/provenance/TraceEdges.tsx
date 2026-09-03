import { Line } from "@react-three/drei";
import { type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import * as THREE from "three";

import type { ProvenanceEdge } from "../../types/provenance";
import type { ProvenancePosition } from "./layout";
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

export function TraceEdges({
  edges,
  positions,
  selectedEdgeIds,
  onSelectEdge,
}: TraceEdgesProps) {
  const { batches, selected } = useMemo(() => {
    const batchMap = new Map<string, EdgeBatch>();
    const selectedItems: ProvenanceEdge[] = [];
    for (const edge of edges) {
      const source = positions.get(edge.source_id);
      const target = positions.get(edge.target_id);
      if (!source || !target) continue;
      if (selectedEdgeIds.has(edge.id)) {
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
      values.push(source.x, source.y, source.z, target.x, target.y, target.z);
      batch.geometry.setAttribute("position", new THREE.Float32BufferAttribute(values, 3));
      if (visual.dashed) {
        const distances = Array.from(
          batch.geometry.getAttribute("lineDistance")?.array ?? [],
        ) as number[];
        distances.push(
          0,
          Math.hypot(target.x - source.x, target.y - source.y, target.z - source.z),
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
        const visual = edgeVisual(edge, selectedEdgeIds);
        return (
          <Line
            key={edge.id}
            points={[
              [source.x, source.y, source.z],
              [target.x, target.y, target.z],
            ]}
            color={visual.color}
            lineWidth={2.3}
            dashed={visual.dashed}
            dashSize={0.32}
            gapSize={0.2}
            transparent
            opacity={1}
            onClick={(event) => {
              event.stopPropagation();
              onSelectEdge(edge.id);
            }}
          />
        );
      })}
    </>
  );
}
