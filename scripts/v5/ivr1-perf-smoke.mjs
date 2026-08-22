#!/usr/bin/env node
/**
 * Integrated Visual Sprint 1 §十 -- the BOUNDED candidate performance smoke.
 * Ten minutes total: ~6 on a fine-pointer desktop context (drag / flick /
 * wrap + High/Medium/Low cycles), ~4 on a touch mobile context (touch drag /
 * wrap). Real input only. Samples every 5s: JS heap, the material-cache
 * truth, render pass stats, video clock, and an in-page rAF frame-time
 * collector (mean fps, p95 frame time). Every ~90s a still is captured and
 * each card-plane rect's mean luma recorded -- a near-black card rect right
 * after motion would be the black-card / pop-in symptom.
 *
 * This is a smoke, not a study: no thresholds are invented here; numbers are
 * reported raw against the O5F sealed expectations (creation constant,
 * switches zero, slopes small).
 */
import { writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = path.join(REPO, "artifacts/integrated-review/perf");
const URL = "http://127.0.0.1:5293/?review=target&qa";
const MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const INSTALL_COLLECTOR = () => {
  const host = window;
  host.__ivrPerf = { deltas: [], last: performance.now() };
  const loop = (t) => {
    const p = host.__ivrPerf;
    p.deltas.push(t - p.last);
    p.last = t;
    if (p.deltas.length > 4000) p.deltas.splice(0, 2000);
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
};

async function sample(page) {
  return page.evaluate(() => {
    const qa = window.__ILG_QA__;
    const p = window.__ivrPerf;
    const ds = p ? p.deltas.slice(-600) : [];
    const sorted = [...ds].sort((a, b) => a - b);
    const p95 = sorted.length ? sorted[Math.floor(sorted.length * 0.95)] : null;
    const mean = ds.length ? ds.reduce((a, b) => a + b, 0) / ds.length : null;
    const mem = performance.memory;
    const cache = qa.getBodyMaterialCacheTruth();
    const vids = [...document.querySelectorAll("video")];
    return {
      t: performance.now() / 1000,
      heapMB: mem ? +(mem.usedJSHeapSize / 1048576).toFixed(2) : null,
      fpsMean: mean ? +(1000 / mean).toFixed(1) : null,
      frameP95ms: p95 ? +p95.toFixed(2) : null,
      quality: qa.getState().quality,
      adaptive: qa.getAdaptiveState().enabled,
      cache: {
        cacheSize: cache.cacheSize ?? null, created: cache.created ?? cache.creationCount ?? null,
        switches: cache.switches ?? cache.switchCount ?? null,
        activeSamples: cache.activeSamples ?? null, textures: cache.info?.textures ?? null,
      },
      passStats: qa.getRenderPassStats(),
      videoTimes: vids.map((v) => +v.currentTime.toFixed(2)),
      assetReady: qa.getAssetState().ready,
    };
  });
}

async function driveDesktop(page, minutes, log) {
  const end = Date.now() + minutes * 60_000;
  let qi = 0;
  const QUALITIES = ["medium", "low", "high"];
  let lastQ = Date.now();
  while (Date.now() < end) {
    // slow drag left
    await page.mouse.move(1000, 450);
    await page.mouse.down();
    for (let i = 1; i <= 30; i++) { await page.mouse.move(1000 - i * 14, 450 - i * 2); await sleep(22); }
    await page.mouse.up();
    await sleep(900);
    // fast flick right
    await page.mouse.move(500, 470);
    await page.mouse.down();
    for (let i = 1; i <= 6; i++) { await page.mouse.move(500 + i * 60, 470); await sleep(14); }
    await page.mouse.up();
    await sleep(1600);
    // long wrap drag
    await page.mouse.move(1100, 430);
    await page.mouse.down();
    for (let i = 1; i <= 60; i++) { await page.mouse.move(1100 - i * 16, 430 + i); await sleep(16); }
    await page.mouse.up();
    await sleep(1200);
    if (Date.now() - lastQ > 55_000) {
      const q = QUALITIES[qi++ % QUALITIES.length];
      await page.evaluate((level) => {
        window.__ILG_QA__.setQuality(level);
      }, q);
      log(`quality -> ${q}`);
      lastQ = Date.now();
    }
  }
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(true));
}

async function driveMobile(page, cdp, minutes) {
  const end = Date.now() + minutes * 60_000;
  while (Date.now() < end) {
    const drag = async (x0, y0, dx, dy, steps, ms) => {
      await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: x0, y: y0, id: 1 }] });
      for (let i = 1; i <= steps; i++) {
        await cdp.send("Input.dispatchTouchEvent", { type: "touchMove",
          touchPoints: [{ x: x0 + dx * i / steps, y: y0 + dy * i / steps, id: 1 }] });
        await sleep(ms / steps);
      }
      await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    };
    await drag(300, 560, -220, -80, 30, 900);
    await sleep(1400);
    await drag(320, 480, -300, -20, 36, 1200); // wrap-length
    await sleep(900);
    await drag(120, 500, 240, 60, 24, 700);
    await sleep(1500);
  }
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(OUT, { recursive: true });
const report = { what: "§十 bounded candidate smoke", url: URL,
  startedAt: new Date().toISOString(), phases: [] };

for (const phase of [
  { name: "desktop", vp: { width: 1440, height: 900 }, touch: false, minutes: 6 },
  { name: "mobile", vp: { width: 390, height: 844 }, touch: true, minutes: 4 },
]) {
  const ctx = await browser.newContext({ viewport: phase.vp, deviceScaleFactor: 1,
    hasTouch: phase.touch, isMobile: phase.touch,
    ...(phase.touch ? { userAgent: MOBILE_UA } : {}) });
  const page = await ctx.newPage();
  const cdp = phase.touch ? await ctx.newCDPSession(page) : null;
  await page.goto(URL, { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getAssetState?.()?.ready === true,
    undefined, { timeout: 180000 });
  await page.evaluate(INSTALL_COLLECTOR);
  await sleep(1500);

  const samples = [];
  const stills = [];
  const sampler = setInterval(async () => {
    try { samples.push(await sample(page)); } catch { /* mid-navigation */ }
  }, 5000);
  const stiller = setInterval(async () => {
    try {
      const png = await page.screenshot();
      const rects = await page.evaluate(() =>
        window.__ILG_QA__.getCardPlaneRects().map((r) => r.rectPx));
      const file = `${phase.name}-still-${stills.length}.png`;
      await writeFile(path.join(OUT, file), png);
      stills.push({ file, rects });
    } catch { /* ignore */ }
  }, 90_000);

  const driver = phase.touch
    ? driveMobile(page, cdp, phase.minutes)
    : driveDesktop(page, phase.minutes, (m) => console.log(`[desktop] ${m}`));
  await driver;
  clearInterval(sampler);
  clearInterval(stiller);
  await sleep(300);
  samples.push(await sample(page));

  const heaps = samples.map((s) => s.heapMB).filter(Boolean);
  const fps = samples.map((s) => s.fpsMean).filter(Boolean);
  const p95s = samples.map((s) => s.frameP95ms).filter(Boolean);
  report.phases.push({
    ...phase, samples, stills,
    summary: {
      samples: samples.length,
      heapMB: { first: heaps[0], last: heaps[heaps.length - 1],
                min: Math.min(...heaps), max: Math.max(...heaps) },
      fpsMean: { min: Math.min(...fps), median: fps.sort((a, b) => a - b)[Math.floor(fps.length / 2)] },
      frameP95ms: { max: Math.max(...p95s), median: p95s.sort((a, b) => a - b)[Math.floor(p95s.length / 2)] },
      cacheFirst: samples[0]?.cache, cacheLast: samples[samples.length - 1]?.cache,
      videoAdvancing: samples.length > 2
        && JSON.stringify(samples[0].videoTimes) !== JSON.stringify(samples[samples.length - 1].videoTimes),
    },
  });
  console.log(`[${phase.name}] done: heap ${heaps[0]} -> ${heaps[heaps.length - 1]} MB, `
    + `fps median ${report.phases[report.phases.length - 1].summary.fpsMean.median}, `
    + `p95 ${report.phases[report.phases.length - 1].summary.frameP95ms.median} ms`);
  await ctx.close();
}
await browser.close();
await writeFile(path.join(OUT, "perf-smoke-raw.json"), JSON.stringify(report, null, 1));
console.log(`-> ${OUT}/perf-smoke-raw.json`);
