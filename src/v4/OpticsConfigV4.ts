import { TILE, type QualityLevel } from "../config";

export type V4QualityLevel = QualityLevel;

export const V4_DEBUG_MODES = [
  "beauty",
  "edge-mask",
  "optical-zones",
  "normals",
  "thickness",
  "refraction-offset",
  "reflection",
  "fresnel",
  "dispersion",
  "adaptivity",
] as const;

export type V4DebugMode = (typeof V4_DEBUG_MODES)[number];

export const V4_DEBUG_CODE: Readonly<Record<V4DebugMode, number>> = {
  beauty: 0,
  "edge-mask": 1,
  "optical-zones": 2,
  normals: 3,
  thickness: 4,
  "refraction-offset": 5,
  reflection: 6,
  fresnel: 7,
  dispersion: 8,
  adaptivity: 9,
};

export const V4_SHELL_MODES = ["additive", "energy-controlled", "off"] as const;
export type V4ShellMode = (typeof V4_SHELL_MODES)[number];

export type V4FrontProfile = "two-piece" | "monotonic-arc";

export type V4GeometryConfig = {
  width: number;
  height: number;
  baseThickness: number;
  superellipseN: number;
  centerFrontZ: number;
  /**
   * Shape of the front surface between the clear centre and the silhouette.
   * `two-piece` is the original shoulder-plus-rollover pair, kept so the
   * change is reviewable; `monotonic-arc` is a single arc whose slope only
   * ever increases toward the silhouette.
   */
  frontProfile: V4FrontProfile;
  /** monotonic-arc: distance from the silhouette that the arc spans. */
  edgeArcPx: number;
  /** monotonic-arc: total sag across the arc. */
  edgeArcDropPx: number;
  /** two-piece: front-surface sag between the clear centre and the crown. */
  shoulderDropPx: number;
  shoulderOuterPx: number;
  rolloverInsetPx: number;
  rolloverDepthPx: number;
  backDishPx: number;
  lensRimWidthPx: number;
};

export const V4_OPTICS_CONFIG = {
  version: "v4",
  sceneTarget: {
    resolutionScale: {
      high: 1,
      medium: 0.75,
      low: 0.55,
    } satisfies Record<V4QualityLevel, number>,
  },
  geometry: {
    width: TILE.width,
    height: TILE.height,
    baseThickness: TILE.thickness,
    superellipseN: TILE.superellipseN,
    centerFrontZ: TILE.thickness * 0.5 + TILE.frontBulge,
    // Round 2 Stage A: the two-piece profile put a dead flat ring at
    // rolloverInsetPx, where the shoulder's smootherstep and the rollover
    // ellipse met tangent-to-tangent at zero slope. Measured slope against
    // distance from the silhouette went 33 deg at 8px, 0.5 deg at 16px, back up
    // to 32 deg at 52px. Refraction is built on that normal, so the card bent,
    // un-bent, then creased. A single arc spans the same band with the same
    // total sag and the same silhouette z, but its slope only increases.
    frontProfile: "monotonic-arc",
    edgeArcPx: 88,
    edgeArcDropPx: 42,
    // Round 1 Stage A: the previous profile sagged only 10px between the centre
    // and the crown, so the normal stayed near (0,0,1) until the last 16px and
    // the card read as flat media with a coloured outline. The shoulder now
    // carries a real lens-edge slope across a wider band.
    shoulderDropPx: 24,
    shoulderOuterPx: 88,
    rolloverInsetPx: 16,
    rolloverDepthPx: 18,
    backDishPx: TILE.backDish,
    lensRimWidthPx: 38,
  } satisfies V4GeometryConfig,
  quality: {
    high: { radialSegments: 26, outlineSegments: 96, sidewallSegments: 7, shaderSamples: 3 },
    medium: { radialSegments: 20, outlineSegments: 72, sidewallSegments: 6, shaderSamples: 3 },
    low: { radialSegments: 15, outlineSegments: 56, sidewallSegments: 4, shaderSamples: 1 },
  } satisfies Record<
    V4QualityLevel,
    { radialSegments: number; outlineSegments: number; sidewallSegments: number; shaderSamples: number }
  >,
  material: {
    ior: 1.48,
    refractionDistance: 165,
    maxRefractionUv: 0.125,
    blurLod: 2.35,
    dispersionUv: 0.0065,
    reflectionStrength: 1.15,
    roughnessCenter: 0.16,
    roughnessRim: 0.055,
    fresnelPower: 5,
    adaptivityRadiusUv: 0.0035,
    zoneCoefficients: {
      // Center remains on the same scene-color path. Its near-zero projected
      // normal only produces a deliberately tiny refraction displacement.
      refraction: { center: 0.025, shoulder: 0.72, strongLensRim: 1, sidewall: 0.9 },
      blur: { center: 0, shoulder: 0.46, strongLensRim: 1, sidewall: 0.68 },
      // Round 2 Stage A: one-hot on strongLensRim painted chroma along the
      // silhouette, which reads as an outlined sticker. It now carries into the
      // shoulder and the sidewall and is graded by displacement in the material,
      // so the band has a soft inner falloff. The shoulder share is kept small
      // on purpose: the gate's full-screen-dispersion guard treats anything
      // inside 0.86 of the card half-size as interior.
      dispersion: { center: 0, shoulder: 0, strongLensRim: 1, sidewall: 0 },
      shell: { center: 0.012, shoulder: 0.48, strongLensRim: 1, sidewall: 0.3 },
    },
    shell: {
      fresnelOpacity: 0.2,
      zoneOpacity: 0.13,
      opacityMax: 0.42,
      clearcoat: 0.68,
      adaptivityMin: 0.7,
      adaptivityMax: 1.18,
    },
  },
  pointerLight: {
    baseX: -360,
    baseY: 540,
    z: 980,
    travelX: 690,
    travelY: 520,
    intensity: 2.8,
  },
} as const;

export function getV4QualityPreset(level: V4QualityLevel) {
  return V4_OPTICS_CONFIG.quality[level];
}
