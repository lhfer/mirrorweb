#!/usr/bin/env node
/**
 * V1 render-culling trace: what the WebGL card meshes ACTUALLY carried,
 * per slot, per frame, under real input.
 *
 * The Target's mesh state is not readable from outside -- its side of the
 * gate is the byte-anchored rule replay (the same python twin the V0 label
 * gate uses). This instrument records the CANDIDATE's own truth: the
 * effective visibility the one applier composed, the label DOM the same
 * verdict drove, the engine truth to replay against, and the per-pass draw
 * stats. One recorder, injected page-side, sampling on the page's own rAF.
 *
 * Usage:
 *   v1-render-trace.mjs --url=<origin> --out=<dir>
 *                       [--vps=WxH,...] [--states=a,b,...] [--settle=ms]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { runSequence, sleep } from "./m2_sequences.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

export const STATES = [
  "rest",
  "pointer-corner-tl",
  "pointer-corner-tr",
  "pointer-corner-br",
  "pointer-corner-bl",
  "slow-horizontal-drag",
  "fast-flick",
  "reverse-flick",
  "touch-drag-release",
  "long-drag-multi-wrap",
  "resize-settle",
  "orientation-flip",
];

const opts = {
  url: null,
  out: path.join(REPO, "artifacts/render-culling/candidate"),
  vps: ["1440x900", "1920x1080", "390x844", "844x390", "700x700"],
  states: STATES.slice(), settle: 7000,
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--states=")) opts.states = a.slice(9).split(",");
  else if (a.startsWith("--settle=")) opts.settle = Number(a.slice(9));
  else if (a.startsWith("--url=")) opts.url = a.slice(6);
}
if (!opts.url) {
  console.error("--url is required");
  process.exit(2);
}

function installRecorder() {
  const M = { armed: false, frames: [], t0: 0, ord: 0 };
  window.__V1 = M;

  const sample = (rafTime) => {
    if (!M.armed) return;
    M.ord += 1;
    const q = window.__ILG_QA__;
    const t = +((rafTime ?? performance.now()) - M.t0).toFixed(3);
    let truth = null;
    try {
      const m = q.getMotionTruth();
      truth = [m.scrollX, m.scrollY, m.pointerX, m.pointerY, m.magnitude,
               m.dollyZ, m.dragging ? 1 : 0];
    } catch { /* not ready */ }
    // Effective flags read off the scene, packed as visible slot indices.
    const rct = q.getRenderCullingTruth();
    const glassIdx = [];
    const mediaIdx = [];
    let shellCount = 0;
    let coverageIdx = [];
    for (const s of rct.slots) {
      if (!s.active) continue;
      if (s.effectiveGlassVisible) glassIdx.push(s.slotIndex);
      if (s.effectiveShellVisible) shellCount += 1;
      if (s.effectiveMediaVisible) mediaIdx.push(s.slotIndex);
      if (s.coverageVisible) coverageIdx.push(s.slotIndex);
    }
    // The label DOM the same verdict drove, read the same way the V0
    // instrument read it.
    const labelIdx = [];
    for (const el of document.querySelectorAll("#labels [data-ilg]")) {
      if (el.style.visibility !== "hidden") {
        labelIdx.push(Number(el.dataset.slot));
      }
    }
    M.frames.push({
      t, ord: M.ord, w: innerWidth, h: innerHeight,
      truth,
      renderCulling: rct.renderCulling,
      activeSlots: rct.grid.activeSlots,
      glassIdx, shellCount, mediaCount: mediaIdx.length,
      coverageIdx: coverageIdx.length === glassIdx.length
        && coverageIdx.every((v, i) => v === glassIdx[i]) ? null : coverageIdx,
      labelIdx,
      pass: q.getRenderPassStats(),
    });
    requestAnimationFrame(sample);
  };
  M.start = () => {
    M.armed = true;
    M.frames.length = 0;
    M.ord = 0;
    M.t0 = performance.now();
    requestAnimationFrame(sample);
  };
  M.stop = () => { M.armed = false; return M.frames.length; };
  M.snapshot = () => {
    const q = window.__ILG_QA__;
    return {
      renderCullingTruth: q.getRenderCullingTruth(),
      labelTruth: q.getLabelTruth(),
      layerState: q.getRenderLayerState(),
      metrics: q.getMetrics(),
    };
  };
  return true;
}

async function runState(page, cdp, state, w, h) {
  const pad = 6;
  switch (state) {
    case "rest":
      await sleep(1500);
      return { snapshotAtEnd: true };
    case "pointer-corner-tl":
      await page.mouse.move(pad, pad, { steps: 12 });
      await sleep(1700);
      return { snapshotAtEnd: true };
    case "pointer-corner-tr":
      await page.mouse.move(w - pad, pad, { steps: 12 });
      await sleep(1700);
      return { snapshotAtEnd: true };
    case "pointer-corner-br":
      await page.mouse.move(w - pad, h - pad, { steps: 12 });
      await sleep(1700);
      return { snapshotAtEnd: true };
    case "pointer-corner-bl":
      await page.mouse.move(pad, h - pad, { steps: 12 });
      await sleep(1700);
      return { snapshotAtEnd: true };
    case "resize-settle": {
      const w2 = Math.round(w * 0.78), h2 = Math.round(h * 0.86);
      await page.setViewportSize({ width: w2, height: h2 });
      await sleep(1500);
      await page.setViewportSize({ width: w, height: h });
      await sleep(1500);
      return { snapshotAtEnd: true };
    }
    case "orientation-flip": {
      await page.setViewportSize({ width: h, height: w });
      await sleep(1500);
      await page.setViewportSize({ width: w, height: h });
      await sleep(1500);
      return { snapshotAtEnd: true };
    }
    default: {
      const r = await runSequence(page, cdp, state, w, h);
      await sleep(r.tailMs ?? 2600);
      return { snapshotAtEnd: false };
    }
  }
}

const browser = await chromium.launch({
  channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
});
await mkdir(opts.out, { recursive: true });
const trace = {
  startedAt: new Date().toISOString(), url: opts.url,
  viewports: opts.vps, states: opts.states, runs: [], errors: [],
};

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({
    viewport: { width: w, height: h }, hasTouch: true,
  });
  for (const state of opts.states) {
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push({ kind: "pageerror", text: String(e) }));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push({ kind: "console", text: m.text().slice(0, 400) });
    });
    const cdp = await page.context().newCDPSession(page);
    try {
      await page.goto(opts.url, { waitUntil: "load", timeout: 60000 });
      await page.waitForFunction(
        () => window.__ILG_QA__?.getState?.()?.ready === true,
        undefined, { timeout: 120000 });
      await sleep(opts.settle);
      await page.evaluate(installRecorder);
      await page.evaluate(() => window.__V1.start());
      const { snapshotAtEnd } = await runState(page, cdp, state, w, h);
      const frames = await page.evaluate(() => window.__V1.stop());
      const snapshot = snapshotAtEnd
        ? await page.evaluate(() => window.__V1.snapshot()) : null;
      const data = await page.evaluate(() => ({ frames: window.__V1.frames }));
      // O2 instrument update: the shell law is MODE-AWARE. Record the
      // applied shell mode as engine truth so the gate can assert the
      // right pairing (off -> zero shells; otherwise shell==glass).
      const shellMode = await page.evaluate(() =>
        window.__ILG_QA__.getOpticsState?.()?.shellModeApplied
        ?? "energy-controlled");
      trace.runs.push({ viewport: vp, state, shellMode, frameCount: frames,
                        frames: data.frames, snapshot, errors });
      process.stdout.write(`  v1 ${vp} ${state}: frames ${frames}, `
        + `errors ${errors.length}\n`);
    } catch (err) {
      trace.errors.push({ viewport: vp, state, error: String(err) });
      process.stdout.write(`  v1 ${vp} ${state}: ERROR ${String(err).slice(0, 200)}\n`);
    }
    await page.close();
  }
  await ctx.close();
}
await browser.close();
const outFile = path.join(opts.out, "render-trace.json");
await writeFile(outFile, JSON.stringify(trace));
process.stdout.write(`wrote ${outFile} (${trace.runs.length} runs, ${trace.errors.length} errors)\n`);
