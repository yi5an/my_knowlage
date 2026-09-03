import type { TraceLayer } from "../../types/provenance";
import { LAYER_Y } from "./layout";
import { layerPalette } from "./provenancePalette";

export function LayerPlane({ layer }: { layer: TraceLayer }) {
  const palette = layerPalette(layer);
  return (
    <mesh position={[0, LAYER_Y[layer], 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <circleGeometry args={[17, 64]} />
      <meshStandardMaterial
        color={palette.plane}
        transparent
        opacity={0.2}
        depthWrite={false}
        roughness={0.8}
        metalness={0.05}
      />
    </mesh>
  );
}
