import { Matrix4, Vector3, type Object3D, type PerspectiveCamera } from "three/webgpu";

/**
 * The Target's CSS3D label coverage culling, as read out of its bundle.
 *
 * Every formula here is a byte-anchored source read --
 * `qa-v5/culling/target-culling-source.json` carries the offsets and the
 * verbatim minified text. Nothing in this file was derived from a visible
 * count.
 *
 * The Target's test, verbatim in structure:
 *
 *   1. project the four CARD CORNERS (a unit quad carried by the mesh world
 *      matrix, whose scale is the plane size) through a DEDICATED camera that
 *      sits at the pointer orbit WITHOUT the velocity dolly;
 *   2. a corner with NDC z < -1 or z > 1 is skipped; zero surviving corners
 *      rejects the card;
 *   3. the screen AABB over the surviving corners must have area STRICTLY
 *      greater than 1 px^2;
 *   4. `draw`: the AABB must overlap the viewport expanded by exactly 64 CSS
 *      px on every side, strictly positive extent on both axes -- no area
 *      fraction;
 *   5. `interactive`: strictly positive overlap with the UNexpanded viewport
 *      AND overlapArea / aabbArea >= 0.5. In the shipped Target this flag is
 *      published to a MotionValue that nothing reads.
 *
 * There is NO JS backface test in the Target's culling: backface hiding is
 * inline `backface-visibility: hidden` CSS, applied at paint. The dot-product
 * below is therefore a QA DIAGNOSTIC only and never feeds the verdict.
 */

/** The margin, exactly as the literal appears in the bundle: 64 CSS px. */
export const COVERAGE_MARGIN_PX = 64;

/**
 * Unit quad corners in the Target's own order: BL, BR, TR, TL (local y-up).
 * The mesh/world matrix carries them onto the card plane.
 */
const CORNERS = [
  new Vector3(-0.5, -0.5, 0),
  new Vector3(0.5, -0.5, 0),
  new Vector3(0.5, 0.5, 0),
  new Vector3(-0.5, 0.5, 0),
];

export type LabelCullingVerdict = {
  slotIndex: number;
  /**
   * QA diagnostic: does the card face the coverage camera? Never part of the
   * verdict -- the Target hides backfaces with CSS, not JS.
   */
  backfaceVisible: boolean;
  /** The Target's `draw`: the only thing that decides DOM visibility. */
  coverageVisible: boolean;
  /** The Target's `interactive`: strict viewport + the half-area rule. */
  strictViewportVisible: boolean;
  /** Projected corner positions in CSS px; null where the NDC z test skipped. */
  projectedQuad: Array<[number, number] | null>;
  /** [minX, minY, maxX, maxY] over the surviving corners; null when none. */
  projectedAabbPx: [number, number, number, number] | null;
  /** AABB area in px^2. 0 when no corner survived. */
  projectedAreaPx: number;
  /** AABB overlap area with the STRICT viewport -- the half-rule numerator. */
  overlapAreaPx: number;
  marginPx: number;
  rejectionReason:
    | null
    | "inactive"
    | "zeroCornersInNdcZ"
    | "aabbAreaAtMostOnePx"
    | "outsideMarginViewport";
};

type CullableSlot = { group: Object3D; slotIndex: number; active?: boolean };

const _m = new Matrix4();
const _s = new Vector3();
const _v = new Vector3();
const _dir = new Vector3();
const _centre = new Vector3();
const _toCam = new Vector3();

function rejected(
  slotIndex: number,
  reason: NonNullable<LabelCullingVerdict["rejectionReason"]>,
  quad: Array<[number, number] | null>,
  aabb: [number, number, number, number] | null,
  area: number,
  overlap: number,
  backface: boolean,
): LabelCullingVerdict {
  return {
    slotIndex,
    backfaceVisible: backface,
    coverageVisible: false,
    strictViewportVisible: false,
    projectedQuad: quad,
    projectedAabbPx: aabb,
    projectedAreaPx: area,
    overlapAreaPx: overlap,
    marginPx: COVERAGE_MARGIN_PX,
    rejectionReason: reason,
  };
}

/**
 * One slot's verdict. `width`/`height` are CSS px -- the same
 * `window.innerWidth/Height` the Target's own test reads.
 *
 * The float operation ORDER matches the bundle's expressions term for term,
 * so a verdict here and a verdict replayed offline from the same inputs agree
 * to the bit, not merely to a tolerance.
 */
export function cullSlot(
  slot: CullableSlot,
  camera: PerspectiveCamera,
  width: number,
  height: number,
  planeWidth: number,
  planeHeight: number,
): LabelCullingVerdict {
  if (slot.active === false) {
    return rejected(slot.slotIndex, "inactive", [null, null, null, null], null, 0, 0, false);
  }

  // The Target refreshes the mesh world matrix inside the test.
  slot.group.updateWorldMatrix(true, false);
  // matrixWorld * scale(planeW, planeH, 1): our slot group's scale is 1 and
  // the Target's mesh scale IS the plane size, so post-multiplying the scale
  // reproduces its matrix exactly (T * R * S both ways).
  _m.copy(slot.group.matrixWorld).scale(_s.set(planeWidth, planeHeight, 1));

  // QA diagnostic only. Centre and normal through the same matrices the
  // verdict uses.
  slot.group.getWorldDirection(_dir);
  _centre.setFromMatrixPosition(slot.group.matrixWorld);
  _toCam.subVectors(camera.position, _centre);
  const backface = _toCam.dot(_dir) > 0;

  const quad: Array<[number, number] | null> = [null, null, null, null];
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let survived = 0;
  for (let k = 0; k < CORNERS.length; k += 1) {
    _v.copy(CORNERS[k]).applyMatrix4(_m).project(camera);
    // NDC z: skipped, not clamped; exactly -1 and 1 survive.
    if (_v.z < -1 || _v.z > 1) continue;
    const px = (0.5 * _v.x + 0.5) * width;
    const py = (-(0.5 * _v.y) + 0.5) * height;
    quad[k] = [px, py];
    minX = Math.min(minX, px);
    maxX = Math.max(maxX, px);
    minY = Math.min(minY, py);
    maxY = Math.max(maxY, py);
    survived += 1;
  }

  if (survived === 0) {
    return rejected(slot.slotIndex, "zeroCornersInNdcZ", quad, null, 0, 0, backface);
  }

  const aabb: [number, number, number, number] = [minX, minY, maxX, maxY];
  const area = (maxX - minX) * (maxY - minY);
  if (area <= 1) {
    return rejected(slot.slotIndex, "aabbAreaAtMostOnePx", quad, aabb, area, 0, backface);
  }

  const mu = Math.min(maxX, width + 64) - Math.max(minX, -64);
  const mc = Math.min(maxY, height + 64) - Math.max(minY, -64);
  const su = Math.min(maxX, width) - Math.max(minX, 0);
  const sc = Math.min(maxY, height) - Math.max(minY, 0);
  const draw = mu > 0 && mc > 0;
  const overlap = su > 0 && sc > 0 ? su * sc : 0;
  const interactive = su > 0 && sc > 0 && (su * sc) / area >= 0.5;

  if (!draw) {
    return rejected(slot.slotIndex, "outsideMarginViewport", quad, aabb, area, overlap, backface);
  }
  return {
    slotIndex: slot.slotIndex,
    backfaceVisible: backface,
    coverageVisible: true,
    strictViewportVisible: interactive,
    projectedQuad: quad,
    projectedAabbPx: aabb,
    projectedAreaPx: area,
    overlapAreaPx: overlap,
    marginPx: COVERAGE_MARGIN_PX,
    rejectionReason: null,
  };
}

/**
 * All slots in one pass, reusing one verdict array to keep the per-frame path
 * allocation-light. The caller must not hold references across frames.
 */
export class SourceExactLabelCulling {
  private verdicts: LabelCullingVerdict[] = [];

  compute(
    slots: readonly CullableSlot[],
    camera: PerspectiveCamera,
    width: number,
    height: number,
    planeWidth: number,
    planeHeight: number,
  ): LabelCullingVerdict[] {
    this.verdicts.length = slots.length;
    for (let n = 0; n < slots.length; n += 1) {
      this.verdicts[n] = cullSlot(slots[n], camera, width, height, planeWidth, planeHeight);
    }
    return this.verdicts;
  }
}
