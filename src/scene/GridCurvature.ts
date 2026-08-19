import { GRID } from "../config";

export type TilePose = {
  x: number;
  y: number;
  z: number;
  rotX: number;
  rotY: number;
};

const _pose: TilePose = { x: 0, y: 0, z: 0, rotX: 0, rotY: 0 };

export function brickColumn(i: number, j: number): number {
  const odd = ((j % 2) + 2) % 2;
  return i + (odd === 1 ? 0.5 : 0);
}

/** Vertical-axis cylinder. +Z is toward the camera, so outer columns sit closer. */
export function placeTile(i: number, j: number, scrollX: number, scrollY: number, out: TilePose = _pose): TilePose {
  const u = brickColumn(i, j) * GRID.cellW - scrollX;
  const v = j * GRID.cellH + GRID.restY0 - scrollY;
  const r = GRID.radius;
  const theta = u / r;
  out.x = r * Math.sin(theta);
  out.y = v;
  out.z = r * (1 - Math.cos(theta));
  out.rotY = -theta;
  out.rotX = 0;
  return out;
}
