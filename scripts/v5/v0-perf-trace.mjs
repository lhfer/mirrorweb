#!/usr/bin/env node
/**
 * Measure the Before/Candidate label cost under sustained REAL input.
 *
 * Not a visible-count argument: per frame it records the frame delta, the
 * visible label count and the classified style writes; per second the JS
 * heap; long tasks via PerformanceObserver; and on the Candidate the
 * labels.sync CPU through the QA probe (armed for the run, off otherwise).
 * The Before build predates the probe and is NOT patched to carry it --
 * patching the Before lane would make it a third candidate -- so its sync
 * cost is bounded from the full frame time instead, and the report says so.
 *
 * Scenarios (the brief's own):
 *   drag-10s        1440x900, slow horizontal drag, ~10 s
 *   flick-10s       1440x900, repeated fast flicks, ~10 s
 *   touch-wrap-20s  390x844, repeated touch drags across wraps, ~20 s
 *   landscape-20s   844x390, orientation flip then drags, ~20 s
 *
 * Usage: v0-perf-trace.mjs --out=<file> --lane=before|candidate --url=<origin>
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { mouseDrag, touchDrag, sleep } from "./m2_sequences.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { out: null, lane: "candidate", url: null };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--lane=")) opts.lane = a.slice(7);
  else if (a.startsWith("--url=")) opts.url = a.slice(6);
}

function installPerf() {
  const M = {
    armed: false, frames: [], heap: [], longTasks: 0, longTaskMs: 0,
    t0: 0, els: [], prev: [],
    writes: { transform: 0, visibility: 0, size: 0 },
  };
  window.__V0P = M;
  M.discover = () => {
    const els = [...document.querySelectorAll("#labels [data-ilg]")];
    M.els = els;
    M.prev = els.map((el) => ({ t: el.style.transform, v: el.style.visibility,
                                w: el.style.width, h: el.style.height }));
    const byEl = new Map(els.map((el, n) => [el, n]));
    M.observer = new MutationObserver((records) => {
      const touched = new Set();
      for (const r of records) touched.add(r.target);
      for (const el of touched) {
        const n = byEl.get(el);
        if (n === undefined) continue;
        const p = M.prev[n];
        if (el.style.transform !== p.t) { M.writes.transform += 1; p.t = el.style.transform; }
        if (el.style.visibility !== p.v) { M.writes.visibility += 1; p.v = el.style.visibility; }
        if (el.style.width !== p.w || el.style.height !== p.h) {
          M.writes.size += 1; p.w = el.style.width; p.h = el.style.height;
        }
      }
    });
    for (const el of els) M.observer.observe(el, { attributes: true, attributeFilter: ["style"] });
    try {
      M.lt = new PerformanceObserver((list) => {
        for (const e of list.getEntries()) { M.longTasks += 1; M.longTaskMs += e.duration; }
      });
      M.lt.observe({ entryTypes: ["longtask"] });
    } catch { /* longtask unsupported */ }
    return { labels: els.length, domNodes: document.querySelectorAll("*").length };
  };
  let last = 0;
  const sample = (t) => {
    if (!M.armed) return;
    const dt = last ? t - last : 0;
    last = t;
    let vis = 0;
    for (const el of M.els) if (el.style.visibility !== "hidden") vis += 1;
    const w = M.writes;
    M.frames.push([+dt.toFixed(3), vis, w.transform, w.visibility, w.size]);
    w.transform = 0; w.visibility = 0; w.size = 0;
    requestAnimationFrame(sample);
  };
  M.start = () => {
    M.armed = true; M.frames.length = 0; M.heap.length = 0;
    M.longTasks = 0; M.longTaskMs = 0; last = 0;
    M.t0 = performance.now();
    if (window.__ILG_QA__ && window.__ILG_QA__.setLabelSyncProbe) {
      window.__ILG_QA__.setLabelSyncProbe(true);
    }
    M.heapTimer = setInterval(() => {
      if (performance.memory) M.heap.push(performance.memory.usedJSHeapSize);
    }, 1000);
    requestAnimationFrame(sample);
  };
  M.stop = () => {
    M.armed = false;
    clearInterval(M.heapTimer);
    let sync = null;
    if (window.__ILG_QA__ && window.__ILG_QA__.getLabelSyncStats) {
      sync = window.__ILG_QA__.getLabelSyncStats();
      window.__ILG_QA__.setLabelSyncProbe(false);
    }
    let adaptive = null;
    if (window.__ILG_QA__ && window.__ILG_QA__.getAdaptiveState) {
      try { adaptive = window.__ILG_QA__.getAdaptiveState(); } catch { }
    }
    return {
      frames: M.frames, heap: M.heap,
      longTasks: M.longTasks, longTaskMs: +M.longTaskMs.toFixed(1),
      labelSync: sync, adaptive,
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
  startedAt: new Date().toISOString(), lane: opts.lane, url: opts.url,
  scenarios: [], errors: [],
};

for (const sc of SCENARIOS) {
  const [w, h] = sc.vp;
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, hasTouch: true });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 300)); });
  const cdp = await page.context().newCDPSession(page);
  try {
    await page.goto(opts.url, { waitUntil: "load", timeout: 60000 });
    await sleep(4500);
    await page.evaluate(installPerf);
    const found = await page.evaluate(() => window.__V0P.discover());
    await page.evaluate(() => window.__V0P.start());
    await drive(page, cdp, sc.name, w, h, sc.seconds);
    await sleep(1200);
    const data = await page.evaluate(() => window.__V0P.stop());
    report.scenarios.push({ name: sc.name, viewport: `${w}x${h}`, found, ...data, errors });
    process.stdout.write(`  ${opts.lane} ${sc.name}: ${data.frames.length} frames, `
      + `${data.longTasks} long tasks, errors ${errors.length}\n`);
  } catch (err) {
    report.errors.push({ scenario: sc.name, error: String(err) });
    process.stdout.write(`  ${opts.lane} ${sc.name}: ERROR ${String(err).slice(0, 160)}\n`);
  }
  await page.close();
  await ctx.close();
}
await browser.close();
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report));
process.stdout.write(`wrote ${opts.out}\n`);
