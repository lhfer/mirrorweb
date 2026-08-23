import { CanvasTexture, LinearFilter, SRGBColorSpace } from "three/webgpu";

export const TEST_BACKGROUNDS = [
  "calibration",
  "checker",
  "h-lines",
  "v-lines",
  "color",
  "video",
  "white",
  "black",
  "gradient",
] as const;

export type TestBackground = (typeof TEST_BACKGROUNDS)[number];

export function createTestPattern(kind: TestBackground, width = 1024, height = 768): CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2d context unavailable");
  paintPattern(ctx, kind, width, height, 0);
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  texture.minFilter = LinearFilter;
  texture.magFilter = LinearFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  return texture;
}

export function paintPattern(
  ctx: CanvasRenderingContext2D,
  kind: TestBackground,
  width: number,
  height: number,
  time: number,
) {
  if (kind === "calibration") {
    paintCalibration(ctx, width, height);
    return;
  }
  if (kind === "white") {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    return;
  }
  if (kind === "black") {
    ctx.fillStyle = "#000000";
    ctx.fillRect(0, 0, width, height);
    return;
  }
  if (kind === "gradient") {
    const g = ctx.createLinearGradient(0, 0, width, height);
    g.addColorStop(0, "#fff7d6");
    g.addColorStop(0.5, "#3b82ff");
    g.addColorStop(1, "#111018");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, width, height);
    return;
  }
  if (kind === "color") {
    const cell = 64;
    for (let y = 0; y < height; y += cell) {
      for (let x = 0; x < width; x += cell) {
        const i = (x / cell + y / cell) % 6;
        ctx.fillStyle = ["#ff2d55", "#ffcc00", "#00e676", "#00b0ff", "#d500f9", "#ffffff"][i];
        ctx.fillRect(x, y, cell, cell);
      }
    }
    return;
  }
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#111111";
  if (kind === "checker") {
    const cell = 48;
    for (let y = 0; y < height; y += cell) {
      for (let x = 0; x < width; x += cell) {
        if (((x / cell + y / cell) | 0) % 2 === 0) ctx.fillRect(x, y, cell, cell);
      }
    }
    return;
  }
  if (kind === "h-lines") {
    for (let y = 0; y < height; y += 10) ctx.fillRect(0, y, width, 3);
    return;
  }
  if (kind === "v-lines") {
    for (let x = 0; x < width; x += 10) ctx.fillRect(x, 0, 3, height);
    return;
  }
  ctx.fillStyle = "#0b1020";
  ctx.fillRect(0, 0, width, height);
  const shift = (time * 180) % width;
  const bars = ["#ffffff", "#ff2d55", "#00e676", "#00b0ff"];
  for (let i = 0; i < 16; i += 1) {
    ctx.fillStyle = bars[i % bars.length];
    ctx.fillRect((i * 80 + shift) % width, 0, 28, height);
  }
  ctx.fillStyle = "#ffcc00";
  ctx.fillRect(0, (time * 90) % height, width, 18);
}

/**
 * Aspect-calibration target for MediaFit.
 *
 * Circles and squares laid out in source-pixel units. Rendered through a
 * correct `cover` fit they stay circles and squares; through `stretch` they
 * become ellipses and rectangles, and the ratio of the measured axes is the
 * aspect error.
 */
export function paintCalibration(ctx: CanvasRenderingContext2D, width: number, height: number) {
  ctx.fillStyle = "#101014";
  ctx.fillRect(0, 0, width, height);

  const step = Math.round(Math.min(width, height) / 6);
  ctx.strokeStyle = "#3a3a48";
  ctx.lineWidth = 1;
  for (let x = 0; x <= width; x += step) {
    ctx.beginPath();
    ctx.moveTo(x + 0.5, 0);
    ctx.lineTo(x + 0.5, height);
    ctx.stroke();
  }
  for (let y = 0; y <= height; y += step) {
    ctx.beginPath();
    ctx.moveTo(0, y + 0.5);
    ctx.lineTo(width, y + 0.5);
    ctx.stroke();
  }

  const r = Math.round(step * 0.72);
  const cx = width / 2;
  const cy = height / 2;
  // Centre circle: survives every cover crop, so it is the primary probe.
  ctx.fillStyle = "#ffffff";
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  // Centre square, same nominal size as the circle's diameter.
  ctx.strokeStyle = "#ff2d55";
  ctx.lineWidth = 4;
  ctx.strokeRect(cx - r, cy - r, r * 2, r * 2);

  // Satellites, close enough to the centre to survive a 16:9 -> 1.35:1 crop.
  ctx.fillStyle = "#00e676";
  for (const [ox, oy] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) {
    ctx.beginPath();
    ctx.arc(cx + ox * step * 1.4, cy + oy * step * 1.4, step * 0.34, 0, Math.PI * 2);
    ctx.fill();
  }

  // Source-edge markers, so a crop preview shows how much was cut.
  ctx.fillStyle = "#00b0ff";
  ctx.fillRect(0, 0, 10, height);
  ctx.fillRect(width - 10, 0, 10, height);
  ctx.fillStyle = "#ffcc00";
  ctx.fillRect(0, 0, width, 10);
  ctx.fillRect(0, height - 10, width, 10);
}
