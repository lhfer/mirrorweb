#!/usr/bin/env node
/**
 * O0 runtime captures: the SAME states on the Target and on our candidate,
 * plus our media-only control (the Target has no layer toggle -- its
 * media-only truth is structural: the shader's tint is white and its only
 * desaturation path is the fresnel-capped env mix, byte-anchored in the O0
 * forensics).
 *
 * The Target's media cannot be frozen from outside, so ROI comparisons are
 * STATISTICAL (chroma/luma distributions over edge and interior bands),
 * never pixel matches -- the brief forbids full-screen pixel matching
 * against different media anyway.
 *
 * Usage: o0-optics-measure.mjs --candidate=<origin> --out=<dir>
 *        [--target=<origin>] [--vps=...]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";
const opts = {
  candidate: null, target: TARGET,
  out: path.join(REPO, "artifacts/optics/o0"),
  vps: ["1440x900", "390x844"],
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--candidate=")) opts.candidate = a.slice(12);
  else if (a.startsWith("--target=")) opts.target = a.slice(9);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
}
if (!opts.candidate) { console.error("--candidate required"); process.exit(2); }

const STATES = [
  ["rest", null],
  ["pointer-corner-br", (w, h) => [w - 6, h - 6]],
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const index = { shots: [] };

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);

  // ---- Target ----
  {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    await page.goto(opts.target, { waitUntil: "load", timeout: 60000 });
    await page.waitForTimeout(9000);
    for (const [state, pointer] of STATES) {
      if (pointer) {
        const [px, py] = pointer(w, h);
        await page.mouse.move(px, py, { steps: 10 });
        await page.waitForTimeout(1800);
      }
      const f = path.join(opts.out, `target-${vp}-${state}.png`);
      await page.screenshot({ path: f });
      index.shots.push({ lane: "target", vp, state, file: f });
    }
    await ctx.close();
  }

  // ---- Candidate: beauty + media-only control ----
  for (const layer of ["beauty", "media-only"]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    await page.goto(opts.candidate, { waitUntil: "load", timeout: 60000 });
    await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
      undefined, { timeout: 120000 });
    await page.waitForTimeout(4000);
    if (layer === "media-only") {
      await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: false, media: true, labels: false }));
      await page.waitForTimeout(600);
    }
    for (const [state, pointer] of STATES) {
      if (pointer) {
        const [px, py] = pointer(w, h);
        await page.mouse.move(px, py, { steps: 10 });
        await page.waitForTimeout(1800);
      }
      const f = path.join(opts.out, `candidate-${layer}-${vp}-${state}.png`);
      await page.screenshot({ path: f });
      index.shots.push({ lane: `candidate-${layer}`, vp, state, file: f });
    }
    await ctx.close();
  }
}
await browser.close();
await writeFile(path.join(opts.out, "index.json"), JSON.stringify(index, null, 1));
process.stdout.write(`captured ${index.shots.length} shots -> ${opts.out}\n`);
