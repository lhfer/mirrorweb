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
  // O3 support-field views. They exist only in the target-sdf lane's
  // shader; selecting one in the geometry lane renders beauty, because
  // adding their branches to the control chain would change the control
  // program and forfeit its exact-zero proof against e913aa6.
  "rim-mask",
  "analytic-normal",
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
  "rim-mask": 10,
  "analytic-normal": 11,
};

export const V4_SHELL_MODES = ["additive", "energy-controlled", "off"] as const;

// O2 System B lane switch: "v1-taps" restores the 5159cf8 dispersion
// verbatim (the B-only lane base); "o1-spectral" is the e01fb30 law (the
// A+B lane base). Selected at material build time; overridable per page
// load with ?dispersionLaw=.
export const V4_DISPERSION_LAWS = ["v1-taps", "o1-spectral"] as const;
export type V4DispersionLaw = (typeof V4_DISPERSION_LAWS)[number];

// O3 reflection-support lane switch. "geometry" is the accepted O2 control
// (the v_o2NormalView geometry normal + the strongLensRim mask);
// "target-sdf" is the O3 candidate (the Target's analytic bevel normal +
// its rounded-rect SDF rim). Selected at material build time -- a JS
// branch, not a shader one, so the geometry lane emits the O2 program byte
// for byte and stays provably pixel-identical to e913aa6. Overridable per
// page load with ?reflectionSupport=.
export const V4_REFLECTION_SUPPORTS = ["geometry", "target-sdf"] as const;
export type V4ReflectionSupport = (typeof V4_REFLECTION_SUPPORTS)[number];

// O4 body-floor diagnostic factors. Each neutralises ONE subsystem of the
// System-B-OFF body so its contribution to the frozen body floor can be
// measured; `repairRefractionNormal` instead repairs the codegen fault the
// O4A audit found (qa-v5/optics-o4/body-code-audit.json).
//
// Every one is a BUILD-TIME branch taken in TypeScript before the node
// graph exists, never a uniform tested inside the shader. A uniform would
// put all lanes in one program, change the control program, and forfeit
// the control's exact-zero proof against the accepted O2 body. With every
// flag false the material builds the identical graph it built before this
// type existed -- the same node objects, not equivalent ones.
export const V4_BODY_DIAG_ORDER = [
  "noRefractionOffset",     // A -- identity / no screen-space displacement
  "noBlur",                 // B -- level-0 sampling, no mip blur
  "noAdaptiveShaping",      // C -- raw refracted colour
  "noDispersion",           // D -- one sample, no spectral spread
  "linearOutput",           // E -- body material toneMapped = false
  "repairRefractionNormal", // N -- feed the body a real geometry normal
] as const;

// O4 PRODUCT lane switch, distinct from the diagnostic factors above.
// "current" is the accepted O2 body; "remove-adaptive-shaping" is the one
// subsystem §七 selected (qa-v5/optics-o4/o4-selected-subsystem.json): the
// Target's body chain contains no contrast shaping, no edge lift and no
// internal shadow, and ours contributes 141% of the desktop body-floor
// excess through them. Build-time, like every other lane switch here.
export const V4_BODY_FLOOR_MODES = ["current", "remove-adaptive-shaping"] as const;
export type V4BodyFloorMode = (typeof V4_BODY_FLOOR_MODES)[number];

// O5 PRODUCT lane switch: the whole card optical body, as one system.
//
// "current" is everything O2 accepted -- convex geometry, a shared
// screen-space body, a separate reflection shell and a separate media plane.
// "target-source" is the Target's own material chain, transcribed from
// qa-v5/optics-o5/target-optical-body-contract.json: a domed unit plane, a
// rounded-rect SDF, an analytic bevel normal, per-IOR spectral refraction of
// the card's OWN media, and the accepted System B environment and white rim in
// the SAME material.
//
// Build-time, like every other lane switch here, and for the same reason: the
// two lanes must be different PROGRAMS, so the control lane emits the accepted
// body byte for byte and keeps its exact-zero identity proof. Overridable per
// page load with ?opticalBody=.
export const V4_OPTICAL_BODIES = ["current", "target-source"] as const;
export type V4OpticalBody = (typeof V4_OPTICAL_BODIES)[number];

export function parseOpticalBody(v: string | null | undefined): V4OpticalBody {
  return V4_OPTICAL_BODIES.includes(v as V4OpticalBody)
    ? (v as V4OpticalBody)
    : "current";
}

// O5 candidate debug views. Each is a SEPARATE PROGRAM built at material
// construction, never a runtime branch -- see TargetOpticalBodyV5 for why that
// distinction is load-bearing after the O4A codegen finding.
export const V5_BODY_VIEW_NAMES = [
  "beauty", "sdf-mask", "analytic-normal", "refraction-only",
] as const;
export type V5BodyViewName = (typeof V5_BODY_VIEW_NAMES)[number];

export function parseBodyView(v: string | null | undefined): V5BodyViewName {
  return V5_BODY_VIEW_NAMES.includes(v as V5BodyViewName)
    ? (v as V5BodyViewName) : "beauty";
}

export function parseBodyFloorMode(v: string | null | undefined): V4BodyFloorMode {
  return V4_BODY_FLOOR_MODES.includes(v as V4BodyFloorMode)
    ? (v as V4BodyFloorMode) : "current";
}

export type V4BodyDiagFactor = (typeof V4_BODY_DIAG_ORDER)[number];
export type V4BodyDiag = Record<V4BodyDiagFactor, boolean>;

export const V4_BODY_DIAG_OFF: V4BodyDiag = Object.freeze(
  Object.fromEntries(V4_BODY_DIAG_ORDER.map((k) => [k, false])),
) as V4BodyDiag;

/** "010010" -> the flags in V4_BODY_DIAG_ORDER. Anything else is all-off. */
export function parseBodyDiag(value: string | null | undefined): V4BodyDiag {
  if (!value || !/^[01]{6}$/.test(value)) return { ...V4_BODY_DIAG_OFF };
  return Object.fromEntries(
    V4_BODY_DIAG_ORDER.map((k, i) => [k, value[i] === "1"]),
  ) as V4BodyDiag;
}

export function bodyDiagCode(diag: V4BodyDiag): string {
  return V4_BODY_DIAG_ORDER.map((k) => (diag[k] ? "1" : "0")).join("");
}

export function isBodyDiagOff(diag: V4BodyDiag): boolean {
  return V4_BODY_DIAG_ORDER.every((k) => !diag[k]);
}
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
    // O1 System A: no longer read by the shader (superseded by
    // dispersionSpread); kept so stored params keep their shape.
    dispersionUv: 0.0065,
    // O1 System A: relative spread of the refraction displacement per unit
    // spectral offset -- see LiquidGlassMaterialV4. Chosen against the
    // Target's measured edge-band statistics, not against Before.
    dispersionSpread: 0.3,
    reflectionStrength: 1.15,
    roughnessCenter: 0.16,
    roughnessRim: 0.055,
    fresnelPower: 5,
    adaptivityRadiusUv: 0.0035,
    // O2: the pre-selection default preserves current behaviour (the O1
    // spectral law). The pre-registered §四 rule decides the shipped
    // default AFTER both lanes are scored; flipping it is the execution
    // of that rule, recorded in candidate-selection.json.
    dispersionLaw: "o1-spectral" as V4DispersionLaw,
    // O3: the code commit ships the O2 CONTROL. The pre-registered §六
    // rule flips this to "target-sdf" in the evidence commit if and only
    // if all twenty absolute-gate items pass; see
    // qa-v5/optics-o3/o3-preregistration.json.
    reflectionSupport: "geometry" as V4ReflectionSupport,
    // O4: the code commit ships the CONTROL. The O4 absolute gate decides
    // whether the candidate becomes the default; there is no automatic
    // flip, and product review owns that call.
    bodyFloorMode: "current" as V4BodyFloorMode,
    // O5: the code commit ships the CONTROL. There is no automatic flip in
    // this brief -- its final states do not include one, and product review
    // owns the decision.
    opticalBody: "current" as V4OpticalBody,
    // O2 System B -- the Target's shipped values, adopted verbatim
    // (byte-anchored in qa-v5/optics-o2/target-system-b-source.json).
    // None of these is a tunable; see o2-selected-system.json.
    systemB: {
      fresnelF0: 0.045,
      envIntensity: 1.93,
      envMaxMix: 0.27,
      envRotationY: -2,
      envRotationX: 0,
      rimIntensity: 0.11,
      // Guard ceiling on the HDR sample before the LERP: a hot texel must
      // not inject Inf (0 * Inf = NaN would break the envMixScale=0
      // floor's exact equivalence to the pre-O2 body).
      envSampleCeiling: 16,
      // The product asset; byte-identical to the Target's served env.
      assetPath: "/hdri/studio_small_03_1k.hdr",
    },
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
