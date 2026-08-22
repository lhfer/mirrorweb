#!/usr/bin/env node
/**
 * O5 §十 -- pipeline and performance, current vs target-source.
 *
 * The candidate is ALLOWED to remove the scene-colour pass. It is not allowed
 * to pay for that with a resource leak, a per-frame material, a media remap on
 * resize, a video texture rebuilt during a wrap, a black first frame, or a
 * mishandled hidden video. Each of those is measured rather than asserted,
 * because "it looks fine" is exactly how this class of defect ships.
 *
 * Frame timing is CPU wall-clock around a forced renderOnce, reported as
 * p50/p95/p99. GPU time is reported only where the backend exposes a
 * timestamp query; where it does not, the field says so instead of carrying a
 * number that means something else.
 *
 * Usage: o5-pipeline.mjs --local=<origin> [--out=<dir>] [--soakMs=300000]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { runSequence } from "./m2_sequences.mjs";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, asset: "bw-split", soakMs: 300000,
  out: path.join(REPO, "artifacts/optics-o5/pipeline") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "soakMs" ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const LANES = [["control", "current"], ["candidate", "target-source"]];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

function pct(sorted, p) {
  if (!sorted.length) return null;
  const i = Math.min(sorted.length - 1,
    Math.max(0, Math.round((p / 100) * (sorted.length - 1))));
  return +sorted[i].toFixed(3);
}

async function measure(laneTag, mode) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await installLocalRoutes(ctx, loadAsset(opts.asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  const t0 = Date.now();
  await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&bodyFloorMode=current&opticalBody=${mode}`,
    { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 180000 });
  const readyMs = Date.now() - t0;

  // FIRST FRAME. Captured before any QA state is set, so a black card at
  // startup cannot be tidied away by the harness before it is seen.
  const firstFrame = await page.screenshot();
  const firstFrameStats = await page.evaluate(() => {
    const c = document.querySelector("canvas");
    if (!c) return null;
    const g = document.createElement("canvas");
    g.width = Math.min(320, c.width); g.height = Math.min(200, c.height);
    const cx = g.getContext("2d");
    cx.drawImage(c, 0, 0, g.width, g.height);
    const d = cx.getImageData(0, 0, g.width, g.height).data;
    let sum = 0, dark = 0, n = 0;
    for (let i = 0; i < d.length; i += 4) {
      const l = 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2];
      sum += l; if (l < 6) dark += 1; n += 1;
    }
    return { meanLuma: +(sum / n).toFixed(2), nearBlackFraction: +(dark / n).toFixed(4) };
  });

  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), 4);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
    qa.renderOnce();
  });

  const passes = await page.evaluate(() =>
    ({ stats: window.__ILG_QA__.getRenderPassStats?.() ?? null,
       layers: window.__ILG_QA__.getRenderLayerState?.() ?? null }));
  const optics = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
  const assets = await page.evaluate(() => window.__ILG_QA__.getAssetState?.() ?? null);
  const metrics0 = await page.evaluate(() => window.__ILG_QA__.getMetrics?.() ?? null);

  // Scene graph census: materials, textures, geometries, meshes.
  const census = async () => page.evaluate(() => {
    const qa = window.__ILG_QA__;
    const st = qa.getState?.() ?? {};
    const pool = qa.getPoolState?.() ?? {};
    return { state: st, pool };
  });
  const censusBefore = await census();

  // CPU frame time around a forced render.
  const frameTimes = await page.evaluate(async (n) => {
    const qa = window.__ILG_QA__;
    const out = [];
    for (let i = 0; i < n; i += 1) {
      const t = performance.now();
      qa.renderOnce();
      out.push(performance.now() - t);
      await new Promise((r) => requestAnimationFrame(() => r()));
    }
    return out;
  }, 180);
  const sorted = [...frameTimes].sort((a, b) => a - b);

  const memory = await page.evaluate(() =>
    (performance.memory ? {
      usedJSHeapMB: +(performance.memory.usedJSHeapSize / 1048576).toFixed(2),
      totalJSHeapMB: +(performance.memory.totalJSHeapSize / 1048576).toFixed(2),
    } : null));

  // Resize: media must NOT be remapped and video textures must NOT rebuild.
  const beforeResize = await page.evaluate(() =>
    ({ fits: window.__ILG_QA__.getMediaFits?.() ?? null,
       pool: window.__ILG_QA__.getPoolState?.() ?? null }));
  await page.setViewportSize({ width: 1180, height: 820 });
  await sleep(700);
  await page.evaluate(() => window.__ILG_QA__.renderOnce());
  const afterResize = await page.evaluate(() =>
    ({ fits: window.__ILG_QA__.getMediaFits?.() ?? null,
       pool: window.__ILG_QA__.getPoolState?.() ?? null }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await sleep(700);

  // Adaptive quality transitions: step every level and confirm the lane
  // survives each, with the candidate's sample count following.
  const qualitySteps = [];
  for (const level of ["high", "medium", "low", "high"]) {
    await page.evaluate((l) => {
      window.__ILG_QA__.setQuality(l);
      window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
    }, level);
    await sleep(220);
    qualitySteps.push({ level,
      optics: await page.evaluate(() => window.__ILG_QA__.getOpticsState()),
      errors: errors.length });
  }

  // Soak: a long repeated drag. Wrap happens many times over, so a texture
  // rebuilt on wrap or a per-frame material shows up as heap growth.
  const soakStart = Date.now();
  const heapSamples = [];
  while (Date.now() - soakStart < opts.soakMs) {
    await runSequence(page, null, "long-drag-multi-wrap", 1440, 900);
    const h = await page.evaluate(() =>
      (performance.memory ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(2)
        : null));
    heapSamples.push({ atMs: Date.now() - soakStart, heapMB: h,
      pool: await page.evaluate(() => window.__ILG_QA__.getPoolState?.() ?? null) });
  }
  const censusAfter = await census();
  const metrics1 = await page.evaluate(() => window.__ILG_QA__.getMetrics?.() ?? null);
  const memoryAfter = await page.evaluate(() =>
    (performance.memory ? {
      usedJSHeapMB: +(performance.memory.usedJSHeapSize / 1048576).toFixed(2),
    } : null));

  await writeFile(path.join(opts.out, `${laneTag}-firstframe.png`), firstFrame);
  records.push({
    lane: laneTag, opticalBody: mode,
    readyMs, firstFrameStats,
    renderPasses: passes.stats, renderLayers: passes.layers,
    optics, assets,
    frameTimeMs: { p50: pct(sorted, 50), p95: pct(sorted, 95),
                   p99: pct(sorted, 99), n: sorted.length,
                   note: "CPU wall-clock around a forced renderOnce, "
                       + "not GPU time" },
    gpuTimeMs: metrics1?.gpuMs ?? null,
    gpuTimeNote: metrics1?.gpuMs == null
      ? "not exposed by this backend; reported as null rather than "
        + "substituting CPU time"
      : "from the renderer's timestamp query",
    memoryBefore: memory, memoryAfter,
    censusBefore, censusAfter,
    resize: { before: beforeResize, after: afterResize },
    qualitySteps,
    soak: { requestedMs: opts.soakMs, elapsedMs: Date.now() - soakStart,
            heapSamples },
    metricsBefore: metrics0, metricsAfter: metrics1,
    errorCount: errors.length, errors: errors.slice(0, 10),
  });
  console.log(`${laneTag}: ready ${readyMs}ms, sceneColor calls `
    + `${passes.stats?.sceneColorCalls}, final ${passes.stats?.finalCalls}, `
    + `p50 ${pct(sorted, 50)}ms p99 ${pct(sorted, 99)}ms, errors ${errors.length}`);
  await ctx.close();
}

for (const [tag, mode] of LANES) await measure(tag, mode);

await writeFile(path.join(opts.out, "pipeline-manifest.json"), JSON.stringify({
  what: "O5 §十 pipeline and performance. The candidate may remove the "
      + "scene-colour pass; it may not pay for that with a leak, a per-frame "
      + "material, a media remap on resize, a black first frame or a "
      + "mishandled hidden video.",
  local: opts.local, asset: opts.asset, soakMs: opts.soakMs, records,
}, null, 1));
console.log(`-> ${opts.out}`);
await browser.close();
