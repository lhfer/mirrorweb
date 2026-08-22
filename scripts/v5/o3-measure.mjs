#!/usr/bin/env node
/**
 * O3 scoring captures.
 *
 * Three lanes, one shader build for the two local ones (§六):
 *   control    = ?reflectionSupport=geometry   -- the accepted O2 System B
 *   candidate  = ?reflectionSupport=target-sdf -- the Target's analytic
 *                bevel normal + its rounded-rect SDF rim
 *   target     = the routed Target, same frozen shared media
 *
 * Everything else is byte-identical between the two local lanes: same
 * origin, same page, same dispersionLaw=o1-spectral, same shell off, same
 * frozen media, same pointer. The ONLY difference is the two swapped
 * inputs to the frozen System B block.
 *
 * States. `full` is the scored one (env 1, rim 1). The three floor states
 * are the DECOMPOSITION: with envMixScale=0 and rimScale=0 System B is
 * fully off and the two lanes must be identical -- whatever band survives
 * there belongs to the frozen refraction / dispersion / adaptive-contrast
 * composition, not to reflection. That is simultaneously §十's band
 * cross-section deliverable and the diagnosis any non-passing band width
 * has to be read against. It is captured on bw-split at every viewport.
 *
 * Debug views (rim-mask, analytic-normal) exist only in the candidate
 * lane's shader; selecting one in the control lane renders beauty, which
 * is recorded rather than hidden -- adding those branches to the control
 * chain would have changed the control program and forfeited gate 1.
 *
 * Usage: o3-measure.mjs --local=<origin> [--target=<url>] [--out=<dir>]
 *        [--freeze=4] [--only=all|local|target]
 */
import { mkdir, writeFile, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, installTargetRoutes, loadAsset,
  TARGET_VIDEO_HOOK, freezeTarget } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null,
  target: "https://infinite-liquid-glass.shader.se/?v=2",
  out: path.join(REPO, "artifacts/optics-o3/measure"), freeze: 4, only: "all" };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const DESKTOP_ASSETS = ["bw-split", "grayscale-step", "rgb-bars", "hf-checker",
  "dark-highlight", "bright-lowsat", "warm-skin", "cool-blue"];
const MOBILE_ASSETS = ["bw-split", "grayscale-step", "rgb-bars", "cool-blue", "warm-skin"];
const TARGET_MOBILE_ASSETS = ["bw-split", "rgb-bars", "cool-blue"];
const LANES = [
  { tag: "control", support: "geometry" },
  { tag: "candidate", support: "target-sdf" },
];
const FULL = { name: "full", env: 1, rim: 1, shell: "off" };
const FLOORS = [
  { name: "env0rim0", env: 0, rim: 0, shell: "off" },
  { name: "env0rim1", env: 0, rim: 1, shell: "off" },
  { name: "env1rim0", env: 1, rim: 0, shell: "off" },
];
const POINTER = [["pl", -0.99, 0], ["pbr", 0.99, 0.99], ["pr", 0.99, 0]];
const DEBUG_VIEWS = ["rim-mask", "analytic-normal"];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

async function shot(page, name) {
  await page.waitForTimeout(250);
  const f = path.join(opts.out, `${name}.png`);
  await page.screenshot({ path: f });
  return path.basename(f);
}

async function applyState(page, st) {
  await page.evaluate((f) => {
    const qa = window.__ILG_QA__;
    qa.setShellMode(f.shell);
    qa.setEnvMixScale(f.env);
    qa.setRimScale(f.rim);
    qa.renderOnce(); qa.renderOnce();
  }, st);
}

async function localLane(vp, mobile, asset, lane, opt = {}) {
  const [w, h] = vp;
  const tag = `${w}x${h}`;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, loadAsset(asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(
    `${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1&reflectionSupport=${lane.support}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  const freeze = await page.evaluate((t) =>
    window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => {
    window.__ILG_QA__.setOffset(0, 0); window.__ILG_QA__.setVelocity(0, 0);
    window.__ILG_QA__.jumpPointer(0, 0);
  });

  const states = [FULL, ...(opt.floors ? FLOORS : [])];
  for (const st of states) {
    await applyState(page, st);
    const optics = await page.evaluate(() =>
      window.__ILG_QA__.getOpticsState ? window.__ILG_QA__.getOpticsState() : null);
    const file = await shot(page, `${lane.tag}-${st.name}-${asset}-${tag}`);
    records.push({ kind: "local", lane: lane.tag, support: lane.support,
      state: st.name, asset, vp: tag, file, optics,
      freeze: { frozen: freeze?.frozen, maxSeekError: freeze?.maxSeekError } });
  }

  await applyState(page, FULL);
  if (opt.pointer) {
    for (const [pname, nx, ny] of POINTER) {
      await page.evaluate(([x, y]) => {
        window.__ILG_QA__.jumpPointer(x, y);
        window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
      }, [nx, ny]);
      const pf = await shot(page, `${lane.tag}-full-${pname}-${asset}-${tag}`);
      records.push({ kind: "local", lane: lane.tag, state: `full-${pname}`,
        asset, vp: tag, pointer: [nx, ny], file: pf });
    }
    await page.evaluate(() => {
      window.__ILG_QA__.jumpPointer(0, 0); window.__ILG_QA__.renderOnce();
    });
  }

  if (opt.debug) {
    for (const mode of DEBUG_VIEWS) {
      await page.evaluate((m) => {
        window.__ILG_QA__.setDebugMode(m);
        window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
      }, mode);
      const df = await shot(page, `${lane.tag}-debug-${mode}-${asset}-${tag}`);
      records.push({ kind: "debug", lane: lane.tag, state: `debug-${mode}`,
        asset, vp: tag, file: df,
        note: lane.support === "geometry"
          ? "the control lane has no O3 debug branch; this frame is beauty, "
            + "by the design that keeps the control program equal to O2's"
          : null });
    }
    await page.evaluate(() => {
      window.__ILG_QA__.setDebugMode("beauty"); window.__ILG_QA__.renderOnce();
    });
  }

  if (opt.mediaOnly) {
    await page.evaluate(() => {
      window.__ILG_QA__.setRenderLayers({ glass: false });
      window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
    });
    const mf = await shot(page, `${lane.tag}-mediaonly-${asset}-${tag}`);
    records.push({ kind: "media-only", lane: lane.tag, asset, vp: tag, file: mf });
    await page.evaluate(() => {
      window.__ILG_QA__.setRenderLayers({ glass: true });
      window.__ILG_QA__.renderOnce();
    });
  }

  records.push({ kind: "errors", lane: lane.tag, asset, vp: tag,
    pageErrors: errors.slice(0, 20), errorCount: errors.length });
  await ctx.close();
}

async function targetLane(vp, mobile, asset, opt = {}) {
  const [w, h] = vp;
  const tag = `${w}x${h}`;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installTargetRoutes(ctx, loadAsset(asset), null);
  await ctx.addInitScript(TARGET_VIDEO_HOOK);
  const page = await ctx.newPage();
  await page.goto(opts.target, { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() =>
    (window.__o2vids?.length ?? 0) >= 8 &&
    window.__o2vids.every((v) => v.readyState >= 2), undefined, { timeout: 90000 });
  await page.waitForTimeout(4000);
  const freeze = await freezeTarget(page, opts.freeze);
  const file = await shot(page, `target-rest-${asset}-${tag}`);
  records.push({ kind: "target", state: "rest", asset, vp: tag, file,
    freeze: { videos: freeze?.videos, allFrozenAt: freeze?.allFrozenAt } });
  if (opt.pointer) {
    const P = { pl: [Math.round(w * 0.005), Math.round(h / 2)],
      pbr: [Math.round(w * 0.995), Math.round(h * 0.995)],
      pr: [Math.round(w * 0.995), Math.round(h / 2)] };
    for (const [pname, [px, py]] of Object.entries(P)) {
      await page.mouse.move(px, py, { steps: 4 });
      await page.waitForTimeout(2000);
      const pf = await shot(page, `target-${pname}-${asset}-${tag}`);
      records.push({ kind: "target", state: pname, asset, vp: tag,
        pointerPx: [px, py], file: pf });
    }
  }
  await ctx.close();
}

const doTarget = opts.only === "all" || opts.only === "target";
const doLocal = opts.only === "all" || opts.only === "local";

for (const asset of DESKTOP_ASSETS) {
  const pointer = asset === "bw-split";
  const mediaOnly = asset === "bw-split" || asset === "rgb-bars";
  const floors = asset === "bw-split";
  const debug = asset === "bw-split" || asset === "rgb-bars";
  if (doTarget) await targetLane([1440, 900], false, asset, { pointer });
  if (doLocal) {
    for (const lane of LANES) {
      await localLane([1440, 900], false, asset, lane,
        { pointer, mediaOnly, floors, debug });
    }
  }
  console.log(`desktop ${asset} done`);
}

for (const vp of [[390, 844], [844, 390]]) {
  for (const asset of MOBILE_ASSETS) {
    const mediaOnly = asset === "bw-split";
    const floors = asset === "bw-split";
    const debug = asset === "bw-split";
    if (doTarget && TARGET_MOBILE_ASSETS.includes(asset)) {
      await targetLane(vp, true, asset);
    }
    if (doLocal) {
      for (const lane of LANES) {
        await localLane(vp, true, asset, lane, { mediaOnly, floors, debug });
      }
    }
    console.log(`${vp.join("x")} ${asset} done`);
  }
}

let allRecords = records;
if (opts.only !== "all") {
  try {
    const prev = JSON.parse(await readFile(
      path.join(opts.out, "measure-manifest.json"), "utf8"));
    const dropKinds = opts.only === "target"
      ? ["target"] : ["local", "media-only", "debug", "errors"];
    allRecords = prev.records
      .filter((r) => !dropKinds.includes(r.kind)).concat(records);
  } catch { /* no previous manifest */ }
}
await writeFile(path.join(opts.out, "measure-manifest.json"), JSON.stringify({
  what: "O3 scoring captures -- control (geometry) and candidate (target-sdf) "
      + "from ONE build and one page each, plus the routed Target.",
  freeze: opts.freeze, target: opts.target, local: opts.local,
  records: allRecords }, null, 1));
console.log(`${records.length} captures -> ${opts.out}`);
await browser.close();
