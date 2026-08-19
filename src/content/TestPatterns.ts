import { CanvasTexture, LinearFilter, SRGBColorSpace } from "three/webgpu";

export const TEST_BACKGROUNDS = [
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
