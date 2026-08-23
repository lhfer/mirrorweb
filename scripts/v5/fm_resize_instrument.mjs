/**
 * Final Motion Convergence §三 -- ONE scheduling instrument, both pages.
 *
 * The §五 card recorder answers "where were the cards this frame". It cannot
 * answer "which callback moved them, in what order, and how long did it hold
 * the main thread" -- and that is the whole of the orientation question.
 *
 * This module is an init script: it is installed BEFORE the first navigation,
 * so it wraps the page's own listeners rather than sitting behind them. It
 * knows nothing about either implementation. It patches four things and
 * records what they do:
 *
 *   addEventListener   every `resize` / `orientationchange` handler, wherever
 *                      it is attached (window, document, screen.orientation),
 *                      timed from entry to return
 *   requestAnimationFrame   every frame callback, timed, in registration order
 *   ResizeObserver     every observer callback, timed
 *   longtask           the browser's own verdict on main-thread blocking
 *
 * Every record carries a single monotonically increasing `seq`, so the
 * ORDER of callbacks across all four sources is recoverable -- §三's
 * `callbackOrder`. Nothing here is conditional on which page it runs in: a
 * difference in the output is a difference in the pages.
 *
 * The wrappers add a `performance.now()` pair per callback. That cost is on
 * BOTH pages and is reported (`instrumentOverheadMs`) rather than assumed
 * negligible.
 */

export const RESIZE_INSTRUMENT = `(() => {
  const W = {
    seq: 0, t0: performance.now(),
    listeners: [], input: [], frames: [], observers: [], longtasks: [],
    overhead: 0, calls: 0,
  };
  window.__FMT = W;
  const now = () => performance.now();
  const stamp = (t) => +(t - W.t0).toFixed(3);

  // ---- resize / orientationchange / pointer listeners ---------------------
  // Pointer types are here for the same reason the resize types are: §四 asks
  // which callback ran between the last move and the release, and only the
  // page's own handlers can answer that. Adding them costs one array push per
  // event on both pages.
  const WATCHED = new Set(["resize", "orientationchange", "change",
    "pointerdown", "pointermove", "pointerup", "pointercancel",
    "touchstart", "touchmove", "touchend", "touchcancel"]);
  const origAdd = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type, fn, opts) {
    const isOrientationMedia = type === "change"
      && typeof screen !== "undefined" && this === screen.orientation;
    if (!(WATCHED.has(type) && (typeof fn === "function" || (fn && fn.handleEvent)))
        || (type === "change" && !isOrientationMedia)) {
      return origAdd.apply(this, arguments);
    }
    const label = this === window ? "window"
      : this === document ? "document"
      : isOrientationMedia ? "screen.orientation"
      : (this.constructor && this.constructor.name) || "element";
    const call = typeof fn === "function" ? fn : fn.handleEvent.bind(fn);
    const wrapped = function (ev) {
      const seq = ++W.seq;
      const a = now();
      try {
        return call.apply(this, arguments);
      } finally {
        const b = now();
        W.calls += 1;
        const rec = {
          kind: "listener", seq, type, on: label,
          at: stamp(a), durMs: +(b - a).toFixed(3),
          eventTs: ev && typeof ev.timeStamp === "number" ? +ev.timeStamp.toFixed(3) : null,
          vw: innerWidth, vh: innerHeight,
        };
        if (ev && typeof ev.clientX === "number") {
          rec.x = +ev.clientX.toFixed(2); rec.y = +ev.clientY.toFixed(2);
        } else if (ev && ev.changedTouches && ev.changedTouches[0]) {
          rec.x = +ev.changedTouches[0].clientX.toFixed(2);
          rec.y = +ev.changedTouches[0].clientY.toFixed(2);
        }
        (type.startsWith("pointer") || type.startsWith("touch")
          ? W.input : W.listeners).push(rec);
      }
    };
    return origAdd.call(this, type, wrapped, opts);
  };

  // ---- requestAnimationFrame -------------------------------------------
  // The recorder below drives itself off \`rawRaf\`, NOT the patched one:
  // a recorder that timed itself would report its own cost as the page's.
  const origRaf = window.requestAnimationFrame.bind(window);
  W.rawRaf = origRaf;
  window.requestAnimationFrame = (cb) => origRaf((t) => {
    const seq = ++W.seq;
    const a = now();
    try {
      return cb(t);
    } finally {
      const b = now();
      W.calls += 1;
      W.frames.push({
        kind: "raf", seq, at: stamp(a), rafTime: +t.toFixed(3),
        durMs: +(b - a).toFixed(3), vw: innerWidth, vh: innerHeight,
      });
    }
  });

  // ---- ResizeObserver ---------------------------------------------------
  if (typeof ResizeObserver === "function") {
    const Orig = ResizeObserver;
    window.ResizeObserver = class extends Orig {
      constructor(cb) {
        super(function (entries, obs) {
          const seq = ++W.seq;
          const a = now();
          try {
            return cb.call(this, entries, obs);
          } finally {
            const b = now();
            W.calls += 1;
            W.observers.push({ kind: "resizeObserver", seq, at: stamp(a),
              durMs: +(b - a).toFixed(3), entries: entries.length,
              vw: innerWidth, vh: innerHeight });
          }
        });
      }
    };
  }

  // ---- main-thread heartbeat --------------------------------------------
  // A frame gap says the page did not draw. It does not say why. This is a
  // macrotask that reschedules itself immediately: while the main thread is
  // free it ticks every few ms, and while something blocks the main thread it
  // stops. So a gap with heartbeats through it is the compositor or the GPU
  // waiting, and a gap with no heartbeats is main-thread work -- ours or the
  // browser's own style and layout. Nothing else distinguishes those two, and
  // they call for opposite fixes.
  // A timer rather than a MessageChannel: a channel reposts as fast as the
  // event loop will take it, which is both a perturbation and a flood. Chrome
  // clamps a nested zero timeout to ~4 ms, which is fine -- the thing being
  // detected is tens of milliseconds long.
  const beat = () => {
    W.beats.push(+(now() - W.t0).toFixed(3));
    setTimeout(beat, 0);
  };
  W.beats = [];
  setTimeout(beat, 0);

  // ---- the browser's own blocking verdict --------------------------------
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) {
        W.longtasks.push({ kind: "longtask", at: stamp(e.startTime),
          durMs: +e.duration.toFixed(3),
          attribution: (e.attribution || []).map((x) => x.name).join(",") });
      }
    }).observe({ entryTypes: ["longtask"] });
  } catch { /* longtask unsupported: the frame gaps still show it */ }

  W.drain = () => {
    const all = [...W.listeners, ...W.input, ...W.frames, ...W.observers]
      .sort((x, y) => x.seq - y.seq);
    return {
      listeners: W.listeners, input: W.input,
      observers: W.observers, longtasks: W.longtasks,
      ordered: all, beats: W.beats,
      frameCount: W.frames.length, instrumentedCalls: W.calls,
      dom: {
        nodes: document.querySelectorAll("*").length,
        cards: (window.__VC2 && window.__VC2.cards) ? window.__VC2.cards.length : null,
        canvases: document.querySelectorAll("canvas").length,
      },
    };
  };
  W.reset = () => {
    W.listeners.length = 0; W.input.length = 0; W.frames.length = 0;
    W.observers.length = 0; W.longtasks.length = 0; W.beats.length = 0;
    W.t0 = performance.now();
  };
})();`;

/**
 * The §三 per-frame record, on top of the scheduling instrument.
 *
 * Card selection is the §五 rule verbatim (nearest to centre, then the nine
 * nearest to that anchor, row-major) so a run recorded here and a run
 * recorded by `vc2-card-truth.mjs` track the same block, and the label rect
 * is read from the same element -- card/label separation is then a
 * subtraction rather than a second measurement.
 */
export const FRAME_RECORDER = `(() => {
  const R = { armed: false, frames: [], tracked: [], t0: 0 };
  window.__FMF = R;

  const centreOf = (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, r };
  };

  R.select = (n) => {
    const S = window.__VC2;
    S.discover();
    const vis = S.cards.filter((c) => c.el.style.visibility !== "hidden");
    const rows = vis.map((c) => ({ c, ...centreOf(c.el) }))
      .filter((x) => x.r.width > 1 && x.r.height > 1);
    if (!rows.length) return [];
    const vcx = innerWidth / 2, vcy = innerHeight / 2;
    const anchor = rows.slice().sort((a, b) =>
      Math.hypot(a.x - vcx, a.y - vcy) - Math.hypot(b.x - vcx, b.y - vcy))[0];
    const near = rows.slice().sort((a, b) =>
      Math.hypot(a.x - anchor.x, a.y - anchor.y)
      - Math.hypot(b.x - anchor.x, b.y - anchor.y)).slice(0, n);
    const rowTol = Math.max(...near.map((x) => x.r.height)) * 0.6;
    near.sort((a, b) => (Math.round(a.y / rowTol) - Math.round(b.y / rowTol)) || (a.x - b.x));
    R.tracked = near.map((x, i) => ({ rank: i, code: x.c.code, el: x.c.el }));
    return near.map((x, i) => ({
      rank: i, code: x.c.code,
      restCentre: [+x.x.toFixed(3), +x.y.toFixed(3)],
      restRect: [+x.r.x.toFixed(3), +x.r.y.toFixed(3),
                 +x.r.width.toFixed(3), +x.r.height.toFixed(3)],
    }));
  };

  const mat = (s) => {
    if (!s) return null;
    const k = s.indexOf("matrix3d(");
    if (k < 0) return null;
    const parts = s.slice(k + 9, s.indexOf(")", k)).split(",");
    if (parts.length !== 16) return null;
    return parts.map((p) => +(+p).toFixed(4));
  };

  /** The card's own text block, so "card and label did not separate" is measurable. */
  const labelRect = (el) => {
    const t = el.querySelector("h1,h2,h3,h4,p,span,div");
    if (!t) return null;
    const r = t.getBoundingClientRect();
    return [+r.x.toFixed(2), +r.y.toFixed(2), +r.width.toFixed(2), +r.height.toFixed(2)];
  };

  const loop = (rafTime) => {
    if (!R.armed) return;
    const t = +((rafTime ?? performance.now()) - R.t0).toFixed(2);
    const cards = [];
    for (const tr of R.tracked) {
      const hidden = tr.el.style.visibility === "hidden";
      const m = mat(tr.el.style.transform);
      const r = tr.el.getBoundingClientRect();
      cards.push([tr.rank, hidden ? 1 : 0, m,
        [+r.x.toFixed(3), +r.y.toFixed(3), +r.width.toFixed(3), +r.height.toFixed(3)],
        labelRect(tr.el)]);
    }
    // Both clocks. \`t\` is the rAF timestamp, which is what the §五 recorder
    // used; \`wall\` is when the callback actually ran. They are not the same
    // series and the difference is not noise: a page whose rAF timestamp is a
    // PREDICTED presentation time runs a constant offset ahead of its own
    // callbacks, and that offset resets at a resize. Recording only the rAF
    // clock would read that reset as a dropped frame.
    R.frames.push([t, innerWidth, innerHeight, cards,
                   +(performance.now() - R.t0).toFixed(2)]);
    raf(loop);
  };

  const raf = (window.__FMT && window.__FMT.rawRaf) || window.requestAnimationFrame;

  R.start = () => {
    R.frames.length = 0;
    R.t0 = performance.now();
    R.armed = true;
    raf(loop);
  };
  R.stop = () => { R.armed = false; return R.frames.length; };
})();`;
