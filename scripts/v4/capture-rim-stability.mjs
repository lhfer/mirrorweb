#!/usr/bin/env node

/**
 * Temporal stability pass for the centre card's rim during real video playback.
 *
 * Holds the grid at rest (offset 0, pointer 0) so nothing but the media moves,
 * then grabs a long run of consecutive frames of the same clip region. The
 * clip rectangle and the frame count are fixed on the command line so both
 * sides of an A/B are measured on exactly the same pixels.
 */

import { spawn } from "node:child_process";
import { mkdir, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

const options = { port: 5290, out: null, frames: 120, clip: { x: 440, y: 430, width: 560, height: 470 } };
for (const argument of process.argv.slice(2)) {
  if (argument.startsWith("--port=")) options.port = Number(argument.slice("--port=".length));
  else if (argument.startsWith("--out=")) options.out = argument.slice("--out=".length);
  else if (argument.startsWith("--frames=")) options.frames = Number(argument.slice("--frames=".length));
  else throw new Error(`Unknown argument: ${argument}`);
}
if (!options.out) throw new Error("--out is required");

function startPreview(port) {
  const child = spawn("npx", ["vite", "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"], {
    cwd: REPO_ROOT,
    stdio: ["ignore", "pipe", "pipe"],
  });
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("vite preview did not start")), 30_000);
    const onData = (chunk) => {
      if (String(chunk).includes("Local:")) { clearTimeout(timer); resolve(child); }
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
    child.once("error", reject);
  });
}

let preview;
let browser;
try {
  await rm(options.out, { recursive: true, force: true }).catch(() => {});
  await mkdir(options.out, { recursive: true });
  preview = await startPreview(options.port);
  browser = await chromium.launch({
    channel: "chrome",
    headless: process.env.ILG_CAPTURE_HEADLESS === "1",
    args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:${options.port}/?optics=v4&qa=1`, { waitUntil: "load" });
  await page.waitForFunction(
    () => window.__ILG_QA__ !== undefined && window.__ILG_QA__.getState()?.ready === true,
    undefined,
    { timeout: 90_000 },
  );
  await page.evaluate(() => { window.__ILG_QA__.reset(); window.__ILG_QA__.setPointer(0, 0); });
  await page.waitForTimeout(4000);
  const quad = await page.evaluate(() => {
    const quads = window.__ILG_V4_GRID_QA__?.getCardQuads?.() ?? [];
    let best = null; let bestDistance = Infinity;
    for (const entry of quads) {
      const xs = entry.quad.map((p) => p[0]);
      const ys = entry.quad.map((p) => p[1]);
      if (xs.some((v) => v < -1 || v > 2)) continue;
      const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
      const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
      const d = Math.hypot(cx - 0.5, cy - 0.5);
      if (d < bestDistance) { bestDistance = d; best = entry.quad; }
    }
    return best;
  });
  for (let i = 0; i < options.frames; i += 1) {
    await page.screenshot({ path: path.join(options.out, `r${String(i).padStart(4, "0")}.png`), clip: options.clip });
  }
  console.log(JSON.stringify({ frames: options.frames, clip: options.clip, centreQuad: quad }));
  await context.close();
} finally {
  await browser?.close();
  preview?.kill("SIGTERM");
}
