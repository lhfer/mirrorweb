#!/usr/bin/env node
/**
 * Dump the source-exact ENGINE state at a list of viewports.
 *
 * Everything here is read back off the running app -- the layout frame the
 * renderer built, the live object matrices, the live camera projection. Nothing
 * is recomputed from the model, because the whole point of the source-contract
 * gate is to compare the engine with the model and with the Target, and a
 * comparison of the model with itself proves nothing.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280", out: path.join(REPO, "artifacts/fsx/engine"), vps: [] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e.message)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
await page.goto(`${opts.origin}/?optics=v4&qa=1&composition=sourceExact&foundation=layout&annotate=0`,
                { waitUntil: "load" });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 120000 });
await page.waitForTimeout(1800);
await page.evaluate(() => {
  window.__ILG_QA__.setQuality("high");
  window.__ILG_QA__.setPointer(0, 0);
  window.__ILG_QA__.pause();
  window.__ILG_QA__.setOffset(0, 0);
});

const out = { capturedAt: new Date().toISOString(), route: "composition=sourceExact", viewports: [], errors };
for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  await page.setViewportSize({ width: w, height: h });
  await page.waitForTimeout(180);
  await page.evaluate(() => window.__ILG_QA__.setOffset(0, 0));
  await page.waitForTimeout(60);
  const state = await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    const v = qa.getV4State();
    return {
      viewport: [window.innerWidth, window.innerHeight],
      frame: v.sourceExactFrame,
      slotIdentity: v.slotIdentity,
      activeSlotCount: v.activeSlotCount,
      camera: v.sourceExactCamera,
      assertions: v.runtimeTruthAssertions,
      pool: qa.getPoolState(),
      scroll: [qa.getState().scrollX, qa.getState().scrollY],
      slots: qa.getSourceExactSlots(),
    };
  });
  out.viewports.push({ id: vp, ...state });
  console.log(`${vp}  cols=${state.frame.cols} rows=${state.frame.rows} slots=${state.activeSlotCount}`);
}
await mkdir(opts.out, { recursive: true });
await writeFile(path.join(opts.out, "engine.json"), JSON.stringify(out));
await ctx.close();
await browser.close();
console.log(`done -> ${opts.out}/engine.json  (${out.viewports.length} viewports, ${errors.length} errors)`);
