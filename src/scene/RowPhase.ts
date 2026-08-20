/**
 * Initial row phase, derived rather than fitted.
 *
 * F2.7's read-only source forensics pass recovered the Target's own layout
 * initialisation. Two facts settle the phase question that F2.5 and F2.6 kept
 * trying to fit:
 *
 * 1. The Target's initial scroll is exactly (0, 0) at every viewport. Its two
 *    scroll springs are constructed at zero and nothing seeds them. There is no
 *    viewport-dependent initial offset to recover, so there is no integer row
 *    branch to unwrap either -- originJ is 0 everywhere.
 *
 * 2. The visible brick phase is a property of the POOL, not of the viewport's
 *    aspect ratio. The Target sizes its pool from a coverage calculation and
 *    forces both counts EVEN. An even row count puts the viewport centre
 *    between two pool rows, and the pool row just below the centre is
 *    `rows / 2`. Odd pool rows carry the half-cell brick offset, so that row is
 *    card-centred exactly when `rows / 2` is odd.
 *
 * So the phase law has no free parameter and no threshold: compute the row
 * count the way the Target computes it, and read its parity. The aspect rule it
 * replaces scored 35 of 39 with a known-fragile boundary 0.01 away from 16:9.
 *
 * The constants below are the Target's grid configuration, read from its
 * shipped bundle. They describe the Target's own pool sizing and are used here
 * ONLY to derive a parity. Our pool stays 9x9 and is not resized by any of it.
 *
 * See docs/v5/TARGET_RESPONSIVE_SOURCE_FORENSICS.md for the bundle URL and hash.
 */

export const TARGET_GRID = {
  perspective: 1200,
  sphereRadius: 5000,
  planeAspect: 4 / 3,
  planeWidthRatio: 0.38,
  planeWidthRatioPortrait: 0.72,
  gapRatio: 0.045,
  referenceWidth: 1728,
  coverageMargin: 1.15,
  minCols: 4,
  maxCols: 16,
  minRows: 4,
  maxRows: 16,
} as const;

/** Screen position of a card's near edge at arc distance `arc` along the sphere. */
function edgeAt(arc: number, half: number, persp: number, radius: number): number {
  const denom = persp + radius * (1 - Math.cos(arc / radius));
  return (radius * persp * Math.sin(arc / radius)) / denom - (half * persp) / denom;
}

/** Smallest arc length whose card edge still reaches `target` on screen. */
function arcToCover(target: number, half: number, persp: number, radius: number): number {
  const horizon = radius * Math.acos(radius / (persp + radius));
  if (edgeAt(horizon, half, persp, radius) < target) return horizon;
  let lo = 0;
  let hi = horizon;
  for (let i = 0; i < 24; i += 1) {
    const mid = (lo + hi) * 0.5;
    if (edgeAt(mid, half, persp, radius) < target) lo = mid;
    else hi = mid;
  }
  return hi;
}

/** Clamp into range and force EVEN, which is what centres the viewport on a seam. */
function forceEven(value: number, lo: number, hi: number): number {
  const n = Math.min(hi, Math.max(lo, Math.ceil(value)));
  if (n % 2 === 0) return n;
  if (n + 1 <= hi) return n + 1;
  if (n - 1 >= lo) return n - 1;
  return n;
}

export type TargetLayout = {
  cols: number;
  rows: number;
  perspective: number;
  sphereRadius: number;
  planeWidth: number;
  planeHeight: number;
  cellW: number;
  cellH: number;
  portrait: boolean;
};

/** The Target's layout for a viewport. A pure function of width and height. */
export function targetLayout(width: number, height: number): TargetLayout {
  const g = TARGET_GRID;
  const w = Math.max(width, 1);
  const h = Math.max(height, 1);
  const s = Math.max(w, h) / g.referenceWidth;
  const perspective = g.perspective * s;
  const sphereRadius = g.sphereRadius * s;
  const ratio = h > w ? g.planeWidthRatioPortrait : g.planeWidthRatio;
  const planeWidth = w * ratio;
  const planeHeight = planeWidth / g.planeAspect;
  const cellW = planeWidth * (1 + g.gapRatio);
  const cellH = planeHeight * (1 + g.gapRatio);
  const zoomZ = 0.1 * perspective;
  const coverX = 0.5 * w * g.coverageMargin + Math.tan(0.05) * perspective + zoomZ;
  const coverY = 0.5 * h * g.coverageMargin + Math.tan(0.05) * perspective + zoomZ;
  const cols = forceEven(
    (2 * arcToCover(coverX, 0.5 * planeWidth, perspective, sphereRadius)) / cellW + 4,
    g.minCols, g.maxCols,
  );
  const rows = forceEven(
    (2 * arcToCover(coverY, 0.5 * planeHeight, perspective, sphereRadius)) / cellH + 4,
    g.minRows, g.maxRows,
  );
  return { cols, rows, perspective, sphereRadius, planeWidth, planeHeight, cellW, cellH, portrait: h > w };
}

/**
 * Does the row just below the viewport centre carry the half-cell brick offset?
 *
 * Our own grid places a card at u = 0 on even rows and a gutter there on odd
 * rows, and `restY0 = -cellH / 2` puts row j = 1 just below the centre. So when
 * the Target's lower centre row is card-centred we have to shift by half a cell
 * to match it, and when it is not we must not.
 */
export function rowOriginHalfCellPhase(width: number, height: number): boolean {
  const rowBelowCentre = targetLayout(width, height).rows / 2;
  // Odd pool rows carry the brick offset, which with an EVEN column count moves
  // their cards from half-integer multiples of cellW onto integers -- a card on
  // the centre line instead of a gutter. Our own row below the centre is j = 0,
  // which is even and already card-centred, so we need the half-cell shift
  // exactly when the Target's lower row is NOT card-centred.
  return rowBelowCentre % 2 === 0;
}

/** Row bookkeeping, kept distinct on purpose. */
export function rowOrigin(width: number, height: number, scrollY: number, cellH: number) {
  const layout = targetLayout(width, height);
  const originJ = Math.round(scrollY / cellH);
  return {
    /** Where the recycling pool believes its origin row is. */
    recyclingOriginJ: originJ,
    /** The Target's initial scroll, which forensics shows is exactly zero. */
    initialScrollY: 0,
    /** Whatever is left after the integer row branch is removed. */
    residualPhaseY: scrollY - originJ * cellH,
    /** Pool row just below the viewport centre in the Target's own pool. */
    targetRows: layout.rows,
    targetCols: layout.cols,
    poolRowBelowCentre: layout.rows / 2,
    halfCellPhase: rowOriginHalfCellPhase(width, height),
  };
}
