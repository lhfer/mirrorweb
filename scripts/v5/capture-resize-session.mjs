#!/usr/bin/env node

/**
 * Stage F2 deliverable: a resize session.
 *
 * Sweeps the viewport continuously from the widest desktop size down through
 * the breakpoint into mobile landscape and portrait, holding on each of the six
 * gated viewports, and composites every frame onto one fixed canvas so the
 * composition's response to the viewport is readable rather than being hidden
 * by the video frame itself resizing.
 *
 * Frames are screenshots, not Playwright's recordVideo: the recorder rescales
 * its output when the page resizes, which is exactly the signal being measured.
 * ffmpeg encodes the sequence.
 *
 * Usage: capture-resize-session.mjs --out=<dir> [--route=/?optics=v4] [--fps=20]
 */

import { spawnSync } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

const options = {
  origin: "http://127.0.0.1:5280",
  route: "/?optics=v4",
  out: path.join(REPO_ROOT, "qa-v5/f2/session"),
  fps: 20,
  canvas: [1920, 1200],
  headless: process.env.ILG_CAPTURE_HEADLESS !== "0",
};
for (const arg of process.argv.slice(2)) {
  if (arg.startsWith("--origin=")) options.origin = arg.slice(9);
  else if (arg.startsWith("--route=")) options.route = arg.slice(8);
  else if (arg.startsWith("--out=")) options.out = path.resolve(REPO_ROOT, arg.slice(6));
  else if (arg.startsWith("--fps=")) options.fps = Number(arg.slice(6));
}

/** The six gated viewports, held long enough to read, plus a continuous sweep. */
const HOLDS = [
  [1920, 1080], [1440, 900], [1366, 768], [1100, 720], [844, 390], [390, 844],
];

function sweep() {
  const steps = [];
  const push = (w, h, hold = 1) => steps.push({ w: Math.round(w), h: Math.round(h), hold });
  // desktop, wide -> narrow, height tracking a 16:10-ish band
  for (let w = 1920; w >= 1024; w -= 28) push(w, Math.round(w * 0.5625 / 0.9));
  // through the landscape band
  for (let w = 1024; w >= 844; w -= 12) push(w, Math.max(380, Math.round(w * 0.55)));
  // mobile landscape -> portrait flip
  push(844, 390, 10);
  push(390, 844, 10);
  return steps;
}

const url = `${options.origin}${options.route}${options.route.includes("?") ? "&" : "?"}qa=1`;
const framesDir = path.join(options.out, "frames");
await rm(options.out, { recursive: true, force: true }).catch(() => {});
await mkdir(framesDir, { recursive: true });

const browser = await chromium.launch({
  channel: "chrome",
  headless: options.headless,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
});
const context = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
const page = await context.newPage();
await page.goto(url, { waitUntil: "load" });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 120_000 });
await page.waitForTimeout(2500);
await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
await page.evaluate(() => {
  window.__ILG_QA__.setPointer(0, 0);
  window.__ILG_QA__.setOffset(0, 0);
  window.__ILG_QA__.pause();
});

const manifest = [];
let n = 0;
const steps = sweep();
for (const [index, step] of steps.entries()) {
  await page.setViewportSize({ width: step.w, height: step.h });
  await page.waitForTimeout(160);
  await page.evaluate(() => window.__ILG_QA__.setOffset(0, 0));
  await page.waitForTimeout(90);
  const held = HOLDS.some(([w, h]) => w === step.w && h === step.h) ? 14 : step.hold;
  const file = path.join(framesDir, `raw-${String(index).padStart(4, "0")}.png`);
  await page.screenshot({ path: file });
  const scale = await page.evaluate(() => {
    const s = window.__ILG_QA__.getV4State?.() ?? {};
    return s.compositionScale ?? null;
  });
  for (let k = 0; k < held; k += 1) {
    manifest.push({ frame: n, w: step.w, h: step.h, src: path.basename(file), scale });
    n += 1;
  }
}
await context.close();
await browser.close();

await writeFile(path.join(options.out, "session.json"), JSON.stringify({ steps: manifest.length, manifest }, null, 2));

// ---- composite every frame onto one fixed canvas and encode -----------------
const py = `
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
out = Path(sys.argv[1]); frames = out / "frames"
man = json.loads((out / "session.json").read_text())["manifest"]
CW, CH = ${options.canvas[0]}, ${options.canvas[1]}
try: font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 30)
except OSError: font = ImageFont.load_default()
comp = out / "composited"; comp.mkdir(exist_ok=True)
cache = {}
for i, m in enumerate(man):
    if m["src"] not in cache:
        cache[m["src"]] = Image.open(frames / m["src"]).convert("RGB")
    src = cache[m["src"]]
    canvas = Image.new("RGB", (CW, CH), (14, 14, 18))
    k = min((CW - 80) / src.width, (CH - 150) / src.height, 1.0)
    view = src.resize((int(src.width * k), int(src.height * k)), Image.LANCZOS)
    x = (CW - view.width) // 2; y = 110 + (CH - 150 - view.height) // 2
    canvas.paste(view, (x, y))
    d = ImageDraw.Draw(canvas)
    d.rectangle([x - 2, y - 2, x + view.width + 1, y + view.height + 1], outline=(90, 90, 110))
    label = f'{m["w"]}x{m["h"]}'
    if m.get("scale"): label += f'   composition scale S = {m["scale"]:.4f}'
    d.text((40, 34), label, fill=(240, 240, 250), font=font)
    d.text((40, 72), "MirrorWeb V5 F2 - resize session, media frozen, offset 0", fill=(130, 140, 170), font=font)
    canvas.save(comp / f"f{i:05d}.png")
print(len(man))
`;
const composited = spawnSync("python3", ["-c", py, options.out], { encoding: "utf8" });
process.stdout.write(composited.stdout || "");
if (composited.status !== 0) {
  console.error(composited.stderr);
  process.exit(1);
}

const mp4 = path.join(options.out, "resize-session.mp4");
const enc = spawnSync("ffmpeg", [
  "-y", "-framerate", String(options.fps),
  "-i", path.join(options.out, "composited", "f%05d.png"),
  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
  "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", mp4,
], { encoding: "utf8" });
if (enc.status !== 0) {
  console.error(enc.stderr?.slice(-2000));
  process.exit(1);
}
console.log(`done -> ${mp4}`);
