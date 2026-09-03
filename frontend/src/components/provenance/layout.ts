import type { ProvenanceGraphResponse, ProvenanceNode, TraceLayer } from "../../types/provenance";

export interface ProvenancePosition {
  x: number;
  y: number;
  z: number;
}

export const LAYER_Y: Record<TraceLayer, number> = {
  conclusion: 9,
  event: 0,
  evidence: -9,
};

const LAYERS: TraceLayer[] = ["conclusion", "event", "evidence"];
const MIN_DISTANCE = 0.8;

export function hashString(value: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function seededRandom(seed: number): () => number {
  let value = seed >>> 0;
  return () => {
    value += 0x6d2b79f5;
    let next = value;
    next = Math.imul(next ^ (next >>> 15), next | 1);
    next ^= next + Math.imul(next ^ (next >>> 7), next | 61);
    return ((next ^ (next >>> 14)) >>> 0) / 4294967296;
  };
}

function clusterKey(graph: ProvenanceGraphResponse, node: ProvenanceNode): string {
  const cluster = [...graph.clusters]
    .sort((left, right) => left.id.localeCompare(right.id))
    .find((candidate) => candidate.node_ids.includes(node.id));
  return cluster?.id ?? `${node.layer}:${node.node_type}`;
}

export function computeProvenanceLayout(
  graph: ProvenanceGraphResponse,
  serializedFilters: string,
): Map<string, ProvenancePosition> {
  const result = new Map<string, ProvenancePosition>();
  const baseSeed = `${graph.graph_version}|${serializedFilters}`;

  for (const layer of LAYERS) {
    const layerNodes = graph.nodes
      .filter((node) => node.layer === layer)
      .sort((left, right) => left.id.localeCompare(right.id));
    const groups = new Map<string, ProvenanceNode[]>();
    for (const node of layerNodes) {
      const key = clusterKey(graph, node);
      groups.set(key, [...(groups.get(key) ?? []), node]);
    }

    const orderedGroups = [...groups.entries()].sort(([left], [right]) =>
      left.localeCompare(right),
    );
    const clusterRadius = Math.max(3.5, orderedGroups.length * 2.2);
    orderedGroups.forEach(([key, members], groupIndex) => {
      const clusterRandom = seededRandom(hashString(`${baseSeed}|${layer}|${key}`));
      const clusterAngle =
        (Math.PI * 2 * groupIndex) / Math.max(orderedGroups.length, 1) +
        (clusterRandom() - 0.5) * 0.5;
      const centerX = Math.cos(clusterAngle) * (orderedGroups.length === 1 ? 0 : clusterRadius);
      const centerZ = Math.sin(clusterAngle) * (orderedGroups.length === 1 ? 0 : clusterRadius);
      const memberRadius = Math.max(1.2, Math.sqrt(members.length) * 1.1);

      members.forEach((node, memberIndex) => {
        const random = seededRandom(hashString(`${baseSeed}|${node.id}`));
        const angle =
          (Math.PI * 2 * memberIndex) / Math.max(members.length, 1) + random() * 0.75;
        const radius = memberRadius * (0.72 + random() * 0.28);
        result.set(node.id, {
          x: centerX + Math.cos(angle) * radius,
          y: LAYER_Y[layer],
          z: centerZ + Math.sin(angle) * radius,
        });
      });
    });

    relaxLayer(layerNodes, result, baseSeed);
  }
  return result;
}

function relaxLayer(
  nodes: ProvenanceNode[],
  positions: Map<string, ProvenancePosition>,
  seed: string,
): void {
  for (let iteration = 0; iteration < 6; iteration += 1) {
    for (let leftIndex = 0; leftIndex < nodes.length; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < nodes.length; rightIndex += 1) {
        const left = positions.get(nodes[leftIndex].id)!;
        const right = positions.get(nodes[rightIndex].id)!;
        let dx = right.x - left.x;
        let dz = right.z - left.z;
        let distance = Math.hypot(dx, dz);
        if (distance >= MIN_DISTANCE) continue;
        if (distance < 0.0001) {
          const angle =
            (hashString(`${seed}|${nodes[leftIndex].id}|${nodes[rightIndex].id}`) /
              0xffffffff) *
            Math.PI *
            2;
          dx = Math.cos(angle);
          dz = Math.sin(angle);
          distance = 1;
        }
        const push = (MIN_DISTANCE - distance) / 2;
        const unitX = dx / distance;
        const unitZ = dz / distance;
        left.x -= unitX * push;
        left.z -= unitZ * push;
        right.x += unitX * push;
        right.z += unitZ * push;
      }
    }
  }
}

export function positionsFromEntries(
  entries: Array<[string, ProvenancePosition]>,
): Map<string, ProvenancePosition> {
  return new Map(entries);
}
