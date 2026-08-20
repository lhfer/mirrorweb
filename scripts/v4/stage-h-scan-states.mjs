#!/usr/bin/env node
/**
 * One-off read-only scan that fixes the review state set.
 *
 * Stage H forbids re-scanning for bright / dark / high-texture / low-texture
 * every round: a candidate that happens to look bad on a high-texture card
 * could otherwise be rescued by the harness quietly choosing a different cell.
 * This runs once, writes an immutable manifest, and is never consulted again.
 *
 * Read-only: it changes nothing and captures nothing to the round evidence.
 */
import { spawn } from "node:child_process";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const port = Number(process.argv.find((a) => a.startsWith("--port="))?.slice(7) ?? 5321);
const out = process.argv.find((a) => a.startsWith("--out="))?.slice(6);
if (!out) throw new Error("--out is required");

const CELL_W = 557.72, CELL_H = 428, REST_Y0 = -211.05;
const brickColumn = (i, j) => i + (((j % 2) + 2) % 2 === 1 ? 0.5 : 0);
const centerOn = (i, j) => ({ x: brickColumn(i, j) * CELL_W, y: j * CELL_H + REST_Y0 });

// Frame centres, not frame boundaries: seeking exactly onto a boundary lets the
// decoder snap either way, which is the one thing that can break media-only
// hash equality between two processes.
const FPS = 30;
const frameCentre = (frame) => Number(((frame + 0.5) / FPS).toFixed(6));
const MEDIA_TIME = frameCentre(60);

function startPreview() {
  const child = spawn("npx", ["vite", "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"] });
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("preview did not start")), 30_000);
    const onData = (c) => { if (String(c).includes("Local:")) { clearTimeout(timer); resolve(child); } };
    child.stdout.on("data", onData); child.stderr.on("data", onData); child.once("error", reject);
  });
}

let preview, browser;
try {
  preview = await startPreview();
  browser = await chromium.launch({ channel: "chrome", headless: process.env.ILG_CAPTURE_HEADLESS === "1",
    args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  await page.goto(`http://127.0.0.1:${port}/?optics=v4&qa=1`, { waitUntil: "load" });
  await page.waitForFunction(() => window.__ILG_QA__?.getState()?.ready === true, undefined, { timeout: 90_000 });
  await page.evaluate(() => window.__ILG_QA__.reset());
  await page.waitForTimeout(1500);
  const freeze = await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), MEDIA_TIME);
  if (!freeze.frozen) throw new Error(`scan aborted: media did not freeze ${JSON.stringify(freeze)}`);

  // Media-only, so the measurement is of the media itself and not of the glass
  // that is about to change.
  await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: false, media: true, labels: false }));

  const cells = [];
  for (let i = -2; i <= 2; i += 1) for (let j = -1; j <= 1; j += 1) cells.push([i, j]);
  const { analyzeBuffers } = await import("./lib/round1-frame-stats.mjs");
  const measured = [];
  for (const [i, j] of cells) {
    const offset = centerOn(i, j);
    await page.evaluate((o) => { window.__ILG_QA__.setPointer(0, 0); window.__ILG_QA__.setOffset(o.x, o.y); }, offset);
    await page.waitForTimeout(320);
    measured.push({ i, j, offset, buffer: await page.screenshot() });
  }
  const stats = await analyzeBuffers(measured.map((m) => m.buffer));
  const scored = measured.map((m, k) => ({ i: m.i, j: m.j, offset: m.offset, ...stats[k] }));

  // The four content states must land on four DIFFERENT cells. Picking each
  // extreme independently let bright and high-texture collapse onto the same
  // cell, which quietly voided the "high-texture is mandatory" safeguard: the
  // state was formally present but added no coverage beyond bright.
  const byLuma = [...scored].sort((a, b) => b.centerLuma - a.centerLuma);
  const byTexture = [...scored].sort((a, b) => b.centerTexture - a.centerTexture);
  const used = new Set();
  const take = (list, fromEnd) => {
    const ordered = fromEnd ? [...list].reverse() : list;
    for (const entry of ordered) {
      const key = `${entry.i},${entry.j}`;
      if (used.has(key)) continue;
      used.add(key);
      return entry;
    }
    throw new Error("not enough distinct cells to fix four content states");
  };
  // Texture first: luminance extremes are plentiful, texture extremes are not.
  const highTexture = take(byTexture, false);
  const lowTexture = take(byTexture, true);
  const bright = take(byLuma, false);
  const dark = take(byLuma, true);
  const pick = { bright, dark, highTexture, lowTexture };

  await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: true, media: true, labels: true }));
  await writeFile(out, `${JSON.stringify({
    generator: "stage-h-scan-states",
    scannedOn: "the Stage H build, whose product render path is proven identical to ffcd8d9",
    mediaTime: MEDIA_TIME,
    mediaTimeRationale: "frame centre (60 + 0.5)/30, never a frame boundary",
    freeze,
    candidates: scored.map((s) => ({ cell: [s.i, s.j], centerLuma: Number(s.centerLuma.toFixed(4)), centerTexture: Number(s.centerTexture.toFixed(4)) })),
    picked: Object.fromEntries(Object.entries(pick).map(([k, v]) => [k, { cell: [v.i, v.j], offset: v.offset, centerLuma: Number(v.centerLuma.toFixed(4)), centerTexture: Number(v.centerTexture.toFixed(4)) }])),
  }, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(Object.fromEntries(Object.entries(pick).map(([k, v]) => [k, { cell: [v.i, v.j], luma: Number(v.centerLuma.toFixed(4)), tex: Number(v.centerTexture.toFixed(4)) }])), null, 2));
  await context.close();
} finally { await browser?.close(); preview?.kill("SIGTERM"); }
