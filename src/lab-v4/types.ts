import {
  V4_DEBUG_MODES,
  V4_SHELL_MODES,
  type V4DebugMode,
  type V4ShellMode,
} from "../v4/OpticsConfigV4";

export const LAB_MODES = ["v3", "v4", "split", "difference"] as const;
export type LabMode = (typeof LAB_MODES)[number];

export const LAB_SHELL_MODES = V4_SHELL_MODES;
export type LabShellMode = V4ShellMode;

export const LAB_POSES = ["front", "left", "right"] as const;
export type LabPose = (typeof LAB_POSES)[number];

export const LAB_DEBUG_VIEWS = V4_DEBUG_MODES;
export type LabDebugView = V4DebugMode;

export const LAB_PATTERNS = [
  "checker",
  "horizontal-lines",
  "vertical-lines",
  "text-grid",
  "high-frequency-photo",
  "low-frequency-flat-color",
  "white",
  "black",
  "animated-gradient",
  "video",
] as const;
export type LabPattern = (typeof LAB_PATTERNS)[number];

export type LabPointer = { x: number; y: number };

export type LabOpticalZoneCoefficients = {
  center: number;
  shoulder: number;
  strongLensRim: number;
  sidewall: number;
};

export type LabState = {
  ready: boolean;
  route: "/glass-lab-v4";
  mode: LabMode;
  pattern: LabPattern;
  debug: LabDebugView;
  shellMode: LabShellMode;
  pose: LabPose;
  backend: "webgpu" | "blocked";
  v3Preserved: true;
  normalPathDirectMedia: false;
  opticalConfig: {
    shoulderOuterPx: number;
    rolloverInsetPx: number;
    rolloverDepthPx: number;
    lensRimWidthPx: number;
    maxRefractionUv: number;
    blurLod: number;
    refractionCoefficients: LabOpticalZoneCoefficients;
    blurCoefficients: LabOpticalZoneCoefficients;
    dispersionCoefficients: LabOpticalZoneCoefficients;
    shellCoefficients: LabOpticalZoneCoefficients;
    shell: {
      fresnelOpacity: number;
      zoneOpacity: number;
      opacityMax: number;
      clearcoat: number;
      adaptivityMin: number;
      adaptivityMax: number;
    };
  };
  sceneTarget: {
    type: "half-float" | "unexpected";
    colorSpace: "linear" | "unexpected";
    quality: string;
    scale: number;
    width: number;
    height: number;
  };
  pointer: LabPointer;
  highlight: {
    source: "pointer-key-light-proxy";
    proxyX: number;
    proxyY: number;
    measuredCentroidAvailable: false;
    continuousInput: true;
  };
  frame: {
    medianMs: number;
    p95Ms: number;
    samples: number;
  };
};

export type LabQaApi = {
  readonly ready: boolean;
  getState: () => LabState;
  setPattern: (pattern: LabPattern | string) => LabState;
  setMode: (mode: LabMode | string) => LabState;
  setDebug: (debug: LabDebugView | "difference" | string) => LabState;
  setShellMode: (mode: LabShellMode | string) => LabState;
  setPose: (pose: LabPose | string) => LabState;
  setPointer: (x: number, y: number) => LabState;
  getMeasurementState: () => LabState;
  reset: () => LabState;
};

declare global {
  interface Window {
    __ILG_V4_LAB_QA__?: LabQaApi;
  }
}
