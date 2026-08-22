#!/usr/bin/env node
/**
 * O5R -- attribute the candidate lane's heap retention to a phase, or clear it.
 *
 * The §十二 sessions established the fact: the candidate lane's GC trough rises
 * about 2 MB/min under the rotating workload where the shipped lane's is flat.
 * They cannot establish the CAUSE, because every phase runs at the same rate,
 * so "quality steps so far" and "minutes elapsed" are the same variable.
 *
 * This separates them. Four short sessions on the candidate, each running ONE
 * phase of the §十二 workload for the same wall-clock time. If the retention
 * follows the quality cycle it shows up in that arm and nowhere else; if it
 * shows up in all four, the quality rebuild is exonerated and something the
 * whole render loop does is responsible.
 *
 * The measurand is the GC trough -- the mean of the lowest tenth of samples --
 * because the raw heap sawtooths and a slope through a sawtooth mostly reports
 * where the endpoints landed. A leak raises the floor the collector can return
 * to; noise does not.
 *
 * This is DIAGNOSTIC. It does not enter the gate, and it is not a substitute
 * for the §十二 sessions, which stand as captured.
 *
 * Usage: o5r-heap-attribution.mjs --local=<origin> [--minutes=6] [--out=<dir>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { runSequence } from "./m2_sequences.mjs";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, asset: "bw-split", minutes: 6,
  out: path.join(REPO, "artifacts/optics-o5r/performance") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "minutes" ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const SAMPLE_MS = 5000;
const DESKTOP = [1440, 900];
const MOBILE = [390, 844];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// One arm per phase of the §十二 workload, plus an idle arm. The idle arm is
// the control for the whole experiment: if even a page doing nothing retains,
// none of the other arms mean anything.
const ARMS = [
  { arm: "idle", what: "no input at all, render loop only" },
  { arm: "desktop-drag", what: "long drag with multiple wraps, no resize" },
  { arm: "mobile-touch", what: "touch drag and pointercancel at 390x844" },
  { arm: "quality-cycle", what: "high -> medium -> low -> high, no drag" },
  { arm: "resize", what: "viewport and orientation cycling, no drag" },
];

function trough(values) {
  if (values.length < 6) return null;
  const s = [...values].sort((a, b) => a - b);
  const k = Math.max(1, Math.floor(values.length / 10));
  return +(s.slice(0, k).reduce((a, b) => a + b, 0) / k).toFixed(2);
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features",
         "--js-flags=--expose-gc"] });
await mkdir(opts.out, { recursive: true });
const records = [];

for (const { arm, what } of ARMS) {
  const ctx = await browser.newContext({
    viewport: { width: DESKTOP[0], height: DESKTOP[1] }, hasTouch: true });
  await installLocalRoutes(ctx, loadAsset(opts.asset), null);
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + "&reflectionSupport=geometry&bodyFloorMode=current"
    + "&opticalBody=target-source-unclamped",
    { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(
    () => window.__ILG_QA__?.getState?.()?.ready === true, undefined,
    { timeout: 180000 });
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.setAdaptiveQuality(false);
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
  });
  await sleep(2000);

  const start = Date.now();
  const totalMs = opts.minutes * 60000;
  const samples = [];
  let work = 0;
  while (Date.now() - start < totalMs) {
    if (arm === "desktop-drag") {
      await runSequence(page, null, "long-drag-multi-wrap",
        DESKTOP[0], DESKTOP[1]);
      work += 1;
    } else if (arm === "mobile-touch") {
      await page.setViewportSize({ width: MOBILE[0], height: MOBILE[1] });
      await runSequence(page, cdp, "touch-drag-release", MOBILE[0], MOBILE[1]);
      await runSequence(page, cdp, "pointercancel", MOBILE[0], MOBILE[1]);
      await page.setViewportSize({ width: DESKTOP[0], height: DESKTOP[1] });
      work += 1;
    } else if (arm === "quality-cycle") {
      for (const level of ["high", "medium", "low", "high"]) {
        await page.evaluate((l) => {
          window.__ILG_QA__.setQuality(l);
          window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
        }, level);
        work += 1;
      }
      await sleep(250);
    } else if (arm === "resize") {
      for (const [w, h] of [MOBILE, [844, 390], [700, 700], DESKTOP]) {
        await page.setViewportSize({ width: w, height: h });
        await page.evaluate(() => window.__ILG_QA__.renderOnce());
        work += 1;
      }
      await sleep(250);
    } else {
      await sleep(1000);
    }
    const heapMB = await page.evaluate(() => (performance.memory
      ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(2) : null));
    samples.push({ atMs: Date.now() - start, heapMB, work });
    const rem = SAMPLE_MS - ((Date.now() - start) % SAMPLE_MS);
    if (Date.now() - start < totalMs) await sleep(Math.min(rem, 2500));
  }

  const gc = await page.evaluate(async () => {
    if (typeof window.gc !== "function") return null;
    window.gc(); await new Promise((r) => setTimeout(r, 1500));
    window.gc(); await new Promise((r) => setTimeout(r, 1500));
    return performance.memory
      ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(2) : null;
  });

  const hs = samples.map((s) => s.heapMB).filter((v) => v !== null);
  const third = Math.max(3, Math.floor(hs.length / 3));
  const t0 = trough(hs.slice(0, third));
  const t1 = trough(hs.slice(-third));
  const rec = { arm, what, minutes: opts.minutes, samples: samples.length,
    workUnits: work,
    firstThirdTroughMB: t0, finalThirdTroughMB: t1,
    troughRiseMB: (t0 !== null && t1 !== null) ? +(t1 - t0).toFixed(2) : null,
    heapStartMB: hs[0] ?? null, heapEndMB: hs.at(-1) ?? null,
    postGcHeapMB: gc, errorCount: errors.length, series: samples };
  records.push(rec);
  console.log(`${arm.padEnd(14)} work=${String(work).padStart(4)} trough `
    + `${t0} -> ${t1}  rise ${rec.troughRiseMB} MB  postGC ${gc} errors `
    + `${errors.length}`);
  await ctx.close();
}
await browser.close();

const byArm = Object.fromEntries(records.map((r) => [r.arm, r.troughRiseMB]));
await writeFile(path.join(opts.out, "heap-attribution.json"), JSON.stringify({
  what: "DIAGNOSTIC, not part of the gate. One arm per phase of the §十二 "
      + "workload, each run alone for the same wall-clock time, so that "
      + "'quality steps so far' stops being the same variable as 'minutes "
      + "elapsed'. Measurand is the GC trough, because the raw heap sawtooths.",
  lane: "target-source-unclamped", asset: opts.asset, minutes: opts.minutes,
  sampleIntervalMs: SAMPLE_MS,
  troughRiseByArm: byArm,
  records,
}, null, 1));
console.log("\ntrough rise by arm:", JSON.stringify(byArm));
console.log(`-> ${opts.out}/heap-attribution.json`);
