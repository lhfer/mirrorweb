#!/usr/bin/env node
/**
 * Does the typography container sit exactly on the card?
 *
 * The label boxes are reconstructed through the REAL CSS3D path -- the camera
 * element's computed transform composed with each label's own, with both
 * transform origins and the perspective divide -- rather than recomputed from
 * the same numbers the engine used. Recomputing would compare the layout frame
 * with itself and always return zero.
 *
 * The reconstruction is checked against the browser's own
 * `getBoundingClientRect` before any of its numbers are used, so a mistake in
 * the reconstruction cannot be mistaken for agreement.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280",
  out: path.join(REPO, "qa-v5/t1/container-alignment.json"),
  vps: ["1440x900", "1920x1080", "390x844", "844x390", "700x700", "667x375", "780x470"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
}

function readLabelGeometry() {
  const host = document.getElementById("labels");
  // three's CSS3DRenderer marks its camera element with an inline
  // transform-style; finding it that way survives any host layout change.
  const cameraElement = host.querySelector("div[style*='preserve-3d']");
  const viewElement = cameraElement.parentElement;
  const layerRect = viewElement.getBoundingClientRect();
  const camStyle = getComputedStyle(cameraElement);
  const Mcam = new DOMMatrix(camStyle.transform);
  const camOrigin = camStyle.transformOrigin.split(" ").map(parseFloat);
  const Ocam = { x: camOrigin[0], y: camOrigin[1], z: camOrigin[2] || 0 };

  const project = (q) => {
    const p = Mcam.transformPoint(new DOMPoint(q.x - Ocam.x, q.y - Ocam.y, q.z - Ocam.z, 1));
    return [layerRect.x + Ocam.x + p.x / p.w, layerRect.y + Ocam.y + p.y / p.w];
  };

  const out = [];
  for (const el of cameraElement.children) {
    const cs = getComputedStyle(el);
    const w = parseFloat(cs.width), h = parseFloat(cs.height);
    const M = new DOMMatrix(cs.transform);
    const o = cs.transformOrigin.split(" ").map(parseFloat);
    const O = { x: o[0], y: o[1], z: o[2] || 0 };
    // Element box corners, top-left first, clockwise -- the same order the
    // engine reports its card corners in.
    const corners = [[0, 0], [w, 0], [w, h], [0, h]].map(([x, y]) => {
      const p = M.transformPoint(new DOMPoint(x - O.x, y - O.y, -O.z, 1));
      return project({ x: O.x + p.x / p.w, y: O.y + p.y / p.w, z: O.z + p.z / p.w });
    });
    const r = el.getBoundingClientRect();
    // `dataset.ilg`, not innerText: a hidden element's innerText is empty.
    const code = el.dataset.ilg ? Number(el.dataset.ilg) : null;
    out.push({
      code,
      slotIndex: el.dataset.slot ? Number(el.dataset.slot) : null,
      hidden: cs.visibility === "hidden",
      cssWidth: w, cssHeight: h,
      objectScale: [Math.hypot(M.m11, M.m12, M.m13), Math.hypot(M.m21, M.m22, M.m23),
                    Math.hypot(M.m31, M.m32, M.m33)],
      containerType: cs.containerType, boxSizing: cs.boxSizing, overflow: cs.overflow,
      cornersPx: corners,
      browserRect: [r.x, r.y, r.width, r.height],
    });
  }
  return { count: out.length, labels: out,
           layerRect: [layerRect.x, layerRect.y, layerRect.width, layerRect.height] };
}

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

const report = { startedAt: new Date().toISOString(),
  method: "label corners reconstructed through the live CSS3D transform chain "
        + "(camera element transform, per-element transform, both transform origins, "
        + "perspective divide) and validated against getBoundingClientRect",
  scheme: "A: element sized to the layout frame's card plane, CSS3D object scale = 1",
  viewports: [], assertions: [] };
const A = (n, ok, d) => report.assertions.push({ assertion: n, pass: !!ok, detail: d ?? null });

/** Offsets so the check is not taken at one lucky grid phase. */
const OFFSETS = [[0, 0], [313, 197], [-640, 480]];

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  await page.setViewportSize({ width: w, height: h });
  await page.waitForTimeout(400);
  const entry = { id: vp, viewport: [w, h], offsets: [] };
  for (const [ox, oy] of OFFSETS) {
    await page.evaluate(([x, y]) => { window.__ILG_QA__.setOffset(x, y); }, [ox, oy]);
    await page.waitForTimeout(120);
    await page.evaluate(`window.__readLabelGeometry = ${readLabelGeometry.toString()}`);
    const [dom, slots, frame, labelTruth] = await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      qa.renderOnce();
      return [window.__readLabelGeometry(), qa.getSourceExactSlots(),
              qa.getV4State().sourceExactFrame, qa.getLabelTruth()];
    });
    const byCode = new Map(dom.labels.filter((l) => l.code !== null).map((l) => [l.code, l]));
    let worstCorner = 0, worstSelfCheck = 0, worstBox = 0, missing = 0, compared = 0;
    let worstScale = 0;
    for (const s of slots) {
      const label = byCode.get(s.code);
      if (!label) { missing += 1; continue; }
      if (label.hidden) continue;                 // back-facing, correctly not drawn
      compared += 1;
      for (let c = 0; c < 4; c += 1) {
        worstCorner = Math.max(worstCorner,
          Math.hypot(label.cornersPx[c][0] - s.cornersPx[c][0],
                     label.cornersPx[c][1] - s.cornersPx[c][1]));
      }
      const xs = label.cornersPx.map((p) => p[0]), ys = label.cornersPx.map((p) => p[1]);
      const aabb = [Math.min(...xs), Math.min(...ys),
                    Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)];
      for (let k = 0; k < 4; k += 1) {
        worstSelfCheck = Math.max(worstSelfCheck, Math.abs(aabb[k] - label.browserRect[k]));
      }
      worstBox = Math.max(worstBox, Math.abs(label.cssWidth - frame.planeWidth),
                                    Math.abs(label.cssHeight - frame.planeHeight));
      worstScale = Math.max(worstScale, ...label.objectScale.map((v) => Math.abs(v - 1)));
    }
    entry.offsets.push({ offset: [ox, oy], activeSlots: slots.length, labelsInDom: dom.count,
      compared, missingLabels: missing,
      worstCornerErrorPx: Number(worstCorner.toFixed(4)),
      worstReconstructionVsBrowserRectPx: Number(worstSelfCheck.toFixed(4)),
      worstBoxErrorPx: Number(worstBox.toFixed(6)),
      worstObjectScaleError: Number(worstScale.toFixed(9)),
      framePlane: [frame.planeWidth, frame.planeHeight],
      labelElementBox: labelTruth.elementBox, typeZ: labelTruth.typeZ });
  }
  const worst = (k) => Math.max(...entry.offsets.map((o) => o[k]));
  report.viewports.push(entry);
  A(`${vp}: label element box equals the layout frame card plane`, worst("worstBoxErrorPx") <= 0.02,
    { worstPx: worst("worstBoxErrorPx"),
      note: "0.02 px covers the browser rounding a computed width to 1/64 px" });
  A(`${vp}: CSS3D object scale is exactly 1`, worst("worstObjectScaleError") < 1e-6,
    worst("worstObjectScaleError"));
  A(`${vp}: reconstruction agrees with the browser's own bounding rect`,
    worst("worstReconstructionVsBrowserRectPx") <= 1.0,
    { worstPx: worst("worstReconstructionVsBrowserRectPx") });
  A(`${vp}: label container corner within 1 px of the card mid-plane corner`,
    worst("worstCornerErrorPx") <= 1.0, { worstPx: worst("worstCornerErrorPx") });
  A(`${vp}: no missing label for any active slot`,
    entry.offsets.every((o) => o.missingLabels === 0),
    entry.offsets.map((o) => o.missingLabels));
  A(`${vp}: no stale label -- every label in the DOM belongs to a pool slot`,
    entry.offsets.every((o) => o.labelsInDom >= o.activeSlots), null);
}

// Resize sync: the box must follow the frame across an orientation flip, and
// slot identity must survive it.
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(500);
const portrait = await page.evaluate(() => {
  const qa = window.__ILG_QA__;
  qa.renderOnce();
  return { label: qa.getLabelTruth(), frame: qa.getV4State().sourceExactFrame,
           identity: qa.getV4State().slotIdentity };
});
await page.setViewportSize({ width: 844, height: 390 });
await page.waitForTimeout(500);
const landscape = await page.evaluate(() => {
  const qa = window.__ILG_QA__;
  qa.renderOnce();
  return { label: qa.getLabelTruth(), frame: qa.getV4State().sourceExactFrame,
           identity: qa.getV4State().slotIdentity };
});
report.orientationFlip = { portrait, landscape };
A("label box tracks the frame across an orientation flip",
  Math.abs(portrait.label.elementBox[0] - portrait.frame.planeWidth) < 1e-6
  && Math.abs(landscape.label.elementBox[0] - landscape.frame.planeWidth) < 1e-6,
  { portrait: portrait.label.elementBox, landscape: landscape.label.elementBox });
A("slot identity survives the flip",
  portrait.identity.codesAreSlotIndexPlusOne && landscape.identity.codesAreSlotIndexPlusOne, null);
A("text plane depth is the measured zero on the source-exact path",
  portrait.label.typeZ === 0 && landscape.label.typeZ === 0,
  { typeZ: portrait.label.typeZ });
A("no console errors", consoleErrors.length === 0, consoleErrors.slice(0, 5));
A("no page errors", pageErrors.length === 0, pageErrors.slice(0, 5));
report.consoleErrors = consoleErrors; report.pageErrors = pageErrors;
report.passed = report.assertions.filter((a) => a.pass).length;
report.total = report.assertions.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report, null, 2));
await ctx.close(); await browser.close();
console.log(`container alignment ${report.verdict}  ${report.passed}/${report.total}`);
for (const a of report.assertions) if (!a.pass) console.log(`  FAIL ${a.assertion}  ${JSON.stringify(a.detail)?.slice(0, 200)}`);
