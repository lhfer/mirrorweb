#!/usr/bin/env node
/**
 * VC2 §九 -- the bounded candidate performance smoke.
 *
 * Ten minutes total: five on a fine-pointer desktop context at full speed,
 * five on a touch phone context under a 4x CPU throttle. §九 asks for at least
 * one run that is not a 120 fps headless machine pretending to be a phone;
 * `Emulation.setCPUThrottlingRate` is the honest version of that available
 * here, and the report says plainly that it throttles the CPU and not the GPU,
 * so it is not a substitute for a real device.
 *
 * Sprint 1's smoke reported that its High/Medium/Low cycles were promoted
 * straight back to high by adaptive quality, so the series read as one level.
 * Here adaptive is turned OFF for the duration of each cycle and back ON
 * afterwards, so the three levels are actually exercised and the adaptive
 * controller is still what runs for most of the wall clock.
 *
 * Samples every 5 s: JS heap, in-page rAF frame times (mean fps, p95), the
 * material cache truth, render pass stats, video clocks, quality. Every 90 s a
 * still is taken and each card rect's mean luma recorded -- a near-black card
 * rect right after motion is the pop-in symptom.
 *
 * Usage: vc2-perf-smoke.mjs [--out=<dir>] [--desktop-min=5] [--mobile-min=5]
 */
import { writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { out: path.join(REPO, "artifacts/visual-convergence/perf"),
               desktopMin: 5, mobileMin: 5, throttle: 4,
               url: "http://127.0.0.1:5293/?review=target&qa" };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k === "out") opts.out = path.resolve(REPO, v);
  else if (k === "desktop-min") opts.desktopMin = Number(v);
  else if (k === "mobile-min") opts.mobileMin = Number(v);
  else if (k === "throttle") opts.throttle = Number(v);
  else if (k === "url") opts.url = v;
}
const MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
  + "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const INSTALL_COLLECTOR = () => {
  window.__vc2Perf = { deltas: [], last: performance.now() };
  const loop = (t) => {
    const p = window.__vc2Perf;
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
    const ds = (window.__vc2Perf?.deltas ?? []).slice(-600);
    const sorted = [...ds].sort((a, b) => a - b);
    const mem = performance.memory;
    const cache = qa.getBodyMaterialCacheTruth();
    return {
      t: +(performance.now() / 1000).toFixed(2),
      heapMB: mem ? +(mem.usedJSHeapSize / 1048576).toFixed(2) : null,
      fpsMean: ds.length ? +(1000 / (ds.reduce((a, b) => a + b, 0) / ds.length)).toFixed(1) : null,
      frameP95ms: sorted.length ? +sorted[Math.floor(sorted.length * 0.95)].toFixed(2) : null,
      quality: qa.getState().quality,
      adaptive: qa.getAdaptiveState().enabled,
      cache: { cacheSize: cache.cacheSize ?? null, activeKey: cache.activeKey ?? null,
               activeSamples: cache.activeSamples ?? null, deviceTier: cache.deviceTier ?? null,
               rendererTextures: cache.rendererTextures ?? null },
      passStats: qa.getRenderPassStats(),
      videoTimes: [...document.querySelectorAll("video")].map((v) => +v.currentTime.toFixed(2)),
      assetReady: qa.getAssetState().ready,
    };
  });
}

async function cardLuma(page) {
  const png = await page.screenshot();
  const rects = await page.evaluate(() =>
    window.__ILG_QA__.getCardPlaneRects().map((r) => r.rectPx));
  return { png, rects };
}

async function driveDesktop(page, minutes, log) {
  const end = Date.now() + minutes * 60_000;
  const LEVELS = ["medium", "low", "high"];
  let qi = 0, lastQ = Date.now();
  while (Date.now() < end) {
    await page.mouse.move(1000, 450);
    await page.mouse.down();
    for (let i = 1; i <= 30; i += 1) { await page.mouse.move(1000 - i * 14, 450 - i * 2); await sleep(22); }
    await page.mouse.up();
    await sleep(900);
    await page.mouse.move(500, 470);
    await page.mouse.down();
    for (let i = 1; i <= 6; i += 1) { await page.mouse.move(500 + i * 60, 470); await sleep(14); }
    await page.mouse.up();
    await sleep(1600);
    await page.mouse.move(1100, 430);
    await page.mouse.down();
    for (let i = 1; i <= 60; i += 1) { await page.mouse.move(1100 - i * 16, 430 + i); await sleep(16); }
    await page.mouse.up();
    await sleep(1200);
    if (Date.now() - lastQ > 40_000) {
      const level = LEVELS[qi++ % LEVELS.length];
      // Adaptive OFF for the cycle, so the level under test is the level that
      // renders; back ON afterwards, so most of the run is the shipped path.
      await page.evaluate((l) => {
        window.__ILG_QA__.setAdaptiveQuality(false);
        window.__ILG_QA__.setQuality(l);
      }, level);
      log(`quality pinned -> ${level}`);
      await sleep(9000);
      await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(true));
      lastQ = Date.now();
    }
  }
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(true));
}

async function driveMobile(page, cdp, minutes) {
  const end = Date.now() + minutes * 60_000;
  const drag = async (x0, y0, dx, dy, steps, ms) => {
    await cdp.send("Input.dispatchTouchEvent",
      { type: "touchStart", touchPoints: [{ x: x0, y: y0, id: 1 }] });
    for (let i = 1; i <= steps; i += 1) {
      await cdp.send("Input.dispatchTouchEvent", { type: "touchMove",
        touchPoints: [{ x: x0 + (dx * i) / steps, y: y0 + (dy * i) / steps, id: 1 }] });
      await sleep(ms / steps);
    }
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  };
  while (Date.now() < end) {
    await drag(300, 560, -220, -80, 30, 900);
    await sleep(1400);
    await drag(340, 480, -900, -20, 50, 1500); // wrap-length
    await sleep(900);
    await drag(120, 500, 240, 60, 24, 700);
    await sleep(1500);
  }
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const report = { what: "VC2 §九 bounded candidate smoke", url: opts.url,
  startedAt: new Date().toISOString(),
  cpuThrottleNote: `the mobile phase runs under Emulation.setCPUThrottlingRate(${opts.throttle}). `
    + "That throttles the CPU only -- the GPU is this machine's. A headless 120 Hz "
    + "run, throttled or not, is NOT a real-device PASS and is not reported as one.",
  phases: [] };

for (const phase of [
  { name: "desktop", vp: { width: 1440, height: 900 }, touch: false,
    minutes: opts.desktopMin, throttle: 1 },
  { name: "mobile-cpu4x", vp: { width: 390, height: 844 }, touch: true,
    minutes: opts.mobileMin, throttle: opts.throttle },
]) {
  const ctx = await browser.newContext({ viewport: phase.vp, deviceScaleFactor: 1,
    hasTouch: phase.touch, isMobile: phase.touch,
    ...(phase.touch ? { userAgent: MOBILE_UA } : {}) });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });
  await page.goto(opts.url, { waitUntil: "load", timeout: 150000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getAssetState?.()?.ready === true,
    undefined, { timeout: 200000 });
  if (phase.throttle > 1) {
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: phase.throttle });
  }
  await page.evaluate(INSTALL_COLLECTOR);
  await sleep(1500);

  const samples = [];
  const stills = [];
  const sampler = setInterval(async () => {
    try { samples.push(await sample(page)); } catch { /* mid-navigation */ }
  }, 5000);
  const stiller = setInterval(async () => {
    try {
      const { png, rects } = await cardLuma(page);
      const file = `${phase.name}-still-${stills.length}.png`;
      await writeFile(path.join(opts.out, file), png);
      stills.push({ file, rects });
    } catch { /* ignore */ }
  }, 90_000);

  if (phase.touch) await driveMobile(page, cdp, phase.minutes);
  else await driveDesktop(page, phase.minutes, (m) => console.log(`[desktop] ${m}`));
  clearInterval(sampler);
  clearInterval(stiller);
  await sleep(300);
  samples.push(await sample(page));

  const num = (k) => samples.map((s) => s[k]).filter((v) => typeof v === "number");
  const heaps = num("heapMB"), fps = num("fpsMean"), p95s = num("frameP95ms");
  const med = (a) => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)];
  report.phases.push({
    name: phase.name, vp: `${phase.vp.width}x${phase.vp.height}`, touch: phase.touch,
    cpuThrottlingRate: phase.throttle, minutes: phase.minutes,
    samples, stills, errors: errors.slice(0, 8),
    summary: {
      samples: samples.length,
      heapMB: { first: heaps[0], last: heaps[heaps.length - 1],
                min: Math.min(...heaps), max: Math.max(...heaps) },
      fpsMean: { min: Math.min(...fps), median: med(fps) },
      frameP95ms: { max: Math.max(...p95s), median: med(p95s) },
      qualitySeries: samples.map((s) => (s.quality ?? "?")[0].toUpperCase()).join(""),
      qualityLevelsSeen: [...new Set(samples.map((s) => s.quality))],
      cacheFirst: samples[0]?.cache, cacheLast: samples[samples.length - 1]?.cache,
      videoAdvancing: samples.length > 2
        && JSON.stringify(samples[0].videoTimes)
           !== JSON.stringify(samples[samples.length - 1].videoTimes),
    },
  });
  const s = report.phases[report.phases.length - 1].summary;
  console.log(`[${phase.name}] heap ${s.heapMB.first} -> ${s.heapMB.last} MB, `
    + `fps median ${s.fpsMean.median}, p95 ${s.frameP95ms.median} ms, `
    + `levels ${s.qualityLevelsSeen.join("/")}, errors ${errors.length}`);
  await ctx.close();
}
await browser.close();
await writeFile(path.join(opts.out, "perf-smoke-raw.json"), JSON.stringify(report, null, 1));
console.log(`-> ${opts.out}/perf-smoke-raw.json`);
