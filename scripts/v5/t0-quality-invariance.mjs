#!/usr/bin/env node
/**
 * Does a quality step preserve the source-exact composition?
 *
 * Supersedes `fsxa-quality-invariance.mjs`, which answered the question with
 * `SourceExactLayoutFrame` -- the INPUT to the rebuild. A quality step
 * rebuilds the glass geometry, so reading the frame back afterwards cannot see
 * whether the rebuild kept the 4:3 override: the frame would report 4/3 either
 * way. That run also held the sampler off, and at the time the render loop
 * returned early in that state, so its screenshots were stale too.
 *
 * This reads the real mesh: the geometry's own bounding box, the scale each
 * mesh actually carries, and the bbox corners projected through the live
 * camera. Each level also gets a freshly drawn silhouette screenshot.
 *
 * The 4:3 assertion is on the MEASURED aspect. If the built outline did not
 * come out 4:3 the number would say so; nothing here is tuned to pass.
 */
import { createHash } from "node:crypto";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280",
               out: path.join(REPO, "qa-v5/t1/quality-invariance.json"),
               shots: path.join(REPO, "artifacts/t1/quality"),
               vps: ["1440x900", "390x844", "700x700"], levels: ["high", "medium", "low", "high"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--shots=")) opts.shots = path.resolve(REPO, a.slice(8));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const consoleErrors = []; const pageErrors = [];
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("pageerror", (e) => pageErrors.push(String(e.message)));
await page.goto(`${opts.origin}/?qa=1&composition=sourceExact`, { waitUntil: "load" });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 180000 });
await page.waitForTimeout(3000);
await page.evaluate(() => { window.__ILG_QA__.setPointer(0, 0); window.__ILG_QA__.pause(); });
await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));

// Proof that the adaptive path FIRES, taken with the sampler on and the page
// running. `sample()` used to write `this.level` and the caller compared the
// returned value with the field it came from, so `changed` was always false.
await page.evaluate(() => { window.__ILG_QA__.setAdaptiveQuality(true); window.__ILG_QA__.resume(); });
await page.evaluate(() => window.__ILG_QA__.setQuality("low"));
await page.waitForTimeout(6000);
const adaptive = await page.evaluate(() => {
  const qa = window.__ILG_QA__;
  const s = qa.getAdaptiveState();
  const m = qa.getMetrics();
  return { ...s, loopFramesDrawn: m.renderedFrames,
           note: "changes recorded by the running sampler, not injected by the harness" };
});
await page.evaluate(() => { window.__ILG_QA__.pause(); window.__ILG_QA__.setAdaptiveQuality(false); });
await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
await mkdir(opts.shots, { recursive: true });

async function snapshot(label, vp, level) {
  await page.evaluate(() => window.__ILG_QA__.renderOnce());
  const file = path.join(opts.shots, `${vp}-${level}.png`);
  await page.screenshot({ path: file });
  const sha = createHash("sha256").update(await readFile(file)).digest("hex");
  const data = await page.evaluate((lbl) => {
    const qa = window.__ILG_QA__;
    const v = qa.getV4State();
    const p = qa.getPoolState();
    const a = qa.getAssetState();
    const mesh = qa.getGlassMeshTruth();
    const labels = qa.getLabelTruth ? qa.getLabelTruth() : null;
    return {
      label: lbl,
      quality: qa.getAdaptiveState().appliedLevel,
      samplerLevel: qa.getAdaptiveState().level,
      viewport: [window.innerWidth, window.innerHeight],
      frameAspect: v.sourceExactFrame.planeWidth / v.sourceExactFrame.planeHeight,
      framePlane: [v.sourceExactFrame.planeWidth, v.sourceExactFrame.planeHeight],
      // The real mesh, not the frame that asked for it.
      mesh: { quality: mesh.quality, geometryUuid: mesh.geometryUuid,
              vertexCount: mesh.vertexCount, indexCount: mesh.indexCount,
              boundingBoxLocal: mesh.boundingBoxLocal, geometryAspect: mesh.geometryAspect,
              meshScale: mesh.meshScale, worldCardWidth: mesh.worldCardWidth,
              worldCardHeight: mesh.worldCardHeight, worldCardAspect: mesh.worldCardAspect,
              allSlotsShareGeometry: mesh.allSlotsShareGeometry,
              allSlotsShareScale: mesh.allSlotsShareScale },
      meshCorners: mesh.slots.map((s) => ({ slotIndex: s.slotIndex, cornersPx: s.cornersPx })),
      labelRects: labels ? labels.slots.map((s) => ({ slotIndex: s.slotIndex,
                                                      rectPx: s.rectPx })) : null,
      activeSlotCount: v.activeSlotCount,
      created: p.created, destroyed: p.destroyed,
      materials: p.materials, geometries: p.geometries,
      textures: a.textures, videos: a.videos, videoFrames: a.videoFrames,
      slotIdentity: v.slotIdentity, camera: v.sourceExactCamera,
      assertions: v.runtimeTruthAssertions,
    };
  }, label);
  return { ...data, silhouettePng: path.relative(REPO, file), silhouetteSha256: sha };
}

const report = { startedAt: new Date().toISOString(), route: "?composition=sourceExact (beauty)",
  supersedes: "qa-v5/fsx-a/quality-invariance.json (read the layout frame, not the mesh)",
  method: "real glass mesh: geometry bounding box x mesh scale, corners projected through the live camera",
  levels: opts.levels, viewports: [], assertions: [], adaptive };
const A = (n, ok, d) => report.assertions.push({ assertion: n, pass: !!ok, detail: d ?? null });

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  await page.setViewportSize({ width: w, height: h });
  await page.waitForTimeout(250);
  await page.evaluate(() => window.__ILG_QA__.setQuality("high"));
  await page.waitForTimeout(350);
  const base = await snapshot(`${vp}@high(base)`, vp, "0-high-base");
  const steps = [base];
  for (let i = 1; i < opts.levels.length; i += 1) {
    const level = opts.levels[i];
    await page.evaluate((l) => window.__ILG_QA__.setQuality(l), level);
    await page.waitForTimeout(400);
    steps.push(await snapshot(`${vp}@${level}`, vp, `${i}-${level}`));
  }
  let worstCorner = 0, worstLabel = 0;
  for (const s of steps) {
    for (let i = 0; i < s.meshCorners.length && i < base.meshCorners.length; i += 1) {
      for (let c = 0; c < 4; c += 1) {
        const a1 = base.meshCorners[i].cornersPx[c];
        const b1 = s.meshCorners[i].cornersPx[c];
        worstCorner = Math.max(worstCorner, Math.hypot(a1[0] - b1[0], a1[1] - b1[1]));
      }
    }
    if (s.labelRects && base.labelRects) {
      for (let i = 0; i < s.labelRects.length && i < base.labelRects.length; i += 1) {
        const a1 = base.labelRects[i].rectPx, b1 = s.labelRects[i].rectPx;
        for (let k = 0; k < 4; k += 1) worstLabel = Math.max(worstLabel, Math.abs(a1[k] - b1[k]));
      }
    }
  }
  const q = (k) => new Set(steps.map((s) => s[k]));
  const aspects = steps.map((s) => s.mesh.worldCardAspect);
  report.viewports.push({ id: vp,
    worstProjectedMeshCornerDeltaPx: Number(worstCorner.toFixed(6)),
    worstLabelRectDeltaPx: base.labelRects ? Number(worstLabel.toFixed(6)) : null,
    measuredWorldCardAspect: aspects, levelsSeen: steps.map((s) => s.quality), steps });

  A(`${vp}: real mesh corners unchanged across high/medium/low/high`, worstCorner <= 0.5,
    { worstPx: Number(worstCorner.toFixed(6)), limit: 0.5 });
  A(`${vp}: MEASURED card aspect is 4/3 at every level`,
    aspects.every((a) => Math.abs(a - 4 / 3) < 1e-6), aspects);
  A(`${vp}: geometry rebuilt at every level (new geometry object per step)`,
    new Set(steps.map((s) => s.mesh.geometryUuid)).size === steps.length,
    steps.map((s) => ({ level: s.quality, uuid: s.mesh.geometryUuid, verts: s.mesh.vertexCount })));
  A(`${vp}: vertex count actually changes with quality`,
    new Set(steps.map((s) => s.mesh.vertexCount)).size > 1,
    steps.map((s) => ({ level: s.quality, verts: s.mesh.vertexCount })));
  A(`${vp}: every slot shares one geometry and one scale`,
    steps.every((s) => s.mesh.allSlotsShareGeometry && s.mesh.allSlotsShareScale), null);
  // 1e-3 px, not 1e-6: the geometry's vertices live in a Float32Array, so a
  // 547.2 plane reads back as 547.2000122. That is the storage format, and the
  // residual scales with the value -- 1.2e-5 at 547 px, 6e-6 at 266 px. Any
  // real geometric error would be orders of magnitude larger.
  A(`${vp}: mesh world card size matches the layout frame`,
    steps.every((s) => Math.abs(s.mesh.worldCardWidth - s.framePlane[0]) < 1e-3
                    && Math.abs(s.mesh.worldCardHeight - s.framePlane[1]) < 1e-3),
    steps.map((s) => ({ level: s.quality, mesh: [s.mesh.worldCardWidth, s.mesh.worldCardHeight],
                        frame: s.framePlane })));
  A(`${vp}: active slot count unchanged`, q("activeSlotCount").size === 1, [...q("activeSlotCount")]);
  A(`${vp}: no mesh created by a quality step`,
    steps.every((s) => s.created === base.created), [...q("created")]);
  A(`${vp}: no mesh destroyed by a quality step`,
    steps.every((s) => s.destroyed === base.destroyed), [...q("destroyed")]);
  A(`${vp}: material count stable`, q("materials").size === 1, [...q("materials")]);
  A(`${vp}: texture count stable`, q("textures").size === 1, [...q("textures")]);
  A(`${vp}: video count stable`, q("videos").size === 1, [...q("videos")]);
  A(`${vp}: slot identity intact at every level`,
    steps.every((s) => s.slotIdentity.codesAreSlotIndexPlusOne && s.slotIdentity.inactiveHidden), null);
  A(`${vp}: camera on axis and one world unit is one CSS pixel at every level`,
    steps.every((s) => s.camera.cameraOnAxis
      && Math.abs(s.camera.oneWorldUnitIsOneCssPixelAtZ0 - 1) < 1e-9), null);
  A(`${vp}: runtime truth passes at every level`, steps.every((s) => s.assertions.allPass), null);
  A(`${vp}: every quality level was actually applied`,
    JSON.stringify(steps.map((s) => s.quality)) === JSON.stringify(opts.levels),
    { requested: opts.levels, applied: steps.map((s) => s.quality) });
  A(`${vp}: a freshly drawn silhouette exists for every level`,
    steps.every((s) => s.silhouettePng), steps.map((s) => s.silhouettePng));
  if (base.labelRects) {
    A(`${vp}: a quality step does not change typography size`, worstLabel <= 0.5,
      { worstLabelRectDeltaPx: Number(worstLabel.toFixed(6)), limit: 0.5 });
  }
}

A("the adaptive sampler actually changes quality on its own",
  Boolean(adaptive && adaptive.changeCount > 0),
  { changeCount: adaptive?.changeCount, changes: adaptive?.changes });
A("no console errors", consoleErrors.length === 0, consoleErrors.slice(0, 5));
A("no page errors", pageErrors.length === 0, pageErrors.slice(0, 5));
report.consoleErrors = consoleErrors; report.pageErrors = pageErrors;
report.passed = report.assertions.filter((a) => a.pass).length;
report.total = report.assertions.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report, null, 2));
await ctx.close(); await browser.close();
console.log(`quality invariance ${report.verdict}  ${report.passed}/${report.total}`);
for (const a of report.assertions) if (!a.pass) console.log(`  FAIL ${a.assertion}  ${JSON.stringify(a.detail)?.slice(0, 240)}`);
