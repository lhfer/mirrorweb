import { compositionParams, GRID, type CompositionVersion, type PortraitLaw, type VerticalMode } from "../config";

export type TilePose = {
  x: number;
  y: number;
  z: number;
  rotX: number;
  rotY: number;
};

/** Which composition a placement uses. v1 is the F2 candidate, kept reachable. */
export type Composition = {
  version: CompositionVersion;
  verticalMode: VerticalMode;
  portraitLaw?: PortraitLaw;
  /**
   * Portrait-only vertical override (F2.7 V2), resolved by the app at resize
   * time because it depends on the viewport and placement does not see one.
   * Undefined under V0 and V1, and in landscape under every model, so landscape
   * placement is bit-identical to before.
   */
  vertical?: { radiusY: number; cellH: number; restY0: number };
};

export const V1_COMPOSITION: Composition = { version: "v1", verticalMode: "depth" };

/**
 * Effective vertical cell pitch for a composition.
 *
 * Recycling has to use the SAME pitch as placement. v2 places rows on
 * `params.cellH` while the pool was still deriving its origin row from
 * `GRID.cellH`; the two differ by a few units, so far from the origin the pool
 * hands a slot the wrong row index, which shows up as a catalog jump and a
 * parity break. Both sides now read this.
 */
export function effectiveCellH(composition: Composition = V1_COMPOSITION): number {
  if (composition.version !== "v2") return GRID.cellH;
  return composition.vertical?.cellH
    ?? compositionParams(composition.verticalMode, composition.portraitLaw).cellH;
}

const _pose: TilePose = { x: 0, y: 0, z: 0, rotX: 0, rotY: 0 };

export function brickColumn(i: number, j: number): number {
  const odd = ((j % 2) + 2) % 2;
  return i + (odd === 1 ? 0.5 : 0);
}

/**
 * Place one card.
 *
 * Horizontal: a vertical-axis cylinder. +Z is toward the camera and the radius
 * is negative, so the centre column is nearest and outer columns recede. This
 * is the accepted V5 Foundation geometry and F2.5 does not touch it.
 *
 * Vertical (v2 only): the same EXACT cosine law on the other axis, not a
 * second-order approximation of it. `depth` moves a row back as it gets further
 * from the axis; `tangent` additionally tips the card to lie along the surface.
 */
export function placeTile(
  i: number,
  j: number,
  scrollX: number,
  scrollY: number,
  out: TilePose = _pose,
  composition: Composition = V1_COMPOSITION,
): TilePose {
  const u = brickColumn(i, j) * GRID.cellW - scrollX;
  const v2 = composition.version === "v2";
  const params = compositionParams(composition.verticalMode, composition.portraitLaw);
  const over = v2 ? composition.vertical : undefined;
  const cellH = v2 ? (over?.cellH ?? params.cellH) : GRID.cellH;
  const restY0 = v2 ? (over?.restY0 ?? params.restY0) : GRID.restY0;
  const v = j * cellH + restY0 - scrollY;

  const r = GRID.radius;
  const theta = u / r;
  out.x = r * Math.sin(theta);
  out.z = r * (1 - Math.cos(theta));
  out.rotY = -theta;

  const radiusY = v2 ? (over?.radiusY ?? params.radiusY) : 0;
  out.y = v;
  if (radiusY) {
    // Exact cosine DEPTH law: a row recedes with its vertical distance from the
    // axis, and keeps its spacing. Rows are not re-parameterised onto an arc --
    // that would pull them toward the horizon and close the gutters, which the
    // Target does not do. The depth term is the exact cosine, not its
    // second-order approximation.
    const phi = v / radiusY;
    out.z += radiusY * (1 - Math.cos(phi));
    // Surface slope is dz/dv = sin(phi), so the tangent angle is atan of it.
    out.rotX = composition.verticalMode === "tangent" ? Math.atan(Math.sin(phi)) : 0;
  } else {
    out.rotX = 0;
  }
  return out;
}
