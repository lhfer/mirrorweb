#!/usr/bin/env node
/** Frame sequences for the resize and long-scroll sessions, for the private package. */
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = path.join(REPO, "artifacts/f27/session-frames");
const Q = "composition=v2&verticalMode=tangent&portraitLaw=p1&portraitVertical=v2&phaseModel=rowOrigin";
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
async function open(w, h) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(`http://127.0.0.1:5280/?optics=v4&qa=1&${Q}&foundation=layout&annotate=0`, { waitUntil: "load" });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 120000 });
  await page.waitForTimeout(2000);
  await page.evaluate(() => { window.__ILG_QA__.setQuality("high"); window.__ILG_QA__.setPointer(0, 0); window.__ILG_QA__.pause(); });
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  return { ctx, page };
}
await mkdir(path.join(OUT, "resize"), { recursive: true });
await mkdir(path.join(OUT, "longscroll"), { recursive: true });
{
  const { ctx, page } = await open(1920, 1080);
  await page.evaluate(() => window.__ILG_QA__.setOffset(260, 180));
  const seq = [];
  for (let w = 1920; w >= 960; w -= 60) seq.push([w, Math.round(w * 0.5625 / 0.9)]);
  for (const vp of [[960, 720], [960, 500], [900, 899], [844, 390], [700, 700], [667, 375], [500, 900], [390, 844]]) seq.push(vp);
  for (const [i, [w, h]] of seq.entries()) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(160);
    await page.screenshot({ path: path.join(OUT, "resize", `${String(i).padStart(3, "0")}-${w}x${h}.png`) });
  }
  await ctx.close();
}
{
  const { ctx, page } = await open(1440, 900);
  const cellH = await page.evaluate(() => window.__ILG_QA__.getV4State().effectiveCellH);
  for (const [i, k] of [0, 0.49, -0.49, 0.51, -0.51, 10, -10, 50, -50, 100, -100].entries()) {
    await page.evaluate(([x, y]) => window.__ILG_QA__.setOffset(x, y), [k * 561.14, k * cellH]);
    await page.waitForTimeout(120);
    await page.screenshot({ path: path.join(OUT, "longscroll", `${String(i).padStart(3, "0")}-k${k}.png`) });
  }
  await ctx.close();
}
await browser.close();
console.log("session frames done");
