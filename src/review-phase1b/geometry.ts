/**
 * Projective geometry helpers shared by Reviewer Mode and the Advanced
 * Inspector: unit-square -> card-quad homography, rectification of the target
 * card into a flat card plane, and the pixel measurements the optical-zone
 * ratios are defined against.
 *
 * Everything works on the verified target bitmap that is already in memory.
 * No pixels leave the page and no measurement is written anywhere by itself.
 */

export type Point = [number, number];
export type Quad = [Point, Point, Point, Point];

export interface Homography {
  a: number;
  b: number;
  c: number;
  d: number;
  e: number;
  f: number;
  g: number;
  h: number;
}

export interface CardMetrics {
  /** Mean top/bottom edge length in source pixels. */
  cardWidth: number;
  /** Mean left/right edge length in source pixels. */
  cardHeight: number;
  /** Shorter of the two; optical-zone ratios are defined against this. */
  minorAxis: number;
  aspect: number;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

function pixelQuad(quad: Quad, width: number, height: number): Quad {
  return quad.map(([x, y]) => [x * width, y * height]) as Quad;
}

/**
 * Heckbert's unit-square -> quadrilateral projective map. The unit square
 * corners (0,0) (1,0) (1,1) (0,1) map to TL, TR, BR, BL respectively, which is
 * the corner order the private annotation contract already enforces.
 */
export function unitSquareHomography(quad: Quad, width = 1, height = 1): Homography {
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = pixelQuad(quad, width, height);
  const dx1 = x1 - x2;
  const dx2 = x3 - x2;
  const dx3 = x0 - x1 + x2 - x3;
  const dy1 = y1 - y2;
  const dy2 = y3 - y2;
  const dy3 = y0 - y1 + y2 - y3;
  if (Math.abs(dx3) < 1e-12 && Math.abs(dy3) < 1e-12) {
    return { a: x1 - x0, b: x2 - x1, c: x0, d: y1 - y0, e: y2 - y1, f: y0, g: 0, h: 0 };
  }
  const denominator = dx1 * dy2 - dy1 * dx2;
  if (Math.abs(denominator) < 1e-12) {
    return { a: x1 - x0, b: x2 - x1, c: x0, d: y1 - y0, e: y2 - y1, f: y0, g: 0, h: 0 };
  }
  const g = (dx3 * dy2 - dy3 * dx2) / denominator;
  const h = (dx1 * dy3 - dy1 * dx3) / denominator;
  return {
    a: x1 - x0 + g * x1,
    b: x3 - x0 + h * x3,
    c: x0,
    d: y1 - y0 + g * y1,
    e: y3 - y0 + h * y3,
    f: y0,
    g,
    h,
  };
}

/** Maps a plane coordinate (u, v) in [0,1]^2 to its source-image position. */
export function planeToSource(homography: Homography, u: number, v: number): Point {
  const { a, b, c, d, e, f, g, h } = homography;
  const w = g * u + h * v + 1;
  const safe = Math.abs(w) < 1e-12 ? 1e-12 : w;
  return [(a * u + b * v + c) / safe, (d * u + e * v + f) / safe];
}

function distance(left: Point, right: Point): number {
  return Math.hypot(left[0] - right[0], left[1] - right[1]);
}

export function cardMetrics(quad: Quad, width: number, height: number): CardMetrics {
  const [tl, tr, br, bl] = pixelQuad(quad, width, height);
  const cardWidth = (distance(tl, tr) + distance(bl, br)) / 2;
  const cardHeight = (distance(tl, bl) + distance(tr, br)) / 2;
  const minorAxis = Math.min(cardWidth, cardHeight);
  return { cardWidth, cardHeight, minorAxis, aspect: cardHeight > 0 ? cardWidth / cardHeight : 1 };
}

export function quadBoundingBox(quad: Quad, width = 1, height = 1): BoundingBox {
  const points = pixelQuad(quad, width, height);
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  return { x: minX, y: minY, width: Math.max(...xs) - minX, height: Math.max(...ys) - minY };
}

export function quadCentroid(quad: Quad): Point {
  return [
    quad.reduce((sum, [x]) => sum + x, 0) / 4,
    quad.reduce((sum, [, y]) => sum + y, 0) / 4,
  ];
}

/** Shoelace area of a normalized quad, used for the coverage assertions. */
export function quadArea(quad: Quad, width = 1, height = 1): number {
  const points = pixelQuad(quad, width, height);
  let sum = 0;
  for (let index = 0; index < 4; index += 1) {
    const [x0, y0] = points[index];
    const [x1, y1] = points[(index + 1) % 4];
    sum += x0 * y1 - x1 * y0;
  }
  return Math.abs(sum / 2);
}

function sampleBilinear(
  source: Uint8ClampedArray,
  sourceWidth: number,
  sourceHeight: number,
  x: number,
  y: number,
  output: Uint8ClampedArray,
  offset: number,
): void {
  const clampedX = Math.min(Math.max(x, 0), sourceWidth - 1);
  const clampedY = Math.min(Math.max(y, 0), sourceHeight - 1);
  const x0 = Math.floor(clampedX);
  const y0 = Math.floor(clampedY);
  const x1 = Math.min(x0 + 1, sourceWidth - 1);
  const y1 = Math.min(y0 + 1, sourceHeight - 1);
  const fx = clampedX - x0;
  const fy = clampedY - y0;
  const topLeft = (y0 * sourceWidth + x0) * 4;
  const topRight = (y0 * sourceWidth + x1) * 4;
  const bottomLeft = (y1 * sourceWidth + x0) * 4;
  const bottomRight = (y1 * sourceWidth + x1) * 4;
  for (let channel = 0; channel < 3; channel += 1) {
    const top = source[topLeft + channel] + (source[topRight + channel] - source[topLeft + channel]) * fx;
    const bottom = source[bottomLeft + channel] + (source[bottomRight + channel] - source[bottomLeft + channel]) * fx;
    output[offset + channel] = top + (bottom - top) * fy;
  }
  output[offset + 3] = 255;
}

export interface RectifyOptions {
  /** Longest edge of the produced card plane, in pixels. */
  maxSize?: number;
  /** Extra margin outside the card, as a ratio of the card size. */
  margin?: number;
}

export interface RectifiedPlane {
  canvas: HTMLCanvasElement;
  width: number;
  height: number;
  /** Ratio of the plane occupied by the margin on each side. */
  margin: number;
  metrics: CardMetrics;
}

interface SourcePixels {
  data: Uint8ClampedArray;
  width: number;
  height: number;
}

const sourceCache = new WeakMap<CanvasImageSource, SourcePixels>();

function readSourcePixels(image: HTMLImageElement | HTMLCanvasElement): SourcePixels {
  const cached = sourceCache.get(image);
  if (cached) return cached;
  const width = image instanceof HTMLImageElement ? image.naturalWidth : image.width;
  const height = image instanceof HTMLImageElement ? image.naturalHeight : image.height;
  if (!width || !height) throw new Error("Target bitmap has no decoded pixels");
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("2D canvas is unavailable for rectification");
  context.drawImage(image, 0, 0);
  const pixels: SourcePixels = { data: context.getImageData(0, 0, width, height).data, width, height };
  sourceCache.set(image, pixels);
  return pixels;
}

/**
 * Renders the card quad as a flat, front-facing card plane.
 *
 * `margin` keeps a ring of surrounding frame visible so a reviewer can still
 * see whether the silhouette was placed slightly inside or outside the real
 * card edge. Plane coordinates therefore run from `-margin` to `1 + margin`.
 */
export function rectifyCardPlane(
  image: HTMLImageElement | HTMLCanvasElement,
  quad: Quad,
  options: RectifyOptions = {},
): RectifiedPlane {
  const maxSize = Math.max(64, Math.round(options.maxSize ?? 900));
  const margin = Math.min(0.4, Math.max(0, options.margin ?? 0.08));
  const source = readSourcePixels(image);
  const metrics = cardMetrics(quad, source.width, source.height);
  const aspect = metrics.aspect > 0 ? metrics.aspect : 1;
  const outerAspect = aspect;
  const width = aspect >= 1 ? maxSize : Math.max(64, Math.round(maxSize * outerAspect));
  const height = aspect >= 1 ? Math.max(64, Math.round(maxSize / outerAspect)) : maxSize;
  const homography = unitSquareHomography(quad, source.width, source.height);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("2D canvas is unavailable for rectification");
  const output = context.createImageData(width, height);
  const span = 1 + margin * 2;
  for (let py = 0; py < height; py += 1) {
    const v = ((py + 0.5) / height) * span - margin;
    for (let px = 0; px < width; px += 1) {
      const u = ((px + 0.5) / width) * span - margin;
      const [sx, sy] = planeToSource(homography, u, v);
      sampleBilinear(source.data, source.width, source.height, sx, sy, output.data, (py * width + px) * 4);
    }
  }
  context.putImageData(output, 0, 0);
  return { canvas, width, height, margin, metrics };
}

/**
 * Converts a plane coordinate in [0,1]^2 (card space) into a pixel position on
 * a rectified plane canvas that was produced with `margin`.
 */
export function cardToPlanePixel(
  plane: Pick<RectifiedPlane, "width" | "height" | "margin">,
  u: number,
  v: number,
): Point {
  const span = 1 + plane.margin * 2;
  return [((u + plane.margin) / span) * plane.width, ((v + plane.margin) / span) * plane.height];
}

/** Inverse of `cardToPlanePixel`. */
export function planePixelToCard(
  plane: Pick<RectifiedPlane, "width" | "height" | "margin">,
  x: number,
  y: number,
): Point {
  const span = 1 + plane.margin * 2;
  return [(x / plane.width) * span - plane.margin, (y / plane.height) * span - plane.margin];
}

/**
 * Inward inset of a card-space edge for an optical-zone ratio.
 *
 * Ratios are defined against the card minor axis, so the same physical
 * distance maps to different u/v fractions on a non-square card.
 */
export function zoneInsetFractions(metrics: CardMetrics, ratio: number): { u: number; v: number } {
  const inset = ratio * metrics.minorAxis;
  return {
    u: metrics.cardWidth > 0 ? inset / metrics.cardWidth : 0,
    v: metrics.cardHeight > 0 ? inset / metrics.cardHeight : 0,
  };
}

/** The inward distance, as a minor-axis ratio, of a card-space position. */
export function cardPositionToRatio(
  metrics: CardMetrics,
  u: number,
  v: number,
  edge: "top" | "right" | "bottom" | "left",
): number {
  if (metrics.minorAxis <= 0) return 0;
  const fraction = edge === "top" ? v : edge === "bottom" ? 1 - v : edge === "left" ? u : 1 - u;
  const axis = edge === "top" || edge === "bottom" ? metrics.cardHeight : metrics.cardWidth;
  return (fraction * axis) / metrics.minorAxis;
}
