#!/usr/bin/env node
/**
 * O3 §八 Target repeatability baseline.
 *
 * Every O3 threshold is derived from how much the TARGET moves against
 * ITSELF under the deterministic shared-media harness, so it has to be
 * measured before any candidate exists. Each repeat is an INDEPENDENT page
 * load in a fresh browser context -- same routed media, same freeze time,
 * same viewport -- so the spread it reports is real page-to-page variance
 * (mount timing, decode order, compositor state), not one page sampled
 * repeatedly.
 *
 * No local lane is captured here and no candidate exists yet.
 *
 * Usage: o3-target-repeatability.mjs [--repeats=3] [--target=<url>]
 *        [--out=<dir>] [--freeze=4]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installTargetRoutes, loadAsset, TARGET_VIDEO_HOOK, freezeTarget }
  from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  target: "https://infinite-liquid-glass.shader.se/?v=2",
  out: path.join(REPO, "artifacts/optics-o3/repeatability"),
  repeats: 3, freeze: 4,
};
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = (k === "repeats" || k === "freeze") ? Number(v) : v;
}

// The six §八 media.
const ASSETS = ["bw-split", "grayscale-step", "dark-highlight", "bright-lowsat",
  "cool-blue", "rgb-bars"];
// bw-split carries the band-width and dark-luma thresholds, so it is
// repeated on every scored viewport; the rest anchor the white ratio.
const MOBILE_VPS = [[390, 844], [844, 390]];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

async function capture(vp, mobile, asset, run) {
  const [w, h] = vp;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installTargetRoutes(ctx, loadAsset(asset), null);
  await ctx.addInitScript(TARGET_VIDEO_HOOK);
  const page = await ctx.newPage();
  await page.goto(opts.target, { waitUntil: "load", timeout: 60000 });
  // The Target gates its mount on every clip decoding. Same condition-driven
  // wait the O2 measure pass uses -- without it the capture is a loading
  // screen, which is exactly the failure this baseline must not bake in.
  await page.waitForFunction(() =>
    (window.__o2vids?.length ?? 0) >= 8 &&
    window.__o2vids.every((v) => v.readyState >= 2), undefined, { timeout: 90000 });
  await page.waitForTimeout(4000);
  const freeze = await freezeTarget(page, opts.freeze);
  await page.waitForTimeout(250);
  const tag = `${w}x${h}`;
  const file = `target-run${run}-${asset}-${tag}.png`;
  await page.screenshot({ path: path.join(opts.out, file) });
  records.push({ kind: "target", run, asset, vp: tag, file,
    freeze: { videos: freeze?.videos, allFrozenAt: freeze?.allFrozenAt } });
  await ctx.close();
  console.log(`run ${run} ${tag} ${asset}`);
}

for (let run = 1; run <= opts.repeats; run += 1) {
  for (const asset of ASSETS) await capture([1440, 900], false, asset, run);
  for (const vp of MOBILE_VPS) await capture(vp, true, "bw-split", run);
}

await writeFile(path.join(opts.out, "repeatability-manifest.json"),
  JSON.stringify({
    what: "O3 §八 Target repeatability captures -- independent page loads",
    target: opts.target, repeats: opts.repeats, freeze: opts.freeze,
    assets: ASSETS, records,
  }, null, 1));
console.log(`${records.length} captures -> ${opts.out}`);
await browser.close();
