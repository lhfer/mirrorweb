#!/usr/bin/env node
/**
 * Clipping and depth order for the source-exact type layer.
 *
 * Three questions, each answered by measurement rather than by looking at a
 * screenshot:
 *
 *  1. Is the clip the Target's clip? Its label has exactly one clipping box --
 *     an absolute layer at the card box with `overflow: hidden` -- and no
 *     clip-path or border-radius. Structural check against the Target's own
 *     measured values.
 *
 *  2. Can a title collide with a neighbour's? For every pair of cards whose
 *     silhouettes do NOT overlap on screen, their title boxes must not overlap
 *     either. Pairs that DO overlap are an occlusion case, not a collision, and
 *     are handled by (3).
 *
 *  3. Does a rear card's text paint over a front card? At each overlap the
 *     topmost element under that pixel must belong to the nearer card. The
 *     depth is solved from the live CSS3D matrices -- for a screen point, the
 *     element coordinates and the perspective denominator are recovered by a
 *     2x2 solve -- so "nearer" is the browser's own geometry, not an estimate.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280",
  out: path.join(REPO, "qa-v5/t1/depth-clipping.json"),
  shots: path.join(REPO, "artifacts/t1/depth-clipping"),
  vps: ["1440x900", "1920x1080", "390x844", "844x390", "700x700", "667x375", "780x470"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--shots=")) opts.shots = path.resolve(REPO, a.slice(8));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
  // "x,y;x,y;..." -- the pointer positions to repeat the sweep at. T1 measured
  // at the origin only, where the camera is on axis; motion moves the camera,
  // so the carry-forward re-takes the overlap count at the orbit's extremes.
  else if (a.startsWith("--pointers=")) {
    opts.pointers = a.slice(11).split(";").map((s2) => s2.split(",").map(Number));
  }
}
if (!opts.pointers) opts.pointers = [[0, 0]];

function readDepthGeometry() {
  const host = document.getElementById("labels");
  const cameraElement = host.querySelector("div[style*='preserve-3d']");
  const viewElement = cameraElement.parentElement;
  const layerRect = viewElement.getBoundingClientRect();
  const camStyle = getComputedStyle(cameraElement);
  const co = camStyle.transformOrigin.split(" ").map(parseFloat);
  const B = new DOMMatrix().translate(co[0], co[1], co[2] || 0)
    .multiply(new DOMMatrix(camStyle.transform))
    .translate(-co[0], -co[1], -(co[2] || 0));

  const localBox = (el, root) => {
    let x = 0, y = 0, n = el;
    while (n && n !== root) { x += n.offsetLeft; y += n.offsetTop; n = n.offsetParent; }
    return [x, y, el.offsetWidth, el.offsetHeight];
  };

  const cards = [];
  for (const el of cameraElement.children) {
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden") continue;
    const w = parseFloat(cs.width), h = parseFloat(cs.height);
    const o = cs.transformOrigin.split(" ").map(parseFloat);
    const C = B.multiply(new DOMMatrix().translate(o[0], o[1], o[2] || 0)
      .multiply(new DOMMatrix(cs.transform))
      .translate(-o[0], -o[1], -(o[2] || 0)));
    // Homogeneous map from element (x, y, 0) to clip space, as flat numbers.
    const M = { a: C.m11, b: C.m21, c: C.m41, d: C.m12, e: C.m22, f: C.m42,
                g: C.m14, h: C.m24, i: C.m44 };
    const projectLocal = (x, y) => {
      const X = M.a * x + M.b * y + M.c;
      const Y = M.d * x + M.e * y + M.f;
      const W = M.g * x + M.h * y + M.i;
      return [layerRect.x + X / W, layerRect.y + Y / W];
    };
    const clip = el.querySelector(".se-clip");
    const title = el.querySelector(".se-title");
    const content = el.querySelector(".se-content");
    const quad = [[0, 0], [w, 0], [w, h], [0, h]].map(([x, y]) => projectLocal(x, y));
    const tb = title ? localBox(title, el) : null;
    cards.push({
      slotIndex: Number(el.dataset.slot), code: Number(el.dataset.ilg),
      box: [w, h], map: M, layerOrigin: [layerRect.x, layerRect.y],
      quad,
      titleQuad: tb ? [[tb[0], tb[1]], [tb[0] + tb[2], tb[1]], [tb[0] + tb[2], tb[1] + tb[3]],
                       [tb[0], tb[1] + tb[3]]].map(([x, y]) => projectLocal(x, y)) : null,
      titleLocalBox: tb,
      clipStyle: clip ? (() => { const c = getComputedStyle(clip);
        const b = localBox(clip, el);
        // Computed width/height, not offsetWidth: offset* is rounded to whole
        // pixels and a 199.5 px card would read 200 and look like a mismatch.
        const cw = parseFloat(c.width), chh = parseFloat(c.height);
        return { overflow: c.overflow, clipPath: c.clipPath, borderRadius: c.borderRadius,
                 localBox: b, computedSize: [cw, chh],
                 coversCard: b[0] === 0 && b[1] === 0
                   && Math.abs(cw - w) < 0.05 && Math.abs(chh - h) < 0.05 }; })() : null,
      contentOverflowsCard: content ? (() => {
        const b = localBox(content, el);
        return { localBox: b, scrollWidth: content.scrollWidth, scrollHeight: content.scrollHeight,
                 clientWidth: content.clientWidth, clientHeight: content.clientHeight };
      })() : null,
    });
  }
  return { cards, layerRect: [layerRect.x, layerRect.y, layerRect.width, layerRect.height] };
}

/** Where a screen point lands in one card's element coordinates, and how deep. */
function hit(card, sx, sy) {
  const M = card.map;
  const x0 = sx - card.layerOrigin[0], y0 = sy - card.layerOrigin[1];
  // (a - x0 g) x + (b - x0 h) y = x0 i - c
  const a11 = M.a - x0 * M.g, a12 = M.b - x0 * M.h, b1 = x0 * M.i - M.c;
  const a21 = M.d - y0 * M.g, a22 = M.e - y0 * M.h, b2 = y0 * M.i - M.f;
  const det = a11 * a22 - a12 * a21;
  if (Math.abs(det) < 1e-12) return null;
  const x = (b1 * a22 - a12 * b2) / det;
  const y = (a11 * b2 - b1 * a21) / det;
  const W = M.g * x + M.h * y + M.i;
  const inside = x >= 0 && x <= card.box[0] && y >= 0 && y <= card.box[1];
  return { x, y, W, inside };
}

const poly = {
  bbox: (q) => [Math.min(...q.map((p) => p[0])), Math.min(...q.map((p) => p[1])),
                Math.max(...q.map((p) => p[0])), Math.max(...q.map((p) => p[1]))],
  bboxOverlap: (a, b, clip) => {
    const A = poly.bbox(a), B = poly.bbox(b);
    let x0 = Math.max(A[0], B[0]), y0 = Math.max(A[1], B[1]);
    let x1 = Math.min(A[2], B[2]), y1 = Math.min(A[3], B[3]);
    // Clamp into the viewport when asked: an overlap whose centroid is off
    // screen can still have most of its area on screen, and only on-screen
    // points can be hit tested.
    if (clip) {
      x0 = Math.max(x0, 1); y0 = Math.max(y0, 1);
      x1 = Math.min(x1, clip[0] - 2); y1 = Math.min(y1, clip[1] - 2);
    }
    const w = x1 - x0, h = y1 - y0;
    return w > 0 && h > 0 ? { w, h, cx: (x0 + x1) / 2, cy: (y0 + y1) / 2 } : null;
  },
};

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const consoleErrors = []; const pageErrors = [];
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("pageerror", (e) => pageErrors.push(String(e.message)));
await page.goto(`${opts.origin}/?qa=1&composition=sourceExact`, { waitUntil: "load", timeout: 120000 });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 180000 });
await page.waitForTimeout(3200);
await page.evaluate(() => {
  window.__ILG_QA__.setAdaptiveQuality(false);
  window.__ILG_QA__.setQuality("high");
  window.__ILG_QA__.setPointer(0, 0);
  window.__ILG_QA__.pause();
});
await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
await mkdir(opts.shots, { recursive: true });

const report = { startedAt: new Date().toISOString(),
  targetReference: "qa-v5/t1/target-typography-contract.json (clip layer: overflow hidden, "
                 + "clip-path none, border-radius 0, at the full card box)",
  viewports: [], assertions: [] };
const A = (n, ok, d) => report.assertions.push({ assertion: n, pass: !!ok, detail: d ?? null });
const OFFSETS = [[0, 0], [313, 197], [-640, 480]];
report.pointers = opts.pointers;

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  await page.setViewportSize({ width: w, height: h });
  await page.waitForTimeout(400);
  const entry = { id: vp, viewport: [w, h], offsets: [] };
  for (const [ox, oy] of OFFSETS) {
   for (const [px, py] of opts.pointers) {
    await page.evaluate(`window.__readDepthGeometry = ${readDepthGeometry.toString()}`);
    const dom = await page.evaluate(([x, y, ppx, ppy]) => {
      const qa = window.__ILG_QA__;
      // `jumpPointer`, not `setPointer`: this page is PAUSED, and setPointer
      // writes only the smoothing target -- the applied pointer would stay at
      // zero and every "extreme" would render the same on-axis camera. An
      // instrument that cannot move what it claims to sweep is not evidence.
      qa.jumpPointer(ppx, ppy);
      qa.setOffset(x, y); qa.renderOnce();
      const geom = window.__readDepthGeometry();
      const t = qa.getMotionTruth();
      geom.labelCamera = t.labelCamera;
      geom.appliedPointer = [t.pointerX, t.pointerY];
      return geom;
    }, [ox, oy, px, py]);

    const cards = dom.cards;
    const clipOk = cards.every((c) => c.clipStyle && c.clipStyle.overflow === "hidden"
      && c.clipStyle.clipPath === "none" && c.clipStyle.borderRadius === "0px"
      && c.clipStyle.coversCard);

    // 2. Titles on non-overlapping cards must not overlap.
    let titleCollisions = 0; const collisionExamples = [];
    for (let i = 0; i < cards.length; i += 1) {
      for (let j = i + 1; j < cards.length; j += 1) {
        if (!cards[i].titleQuad || !cards[j].titleQuad) continue;
        if (poly.bboxOverlap(cards[i].quad, cards[j].quad)) continue;   // occlusion case
        if (poly.bboxOverlap(cards[i].titleQuad, cards[j].titleQuad)) {
          titleCollisions += 1;
          if (collisionExamples.length < 5) collisionExamples.push([cards[i].code, cards[j].code]);
        }
      }
    }

    // 3. Rear text must not paint over a front card.
    //
    // Sample the interior of every on-screen card, hit-test each sample, and
    // require the topmost label to be the card that is actually nearest at
    // that pixel -- solved from the live matrices, so "nearest" is the
    // browser's own geometry. This is testable everywhere, unlike a probe that
    // needs two card planes to cross on screen.
    const probes = [];
    for (const card of cards) {
      const bb = poly.bbox(card.quad);
      for (let u = 1; u <= 3; u += 1) {
        for (let v = 1; v <= 3; v += 1) {
          const sx = bb[0] + (bb[2] - bb[0]) * (u / 4);
          const sy = bb[1] + (bb[3] - bb[1]) * (v / 4);
          if (sx < 1 || sy < 1 || sx > w - 2 || sy > h - 2) continue;
          const own = hit(card, sx, sy);
          if (!own || !own.inside) continue;
          // Everyone whose plane also contains this pixel; nearest wins.
          let nearest = card, nearestW = own.W, covering = 0;
          for (const other of cards) {
            if (other === card) continue;
            const o = hit(other, sx, sy);
            if (!o || !o.inside) continue;
            covering += 1;
            if (o.W < nearestW - 1e-6) { nearest = other; nearestW = o.W; }
          }
          probes.push({ at: [sx, sy], cardCode: card.code, nearerCode: nearest.code,
                        coveringCards: covering, wNearer: nearestW });
        }
      }
    }
    const resolved = await page.evaluate((ps) => ps.map((p) => {
      const stack = document.elementsFromPoint(p.at[0], p.at[1]);
      for (const el of stack) {
        const card = el.closest ? el.closest("[data-ilg]") : null;
        if (card) return { ...p, topCode: Number(card.dataset.ilg) };
      }
      return { ...p, topCode: null };
    }), probes);
    const decided = resolved.filter((p) => p.topCode !== null);
    const wrong = decided.filter((p) => p.topCode !== p.nearerCode);
    const overlapped = probes.filter((p) => p.coveringCards > 0).length;

    entry.offsets.push({ offset: [ox, oy], pointer: [px, py], visibleCards: cards.length,
      clipStructureMatchesTarget: clipOk,
      clipSample: cards[0]?.clipStyle ?? null,
      titleCollisionsBetweenNonOverlappingCards: titleCollisions, collisionExamples,
      depthProbes: probes.length, depthDecided: decided.length,
      depthSamplesWithAnotherCardPlaneOverThem: overlapped,
      depthWrong: wrong.length, depthWrongExamples: wrong.slice(0, 5),
      appliedPointer: dom.appliedPointer, labelCamera: dom.labelCamera });
    if (ox === 0 && oy === 0 && px === 0 && py === 0) {
      // The page footer is a separate DOM overlay, not part of the card type
      // layer. Leaving it in would put its ink outside every card silhouette
      // and make the clip measurement about the footer instead.
      const hideFooter = await page.addStyleTag({ content: "#page-overlay{display:none!important}" });
      await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: false, media: false, labels: true }));
      await page.evaluate(() => window.__ILG_QA__.renderOnce());
      await page.waitForTimeout(250);
      await page.screenshot({ path: path.join(opts.shots, `${vp}-labels-only.png`) });
      // Remove by handle. Searching <style> tags for the selector would also
      // match the dev server's injected app stylesheet, which contains
      // #page-overlay rules -- deleting that took the card layout with it.
      await hideFooter.evaluate((el) => el.remove());
      await writeFile(path.join(opts.shots, `${vp}-quads.json`),
        JSON.stringify({ viewport: [w, h],
          cards: cards.map((c) => ({ code: c.code, quad: c.quad, titleQuad: c.titleQuad })) }, null, 2));
      await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: true, media: true, labels: true }));
    }
   }
  }
  await page.evaluate(() => window.__ILG_QA__.jumpPointer(0, 0));
  report.viewports.push(entry);
  A(`${vp}: clip layer matches the Target's (overflow hidden, no clip-path, no radius, full card box)`,
    entry.offsets.every((o) => o.clipStructureMatchesTarget), entry.offsets[0].clipSample);
  A(`${vp}: no title collides with a title on a non-overlapping card`,
    entry.offsets.every((o) => o.titleCollisionsBetweenNonOverlappingCards === 0),
    entry.offsets.map((o) => o.titleCollisionsBetweenNonOverlappingCards));
  // Report the OVERLAP count in the same detail as the verdict. Without it the
  // row reads as "rear-card text never covers a front card, proven", when what
  // was actually sampled is single-card interiors: if no two card planes ever
  // overlap on screen, no sample can exercise the occlusion case at all.
  A(`${vp}: at every sampled pixel the topmost label is the nearest card's`,
    entry.offsets.every((o) => o.depthWrong === 0),
    entry.offsets.map((o) => ({ probes: o.depthProbes, decided: o.depthDecided,
      wrong: o.depthWrong,
      samplesWithAnotherCardPlaneOverThem: o.depthSamplesWithAnotherCardPlaneOverThem })));
  A(`${vp}: the depth probe resolved a topmost label at on-screen samples`,
    entry.offsets.every((o) => o.depthDecided >= 20),
    entry.offsets.map((o) => ({ probes: o.depthProbes, decided: o.depthDecided })));
  // The sweep proves itself. If the pointer never reached the pose, every
  // "extreme" above was the same frame and the depth count means nothing.
  if (opts.pointers.length > 1) {
    const cams = entry.offsets.filter((o) => o.labelCamera).map((o) => o.labelCamera);
    const spreadX = cams.length ? Math.max(...cams.map((c) => c[0])) - Math.min(...cams.map((c) => c[0])) : 0;
    const spreadY = cams.length ? Math.max(...cams.map((c) => c[1])) - Math.min(...cams.map((c) => c[1])) : 0;
    entry.pointerSweepMovedCameraBy = [spreadX, spreadY];
    A(`${vp}: the pointer sweep actually moved the camera`,
      spreadX > 1 && spreadY > 1,
      { spreadX, spreadY, appliedPointers: entry.offsets.map((o) => o.appliedPointer),
        labelCameras: cams.slice(0, 8) });
  }
}
A("no console errors", consoleErrors.length === 0, consoleErrors.slice(0, 5));
A("no page errors", pageErrors.length === 0, pageErrors.slice(0, 5));
report.consoleErrors = consoleErrors; report.pageErrors = pageErrors;
// What this file does and does not establish, stated where the verdict is.
const overlapTotal = report.viewports
  .flatMap((v) => v.offsets)
  .reduce((n, o) => n + o.depthSamplesWithAnotherCardPlaneOverThem, 0);
report.actualOverlappingCardPlaneSamples = overlapTotal;
report.pointerSweep = opts.pointers;
report.scope = overlapTotal === 0
  ? "PROVEN: the clip STRUCTURE matches the Target's, and within every sampled "
    + "card interior the topmost label is that card's own. NOT PROVEN: real "
    + "occlusion ordering. actualOverlappingCardPlaneSamples = 0 -- no two card "
    + "planes were observed overlapping on screen in any tested configuration, "
    + "so the rear-card-text-over-front-card case was never exercised. Carried "
    + "forward to the motion stage, where the pointer orbit and scroll offsets "
    + `move the planes. Pointer positions swept: ${JSON.stringify(opts.pointers)}.`
  : `${overlapTotal} samples had another card plane over them; the occlusion `
    + "case was exercised.";
report.passed = report.assertions.filter((a) => a.pass).length;
report.total = report.assertions.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report, null, 2));
await ctx.close(); await browser.close();
console.log(`depth / clipping ${report.verdict}  ${report.passed}/${report.total}`);
for (const a of report.assertions) if (!a.pass) console.log(`  FAIL ${a.assertion}  ${JSON.stringify(a.detail)?.slice(0, 220)}`);
