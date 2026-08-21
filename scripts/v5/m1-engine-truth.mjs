#!/usr/bin/env node
/**
 * Is the recovered scroll the scroll, and is our engine the contract?
 *
 * Every cross-side number in this round is recovered from CSS3D card matrices,
 * because the Target's scroll is unreachable from a page script. That recovery
 * is an instrument, and an instrument used on both sides still has to be shown
 * to be right. Our page can answer that directly: it publishes its own scroll
 * through a QA hook, so the same run can carry BOTH the recovered curve and the
 * engine's own value.
 *
 * Two questions, separated:
 *   recovered vs engine truth   -- is the instrument reading the page correctly?
 *   contract replay vs truth    -- is our engine running the Target's model?
 *
 * A disagreement between our page and the Target means nothing until these two
 * are known, because either one of them could be the whole disagreement.
 *
 * Usage: m1-engine-truth.mjs [--origin=<o>] [--vps=WxH,...] [--seqs=a,b] [--out=<json>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280",
  out: path.join(REPO, "artifacts/motion/engine-truth/trace.json"),
  vps: ["1440x900", "390x844"],
  seqs: ["fast-flick", "reverse-flick", "slow-horizontal-drag", "medium-drag", "pointercancel"],
  repeat: 2, settle: 7000 };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--seqs=")) opts.seqs = a.slice(7).split(",");
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
  else if (a.startsWith("--repeat=")) opts.repeat = Number(a.slice(9));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function installRecorder() {
  const M = { armed: false, frames: [], events: [], cards: [], cameraEl: null, t0: 0 };
  window.__ET = M;
  const EVENTS = ["pointerdown", "pointermove", "pointerup", "pointercancel",
                  "touchstart", "touchmove", "touchend", "touchcancel"];
  for (const type of EVENTS) {
    window.addEventListener(type, (e) => {
      if (!M.armed) return;
      M.events.push({ t: +(performance.now() - M.t0).toFixed(3), type,
        pointerType: e.pointerType ?? null,
        clientX: e.clientX ?? (e.touches && e.touches[0] ? e.touches[0].clientX : null),
        clientY: e.clientY ?? (e.touches && e.touches[0] ? e.touches[0].clientY : null),
        deltaX: e.deltaX ?? null, deltaY: e.deltaY ?? null, deltaMode: e.deltaMode ?? null,
        defaultPrevented: e.defaultPrevented });
    }, { capture: true, passive: true });
  }
  const tail4 = (s) => {
    const k = s.indexOf("matrix3d(");
    if (k < 0) return null;
    const parts = s.slice(k + 9, s.indexOf(")", k)).split(",");
    if (parts.length !== 16) return null;
    return [Number(parts[12]), Number(parts[13]), Number(parts[14])];
  };
  M.discover = () => {
    const cards = [];
    let cameraEl = null;
    for (const d of document.querySelectorAll("div")) {
      if (cameraEl === null && d.style.transform && d.style.transform.includes("perspective(")) cameraEl = d;
      if (!d.style.transform || !d.style.transform.includes("matrix3d")) continue;
      if (d.dataset && d.dataset.ilg !== undefined) cards.push({ code: Number(d.dataset.ilg), el: d });
    }
    cards.sort((a, b) => a.code - b.code);
    M.cards = cards; M.cameraEl = cameraEl;
    return { cards: cards.length, hasCamera: !!cameraEl };
  };
  const sample = () => {
    if (!M.armed) return;
    const t = +(performance.now() - M.t0).toFixed(3);
    const pos = [];
    for (const c of M.cards) {
      if (c.el.style.visibility === "hidden") { pos.push([c.code, null, null, null]); continue; }
      const v = c.el.style.transform ? tail4(c.el.style.transform) : null;
      pos.push(v ? [c.code, +v[0].toFixed(4), +v[1].toFixed(4), +v[2].toFixed(4)]
                 : [c.code, null, null, null]);
    }
    // The engine's own answer, read on the SAME frame as the matrices, so the
    // two curves cannot be a frame apart for reasons that have nothing to do
    // with either one being wrong.
    const q = window.__ILG_QA__.getMotionTruth();
    M.frames.push({ t, w: innerWidth, h: innerHeight,
      camera: M.cameraEl ? M.cameraEl.style.transform || null : null,
      perspective: null, docScrollTop: 0, docScrollLeft: 0,
      truth: { scrollX: q.scrollX, scrollY: q.scrollY,
               scrollTargetX: q.scrollTargetX, scrollTargetY: q.scrollTargetY,
               velocityX: q.velocityX, velocityY: q.velocityY,
               magnitude: q.magnitude, dragging: q.dragging,
               pointerX: q.pointerX, pointerY: q.pointerY,
               gridX: q.gridX, gridY: q.gridY },
      cards: pos });
    requestAnimationFrame(sample);
  };
  M.start = () => { M.armed = true; M.frames.length = 0; M.events.length = 0;
                    M.t0 = performance.now(); requestAnimationFrame(sample); };
  M.stop = () => { M.armed = false; return { frames: M.frames.length, events: M.events.length }; };
  M.dump = () => ({ frames: M.frames, events: M.events, cardCodes: M.cards.map((c) => c.code) });
  return true;
}

async function mouseDrag(page, from, dx, dy, steps, gap, release = true) {
  await page.mouse.move(from[0], from[1]);
  await page.mouse.down();
  for (let i = 1; i <= steps; i += 1) {
    await page.mouse.move(from[0] + dx * i, from[1] + dy * i);
    if (gap > 0) await sleep(gap);
  }
  if (release) await page.mouse.up();
}

/** Byte-for-byte the same gestures m0-motion-trace.mjs dispatches. */
async function runSequence(page, cdp, name, w, h) {
  const cx = Math.round(w / 2), cy = Math.round(h / 2);
  const span = Math.min(w, h);
  switch (name) {
    case "slow-horizontal-drag":
      await mouseDrag(page, [cx - span * 0.3, cy], span * 0.02, 0, 30, 26);
      return { tailMs: 2600 };
    case "medium-drag":
      await mouseDrag(page, [cx - span * 0.3, cy], span * 0.045, 0, 14, 16);
      return { tailMs: 2600 };
    case "fast-flick":
      await mouseDrag(page, [cx + span * 0.36, cy], -span * 0.09, 0, 8, 6);
      return { tailMs: 3400 };
    case "reverse-flick":
      await page.mouse.move(cx - span * 0.3, cy);
      await page.mouse.down();
      for (let i = 1; i <= 8; i += 1) { await page.mouse.move(cx - span * 0.3 + span * 0.07 * i, cy); await sleep(8); }
      for (let i = 1; i <= 8; i += 1) { await page.mouse.move(cx + span * 0.26 - span * 0.075 * i, cy); await sleep(6); }
      await page.mouse.up();
      return { tailMs: 3400 };
    case "pointercancel": {
      const pt = (x, y) => [{ x, y, radiusX: 12, radiusY: 12, force: 1 }];
      await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pt(cx, cy) });
      for (let i = 1; i <= 10; i += 1) {
        await cdp.send("Input.dispatchTouchEvent",
          { type: "touchMove", touchPoints: pt(cx - span * 0.05 * i, cy) });
        await sleep(12);
      }
      await cdp.send("Input.dispatchTouchEvent", { type: "touchCancel", touchPoints: [] });
      return { tailMs: 2600 };
    }
    default: throw new Error(`unknown sequence ${name}`);
  }
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const out = { startedAt: new Date().toISOString(), origin: opts.origin,
  what: "our page's own scroll, recorded on the same frame as the card matrices, so the "
      + "recovery instrument and the engine can be judged separately",
  runs: [], errors: [] };

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    deviceScaleFactor: 1, hasTouch: true });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  page.on("pageerror", (e) => out.errors.push(`${vp}: ${e.message}`));
  await page.goto(`${opts.origin}/?qa=1&composition=sourceExact`, { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 180000 });
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  await page.waitForTimeout(opts.settle);
  await page.evaluate(`(${installRecorder.toString()})()`);
  const found = await page.evaluate(() => window.__ET.discover());
  if (!found.cards) out.errors.push(`${vp}: no cards discovered`);

  for (const seq of opts.seqs) {
    for (let rep = 0; rep < opts.repeat; rep += 1) {
      await page.evaluate(() => { window.__ILG_QA__.reset(); });
      await page.mouse.move(Math.round(w / 2), Math.round(h / 2));
      await page.waitForTimeout(1400);
      await page.evaluate(() => window.__ET.start());
      const { tailMs } = await runSequence(page, cdp, seq, w, h);
      await page.waitForTimeout(tailMs);
      await page.evaluate(() => window.__ET.stop());
      const dump = await page.evaluate(() => window.__ET.dump());
      out.runs.push({ viewport: [w, h], id: vp, sequence: seq, repeat: rep, ...dump });
      process.stdout.write(`  ${vp} ${seq} #${rep}  frames=${dump.frames.length} events=${dump.events.length}\n`);
    }
  }
  await ctx.close();
}
await browser.close();
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(out));
console.log(`engine truth -> ${opts.out}  (${out.runs.length} runs, ${out.errors.length} errors)`);
