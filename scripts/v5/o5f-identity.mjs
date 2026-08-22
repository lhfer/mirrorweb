#!/usr/bin/env node
/**
 * O5F §六 -- identity captures: the cached build against a 445037e worktree.
 *
 * Three proofs in one run, in the §六 order, all BEFORE any memory scoring:
 *
 *   A  opticalBody=current              -- 5 viewports x 7 fixed states
 *   B  opticalBody=target-source-unclamped -- the same 35 states
 *   C  the generated WGSL, vertex and fragment, at the 5-sample tier and
 *      after a switch to the 3-sample tier, both origins
 *
 * plus the retired-defect demonstration: on each origin the candidate runs
 * high -> low -> high on a paused, media-frozen page and is photographed
 * before and after. At the baseline the first quality step rebinds the
 * convex volume geometry, so the pixels do not return; at O5F a quality
 * change is a cached-set switch and they must return exactly.
 *
 * The 35 states are the O5 control-identity states, unchanged: fixed
 * (offset, velocity, pointer) triples rather than replayed gestures, because
 * two servers cannot be driven through a real drag onto the same frame.
 *
 * Usage: o5f-identity.mjs --local=<origin> --base=<origin> [--out=<dir>]
 */
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, base: null, asset: "bw-split", freeze: 4,
  out: path.join(REPO, "artifacts/optics-o5f/identity") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local || !opts.base) {
  console.error("--local and --base are required");
  process.exit(2);
}

const VIEWPORTS = ["1440x900", "1920x1080", "390x844", "844x390", "700x700"];
const LANES = ["current", "target-source-unclamped"];

/** name -> QA state. Velocities are those the named gesture actually reaches. */
const STATES = [
  ["rest", { offset: [0, 0], velocity: [0, 0], pointer: [0, 0] }],
  ["pointer-left", { offset: [0, 0], velocity: [0, 0], pointer: [-0.99, 0] }],
  ["pointer-right", { offset: [0, 0], velocity: [0, 0], pointer: [0.99, 0] }],
  ["pointer-corner", { offset: [0, 0], velocity: [0, 0], pointer: [0.99, 0.99] }],
  ["slow-drag", { offset: [180, 0], velocity: [42, 0], pointer: [-0.35, 0] }],
  ["fast-flick", { offset: [-620, 0], velocity: [-1750, 0], pointer: [0.4, 0] }],
  ["touch", { offset: [0, 240], velocity: [0, 310], pointer: [0, -0.4] }],
];

const sha256 = (s) => createHash("sha256").update(s).digest("hex");

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });

async function openPage(origin, body, vp) {
  const [w, h] = vp.split("x").map(Number);
  const mobile = w < 500 || h < 500;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, loadAsset(opts.asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${origin}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&bodyFloorMode=current&opticalBody=${body}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  await page.evaluate((t) =>
    window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    // PAUSE before any state is set -- the page's own RAF loop would
    // integrate a velocity-bearing state for a scheduler-dependent dt.
    qa.pause();
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
  });
  return { ctx, page, errors };
}

async function captureLane(origin, tag, body, vp) {
  const { ctx, page, errors } = await openPage(origin, body, vp);
  const out = [];
  for (const [state, s] of STATES) {
    await page.evaluate((st) => {
      const qa = window.__ILG_QA__;
      qa.setVelocity(st.velocity[0], st.velocity[1]);
      qa.setOffset(st.offset[0], st.offset[1]);
      qa.jumpPointer(st.pointer[0], st.pointer[1]);
      qa.setTime(4);
      qa.renderOnce(); qa.renderOnce();
    }, s);
    await page.waitForTimeout(120);
    const file = `${body}-${tag}-${state}-${vp}.png`;
    await page.screenshot({ path: path.join(opts.out, file) });
    const probe = await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      const st = qa.getState();
      const op = qa.getOpticsState();
      return {
        opticalBody: op.opticalBody ?? null,
        opticalBodySamples: op.opticalBodySamples ?? null,
        environmentMode: op.environmentMode ?? null,
        envSampleClamped: op.envSampleClamped ?? null,
        bodyFloorMode: op.bodyFloorMode ?? null,
        reflectionSupport: op.reflectionSupport ?? null,
        dispersionLaw: op.dispersionLaw ?? null,
        shellMode: op.shellModeApplied ?? op.shellMode ?? null,
        envMixScale: op.envMixScale ?? null,
        rimScale: op.rimScale ?? null,
        glassMeshesVisible: st.glassMeshesVisible ?? null,
        reflectionShellsVisible: st.reflectionShellsVisible ?? null,
        mediaMeshesVisible: st.mediaMeshesVisible ?? null,
        activeSlots: st.activeSlots ?? null,
        drawCallsFinal: st.drawCallsFinal ?? null,
        drawCallsSceneColor: st.drawCallsSceneColor ?? null,
      };
    });
    // §五 truth, EVIDENCE ONLY: the surface does not exist at the baseline
    // commit, so it is recorded where present and excluded from the
    // probe-mismatch comparison.
    const cacheTruth = await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      if (typeof qa.getBodyMaterialCacheTruth !== "function") return null;
      const t = qa.getBodyMaterialCacheTruth();
      return { activeKey: t.activeKey, cacheSize: t.cacheSize,
        materialCreationCount: t.materialCreationCount,
        cacheSwitchCount: t.cacheSwitchCount };
    });
    out.push({ state, file, probe, cacheTruth });
  }
  await ctx.close();
  return { captures: out, errorCount: errors.length, errors: errors.slice(0, 6) };
}

/** §六C -- WGSL at the 5-sample tier, the 3-sample tier, and back at 5. */
async function programProbe(origin, tag) {
  const { ctx, page, errors } = await openPage(
    origin, "target-source-unclamped", "1440x900");
  const out = {};
  for (const step of ["high", "low", "high-return"]) {
    const level = step === "high-return" ? "high" : step;
    await page.evaluate((q) => {
      window.__ILG_QA__.setQuality(q);
      window.__ILG_QA__.renderOnce();
    }, level);
    const src = await page.evaluate(() =>
      window.__ILG_QA__.getGlassShaderSource());
    out[step] = {
      samples: src?.opticalBodySamples ?? null,
      vertexSha256: src ? sha256(src.vertexShader) : null,
      fragmentSha256: src ? sha256(src.fragmentShader) : null,
      vertexLength: src?.vertexShader?.length ?? null,
      fragmentLength: src?.fragmentShader?.length ?? null,
    };
  }
  await ctx.close();
  return { tag, programs: out, errorCount: errors.length };
}

/** The retired-defect demonstration: high -> low -> high must return. */
async function cycleReturn(origin, tag) {
  const { ctx, page, errors } = await openPage(
    origin, "target-source-unclamped", "1440x900");
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.setVelocity(0, 0); qa.setOffset(0, 0); qa.jumpPointer(0, 0);
    qa.setTime(4);
    qa.renderOnce(); qa.renderOnce();
  });
  await page.waitForTimeout(120);
  const before = `cyclereturn-${tag}-before.png`;
  await page.screenshot({ path: path.join(opts.out, before) });
  for (const level of ["low", "high"]) {
    await page.evaluate((q) => {
      window.__ILG_QA__.setQuality(q);
      window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
    }, level);
  }
  await page.waitForTimeout(120);
  const after = `cyclereturn-${tag}-after.png`;
  await page.screenshot({ path: path.join(opts.out, after) });
  await ctx.close();
  return { tag, before, after, errorCount: errors.length };
}

const records = [];
for (const body of LANES) {
  for (const vp of VIEWPORTS) {
    const local = await captureLane(opts.local, "local", body, vp);
    const base = await captureLane(opts.base, "base", body, vp);
    records.push({ body, vp, local, base });
    console.log(`${body} ${vp}: captured (local errors ${local.errorCount}, `
      + `base errors ${base.errorCount})`);
  }
}
const programs = {
  local: await programProbe(opts.local, "local"),
  base: await programProbe(opts.base, "base"),
};
console.log("program probe: done");
const cycles = {
  local: await cycleReturn(opts.local, "local"),
  base: await cycleReturn(opts.base, "base"),
};
console.log("cycle-return demonstration: done");

await writeFile(path.join(opts.out, "identity-manifest.json"), JSON.stringify({
  what: "O5F §六 identity captures. Both lanes at the O5F material-cache "
      + "commit against a 445037e worktree build, same deterministic media, "
      + "same frozen time, five viewports, seven fixed states -- plus the "
      + "generated-WGSL probe at both sample tiers and the high->low->high "
      + "cycle-return demonstration.",
  local: opts.local, base: opts.base, asset: opts.asset, freeze: opts.freeze,
  lanes: LANES, viewports: VIEWPORTS,
  states: STATES.map(([n, s]) => ({ state: n, ...s })),
  cacheTruthNote: "recorded on the O5F side only; the surface does not exist "
      + "at the baseline commit and is excluded from the probe comparison.",
  records, programs, cycles,
}, null, 1));
console.log(`-> ${opts.out}`);
await browser.close();
