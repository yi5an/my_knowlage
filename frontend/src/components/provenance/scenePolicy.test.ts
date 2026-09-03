import { describe, expect, it } from "vitest";

import { scenePolicy, shouldBatchSelectedEdges } from "./scenePolicy";

describe("scenePolicy", () => {
  it("reduces label density by distance and graph size", () => {
    const close = scenePolicy({ cameraDistance: 18, nodeCount: 100, dpr: 2 });
    const far = scenePolicy({ cameraDistance: 75, nodeCount: 2_000, dpr: 2 });
    expect(close.maxLabels).toBeGreaterThan(far.maxLabels);
    expect(far.quality).toBe("low");
  });

  it("caps DPR and effects on constrained scenes", () => {
    const policy = scenePolicy({ cameraDistance: 35, nodeCount: 900, dpr: 3 });
    expect(policy.dpr).toBeLessThanOrEqual(1.25);
    expect(policy.shadows).toBe(false);
    expect(policy.nodeScale).toBeLessThan(0.6);
    expect(policy.maxParticles).toBeLessThanOrEqual(32);
  });

  it("emits particles only for a selected path and never auto-rotates by default", () => {
    expect(scenePolicy({ cameraDistance: 30, nodeCount: 100, dpr: 1 }).particles).toBe(false);
    const selected = scenePolicy({
      cameraDistance: 30,
      nodeCount: 100,
      dpr: 1,
      selectedPathEdges: 3,
    });
    expect(selected.particles).toBe(true);
    expect(selected.autoRotate).toBe(false);
    expect(selected.preserveSelectedPath).toBe(true);
  });

  it("disables every animation under reduced motion", () => {
    const policy = scenePolicy({
      cameraDistance: 20,
      nodeCount: 100,
      dpr: 2,
      selectedPathEdges: 4,
      reducedMotion: true,
      autoRotateRequested: true,
    });
    expect(policy).toMatchObject({
      particles: false,
      entrance: false,
      drift: false,
      cameraTween: false,
      autoRotate: false,
      preserveSelectedPath: true,
    });
  });

  it("batches very large selected paths instead of creating one wide-line object per edge", () => {
    expect(shouldBatchSelectedEdges(160)).toBe(false);
    expect(shouldBatchSelectedEdges(161)).toBe(true);
  });
});
