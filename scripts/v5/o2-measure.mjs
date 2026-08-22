#!/usr/bin/env node
/**
 * O2 scoring captures (o2-selected-system.json captureProtocol):
 *
 * Lanes -- Target (routed shared media) + before/floors/candidates all from
 * ONE local origin via QA state:
 *   before   = dispersionLaw=v1, envMixScale=0, rimScale=0, shell
 *              energy-controlled (proven == 5159cf8 by the blocking gate)
 *   envmix0  = env 0, rim 1, shell off        (per registered floorStates)
 *   lerponly = env 1, rim 0, shell off
 *   fullB    = env 1, rim 1, shell off        (the candidate)
 * B-only lane = ?dispersionLaw=v1, A+B lane = ?dispersionLaw=o1.
 *
 * Pointer states (desktop bw-split only): rest / left nx=-0.99 /
 * corner-br / right nx=+0.99. Local pages jump the applied pointer;
 * the Target gets real mouse moves plus settle time.
 *
 * Media-only rows (F7): candidate lanes vs the base worktree origins,
 * glass layer hidden, same frozen media.
 *
 * Usage: o2-measure.mjs --local=<origin> --v1base=<origin> --o1base=<origin>
 *        [--target=<url>] [--out=<dir>] [--freeze=4]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, installTargetRoutes, loadAsset,
  TARGET_VIDEO_HOOK, freezeTarget } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, v1base: null, o1base: null,
  target: "https://infinite-liquid-glass.shader.se/?v=2",
  out: path.join(REPO, "artifacts/optics-o2/measure"), freeze: 4, only: "all" };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local || !opts.v1base || !opts.o1base) {
  console.error("--local, --v1base, --o1base required"); process.exit(2);
}

const DESKTOP_ASSETS = ["grayscale-step", "bw-split", "rgb-bars", "hf-checker",
  "dark-highlight", "bright-lowsat", "warm-skin", "cool-blue"];
const MOBILE_ASSETS = ["bw-split", "grayscale-step", "rgb-bars", "cool-blue", "warm-skin"];
const FLOORS = [
  { name: "before", env: 0, rim: 0, shell: "energy-controlled" },
  { name: "envmix0", env: 0, rim: 1, shell: "off" },
  { name: "lerponly", env: 1, rim: 0, shell: "off" },
  { name: "fullB", env: 1, rim: 1, shell: "off" },
];
const POINTER = [["pl", -0.99, 0], ["pbr", 0.99, 0.99], ["pr", 0.99, 0]];

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

async function localLane(vp, mobile, asset, origin, law, floors, opt = {}) {
  const [w, h] = vp;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, loadAsset(asset), null);
  const page = await ctx.newPage();
  const lawQ = law ? `&dispersionLaw=${law}` : "";
  await page.goto(`${origin}/?composition=sourceExact&qa${lawQ}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  const freeze = await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => { window.__ILG_QA__.setOffset(0, 0); window.__ILG_QA__.setVelocity(0, 0); });
  const tag = `${w}x${h}`;
  const laneTag = law === "v1" ? "v1" : law === "o1" ? "o1" : "base";
  for (const fl of floors) {
    await page.evaluate((f) => {
      const qa = window.__ILG_QA__;
      if (qa.setShellMode) qa.setShellMode(f.shell);
      if (qa.setEnvMixScale) { qa.setEnvMixScale(f.env); qa.setRimScale(f.rim); }
      qa.renderOnce(); qa.renderOnce();
    }, fl);
    const optics = await page.evaluate(() =>
      window.__ILG_QA__.getOpticsState ? window.__ILG_QA__.getOpticsState() : null);
    const file = await shot(page, `local-${laneTag}-${fl.name}-${asset}-${tag}`);
    records.push({ kind: "local", lane: laneTag, state: fl.name, asset, vp: tag,
      file, freeze: { frozen: freeze?.frozen, maxSeekError: freeze?.maxSeekError }, optics });
    if (fl.name === "fullB" && opt.pointer) {
      for (const [pname, nx, ny] of POINTER) {
        await page.evaluate(([x, y]) => {
          window.__ILG_QA__.jumpPointer(x, y);
          window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
        }, [nx, ny]);
        const pf = await shot(page, `local-${laneTag}-fullB-${pname}-${asset}-${tag}`);
        records.push({ kind: "local", lane: laneTag, state: `fullB-${pname}`, asset,
          vp: tag, pointer: [nx, ny], file: pf });
      }
      await page.evaluate(() => { window.__ILG_QA__.jumpPointer(0, 0);
        window.__ILG_QA__.renderOnce(); });
    }
  }
  if (opt.mediaOnly) {
    await page.evaluate(() => {
      window.__ILG_QA__.setRenderLayers({ glass: false });
      window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
    });
    const mf = await shot(page, `local-${laneTag}-mediaonly-${asset}-${tag}`);
    records.push({ kind: "media-only", lane: laneTag, asset, vp: tag, file: mf });
    await page.evaluate(() => { window.__ILG_QA__.setRenderLayers({ glass: true });
      window.__ILG_QA__.renderOnce(); });
  }
  await ctx.close();
}

async function targetLane(vp, mobile, asset, opt = {}) {
  const [w, h] = vp;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  const asset_ = loadAsset(asset);
  await installTargetRoutes(ctx, asset_, null);
  await ctx.addInitScript(TARGET_VIDEO_HOOK);
  const page = await ctx.newPage();
  await page.goto(opts.target, { waitUntil: "load", timeout: 60000 });
  // The Target gates its mount on every clip decoding; wait for the hook
  // to hold the full tier's videos with decoded frames (the harness used a
  // fixed 11s -- this is the same wait, condition-driven), then give the
  // mount animation time to finish.
  await page.waitForFunction(() =>
    (window.__o2vids?.length ?? 0) >= 8 &&
    window.__o2vids.every((v) => v.readyState >= 2), undefined,
    { timeout: 90000 });
  await page.waitForTimeout(4000);
  const freeze = await freezeTarget(page, opts.freeze);
  const tag = `${w}x${h}`;
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

// ---- desktop 1440x900
const doTarget = opts.only === "all" || opts.only === "target";
const doLocal = opts.only === "all" || opts.only === "local";
for (const asset of DESKTOP_ASSETS) {
  const pointer = asset === "bw-split";
  const mediaOnly = asset === "bw-split" || asset === "rgb-bars";
  if (doTarget) await targetLane([1440, 900], false, asset, { pointer });
  if (doLocal) {
    await localLane([1440, 900], false, asset, opts.local, "v1", FLOORS, { pointer, mediaOnly });
    await localLane([1440, 900], false, asset, opts.local, "o1", FLOORS.slice(1), { pointer, mediaOnly });
    if (mediaOnly) {
      await localLane([1440, 900], false, asset, opts.v1base, null, [FLOORS[0]], { mediaOnly });
      await localLane([1440, 900], false, asset, opts.o1base, null, [FLOORS[0]], { mediaOnly });
    }
  }
  console.log(`desktop ${asset} done`);
}
// ---- mobile portrait + landscape
for (const vp of [[390, 844], [844, 390]]) {
  for (const asset of MOBILE_ASSETS) {
    const mediaOnly = asset === "bw-split" && vp[0] === 390;
    if (doTarget) await targetLane(vp, true, asset);
    if (doLocal) {
      await localLane(vp, true, asset, opts.local, "v1", FLOORS, { mediaOnly });
      await localLane(vp, true, asset, opts.local, "o1", FLOORS.slice(1),
        { mediaOnly: mediaOnly });
      if (mediaOnly) {
        await localLane(vp, true, asset, opts.v1base, null, [FLOORS[0]], { mediaOnly });
        await localLane(vp, true, asset, opts.o1base, null, [FLOORS[0]], { mediaOnly });
      }
    }
    console.log(`${vp.join("x")} ${asset} done`);
  }
}
let allRecords = records;
if (opts.only !== "all") {
  try {
    const prev = JSON.parse(
      await (await import("node:fs/promises")).readFile(
        path.join(opts.out, "measure-manifest.json"), "utf8"));
    const dropKind = opts.only === "target" ? "target" : null;
    allRecords = prev.records
      .filter((r) => (dropKind ? r.kind !== dropKind : true))
      .concat(records);
  } catch { /* no previous manifest */ }
}
await writeFile(path.join(opts.out, "measure-manifest.json"),
  JSON.stringify({ capturedAtHead: "e913aa6", freeze: opts.freeze,
    target: opts.target, records: allRecords }, null, 1));
console.log(`${records.length} captures -> ${opts.out}`);
await browser.close();
