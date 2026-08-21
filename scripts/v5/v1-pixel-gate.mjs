#!/usr/bin/env node
/**
 * V1 pixel-invariance gate captures.
 *
 * Two comparisons, both on frozen media, at every viewport and settled
 * state:
 *
 *   A/B      -- the SAME candidate build, coverage culling ON vs OFF. This
 *               isolates the culling itself: the two frames must be
 *               IDENTICAL, because everything the verdict hides is either
 *               back-facing (no fragments, FrontSide materials) or entirely
 *               outside the viewport's 64 px band (no on-screen fragments),
 *               and the scene-colour input is not culled at all.
 *   baseline -- the V0-accepted build vs the candidate with culling ON.
 *               Ties the candidate to the accepted baseline: V1 changed no
 *               shader and no layout, so settled frames must match to the
 *               declared tolerance.
 *
 * Usage:
 *   v1-pixel-gate.mjs --candidate=<origin> [--baseline=<origin>]
 *                     --out=<dir> [--vps=...]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  candidate: null, baseline: null,
  out: path.join(REPO, "artifacts/render-culling/pixels"),
  vps: ["1440x900", "1920x1080", "390x844", "844x390", "700x700"],
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--candidate=")) opts.candidate = a.slice(12);
  else if (a.startsWith("--baseline=")) opts.baseline = a.slice(11);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
}
if (!opts.candidate) { console.error("--candidate required"); process.exit(2); }

const STATES = [
  ["rest", null],
  ["pointer-corner-br", (w, h) => [w - 6, h - 6]],
  ["pointer-corner-tl", () => [6, 6]],
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });

async function settleAndShoot(page, w, h, pointer, file) {
  if (pointer) {
    const [px, py] = pointer(w, h);
    await page.mouse.move(px, py, { steps: 10 });
    await page.waitForTimeout(1800);
  }
  await page.waitForTimeout(600);
  await page.screenshot({ path: file });
}

const index = { candidate: opts.candidate, baseline: opts.baseline, shots: [] };
for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  for (const [lane, origin] of [["candidate", opts.candidate],
                                ["baseline", opts.baseline]]) {
    if (!origin) continue;
    const ctx = await browser.newContext({ viewport: { width: w, height: h } });
    const page = await ctx.newPage();
    await page.goto(origin, { waitUntil: "load", timeout: 60000 });
    await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
      undefined, { timeout: 120000 });
    await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
    await page.waitForTimeout(2200);
    for (const [state, pointer] of STATES) {
      if (lane === "candidate") {
        await page.evaluate(() => window.__ILG_QA__.setRenderCulling?.(true));
        await page.waitForTimeout(300);
        const on = path.join(opts.out, `${vp}-${state}-candidate-on.png`);
        await settleAndShoot(page, w, h, pointer, on);
        await page.evaluate(() => window.__ILG_QA__.setRenderCulling?.(false));
        await page.waitForTimeout(300);
        const off = path.join(opts.out, `${vp}-${state}-candidate-off.png`);
        // pointer already parked by the ON shot; do not move again
        await page.waitForTimeout(600);
        await page.screenshot({ path: off });
        await page.evaluate(() => window.__ILG_QA__.setRenderCulling?.(true));
        index.shots.push({ vp, state, lane, on, off });
      } else {
        const f = path.join(opts.out, `${vp}-${state}-baseline.png`);
        await settleAndShoot(page, w, h, pointer, f);
        index.shots.push({ vp, state, lane, file: f });
      }
    }
    await ctx.close();
  }
}
await browser.close();
await writeFile(path.join(opts.out, "index.json"), JSON.stringify(index, null, 1));
process.stdout.write(`captured ${index.shots.length} shot sets -> ${opts.out}\n`);
