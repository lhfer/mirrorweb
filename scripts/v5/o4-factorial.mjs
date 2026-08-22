#!/usr/bin/env node
/**
 * O4B — frozen body floor factorial capture (§六).
 *
 * Every capture is taken with System B OFF (envMixScale 0, rimScale 0,
 * shell off), labels off, deterministic shared media frozen at 4.0s,
 * reflectionSupport=geometry and dispersionLaw=o1-spectral. That state is
 * the accepted O2 body with the reflection neutralised, and the all-current
 * lane in it is what every factor is measured against.
 *
 * The design is the specified 2^5 over A..E, REPLICATED at both states of a
 * sixth axis N -- the refraction-normal repair the O4A audit made necessary.
 * N is not part of §六's five factors and is reported separately, but §七.E
 * cannot be judged without its contribution measured on the identical
 * basis, so the two 32-lane blocks are run rather than one.
 *
 * Lanes are build-time: each is its own page load with its own
 * ?bodyDiag=, and each lane's generated program hash is recorded, so a
 * claim that two lanes differ is backed by the program and not only by
 * pixels.
 *
 * Usage: o4-factorial.mjs --local=<origin> [--vp=1440x900] [--out=<dir>]
 *        [--media=a,b,c] [--lanes=all|ofat|<code>,<code>...]
 */
import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, vp: "1440x900", freeze: 4,
  media: "bw-split,grayscale-step,rgb-bars,hf-checker",
  lanes: "all", out: path.join(REPO, "artifacts/optics-o4/factorial") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const FACTORS = ["A", "B", "C", "D", "E", "N"];   // order of ?bodyDiag= chars

function allLanes() {
  const out = [];
  for (let i = 0; i < 64; i += 1) {
    out.push(FACTORS.map((_, b) => ((i >> (5 - b)) & 1)).join(""));
  }
  return out;
}
function ofatLanes() {
  const out = ["000000"];
  for (let b = 0; b < 6; b += 1) {
    out.push(FACTORS.map((_, j) => (j === b ? 1 : 0)).join(""));
  }
  out.push("111111");
  return out;
}
const LANES = opts.lanes === "all" ? allLanes()
  : opts.lanes === "ofat" ? ofatLanes()
  : opts.lanes.split(",");
const MEDIA = opts.media.split(",");
const [W, H] = opts.vp.split("x").map(Number);
const MOBILE = W < 500 || H < 500;

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

for (const asset of MEDIA) {
  const ctx = await browser.newContext({ viewport: { width: W, height: H },
    hasTouch: MOBILE, ...(MOBILE ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, loadAsset(asset), null);
  const page = await ctx.newPage();
  let mediaOnlyDone = false;

  for (const code of LANES) {
    await page.goto(
      `${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
      + `&reflectionSupport=geometry&bodyDiag=${code}`,
      { waitUntil: "load", timeout: 60000 });
    await page.waitForFunction(
      () => window.__ILG_QA__?.getState?.()?.ready === true,
      undefined, { timeout: 120000 });
    await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
    const freeze = await page.evaluate((t) =>
      window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
    await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      qa.setOffset(0, 0); qa.setVelocity(0, 0); qa.jumpPointer(0, 0);
      // System B OFF -- the body floor is what this measures.
      qa.setShellMode("off"); qa.setEnvMixScale(0); qa.setRimScale(0);
      // Labels off for every optical ROI, per the sealed instrument contract.
      qa.setRenderLayers({ labels: false });
      qa.renderOnce(); qa.renderOnce();
    });
    await page.waitForTimeout(180);

    const src = await page.evaluate(() =>
      (typeof window.__ILG_QA__.getGlassShaderSource === "function"
        ? window.__ILG_QA__.getGlassShaderSource() : null));
    const optics = await page.evaluate(() =>
      window.__ILG_QA__.getOpticsState ? window.__ILG_QA__.getOpticsState() : null);

    const file = `${opts.vp}-${asset}-${code}.png`;
    await page.screenshot({ path: path.join(opts.out, file) });
    records.push({
      kind: "lane", vp: opts.vp, asset, bodyDiag: code, file,
      programSha256: src
        ? createHash("sha256").update(src.fragmentShader).digest("hex") : null,
      programBytes: src ? src.fragmentShader.length : null,
      reportedBodyDiag: optics?.bodyDiag ?? null,
      envMixScale: optics?.envMixScale, rimScale: optics?.rimScale,
      shellMode: optics?.shellMode,
      frozen: freeze?.frozen, maxSeekError: freeze?.maxSeekError,
    });

    // One media-only frame per (viewport, media) -- the true silhouette is
    // derived from the CONTROL lane against it, then reused for the cell.
    if (!mediaOnlyDone && code === "000000") {
      await page.evaluate(() => {
        window.__ILG_QA__.setRenderLayers({ glass: false });
        window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
      });
      const mf = `${opts.vp}-${asset}-mediaonly.png`;
      await page.screenshot({ path: path.join(opts.out, mf) });
      records.push({ kind: "media-only", vp: opts.vp, asset, file: mf });
      await page.evaluate(() => {
        window.__ILG_QA__.setRenderLayers({ glass: true });
        window.__ILG_QA__.renderOnce();
      });
      mediaOnlyDone = true;
    }
  }
  await ctx.close();
  console.log(`${asset}: ${LANES.length} lanes done`);
}

const manifestPath = path.join(opts.out, `manifest-${opts.vp}.json`);
await writeFile(manifestPath, JSON.stringify({
  what: "O4B factorial captures. System B OFF, labels off, deterministic "
      + "frozen media, geometry support, o1-spectral dispersion.",
  design: "the specified 2^5 over A..E, replicated at both states of N (the "
        + "refraction-normal repair). N is reported separately from the five.",
  factorOrder: FACTORS,
  factorMeaning: {
    A: "noRefractionOffset -- identity, no screen-space displacement",
    B: "noBlur -- level-0 sampling, no mip blur",
    C: "noAdaptiveShaping -- raw refracted colour",
    D: "noDispersion -- one sample, no spectral spread",
    E: "linearOutput -- body material toneMapped = false",
    N: "repairRefractionNormal -- body reads a real geometry normal "
       + "(see qa-v5/optics-o4/body-code-audit.json)",
  },
  viewport: opts.vp, freeze: opts.freeze, lanes: LANES.length,
  media: MEDIA, records,
}, null, 1));
console.log(`${records.length} captures -> ${manifestPath}`);
await browser.close();
