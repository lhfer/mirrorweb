#!/usr/bin/env node
/**
 * O5 §八/§九 -- scoring captures.
 *
 * Order matters and is enforced by the script: TARGET REPEATABILITY is
 * captured FIRST, before any candidate frame exists, because every §九 window
 * is max(2 x repeatability, floor) and a window derived after seeing the
 * candidate is not a window, it is a fit.
 *
 * Three lanes on one deterministic media harness:
 *   target      the live site, its own clips replaced by our shared assets
 *   control     opticalBody=current   -- the accepted O2 body
 *   candidate   opticalBody=target-source
 *
 * Rest is the state every optical measurand is scored in, because it is the
 * only one both a local QA hook and a live site can be put into identically.
 * Pointer states are driven with real mouse moves and a settle, the way O3
 * drove them, since the Target has no QA surface. Motion lives in its own
 * gate with real gesture playback.
 *
 * Usage: o5-measure.mjs --local=<origin> [--target=<url>] [--out=<dir>]
 *        [--repeats=3] [--only=all|target|local]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, installTargetRoutes, loadAsset,
  TARGET_VIDEO_HOOK, freezeTarget } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null,
  target: "https://infinite-liquid-glass.shader.se/?v=2",
  out: path.join(REPO, "artifacts/optics-o5/measure"),
  freeze: 4, repeats: 3, only: "all" };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = (k === "freeze" || k === "repeats") ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const VIEWPORTS = [[1440, 900], [390, 844], [844, 390], [700, 700]];
const DESKTOP = ["bw-split", "grayscale-step", "rgb-bars", "hf-checker",
  "dark-highlight", "bright-lowsat", "warm-skin", "cool-blue", "cover-control"];
const MOBILE = ["bw-split", "rgb-bars", "cool-blue", "cover-control"];
const LANES = ["control", "candidate"];
// Repeatability is measured on the metrics' own assets: the band and luma
// windows come from bw-split, the compression window from cover-control.
const REPEAT_ASSETS = ["bw-split", "cover-control"];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

const assetsFor = (w, h) => (w < 500 || h < 500 ? MOBILE : DESKTOP);

async function shot(page, name) {
  const file = `${name}.png`;
  await page.screenshot({ path: path.join(opts.out, file) });
  return file;
}

const pointerPx = (w, h) => ({
  pl: [Math.round(w * 0.005), Math.round(h / 2)],
  pr: [Math.round(w * 0.995), Math.round(h / 2)],
  pbr: [Math.round(w * 0.995), Math.round(h * 0.995)],
});

// ---------------------------------------------------------------- target
async function targetLane(vp, asset, { pointer = false, repeat = null } = {}) {
  const [w, h] = vp;
  const mobile = w < 500 || h < 500;
  const tag = `${w}x${h}`;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installTargetRoutes(ctx, loadAsset(asset), null);
  await ctx.addInitScript(TARGET_VIDEO_HOOK);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(opts.target, { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() =>
    (window.__o2vids?.length ?? 0) >= 8 &&
    window.__o2vids.every((v) => v.readyState >= 2), undefined, { timeout: 90000 });
  await page.waitForTimeout(4000);
  const freeze = await freezeTarget(page, opts.freeze);
  const suffix = repeat === null ? "" : `-r${repeat}`;
  const file = await shot(page, `target-rest-${asset}-${tag}${suffix}`);
  records.push({ kind: "target", lane: "target", state: "rest", asset,
    vp: tag, file, repeat,
    freeze: { videos: freeze?.videos, allFrozenAt: freeze?.allFrozenAt },
    errorCount: errors.length });
  if (pointer) {
    for (const [pn, [px, py]] of Object.entries(pointerPx(w, h))) {
      await page.mouse.move(px, py, { steps: 4 });
      await page.waitForTimeout(2000);
      const pf = await shot(page, `target-${pn}-${asset}-${tag}`);
      records.push({ kind: "target", lane: "target", state: pn, asset,
        vp: tag, file: pf, pointerPx: [px, py] });
    }
  }
  await ctx.close();
}

// ---------------------------------------------------------------- local
async function localLane(lane, vp, asset, { pointer = false, aux = false } = {}) {
  const [w, h] = vp;
  const mobile = w < 500 || h < 500;
  const tag = `${w}x${h}`;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, loadAsset(asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&bodyFloorMode=current&opticalBody=`
    + `${lane === "candidate" ? "target-source" : "current"}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  const freeze = await page.evaluate((t) =>
    window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.pause();
    qa.setOffset(0, 0); qa.setVelocity(0, 0); qa.jumpPointer(0, 0);
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
    qa.renderOnce(); qa.renderOnce();
  });
  await page.waitForTimeout(160);
  const optics = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
  const passes = await page.evaluate(() =>
    ({ stats: window.__ILG_QA__.getRenderPassStats?.() ?? null,
       layers: window.__ILG_QA__.getRenderLayerState?.() ?? null }));
  const file = await shot(page, `${lane}-rest-${asset}-${tag}`);
  records.push({ kind: "lane", lane, state: "rest", asset, vp: tag, file,
    optics, passes, frozen: freeze?.frozen, errorCount: errors.length,
    errors: errors.slice(0, 6) });

  if (pointer) {
    for (const [pn, [px, py]] of Object.entries(pointerPx(w, h))) {
      const nx = (px / w) * 2 - 1;
      const ny = (py / h) * 2 - 1;
      await page.evaluate(([x, y]) => {
        window.__ILG_QA__.jumpPointer(x, y);
        window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
      }, [nx, ny]);
      await page.waitForTimeout(120);
      const pf = await shot(page, `${lane}-${pn}-${asset}-${tag}`);
      records.push({ kind: "lane", lane, state: pn, asset, vp: tag, file: pf,
        pointerNdc: [nx, ny] });
    }
    await page.evaluate(() => {
      window.__ILG_QA__.jumpPointer(0, 0); window.__ILG_QA__.renderOnce();
    });
  }

  if (aux) {
    // media-only: the flat media with the body switched off. It is the true
    // silhouette's second input and the edge-compression baseline check.
    await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      qa.setRenderLayers({ glass: false, media: true });
      qa.renderOnce(); qa.renderOnce();
    });
    await page.waitForTimeout(120);
    const mf = await shot(page, `${lane}-mediaonly-${asset}-${tag}`);
    records.push({ kind: "media-only", lane, asset, vp: tag, file: mf });

    // glass-only: the body with the media plane off. In the candidate the
    // body carries its own media, so this is the same picture as beauty; in
    // the control it is the glass over an empty scene-colour pass. Both are
    // captured because the DIFFERENCE between them is the point.
    await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      qa.setRenderLayers({ glass: true, media: false });
      qa.renderOnce(); qa.renderOnce();
    });
    await page.waitForTimeout(120);
    const gf = await shot(page, `${lane}-glassonly-${asset}-${tag}`);
    records.push({ kind: "glass-only", lane, asset, vp: tag, file: gf });
    await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      qa.setRenderLayers({ glass: true, media: true });
      qa.renderOnce();
    });
  }
  records.push({ kind: "errors", lane, asset, vp: tag,
    errorCount: errors.length, samples: errors.slice(0, 8) });
  await ctx.close();
}

// ---- 1. TARGET REPEATABILITY, before anything else -------------------
if (opts.only !== "local") {
  for (const vp of VIEWPORTS) {
    for (const asset of REPEAT_ASSETS) {
      if (!assetsFor(vp[0], vp[1]).includes(asset)) continue;
      for (let r = 0; r < opts.repeats; r += 1) {
        await targetLane(vp, asset, { repeat: r });
      }
      console.log(`target repeatability ${vp.join("x")} ${asset}: `
        + `${opts.repeats} runs`);
    }
  }
  // ---- 2. TARGET scoring captures -----------------------------------
  for (const vp of VIEWPORTS) {
    for (const asset of assetsFor(vp[0], vp[1])) {
      await targetLane(vp, asset, { pointer: asset === "bw-split" });
    }
    console.log(`target ${vp.join("x")} done`);
  }
}

// ---- 3. LOCAL lanes --------------------------------------------------
if (opts.only !== "target") {
  for (const vp of VIEWPORTS) {
    for (const asset of assetsFor(vp[0], vp[1])) {
      for (const lane of LANES) {
        await localLane(lane, vp, asset, {
          pointer: asset === "bw-split",
          aux: ["bw-split", "rgb-bars", "cover-control", "hf-checker"]
            .includes(asset),
        });
      }
    }
    console.log(`local ${vp.join("x")} done`);
  }
}

await writeFile(path.join(opts.out, "measure-manifest.json"), JSON.stringify({
  what: "O5 §八/§九 scoring captures. Target repeatability is captured BEFORE "
      + "any candidate frame, because every window is derived from it.",
  target: opts.target, local: opts.local, freeze: opts.freeze,
  repeats: opts.repeats, viewports: VIEWPORTS.map((v) => v.join("x")),
  desktopAssets: DESKTOP, mobileAssets: MOBILE, repeatAssets: REPEAT_ASSETS,
  records,
}, null, 1));
console.log(`${records.length} records -> ${opts.out}`);
await browser.close();
