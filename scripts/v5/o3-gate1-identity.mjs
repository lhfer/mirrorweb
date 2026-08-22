#!/usr/bin/env node
/**
 * O3 gate 1 (structural, BLOCKING): the geometry lane of the O3 build must
 * be pixel-identical to the e913aa6 O2 baseline under deterministic media.
 *
 * §六 requires "all other O2 code byte-identical", and every "not worse
 * than O2" item in §九 compares against the SAME-RUN geometry lane. If that
 * lane is not O2, those comparisons are against something else and the
 * whole scored set is void. So this runs first and blocks.
 *
 * Both sides get the SAME query string. The baseline predates
 * ?reflectionSupport and ignores it -- which is itself worth recording:
 * the parameter is inert on a build that has no lane switch.
 *
 * Threshold is exactly zero. The <=1/255 FMA envelope O2 recorded for its
 * runtime-neutralised rows does NOT apply here: the lane switch is a JS
 * branch taken before the node graph is built, so the geometry lane never
 * constructs the analytic-bevel nodes and the compiler has nothing extra to
 * schedule. A non-zero result means investigate, never excuse.
 *
 * Usage: o3-gate1-identity.mjs --candidate=<origin> --base=<origin>
 *        [--out=<dir>] [--freeze=4]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { candidate: null, base: null, freeze: 4,
  out: path.join(REPO, "artifacts/optics-o3/gate1") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.candidate || !opts.base) {
  console.error("--candidate and --base required"); process.exit(2);
}

// The scored O2 state: A+B lane, System B fully on, sourceExact shell off.
const QUERY = "&composition=sourceExact&dispersionLaw=o1&reflectionSupport=geometry";
const CASES = [
  { vp: "1440x900", asset: "bw-split" },
  { vp: "1440x900", asset: "rgb-bars" },
  { vp: "1440x900", asset: "grayscale-step" },
  { vp: "390x844", asset: "bw-split", mobile: true },
  { vp: "844x390", asset: "bw-split", mobile: true },
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });

async function capture(origin, side, c) {
  const [w, h] = c.vp.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: !!c.mobile, ...(c.mobile ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, loadAsset(c.asset), null);
  const page = await ctx.newPage();
  await page.goto(`${origin}/?qa${QUERY}`, { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.setShellMode("off");
    qa.setEnvMixScale(1);
    qa.setRimScale(1);
    qa.setOffset(0, 0);
    qa.setVelocity(0, 0);
    qa.jumpPointer(0, 0);
  });
  const freeze = await page.evaluate((t) =>
    window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => {
    window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
  });
  await page.waitForTimeout(400);
  // What the build actually believes it is running -- so a zero diff can be
  // read as "same pixels from the declared state", not "same pixels from an
  // unknown state".
  const optics = await page.evaluate(() =>
    window.__ILG_QA__.getOpticsState ? window.__ILG_QA__.getOpticsState() : null);
  const file = path.join(opts.out, `${side}-${c.asset}-${c.vp}.png`);
  await page.screenshot({ path: file });
  await ctx.close();
  return { file: path.basename(file), optics,
    frozen: freeze?.frozen, maxSeekError: freeze?.maxSeekError };
}

const pairs = [];
for (const c of CASES) {
  const a = await capture(opts.candidate, "o3build-geometry-lane", c);
  const b = await capture(opts.base, "e913aa6-baseline", c);
  pairs.push({ ...c, query: QUERY, candidate: a, base: b });
  console.log(`captured ${c.asset} ${c.vp}`);
}

await writeFile(path.join(opts.out, "pairs.json"), JSON.stringify({
  what: "O3 gate 1 -- geometry lane vs the e913aa6 O2 baseline, deterministic "
      + "frozen media, identical query on both sides.",
  candidateOrigin: opts.candidate,
  baseOrigin: opts.base,
  baseCommit: "e913aa6a33e384ba4fc80eb28b9a8718fb20e5b9",
  query: QUERY,
  freeze: opts.freeze,
  threshold: 0,
  thresholdNote: "exact zero; the FMA envelope does not apply because the "
    + "lane switch is a JS branch before graph construction.",
  pairs,
}, null, 1));
console.log(`${pairs.length} pairs -> ${opts.out}`);
await browser.close();
