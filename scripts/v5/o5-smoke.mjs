#!/usr/bin/env node
/**
 * O5 candidate smoke test.
 *
 * Not a gate -- the gates come later. This answers the only question that
 * matters before any of them: does the target-source lane render at all, does
 * it render something DIFFERENT from the control, and does it do so without
 * console errors, NaN pixels or a black card.
 *
 * Usage: o5-smoke.mjs --local=<origin> [--out=<dir>] [--asset=bw-split]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: "http://127.0.0.1:5280", asset: "bw-split", freeze: 4,
  out: path.join(REPO, "artifacts/optics-o5/smoke") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

async function run(lane, vp) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await installLocalRoutes(ctx, loadAsset(opts.asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const url = `${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&opticalBody=${lane}`;
  await page.goto(url, { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  const freeze = await page.evaluate((t) =>
    window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.setOffset(0, 0); qa.setVelocity(0, 0); qa.jumpPointer(0, 0);
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
    qa.renderOnce(); qa.renderOnce();
  });
  await page.waitForTimeout(200);
  const optics = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
  const file = `${lane}-${opts.asset}-${vp}.png`;
  await page.screenshot({ path: path.join(opts.out, file) });
  records.push({ lane, vp, file, optics, frozen: freeze?.frozen,
    errorCount: errors.length, errors: errors.slice(0, 8) });
  console.log(`  ${lane} ${vp}: errors=${errors.length} `
    + `opticalBody=${optics.opticalBody} samples=${optics.opticalBodySamples} `
    + `materials=${optics.opticalBodyMaterials}`);
  await ctx.close();
}

for (const vp of ["1440x900", "700x700"]) {
  for (const lane of ["current", "target-source"]) await run(lane, vp);
}

await writeFile(path.join(opts.out, "smoke.json"),
  JSON.stringify({ what: "O5 candidate smoke: does the lane render, differ, "
    + "and stay error-free", local: opts.local, asset: opts.asset, records },
    null, 1));
console.log(`-> ${opts.out}`);
await browser.close();
