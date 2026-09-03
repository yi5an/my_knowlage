import type { ProvenancePosition } from "./layout";

export type Vector3Tuple = [number, number, number];

export interface ProvenanceCameraState {
  position: Vector3Tuple;
  target: Vector3Tuple;
}

export const DEFAULT_CAMERA_STATE: ProvenanceCameraState = {
  position: [22, 18, 28],
  target: [0, 0, 0],
};

const MIN_DISTANCE = 6;
const MAX_DISTANCE = 90;
const MIN_POLAR = 0.18;
const MAX_POLAR = Math.PI - 0.18;

function finiteTuple(value: Vector3Tuple): boolean {
  return value.every(Number.isFinite);
}

export function clampCameraState(state: ProvenanceCameraState): ProvenanceCameraState {
  if (!finiteTuple(state.position) || !finiteTuple(state.target)) return DEFAULT_CAMERA_STATE;
  let dx = state.position[0] - state.target[0];
  let dy = state.position[1] - state.target[1];
  let dz = state.position[2] - state.target[2];
  let distance = Math.hypot(dx, dy, dz);
  if (distance < 0.0001) {
    [dx, dy, dz] = [0, 1, 1];
    distance = Math.SQRT2;
  }
  const rawPolar = Math.acos(dy / distance);
  if (
    distance >= MIN_DISTANCE &&
    distance <= MAX_DISTANCE &&
    rawPolar >= MIN_POLAR &&
    rawPolar <= MAX_POLAR
  ) {
    return { position: [...state.position], target: [...state.target] };
  }
  const boundedDistance = Math.min(MAX_DISTANCE, Math.max(MIN_DISTANCE, distance));
  const polar = Math.min(MAX_POLAR, Math.max(MIN_POLAR, rawPolar));
  const azimuth = Math.atan2(dz, dx);
  const horizontal = Math.sin(polar) * boundedDistance;
  return {
    target: [...state.target],
    position: [
      state.target[0] + Math.cos(azimuth) * horizontal,
      state.target[1] + Math.cos(polar) * boundedDistance,
      state.target[2] + Math.sin(azimuth) * horizontal,
    ],
  };
}

export function focusCameraState(position: ProvenancePosition): ProvenanceCameraState {
  return clampCameraState({
    target: [position.x, position.y, position.z],
    position: [position.x + 10, position.y + 7, position.z + 12],
  });
}

export function serializeCameraState(state: ProvenanceCameraState): string {
  const bounded = clampCameraState(state);
  const encode = (tuple: Vector3Tuple) => tuple.map((value) => Number(value.toFixed(3))).join(",");
  return new URLSearchParams({
    camera: `${encode(bounded.position)};${encode(bounded.target)}`,
  }).toString();
}

export function parseCameraState(params: URLSearchParams): ProvenanceCameraState {
  const raw = params.get("camera");
  if (!raw) return DEFAULT_CAMERA_STATE;
  const [positionRaw, targetRaw] = raw.split(";");
  const parse = (value?: string): Vector3Tuple | null => {
    if (!value) return null;
    const values = value.split(",").map(Number);
    return values.length === 3 && values.every(Number.isFinite)
      ? (values as Vector3Tuple)
      : null;
  };
  const position = parse(positionRaw);
  const target = parse(targetRaw);
  return position && target ? clampCameraState({ position, target }) : DEFAULT_CAMERA_STATE;
}

export interface KeyboardCameraAction {
  handled: boolean;
  clearSelection: boolean;
  state: ProvenanceCameraState;
}

export function applyKeyboardCameraAction(
  state: ProvenanceCameraState,
  key: string,
): KeyboardCameraAction {
  const normalized = key.toLowerCase();
  if (normalized === "r") {
    return { handled: true, clearSelection: true, state: DEFAULT_CAMERA_STATE };
  }
  if (key === "Escape") {
    return { handled: true, clearSelection: true, state };
  }
  const pan: Record<string, Vector3Tuple> = {
    ArrowLeft: [-1.2, 0, 0],
    ArrowRight: [1.2, 0, 0],
    ArrowUp: [0, 0, -1.2],
    ArrowDown: [0, 0, 1.2],
  };
  if (pan[key]) {
    const delta = pan[key];
    return {
      handled: true,
      clearSelection: false,
      state: {
        position: state.position.map((value, index) => value + delta[index]) as Vector3Tuple,
        target: state.target.map((value, index) => value + delta[index]) as Vector3Tuple,
      },
    };
  }
  if (["+", "=", "-", "_"].includes(key)) {
    const factor = key === "+" || key === "=" ? 0.86 : 1.16;
    return {
      handled: true,
      clearSelection: false,
      state: clampCameraState({
        target: state.target,
        position: state.position.map(
          (value, index) => state.target[index] + (value - state.target[index]) * factor,
        ) as Vector3Tuple,
      }),
    };
  }
  return { handled: false, clearSelection: false, state };
}
