export const LOCAL_URL = "http://127.0.0.1:5280";
export const REFERENCE_URL = "https://infinite-liquid-glass.shader.se/?v=2";

/** Locked from A 1440×900 overlay remasurement. */
export const REF_VIEW = { width: 1440, height: 900 };

export const TILE = {
  width: 518,
  height: 438,
  thickness: 42,
  radius: 58,
  superellipseN: 5,
  outlineSegments: 64,
  bevelSegments: 4,
  smoothness: 3,
  frontBulge: 22,
  backDish: 6,
};

export const GLASS = {
  ior: 1.48,
  warp: 0.2,
  rimPower: 1.42,
  dispersion: 0.07,
  fresnel: 0.14,
  absorption: 0.22,
  blur: 0.008,
  roughness: 0.045,
};

/** 9×9 keeps ≥2 rows and ≥2 cols of overscan around the A rest window. */
export const GRID = {
  cellW: 557.72,
  cellH: 428,
  restY0: -211.05,
  radius: 7200,
  cols: 9,
  rows: 9,
};

export const CAMERA = {
  perspectivePx: 1000,
  fov: 48.46,
  z: 1000,
  y: 8,
  lookY: 0,
  near: 10,
  far: 12000,
};

export const MOTION = {
  dragGain: 0.58,
  damping: 11,
  stopThreshold: 70,
  maxSpeed: 1800,
  wheelGain: 0.055,
  tiltDeg: 1.05,
  parallax: 0.016,
  pointerDamping: 6,
  lightTravel: 120,
};

/** Pull the camera back on short or narrow frames so the brick grid stays discrete. A 1440×900 stays at 1. */
export function viewZoom(width: number, height: number) {
  const minW = TILE.width + GRID.cellW * 0.85;
  const minH = TILE.height + GRID.cellH * 0.65;
  return Math.max(1, minW / Math.max(1, width), minH / Math.max(1, height));
}

export const CLEAR_COLOR = 0x000208;

export type QualityLevel = "high" | "medium" | "low";
