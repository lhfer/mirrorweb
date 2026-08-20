#!/usr/bin/env node
/** Resize, long-scroll and pool-boundary frame sequences for the private package. */
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = path.join(REPO, "artifacts/fsx/session-frames");
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto("http://127.0.0.1:5280/?optics=v4&qa=1&composition=sourceExact&foundation=layout&annotate=0",
                { waitUntil: "load" });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 120000 });
await page.waitForTimeout(1800);
await page.evaluate(() => { window.__ILG_QA__.setQuality("high"); window.__ILG_QA__.setPointer(0, 0); window.__ILG_QA__.pause(); });
await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));

async function shots(name, steps, before) {
  await mkdir(path.join(OUT, name), { recursive: true });
  if (before) await before();
  for (const [i, step] of steps.entries()) {
    // Both kinds of step used to be arrays, so the offset steps were being fed
    // to setViewportSize -- which is how this asked for a zero-width screenshot.
    if (!step.offset) {
      await page.setViewportSize({ width: step[0], height: step[1] });
      await page.waitForTimeout(200);
      await page.screenshot({ path: path.join(OUT, name, `${String(i).padStart(3, "0")}-${step[0]}x${step[1]}.png`) });
    } else {
      await page.evaluate(([x, y]) => window.__ILG_QA__.setOffset(x, y), step.offset);
      await page.waitForTimeout(140);
      await page.screenshot({ path: path.join(OUT, name, `${String(i).padStart(3, "0")}-k${step.k}.png`) });
    }
  }
}
const resize = [];
for (let w = 1920; w >= 960; w -= 60) resize.push([w, Math.round((w * 0.5625) / 0.9)]);
for (const vp of [[960, 720], [960, 500], [900, 899], [844, 390], [700, 700], [667, 375], [500, 900], [390, 844]]) resize.push(vp);
await shots("resize", resize, async () => { await page.evaluate(() => window.__ILG_QA__.setOffset(260, 180)); });

await page.setViewportSize({ width: 1440, height: 900 });
await page.waitForTimeout(200);
const f = await page.evaluate(() => window.__ILG_QA__.getV4State().sourceExactFrame);
await shots("longscroll",
  [0, 0.49, -0.49, 0.51, -0.51, 10, -10, 50, -50, 100, -100]
    .map((k) => ({ offset: [k * f.cellW, k * f.cellH], k })));

await page.evaluate(() => window.__ILG_QA__.setOffset(0, 0));
await shots("pool-boundary", [[1440, 700], [1440, 900], [700, 700], [320, 900], [320, 980],
                              [320, 900], [700, 700], [1440, 900], [1440, 700]]);
await ctx.close();
await browser.close();
console.log("session frames done");
