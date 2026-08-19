export const LAB_MODES = ["v3", "v4", "split", "difference"] as const;
export type LabMode = (typeof LAB_MODES)[number];

export const LAB_DEBUG_VIEWS = [
  "beauty",
  "edge-mask",
  "normals",
  "thickness",
  "refraction-offset",
  "reflection",
  "fresnel",
  "dispersion",
  "adaptivity",
] as const;
export type LabDebugView = (typeof LAB_DEBUG_VIEWS)[number];

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

export type LabState = {
  ready: boolean;
  route: "/glass-lab-v4";
  mode: LabMode;
  pattern: LabPattern;
  debug: LabDebugView;
  backend: "webgpu" | "blocked";
  v3Preserved: true;
  normalPathDirectMedia: false;
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
  setPointer: (x: number, y: number) => LabState;
  getMeasurementState: () => LabState;
  reset: () => LabState;
};

declare global {
  interface Window {
    __ILG_V4_LAB_QA__?: LabQaApi;
  }
}
