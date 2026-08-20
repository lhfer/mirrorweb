#!/usr/bin/env node
/**
 * Does a quality step preserve the source-exact composition?
 *
 * Two defects met here. `AdaptiveQuality.sample()` wrote `this.level` before
 * returning it and the caller compared the two, so the adaptive path never
 * fired and the quality rebuild was never exercised at runtime. That rebuild
 * called `createConvexGlassGeometryV4(quality)` with no override, which on the
 * source-exact path would have handed every card TILE's 1.3508 aspect and
 * TILE's width in place of the contract's 4:3 reference plane.
 *
 * So this drives high -> medium -> low -> high and checks, at every level, that
 * the composition is untouched and that nothing was created, destroyed or
 * reloaded.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280", out: path.join(REPO, "qa-v5/fsx-a/quality-invariance.json"),
               vps: ["1440x900", "390x844", "700x700"], levels: ["high", "medium", "low", "high"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const consoleErrors = []; const pageErrors = [];
// Beauty route: the glass volume is the thing a quality step rebuilds, and
// foundation mode has no glass to rebuild.
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("pageerror", (e) => pageErrors.push(String(e.message)));
await page.goto(`${opts.origin}/?qa=1&composition=sourceExact`, { waitUntil: "load" });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 180000 });
await page.waitForTimeout(3000);
await page.evaluate(() => { window.__ILG_QA__.setPointer(0, 0); window.__ILG_QA__.pause(); });
await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));

// Proof that the adaptive path FIRES, taken before the sweep and with the
// sampler on. Until this round `sample()` wrote `this.level` and the caller
// compared the returned value with the field it came from, so `changed` was
// always false and neither grid.setQuality nor pipeline.setQuality was ever
// reached automatically. Running unpaused for a few seconds and reading the
// recorded changes is the difference between claiming that and showing it.
await page.evaluate(() => { window.__ILG_QA__.setAdaptiveQuality(true); window.__ILG_QA__.resume(); });
await page.evaluate(() => window.__ILG_QA__.setQuality("low"));
await page.waitForTimeout(6000);
const adaptive = await page.evaluate(() => {
  const s = window.__ILG_QA__.getAdaptiveState();
  return { ...s, note: "changes recorded by the running sampler, not injected by the harness" };
});
await page.evaluate(() => { window.__ILG_QA__.pause(); window.__ILG_QA__.setAdaptiveQuality(false); });
await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));

async function snapshot(label) {
  return page.evaluate((lbl) => {
    const qa = window.__ILG_QA__;
    const v = qa.getV4State();
    const p = qa.getPoolState();
    const a = qa.getAssetState();
    const f = v.sourceExactFrame;
    const slots = qa.getSourceExactSlots();
    return {
      label: lbl,
      quality: qa.getAdaptiveState().appliedLevel,
      samplerLevel: qa.getAdaptiveState().level,
      viewport: [window.innerWidth, window.innerHeight],
      frame: f,
      cardAspect: f.planeWidth / f.planeHeight,
      activeSlotCount: v.activeSlotCount,
      created: p.created, destroyed: p.destroyed,
      materials: p.materials, geometries: p.geometries,
      textures: a.textures, videos: a.videos, videoFrames: a.videoFrames,
      slotIdentity: v.slotIdentity,
      camera: v.sourceExactCamera,
      assertions: v.runtimeTruthAssertions,
      corners: slots.map((s) => ({ slotIndex: s.slotIndex, cornersPx: s.cornersPx })),
      world: slots.map((s) => ({ slotIndex: s.slotIndex, world: s.world, normal: s.normal })),
    };
  }, label);
}

const report = { startedAt: new Date().toISOString(), route: "?composition=sourceExact (beauty)",
                 levels: opts.levels, viewports: [], assertions: [], adaptive };
const A = (n, ok, d) => report.assertions.push({ assertion: n, pass: !!ok, detail: d });

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  await page.setViewportSize({ width: w, height: h });
  await page.waitForTimeout(250);
  await page.evaluate(() => window.__ILG_QA__.setQuality("high"));
  await page.waitForTimeout(350);
  const base = await snapshot(`${vp}@high(base)`);
  const steps = [base];
  for (const level of opts.levels.slice(1)) {
    await page.evaluate((l) => window.__ILG_QA__.setQuality(l), level);
    await page.waitForTimeout(400);
    steps.push(await snapshot(`${vp}@${level}`));
  }
  // Corner delta against the FIRST level: a quality step must not move a card.
  let worstCorner = 0;
  let worstWorld = 0;
  for (const s of steps) {
    for (let i = 0; i < s.corners.length && i < base.corners.length; i += 1) {
      for (let c = 0; c < 4; c += 1) {
        const a1 = base.corners[i].cornersPx[c];
        const b1 = s.corners[i].cornersPx[c];
        worstCorner = Math.max(worstCorner, Math.hypot(a1[0] - b1[0], a1[1] - b1[1]));
      }
      const aw = base.world[i].world; const bw = s.world[i].world;
      worstWorld = Math.max(worstWorld, Math.hypot(aw[0] - bw[0], aw[1] - bw[1], aw[2] - bw[2]));
    }
  }
  const q = (k) => new Set(steps.map((s) => s[k]));
  report.viewports.push({ id: vp, worstProjectedCornerDeltaPx: Number(worstCorner.toFixed(6)),
                          worstWorldDelta: Number(worstWorld.toFixed(9)),
                          levelsSeen: steps.map((s) => s.quality), steps });
  A(`${vp}: projected card corners unchanged across high/medium/low/high`, worstCorner <= 0.5,
    { worstPx: Number(worstCorner.toFixed(6)), limit: 0.5 });
  A(`${vp}: card aspect stays exactly 4/3`,
    steps.every((s) => Math.abs(s.cardAspect - 4 / 3) < 1e-9), [...q("cardAspect")]);
  A(`${vp}: active slot count unchanged`, q("activeSlotCount").size === 1, [...q("activeSlotCount")]);
  A(`${vp}: no mesh created by a quality step`,
    steps.every((s) => s.created === base.created), [...q("created")]);
  A(`${vp}: no mesh destroyed by a quality step`,
    steps.every((s) => s.destroyed === base.destroyed), [...q("destroyed")]);
  A(`${vp}: material count stable`, q("materials").size === 1, [...q("materials")]);
  A(`${vp}: texture count stable`, q("textures").size === 1, [...q("textures")]);
  A(`${vp}: video count stable`, q("videos").size === 1, [...q("videos")]);
  A(`${vp}: video never reloads`,
    steps.every((s, i) => i === 0 || s.videoFrames >= steps[i - 1].videoFrames), null);
  A(`${vp}: slot identity intact at every level`,
    steps.every((s) => s.slotIdentity.codesAreSlotIndexPlusOne && s.slotIdentity.inactiveHidden), null);
  A(`${vp}: camera on axis and one world unit is one CSS pixel at every level`,
    steps.every((s) => s.camera.cameraOnAxis
      && Math.abs(s.camera.oneWorldUnitIsOneCssPixelAtZ0 - 1) < 1e-9), null);
  A(`${vp}: runtime truth passes at every level`, steps.every((s) => s.assertions.allPass), null);
  A(`${vp}: every quality level was actually applied`,
    JSON.stringify(steps.map((s) => s.quality)) === JSON.stringify(opts.levels),
    { requested: opts.levels, applied: steps.map((s) => s.quality) });
}

A("the adaptive sampler actually changes quality on its own",
  Boolean(adaptive && adaptive.changeCount > 0),
  { changeCount: adaptive?.changeCount, changes: adaptive?.changes,
    why: "sample() now returns { level, changed }; the caller used to compare the "
      + "returned level with the field sample() had already written to it, so this "
      + "path had never once fired." });
A("no console errors", consoleErrors.length === 0, consoleErrors.slice(0, 5));
A("no page errors", pageErrors.length === 0, pageErrors.slice(0, 5));
report.consoleErrors = consoleErrors;
report.pageErrors = pageErrors;
report.passed = report.assertions.filter((a) => a.pass).length;
report.total = report.assertions.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report, null, 2));
await ctx.close();
await browser.close();
console.log(`quality invariance ${report.verdict}  ${report.passed}/${report.total}`);
for (const a of report.assertions) if (!a.pass) console.log(`  FAIL ${a.assertion}  ${JSON.stringify(a.detail)?.slice(0, 200)}`);
