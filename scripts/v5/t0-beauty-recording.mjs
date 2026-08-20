#!/usr/bin/env node
/**
 * Desktop and mobile beauty recordings.
 *
 * Supersedes `fsxa-beauty-recording.mjs`, which drove `setOffset` in a loop
 * with the adaptive sampler off. The render loop returned early in that state
 * and `setOffset` did not draw, so all 24 frames were the same pixels: a 9
 * second GIF of one still image.
 *
 * Every frame here is drawn explicitly, hashed, and stamped with the offset
 * READ BACK OUT OF THE ENGINE rather than the offset that was requested -- a
 * recording that logs its own inputs cannot show that anything moved.
 */
import { createHash } from "node:crypto";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280", out: path.join(REPO, "artifacts/t1/recording"),
               frames: 24, minUnique: 12 };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--frames=")) opts.frames = Number(a.slice(9));
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const report = { capturedAt: new Date().toISOString(), frames: opts.frames,
  minUniqueRequired: opts.minUnique,
  supersedes: "artifacts/fsx-a/recording (24 identical frames)",
  method: "explicit renderOnce() per frame; offsets read back from the engine",
  recordings: [], assertions: [], errors: [] };
const A = (n, ok, d) => report.assertions.push({ assertion: n, pass: !!ok, detail: d ?? null });

for (const [name, w, h] of [["desktop", 1440, 900], ["mobile", 390, 844]]) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1,
    isMobile: w < 500, hasTouch: w < 500 });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => report.errors.push(`${name}: ${e.message}`));
  await page.goto(`${opts.origin}/?qa=1&composition=sourceExact`, { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 180000 });
  await page.waitForTimeout(3200);
  await page.evaluate(() => {
    window.__ILG_QA__.setAdaptiveQuality(false);
    window.__ILG_QA__.setQuality("high");
    window.__ILG_QA__.setPointer(0, 0);
    window.__ILG_QA__.pause();
  });
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  const dir = path.join(opts.out, name);
  await mkdir(dir, { recursive: true });
  const frames = [];
  for (let i = 0; i < opts.frames; i += 1) {
    const t = i / (opts.frames - 1);
    // Pure world offsets, so the recording is reproducible and does not depend
    // on the frozen dragGain.
    const state = await page.evaluate(([x, y]) => {
      const qa = window.__ILG_QA__;
      qa.setOffset(x, y);
      qa.renderOnce();
      const v = qa.getV4State();
      return { requested: [x, y], engineScrollX: v.scrollX, engineScrollY: v.scrollY,
               gridX: v.gridX, gridY: v.gridY, renderStamp: qa.getRenderStamp() };
    }, [Math.round(900 * t), Math.round(500 * t)]);
    await page.waitForTimeout(70);
    const file = path.join(dir, `${String(i).padStart(3, "0")}.png`);
    await page.screenshot({ path: file });
    const sha = createHash("sha256").update(await readFile(file)).digest("hex");
    frames.push({ index: i, ...state, png: path.relative(REPO, file), sha256: sha });
  }
  const uniq = new Set(frames.map((f) => f.sha256));
  const movedX = new Set(frames.map((f) => f.engineScrollX)).size;
  report.recordings.push({ name, viewport: [w, h], frameCount: frames.length,
    uniqueFrameCount: uniq.size, firstSha: frames[0].sha256,
    lastSha: frames[frames.length - 1].sha256, distinctEngineScrollX: movedX, frames });
  A(`${name}: at least ${opts.frames} frames`, frames.length >= opts.frames, frames.length);
  A(`${name}: at least ${opts.minUnique} unique frames`, uniq.size >= opts.minUnique,
    { unique: uniq.size, of: frames.length });
  A(`${name}: first and last frame differ`,
    frames[0].sha256 !== frames[frames.length - 1].sha256,
    { first: frames[0].sha256.slice(0, 16), last: frames[frames.length - 1].sha256.slice(0, 16) });
  A(`${name}: the engine's own scroll moved, not just the request`,
    movedX >= opts.minUnique, { distinctEngineScrollX: movedX });
  console.log(`${name}: ${uniq.size}/${frames.length} unique, engine scrollX values ${movedX}`);
  await ctx.close();
}
await browser.close();
A("no page errors", report.errors.length === 0, report.errors.slice(0, 5));
report.passed = report.assertions.filter((a) => a.pass).length;
report.total = report.assertions.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
await writeFile(path.join(opts.out, "recording.json"), JSON.stringify(report, null, 2));
console.log(`recording ${report.verdict}  ${report.passed}/${report.total}`);
for (const a of report.assertions) if (!a.pass) console.log(`  FAIL ${a.assertion}  ${JSON.stringify(a.detail)}`);
