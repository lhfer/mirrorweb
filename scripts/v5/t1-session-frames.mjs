#!/usr/bin/env node
/**
 * One live session, resized across orientations.
 *
 * Fresh contexts prove a viewport renders correctly from a cold start. They
 * cannot show that a RESIZE re-points the type layer, because every frame comes
 * from a page that was born at that size. This drives one page through
 * landscape -> portrait -> square -> landscape, capturing after each, and
 * records the label box and the frame side by side.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280", out: path.join(REPO, "artifacts/t1/session"),
  steps: ["1440x900", "390x844", "700x700", "844x390", "1440x900"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e.message)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
await page.goto(`${opts.origin}/?qa=1&composition=sourceExact`, { waitUntil: "load", timeout: 120000 });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 180000 });
await page.waitForTimeout(3200);
await page.evaluate(() => {
  window.__ILG_QA__.setAdaptiveQuality(false);
  window.__ILG_QA__.setQuality("high");
  window.__ILG_QA__.setPointer(0, 0);
  window.__ILG_QA__.pause();
  window.__ILG_QA__.setOffset(0, 0);
});
await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
await mkdir(opts.out, { recursive: true });
const report = { capturedAt: new Date().toISOString(), oneLiveSession: true, steps: [], errors };
for (let n = 0; n < opts.steps.length; n += 1) {
  const [w, h] = opts.steps[n].split("x").map(Number);
  await page.setViewportSize({ width: w, height: h });
  await page.waitForTimeout(600);
  await page.evaluate(() => window.__ILG_QA__.renderOnce());
  const file = path.join(opts.out, `${n}-${opts.steps[n]}.png`);
  await page.screenshot({ path: file });
  const state = await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    const l = qa.getLabelTruth(), v = qa.getV4State();
    return { labelBox: l.elementBox, framePlane: [v.sourceExactFrame.planeWidth,
                                                  v.sourceExactFrame.planeHeight],
             typeZ: l.typeZ, activeSlots: v.activeSlotCount,
             identity: v.slotIdentity.codesAreSlotIndexPlusOne,
             cols: v.sourceExactFrame.cols, rows: v.sourceExactFrame.rows };
  });
  const ok = Math.abs(state.labelBox[0] - state.framePlane[0]) < 1e-6
          && Math.abs(state.labelBox[1] - state.framePlane[1]) < 1e-6;
  report.steps.push({ step: n, viewport: opts.steps[n], png: path.relative(REPO, file),
                      ...state, labelBoxTracksFrame: ok });
  console.log(`${opts.steps[n]}  label=${state.labelBox.map((x) => x.toFixed(2))} frame=${state.framePlane.map((x) => x.toFixed(2))} tracks=${ok} slots=${state.activeSlots}`);
}
report.allStepsTrack = report.steps.every((s) => s.labelBoxTracksFrame);
report.identityHeld = report.steps.every((s) => s.identity);
await writeFile(path.join(opts.out, "session.json"), JSON.stringify(report, null, 2));
await ctx.close(); await browser.close();
console.log(`session ${report.allStepsTrack && report.identityHeld && !errors.length ? "PASS" : "FAIL"}`);
