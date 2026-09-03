export type CanvasFactory = () => Pick<HTMLCanvasElement, "getContext">;

export function supportsWebGL(
  createCanvas: CanvasFactory = () => document.createElement("canvas"),
): boolean {
  try {
    const canvas = createCanvas();
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}
