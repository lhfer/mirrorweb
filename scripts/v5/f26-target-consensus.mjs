#!/usr/bin/env node
/**
 * Multi-frame Target capture, so video content stops contaminating geometry.
 *
 * A dark video frame can read as void, which invents gutters and truncates card
 * edges. One frame cannot tell that apart from real structure; several frames
 * of the same viewport can, because a real gutter is void in every one of them
 * and a dark patch of video is not.
 *
 * Captures N frames per viewport, spaced far enough apart that the clips have
 * moved on. Read-only.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";
const opts = { out: path.join(REPO, "artifacts/v5-target-consensus"), frames: 5, gapMs: 1400,
  vps: ["1440x900", "1100x720", "390x844", "844x390", "760x470", "926x428", "960x500"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--frames=")) opts.frames = Number(a.slice(9));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
}
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const report = { target: TARGET, capturedAt: new Date().toISOString(), frames: opts.frames, samples: [] };
for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1,
    isMobile: w < 500, hasTouch: w < 500 });
  const page = await ctx.newPage();
  await page.goto(TARGET, { waitUntil: "load", timeout: 90_000 });
  for (let t = 0; t < 240; t++) {
    const s = await page.evaluate(() => {
      const m = (document.body?.innerText || "").match(/(\d+)\s*%/);
      return { p: m ? Number(m[1]) : null, c: !!document.querySelector("canvas") };
    });
    if (s.c && (s.p === null || s.p >= 100)) break;
    await page.waitForTimeout(150);
  }
  await page.waitForTimeout(4000);
  const files = [];
  for (let n = 0; n < opts.frames; n++) {
    const f = path.join(opts.out, `${vp}-f${n}.png`);
    await page.screenshot({ path: f });
    files.push(path.basename(f));
    if (n < opts.frames - 1) await page.waitForTimeout(opts.gapMs);
  }
  report.samples.push({ id: vp, viewport: [w, h], files });
  console.log(`captured ${vp} x${opts.frames}`);
  await ctx.close();
}
await writeFile(path.join(opts.out, "capture.json"), JSON.stringify(report, null, 2));
await browser.close();
console.log(`done -> ${opts.out}`);
