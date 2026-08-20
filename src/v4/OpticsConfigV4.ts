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

/**
 * How the material turns the surface normal into a scene-colour sample offset.
 *
 * `projected-exit` is the original law: project the surface point and the Snell
 * exit point and take the screen-space difference. It saturates by
 * construction - moving the exit point further along the refracted ray
 * converges on that ray's vanishing point - which is why `refractionDistance`
 * is near-inert past about 150 (ILG-A-009).
 *
 * `snell-screen` displaces by tan(theta_t) scaled by thickness, so the offset
 * rises monotonically with surface slope and has no upper asymptote.
 *
 * `snell-screen-multitap` accumulates several samples along that displacement,
 * so a fragment integrates a segment of the refracted path instead of a point.
 */
export const V4_REFRACTION_MODELS = ["projected-exit", "snell-screen", "snell-screen-multitap"] as const;
export type V4RefractionModel = (typeof V4_REFRACTION_MODELS)[number];

export type V4GeometryConfig = {
  width: number;
  height: number;
  baseThickness: number;
  superellipseN: number;
  centerFrontZ: number;
  /** Front-surface sag between the clear centre and the rollover crown. */
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
    // `shaderSamples` is declared here but referenced nowhere in the codebase.
    // `refractionTaps` is the live one, used by the multitap refraction model.
    high: { radialSegments: 26, outlineSegments: 96, sidewallSegments: 7, shaderSamples: 3, refractionTaps: 4 },
    medium: { radialSegments: 20, outlineSegments: 72, sidewallSegments: 6, shaderSamples: 3, refractionTaps: 3 },
    low: { radialSegments: 15, outlineSegments: 56, sidewallSegments: 4, shaderSamples: 1, refractionTaps: 2 },
  } satisfies Record<
    V4QualityLevel,
    {
      radialSegments: number;
      outlineSegments: number;
      sidewallSegments: number;
      shaderSamples: number;
      refractionTaps: number;
    }
  >,
  material: {
    ior: 1.48,
    refractionModel: "snell-screen-multitap" as V4RefractionModel,
    /** snell-screen: displacement at grazing incidence, in scene-target UV. */
    refractionGainUv: 0.085,
    /** snell-screen: distance from the silhouette the refracting band spans. */
    edgeBandPx: 88,
    // Only used by the `projected-exit` model, and near-inert even there:
    // changing it from 300 to 1200 moves the beauty render by at most 4 of 255
    // levels on 0.001% of pixels, because the projected exit point converges on
    // the refracted ray's vanishing point instead of diverging (ILG-A-009).
    //
    // Measured on the debug view, which round 4 validated as sound after round
    // 3 wrongly suspected it (GATE-005, closed as a false positive): across the
    // 88px shoulder the offset spans 3 of 255 levels while the 38px strong rim
    // spans 100, and no zone is pinned against the maxRefractionUv clamp.
    refractionDistance: 300,
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
