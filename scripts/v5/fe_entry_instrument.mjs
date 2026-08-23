/**
 * Final Entry Convergence §四 -- ONE cold-load recorder, both pages.
 *
 * The motion recorders in this repo all start measuring after the page has
 * settled, because every question so far was about a page that had already
 * loaded. This one has to be running BEFORE the first byte of the app: the
 * whole subject is the window between navigation start and the moment the grid
 * stops moving, and half of that window is over before an app-level QA hook
 * exists on either side.
 *
 * So it is an init script that arms a raw rAF loop on the first frame it can
 * and records, per frame, four things the entry gate needs:
 *
 *   the loader      presence, computed opacity, the percent it is showing,
 *                   and whether it is still swallowing pointer events
 *   the canvas      presence and computed opacity
 *   the card layer  how many label elements are MOUNTED, how many carry a
 *                   transform at all, and how many are visible
 *   the cards       per ILG code: screen centre, box, opacity
 *
 * Card geometry is `getBoundingClientRect`, which forces a style/layout flush.
 * That cost is real, it is paid identically on both pages, and it is reported
 * per run as `instrumentOverheadMs` rather than assumed away. Everything else
 * here is an inline-style or cached-node read and costs nothing measurable.
 *
 * Nothing in this file names either implementation. The loader is found by
 * what a loader IS -- a viewport-covering element showing "NN%" -- and cards
 * are found by the same ILG predicate every recorder in this repo has used
 * since M2. A difference in the output is a difference in the pages.
 */

export const ENTRY_RECORDER = `(() => {
  const R = {
    frames: [], overhead: 0, samples: 0, loaderEl: null, pctEl: null,
    firstFrameAt: null, marks: {}, videoFirst: {},
  };
  window.__FE = R;
  const now = () => performance.now();
  const n3 = (v) => (Number.isFinite(v) ? +v.toFixed(3) : null);

  /**
   * The loading overlay, by behaviour rather than by selector.
   *
   * A loader is a fixed element that covers the viewport and shows a
   * percentage. Both pages have exactly one such element and neither has a
   * second one, so the predicate is unambiguous on both -- and it keeps
   * working if either page renames a class.
   */
  const findLoader = () => {
    for (const el of document.body.querySelectorAll("div")) {
      const cs = getComputedStyle(el);
      if (cs.position !== "fixed") continue;
      const r = el.getBoundingClientRect();
      if (r.width < innerWidth * 0.9 || r.height < innerHeight * 0.9) continue;
      const pct = [...el.querySelectorAll("*")].find(
        (k) => k.children.length === 0 && /^\\s*\\d{1,3}\\s*%?\\s*$/.test(k.textContent || ""),
      ) || ([...el.querySelectorAll("*")].find(
        (k) => /\\d{1,3}\\s*%/.test(k.textContent || "") && k.children.length <= 2));
      if (!pct) continue;
      return { el, pctEl: pct };
    }
    return null;
  };

  /** Every mounted card label, whether or not it has ever been drawn. */
  const cardEls = () => {
    const out = [];
    for (const d of document.querySelectorAll("div")) {
      const t = d.textContent || "";
      const m = t.match(/ILG[\\u2014-]\\s?(\\d+)/g);
      if (!m || m.length !== 1) continue;
      out.push(d);
    }
    return out;
  };

  /**
   * The common ancestor of the card labels -- the CSS3D layer host. Cached,
   * because it is the anchor for the cheap per-frame mount count and it does
   * not move once the app has booted.
   */
  R.host = null;
  const findHost = (els) => {
    if (!els.length) return null;
    let h = els[0].parentElement;
    while (h && !els.every((e) => h.contains(e))) h = h.parentElement;
    return h;
  };

  /**
   * Per-frame mount census.
   *
   * MOUNTED is every direct child of the layer host: the Target renders one
   * host child per pool slot and so do we, so this is the number the §六
   * question is actually about. TRANSFORMED is how many of those carry an
   * inline matrix3d -- on both pages a label's transform is written only when
   * the card is first drawn, so this is the "ever drawn" count and NOT the
   * mounted count. The two were conflated in the previous round's evidence.
   */
  const census = (host) => {
    if (!host) return { mounted: null, transformed: null, visible: null };
    const kids = host.children;
    let tf = 0, vis = 0;
    for (let i = 0; i < kids.length; i += 1) {
      const s = kids[i].style;
      if (s.transform && s.transform.indexOf("matrix3d") >= 0) tf += 1;
      if (s.visibility !== "hidden") vis += 1;
    }
    return { mounted: kids.length, transformed: tf, visible: vis };
  };

  R.arm = () => {
    if (R.armed) return;
    R.armed = true;
    const raf = window.requestAnimationFrame.bind(window);
    const tick = () => {
      const a = now();
      const rec = { t: n3(a), rs: document.readyState };
      try {
        if (!document.body) { R.frames.push(rec); raf(tick); return; }
        if (!R.loaderEl) {
          const f = findLoader();
          if (f) { R.loaderEl = f.el; R.pctEl = f.pctEl; }
        }
        if (R.loaderEl) {
          const cs = getComputedStyle(R.loaderEl);
          rec.loader = {
            inDom: R.loaderEl.isConnected,
            opacity: n3(parseFloat(cs.opacity)),
            display: cs.display,
            pointerEvents: cs.pointerEvents,
            pct: R.pctEl ? parseInt((R.pctEl.textContent || "").replace(/\\D/g, ""), 10) : null,
          };
        } else {
          rec.loader = { inDom: false, opacity: null, display: null,
                         pointerEvents: null, pct: null };
        }

        const cv = document.querySelector("canvas");
        rec.canvas = cv
          ? { present: true, opacity: n3(parseFloat(getComputedStyle(cv).opacity)) }
          : { present: false, opacity: null };

        // Card discovery is the expensive half, so it runs only until the
        // layer exists, and after that the host's children are the census.
        if (!R.host || !R.host.isConnected) {
          const els = cardEls();
          R.host = findHost(els);
          if (R.host && R.firstFrameAt === null) R.firstFrameAt = n3(a);
        }
        rec.dom = census(R.host);
        rec.nodes = null;

        rec.cards = [];
        if (R.host) {
          const kids = R.host.children;
          for (let i = 0; i < kids.length; i += 1) {
            const el = kids[i];
            const s = el.style;
            if (!s.transform || s.transform.indexOf("matrix3d") < 0) continue;
            if (s.visibility === "hidden") continue;
            const txt = el.textContent || "";
            const m = txt.match(/ILG[\\u2014-]\\s?(\\d+)/);
            if (!m) continue;
            const r = el.getBoundingClientRect();
            if (!(r.width > 1 && r.height > 1)) continue;
            rec.cards.push([+m[1], n3(r.x + r.width / 2), n3(r.y + r.height / 2),
                            n3(r.width), n3(r.height)]);
          }
        }

        rec.videos = [];
        for (const v of document.querySelectorAll("video")) {
          rec.videos.push(n3(v.currentTime));
          if (v.currentTime > 0 && R.videoFirst[v.src || v.currentSrc] === undefined) {
            R.videoFirst[v.src || v.currentSrc] = n3(a);
          }
        }
        for (const v of (window.__o2vids || [])) {
          rec.videos.push(n3(v.currentTime));
        }

        const q = window.__ILG_QA__;
        if (q && q.getIntroState) rec.intro = q.getIntroState();
      } catch (e) {
        rec.error = String(e && e.message);
      }
      const b = now();
      R.overhead += b - a;
      R.samples += 1;
      rec.costMs = n3(b - a);
      R.frames.push(rec);
      if (R.frames.length < 6000 && !R.stopped) raf(tick);
    };
    raf(tick);
  };

  R.stop = () => { R.stopped = true; };
  R.mark = (k) => { R.marks[k] = n3(now()); };
  R.drain = () => ({
    frames: R.frames,
    marks: R.marks,
    videoFirst: R.videoFirst,
    layerFirstSeenAt: R.firstFrameAt,
    instrumentOverheadMs: n3(R.overhead),
    samples: R.samples,
    nodes: document.querySelectorAll("*").length,
    viewport: [innerWidth, innerHeight],
    dpr: devicePixelRatio,
    nav: (() => {
      const e = performance.getEntriesByType("navigation")[0];
      if (!e) return null;
      return { type: e.type, domContentLoaded: n3(e.domContentLoadedEventEnd),
               loadEvent: n3(e.loadEventEnd), transferSize: e.transferSize,
               responseEnd: n3(e.responseEnd) };
    })(),
    resources: performance.getEntriesByType("resource").length,
    fromCache: performance.getEntriesByType("resource")
      .filter((r) => r.transferSize === 0 && r.decodedBodySize > 0).length,
  });

  R.arm();
})();`;
