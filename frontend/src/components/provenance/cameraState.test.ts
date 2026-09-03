import { describe, expect, it } from "vitest";

import {
  DEFAULT_CAMERA_STATE,
  applyKeyboardCameraAction,
  clampCameraState,
  focusCameraState,
  parseCameraState,
  serializeCameraState,
} from "./cameraState";

describe("camera state", () => {
  it("clamps distance and pitch to the approved limits", () => {
    const near = clampCameraState({ position: [0, 0.01, 0.01], target: [0, 0, 0] });
    const far = clampCameraState({ position: [0, -1_000, 0], target: [0, 0, 0] });
    expect(Math.hypot(...near.position)).toBeCloseTo(6);
    expect(Math.hypot(...far.position)).toBeCloseTo(90);
    expect(Math.abs(near.position[1])).toBeGreaterThan(0.5);
  });

  it("focuses above and away from a selected node", () => {
    const focused = focusCameraState({ x: 4, y: 9, z: -2 });
    expect(focused.target).toEqual([4, 9, -2]);
    expect(Math.hypot(
      focused.position[0] - 4,
      focused.position[1] - 9,
      focused.position[2] + 2,
    )).toBeGreaterThanOrEqual(24);
  });

  it("round-trips URL state and rejects invalid values", () => {
    const serialized = serializeCameraState({ position: [12, 8, 18], target: [1, 2, 3] });
    expect(parseCameraState(new URLSearchParams(serialized))).toEqual({
      position: [12, 8, 18],
      target: [1, 2, 3],
    });
    expect(parseCameraState(new URLSearchParams("camera=broken"))).toEqual(
      DEFAULT_CAMERA_STATE,
    );
  });

  it("applies keyboard pan, zoom, reset, and clear-selection actions", () => {
    const panned = applyKeyboardCameraAction(DEFAULT_CAMERA_STATE, "ArrowRight");
    const zoomed = applyKeyboardCameraAction(DEFAULT_CAMERA_STATE, "+");
    const reset = applyKeyboardCameraAction(panned.state, "r");
    const escaped = applyKeyboardCameraAction(DEFAULT_CAMERA_STATE, "Escape");
    expect(panned.state.target[0]).toBeGreaterThan(DEFAULT_CAMERA_STATE.target[0]);
    expect(Math.hypot(...zoomed.state.position)).toBeLessThan(
      Math.hypot(...DEFAULT_CAMERA_STATE.position),
    );
    expect(reset.state).toEqual(DEFAULT_CAMERA_STATE);
    expect(reset.clearSelection).toBe(true);
    expect(escaped.clearSelection).toBe(true);
  });
});
