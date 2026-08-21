#!/usr/bin/env node
/**
 * Candidate beauty frames for the private culling package: one full-page
 * screenshot per viewport, at rest, media frozen at the same fixed time every
 * capture in this repo uses. No overlay, no annotation -- the page as shipped.
 *
 * Usage: v0-beauty.mjs --url=<origin> --out=<dir> [--vps=WxH,...]
 */
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { url: null, out: null,
  vps: ["1440x900", "1920x1080", "390x844", "844x390", "700x700"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--url=")) opts.url = a.slice(6);
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.goto(opts.url, { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(opts.out, `beauty-${vp}.png`) });
  process.stdout.write(`  beauty ${vp}\n`);
  await ctx.close();
}
await browser.close();
