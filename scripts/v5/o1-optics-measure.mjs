#!/usr/bin/env node
/**
 * O1 final captures: Target + BEFORE (the V0-accepted build -- optics-
 * identical to pre-O1, proven bit-exact by the V1 pixel gate) + CANDIDATE
 * (the O1 build), same states, one session.
 *
 * Local lanes additionally capture the media-only and glass-only layer
 * controls. The Target has no layer toggle; its lane is beauty only.
 *
 * Media is LIVE on every lane (the Target's cannot be frozen from
 * outside), so ROI comparisons are distribution statistics, never pixel
 * matches -- the brief forbids full-screen pixel matching against
 * different media anyway.
 *
 * Usage: o1-optics-measure.mjs --candidate=<origin> --before=<origin>
 *        --out=<dir> [--target=<origin>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  candidate: null, before: null,
  target: "https://infinite-liquid-glass.shader.se/?v=2",
  out: path.join(REPO, "artifacts/optics/o1-final"),
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--candidate=")) opts.candidate = a.slice(12);
  else if (a.startsWith("--before=")) opts.before = a.slice(9);
  else if (a.startsWith("--target=")) opts.target = a.slice(9);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
}
if (!opts.candidate || !opts.before) {
  console.error("--candidate and --before required"); process.exit(2);
}

const VPS = ["1440x900", "390x844"];
const STATES = [
  ["rest", null],
  ["pointer-corner-br", (w, h) => [w - 6, h - 6]],
];
const LAYERS = {
  beauty: null,
  "media-only": { glass: false, media: true, labels: false },
  "glass-only": { glass: true, media: false, labels: false },
};

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const index = { shots: [] };

// Metric lanes are captured over REPEATS 3 fresh loads: every load
// reshuffles the media assignment, so repeats sample the media
// distribution instead of trusting one draw of it.
const REPEATS = 3;

async function shoot(page, lane, vp, w, h, rep) {
  for (const [state, pointer] of STATES) {
    if (pointer) {
      const [px, py] = pointer(w, h);
      await page.mouse.move(px, py, { steps: 10 });
      await page.waitForTimeout(1800);
    }
    const suffix = rep === null ? "" : `-r${rep}`;
    const f = path.join(opts.out, `${lane}-${vp}-${state}${suffix}.png`);
    await page.screenshot({ path: f });
    index.shots.push({ lane, vp, state, rep, file: f });
  }
}

for (const vp of VPS) {
  const [w, h] = vp.split("x").map(Number);
  for (let rep = 0; rep < REPEATS; rep++) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    await page.goto(opts.target, { waitUntil: "load", timeout: 60000 });
    await page.waitForTimeout(9000);
    await shoot(page, "target", vp, w, h, rep);
    await ctx.close();
  }
  for (const [name, origin] of [["candidate", opts.candidate], ["before", opts.before]]) {
    for (const [layer, cfg] of Object.entries(LAYERS)) {
      const reps = layer === "beauty" ? REPEATS : 1;
      for (let rep = 0; rep < reps; rep++) {
        const ctx = await browser.newContext({ viewport: { width: w, height: h } });
        const page = await ctx.newPage();
        await page.goto(origin + "/?composition=sourceExact&qa",
          { waitUntil: "load", timeout: 60000 });
        await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
          undefined, { timeout: 120000 });
        await page.waitForTimeout(4000);
        if (cfg) {
          await page.evaluate((c) => window.__ILG_QA__.setRenderLayers(c), cfg);
          await page.waitForTimeout(600);
        }
        await shoot(page, `${name}-${layer}`, vp, w, h,
                    layer === "beauty" ? rep : null);
        await ctx.close();
      }
    }
  }
}
await browser.close();
await writeFile(path.join(opts.out, "index.json"), JSON.stringify(index, null, 1));
process.stdout.write(`captured ${index.shots.length} shots -> ${opts.out}\n`);
