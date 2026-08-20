#!/usr/bin/env node
/** Desktop and mobile beauty recordings: a slow drift so motion is visible, then rest. */
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = path.join(REPO, "artifacts/fsx-a/recording");
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
for (const [name, w, h] of [["desktop", 1440, 900], ["mobile", 390, 844]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1,
    isMobile: w < 500, hasTouch: w < 500 });
  const page = await ctx.newPage();
  await page.goto("http://127.0.0.1:5280/?qa=1&composition=sourceExact", { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 180000 });
  await page.waitForTimeout(3200);
  await page.evaluate(() => {
    window.__ILG_QA__.setAdaptiveQuality?.(false);
    window.__ILG_QA__.setQuality("high");
    window.__ILG_QA__.setPointer(0, 0);
    window.__ILG_QA__.pause();
  });
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  await mkdir(path.join(OUT, name), { recursive: true });
  const frames = 24;
  for (let i = 0; i < frames; i += 1) {
    const t = i / (frames - 1);
    // Pure world offsets, so the recording is reproducible and does not depend
    // on the frozen dragGain.
    await page.evaluate(([x, y]) => window.__ILG_QA__.setOffset(x, y),
                        [Math.round(900 * t), Math.round(500 * t)]);
    await page.waitForTimeout(90);
    await page.screenshot({ path: path.join(OUT, name, `${String(i).padStart(3, "0")}.png`) });
  }
  await ctx.close();
  console.log(`recorded ${name}`);
}
await browser.close();
