export interface ScenePolicyInput {
  cameraDistance: number;
  nodeCount: number;
  dpr: number;
  selectedPathEdges?: number;
  reducedMotion?: boolean;
  autoRotateRequested?: boolean;
}

export interface ProvenanceScenePolicy {
  quality: "high" | "medium" | "low";
  maxLabels: number;
  dpr: number;
  shadows: boolean;
  nodeScale: number;
  maxParticles: number;
  particles: boolean;
  entrance: boolean;
  drift: boolean;
  cameraTween: boolean;
  autoRotate: boolean;
  preserveSelectedPath: true;
}

export function shouldBatchSelectedEdges(selectedEdgeCount: number): boolean {
  return selectedEdgeCount > 160;
}

export function scenePolicy(input: ScenePolicyInput): ProvenanceScenePolicy {
  const quality = input.nodeCount > 750 ? "low" : input.nodeCount > 280 ? "medium" : "high";
  const maxLabels =
    quality === "low"
      ? input.cameraDistance > 55
        ? 10
        : 20
      : quality === "medium"
        ? input.cameraDistance > 55
          ? 24
          : 42
        : input.cameraDistance > 55
          ? 36
          : 90;
  const reducedMotion = input.reducedMotion ?? false;
  return {
    quality,
    maxLabels,
    dpr: Math.min(input.dpr, quality === "high" ? 1.75 : quality === "medium" ? 1.25 : 1),
    shadows: quality === "high",
    nodeScale: quality === "high" ? 1 : quality === "medium" ? 0.72 : 0.46,
    maxParticles: quality === "high" ? 120 : quality === "medium" ? 64 : 32,
    particles: !reducedMotion && (input.selectedPathEdges ?? 0) > 0,
    entrance: !reducedMotion,
    drift: !reducedMotion,
    cameraTween: !reducedMotion,
    autoRotate: !reducedMotion && Boolean(input.autoRotateRequested),
    preserveSelectedPath: true,
  };
}
