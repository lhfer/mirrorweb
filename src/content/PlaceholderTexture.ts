import { CanvasTexture, LinearFilter, LinearMipmapLinearFilter, SRGBColorSpace } from "three/webgpu";
import type { CatalogItem } from "./catalog";

function hash(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i += 1) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function createPlaceholderTexture(item: CatalogItem, width = 1024, height = 768): CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("2d context unavailable");

  const [c0, c1, c2, c3] = item.palette;
  const seed = hash(item.code + item.title);
  const rnd = (n: number) => {
    const x = Math.sin(seed * 0.001 + n * 12.9898) * 43758.5453;
    return x - Math.floor(x);
  };

  const sky = ctx.createLinearGradient(0, 0, 0, height);
  sky.addColorStop(0, c0);
  sky.addColorStop(0.42, c1);
  sky.addColorStop(0.7, c2);
  sky.addColorStop(1, c3);
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, width, height);

  const sunX = width * (0.55 + rnd(2) * 0.3);
  const sunY = height * (0.18 + rnd(3) * 0.16);
  const glow = ctx.createRadialGradient(sunX, sunY, 8, sunX, sunY, width * 0.45);
  glow.addColorStop(0, c3);
  glow.addColorStop(0.35, c2);
  glow.addColorStop(1, "rgba(0,0,0,0)");
  ctx.globalAlpha = 0.85;
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, width, height);
  ctx.globalAlpha = 1;

  const horizon = height * (0.46 + rnd(4) * 0.12);
  ctx.fillStyle = c1;
  ctx.beginPath();
  ctx.moveTo(0, height);
  ctx.lineTo(0, horizon + 50);
  for (let x = 0; x <= width; x += 14) {
    ctx.lineTo(x, horizon + Math.sin((x + seed) * 0.012) * 34 + rnd(x + 9) * 48);
  }
  ctx.lineTo(width, height);
  ctx.closePath();
  ctx.fill();

  ctx.fillStyle = c0;
  ctx.beginPath();
  ctx.moveTo(0, height);
  ctx.lineTo(0, horizon + 110);
  for (let x = 0; x <= width; x += 20) {
    ctx.lineTo(x, horizon + 80 + Math.sin((x + seed) * 0.02) * 18 + rnd(x + 21) * 22);
  }
  ctx.lineTo(width, height);
  ctx.closePath();
  ctx.fill();

  ctx.globalAlpha = 0.22;
  for (let i = 0; i < 10; i += 1) {
    ctx.fillStyle = i % 2 ? c3 : c2;
    ctx.beginPath();
    ctx.ellipse(
      width * rnd(30 + i),
      height * (0.15 + rnd(40 + i) * 0.5),
      50 + rnd(50 + i) * 160,
      16 + rnd(60 + i) * 40,
      rnd(70 + i) * Math.PI,
      0,
      Math.PI * 2,
    );
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  const grain = ctx.getImageData(0, 0, width, height);
  const data = grain.data;
  for (let i = 0; i < data.length; i += 12) {
    const n = (rnd(i * 0.13) - 0.5) * 18;
    data[i] = Math.max(0, Math.min(255, data[i] + n));
    data[i + 1] = Math.max(0, Math.min(255, data[i + 1] + n));
    data[i + 2] = Math.max(0, Math.min(255, data[i + 2] + n));
  }
  ctx.putImageData(grain, 0, 0);

  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  texture.minFilter = LinearMipmapLinearFilter;
  texture.magFilter = LinearFilter;
  texture.generateMipmaps = true;
  texture.needsUpdate = true;
  return texture;
}
