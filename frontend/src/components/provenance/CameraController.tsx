import { OrbitControls } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  type RefObject,
} from "react";
import * as THREE from "three";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

import {
  DEFAULT_CAMERA_STATE,
  clampCameraState,
  focusCameraState,
  type ProvenanceCameraState,
} from "./cameraState";
import type { ProvenancePosition } from "./layout";
import { updateProvenanceDebug } from "./debug";

export interface CameraControllerHandle {
  getState(): ProvenanceCameraState;
  applyState(state: ProvenanceCameraState): void;
  reset(): void;
}

interface CameraControllerProps {
  initialState?: ProvenanceCameraState;
  focusPosition?: ProvenancePosition;
  shiftPan: boolean;
  motionEnabled?: boolean;
  onCameraChange?: (state: ProvenanceCameraState) => void;
}

interface CameraTween {
  elapsed: number;
  duration: number;
  fromPosition: THREE.Vector3;
  fromTarget: THREE.Vector3;
  toPosition: THREE.Vector3;
  toTarget: THREE.Vector3;
}

export const CameraController = forwardRef<CameraControllerHandle, CameraControllerProps>(
  function CameraController(
    {
      initialState = DEFAULT_CAMERA_STATE,
      focusPosition,
      shiftPan,
      motionEnabled = true,
      onCameraChange,
    },
    forwardedRef,
  ) {
    const controlsRef = useRef<OrbitControlsImpl>(null);
    const { camera, invalidate } = useThree();
    const tweenRef = useRef<CameraTween | null>(null);

    const readState = (): ProvenanceCameraState => {
      const target = controlsRef.current?.target ?? new THREE.Vector3(...initialState.target);
      const state = clampCameraState({
        position: camera.position.toArray() as [number, number, number],
        target: target.toArray() as [number, number, number],
      });
      updateProvenanceDebug({
        cameraPosition: [...state.position],
        cameraQuaternion: camera.quaternion.toArray() as [number, number, number, number],
        controlsTarget: [...state.target],
      });
      return state;
    };

    const applyState = (state: ProvenanceCameraState) => {
      const bounded = clampCameraState(state);
      camera.position.set(...bounded.position);
      controlsRef.current?.target.set(...bounded.target);
      controlsRef.current?.update();
      readState();
      invalidate();
    };

    useImperativeHandle(
      forwardedRef,
      () => ({
        getState: readState,
        applyState,
        reset: () => {
          tweenRef.current = null;
          applyState(DEFAULT_CAMERA_STATE);
          onCameraChange?.(DEFAULT_CAMERA_STATE);
        },
      }),
      // The R3F camera remains stable for the lifetime of the canvas.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [camera, invalidate, onCameraChange],
    );

    useEffect(() => {
      applyState(initialState);
      // Initial state should only be applied when the serialized URL camera changes.
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [initialState]);

    useEffect(() => {
      const controls = controlsRef.current;
      if (!controls) return;
      controls.mouseButtons.LEFT = shiftPan ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
    }, [shiftPan]);

    useEffect(() => {
      if (!focusPosition || !controlsRef.current) return;
      const destination = focusCameraState(focusPosition);
      if (!motionEnabled) {
        applyState(destination);
        onCameraChange?.(destination);
        return;
      }
      tweenRef.current = {
        elapsed: 0,
        duration: 0.45,
        fromPosition: camera.position.clone(),
        fromTarget: controlsRef.current.target.clone(),
        toPosition: new THREE.Vector3(...destination.position),
        toTarget: new THREE.Vector3(...destination.target),
      };
      invalidate();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [focusPosition, motionEnabled]);

    useFrame((_state, delta) => {
      const tween = tweenRef.current;
      const controls = controlsRef.current;
      if (!tween || !controls) return;
      tween.elapsed = Math.min(tween.duration, tween.elapsed + delta);
      const progress = tween.elapsed / tween.duration;
      const eased = 1 - Math.pow(1 - progress, 3);
      camera.position.lerpVectors(tween.fromPosition, tween.toPosition, eased);
      controls.target.lerpVectors(tween.fromTarget, tween.toTarget, eased);
      controls.update();
      if (progress < 1) {
        invalidate();
      } else {
        tweenRef.current = null;
        onCameraChange?.(readState());
      }
    });

    return (
      <OrbitControls
        ref={controlsRef as RefObject<OrbitControlsImpl>}
        makeDefault
        enableDamping
        dampingFactor={0.08}
        zoomToCursor
        minDistance={6}
        maxDistance={90}
        minPolarAngle={0.18}
        maxPolarAngle={Math.PI - 0.18}
        mouseButtons={{
          LEFT: THREE.MOUSE.ROTATE,
          MIDDLE: THREE.MOUSE.PAN,
          RIGHT: THREE.MOUSE.PAN,
        }}
        onChange={() => {
          readState();
          invalidate();
        }}
        onEnd={() => onCameraChange?.(readState())}
      />
    );
  },
);
