export interface ProvenanceDebugSnapshot {
  renderer: "WebGLRenderer";
  frame: number;
  cameraPosition: [number, number, number];
  cameraQuaternion: [number, number, number, number];
  controlsTarget: [number, number, number];
  selectedNodeId: string | null;
  selectedEdgeCount: number;
  geometries: number;
  textures: number;
  mounted: boolean;
  reducedMotion: boolean;
  nodeScreenPositions: Record<string, [number, number]>;
  edgeScreenPositions: Record<string, [number, number]>;
}

declare global {
  interface Window {
    __KNOWPILOT_PROVENANCE_DEBUG__?: ProvenanceDebugSnapshot;
  }
}

export function updateProvenanceDebug(
  values: Partial<ProvenanceDebugSnapshot>,
): void {
  if (!provenanceDebugEnabled()) return;
  const previous = window.__KNOWPILOT_PROVENANCE_DEBUG__;
  window.__KNOWPILOT_PROVENANCE_DEBUG__ = {
    renderer: "WebGLRenderer",
    frame: previous?.frame ?? 1,
    cameraPosition: values.cameraPosition ?? previous?.cameraPosition ?? [22, 18, 28],
    cameraQuaternion: values.cameraQuaternion ?? previous?.cameraQuaternion ?? [0, 0, 0, 1],
    controlsTarget: values.controlsTarget ?? previous?.controlsTarget ?? [0, 0, 0],
    selectedNodeId:
      "selectedNodeId" in values ? (values.selectedNodeId ?? null) : previous?.selectedNodeId ?? null,
    selectedEdgeCount: values.selectedEdgeCount ?? previous?.selectedEdgeCount ?? 0,
    geometries: values.geometries ?? previous?.geometries ?? 0,
    textures: values.textures ?? previous?.textures ?? 0,
    mounted: values.mounted ?? previous?.mounted ?? true,
    reducedMotion: values.reducedMotion ?? previous?.reducedMotion ?? false,
    nodeScreenPositions: values.nodeScreenPositions ?? previous?.nodeScreenPositions ?? {},
    edgeScreenPositions: values.edgeScreenPositions ?? previous?.edgeScreenPositions ?? {},
  };
}

export function provenanceDebugEnabled(): boolean {
  if (typeof window === "undefined") return false;
  return (
    import.meta.env.DEV ||
    import.meta.env.MODE === "test" ||
    new URLSearchParams(window.location.search).has("fixture")
  );
}
