export const LOCAL_URL = "http://127.0.0.1:5280";
export const REFERENCE_URL = "https://infinite-liquid-glass.shader.se/?v=2";

/** Locked from A 1440×900 overlay remasurement. */
export const REF_VIEW = { width: 1440, height: 900 };

/**
 * Card slab, in world units (1 world unit = 1 CSS px on the z=0 plane at
 * 1440x900). Width/height come from the V5 F0 joint fit against the Target
 * frame, minus the rim inflation a pixel detector adds to a rendered card
 * (~1 px across, ~2 px down). See docs/v5/FOUNDATION_FIT.md.
 */
export const TILE = {
  width: 539.8,
  height: 399.6,
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
  cellW: 561.14,
  cellH: 420.43,
  restY0: -209.97,
  // NEGATIVE on purpose. The Target grid is CONVEX toward the camera: the
  // centre column is nearest and outer columns recede, so an outer card is
  // smaller than a centre card in the same row (Target bottom row: 388.3 px
  // tall at |u|=cellW vs 401.1 px at u=0). The old +7200 was concave, which
  // makes outer cards larger and fails every same-row size check.
  radius: -4058.94,
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

/**
 * Responsive composition scaling (Stage F2).
 *
 * `compositionScale` is S: screen pixels per world unit on the z = 0 plane. The
 * V5 Foundation geometry is fitted at 1440x900 where S = 1, and every other
 * viewport is that same world grid viewed at a different scale. Nothing about
 * the cards changes; only S does.
 *
 * The law is measured, not assumed. scripts/v5/fit-scale.py recovers S from the
 * live Target at a sweep of viewports, holding the world geometry fixed, and
 * two regimes come out:
 *
 *   landscape (width >= height)  S = width / 1440
 *   portrait  (width <  height)  S = PORTRAIT_GAIN * width / 1440
 *
 * The split is ORIENTATION, not a width breakpoint: a 700x900 portrait window
 * uses the portrait law while a 667x375 landscape window uses the landscape
 * one, even though the portrait window is the wider of the two. A width
 * breakpoint cannot produce that.
 *
 * It is a width law, not a height or area law: at a fixed 1440 width the Target
 * returns the same S at 700 and at 1080 tall.
 */
export function isPortrait(width: number, height: number): boolean {
  return width < height;
}

import { rowOriginHalfCellPhase, targetLayout } from "./scene/RowPhase";

export const COMPOSITION_VERSIONS = ["v1", "v2"] as const;
export type CompositionVersion = (typeof COMPOSITION_VERSIONS)[number];
export const VERTICAL_MODES = ["depth", "tangent"] as const;
export type VerticalMode = (typeof VERTICAL_MODES)[number];

/**
 * Stage F2.5 — joint responsive and vertical composition.
 *
 * v1 is the F2 candidate, kept reachable at `?composition=v1` so the change is
 * reversible until product review says otherwise. v2 is this candidate.
 *
 * Three things move together and were solved together, because they are
 * coupled: portrait scale, vertical grid depth, and the rest phase. Fitting
 * the scale first and then attributing whatever is left to a vertical radius
 * would have produced a confident wrong answer.
 */
export const COMPOSITION_V2 = {
  /**
   * Per-mode parameters. Both were solved by the SAME joint fit
   * (scripts/v5/f25-joint-fit.py) against the same Target observations, so the
   * two candidates are compared on equal terms rather than one being handed
   * the other's parameters.
   *
   * `radiusY` is an exact cosine DEPTH law: a row recedes with its vertical
   * distance from the axis and keeps its spacing. F3's diagnostic seed of
   * -2053 came from a parabolic approximation fitted to row heights alone; the
   * joint fit, which also has to satisfy gutters and band positions, lands far
   * looser. The seed was a seed, not ground truth.
   */
  /**
   * Portrait law candidates, all three runnable via `?portraitLaw=`.
   *
   * P0 is what F2.5 shipped. It misses the held-out 390x844 scale by +5.09%.
   * P1 is the law cross-validation endorses, +0.47%, with vertical untouched so
   * only the scale changes. P2 locks P1's scale and refits the vertical under
   * it. Numbers are exactly those validated in qa-v5/f26/portrait-crossval.json.
   */
  portraitLaws: {
    p0: { radiusY: -4707.6, cellH: 419.95, restY0: -200.99,
          portraitGainBase: 1.9468, portraitGainAspectSlope: -0.31 },
    p1: { radiusY: -4707.6, cellH: 419.95, restY0: -200.99,
          portraitGainBase: 1.87715, portraitGainAspectSlope: 0.12204 },
    p2: { radiusY: -5576.1, cellH: 422.56, restY0: -202.57,
          portraitGainBase: 1.87715, portraitGainAspectSlope: 0.12204 },
  },
  /** Which of the three ships. */
  portraitLaw: "p1" as "p0" | "p1" | "p2",
  depth: {
    radiusY: -6496.2,
    cellH: 423.69,
    restY0: -202.41,
    portraitGainBase: 1.9026,
    portraitGainAspectSlope: 0,
  },
  tangent: {
    radiusY: -4707.6,
    cellH: 419.95,
    restY0: -200.99,
    portraitGainBase: 1.9468,
    portraitGainAspectSlope: -0.31,
  },
  /** Default when no `?verticalMode=` is given. */
  verticalMode: "tangent" as VerticalMode,
  /**
   * Rest phase, by viewport SHAPE.
   *
   * The F2.5 rule switched on composition scale. Re-measured against the
   * RUNTIME law -- the shipped landscape scale is width/1440, not the offline
   * fitter's -- that rule scores 23 of 39. A CSS-width interval cannot work
   * either: the same width takes different phases at different heights
   * (900x420 against 900x899, 1440x700 against 1440x900), so the widths
   * interleave and no interval separates them.
   *
   * What does separate them is aspect. `height < 0.5525 * width` scores 35 of
   * 39, on a plateau running from 0.545 to 0.56; 0.5525 is its midpoint.
   *
   * KNOWN FRAGILITY: 16:9 sits at 0.5625, barely above the threshold. The most
   * common desktop aspect is roughly 0.01 away from flipping phase. Widening
   * the sweep around 16:9 is the first thing to do if this rule misbehaves.
   *
   * Misses, recorded rather than tuned away: 667x375, 700x700, 780x470,
   * 1440x1080. See qa-v5/f26/landscape-phase.json.
   *
   * SUPERSEDED in F2.7 by `phaseModel: "rowOrigin"`, which has no threshold at
   * all. Kept reachable as `?phaseModel=aspect` so the change is reversible.
   */
  restPhaseAspectThreshold: 0.5525,
  /** Which rest-phase law runs. See src/scene/RowPhase.ts. */
  phaseModel: "rowOrigin" as PhaseModel,
} as const;

export const PHASE_MODELS = ["aspect", "rowOrigin"] as const;
export type PhaseModel = (typeof PHASE_MODELS)[number];

export function phaseModel(search: string = location.search): PhaseModel {
  const value = new URLSearchParams(search).get("phaseModel");
  return (PHASE_MODELS as readonly string[]).includes(value ?? "")
    ? (value as PhaseModel)
    : COMPOSITION_V2.phaseModel;
}

/**
 * Portrait-only vertical composition (Stage F2.7 part B).
 *
 * The horizontal scale law is frozen this round, so the only lever left in
 * portrait is the vertical one. V0 is the control -- P1 exactly as it ships.
 * V1 adds one shared vertical scale, applied in the PROJECTION rather than as a
 * scene-root scale: a non-uniform root scale would perturb normals and so would
 * change the frozen refraction, while an anamorphic projection cannot.
 * V2 additionally refits the portrait row geometry under V1's scale.
 *
 * `scaleY` is not eyeballed. Source forensics gives the Target's exact portrait
 * card height at any viewport (planeWidth / planeAspect, with planeWidth =
 * 0.72 * width), so the required multiplier is the ratio of that to what our
 * frozen geometry renders. See qa-v5/f27/portrait-vertical-models.json.
 */
export const PORTRAIT_VERTICAL_MODELS = ["v0", "v1", "v2"] as const;
export type PortraitVerticalModel = (typeof PORTRAIT_VERTICAL_MODELS)[number];

export const PORTRAIT_VERTICAL = {
  models: {
    /** Control: P1 exactly as it ships. */
    v0: { scaleY: 1, radiusY: null as number | null, cellH: null as number | null, restY0: null as number | null },
    /**
     * One shared vertical scale, nothing else.
     *
     * 1.03883 is the median of the required ratio over the five training
     * viewports, measured with the gate's own detector against a five-frame
     * Target consensus. An entirely independent route agrees: source forensics
     * gives the Target's portrait card height exactly (0.72 * width / (4/3)),
     * and dividing that by what our frozen geometry renders gives 1.03923 --
     * 0.04% away, from arithmetic rather than from pixels.
     */
    v1: { scaleY: 1.03883, radiusY: null as number | null, cellH: null as number | null, restY0: null as number | null },
    /**
     * V1 plus the portrait row origin.
     *
     * `restY0` is NOT fitted. The Target's rows sit at half-integer multiples of
     * cellH about the viewport centre, so the row origin is exactly -cellH/2.
     * The F2.5 joint fit landed on -200.99 instead, which pushes the centre
     * seam 9 world units off centre -- that is the centre-dark-band failure
     * 390x844 has carried since F2. radiusY and cellH keep V1's values, because
     * nothing in the evidence asks them to move.
     */
    v2: { scaleY: 1.03883, radiusY: -4707.6 as number | null, cellH: 419.95 as number | null,
          restY0: -209.975 as number | null },
  },
  model: "v1" as PortraitVerticalModel,
} as const;

/**
 * DIAGNOSTIC ONLY, default off.
 *
 * The Target's rows sit at half-integer multiples of cellH about the viewport
 * centre, so the row origin is exactly -cellH/2 in BOTH regimes. F2.5's joint
 * fit moved it to -200.99, and that 9-unit offset is why the viewport centre
 * misses the horizontal gutter at 667x375, 700x700 and 780x470.
 *
 * F2.7 authorises a portrait-only vertical change, so this is NOT shipped. It
 * exists as a runnable variant, `?landscapeRowOrigin=centred`, so the product
 * owner is deciding on measured evidence rather than on a claim.
 */
export const LANDSCAPE_ROW_ORIGINS = ["f25", "centred"] as const;
export type LandscapeRowOrigin = (typeof LANDSCAPE_ROW_ORIGINS)[number];

export function landscapeRowOrigin(search: string = location.search): LandscapeRowOrigin {
  const value = new URLSearchParams(search).get("landscapeRowOrigin");
  return (LANDSCAPE_ROW_ORIGINS as readonly string[]).includes(value ?? "")
    ? (value as LandscapeRowOrigin)
    : "f25";
}

export function portraitVerticalModel(search: string = location.search): PortraitVerticalModel {
  const value = new URLSearchParams(search).get("portraitVertical");
  return (PORTRAIT_VERTICAL_MODELS as readonly string[]).includes(value ?? "")
    ? (value as PortraitVerticalModel)
    : PORTRAIT_VERTICAL.model;
}

/**
 * Vertical projection multiplier. Landscape is untouched at every viewport and
 * under every model, so nothing that currently passes can move.
 */
export function verticalScaleY(
  width: number, height: number,
  version: CompositionVersion = "v1",
  model: PortraitVerticalModel = PORTRAIT_VERTICAL.model,
): number {
  if (version !== "v2" || !isPortrait(width, height)) return 1;
  return PORTRAIT_VERTICAL.models[model].scaleY;
}

/** Portrait row geometry override, non-null only under V2. */
export function verticalOverride(
  width: number, height: number,
  version: CompositionVersion = "v1",
  model: PortraitVerticalModel = PORTRAIT_VERTICAL.model,
  landscape: LandscapeRowOrigin = "f25",
): { radiusY: number; cellH: number; restY0: number } | undefined {
  if (version !== "v2") return undefined;
  if (!isPortrait(width, height)) {
    if (landscape !== "centred") return undefined;
    const p = compositionParams(COMPOSITION_V2.verticalMode, COMPOSITION_V2.portraitLaw);
    return { radiusY: p.radiusY, cellH: p.cellH, restY0: -p.cellH / 2 };
  }
  const m = PORTRAIT_VERTICAL.models[model];
  if (m.radiusY === null || m.cellH === null || m.restY0 === null) return undefined;
  return { radiusY: m.radiusY, cellH: m.cellH, restY0: m.restY0 };
}

export const PORTRAIT_LAWS = ["p0", "p1", "p2"] as const;
export type PortraitLaw = (typeof PORTRAIT_LAWS)[number];

export function portraitLaw(search: string = location.search): PortraitLaw {
  const value = new URLSearchParams(search).get("portraitLaw");
  return (PORTRAIT_LAWS as readonly string[]).includes(value ?? "")
    ? (value as PortraitLaw)
    : COMPOSITION_V2.portraitLaw;
}

/**
 * Effective parameters. `tangent` -- the shipping vertical mode -- takes them
 * from the selected portrait law, so scale and vertical stay the pair that was
 * validated together. `depth` keeps its own joint-fit set, since it exists only
 * as the comparison candidate.
 */
export function compositionParams(mode: VerticalMode, law: PortraitLaw = COMPOSITION_V2.portraitLaw) {
  return mode === "tangent" ? COMPOSITION_V2.portraitLaws[law] : COMPOSITION_V2.depth;
}

export function compositionVersion(search: string = location.search): CompositionVersion {
  const value = new URLSearchParams(search).get("composition");
  return (COMPOSITION_VERSIONS as readonly string[]).includes(value ?? "")
    ? (value as CompositionVersion)
    : "v1";
}

export function verticalMode(search: string = location.search): VerticalMode {
  const value = new URLSearchParams(search).get("verticalMode");
  return (VERTICAL_MODES as readonly string[]).includes(value ?? "")
    ? (value as VerticalMode)
    : COMPOSITION_V2.verticalMode;
}

export const RESPONSIVE = {
  /** Viewport the Foundation geometry was fitted at; S is 1 here by definition. */
  referenceWidth: 1440,
  landscapeGain: 1,
  portraitGain: 1.8975,
  /**
   * How a scale is realised. "camera" moves the camera along z and leaves the
   * focal length alone; "focal" scales the focal length and leaves the camera
   * where it is. The Target's own frames decided it: its gutter centres divided
   * by S are identical to 0.1 px from 960 to 2560 wide, which only a uniform
   * rescale produces.
   */
  mechanism: "focal" as "camera" | "focal",
  /** v1 rest offsets in world units, per orientation. Superseded in v2. */
  restOffset: {
    landscape: { x: 0, y: 0 },
    portrait: { x: 280.57, y: 0 },
  },
} as const;

export function compositionScale(
  width: number,
  height: number,
  version: CompositionVersion = "v1",
  mode: VerticalMode = COMPOSITION_V2.verticalMode,
  law: PortraitLaw = COMPOSITION_V2.portraitLaw,
): number {
  const w = Math.max(1, width);
  if (version === "v2" && isPortrait(width, height)) {
    const params = compositionParams(mode, law);
    const aspect = w / Math.max(1, height);
    const gain = params.portraitGainBase + params.portraitGainAspectSlope * (aspect - 0.5);
    return (gain * w) / RESPONSIVE.referenceWidth;
  }
  const gain = isPortrait(width, height) ? RESPONSIVE.portraitGain : RESPONSIVE.landscapeGain;
  return (gain * w) / RESPONSIVE.referenceWidth;
}

export function restOffset(
  width: number,
  height: number,
  version: CompositionVersion = "v1",
  mode: VerticalMode = COMPOSITION_V2.verticalMode,
  phase: PhaseModel = COMPOSITION_V2.phaseModel,
): { x: number; y: number } {
  if (version === "v2") {
    void mode;
    // rowOrigin: the phase is the parity of the Target's own pool row count,
    // derived from its coverage calculation. No threshold, nothing fitted.
    // aspect: the superseded F2.6 rule, kept for rollback and comparison.
    const half = phase === "rowOrigin"
      ? rowOriginHalfCellPhase(width, height)
      : isPortrait(width, height) || height < COMPOSITION_V2.restPhaseAspectThreshold * width;
    // y is 0 because the Target's initial scroll is 0: its scroll springs are
    // constructed at zero and nothing seeds them. There is no integer row
    // branch to unwrap, so originJ is 0 at every viewport.
    return { x: half ? GRID.cellW / 2 : 0, y: 0 };
  }
  return isPortrait(width, height) ? RESPONSIVE.restOffset.portrait : RESPONSIVE.restOffset.landscape;
}

/** Re-exported so runtime evidence can report what the phase law was told. */
export { targetLayout };

/**
 * Camera distance multiplier the render path applies. Under the "camera"
 * mechanism a scale of S means standing 1/S as far away; under "focal" the
 * camera does not move and the focal length carries the scale instead.
 */
export function viewZoom(width: number, height: number, version: CompositionVersion = "v1",
  mode: VerticalMode = COMPOSITION_V2.verticalMode,
  law: PortraitLaw = COMPOSITION_V2.portraitLaw) {
  const scale = compositionScale(width, height, version, mode, law);
  return RESPONSIVE.mechanism === "camera" ? 1 / scale : 1;
}

/** Effective focal length in pixels, after the responsive law. */
export function effectivePerspectivePx(width: number, height: number, version: CompositionVersion = "v1",
  mode: VerticalMode = COMPOSITION_V2.verticalMode,
  law: PortraitLaw = COMPOSITION_V2.portraitLaw) {
  const scale = compositionScale(width, height, version, mode, law);
  return RESPONSIVE.mechanism === "focal" ? CAMERA.perspectivePx * scale : CAMERA.perspectivePx;
}

/**
 * Void colour, calibrated by round trip rather than copied.
 *
 * The Target's gutter is a navy whose median over 161k void pixels is
 * (0, 3, 18). Setting that value literally renders as pure black: the clear
 * colour goes through the tone-mapped, sRGB-encoded output path, which crushes
 * anything that dark. 0x001025 is the input that comes out the other side as
 * exactly (0, 3, 18). See docs/v5/RESPONSIVE_SCALING.md.
 */
export const CLEAR_COLOR = 0x001025;

export type QualityLevel = "high" | "medium" | "low";
