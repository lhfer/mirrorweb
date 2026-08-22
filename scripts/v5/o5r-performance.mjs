#!/usr/bin/env node
/**
 * O5R §十二 -- performance and resource closure.
 *
 * §十二 says in as many words that a five-minute start/end heap delta is not
 * enough, and it is right: a delta of two samples cannot distinguish a leak
 * from allocation that has not yet been collected. So this runs three
 * INDEPENDENT fifteen-minute sessions on the candidate, samples every ten
 * seconds, and reports the slope over the FIRST third against the slope over
 * the FINAL third. A leak keeps climbing; a warm-up plateaus.
 *
 * The workload rotates through everything §十二 names, so no single phase can
 * dominate the sample: desktop drag and wrap, mobile touch and wrap, quality
 * cycles high -> medium -> low -> high, and resize / orientation cycles.
 *
 * Where a quantity is not exposed, the field says so rather than carrying a
 * substitute. Shader program count is the one that is not: the WebGPU backend
 * does not publish it, and reporting draw calls in its place would be
 * answering a different question.
 *
 * Usage: o5r-performance.mjs --local=<origin> [--out=<dir>] [--minutes=15]
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
  out: path.join(REPO, "artifacts/optics-o5r/performance") };
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

function slope(points) {
  // Least squares on (minutes, MB). Returns MB per minute.
  const xs = points.map((p) => p.atMs / 60000);
  const ys = points.map((p) => p.heapMB);
  const n = xs.length;
  if (n < 3) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0, den = 0;
  for (let i = 0; i < n; i += 1) {
    num += (xs[i] - mx) * (ys[i] - my);
    den += (xs[i] - mx) ** 2;
  }
  return den === 0 ? null : +(num / den).toFixed(4);
}

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
    return {
      heapMB: performance.memory
        ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(2) : null,
      pool: qa.getPoolState?.() ?? null,
      asset: qa.getAssetState?.() ?? null,
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
  const blackFrames = [];
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
        const o = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
        qualitySteps.push({ atMs: Date.now() - start, level,
          samples: o.opticalBodySamples, errors: errors.length });
      }
    }
    phase += 1;

    const s = await probe();
    samples.push({ atMs: Date.now() - start, phase: p, ...s });
    if (samples.length % SHOT_EVERY === 0) {
      const f = `${lane}-s${index}-t${Math.round((Date.now() - start) / 1000)}.png`;
      await page.screenshot({ path: path.join(opts.out, f) });
      blackFrames.push({ atMs: Date.now() - start, file: f });
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

  const third = Math.max(3, Math.floor(samples.length / 3));
  const rec = {
    lane, opticalBody: mode, session: index, readyMs,
    minutes: opts.minutes, sampleCount: samples.length,
    firstFrame: path.basename(firstShot),
    heapFirstThirdSlopeMBPerMin: slope(samples.slice(0, third)),
    heapFinalThirdSlopeMBPerMin: slope(samples.slice(-third)),
    heapStartMB: samples[0]?.heapMB ?? null,
    heapEndMB: samples.at(-1)?.heapMB ?? null,
    postGcHeapMB: gc,
    postGcAvailable: gc !== null,
    poolFirst: samples[0]?.pool ?? null,
    poolLast: samples.at(-1)?.pool ?? null,
    videoElementsFirst: samples[0]?.videoElements ?? null,
    videoElementsLast: samples.at(-1)?.videoElements ?? null,
    videoElementsMax: Math.max(...samples.map((s) => s.videoElements ?? 0)),
    qualitySteps,
    shaderProgramCount: null,
    shaderProgramNote: "not exposed by the WebGPU backend. Reported as null "
                     + "rather than substituting draw calls, which answer a "
                     + "different question.",
    blackFrameShots: blackFrames,
    errorCount: errors.length, errors: errors.slice(0, 10),
    samples,
  };
  records.push(rec);
  console.log(`${lane} s${index}: ${samples.length} samples, heap `
    + `${rec.heapStartMB} -> ${rec.heapEndMB} MB, first-third slope `
    + `${rec.heapFirstThirdSlopeMBPerMin}, final-third `
    + `${rec.heapFinalThirdSlopeMBPerMin} MB/min, postGC ${gc}, errors `
    + `${errors.length}`);
  await ctx.close();
}

for (let i = 1; i <= opts.sessions; i += 1) {
  await session("candidate", "target-source-unclamped", i);
}
await session("control", "current", 1);

await writeFile(path.join(opts.out, "performance-manifest.json"),
  JSON.stringify({
    what: "O5R §十二 -- three independent fifteen-minute candidate sessions "
        + "plus one control reference. Heap every ten seconds, slope over the "
        + "first third against the final third, post-GC plateau where the "
        + "runtime allows it.",
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
