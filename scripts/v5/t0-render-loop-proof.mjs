#!/usr/bin/env node
/**
 * Does the page still update, and does a QA hook produce a frame?
 *
 * Two things are proven here, because the FSX-A round got both wrong at once.
 *
 * 1. THE LOOP. `tick` contained `if (!this.adaptiveQuality) return;`, which
 *    returned out of the whole tick -- motion.step, grid.update, applyPose,
 *    labels.sync and drawFrame with it. Every FSX-A capture ran with the
 *    sampler off, so every one of them was taken against a frozen canvas.
 *    Assertion: with the sampler OFF and motion running, the loop's own frame
 *    counter advances and the canvas pixels change.
 *
 * 2. THE HOOK PATH. A paused capture must not depend on "a later frame will
 *    repaint". Each named hook now ends in `renderOnce()`. Assertion: the
 *    render stamp advances synchronously across the call, and where the op is
 *    visually consequential the canvas hash moves with it.
 *
 * The stamp is the primary evidence, not the hash: the live loop repaints too,
 * so an unchanged hash cannot distinguish "the explicit redraw ran" from "the
 * loop happened to redraw anyway". The hash is the corroborating half.
 */
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280",
               out: path.join(REPO, "qa-v5/t1/render-loop-proof.json") };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
}

const sha = async (page) => createHash("sha256").update(await page.screenshot()).digest("hex");
const qaCall = (page, fn, arg) => page.evaluate(([f, a]) => {
  const qa = window.__ILG_QA__;
  const before = qa.getRenderStamp();
  const r = a === undefined ? qa[f]() : (Array.isArray(a) ? qa[f](...a) : qa[f](a));
  return { before, after: qa.getRenderStamp(), returned: typeof r === "number" ? r : null };
}, [fn, arg]);

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const consoleErrors = []; const pageErrors = [];
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("pageerror", (e) => pageErrors.push(String(e.message)));
await page.goto(`${opts.origin}/?qa=1&composition=sourceExact`, { waitUntil: "load", timeout: 120000 });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 180000 });
await page.waitForTimeout(3200);

const report = { startedAt: new Date().toISOString(), route: "?qa=1&composition=sourceExact",
                 viewport: [1440, 900], assertions: [], ops: [] };
const A = (n, ok, d) => report.assertions.push({ assertion: n, pass: !!ok, detail: d ?? null });

// ---------------------------------------------------------------- 1. the loop
// Sampler OFF, motion RUNNING. This is exactly the state every FSX-A capture
// was in, and it is the state that used to freeze the page.
await page.evaluate(() => {
  window.__ILG_QA__.setAdaptiveQuality(false);
  window.__ILG_QA__.setQuality("high");
  window.__ILG_QA__.setPointer(0, 0);
  window.__ILG_QA__.reset();
  window.__ILG_QA__.resume();
  window.__ILG_QA__.setVelocity(900, 500);
});
const loopA = await page.evaluate(() => window.__ILG_QA__.getMetrics());
const shaLoopA = await sha(page);
await page.waitForTimeout(1200);
const loopB = await page.evaluate(() => window.__ILG_QA__.getMetrics());
const shaLoopB = await sha(page);
report.loopWithSamplerOff = {
  adaptiveSampler: loopB.adaptiveSampler, motionPaused: loopB.motionPaused,
  renderedFramesBefore: loopA.renderedFrames, renderedFramesAfter: loopB.renderedFrames,
  framesInWindow: loopB.renderedFrames - loopA.renderedFrames,
  canvasShaBefore: shaLoopA, canvasShaAfter: shaLoopB,
};
A("render loop keeps drawing while the adaptive sampler is OFF",
  loopB.renderedFrames - loopA.renderedFrames >= 20,
  { framesIn1200ms: loopB.renderedFrames - loopA.renderedFrames });
A("the canvas actually changes while the sampler is OFF and motion runs",
  shaLoopA !== shaLoopB, { before: shaLoopA.slice(0, 16), after: shaLoopB.slice(0, 16) });
A("the sampler really was off for that window", loopB.adaptiveSampler === false, null);

// Control: with the sampler ON the loop must also run. If only one of the two
// states drew, the fix would have moved the freeze rather than removed it.
await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(true));
const onA = await page.evaluate(() => window.__ILG_QA__.getMetrics());
await page.waitForTimeout(800);
const onB = await page.evaluate(() => window.__ILG_QA__.getMetrics());
A("render loop keeps drawing while the adaptive sampler is ON",
  onB.renderedFrames - onA.renderedFrames >= 15,
  { framesIn800ms: onB.renderedFrames - onA.renderedFrames });

// ------------------------------------------------------------ 2. the hooks
// Paused, sampler off: nothing but the explicit call can produce a frame.
await page.evaluate(() => {
  window.__ILG_QA__.setAdaptiveQuality(false);
  window.__ILG_QA__.setVelocity(0, 0);
  window.__ILG_QA__.pause();
  window.__ILG_QA__.setOffset(0, 0);
  window.__ILG_QA__.setQuality("high");
});
await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
await page.waitForTimeout(600);

/** `visual: true` means the op must move pixels as well as the stamp. */
const OPS = [
  { fn: "setQuality",         arg: "medium",                                   visual: false },
  { fn: "setRenderLayers",    arg: { glass: false, media: true, labels: false }, visual: true },
  { fn: "setRenderLayers",    arg: { glass: true, media: true, labels: true },   visual: true,
    id: "setRenderLayers(restore)" },
  { fn: "setOffset",          arg: [640, 400],                                 visual: true },
  // NOT marked visual, and that is a finding rather than a concession.
  // `MotionController.setPointer` writes pointerTARGET; the applied pointerX
  // only follows inside `step()`, which a paused page never runs. So the frame
  // this draws is legitimately identical: the applied state has not moved yet.
  // Motion is frozen this round, so the limitation is recorded, not patched --
  // and the assertion below shows the path is alive, just gated on stepping.
  { fn: "setPointer",         arg: [0.35, -0.2],                               visual: false },
  { fn: "setDpr",             arg: 2,                                          visual: false },
  { fn: "setDpr",             arg: 1,                                          visual: false, id: "setDpr(restore)" },
  { fn: "setAdaptiveQuality", arg: false,                                      visual: false },
  { fn: "reset",              arg: undefined,                                  visual: true },
];

for (const op of OPS) {
  const before = await sha(page);
  const stamp = await qaCall(page, op.fn, op.arg);
  const after = await sha(page);
  const entry = { op: op.id ?? `${op.fn}(${JSON.stringify(op.arg) ?? ""})`,
                  stampBefore: stamp.before, stampAfter: stamp.after,
                  stampAdvanced: stamp.after > stamp.before,
                  canvasShaBefore: before, canvasShaAfter: after,
                  canvasChanged: before !== after, expectedVisualChange: op.visual };
  report.ops.push(entry);
  A(`${entry.op}: draws a frame synchronously (render stamp advances)`, entry.stampAdvanced,
    { before: stamp.before, after: stamp.after });
  if (op.visual) {
    A(`${entry.op}: the canvas changes`, entry.canvasChanged,
      { before: before.slice(0, 16), after: after.slice(0, 16) });
  }
  await page.evaluate(() => { window.__ILG_QA__.pause(); });
}

// The pointer path IS alive; it is the smoother that needs a step. Set a
// pointer, let the page run briefly so `step()` can carry pointerX toward its
// target, then pause: the canvas must move. Without this, "setPointer produced
// an identical frame" and "setPointer produced no frame" look the same.
await page.evaluate(() => { window.__ILG_QA__.setPointer(0, 0); window.__ILG_QA__.renderOnce(); });
await page.waitForTimeout(300);
const pointerRest = await sha(page);
const pointerBefore = await page.evaluate(() => {
  const v = window.__ILG_QA__.getV4State();
  return { pointerX: v.pointerX ?? null, pointerTargetX: v.pointerTargetX ?? null };
});
await page.evaluate(() => { window.__ILG_QA__.setPointer(0.6, -0.35); });
const pointerPausedSha = await sha(page);
const pointerPaused = await page.evaluate(() => {
  const s = window.__ILG_QA__.getState();
  return { pointerX: s.pointerX, pointerTargetX: s.pointerTargetX };
});
await page.evaluate(() => window.__ILG_QA__.resume());
await page.waitForTimeout(700);
await page.evaluate(() => window.__ILG_QA__.pause());
const pointerMovedSha = await sha(page);
const pointerAfter = await page.evaluate(() => {
  const s = window.__ILG_QA__.getState();
  return { pointerX: s.pointerX, pointerTargetX: s.pointerTargetX };
});
report.pointerPath = { restSha: pointerRest, pausedSha: pointerPausedSha,
  afterSteppingSha: pointerMovedSha, before: pointerBefore, whilePaused: pointerPaused,
  afterStepping: pointerAfter,
  note: "setPointer writes the smoothing TARGET; MotionController.step carries the "
      + "applied pointer toward it, so a paused page redraws an identical frame. "
      + "Motion is frozen this round: this is recorded, not changed." };
A("setPointer moves the target immediately while paused",
  pointerPaused.pointerTargetX !== pointerBefore.pointerTargetX
    || pointerPaused.pointerTargetX === 0.6, pointerPaused);
A("the pointer path reaches the pixels once the page steps",
  pointerRest !== pointerMovedSha && pointerAfter.pointerX !== 0,
  { restSha: pointerRest.slice(0, 16), afterSteppingSha: pointerMovedSha.slice(0, 16),
    appliedPointerX: pointerAfter.pointerX });
await page.evaluate(() => { window.__ILG_QA__.setPointer(0, 0); window.__ILG_QA__.resume(); });
await page.waitForTimeout(500);
await page.evaluate(() => window.__ILG_QA__.pause());

// With the sampler off, the EXPLICIT RENDER STAMP must stay unchanged between
// two reads when no QA hook is called. That is what is measured -- the stamp
// counts `renderOnce()` calls, so this says nothing about whether the browser
// composited or the canvas repainted; it says the explicit draw path did not
// run. Without it, "the stamp advanced" could be a coincidence of timing.
const idleA = await page.evaluate(() => window.__ILG_QA__.getRenderStamp());
await page.waitForTimeout(700);
const idleB = await page.evaluate(() => window.__ILG_QA__.getRenderStamp());
A("the render stamp only moves when a hook is called",
  idleA === idleB, { idleA, idleB });

A("no console errors", consoleErrors.length === 0, consoleErrors.slice(0, 5));
A("no page errors", pageErrors.length === 0, pageErrors.slice(0, 5));
report.consoleErrors = consoleErrors; report.pageErrors = pageErrors;
report.passed = report.assertions.filter((a) => a.pass).length;
report.total = report.assertions.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report, null, 2));
await ctx.close(); await browser.close();
console.log(`render loop proof ${report.verdict}  ${report.passed}/${report.total}`);
for (const a of report.assertions) if (!a.pass) console.log(`  FAIL ${a.assertion}  ${JSON.stringify(a.detail)?.slice(0, 180)}`);
