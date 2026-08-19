#!/usr/bin/env node

/**
 * Refraction-offset saturation probe.
 *
 * Renders the same pose twice, once through the optical-zones debug view and
 * once through the refraction-offset debug view, so the two can be crossed:
 * how much of the strong-rim band is already pinned at the maxRefractionUv
 * clamp, and whether the offset still varies across the band or has gone flat.
 *
 * Nothing here judges the result. It only produces the two frames plus the
 * centre card quad; the measurement itself is done offline.
 */

import { spawn } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

const options = { port: 5292, out: null, overscan: null, shell: null };
for (const argument of process.argv.slice(2)) {
  if (argument.startsWith("--port=")) options.port = Number(argument.slice("--port=".length));
  else if (argument.startsWith("--out=")) options.out = argument.slice("--out=".length);
  else if (argument.startsWith("--overscan=")) options.overscan = Number(argument.slice("--overscan=".length));
  else if (argument.startsWith("--shell=")) options.shell = argument.slice("--shell=".length);
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
  const overscanQuery = options.overscan ? `&overscan=${options.overscan}` : "";
  const shellQuery = options.shell ? `&shell=${options.shell}` : "";
  await page.goto(`http://127.0.0.1:${options.port}/?optics=v4&qa=1${overscanQuery}${shellQuery}`, { waitUntil: "load" });
  await page.waitForFunction(
    () => window.__ILG_QA__ !== undefined && window.__ILG_QA__.getState()?.ready === true,
    undefined,
    { timeout: 90_000 },
  );
  await page.evaluate(() => {
    window.__ILG_QA__.reset();
    window.__ILG_QA__.setPointer(0, 0);
    window.__ILG_QA__.setTime(2);
  });
  await page.waitForTimeout(3000);

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

  for (const mode of ["optical-zones", "refraction-offset", "dispersion", "beauty"]) {
    await page.evaluate((value) => window.__ILG_QA__.setDebugMode(value), mode);
    await page.evaluate(() => window.__ILG_QA__.setTime(2));
    await page.waitForTimeout(900);
    await page.screenshot({ path: path.join(options.out, `${mode}.png`) });
  }

  const v4State = await page.evaluate(() => window.__ILG_V4_GRID_QA__.getV4State());
  await writeFile(
    path.join(options.out, "probe.json"),
    `${JSON.stringify({ centreQuad: quad, sceneColor: v4State.sceneColor, overscan: options.overscan, shell: options.shell }, null, 2)}\n`,
    "utf8",
  );
  console.log(JSON.stringify({ out: options.out, clampHeadroom: v4State.sceneColor.clampHeadroom }));
  await context.close();
} finally {
  await browser?.close();
  preview?.kill("SIGTERM");
}
