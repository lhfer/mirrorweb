import { BufferAttribute, BufferGeometry, Vector3 } from "three/webgpu";
import {
  V4_OPTICS_CONFIG,
  getV4QualityPreset,
  type V4GeometryConfig,
  type V4QualityLevel,
} from "../v4/OpticsConfigV4";

type Point = { x: number; y: number; z: number };

const EPSILON = 1e-6;

function clamp01(value: number) {
  return Math.max(0, Math.min(1, value));
}

function smootherstep(value: number) {
  const t = clamp01(value);
  return t * t * t * (t * (t * 6 - 15) + 10);
}

function superellipseBoundary(theta: number, config: V4GeometryConfig) {
  const a = config.width * 0.5;
  const b = config.height * 0.5;
  const ct = Math.cos(theta);
  const st = Math.sin(theta);
  return {
    x: Math.sign(ct) * a * Math.abs(ct) ** (2 / config.superellipseN),
    y: Math.sign(st) * b * Math.abs(st) ** (2 / config.superellipseN),
  };
}

/** First-order Euclidean distance to the actual implicit superellipse boundary. */
function edgeDistance(x: number, y: number, config: V4GeometryConfig) {
  const a = config.width * 0.5;
  const b = config.height * 0.5;
  const n = config.superellipseN;
  const ax = Math.abs(x / a);
  const ay = Math.abs(y / b);
  const sum = ax ** n + ay ** n;
  if (sum < 1e-10) return Math.min(a, b);
  const rho = sum ** (1 / n);
  const gradientScale = sum ** (1 / n - 1);
  const gx = Math.sign(x) * gradientScale * ax ** (n - 1) / a;
  const gy = Math.sign(y) * gradientScale * ay ** (n - 1) / b;
  const gradientLength = Math.hypot(gx, gy);
  if (gradientLength < EPSILON) return Math.min(a, b);
  return Math.max(0, (1 - rho) / gradientLength);
}

function frontZ(distance: number, config: V4GeometryConfig) {
  if (config.frontProfile === "monotonic-arc") {
    // One arc from the clear centre to the silhouette. Its slope is zero where
    // it leaves the centre face and rises without ever turning back, so the
    // view-space normal — and every refraction term built on it — ramps across
    // the whole band instead of bending, un-bending and then creasing.
    // The arc reaches the silhouette at exactly centerFrontZ - edgeArcDropPx,
    // which is where the two-piece profile ended too, so the card outline and
    // the sidewall band are unchanged.
    const u = clamp01(1 - distance / Math.max(EPSILON, config.edgeArcPx));
    return config.centerFrontZ - config.edgeArcDropPx * (1 - Math.sqrt(1 - u * u));
  }

  const half = config.baseThickness * 0.5;
  // How far the front surface sags between the clear centre and the crown at
  // the start of the rollover. This is the slope the view-space normal — and
  // therefore every refraction term — is built on, so it is an explicit config
  // value rather than a constant buried in the profile.
  const crownZ = config.centerFrontZ - config.shoulderDropPx;
  if (distance >= config.shoulderOuterPx) return config.centerFrontZ;
  if (distance >= config.rolloverInsetPx) {
    const t = (config.shoulderOuterPx - distance)
      / Math.max(EPSILON, config.shoulderOuterPx - config.rolloverInsetPx);
    return config.centerFrontZ + (crownZ - config.centerFrontZ) * smootherstep(t);
  }

  // A quarter-ellipse rollover: horizontal tangent at the shoulder and a
  // vertical tangent at the sidewall entrance.
  const sine = clamp01(1 - distance / Math.max(EPSILON, config.rolloverInsetPx));
  const cosine = Math.sqrt(Math.max(0, 1 - sine * sine));
  return crownZ - config.rolloverDepthPx * (1 - cosine);
}

function backZ(rho: number, config: V4GeometryConfig) {
  const centerWeight = (1 - rho * rho) ** 2;
  return -config.baseThickness * 0.5 - config.backDishPx * centerWeight;
}

function profileCurvature(distance: number, config: V4GeometryConfig) {
  const h = 0.6;
  const d = Math.max(h, distance);
  const z0 = frontZ(Math.max(0, d - h), config);
  const z1 = frontZ(d, config);
  const z2 = frontZ(d + h, config);
  const first = (z2 - z0) / (2 * h);
  const second = (z2 - 2 * z1 + z0) / (h * h);
  const curvature = Math.abs(second) / Math.max(EPSILON, (1 + first * first) ** 1.5);
  return clamp01(curvature * 18);
}

function frontPoint(rho: number, theta: number, config: V4GeometryConfig): Point {
  const boundary = superellipseBoundary(theta, config);
  const x = boundary.x * rho;
  const y = boundary.y * rho;
  return { x, y, z: frontZ(edgeDistance(x, y, config), config) };
}

function backPoint(rho: number, theta: number, config: V4GeometryConfig): Point {
  const boundary = superellipseBoundary(theta, config);
  return { x: boundary.x * rho, y: boundary.y * rho, z: backZ(rho, config) };
}

function subtract(a: Point, b: Point) {
  return new Vector3(a.x - b.x, a.y - b.y, a.z - b.z);
}

function frontNormal(rho: number, theta: number, config: V4GeometryConfig) {
  if (rho < 1e-4) return new Vector3(0, 0, 1);
  const dr = 0.0015;
  const dt = 0.0015;
  const radial = subtract(
    frontPoint(Math.min(1, rho + dr), theta, config),
    frontPoint(Math.max(0, rho - dr), theta, config),
  );
  const tangent = subtract(
    frontPoint(rho, theta + dt, config),
    frontPoint(rho, theta - dt, config),
  );
  const normal = radial.cross(tangent).normalize();
  if (normal.z < 0) normal.multiplyScalar(-1);
  return normal;
}

function backNormal(rho: number, theta: number, config: V4GeometryConfig) {
  if (rho < 1e-4) return new Vector3(0, 0, -1);
  const dr = 0.0015;
  const dt = 0.0015;
  const radial = subtract(
    backPoint(Math.min(1, rho + dr), theta, config),
    backPoint(Math.max(0, rho - dr), theta, config),
  );
  const tangent = subtract(
    backPoint(rho, theta + dt, config),
    backPoint(rho, theta - dt, config),
  );
  const normal = tangent.cross(radial).normalize();
  if (normal.z > 0) normal.multiplyScalar(-1);
  return normal;
}

function sideNormal(theta: number, config: V4GeometryConfig) {
  const point = superellipseBoundary(theta, config);
  const a = config.width * 0.5;
  const b = config.height * 0.5;
  const n = config.superellipseN;
  const gx = Math.sign(point.x) * Math.abs(point.x / a) ** (n - 1) / a;
  const gy = Math.sign(point.y) * Math.abs(point.y / b) ** (n - 1) / b;
  return new Vector3(gx, gy, 0).normalize();
}

function radialStations(count: number) {
  const values: number[] = [];
  for (let i = 1; i <= count; i += 1) {
    const t = i / count;
    values.push(1 - (1 - t) ** 1.65);
  }
  return values;
}

export function createConvexGlassGeometryV4(
  quality: V4QualityLevel = "high",
  overrides: Partial<V4GeometryConfig> = {},
): BufferGeometry {
  const config: V4GeometryConfig = { ...V4_OPTICS_CONFIG.geometry, ...overrides };
  const preset = getV4QualityPreset(quality);
  const radial = radialStations(preset.radialSegments);
  const segs = preset.outlineSegments;
  const positions: number[] = [];
  const normals: number[] = [];
  const uvs: number[] = [];
  const edgeDistances: number[] = [];
  const shoulders: number[] = [];
  const lensRims: number[] = [];
  const sidewalls: number[] = [];
  const thicknesses: number[] = [];
  const curvatures: number[] = [];
  const indices: number[] = [];

  const push = (
    point: Point,
    normal: Vector3,
    distance: number,
    shoulder: number,
    lensRim: number,
    sidewall: number,
    thickness: number,
    curvature: number,
  ) => {
    positions.push(point.x, point.y, point.z);
    normals.push(normal.x, normal.y, normal.z);
    uvs.push(point.x / config.width + 0.5, point.y / config.height + 0.5);
    edgeDistances.push(distance);
    shoulders.push(shoulder);
    lensRims.push(lensRim);
    sidewalls.push(sidewall);
    thicknesses.push(thickness);
    curvatures.push(curvature);
    return positions.length / 3 - 1;
  };

  const opticalWeights = (distance: number) => {
    const edgeWeight = 1 - smootherstep(distance / config.shoulderOuterPx);
    const rimWeight = 1 - smootherstep(distance / config.lensRimWidthPx);
    return { shoulder: edgeWeight * (1 - rimWeight), rim: rimWeight };
  };

  const stitch = (inner: number[], outer: number[], reverse = false) => {
    if (inner.length === 1) {
      for (let s = 0; s < segs; s += 1) {
        const center = inner[0];
        const b = outer[s];
        const c = outer[(s + 1) % segs];
        if (reverse) indices.push(center, c, b);
        else indices.push(center, b, c);
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

  const front: number[][] = [];
  const centerDistance = Math.min(config.width, config.height) * 0.5;
  front.push([
    push(
      { x: 0, y: 0, z: config.centerFrontZ },
      new Vector3(0, 0, 1),
      centerDistance,
      0,
      0,
      0,
      config.centerFrontZ - backZ(0, config),
      0,
    ),
  ]);

  for (const rho of radial) {
    const ring: number[] = [];
    for (let s = 0; s < segs; s += 1) {
      const theta = s / segs * Math.PI * 2;
      const point = frontPoint(rho, theta, config);
      const distance = edgeDistance(point.x, point.y, config);
      const weights = opticalWeights(distance);
      ring.push(push(
        point,
        frontNormal(rho, theta, config),
        distance,
        weights.shoulder,
        weights.rim,
        0,
        point.z - backZ(rho, config),
        Math.max(profileCurvature(distance, config), weights.rim * 0.35),
      ));
    }
    front.push(ring);
  }

  for (let ring = 0; ring < front.length - 1; ring += 1) {
    stitch(front[ring], front[ring + 1]);
  }

  const boundaryFrontZ = frontZ(0, config);
  const boundaryBackZ = backZ(1, config);
  const boundaryThickness = boundaryFrontZ - boundaryBackZ;
  const side: number[][] = [front[front.length - 1]];
  for (let row = 1; row <= preset.sidewallSegments; row += 1) {
    const t = row / preset.sidewallSegments;
    const z = boundaryFrontZ + (boundaryBackZ - boundaryFrontZ) * t;
    const ring: number[] = [];
    for (let s = 0; s < segs; s += 1) {
      const theta = s / segs * Math.PI * 2;
      const boundary = superellipseBoundary(theta, config);
      ring.push(push(
        { x: boundary.x, y: boundary.y, z },
        sideNormal(theta, config),
        0,
        0,
        0,
        smootherstep(t),
        boundaryThickness,
        0,
      ));
    }
    stitch(side[side.length - 1], ring);
    side.push(ring);
  }

  const back: number[][] = [];
  back.push([
    push(
      { x: 0, y: 0, z: backZ(0, config) },
      new Vector3(0, 0, -1),
      centerDistance,
      0,
      0,
      0,
      config.centerFrontZ - backZ(0, config),
      0,
    ),
  ]);
  for (let r = 0; r < radial.length - 1; r += 1) {
    const rho = radial[r];
    const ring: number[] = [];
    for (let s = 0; s < segs; s += 1) {
      const theta = s / segs * Math.PI * 2;
      const point = backPoint(rho, theta, config);
      const distance = edgeDistance(point.x, point.y, config);
      ring.push(push(
        point,
        backNormal(rho, theta, config),
        distance,
        0,
        0,
        0,
        frontZ(distance, config) - point.z,
        0,
      ));
    }
    back.push(ring);
  }
  back.push(side[side.length - 1]);
  for (let ring = 0; ring < back.length - 1; ring += 1) {
    stitch(back[ring], back[ring + 1], true);
  }

  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(new Float32Array(positions), 3));
  geometry.setAttribute("normal", new BufferAttribute(new Float32Array(normals), 3));
  geometry.setAttribute("uv", new BufferAttribute(new Float32Array(uvs), 2));
  geometry.setAttribute("aEdgeDistance", new BufferAttribute(new Float32Array(edgeDistances), 1));
  geometry.setAttribute("aShoulder", new BufferAttribute(new Float32Array(shoulders), 1));
  geometry.setAttribute("aLensRim", new BufferAttribute(new Float32Array(lensRims), 1));
  geometry.setAttribute("aSidewall", new BufferAttribute(new Float32Array(sidewalls), 1));
  geometry.setAttribute("aThickness", new BufferAttribute(new Float32Array(thicknesses), 1));
  geometry.setAttribute("aCurvature", new BufferAttribute(new Float32Array(curvatures), 1));
  geometry.setIndex(indices);
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();
  geometry.userData.opticsV4 = {
    version: "v4",
    quality,
    profile: "c1-superellipse-rollover",
    edgeDistance: "implicit-superellipse-gradient",
    attributes: ["aEdgeDistance", "aShoulder", "aLensRim", "aSidewall", "aThickness", "aCurvature"],
  };
  return geometry;
}
