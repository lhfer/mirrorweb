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

export const RESPONSIVE = {
  /** Viewport the Foundation geometry was fitted at; S is 1 here by definition. */
  referenceWidth: 1440,
  landscapeGain: 1,
  portraitGain: 1.8975,
  /**
   * How a scale is realised. "camera" moves the camera along z and leaves the
   * focal length alone; "focal" scales the focal length and leaves the camera
   * where it is. They agree to first order and differ in how fast an outer card
   * shrinks, which is what the fit was asked to decide.
   */
  mechanism: "focal" as "camera" | "focal",
  /**
   * Rest offset in world units, per regime.
   *
   * Landscape is zero: at 1440x900, 1366x768, 1920x1080 and 844x390 the local
   * gutters land on the Target's to within 1 px with no offset at all.
   *
   * Portrait is half a cell across. The Target's portrait composition has the
   * OPPOSITE brick parity to its landscape one -- a row that carries a centre
   * gutter in landscape carries a centre card in portrait -- and half a cell is
   * exactly what swaps it.
   */
  restOffset: {
    landscape: { x: 0, y: 0 },
    portrait: { x: 280.57, y: 0 },
  },
} as const;

export function restOffset(width: number, height: number): { x: number; y: number } {
  return isPortrait(width, height) ? RESPONSIVE.restOffset.portrait : RESPONSIVE.restOffset.landscape;
}

export function compositionScale(width: number, height: number): number {
  const gain = isPortrait(width, height) ? RESPONSIVE.portraitGain : RESPONSIVE.landscapeGain;
  return (gain * Math.max(1, width)) / RESPONSIVE.referenceWidth;
}

/**
 * Camera distance multiplier the render path applies. Under the "camera"
 * mechanism a scale of S means standing 1/S as far away; under "focal" the
 * camera does not move and the focal length carries the scale instead.
 */
export function viewZoom(width: number, height: number) {
  const scale = compositionScale(width, height);
  return RESPONSIVE.mechanism === "camera" ? 1 / scale : 1;
}

/** Effective focal length in pixels, after the responsive law. */
export function effectivePerspectivePx(width: number, height: number) {
  const scale = compositionScale(width, height);
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
