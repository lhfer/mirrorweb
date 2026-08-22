#!/usr/bin/env node
/**
 * O5F §七.2-6 -- three independent fifteen-minute CANDIDATE sessions and
 * three independent fifteen-minute CONTROL sessions under the identical
 * rotating workload: desktop drag/wrap, mobile touch/wrap, landscape
 * drag/wrap, quality cycles, with resize/orientation changes between every
 * phase. The workload is O5R §十二's, unchanged, so the O5F numbers answer
 * the O5R finding on its own terms.
 *
 * Three controls rather than O5R's one because the §七 thresholds are
 * control-relative: the slope window is the worst |final-third slope| a
 * control session reaches, and the trough threshold is twice the spread of
 * the control sessions' rises. One control cannot have a spread.
 *
 * Every 10-second sample carries the §五 cache truth -- UUIDs included --
 * and the renderer's own texture/geometry/program counts, so a UUID churn or
 * a texture leak is caught at the sample it happens, not inferred from the
 * heap curve.
 *
 * Usage: o5f-sessions.mjs --local=<origin> [--out=<dir>] [--minutes=15]
 *        [--sessions=3]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { runSequence } from "./m2_sequences.mjs";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, asset: "bw-split", minutes: 15, sessions: 3,
  out: path.join(REPO, "artifacts/optics-o5f/stress") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = (k === "minutes" || k === "sessions") ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const SAMPLE_MS = 10000;
const SHOT_EVERY = 6;                 // one screenshot per minute
const DESKTOP = [1440, 900];
const MOBILE = [390, 844];
const LANDSCAPE = [844, 390];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features",
         "--js-flags=--expose-gc"] });
await mkdir(opts.out, { recursive: true });
const records = [];

async function session(lane, mode, index) {
  const ctx = await browser.newContext({
    viewport: { width: DESKTOP[0], height: DESKTOP[1] }, hasTouch: true });
  await installLocalRoutes(ctx, loadAsset(opts.asset), null);
  const page = await ctx.newPage();
  // Touch phases need a CDP client: the shared sequence library dispatches
  // real Input.dispatchTouchEvent, which is what makes "mobile touch / wrap"
  // a touch test rather than a mouse test wearing a small viewport.
  const cdp = await ctx.newCDPSession(page);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  const t0 = Date.now();
  await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&bodyFloorMode=current&opticalBody=${mode}`,
    { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(
    () => window.__ILG_QA__?.getState?.()?.ready === true, undefined,
    { timeout: 180000 });
  const readyMs = Date.now() - t0;

  // The first frame, before any QA state is set, so a black card at startup
  // cannot be tidied away by the harness before it is seen.
  const firstShot = path.join(opts.out, `${lane}-s${index}-firstframe.png`);
  await page.screenshot({ path: firstShot });

  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
  });

  const probe = async () => page.evaluate(() => {
    const qa = window.__ILG_QA__;
    const vids = [...document.querySelectorAll("video")];
    const cache = qa.getBodyMaterialCacheTruth?.() ?? null;
    return {
      // §十四 -- the device-predicate inputs of THIS context, recorded so
      // the post-fix scorer verifies each context's sample expectation
      // from truth instead of assuming it.
      contextPredicate: {
        pointerCoarse: matchMedia("(pointer: coarse)").matches,
        hardwareConcurrency: navigator.hardwareConcurrency ?? 8,
        deviceMemory: navigator.deviceMemory ?? 8,
      },
      heapMB: performance.memory
        ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(2) : null,
      pool: qa.getPoolState?.() ?? null,
      cache: cache && {
        sampleLaw: cache.sampleLaw ?? null,
        deviceTier: cache.deviceTier ?? null,
        activeSamples: cache.activeSamples ?? null,
        activeKey: cache.activeKey, cacheSize: cache.cacheSize,
        materialCreationCount: cache.materialCreationCount,
        materialDisposalCount: cache.materialDisposalCount,
        cacheSwitchCount: cache.cacheSwitchCount,
        activeMaterialUuids: cache.activeMaterialUuids,
        videoTextureUuids: cache.videoTextureUuids,
        environmentUuid: cache.environmentUuid,
        rendererTextures: cache.rendererTextures,
        rendererGeometries: cache.rendererGeometries,
        rendererPrograms: cache.rendererPrograms,
      },
      optics: {
        opticalBody: qa.getOpticsState?.()?.opticalBody ?? null,
        samples: qa.getOpticsState?.()?.opticalBodySamples ?? null,
        environmentMode: qa.getOpticsState?.()?.environmentMode ?? null,
      },
      drawCalls: qa.getMetrics?.()?.drawCalls ?? null,
      videoElements: vids.length,
      videoTimes: vids.map((v) => +v.currentTime.toFixed(3)),
      videoReadyStates: vids.map((v) => v.readyState),
    };
  });

  const start = Date.now();
  const totalMs = opts.minutes * 60000;
  const samples = [];
  const qualitySteps = [];
  const shots = [];
  let phase = 0;
  while (Date.now() - start < totalMs) {
    // Rotate the workload so no phase dominates the sample.
    const p = phase % 4;
    if (p === 0) {
      await page.setViewportSize({ width: DESKTOP[0], height: DESKTOP[1] });
      await runSequence(page, null, "long-drag-multi-wrap",
        DESKTOP[0], DESKTOP[1]);
    } else if (p === 1) {
      await page.setViewportSize({ width: MOBILE[0], height: MOBILE[1] });
      await sleep(300);
      await runSequence(page, cdp, "touch-drag-release", MOBILE[0], MOBILE[1]);
      await runSequence(page, cdp, "pointercancel", MOBILE[0], MOBILE[1]);
    } else if (p === 2) {
      await page.setViewportSize({ width: LANDSCAPE[0], height: LANDSCAPE[1] });
      await sleep(300);
      await runSequence(page, null, "long-drag-multi-wrap",
        LANDSCAPE[0], LANDSCAPE[1]);
    } else {
      await page.setViewportSize({ width: DESKTOP[0], height: DESKTOP[1] });
      await sleep(300);
      for (const level of ["high", "medium", "low", "high"]) {
        await page.evaluate((l) => {
          window.__ILG_QA__.setQuality(l);
          window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
        }, level);
        await sleep(250);
        const o = await page.evaluate(() => {
          const qa = window.__ILG_QA__;
          return { samples: qa.getOpticsState().opticalBodySamples,
            creation: qa.getBodyMaterialCacheTruth?.()
              ?.materialCreationCount ?? null };
        });
        qualitySteps.push({ atMs: Date.now() - start, level,
          samples: o.samples, creation: o.creation, errors: errors.length });
      }
    }
    phase += 1;

    const s = await probe();
    samples.push({ atMs: Date.now() - start, phase: p, ...s });
    if (samples.length % SHOT_EVERY === 0) {
      const f = `${lane}-s${index}-t${Math.round((Date.now() - start) / 1000)}.png`;
      await page.screenshot({ path: path.join(opts.out, f) });
      shots.push({ atMs: Date.now() - start, file: f });
    }
    const remaining = SAMPLE_MS - ((Date.now() - start) % SAMPLE_MS);
    if (Date.now() - start < totalMs) await sleep(Math.min(remaining, 4000));
  }

  // Post-GC plateau, where the runtime lets us ask.
  const gc = await page.evaluate(async () => {
    if (typeof window.gc !== "function") return null;
    window.gc();
    await new Promise((r) => setTimeout(r, 1200));
    window.gc();
    await new Promise((r) => setTimeout(r, 1200));
    return performance.memory
      ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(2) : null;
  });

  const rec = {
    lane, opticalBody: mode, session: index, readyMs,
    minutes: opts.minutes, sampleCount: samples.length,
    firstFrame: path.basename(firstShot),
    heapStartMB: samples[0]?.heapMB ?? null,
    heapEndMB: samples.at(-1)?.heapMB ?? null,
    postGcHeapMB: gc,
    postGcAvailable: gc !== null,
    poolFirst: samples[0]?.pool ?? null,
    poolLast: samples.at(-1)?.pool ?? null,
    cacheFirst: samples[0]?.cache ?? null,
    cacheLast: samples.at(-1)?.cache ?? null,
    videoElementsFirst: samples[0]?.videoElements ?? null,
    videoElementsLast: samples.at(-1)?.videoElements ?? null,
    videoElementsMax: Math.max(...samples.map((s) => s.videoElements ?? 0)),
    qualitySteps,
    periodicShots: shots,
    errorCount: errors.length, errors: errors.slice(0, 10),
    samples,
  };
  records.push(rec);
  console.log(`${lane} s${index}: ${samples.length} samples, heap `
    + `${rec.heapStartMB} -> ${rec.heapEndMB} MB, postGC ${gc}, creation `
    + `${rec.cacheFirst?.materialCreationCount ?? "n/a"} -> `
    + `${rec.cacheLast?.materialCreationCount ?? "n/a"}, errors `
    + `${errors.length}`);
  await ctx.close();
}

for (let i = 1; i <= opts.sessions; i += 1) {
  await session("candidate", "target-source-unclamped", i);
}
for (let i = 1; i <= opts.sessions; i += 1) {
  await session("control", "current", i);
}

await writeFile(path.join(opts.out, "sessions-manifest.json"),
  JSON.stringify({
    what: "O5F §七 -- three independent fifteen-minute candidate sessions "
        + "and three control sessions under the O5R §十二 workload, "
        + "unchanged. Heap and the §五 cache truth every ten seconds.",
    local: opts.local, asset: opts.asset, minutes: opts.minutes,
    sessions: opts.sessions, sampleIntervalMs: SAMPLE_MS,
    workload: ["desktop drag / wrap", "mobile touch / wrap",
               "landscape drag / wrap",
               "quality cycle high -> medium -> low -> high",
               "resize and orientation cycles between every phase"],
    records,
  }, null, 1));
console.log(`-> ${opts.out}`);
await browser.close();
