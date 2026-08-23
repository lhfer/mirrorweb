import CONTRACT from "../../config/target-layout-source-v2.json";

/**
 * The Target's layout, computed the way the Target computes it.
 *
 * Every constant comes from `config/target-layout-source-v2.json`, which is the
 * single source contract. There is no second copy here and no fitted number
 * anywhere in this file: if a value disagrees with a Target frame, this file is
 * wrong, not the frame.
 *
 * `npm run v5:target-layout-source` checks that this module, the Python model
 * and the live Target DOM all agree, and fails if the Target bundle hash moves.
 */

export const SOURCE_CONTRACT = CONTRACT;
export const TARGET_GRID = CONTRACT.grid;
export const TARGET_CAMERA = CONTRACT.camera;

/** Reference plane width, i.e. the plane the Target's own `cardScale` is 1 at. */
export const REFERENCE_PLANE_WIDTH = TARGET_GRID.referenceWidth * TARGET_GRID.planeWidthRatio;

/**
 * Everything downstream needs about one viewport, computed once per resize.
 *
 * Renderer, grid, foundation overlay, MediaFit and the QA hooks all consume THIS
 * object. None of them recomputes any of it -- that is the point. Two consumers
 * deriving the same quantity independently is how the old path ended up with a
 * reported scale that did not match the camera.
 */
export type SourceExactLayoutFrame = {
  viewport: [number, number];
  perspective: number;
  sphereRadius: number;
  planeWidth: number;
  planeHeight: number;
  cellW: number;
  cellH: number;
  cols: number;
  rows: number;
  periodX: number;
  periodY: number;
  portrait: boolean;
  /** Uniform scale from the reference card to this viewport's card. */
  cardScale: number;
  activeSlotCount: number;
  bundleHash: string;
  layoutVersion: string;
};

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

/** Clamp into range and force EVEN. Even counts put the viewport centre on a seam. */
function forceEven(value: number, lo: number, hi: number): number {
  const n = Math.min(hi, Math.max(lo, Math.ceil(value)));
  if (n % 2 === 0) return n;
  if (n + 1 <= hi) return n + 1;
  if (n - 1 >= lo) return n - 1;
  return n;
}

export function sourceExactLayout(width: number, height: number): SourceExactLayoutFrame {
  const g = TARGET_GRID;
  const w = Math.max(width, 1);
  const h = Math.max(height, 1);
  const s = Math.max(w, h) / g.referenceWidth;
  const perspective = g.perspective * s;
  const sphereRadius = g.sphereRadius * s;
  const portrait = h > w;
  const planeWidth = w * (portrait ? g.planeWidthRatioPortrait : g.planeWidthRatio);
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
  return {
    viewport: [w, h],
    perspective, sphereRadius, planeWidth, planeHeight, cellW, cellH, cols, rows,
    periodX: cols * cellW,
    periodY: rows * cellH,
    portrait,
    cardScale: planeWidth / REFERENCE_PLANE_WIDTH,
    activeSlotCount: cols * rows,
    bundleHash: CONTRACT.target.appBundleSha256,
    layoutVersion: CONTRACT.layoutVersion,
  };
}

/** Symmetric modulo: the Target's own infinite-grid wrap, into [-P/2, P/2). */
export function wrap(value: number, period: number): number {
  const half = 0.5 * period;
  return ((value + half) % period + period) % period - half;
}

export type SlotPose = {
  x: number; y: number; z: number;
  /** Unit normal on the sphere; the card's local +Z is rotated onto it. */
  nx: number; ny: number; nz: number;
  xArc: number; yArc: number;
  poolRow: number; poolCol: number;
};

/**
 * Where one pool slot sits, exactly as the Target places it.
 *
 * ONE sphere: both axes share `sphereRadius`, x carries the `cos(thetaY)`
 * convergence toward the poles and y is `sin(thetaY)`, not arc length. The old
 * path's vertical-axis cylinder plus a separate `radiusY` is not an
 * approximation of this -- it is a different surface.
 *
 * The half-cell brick offset is a property of the POOL ROW. Nothing else shifts
 * the grid: there is no rest offset and no phase rule on this path, because an
 * even column count already puts a seam on the centre line for even rows.
 */
export function placeSourceExactSlot(
  slotIndex: number, scrollX: number, scrollY: number, frame: SourceExactLayoutFrame,
  out: SlotPose = { x: 0, y: 0, z: 0, nx: 0, ny: 0, nz: 1, xArc: 0, yArc: 0, poolRow: 0, poolCol: 0 },
): SlotPose {
  const { cols, rows, cellW, cellH, sphereRadius: R } = frame;
  const poolRow = Math.floor(slotIndex / cols);
  const poolCol = slotIndex % cols;
  const brick = (poolRow % 2) * cellW * 0.5;
  const xArc = wrap((poolCol - (cols - 1) / 2) * cellW + scrollX + brick, frame.periodX);
  const yArc = wrap(-(poolRow - (rows - 1) / 2) * cellH - scrollY, frame.periodY);
  const tx = xArc / R;
  const ty = yArc / R;
  const cy = Math.cos(ty);
  out.nx = Math.sin(tx) * cy;
  out.ny = Math.sin(ty);
  out.nz = Math.cos(tx) * cy;
  out.x = out.nx * R;
  out.y = out.ny * R;
  out.z = out.nz * R - R;
  out.xArc = xArc;
  out.yArc = yArc;
  out.poolRow = poolRow;
  out.poolCol = poolCol;
  return out;
}

/** ILG code for a pool slot. The Target binds its label to the slot, not the cell. */
export function slotCode(slotIndex: number): number {
  return slotIndex + 1;
}
