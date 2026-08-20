import { compositionParams, GRID, type CompositionVersion, type VerticalMode } from "../config";

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
};

export const V1_COMPOSITION: Composition = { version: "v1", verticalMode: "depth" };

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
  const params = compositionParams(composition.verticalMode);
  const cellH = v2 ? params.cellH : GRID.cellH;
  const restY0 = v2 ? params.restY0 : GRID.restY0;
  const v = j * cellH + restY0 - scrollY;

  const r = GRID.radius;
  const theta = u / r;
  out.x = r * Math.sin(theta);
  out.z = r * (1 - Math.cos(theta));
  out.rotY = -theta;

  const radiusY = v2 ? params.radiusY : 0;
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
