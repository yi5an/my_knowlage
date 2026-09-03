import type { TraceLayer } from "../../types/provenance";
import { LAYER_Y } from "./layout";

const COLORS: Record<TraceLayer, string> = {
  conclusion: "#a855f7",
  event: "#3b82f6",
  evidence: "#14b8a6",
};

export function LayerPlane({ layer }: { layer: TraceLayer }) {
  return (
    <mesh position={[0, LAYER_Y[layer], 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <circleGeometry args={[17, 64]} />
      <meshStandardMaterial
        color={COLORS[layer]}
        transparent
        opacity={0.075}
        depthWrite={false}
        roughness={0.8}
        metalness={0.05}
      />
    </mesh>
  );
}
