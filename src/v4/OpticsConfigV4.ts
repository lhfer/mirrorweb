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
    high: { radialSegments: 26, outlineSegments: 96, sidewallSegments: 7, shaderSamples: 3 },
    medium: { radialSegments: 20, outlineSegments: 72, sidewallSegments: 6, shaderSamples: 3 },
    low: { radialSegments: 15, outlineSegments: 56, sidewallSegments: 4, shaderSamples: 1 },
  } satisfies Record<
    V4QualityLevel,
    { radialSegments: number; outlineSegments: number; sidewallSegments: number; shaderSamples: number }
  >,
  material: {
    ior: 1.48,
    // Round 3 Stage A. What is measured: no zone is pinned against the
    // maxRefractionUv clamp (0 of 64973 shoulder pixels, 0 of 58846 strong-rim
    // pixels), read at the 8-bit endpoints and so independent of the output
    // transfer. The clamp is not the limit, and neither it nor the scene-target
    // overscan is touched here.
    //
    // What is NOT measured: how far the sample actually moves. The
    // refraction-offset debug view appears to show a flat shoulder, but that
    // view is unsound - it moves by at most 2 of 255 levels while this very
    // change moves the beauty render on 34.9% of pixels. See GATE-005. The
    // displacement increase below is therefore an experiment justified by the
    // blind A/B and the engineering gate, not by that view.
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
