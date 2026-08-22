#!/usr/bin/env node
/**
 * O5R scoring captures.
 *
 * Three phases, and the split is not cosmetic. §三 requires every corrected
 * instrument to be COMMITTED before any O5R candidate capture, so:
 *
 *   --phase=target   Target repeatability and scoring. Runs first, always.
 *                    Every window in the corrected gate is derived from these
 *                    frames, so they must exist before any lane is scored --
 *                    and the Target is not the candidate, so capturing it
 *                    before the seal is what the brief asks for, not a leak.
 *   --phase=pre      control (opticalBody=current) and the SEALED O5 clamped
 *                    candidate. Both already existed at the O5 head; the
 *                    clamped lane is re-captured here so §十三A's regression
 *                    re-run reads pixels from this head, and so the
 *                    clamped-lane identity check has something to compare.
 *   --phase=post     the O5R candidate, opticalBody=target-source-unclamped.
 *                    Runs ONLY after the instrument contract is committed.
 *
 * Lanes, assets and viewports are all fixed here rather than passed in, so a
 * re-run cannot quietly cover less than the round claims.
 *
 * Usage: o5r-measure.mjs --local=<origin> --phase=<target|pre|post>
 *        [--target=<url>] [--out=<dir>] [--repeats=3]
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import {
  installLocalRoutes, installTargetRoutes, loadAsset,
  TARGET_VIDEO_HOOK, freezeTarget,
} from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const O5R_MEDIA = path.join(REPO, "artifacts/optics-o5r/media");
const opts = {
  local: null,
  target: "https://infinite-liquid-glass.shader.se/?v=2",
  out: path.join(REPO, "artifacts/optics-o5r/measure"),
  freeze: 4, repeats: 3, phase: "target",
};
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = (k === "freeze" || k === "repeats") ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const VIEWPORTS = [[1440, 900], [390, 844], [844, 390], [700, 700]];

// §九's seven full-frame assets, plus the four the corrected instruments need:
// rgb-bars for the saturated-edge repair, calib-landmarks for the refraction
// repair, rgb-micro and detail-chart for the interior-fidelity repair.
const ASSETS = [
  "bw-split", "grayscale-step", "hf-checker", "dark-highlight",
  "bright-lowsat", "cool-blue", "warm-skin",
  "rgb-bars", "calib-landmarks", "rgb-micro", "detail-chart",
];
const O5R_ASSETS = new Set(["calib-landmarks", "rgb-micro", "detail-chart"]);

const LANE_QUERY = {
  control: "current",
  "o5-clamped": "target-source",
  "o5r-unclamped": "target-source-unclamped",
};
const PHASE_LANES = {
  pre: ["control", "o5-clamped"],
  post: ["o5r-unclamped"],
};

// The QA measurement views, §六 and §八. sdf-mask is media-independent so it is
// taken once per lane per viewport; the UV views are taken on the calibration
// asset, which is what they are for.
const UV_VIEWS = ["uv-unrefracted", "uv-refracted", "refraction-displacement"];

const asset_of = (name) =>
  loadAsset(name, O5R_ASSETS.has(name) ? O5R_MEDIA : undefined);

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });

const manPath = path.join(opts.out, "measure-manifest.json");
let man;
try {
  man = JSON.parse(await readFile(manPath, "utf8"));
} catch {
  man = {
    what: "O5R scoring captures. Target repeatability is captured BEFORE any "
        + "candidate frame, because every corrected window is derived from it. "
        + "The O5R candidate lane is captured only after the instrument "
        + "contract commit.",
    target: opts.target, local: opts.local, freeze: opts.freeze,
    repeats: opts.repeats, viewports: VIEWPORTS.map((v) => v.join("x")),
    assets: ASSETS, o5rCalibrationAssets: [...O5R_ASSETS],
    phasesRun: [], records: [],
  };
}
const records = man.records;

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
  await installTargetRoutes(ctx, asset_of(asset), null);
  await ctx.addInitScript(TARGET_VIDEO_HOOK);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(opts.target, { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() =>
    (window.__o2vids?.length ?? 0) >= 8
    && window.__o2vids.every((v) => v.readyState >= 2), undefined,
    { timeout: 90000 });
  await page.waitForTimeout(4000);
  const freeze = await freezeTarget(page, opts.freeze);
  const suffix = repeat === null ? "" : `-r${repeat}`;
  const file = await shot(page, `target-rest-${asset}-${tag}${suffix}`);
  records.push({ kind: "target", lane: "target", state: "rest", asset,
    vp: tag, file, repeat,
    freeze: { videos: freeze?.length ?? null },
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
async function openLocal(lane, vp, asset, extraQuery = "") {
  const [w, h] = vp;
  const mobile = w < 500 || h < 500;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, asset_of(asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&bodyFloorMode=current`
    + `&opticalBody=${LANE_QUERY[lane]}${extraQuery}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(
    () => window.__ILG_QA__?.getState?.()?.ready === true, undefined,
    { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t),
    opts.freeze);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.pause();
    qa.setOffset(0, 0); qa.setVelocity(0, 0); qa.jumpPointer(0, 0);
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
    qa.renderOnce(); qa.renderOnce();
  });
  await page.waitForTimeout(160);
  return { ctx, page, errors };
}

async function localLane(lane, vp, asset, { pointer = false, aux = false } = {}) {
  const [w, h] = vp;
  const tag = `${w}x${h}`;
  const { ctx, page, errors } = await openLocal(lane, vp, asset);
  const optics = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
  const passes = await page.evaluate(() =>
    ({ stats: window.__ILG_QA__.getRenderPassStats?.() ?? null,
       layers: window.__ILG_QA__.getRenderLayerState?.() ?? null }));
  const file = await shot(page, `${lane}-rest-${asset}-${tag}`);
  records.push({ kind: "lane", lane, state: "rest", asset, vp: tag, file,
    optics, passes, errorCount: errors.length, errors: errors.slice(0, 6) });

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
    await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      qa.setRenderLayers({ glass: false, media: true });
      qa.renderOnce(); qa.renderOnce();
    });
    await page.waitForTimeout(120);
    const mf = await shot(page, `${lane}-mediaonly-${asset}-${tag}`);
    records.push({ kind: "media-only", lane, asset, vp: tag, file: mf });
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

/** The QA measurement views, plus the live matrices the CPU replay needs. */
async function measurementViews(lane, vp) {
  const [w, h] = vp;
  const tag = `${w}x${h}`;
  for (const view of [...UV_VIEWS, "sdf-mask", "analytic-normal"]) {
    const { ctx, page, errors } = await openLocal(
      lane, vp, "calib-landmarks", `&bodyView=${view}`);
    const optics = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
    const file = await shot(page, `${lane}-view-${view}-${tag}`);
    records.push({ kind: "view", lane, view, asset: "calib-landmarks",
      vp: tag, file, reportedView: optics.opticalBodyView,
      errorCount: errors.length });
    await ctx.close();
  }
  // Live matrices, read from the Beauty build so nothing about the QA views
  // can influence what the replay is driven with.
  const { ctx, page } = await openLocal(lane, vp, "calib-landmarks");
  const truth = await page.evaluate(() => window.__ILG_QA__.getCardBodyTruth());
  await writeFile(path.join(opts.out, `${lane}-bodytruth-${tag}.json`),
    JSON.stringify(truth, null, 1));
  records.push({ kind: "body-truth", lane, vp: tag,
    file: `${lane}-bodytruth-${tag}.json`,
    cards: Array.isArray(truth.cards) ? truth.cards.length : null });
  await ctx.close();
}

// ------------------------------------------------------------------ run
if (opts.phase === "target") {
  for (const vp of VIEWPORTS) {
    for (const asset of ASSETS) {
      for (let r = 0; r < opts.repeats; r += 1) {
        await targetLane(vp, asset, { repeat: r });
      }
      console.log(`target ${vp.join("x")} ${asset}: ${opts.repeats} runs`);
    }
    // Pointer states on the band asset only, as O5 did: the pointer item is
    // about where the reflection sits, and bw-split is the asset the band is
    // measured on.
    await targetLane(vp, "bw-split", { pointer: true });
  }
} else {
  const lanes = PHASE_LANES[opts.phase];
  if (!lanes) { console.error(`unknown phase ${opts.phase}`); process.exit(2); }
  for (const vp of VIEWPORTS) {
    for (const lane of lanes) {
      for (const asset of ASSETS) {
        await localLane(lane, vp, asset, {
          pointer: asset === "bw-split",
          aux: ["bw-split", "hf-checker", "calib-landmarks",
                "rgb-bars"].includes(asset),
        });
      }
      if (lane !== "control") await measurementViews(lane, vp);
      console.log(`${lane} ${vp.join("x")} done`);
    }
  }
}

if (!man.phasesRun.includes(opts.phase)) man.phasesRun.push(opts.phase);
await writeFile(manPath, JSON.stringify(man, null, 1));
console.log(`phase=${opts.phase}: ${records.length} records total -> ${opts.out}`);
await browser.close();
