#!/usr/bin/env node
/**
 * Does the type stay on its card while the page is moving?
 *
 * The T1 gate measured this at rest. Motion is where it can come apart: the
 * label layer and the glass are two different renderers reading the same pose,
 * and if they read it at different points in the frame the text slides off the
 * card under a flick.
 *
 * CORRECTED. This harness was built on the reading that the Target keeps a
 * dolly-free second camera for the CSS3D layer, so that glass and labels
 * separate under fast motion by design -- and it therefore gated the label
 * against an UN-dollied card plane and asserted that the two cameras DO
 * separate. The Target's own recorded CSS3D camera matrix says otherwise: its
 * distance from the origin is exactly 1000.000 at rest, 1158.13 during a fast
 * flick and 1223.01 during a long drag, and exactly 1000.000 through an entire
 * pointer sweep, which moves the camera but produces no velocity. Its CSS3D
 * camera carries the dolly.
 *
 * So there is no separation to allow for. The label is gated against the card
 * plane through the same camera that paints both, and the assertion that the
 * cameras separate is inverted: they must now agree at every frame, and the
 * peak gap is reported so a regression to two cameras cannot pass quietly.
 *
 * Every run is driven by real pointer input. No QA hook moves the page.
 *
 * Usage: m1-card-label-motion.mjs [--url=<origin>] [--out=<json>] [--vps=WxH,...]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  origin: "http://127.0.0.1:5280",
  out: path.join(REPO, "qa-v5/motion/card-label-motion.json"),
  vps: ["1440x900", "390x844", "844x390", "700x700"],
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Project the card mid-plane corners through the LABEL camera and compare with
 * the label element's own reconstructed corners, in one page call per frame.
 */
function installProbe() {
  const M = { armed: false, samples: [] };
  window.__CLM = M;

  M.sample = () => {
    const qa = window.__ILG_QA__;
    const rects = qa.getCardPlaneRects();
    const labels = qa.getLabelTruth();
    const motion = qa.getMotionTruth();
    const bySlot = new Map();
    for (const q of rects) bySlot.set(q.slotIndex, q.rectPx);
    let worst = 0, worstSlot = null, compared = 0;
    for (const s of labels.slots) {
      if (!s.visible) continue;
      const cr = bySlot.get(s.slotIndex);
      if (!cr) continue;
      // getCardPlaneRects projects the card mid-plane through the same camera
      // the label layer uses, so this is like-for-like rather than a
      // comparison of two different projections.
      const box = [cr[0], cr[1], cr[0] + cr[2], cr[1] + cr[3]];
      const rect = [s.rectPx[0], s.rectPx[1], s.rectPx[0] + s.rectPx[2], s.rectPx[1] + s.rectPx[3]];
      const d = Math.max(Math.abs(box[0] - rect[0]), Math.abs(box[1] - rect[1]),
                         Math.abs(box[2] - rect[2]), Math.abs(box[3] - rect[3]));
      compared += 1;
      if (d > worst) { worst = d; worstSlot = s.slotIndex; }
    }
    return { worst, worstSlot, compared,
             magnitude: motion.magnitude, dollyZ: motion.dollyZ,
             scrollX: motion.scrollX, velocityX: motion.velocityX,
             renderCameraZ: motion.renderCamera ? motion.renderCamera[2] : null,
             labelCameraZ: motion.labelCamera ? motion.labelCamera[2] : null };
  };

  const loop = () => {
    if (!M.armed) return;
    M.samples.push({ t: +performance.now().toFixed(2), ...M.sample() });
    requestAnimationFrame(loop);
  };
  M.start = () => { M.armed = true; M.samples.length = 0; requestAnimationFrame(loop); };
  M.stop = () => { M.armed = false; return M.samples.length; };
  return true;
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

const report = { startedAt: new Date().toISOString(), origin: opts.origin,
  gate: "label corners against the card mid-plane projected through the CSS3D camera",
  gateWhy: "the Target's CSS3D camera carries the velocity dolly -- its recorded distance from "
         + "the origin goes 1000.000 at rest, 1158.13 on a flick, 1223.01 on a long drag, and "
         + "exactly 1000.000 through a pointer sweep. There is no glass/label separation to "
         + "allow for, and an earlier version of this file gated on the assumption that there "
         + "was. The two cameras must now agree at every frame.",
  thresholdPx: 1.0, viewports: [], assertions: [], consoleErrors: [], pageErrors: [] };
const A = (n, ok, d) => report.assertions.push({ assertion: n, pass: !!ok, detail: d ?? null });

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    deviceScaleFactor: 1, hasTouch: true });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => report.pageErrors.push(`${vp}: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") report.consoleErrors.push(`${vp}: ${m.text()}`); });
  await page.goto(`${opts.origin}/?qa=1&composition=sourceExact`, { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 180000 });
  await page.waitForTimeout(3000);
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  await page.evaluate(installProbe);

  const span = Math.min(w, h);
  const cx = Math.round(w / 2), cy = Math.round(h / 2);
  const runs = [];
  for (const kind of ["drag", "flick"]) {
    await page.mouse.move(cx, cy);
    await page.waitForTimeout(1400);
    await page.evaluate(() => window.__CLM.start());
    if (kind === "drag") {
      await page.mouse.move(cx - span * 0.3, cy);
      await page.mouse.down();
      for (let i = 1; i <= 24; i += 1) {
        await page.mouse.move(cx - span * 0.3 + span * 0.024 * i, cy + span * 0.01 * i);
        await sleep(22);
      }
      await page.mouse.up();
      await page.waitForTimeout(2400);
    } else {
      await page.mouse.move(cx + span * 0.36, cy);
      await page.mouse.down();
      for (let i = 1; i <= 8; i += 1) { await page.mouse.move(cx + span * 0.36 - span * 0.09 * i, cy); await sleep(6); }
      await page.mouse.up();
      await page.waitForTimeout(3200);
    }
    await page.evaluate(() => window.__CLM.stop());
    const samples = await page.evaluate(() => window.__CLM.samples);
    const moving = samples.filter((s) => Math.abs(s.velocityX) > 1 || s.magnitude > 1);
    const worst = samples.reduce((a, s) => (s.worst > a.worst ? s : a), samples[0]);
    const dollyPeak = samples.reduce((a, s) => Math.max(a, Math.abs(s.dollyZ)), 0);
    const camGap = samples.reduce(
      (a, s) => Math.max(a, Math.abs((s.renderCameraZ ?? 0) - (s.labelCameraZ ?? 0))), 0);
    runs.push({ kind, frames: samples.length, movingFrames: moving.length,
                worstCornerDeltaPx: +worst.worst.toFixed(4),
                worstAtSlot: worst.worstSlot, worstAtMagnitude: +worst.magnitude.toFixed(3),
                comparedPerFrameMin: Math.min(...samples.map((s) => s.compared)),
                dollyPeakZ: +dollyPeak.toFixed(3),
                cameraSeparationPeakZ: +camGap.toFixed(3),
                scrollTravel: +(samples[samples.length - 1].scrollX - samples[0].scrollX).toFixed(3) });
  }
  report.viewports.push({ id: vp, viewport: [w, h], runs });
  for (const r of runs) {
    A(`${vp} ${r.kind}: label corners track the card plane within 1 px throughout`,
      r.worstCornerDeltaPx <= report.thresholdPx, r);
    A(`${vp} ${r.kind}: the page actually moved`, Math.abs(r.scrollTravel) > 50,
      { scrollTravel: r.scrollTravel, movingFrames: r.movingFrames });
    A(`${vp} ${r.kind}: every visible label was compared against a card`,
      r.comparedPerFrameMin > 0, { comparedPerFrameMin: r.comparedPerFrameMin });
  }
  A(`${vp}: the CSS3D camera carries the dolly -- the two cameras never separate`,
    runs.every((r) => r.cameraSeparationPeakZ < 1e-6),
    runs.map((r) => ({ kind: r.kind, dollyPeakZ: r.dollyPeakZ,
                       cameraSeparationPeakZ: r.cameraSeparationPeakZ })));
  A(`${vp}: the dolly actually engaged, so the row above was exercised`,
    runs.some((r) => r.dollyPeakZ > 1.0),
    runs.map((r) => ({ kind: r.kind, dollyPeakZ: r.dollyPeakZ })));
  await ctx.close();
}
await browser.close();

A("no console errors", report.consoleErrors.length === 0, report.consoleErrors.slice(0, 5));
A("no page errors", report.pageErrors.length === 0, report.pageErrors.slice(0, 5));
report.passed = report.assertions.filter((a) => a.pass).length;
report.total = report.assertions.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report, null, 2));
console.log(`card / label under motion ${report.verdict}  ${report.passed}/${report.total}`);
for (const a of report.assertions) {
  if (!a.pass) console.log(`  FAIL ${a.assertion}  ${JSON.stringify(a.detail)?.slice(0, 200)}`);
}
