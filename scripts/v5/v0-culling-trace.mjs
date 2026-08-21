#!/usr/bin/env node
/**
 * Drive a page with REAL input and record what its LABELS did -- visibility,
 * screen rect and DOM style writes, per label, per frame.
 *
 * One instrument for all three lanes (Target / Before / Candidate), the same
 * discipline as the motion rounds: pointed at the Target it reads the only
 * observable there is -- the label DOM; pointed at our pages it reads the
 * same DOM the same way, plus the engine truth where the page exposes it, so
 * a comparison is between two pages rather than between two readers.
 *
 * WHAT THIS FIXES OVER THE MOTION-ROUND DISCOVERY
 * -----------------------------------------------
 * The m2/m3 recorder discovered cards by their inline matrix3d transform. A
 * Target label that has NEVER been drawn carries no inline transform at all
 * -- it is born `visibility:hidden` and the culling never touches a culled
 * label -- so that discovery found 41 of the pool and a card first drawn
 * MID-GESTURE was invisible to the whole trace. Here the pool is enumerated
 * STRUCTURALLY: the Target's label container is the `fixed inset-0 z-5` div
 * and every label is a child of its inner wrapper, readable via textContent
 * (which, unlike innerText, is not render-aware) whether hidden or not. Our
 * page publishes `data-ilg` on every label element for the same reason.
 *
 * Per frame, per label: `null` when hidden, else the screen rect. Style
 * writes are counted by a MutationObserver per label, classified by comparing
 * the cached previous transform/visibility/size values -- the same counter on
 * every lane, so "the Candidate writes less" is a measured statement.
 *
 * Usage:
 *   v0-culling-trace.mjs --out=<dir> --lane=target|before|candidate
 *                        [--url=<origin>] [--vps=WxH,...] [--states=a,b,...]
 *                        [--settle=ms]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { runSequence, sleep } from "./m2_sequences.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";

export const STATES = [
  "rest",
  "pointer-centre",
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
  url: TARGET, lane: "target",
  out: path.join(REPO, "artifacts/culling/target"),
  vps: ["1440x900", "1920x1080", "390x844", "844x390", "700x700"],
  states: STATES.slice(), settle: 7000,
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--states=")) opts.states = a.slice(9).split(",");
  else if (a.startsWith("--settle=")) opts.settle = Number(a.slice(9));
  else if (a.startsWith("--lane=")) opts.lane = a.slice(7);
  else if (a.startsWith("--url=")) opts.url = a.slice(6);
}

function installRecorder() {
  const M = {
    armed: false, frames: [], pool: [], els: [], prev: [],
    cameraEl: null, perspEl: null, hasTruth: false,
    t0: 0, ord: 0,
    writes: { transform: 0, visibility: 0, size: 0, other: 0 },
  };
  window.__V0 = M;

  M.discover = () => {
    const found = [];
    // Our pages: every label element carries data-ilg and data-slot.
    const ours = document.querySelectorAll("#labels [data-ilg]");
    if (ours.length > 0) {
      for (const el of ours) found.push({ code: Number(el.dataset.ilg), el });
      found.sort((a, b) => Number(a.el.dataset.slot) - Number(b.el.dataset.slot));
    } else {
      // The Target: the label container is the `fixed inset-0 z-5` div; the
      // labels are the children of its single inner wrapper, in SLOT ORDER
      // (React renders them by index). textContent reads the ILG code
      // whether the label is hidden or not.
      let container = null;
      for (const d of document.querySelectorAll("div")) {
        const c = String(d.className);
        if (c.includes("fixed") && c.includes("inset-0") && c.includes("z-5")) {
          container = d;
          break;
        }
      }
      const inner = container ? container.firstElementChild : null;
      if (inner) {
        for (const el of inner.children) {
          const m = /ILG[—-]\s?(\d+)/.exec((el.textContent || ""));
          if (m) found.push({ code: Number(m[1]), el });
        }
      }
    }
    M.els = found.map((f) => f.el);
    M.pool = found.map((f) => f.code);
    M.prev = found.map((f) => ({
      t: f.el.style.transform, v: f.el.style.visibility,
      w: f.el.style.width, h: f.el.style.height,
    }));

    // CSS3D camera, both spellings (see the motion-round recorder).
    let cameraEl = null, perspEl = null;
    for (const d of document.querySelectorAll("div")) {
      if (cameraEl === null && d.style.transform && d.style.transform.includes("perspective(")) {
        cameraEl = d; perspEl = d.parentElement;
      }
      if (perspEl === null && getComputedStyle(d).perspective !== "none") {
        perspEl = d;
        const kid = d.querySelector(":scope > div");
        if (kid) cameraEl = kid;
      }
      if (cameraEl && perspEl) break;
    }
    M.cameraEl = cameraEl; M.perspEl = perspEl;
    M.hasTruth = typeof window.__ILG_QA__ !== "undefined"
      && typeof window.__ILG_QA__.getMotionTruth === "function";

    // One observer per label. Records land as a microtask after the frame's
    // writes, so a batch is attributed to the sample that FOLLOWS the frame
    // that wrote it -- the same one-frame convention on every lane. A write
    // that leaves the property value unchanged is not counted; neither side
    // performs any (both guard or cache), and what is being counted is DOM
    // style CHANGE pressure.
    const byEl = new Map(M.els.map((el, n) => [el, n]));
    M.observer = new MutationObserver((records) => {
      const touched = new Set();
      for (const r of records) touched.add(r.target);
      for (const el of touched) {
        const n = byEl.get(el);
        if (n === undefined) continue;
        const p = M.prev[n];
        let classified = false;
        if (el.style.transform !== p.t) { M.writes.transform += 1; p.t = el.style.transform; classified = true; }
        if (el.style.visibility !== p.v) { M.writes.visibility += 1; p.v = el.style.visibility; classified = true; }
        if (el.style.width !== p.w || el.style.height !== p.h) {
          M.writes.size += 1; p.w = el.style.width; p.h = el.style.height; classified = true;
        }
        if (!classified) M.writes.other += 1;
      }
    });
    for (const el of M.els) M.observer.observe(el, { attributes: true, attributeFilter: ["style"] });

    const mid = document.elementFromPoint(Math.round(innerWidth / 2), Math.round(innerHeight / 2));
    return {
      pool: M.pool.length, codes: M.pool.slice(),
      hasCamera: !!cameraEl, hasPerspective: !!perspEl, hasEngineTruth: M.hasTruth,
      visible: M.els.filter((el) => el.style.visibility !== "hidden").length,
      domNodes: document.querySelectorAll("*").length,
      topElementAtCentre: mid ? `${mid.tagName}.${String(mid.className).slice(0, 90)}` : null,
    };
  };

  const truthOf = () => {
    if (!M.hasTruth) return null;
    try {
      const q = window.__ILG_QA__.getMotionTruth();
      return [q.scrollX, q.scrollY, q.pointerX, q.pointerY, q.magnitude,
              q.dollyZ, q.dragging ? 1 : 0];
    } catch { return null; }
  };

  /** The translation column of an inline matrix3d -- the label's world position. */
  const tail3 = (s) => {
    const k = s ? s.indexOf("matrix3d(") : -1;
    if (k < 0) return [null, null, null];
    const parts = s.slice(k + 9, s.indexOf(")", k)).split(",");
    if (parts.length !== 16) return [null, null, null];
    return [Number(parts[12]), Number(parts[13]), Number(parts[14])];
  };

  const sample = (rafTime) => {
    if (!M.armed) return;
    const ord = ++M.ord;
    const t = +((rafTime ?? performance.now()) - M.t0).toFixed(3);
    const truth = truthOf();
    const labels = [];
    for (const el of M.els) {
      if (el.style.visibility === "hidden") { labels.push(null); continue; }
      const r = el.getBoundingClientRect();
      const [wx, wy, wz] = tail3(el.style.transform);
      // [worldX, worldY, worldZ, rectX, rectY, rectW, rectH]. The world
      // position lets the offline replay recover the ABSOLUTE scroll of a
      // lane that publishes no truth (the Target), by inverting the slot
      // placement formula per live card.
      labels.push([wx, wy, wz,
                   +r.x.toFixed(2), +r.y.toFixed(2), +r.width.toFixed(2), +r.height.toFixed(2)]);
    }
    const w = M.writes;
    M.frames.push({
      t, ord, w: innerWidth, h: innerHeight,
      camera: M.cameraEl ? M.cameraEl.style.transform : null,
      perspective: M.perspEl
        ? (M.perspEl.style.perspective || getComputedStyle(M.perspEl).perspective) : null,
      truth, labels,
      writes: [w.transform, w.visibility, w.size, w.other],
    });
    w.transform = 0; w.visibility = 0; w.size = 0; w.other = 0;
    requestAnimationFrame(sample);
  };

  M.start = () => {
    M.armed = true; M.frames.length = 0; M.ord = 0;
    M.t0 = performance.now();
    const w = M.writes;
    w.transform = 0; w.visibility = 0; w.size = 0; w.other = 0;
    requestAnimationFrame(sample);
  };
  M.stop = () => { M.armed = false; return M.frames.length; };

  /** Our pages only: the full per-slot verdict payload, for bit-exact replay checks. */
  M.snapshot = () => {
    if (typeof window.__ILG_QA__ === "undefined"
        || typeof window.__ILG_QA__.getLabelTruth !== "function") return null;
    try { return window.__ILG_QA__.getLabelTruth(); } catch { return null; }
  };
  return true;
}

/** Drive one state. Returns { tailMs, snapshotAtEnd }. */
async function runState(page, cdp, state, w, h) {
  const cx = Math.round(w / 2), cy = Math.round(h / 2);
  const pad = 6;
  switch (state) {
    case "rest":
      await sleep(1500);
      return { snapshotAtEnd: true };
    case "pointer-centre":
      await page.mouse.move(cx, cy, { steps: 12 });
      await sleep(1700);
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
  startedAt: new Date().toISOString(), url: opts.url, lane: opts.lane,
  viewports: opts.vps, states: opts.states,
  runs: [], errors: [],
};

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({
    viewport: { width: w, height: h },
    hasTouch: true,
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
      await page.goto(opts.url, { waitUntil: "load", timeout : 60000 });
      await sleep(opts.settle);
      await page.evaluate(installRecorder);
      const found = await page.evaluate(() => window.__V0.discover());
      await page.evaluate(() => window.__V0.start());
      const { snapshotAtEnd } = await runState(page, cdp, state, w, h);
      const frames = await page.evaluate(() => window.__V0.stop());
      const snapshot = snapshotAtEnd
        ? await page.evaluate(() => window.__V0.snapshot()) : null;
      const data = await page.evaluate(() => ({
        pool: window.__V0.pool, frames: window.__V0.frames,
      }));
      trace.runs.push({
        viewport: vp, state, found, frameCount: frames,
        pool: data.pool, frames: data.frames,
        snapshot, errors,
      });
      process.stdout.write(`  ${opts.lane} ${vp} ${state}: pool ${found.pool}, `
        + `visible ${found.visible}, frames ${frames}, errors ${errors.length}\n`);
    } catch (err) {
      trace.errors.push({ viewport: vp, state, error: String(err) });
      process.stdout.write(`  ${opts.lane} ${vp} ${state}: ERROR ${String(err).slice(0, 200)}\n`);
    }
    await page.close();
  }
  await ctx.close();
}

await browser.close();
const outFile = path.join(opts.out, "culling-trace.json");
await writeFile(outFile, JSON.stringify(trace));
process.stdout.write(`wrote ${outFile} (${trace.runs.length} runs, ${trace.errors.length} errors)\n`);
