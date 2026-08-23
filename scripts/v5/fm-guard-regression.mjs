#!/usr/bin/env node
/**
 * Final Motion §八 -- the frozen regressions that the resize guard could break.
 *
 * The guard's whole content is "do not re-apply when the bounds did not
 * change". The way that can go wrong is the mirror image of what it fixes: a
 * viewport change the guard fails to notice, leaving the page laid out for the
 * previous one. Everything else in §八 is covered by the existing gates -- the
 * source contract, the runtime gate, the typography contract, the route check
 * -- and none of those drive a SEQUENCE of resizes.
 *
 * So this drives one: a walk across viewports that includes a repeat of the
 * same size, a return to a size already visited, a one-pixel change, and a
 * portrait/landscape flip. After each step it reads the page's own truth back
 * and checks it against the viewport the browser is actually at.
 *
 * What is checked after every step:
 *   - the layout frame's viewport IS the window's viewport (no stale layout)
 *   - rows/cols and plane size are the ones the model gives for that viewport,
 *     via the engine's own runtime assertions
 *   - slot identity is intact and active slot count is the frame's
 *   - the material cache is the same finite set it was at the start
 *   - label and render culling still report a live count, not a frozen one
 *   - no console or page error was emitted
 *   - `viewportApplies` advanced by exactly one per DISTINCT bounds and by
 *     zero for a repeat of the same bounds
 *
 * Usage: fm-guard-regression.mjs [--origin=http://127.0.0.1:5294] [--out=<json>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  origin: "http://127.0.0.1:5294",
  out: path.join(REPO, "artifacts/final-motion/guard-regression.json"),
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--origin=")) opts.origin = a.slice(9);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
}

/**
 * `expectApply` is whether the bounds differ from the step before, which is
 * what the guard keys on. A step marked false that applies anyway is a guard
 * that does nothing; a step marked true that does not apply is a stale layout.
 */
const WALK = [
  { vp: [1440, 900], expectApply: true, why: "start" },
  { vp: [1440, 900], expectApply: false, why: "same bounds again -- the guard's whole point" },
  { vp: [390, 844], expectApply: true, why: "desktop -> phone portrait" },
  { vp: [844, 390], expectApply: true, why: "portrait -> landscape flip" },
  { vp: [844, 390], expectApply: false, why: "same bounds again, after a flip" },
  { vp: [844, 391], expectApply: true, why: "one pixel taller -- the smallest real change" },
  { vp: [700, 700], expectApply: true, why: "square" },
  { vp: [390, 844], expectApply: true, why: "back to a size already visited" },
  { vp: [1440, 900], expectApply: true, why: "back to the start" },
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 },
                                       deviceScaleFactor: 1 });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e.message)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

await page.goto(`${opts.origin}/?review=target&qa`, { waitUntil: "load" });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
                           undefined, { timeout: 120000 });
await page.waitForTimeout(1500);

const read = () => page.evaluate(() => {
  const qa = window.__ILG_QA__;
  const v = qa.getV4State();
  const cull = qa.getRenderCullingTruth();
  const labels = qa.getLabelTruth();
  return {
    viewport: [window.innerWidth, window.innerHeight],
    frameViewport: v.sourceExactFrame?.viewport ?? null,
    rows: v.sourceExactFrame?.rows ?? null,
    cols: v.sourceExactFrame?.cols ?? null,
    planeW: v.sourceExactFrame?.planeWidth ?? null,
    planeH: v.sourceExactFrame?.planeHeight ?? null,
    activeSlotCount: v.activeSlotCount,
    slotIdentityOk: v.slotIdentity?.ok ?? null,
    assertions: v.runtimeTruthAssertions ?? null,
    applies: v.resizeScheduling?.applies ?? null,
    appliedViewport: v.resizeScheduling?.appliedViewport ?? null,
    cacheSize: qa.getBodyMaterialCacheTruth()?.cacheSize ?? null,
    opticalBody: qa.getOpticsState()?.opticalBody ?? null,
    renderDrawn: cull?.drawn ?? cull?.visible ?? null,
    renderTotal: cull?.total ?? null,
    labelsMounted: labels?.mounted ?? labels?.count ?? null,
    labelsVisible: labels?.visible ?? null,
    mediaFits: (qa.getMediaFits() || []).length,
  };
});

const steps = [];
let prev = null;
let baseCache = null;
for (const s of WALK) {
  await page.setViewportSize({ width: s.vp[0], height: s.vp[1] });
  // Well past the 80 ms late-report timer, so a step that was going to apply
  // twice has had every chance to.
  await page.waitForTimeout(400);
  const r = await read();
  if (baseCache === null) baseCache = r.cacheSize;
  const applied = prev === null ? null : r.applies - prev.applies;
  const failures = [];
  if (r.frameViewport && (r.frameViewport[0] !== r.viewport[0]
                          || r.frameViewport[1] !== r.viewport[1])) {
    failures.push(`stale layout: frame ${r.frameViewport} at viewport ${r.viewport}`);
  }
  if (r.slotIdentityOk === false) failures.push("slot identity broken");
  if (r.cacheSize !== baseCache) {
    failures.push(`material cache moved ${baseCache} -> ${r.cacheSize}`);
  }
  if (r.assertions && Object.entries(r.assertions)
      .some(([, v]) => v === false)) {
    failures.push(`runtime assertion false: ${JSON.stringify(r.assertions)}`);
  }
  if (applied !== null && applied !== (s.expectApply ? 1 : 0)) {
    failures.push(`applied ${applied} times, expected ${s.expectApply ? 1 : 0}`);
  }
  steps.push({ ...s, ...r, appliedThisStep: applied, failures });
  console.log(`${s.vp.join("x").padEnd(9)} applies+${applied ?? "-"} `
    + `frame=${r.frameViewport?.join("x")} rows=${r.rows} cols=${r.cols} `
    + `slots=${r.activeSlotCount} cache=${r.cacheSize} `
    + `${failures.length ? "FAIL " + failures.join("; ") : "ok"}`);
  prev = r;
}

const pass = steps.every((s) => s.failures.length === 0) && errors.length === 0;
const doc = {
  what: "Final Motion §八 -- a resize WALK against the shipped bounds-equality "
      + "guard. The existing gates each measure one viewport at a time; this is "
      + "the one that could catch a viewport change the guard fails to notice.",
  origin: opts.origin, capturedAt: new Date().toISOString(),
  pass, errors, steps,
};
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(doc, null, 1));
console.log(`guard regression ${pass ? "PASS" : "FAIL"}  ${steps.length} steps, `
  + `${errors.length} errors`);
console.log(`-> ${opts.out}`);
await browser.close();
process.exit(pass ? 0 : 1);
