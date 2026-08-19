import { BufferAttribute, BufferGeometry } from "three/webgpu";
import { TILE, type QualityLevel } from "../config";

function superellipsePoint(radius: number, theta: number, a: number, b: number, n: number) {
  const ct = Math.cos(theta);
  const st = Math.sin(theta);
  return {
    x: radius * Math.sign(ct) * a * Math.abs(ct) ** (2 / n),
    y: radius * Math.sign(st) * b * Math.abs(st) ** (2 / n),
  };
}

function frontZ(radius: number) {
  const plateau = 0.34;
  const half = TILE.thickness * 0.5;
  if (radius <= plateau) return half + TILE.frontBulge;
  const t = (radius - plateau) / (1 - plateau);
  return half + TILE.frontBulge * (1 - t) ** 1.45;
}

function backZ(radius: number) {
  return -TILE.thickness * 0.5 - TILE.backDish * (1 - radius * radius);
}

export function createConvexGlassGeometry(quality: QualityLevel): BufferGeometry {
  const rings = quality === "low" ? 10 : quality === "medium" ? 14 : 18;
  const segs = quality === "low" ? 48 : quality === "medium" ? 60 : 72;
  const a = TILE.width / 2;
  const b = TILE.height / 2;
  const n = TILE.superellipseN;
  const positions: number[] = [];
  const uvs: number[] = [];
  const uv1: number[] = [];
  const indices: number[] = [];

  const push = (x: number, y: number, z: number, rim: number) => {
    positions.push(x, y, z);
    uvs.push(x / TILE.width + 0.5, y / TILE.height + 0.5);
    const thick = (frontZ(rim) - backZ(rim)) / (TILE.thickness + TILE.frontBulge + TILE.backDish);
    uv1.push(rim, thick);
    return positions.length / 3 - 1;
  };

  const front: number[][] = [];
  const back: number[][] = [];
  front.push([push(0, 0, frontZ(0), 0)]);
  back.push([push(0, 0, backZ(0), 0)]);

  for (let ring = 1; ring <= rings; ring += 1) {
    const radius = ring / rings;
    const frontRing: number[] = [];
    const backRing: number[] = [];
    for (let s = 0; s < segs; s += 1) {
      const theta = (s / segs) * Math.PI * 2;
      const p = superellipsePoint(radius, theta, a, b, n);
      frontRing.push(push(p.x, p.y, frontZ(radius), radius));
      backRing.push(push(p.x, p.y, backZ(radius), radius));
    }
    front.push(frontRing);
    back.push(backRing);
  }

  const stitch = (inner: number[], outer: number[], reverse = false) => {
    if (inner.length === 1) {
      for (let s = 0; s < segs; s += 1) {
        const a0 = inner[0];
        const b0 = outer[s];
        const c0 = outer[(s + 1) % segs];
        if (reverse) indices.push(a0, c0, b0);
        else indices.push(a0, b0, c0);
      }
      return;
    }
    for (let s = 0; s < segs; s += 1) {
      const i0 = inner[s];
      const i1 = inner[(s + 1) % segs];
      const o0 = outer[s];
      const o1 = outer[(s + 1) % segs];
      if (reverse) indices.push(i0, o1, o0, i0, i1, o1);
      else indices.push(i0, o0, o1, i0, o1, i1);
    }
  };

  for (let ring = 0; ring < rings; ring += 1) stitch(front[ring], front[ring + 1]);
  for (let ring = 0; ring < rings; ring += 1) stitch(back[ring], back[ring + 1], true);

  const frontRim = front[rings];
  const backRim = back[rings];
  for (let s = 0; s < segs; s += 1) {
    const f0 = frontRim[s];
    const f1 = frontRim[(s + 1) % segs];
    const b0 = backRim[s];
    const b1 = backRim[(s + 1) % segs];
    indices.push(f0, b0, b1, f0, b1, f1);
  }

  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(new Float32Array(positions), 3));
  geometry.setAttribute("uv", new BufferAttribute(new Float32Array(uvs), 2));
  geometry.setAttribute("uv1", new BufferAttribute(new Float32Array(uv1), 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}
