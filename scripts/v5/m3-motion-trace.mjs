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
 * it, so the scroll trajectory can be recovered exactly (see motion_trace.py)
 * without reading a private field and without touching a video frame.
 *
 * Usage:
 *   m2-motion-trace.mjs --out=<dir> [--url=<origin>] [--vps=WxH,...]
 *                       [--seqs=a,b,...] [--repeat=N] [--shots]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { SEQUENCES, runSequence } from "./m2_sequences.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";



const opts = {
  url: TARGET, local: false,
  out: path.join(REPO, "artifacts/motion/m2-target"),
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
/**
 * Installed once per page. Samples every animation frame while armed.
 *
 * WHAT CHANGED FROM THE M1 RECORDER, AND WHY
 * ------------------------------------------
 * M1 stamped every event with `performance.now()` at listener entry and every
 * frame with the rAF timestamp, and the replay then attributed an event to a
 * frame with `event.t <= frame.t`. Those are two different points in the frame
 * pipeline. Chrome dispatches input BEFORE the rAF callback block, while the
 * rAF timestamp is the frame's START time -- so an event dispatched in frame N
 * has `event.t > frame_N.t` and the rule pushed it into frame N+1.
 *
 * Measured on the M1 local traces: 90% of all recorded events fall in the
 * window `(frame.t, frame.wall]`, i.e. the rule misattributed nine events in
 * ten. It is not a small effect and it is not random -- it is one dispatch
 * frame, always in the same direction, which is why the engine-vs-contract
 * final error was 0.1457 on EVERY reverse-flick row and 0.0527 on EVERY
 * fast-flick row across four viewports and three repeats.
 *
 * A wall-clock boundary is a better heuristic but still a heuristic. What is
 * recorded here instead is the thing itself: ONE monotonically increasing
 * counter, bumped by every event listener and by every frame callback, so the
 * order in which the page's own JavaScript actually ran is a recorded fact
 * rather than something reconstructed from two clocks afterwards.
 *
 * Card transforms are read from the INLINE style string rather than through
 * getComputedStyle: both sides write `element.style.transform` directly, and a
 * computed-style read per card per frame forces a style recalculation that
 * would perturb the very frame timing being measured.
 *
 * WHAT CHANGED FROM THE M2 RECORDER, AND WHY
 * ------------------------------------------
 * The counter settled the order of events against OUR callback. It could not
 * settle the order of an event against the PAGE's own frame callback, which is
 * invisible from outside -- so M2 had to replay five release runs both ways
 * and report three of them as INSTRUMENT_SUBFRAME_RACE.
 *
 * That window is closed here by asking the engine instead of guessing. Every
 * listener reads the engine's own frame counter synchronously, in the same
 * dispatch the page's handler runs in, so how many frames the model had
 * integrated when the event arrived is a recorded number. And the model
 * records each release itself -- the full gesture history, the two points its
 * 100 ms velocity window used, the velocity that came out, and the scroll
 * target either side of the fling -- so the replay checks against what the
 * engine did rather than against a reading of what it might have done.
 *
 * ONE recorder for both sides. The only thing that differs is a feature
 * detection: where the page exposes `window.__ILG_QA__.getMotionTruth`, the
 * engine's own published state is read IN THE SAME CALLBACK as the card
 * matrices, so "what the model says" and "what the DOM shows" can never be one
 * frame apart in the artifact. The Target exposes nothing, so that field is
 * null there and every Target number still comes from its own card matrices.
 */
function installRecorder() {
  const M = {
    armed: false, frames: [], events: [], cards: [], cameraEl: null, perspEl: null,
    t0: 0,
    // The single monotone callback counter. Bumped by every listener and every
    // frame callback, in the order the browser actually ran them. This is the
    // instrument the replay reads; the two clocks are kept alongside so the
    // relationship between them stays measurable rather than assumed.
    ord: 0,
    frameIndex: 0,
    hasTruth: false,
    releaseBase: 0,
  };
  window.__M0 = M;   // name kept: the analysis scripts of both rounds read it

  /**
   * The engine's frame counter and release state, or null on a page with none.
   *
   * Deliberately four numbers and nothing else: this runs inside an input
   * listener on every pointermove, so it must not do work that could shift the
   * dispatch it is measuring.
   */
  const engineAt = () => {
    if (!M.hasTruth) return null;
    try {
      const q = window.__ILG_QA__.getMotionTruth();
      return [q.motionSteps ?? null, q.pendingReleaseCount ?? null,
              q.dragging ? 1 : 0,
              (q.releaseRecords && q.releaseRecords.length) || 0];
    } catch (err) { return null; }
  };

  const EVENTS = ["pointerdown", "pointermove", "pointerup", "pointercancel",
                  "lostpointercapture", "gotpointercapture", "wheel",
                  "touchstart", "touchmove", "touchend", "touchcancel"];
  const TERMINAL = { pointerup: 1, pointercancel: 1, touchend: 1, touchcancel: 1 };
  const CANCELLING = { pointercancel: 1, touchcancel: 1 };
  for (const type of EVENTS) {
    window.addEventListener(type, (e) => {
      if (!M.armed) return;
      const enter = performance.now() - M.t0;
      // The engine's own step counter, read INSIDE the listener.
      //
      // This is the M3 addition and it is what closes the M2 sub-frame race.
      // From outside, a pointerup dispatched between two of our sample
      // callbacks might or might not have been preceded by the page's own
      // frame callback -- and the two readings give different flings, which
      // is why M2 had to report three runs as INSTRUMENT_SUBFRAME_RACE.
      // Nothing outside can see the page's callback. But the engine counts
      // its own frames, and reading that counter here, in the same dispatch
      // the page's own handler runs in, says exactly how many frames the
      // model had integrated when this event arrived. There is then nothing
      // left to infer.
      const eng = engineAt();
      M.events.push({
        // `t` keeps the M1 meaning -- listener entry on performance.now() --
        // so a reader written for the old traces still gets what it expects.
        t: +enter.toFixed(3),
        // The browser's own stamp on the event. For a trusted event this is
        // when the input was generated, which can precede dispatch by a frame
        // or more when the compositor coalesces moves.
        timeStamp: +(e.timeStamp).toFixed(3),
        enter: +enter.toFixed(3),
        // The number the replay orders by.
        ord: ++M.ord,
        type,
        pointerId: e.pointerId ?? null, pointerType: e.pointerType ?? null,
        clientX: e.clientX ?? (e.touches && e.touches[0] ? e.touches[0].clientX : null),
        clientY: e.clientY ?? (e.touches && e.touches[0] ? e.touches[0].clientY : null),
        deltaX: e.deltaX ?? null, deltaY: e.deltaY ?? null,
        deltaMode: e.deltaMode ?? null,
        buttons: e.buttons ?? null,
        // Whether the browser generated it. The three synthetic events in the
        // suite -- deltaMode 1/2 wheels and the lostpointercapture -- are
        // marked here rather than in a comment, so a reader can separate
        // "the page ignored real input" from "the page ignored a fake event".
        isTrusted: e.isTrusted === true,
        cancelable: e.cancelable === true,
        defaultPrevented: e.defaultPrevented,
        engineStep: eng ? eng[0] : null,
        enginePendingRelease: eng ? eng[1] : null,
        engineDragging: eng ? eng[2] : null,
        engineReleaseCount: eng ? eng[3] : null,
        terminal: TERMINAL[type] === 1,
        cancelling: CANCELLING[type] === 1,
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
    M.hasTruth = typeof window.__ILG_QA__ !== "undefined"
      && typeof window.__ILG_QA__.getMotionTruth === "function";
    // Is anything sitting over the drag surface? A loading overlay that never
    // cleared would swallow every pointerdown and the trace would be a page
    // that ignored its input rather than a page with no motion model.
    const mid = document.elementFromPoint(Math.round(innerWidth / 2), Math.round(innerHeight / 2));
    return { cards: cards.length, hasCamera: !!cameraEl, hasPerspective: !!perspEl,
             hasEngineTruth: M.hasTruth,
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

  /** The 14 numbers of the engine's own state, or null on a page that has none. */
  const truthOf = () => {
    if (!M.hasTruth) return null;
    try {
      const q = window.__ILG_QA__.getMotionTruth();
      return [q.scrollX, q.scrollY, q.scrollTargetX, q.scrollTargetY,
              q.velocityX, q.velocityY, q.magnitude,
              q.pointerX, q.pointerY, q.pointerTargetX, q.pointerTargetY,
              q.dollyZ, q.dragging ? 1 : 0, q.motionSteps ?? null,
              q.releaseVelocityX ?? null, q.releaseVelocityY ?? null,
              q.lastReleaseStep ?? null, q.pendingReleaseCount ?? null];
    } catch (err) { return null; }
  };

  const sample = (rafTime) => {
    if (!M.armed) return;
    // The order counter is bumped FIRST, before anything in this callback can
    // yield, so an event listener cannot interleave into the middle of a
    // sample and take a number that makes it look like it ran earlier.
    const ord = ++M.ord;
    const enter = performance.now() - M.t0;
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
    //
    // It is the INTEGRATION clock. It is NOT an ordering clock, which is the
    // mistake the M1 replay made; ordering is `ord`.
    const t = +((rafTime ?? performance.now()) - M.t0).toFixed(3);
    // Read the engine's own state in this same callback, BEFORE the DOM read,
    // so the two are as close together as the language allows.
    const truth = truthOf();
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
      // THE RAW rAF TIMESTAMP, unrounded and with its own origin.
      //
      // `t` is that timestamp minus t0, rounded to a thousandth. That is the
      // right number to plot and the WRONG number to replay a gesture history
      // with, because the library's velocity window is a strict `>` against
      // 100 ms: a history point exactly one window old falls inside on one
      // time origin and outside on the other, purely through the last bit of
      // a double. Measured on the very first M3 smoke run -- the engine took
      // its window over 108.3 ms and a replay on the shifted clock took the
      // same gesture over 100.0 ms, a 8.3% difference in the fling from a
      // rounding difference. The engine stamps its history with THIS number,
      // so the replay is given THIS number.
      raf: rafTime ?? performance.now(),
      // performance.now() alongside, so the difference between the two clocks
      // is measurable rather than assumed away.
      wall: +enter.toFixed(3),
      enter: +enter.toFixed(3),
      ord,
      frameIndex: M.frameIndex++,
      w: window.innerWidth, h: window.innerHeight,
      camera: M.cameraEl ? M.cameraEl.style.transform || null : null,
      // The Target never calls preventDefault on a wheel event, and neither
      // does the source-exact path -- there is no listener to call it. So the
      // document's own scroll position is worth recording: "the cards did not
      // move" and "the page did not scroll" are two different claims.
      docScrollTop: (document.scrollingElement || document.documentElement).scrollTop,
      docScrollLeft: (document.scrollingElement || document.documentElement).scrollLeft,
      perspective: perspectiveOf(),
      truth,
      cards: pos,
    });
    requestAnimationFrame(sample);
  };

  M.start = () => {
    M.armed = true; M.frames.length = 0; M.events.length = 0;
    M.ord = 0; M.frameIndex = 0;
    // The engine's release log is a rolling buffer that outlives one run, so
    // remember where this run starts in it and hand back only its own.
    M.releaseBase = (() => { const e = engineAt(); return e ? e[3] : 0; })();
    // t0 on the rAF clock too: both are performance.now()-based, but the
    // origin has to be the same one the samples are measured against.
    M.t0 = performance.now();
    requestAnimationFrame(sample);
  };
  M.stop = () => { M.armed = false; return { frames: M.frames.length, events: M.events.length }; };
  /** Every release the engine recorded, exactly as it recorded it. */
  const releaseRecordsOf = () => {
    if (!M.hasTruth) return [];
    try {
      const q = window.__ILG_QA__.getMotionTruth();
      const all = q.releaseRecords || [];
      return JSON.parse(JSON.stringify(all.slice(M.releaseBase || 0)));
    } catch (err) { return []; }
  };

  M.dump = () => ({ frames: M.frames, events: M.events,
                    hasTruth: M.hasTruth,
                    releaseRecords: releaseRecordsOf(),
                    magnitudeWriterOrder: (() => {
                      if (!M.hasTruth) return null;
                      try { return window.__ILG_QA__.getMotionTruth().magnitudeWriterOrder ?? null; }
                      catch (err) { return null; }
                    })(),
                    truthFields: ["scrollX", "scrollY", "scrollTargetX", "scrollTargetY",
                                  "velocityX", "velocityY", "magnitude",
                                  "pointerX", "pointerY", "pointerTargetX", "pointerTargetY",
                                  "dollyZ", "dragging", "motionSteps",
                                  "releaseVelocityX", "releaseVelocityY",
                                  "lastReleaseStep", "pendingReleaseCount"],
                    cardCodes: M.cards.map((c) => c.code) });
  return true;
}

/* Input sequences live in m2_sequences.mjs, shared with the screen
   recorder so the gestures a reviewer watches are the gestures the gate
   measured. */

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
                      cardCodes: dump.cardCodes, hasTruth: dump.hasTruth,
                      frames: dump.frames, events: dump.events,
                      releaseRecords: dump.releaseRecords || [],
                      magnitudeWriterOrder: dump.magnitudeWriterOrder ?? null });
      run.truthFields = dump.truthFields;
      // The ordering instrument is the point of this recorder. If a run comes
      // back without it, the trace is an M1 trace wearing an M2 name and every
      // conclusion drawn from it would be the old one. Fail here, loudly.
      if (dump.frames.length && dump.frames[0].ord === undefined) {
        throw new Error(`${vp} ${seq} #${rep}: frames carry no callback order`);
      }
      if (dump.events.length && dump.events[0].ord === undefined) {
        throw new Error(`${vp} ${seq} #${rep}: events carry no callback order`);
      }
      if (opts.local && !dump.hasTruth) {
        throw new Error(`${vp} ${seq} #${rep}: local page exposed no engine truth`);
      }
      // A bundle built before the scheduling readbacks landed still answers
      // getMotionTruth() -- it just returns undefined for the fields this round
      // depends on, which reaches the analysis as a column of nulls and fails
      // somewhere far from the cause. `motionSteps` is index 13; if the served
      // build predates it, say so here.
      if (opts.local && dump.frames.length
          && !dump.frames.some((f) => f.truth && f.truth[13] !== null
                                      && f.truth[13] !== undefined)) {
        throw new Error(`${vp} ${seq} #${rep}: the served build has no motionSteps `
                        + `readback -- it predates the M2 code commit. Rebuild.`);
      }
      // M3: the release evidence has to be there, or release-history-proof.json
      // would be written from an empty list and read as "nothing to explain".
      // Every sequence in the suite that carries a pointerup or a pointercancel
      // must come back with at least one release record.
      if (opts.local && dump.events.some((e) => e.terminal)
          && (!dump.releaseRecords || dump.releaseRecords.length === 0)) {
        const started = dump.frames.some((f) => f.truth && f.truth[12] === 1);
        if (started) {
          throw new Error(`${vp} ${seq} #${rep}: the gesture ran but the engine `
                          + `recorded no release. The release readback is missing.`);
        }
      }
      if (opts.local && dump.magnitudeWriterOrder === null) {
        throw new Error(`${vp} ${seq} #${rep}: the served build exposes no `
                        + `magnitudeWriterOrder -- it predates the M3 code commit. Rebuild.`);
      }
      // A resize sequence leaves the viewport where it started, but re-assert.
      await page.setViewportSize({ width: w, height: h });
      process.stdout.write(`  ${vp} ${seq} #${rep}  frames=${dump.frames.length} events=${dump.events.length} truth=${dump.hasTruth} releases=${(dump.releaseRecords || []).length}\n`);
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
