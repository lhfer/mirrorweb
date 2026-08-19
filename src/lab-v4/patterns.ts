import { CanvasTexture, LinearFilter, SRGBColorSpace } from "three/webgpu";
import { LAB_PATTERNS, type LabPattern } from "./types";

const WIDTH = 1600;
const HEIGHT = 1000;

function seeded(index: number) {
  const value = Math.sin(index * 91.733 + 17.31) * 43758.5453;
  return value - Math.floor(value);
}

function clear(ctx: CanvasRenderingContext2D, color: string) {
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
}

function drawChecker(ctx: CanvasRenderingContext2D) {
  clear(ctx, "#f1f2ed");
  const size = 64;
  ctx.fillStyle = "#111617";
  for (let y = -size; y < HEIGHT + size; y += size) {
    for (let x = -size; x < WIDTH + size; x += size) {
      if ((((x / size) | 0) + ((y / size) | 0)) % 2 === 0) ctx.fillRect(x, y, size, size);
    }
  }
}

function drawLines(ctx: CanvasRenderingContext2D, horizontal: boolean) {
  clear(ctx, "#eceee8");
  ctx.fillStyle = "#111719";
  for (let value = -4; value < (horizontal ? HEIGHT : WIDTH) + 4; value += 18) {
    if (horizontal) ctx.fillRect(0, value, WIDTH, 4);
    else ctx.fillRect(value, 0, 4, HEIGHT);
  }
  ctx.fillStyle = "#eb4c34";
  if (horizontal) ctx.fillRect(0, HEIGHT / 2 - 2, WIDTH, 4);
  else ctx.fillRect(WIDTH / 2 - 2, 0, 4, HEIGHT);
}

function drawTextGrid(ctx: CanvasRenderingContext2D) {
  clear(ctx, "#e9ece5");
  ctx.textBaseline = "middle";
  ctx.font = "600 30px ui-monospace, SFMono-Regular, Menlo, monospace";
  for (let row = 0; row < 12; row += 1) {
    for (let col = 0; col < 10; col += 1) {
      const x = 48 + col * 158;
      const y = 46 + row * 84;
      ctx.fillStyle = (row + col) % 3 === 0 ? "#e5422f" : "#101718";
      ctx.fillText(`${String.fromCharCode(65 + ((row + col) % 26))}${row}${col}`, x, y);
      ctx.fillStyle = "rgba(16, 23, 24, .28)";
      ctx.fillRect(x, y + 24, 112, 1);
    }
  }
}

function drawSyntheticPhoto(ctx: CanvasRenderingContext2D) {
  const sky = ctx.createLinearGradient(0, 0, 0, HEIGHT);
  sky.addColorStop(0, "#102c47");
  sky.addColorStop(0.46, "#7eb1c2");
  sky.addColorStop(0.47, "#e3be86");
  sky.addColorStop(1, "#281b18");
  ctx.fillStyle = sky;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);

  for (let layer = 0; layer < 5; layer += 1) {
    ctx.beginPath();
    ctx.moveTo(0, HEIGHT);
    const base = 520 + layer * 72;
    for (let x = 0; x <= WIDTH; x += 18) {
      const wave = Math.sin(x * (0.008 + layer * 0.002) + layer) * (60 - layer * 7);
      const detail = (seeded(x + layer * 101) - 0.5) * (58 - layer * 8);
      ctx.lineTo(x, base + wave + detail);
    }
    ctx.lineTo(WIDTH, HEIGHT);
    ctx.closePath();
    ctx.fillStyle = ["#5c493d", "#473b34", "#32302e", "#232827", "#131918"][layer];
    ctx.fill();
  }

  for (let i = 0; i < 780; i += 1) {
    const x = seeded(i * 3) * WIDTH;
    const y = 690 + seeded(i * 3 + 1) * 310;
    const height = 4 + seeded(i * 3 + 2) * 34;
    ctx.strokeStyle = i % 11 === 0 ? "#bda66f" : "rgba(214, 225, 200, .58)";
    ctx.lineWidth = i % 7 === 0 ? 2 : 1;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + (seeded(i + 999) - 0.5) * 8, y - height);
    ctx.stroke();
  }

  ctx.fillStyle = "rgba(247, 242, 216, .9)";
  ctx.beginPath();
  ctx.arc(1260, 205, 42, 0, Math.PI * 2);
  ctx.fill();
}

function drawFlatColor(ctx: CanvasRenderingContext2D) {
  clear(ctx, "#cf6039");
  ctx.fillStyle = "#dca764";
  ctx.fillRect(0, 0, WIDTH * 0.48, HEIGHT);
  ctx.fillStyle = "#356f73";
  ctx.fillRect(WIDTH * 0.48, 0, WIDTH * 0.52, HEIGHT * 0.62);
  ctx.fillStyle = "#243339";
  ctx.fillRect(WIDTH * 0.48, HEIGHT * 0.62, WIDTH * 0.52, HEIGHT * 0.38);
}

function drawAnimatedGradient(ctx: CanvasRenderingContext2D, time: number) {
  const x = WIDTH * (0.5 + Math.sin(time * 0.42) * 0.34);
  const y = HEIGHT * (0.5 + Math.cos(time * 0.31) * 0.3);
  const gradient = ctx.createRadialGradient(x, y, 20, WIDTH / 2, HEIGHT / 2, WIDTH * 0.82);
  gradient.addColorStop(0, "#f6e8b5");
  gradient.addColorStop(0.3, "#d76b3e");
  gradient.addColorStop(0.63, "#246f83");
  gradient.addColorStop(1, "#09131e");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, WIDTH, HEIGHT);
}

function drawVideoPlaceholder(ctx: CanvasRenderingContext2D, time: number) {
  clear(ctx, "#101618");
  const travel = (time * 110) % (WIDTH + 320) - 160;
  for (let i = -4; i < 14; i += 1) {
    ctx.fillStyle = ["#e54834", "#e8c768", "#78a9ad", "#f0eee5"][((i % 4) + 4) % 4];
    ctx.fillRect(i * 148 + travel, 0, 54, HEIGHT);
  }
  ctx.fillStyle = "rgba(4, 8, 9, .82)";
  ctx.fillRect(0, HEIGHT * 0.69, WIDTH, HEIGHT * 0.31);
  ctx.fillStyle = "#f2f2ec";
  ctx.font = "600 34px ui-monospace, SFMono-Regular, Menlo, monospace";
  ctx.letterSpacing = "6px";
  ctx.fillText("VIDEO PLACEHOLDER · PRIVATE MEDIA DISABLED", 72, HEIGHT * 0.82);
  ctx.fillStyle = "#e54834";
  ctx.fillRect(72, HEIGHT * 0.86, 280, 5);
}

function drawVideoFrame(ctx: CanvasRenderingContext2D, video: HTMLVideoElement) {
  clear(ctx, "#050708");
  const sourceWidth = Math.max(1, video.videoWidth);
  const sourceHeight = Math.max(1, video.videoHeight);
  const scale = Math.max(WIDTH / sourceWidth, HEIGHT / sourceHeight);
  const width = sourceWidth * scale;
  const height = sourceHeight * scale;
  ctx.drawImage(video, (WIDTH - width) * 0.5, (HEIGHT - height) * 0.5, width, height);
}

export class LabPatternTexture {
  readonly canvas = document.createElement("canvas");
  readonly texture: CanvasTexture;
  pattern: LabPattern = "checker";
  private lastAnimationFrame = -1;
  private video: HTMLVideoElement | null = null;
  private videoUrl: string | null = null;

  constructor() {
    this.canvas.width = WIDTH;
    this.canvas.height = HEIGHT;
    this.texture = new CanvasTexture(this.canvas);
    this.texture.colorSpace = SRGBColorSpace;
    this.texture.minFilter = LinearFilter;
    this.texture.magFilter = LinearFilter;
    this.texture.generateMipmaps = true;
    this.paint(0, true);
  }

  setPattern(pattern: LabPattern) {
    this.pattern = pattern;
    this.lastAnimationFrame = -1;
    this.paint(0, true);
  }

  update(timeSeconds: number) {
    if (this.pattern !== "animated-gradient" && this.pattern !== "video") return false;
    const frame = Math.floor(timeSeconds * 30);
    if (frame === this.lastAnimationFrame) return false;
    this.lastAnimationFrame = frame;
    this.paint(timeSeconds, true);
    return true;
  }

  async loadVideoFile(file: File) {
    this.releaseVideo();
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.src = url;
    video.muted = true;
    video.loop = true;
    video.playsInline = true;
    video.preload = "auto";
    await new Promise<void>((resolve, reject) => {
      video.addEventListener("loadeddata", () => resolve(), { once: true });
      video.addEventListener("error", () => reject(new Error("The selected video could not be decoded.")), { once: true });
    });
    this.video = video;
    this.videoUrl = url;
    this.pattern = "video";
    await video.play();
    this.lastAnimationFrame = -1;
    this.paint(video.currentTime, true);
  }

  dispose() {
    this.releaseVideo();
    this.texture.dispose();
  }

  private releaseVideo() {
    this.video?.pause();
    this.video?.removeAttribute("src");
    this.video?.load();
    if (this.videoUrl) URL.revokeObjectURL(this.videoUrl);
    this.video = null;
    this.videoUrl = null;
  }

  private paint(time: number, invalidate: boolean) {
    const ctx = this.canvas.getContext("2d");
    if (!ctx) throw new Error("2D canvas unavailable for V4 test pattern");
    switch (this.pattern) {
      case "checker": drawChecker(ctx); break;
      case "horizontal-lines": drawLines(ctx, true); break;
      case "vertical-lines": drawLines(ctx, false); break;
      case "text-grid": drawTextGrid(ctx); break;
      case "high-frequency-photo": drawSyntheticPhoto(ctx); break;
      case "low-frequency-flat-color": drawFlatColor(ctx); break;
      case "white": clear(ctx, "#f4f3eb"); break;
      case "black": clear(ctx, "#020303"); break;
      case "animated-gradient": drawAnimatedGradient(ctx, time); break;
      case "video":
        if (this.video && this.video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
          drawVideoFrame(ctx, this.video);
        } else {
          drawVideoPlaceholder(ctx, time);
        }
        break;
    }
    if (invalidate) this.texture.needsUpdate = true;
  }
}

export function parseLabPattern(value: string): LabPattern | null {
  const aliases: Record<string, LabPattern> = {
    "h-lines": "horizontal-lines",
    "v-lines": "vertical-lines",
    color: "low-frequency-flat-color",
    gradient: "animated-gradient",
    photo: "high-frequency-photo",
  };
  const normalized = aliases[value] ?? value;
  return LAB_PATTERNS.includes(normalized as LabPattern) ? (normalized as LabPattern) : null;
}
