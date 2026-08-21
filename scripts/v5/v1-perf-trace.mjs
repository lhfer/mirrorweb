#!/usr/bin/env node
/**
 * V1 render-culling performance under sustained REAL input -- an A/B on the
 * SAME candidate build: coverage culling ON vs OFF via the QA toggle. The
 * V0-accepted Before build cannot carry the per-pass draw-call probes (the
 * same reasoning as the labels.sync probe), and culling OFF on this build
 * IS the accepted Before behaviour -- proven separately by the pixel gate's
 * byte-identical A/B and the frozen regressions.
 *
 * Per frame: [dt, finalDrawCalls, finalTriangles, sceneColorDrawCalls,
 * glassVisible]. Per second: JS heap, renderer memory counters. Per
 * scenario: media decode state before/after (videos must keep playing and
 * advancing identically in both lanes), adaptive quality state, long tasks.
 *
 * GPU frame time is NOT instrumentable at this build: the renderer is
 * created without timestamp tracking, and enabling it is a renderer-init
 * change this round does not make. The report says so instead of faking a
 * percentile.
 *
 * A separate mode, --cycles=N, runs N repeated 5-minute drag cycles at
 * 1440x900 sampling the heap each second -- the brief's leak check.
 *
 * Usage:
 *   v1-perf-trace.mjs --url=<origin> --culling=on|off --out=<file>
 *   v1-perf-trace.mjs --url=<origin> --cycles=2 --out=<file>
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { mouseDrag, touchDrag, sleep } from "./m2_sequences.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { out: null, url: null, culling: "on", cycles: 0 };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--url=")) opts.url = a.slice(6);
  else if (a.startsWith("--culling=")) opts.culling = a.slice(10);
  else if (a.startsWith("--cycles=")) opts.cycles = Number(a.slice(9));
}
if (!opts.out || !opts.url) { console.error("--out and --url required"); process.exit(2); }

function installPerf() {
  const M = { armed: false, frames: [], heap: [], memory: [],
              longTasks: 0, longTaskMs: 0, t0: 0, last: 0 };
  window.__V1P = M;
  try {
    M.obs = new PerformanceObserver((list) => {
      for (const e of list.getEntries()) { M.longTasks += 1; M.longTaskMs += e.duration; }
    });
    M.obs.observe({ entryTypes: ["longtask"] });
  } catch { /* unsupported */ }
  const sample = (t) => {
    if (!M.armed) return;
    const q = window.__ILG_QA__;
    const dt = M.last ? t - M.last : 0;
    M.last = t;
    const p = q.getRenderPassStats();
    const g = q.getRenderCullingTruth().grid;
    M.frames.push([+dt.toFixed(2), p.finalCalls ?? -1, p.finalTriangles ?? -1,
                   p.sceneColorCalls ?? -1, g.glassVisible]);
    requestAnimationFrame(sample);
  };
  M.tick = window.setInterval(() => {
    if (!M.armed) return;
    const mem = performance.memory;
    if (mem) M.heap.push(+(mem.usedJSHeapSize / 1048576).toFixed(2));
    try {
      const info = window.__ILG_QA__.getMetrics();
      M.memory.push({ drawCalls: info.drawCalls, triangles: info.triangles });
    } catch { /* not ready */ }
  }, 1000);
  M.start = () => { M.armed = true; M.frames.length = 0; M.heap.length = 0; M.last = 0; requestAnimationFrame(sample); };
  M.stop = () => {
    M.armed = false;
    const q = window.__ILG_QA__;
    return {
      frames: M.frames, heap: M.heap,
      longTasks: M.longTasks, longTaskMs: +M.longTaskMs.toFixed(1),
      adaptive: q.getAdaptiveState(),
      media: q.getMediaState(),
      labelSync: q.getLabelSyncStats(),
      domNodes: document.querySelectorAll("*").length,
    };
  };
  return true;
}

const SCENARIOS = [
  { name: "drag-10s", vp: [1440, 900], seconds: 10 },
  { name: "flick-10s", vp: [1440, 900], seconds: 10 },
  { name: "touch-wrap-20s", vp: [390, 844], seconds: 20 },
  { name: "landscape-20s", vp: [844, 390], seconds: 20 },
];

async function drive(page, cdp, name, w, h, seconds) {
  const cx = Math.round(w / 2), cy = Math.round(h / 2);
  const span = Math.min(w, h);
  const until = Date.now() + seconds * 1000;
  switch (name) {
    case "drag-10s":
      while (Date.now() < until) {
        await mouseDrag(page, [cx - span * 0.3, cy], span * 0.02, 0, 24, 26);
        await sleep(300);
      }
      return;
    case "flick-10s":
      while (Date.now() < until) {
        await mouseDrag(page, [cx + span * 0.36, cy], -span * 0.09, 0, 8, 6);
        await sleep(900);
      }
      return;
    case "touch-wrap-20s":
      while (Date.now() < until) {
        await touchDrag(cdp, [cx + span * 0.3, cy + span * 0.2], -span * 0.055, -span * 0.02, 12, 10);
        await sleep(700);
      }
      return;
    case "landscape-20s": {
      await page.setViewportSize({ width: h, height: w });
      await sleep(1200);
      await page.setViewportSize({ width: w, height: h });
      await sleep(1200);
      while (Date.now() < until) {
        await mouseDrag(page, [cx - span * 0.3, cy], span * 0.03, 0, 16, 18);
        await sleep(400);
      }
      return;
    }
    default:
      throw new Error(`unknown scenario ${name}`);
  }
}

const browser = await chromium.launch({
  channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features",
         "--enable-precise-memory-info"],
});
const report = {
  startedAt: new Date().toISOString(), url: opts.url,
  culling: opts.culling, cycles: opts.cycles,
  gpuFrameTime: "not instrumentable at this build: the renderer is created "
                + "without timestamp tracking",
  scenarios: [], errors: [],
};

async function preparePage(ctx, w, h) {
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 300)); });
  const cdp = await page.context().newCDPSession(page);
  await page.goto(opts.url, { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await sleep(4000);
  await page.evaluate((on) => {
    window.__ILG_QA__.setRenderCulling(on);
    window.__ILG_QA__.setLabelSyncProbe(true);
  }, opts.culling === "on");
  await page.evaluate(installPerf);
  return { page, cdp, errors };
}

if (opts.cycles > 0) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const { page, cdp, errors } = await preparePage(ctx, 1440, 900);
  const cycles = [];
  for (let c = 0; c < opts.cycles; c += 1) {
    await page.evaluate(() => window.__V1P.start());
    await drive(page, cdp, "drag-10s", 1440, 900, 300);
    const data = await page.evaluate(() => window.__V1P.stop());
    cycles.push({ cycle: c + 1, heap: data.heap,
                  heapStartMB: data.heap[0] ?? null,
                  heapEndMB: data.heap[data.heap.length - 1] ?? null,
                  longTasks: data.longTasks, media: data.media.slice(0, 3) });
    process.stdout.write(`  cycle ${c + 1}: heap ${data.heap[0]} -> `
      + `${data.heap[data.heap.length - 1]} MB\n`);
  }
  report.heapCycles = cycles;
  report.errorsInPage = errors.length;
  await ctx.close();
} else {
  for (const sc of SCENARIOS) {
    const [w, h] = sc.vp;
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, hasTouch: true });
    try {
      const { page, cdp, errors } = await preparePage(ctx, w, h);
      const mediaBefore = await page.evaluate(() => window.__ILG_QA__.getMediaState());
      await page.evaluate(() => window.__V1P.start());
      await drive(page, cdp, sc.name, w, h, sc.seconds);
      await sleep(1200);
      const data = await page.evaluate(() => window.__V1P.stop());
      report.scenarios.push({ name: sc.name, viewport: `${w}x${h}`,
                              mediaBefore, ...data, errors });
      process.stdout.write(`  culling-${opts.culling} ${sc.name}: `
        + `${data.frames.length} frames, ${data.longTasks} long tasks, `
        + `errors ${errors.length}\n`);
    } catch (err) {
      report.errors.push({ scenario: sc.name, error: String(err) });
      process.stdout.write(`  ${sc.name}: ERROR ${String(err).slice(0, 160)}\n`);
    }
    await ctx.close();
  }
}
await browser.close();
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report));
process.stdout.write(`wrote ${opts.out}\n`);
