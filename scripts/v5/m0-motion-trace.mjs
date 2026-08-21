#!/usr/bin/env node
/**
 * Drive a page with REAL input and record what its cards actually did.
 *
 * One instrument for both sides. Pointed at the Target it is the only way to
 * see the motion model run, because none of its state is reachable from the
 * page; pointed at our own page it is the same measurement, so a comparison is
 * between two pages rather than between two readers.
 *
 * Nothing here calls a QA hook to move anything. Every sequence is dispatched
 * as trusted browser input -- mouse, wheel or touch -- so what is recorded is
 * what the application's own gesture layer decided to do with it. `setOffset`
 * exists on our page and is deliberately not used: a trace produced by writing
 * the offset directly would prove nothing about the gesture layer, which is
 * the thing under test.
 *
 * The observable is the Target's own CSS3D card matrices. Its scroll lives in
 * closed-over motion values, but every card's world position is a function of
 * it, so the scroll trajectory can be recovered exactly (see m0-motion-model.py)
 * without reading a private field and without touching a video frame.
 *
 * Usage:
 *   m0-motion-trace.mjs --out=<dir> [--url=<origin>] [--vps=WxH,...]
 *                       [--seqs=a,b,...] [--repeat=N] [--shots]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";

const SEQUENCES = [
  "slow-horizontal-drag",
  "slow-vertical-drag",
  "diagonal-drag",
  "medium-drag",
  "fast-flick",
  "reverse-flick",
  "wheel-mouse-steps",
  "wheel-trackpad-small",
  "wheel-deltamode",
  "pointer-sweep",
  "touch-drag-release",
  "pointercancel",
  "lostpointercapture",
  "resize-during-motion",
  "long-drag-multi-wrap",
];

const opts = {
  url: TARGET, local: false,
  out: path.join(REPO, "artifacts/motion/target"),
  vps: ["1440x900", "390x844", "844x390", "700x700"],
  seqs: SEQUENCES.slice(), repeat: 3, shots: false, settle: 7000,
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--seqs=")) opts.seqs = a.slice(7).split(",");
  else if (a.startsWith("--repeat=")) opts.repeat = Number(a.slice(9));
  else if (a.startsWith("--settle=")) opts.settle = Number(a.slice(9));
  else if (a === "--shots") opts.shots = true;
  else if (a.startsWith("--url=")) { opts.url = a.slice(6); opts.local = true; }
}

/* ------------------------------------------------------------------ */
/* in-page recorder                                                    */
/* ------------------------------------------------------------------ */

/**
 * Installed once per page. Samples every animation frame while armed.
 *
 * Card transforms are read from the INLINE style string rather than through
 * getComputedStyle: both sides write `element.style.transform` directly, and a
 * computed-style read per card per frame forces a style recalculation that
 * would perturb the very frame timing being measured.
 */
function installRecorder() {
  const M = {
    armed: false, frames: [], events: [], cards: [], cameraEl: null, perspEl: null,
    t0: 0,
  };
  window.__M0 = M;

  const EVENTS = ["pointerdown", "pointermove", "pointerup", "pointercancel",
                  "lostpointercapture", "gotpointercapture", "wheel",
                  "touchstart", "touchmove", "touchend", "touchcancel"];
  for (const type of EVENTS) {
    window.addEventListener(type, (e) => {
      if (!M.armed) return;
      M.events.push({
        t: +(performance.now() - M.t0).toFixed(3), type,
        pointerId: e.pointerId ?? null, pointerType: e.pointerType ?? null,
        clientX: e.clientX ?? (e.touches && e.touches[0] ? e.touches[0].clientX : null),
        clientY: e.clientY ?? (e.touches && e.touches[0] ? e.touches[0].clientY : null),
        deltaX: e.deltaX ?? null, deltaY: e.deltaY ?? null,
        deltaMode: e.deltaMode ?? null,
        buttons: e.buttons ?? null,
        defaultPrevented: e.defaultPrevented,
      });
    }, { capture: true, passive: true });
  }

  M.discover = () => {
    const cards = [];
    let cameraEl = null, perspEl = null;
    for (const d of document.querySelectorAll("div")) {
      const cs = getComputedStyle(d);
      // Two ways to carry the CSS3D camera. The Target writes a real
      // `perspective` property on the host and the camera matrix on its child;
      // three.js writes `perspective(...)` as a transform FUNCTION on the
      // camera element itself. Same geometry, different spelling, and a reader
      // that only knows one of them silently reports "no camera" on the other.
      if (cameraEl === null && d.style.transform && d.style.transform.includes("perspective(")) {
        cameraEl = d;
        perspEl = d.parentElement;
      }
      if (perspEl === null && cs.perspective !== "none") {
        perspEl = d;
        const kid = d.querySelector(":scope > div");
        if (kid) cameraEl = kid;
      }
      if (!d.style.transform || !d.style.transform.includes("matrix3d")) continue;
      // textContent, not innerText: innerText is render-aware and comes back
      // empty for a card the page has hidden, which is most of them.
      const text = (d.textContent || "").replace(/\s+/g, " ").trim();
      const m = text.match(/ILG[—-]\s?(\d+)/g) || [];
      if (m.length !== 1) continue;
      const code = Number(text.match(/ILG[—-]\s?(\d+)/)[1]);
      cards.push({ code, el: d });
    }
    // Slot identity from the element when the page publishes it, so a hidden
    // card -- whose innerText is empty -- is still identifiable.
    for (const d of document.querySelectorAll("[data-ilg]")) {
      if (cards.some((c) => c.el === d)) continue;
      if (!d.style.transform || !d.style.transform.includes("matrix3d")) continue;
      cards.push({ code: Number(d.dataset.ilg), el: d });
    }
    cards.sort((a, b) => a.code - b.code);
    M.cards = cards; M.cameraEl = cameraEl; M.perspEl = perspEl;
    // Is anything sitting over the drag surface? A loading overlay that never
    // cleared would swallow every pointerdown and the trace would be a page
    // that ignored its input rather than a page with no motion model.
    const mid = document.elementFromPoint(Math.round(innerWidth / 2), Math.round(innerHeight / 2));
    return { cards: cards.length, hasCamera: !!cameraEl, hasPerspective: !!perspEl,
             visibleCards: cards.filter((c) => c.el.style.visibility !== "hidden").length,
             topElementAtCentre: mid ? `${mid.tagName}.${String(mid.className).slice(0, 90)}` : null,
             topElementZ: mid ? getComputedStyle(mid).zIndex : null };
  };

  const tail4 = (s) => {
    // The inline value is `translate(-50%,-50%) matrix3d(a,b,...,m15)` on both
    // sides, so the matrix has to be found rather than assumed to lead.
    const k = s.indexOf("matrix3d(");
    if (k < 0) return null;
    const parts = s.slice(k + 9, s.indexOf(")", k)).split(",");
    if (parts.length !== 16) return null;
    return [Number(parts[12]), Number(parts[13]), Number(parts[14])];
  };

  /** Whichever of the two spellings this page uses; "none" is not an answer. */
  const perspectiveOf = () => {
    if (M.perspEl) {
      const own = M.perspEl.style.perspective
        || getComputedStyle(M.perspEl).perspective;
      if (own && own !== "none") return own;
    }
    const t = M.cameraEl ? M.cameraEl.style.transform : "";
    const m = /perspective\(([-\d.]+)px\)/.exec(t || "");
    return m ? `${m[1]}px` : null;
  };

  const sample = (rafTime) => {
    if (!M.armed) return;
    // The rAF timestamp, not performance.now() at callback entry.
    //
    // Both pages integrate on the frame's rAF timestamp -- a spring solved in
    // closed form reads its clock straight off it. Stamping the sample with the
    // wall clock at the moment this callback happens to run instead puts the
    // scheduling jitter between the frame and this callback into the sample
    // TIME while the position it records belongs to the frame. Measured, that
    // jitter is +-5 ms against an 8.3 ms frame, so any per-frame derivative --
    // velocity, and worse, the jerk taken from it -- is divided by the wrong
    // dt. Recomputing our worst jerk on the same positions with a uniform frame
    // period cut it by 2.8x. rAF hands every callback in a frame the SAME
    // timestamp, which is the number the page itself integrated with.
    const t = +((rafTime ?? performance.now()) - M.t0).toFixed(3);
    const pos = [];
    for (const c of M.cards) {
      // Both sides stop updating the transform of a card they have culled and
      // simply hide it, so a hidden card's matrix is STALE. Recording the
      // visibility beside the matrix is what lets the reader drop those; a
      // median taken over the whole pool would be a median over frozen cards.
      if (c.el.style.visibility === "hidden") { pos.push([c.code, null, null, null]); continue; }
      const s = c.el.style.transform;
      const v = s ? tail4(s) : null;
      // The BROWSER's own projected screen box, so "was this card on screen"
      // and "did it move more than 2 px on screen" are answered by the same
      // engine that painted it, on both sides, with no projection convention
      // to re-derive from a transform string. The product brief's wrap claim
      // is in pixels; world units cannot answer it.
      const r = c.el.getBoundingClientRect();
      pos.push(v
        ? [c.code, +v[0].toFixed(4), +v[1].toFixed(4), +v[2].toFixed(4),
           +r.left.toFixed(2), +r.top.toFixed(2), +r.width.toFixed(2), +r.height.toFixed(2)]
        : [c.code, null, null, null]);
    }
    M.frames.push({
      t,
      // performance.now() alongside, so the difference between the two clocks
      // is measurable rather than assumed away.
      wall: +(performance.now() - M.t0).toFixed(3),
      w: window.innerWidth, h: window.innerHeight,
      camera: M.cameraEl ? M.cameraEl.style.transform || null : null,
      // The Target never calls preventDefault on a wheel event, and neither
      // does the source-exact path -- there is no listener to call it. So the
      // document's own scroll position is worth recording: "the cards did not
      // move" and "the page did not scroll" are two different claims.
      docScrollTop: (document.scrollingElement || document.documentElement).scrollTop,
      docScrollLeft: (document.scrollingElement || document.documentElement).scrollLeft,
      perspective: perspectiveOf(),
      cards: pos,
    });
    requestAnimationFrame(sample);
  };

  M.start = () => {
    M.armed = true; M.frames.length = 0; M.events.length = 0;
    // t0 on the rAF clock too: both are performance.now()-based, but the
    // origin has to be the same one the samples are measured against.
    M.t0 = performance.now();
    requestAnimationFrame(sample);
  };
  M.stop = () => { M.armed = false; return { frames: M.frames.length, events: M.events.length }; };
  M.dump = () => ({ frames: M.frames, events: M.events,
                    cardCodes: M.cards.map((c) => c.code) });
  return true;
}

/* ------------------------------------------------------------------ */
/* input sequences -- every one of them real browser input             */
/* ------------------------------------------------------------------ */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Straight mouse drag, `steps` moves of `dx,dy` each spaced `gap` ms. */
async function mouseDrag(page, from, dx, dy, steps, gap, release = true) {
  await page.mouse.move(from[0], from[1]);
  await page.mouse.down();
  for (let i = 1; i <= steps; i += 1) {
    await page.mouse.move(from[0] + dx * i, from[1] + dy * i);
    if (gap > 0) await sleep(gap);
  }
  if (release) await page.mouse.up();
}

async function touchDrag(cdp, from, dx, dy, steps, gap, end = "touchend") {
  const pt = (x, y) => [{ x, y, radiusX: 12, radiusY: 12, force: 1 }];
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pt(from[0], from[1]) });
  for (let i = 1; i <= steps; i += 1) {
    await cdp.send("Input.dispatchTouchEvent",
      { type: "touchMove", touchPoints: pt(from[0] + dx * i, from[1] + dy * i) });
    if (gap > 0) await sleep(gap);
  }
  if (end === "touchcancel") await cdp.send("Input.dispatchTouchEvent", { type: "touchCancel", touchPoints: [] });
  else await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

async function runSequence(page, cdp, name, w, h) {
  const cx = Math.round(w / 2), cy = Math.round(h / 2);
  const span = Math.min(w, h);
  switch (name) {
    case "slow-horizontal-drag":
      await mouseDrag(page, [cx - span * 0.3, cy], span * 0.02, 0, 30, 26);
      return { tailMs: 2600 };
    case "slow-vertical-drag":
      await mouseDrag(page, [cx, cy - span * 0.3], 0, span * 0.02, 30, 26);
      return { tailMs: 2600 };
    case "diagonal-drag":
      await mouseDrag(page, [cx - span * 0.22, cy - span * 0.22], span * 0.014, span * 0.014, 30, 26);
      return { tailMs: 2600 };
    case "medium-drag":
      await mouseDrag(page, [cx - span * 0.3, cy], span * 0.045, 0, 14, 16);
      return { tailMs: 2600 };
    case "fast-flick":
      await mouseDrag(page, [cx + span * 0.36, cy], -span * 0.09, 0, 8, 6);
      return { tailMs: 3400 };
    case "reverse-flick":
      // out, then hard back the other way without releasing in between
      await page.mouse.move(cx - span * 0.3, cy);
      await page.mouse.down();
      for (let i = 1; i <= 8; i += 1) { await page.mouse.move(cx - span * 0.3 + span * 0.07 * i, cy); await sleep(8); }
      for (let i = 1; i <= 8; i += 1) { await page.mouse.move(cx + span * 0.26 - span * 0.075 * i, cy); await sleep(6); }
      await page.mouse.up();
      return { tailMs: 3400 };
    case "wheel-mouse-steps":
      await page.mouse.move(cx, cy);
      for (let i = 0; i < 8; i += 1) { await page.mouse.wheel(0, 120); await sleep(60); }
      for (let i = 0; i < 4; i += 1) { await page.mouse.wheel(120, 0); await sleep(60); }
      return { tailMs: 2200 };
    case "wheel-trackpad-small":
      await page.mouse.move(cx, cy);
      for (let i = 0; i < 40; i += 1) { await page.mouse.wheel(2.5, 6.5); await sleep(12); }
      return { tailMs: 2200 };
    case "wheel-deltamode": {
      // deltaMode 1 (lines) and 2 (pages) cannot be produced by a real device
      // through the automation API, so they are dispatched synthetically and
      // labelled as such. The claim under test is that NO wheel listener is
      // registered at all, and an untrusted WheelEvent still reaches a
      // listener if one exists -- so absence of response is evidence either
      // way, and deltaMode 0 is additionally covered by a real wheel above.
      await page.mouse.move(cx, cy);
      for (const mode of [0, 1, 2]) {
        for (let i = 0; i < 6; i += 1) {
          await page.evaluate(([m, x, y]) => {
            const scale = m === 0 ? 100 : m === 1 ? 3 : 1;
            window.dispatchEvent(new WheelEvent("wheel", {
              deltaX: scale, deltaY: scale, deltaMode: m,
              clientX: x, clientY: y, bubbles: true, cancelable: true,
            }));
          }, [mode, cx, cy]);
          await sleep(40);
        }
        await sleep(260);
      }
      return { tailMs: 2200 };
    }
    case "pointer-sweep": {
      const pad = 6;
      const stops = [[cx, cy], [pad, pad], [w - pad, pad], [w - pad, h - pad], [pad, h - pad], [cx, cy]];
      for (const [x, y] of stops) {
        await page.mouse.move(x, y, { steps: 14 });
        await sleep(520);
      }
      return { tailMs: 1400 };
    }
    case "touch-drag-release":
      await touchDrag(cdp, [cx + span * 0.3, cy + span * 0.16], -span * 0.06, -span * 0.03, 12, 10);
      return { tailMs: 3400 };
    case "pointercancel":
      await touchDrag(cdp, [cx, cy], -span * 0.05, 0, 10, 12, "touchcancel");
      return { tailMs: 2600 };
    case "lostpointercapture": {
      // Press, drag, then take the capture away: dispatch the event the page
      // would get if something else claimed the pointer mid-gesture.
      await page.mouse.move(cx + span * 0.28, cy);
      await page.mouse.down();
      for (let i = 1; i <= 8; i += 1) { await page.mouse.move(cx + span * 0.28 - span * 0.05 * i, cy); await sleep(12); }
      await page.evaluate(() => {
        const e = new PointerEvent("lostpointercapture", { pointerId: 1, bubbles: true, cancelable: false });
        (document.elementFromPoint(window.innerWidth / 2, window.innerHeight / 2) || document.body).dispatchEvent(e);
      });
      await sleep(220);
      await page.mouse.up();
      return { tailMs: 2600 };
    }
    case "resize-during-motion": {
      await mouseDrag(page, [cx + span * 0.34, cy], -span * 0.085, 0, 8, 6);
      await sleep(120);
      await page.setViewportSize({ width: Math.round(w * 0.78), height: Math.round(h * 0.86) });
      await sleep(1200);
      await page.setViewportSize({ width: w, height: h });
      return { tailMs: 2600 };
    }
    case "long-drag-multi-wrap":
      await mouseDrag(page, [Math.round(w * 0.9), cy], -Math.round(w * 0.1), 0, 40, 14);
      return { tailMs: 3400 };
    default:
      throw new Error(`unknown sequence ${name}`);
  }
}

/* ------------------------------------------------------------------ */

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

const run = { startedAt: new Date().toISOString(), url: opts.url, local: opts.local,
              repeat: opts.repeat, sequences: opts.seqs, viewports: opts.vps, runs: [], errors: [] };

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    deviceScaleFactor: 1, hasTouch: true, isMobile: false });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  page.on("pageerror", (e) => run.errors.push(`${vp}: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") run.errors.push(`${vp}: ${m.text()}`); });
  await page.goto(opts.url, { waitUntil: "load", timeout: 120000 });
  if (opts.local) {
    await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
      undefined, { timeout: 180000 });
  }
  await page.waitForTimeout(opts.settle);
  await page.evaluate(installRecorder);
  const found = await page.evaluate(() => window.__M0.discover());

  for (const seq of opts.seqs) {
    for (let rep = 0; rep < opts.repeat; rep += 1) {
      // Settle first: every run must start from rest, or the previous run's
      // tail is inside this run's release curve.
      await page.mouse.move(Math.round(w / 2), Math.round(h / 2));
      await page.waitForTimeout(1500);
      // A dev server can reload the page under us -- an HMR update wipes the
      // recorder and every later evaluate fails on a missing global. Re-install
      // rather than crash, and record that it happened.
      const alive = await page.evaluate(() => typeof window.__M0 !== "undefined");
      if (!alive) {
        run.errors.push(`${vp} ${seq} #${rep}: recorder was gone (page reloaded); reinstalled`);
        if (opts.local) {
          await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
            undefined, { timeout: 180000 });
        }
        await page.waitForTimeout(opts.settle);
        await page.evaluate(installRecorder);
      }
      await page.evaluate(() => window.__M0.discover());
      await page.evaluate(() => window.__M0.start());
      const { tailMs } = await runSequence(page, cdp, seq, w, h);
      await page.waitForTimeout(tailMs);
      await page.evaluate(() => window.__M0.stop());
      const dump = await page.evaluate(() => window.__M0.dump());
      run.runs.push({ viewport: [w, h], id: vp, sequence: seq, repeat: rep,
                      cardCodes: dump.cardCodes, frames: dump.frames, events: dump.events });
      // A resize sequence leaves the viewport where it started, but re-assert.
      await page.setViewportSize({ width: w, height: h });
      process.stdout.write(`  ${vp} ${seq} #${rep}  frames=${dump.frames.length} events=${dump.events.length}\n`);
    }
  }
  run.cardsFound = found;
  await ctx.close();
}
await browser.close();

await mkdir(opts.out, { recursive: true });
const file = path.join(opts.out, "trace.json");
await writeFile(file, JSON.stringify(run));
console.log(`trace -> ${file}  (${run.runs.length} runs, ${run.errors.length} errors)`);
for (const e of run.errors.slice(0, 5)) console.log(`  ${e}`);
