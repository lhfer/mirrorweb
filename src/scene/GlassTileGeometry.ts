import { ExtrudeGeometry, PlaneGeometry, Shape } from "three/webgpu";
import { TILE } from "../config";
import type { QualityLevel } from "../config";

function superellipse(width: number, height: number, n: number, segments: number): Shape {
  const a = width / 2;
  const b = height / 2;
  const shape = new Shape();
  for (let i = 0; i <= segments; i += 1) {
    const t = (i / segments) * Math.PI * 2;
    const ct = Math.cos(t);
    const st = Math.sin(t);
    const x = Math.sign(ct) * a * Math.abs(ct) ** (2 / n);
    const y = Math.sign(st) * b * Math.abs(st) ** (2 / n);
    if (i === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  }
  return shape;
}

export function createGlassTileGeometry(quality: QualityLevel): ExtrudeGeometry {
  const bevel = quality === "low" ? 4 : 8;
  const bevelSegments = quality === "high" ? TILE.bevelSegments : quality === "medium" ? 3 : 2;
  const segments = quality === "low" ? 32 : TILE.outlineSegments;
  const geometry = new ExtrudeGeometry(superellipse(TILE.width, TILE.height, TILE.superellipseN, segments), {
    depth: TILE.thickness - bevel * 2,
    bevelEnabled: true,
    bevelThickness: bevel,
    bevelSize: bevel,
    bevelSegments,
    curveSegments: 1,
  });
  geometry.center();
  geometry.computeVertexNormals();
  return geometry;
}

export function createContentGeometry(): PlaneGeometry {
  return new PlaneGeometry(TILE.width * 0.9, TILE.height * 0.9, 1, 1);
}
