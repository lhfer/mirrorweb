#!/usr/bin/env node

/**
 * Stage F1 evidence: media fit.
 *
 * Captures the three fit modes on the calibration target (circles must stay
 * circles) and on the three real clips, media-only so the glass cannot be
 * blamed for a distortion the media plane already has.
 */

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const options = { origin: "http://127.0.0.1:5280", out: path.join(REPO_ROOT, "qa-v5/mediafit"), headless: true, dpr: 1 };
for (const arg of process.argv.slice(2)) {
  if (arg.startsWith("--origin=")) options.origin = arg.slice(9);
  else if (arg.startsWith("--out=")) options.out = path.resolve(REPO_ROOT, arg.slice(6));
  else if (arg === "--headed") options.headless = false;
  else if (arg.startsWith("--dpr=")) options.dpr = Number(arg.slice(6));
}

const browser = await chromium.launch({
  channel: "chrome",
  headless: options.headless,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
});

async function session(query) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: options.dpr });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${options.origin}/?optics=v4&qa=1${query}`, { waitUntil: "load" });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 120_000 });
  await page.waitForTimeout(1800);
  return { context, page, errors };
}

await mkdir(options.out, { recursive: true });
const report = { modes: [], clips: null, errors: [] };

// ---- calibration target, all three modes, media only ---------------------
{
  const { context, page, errors } = await session("&mediacal=1");
  await page.evaluate(() => {
    window.__ILG_QA__.setRenderLayers({ glass: false, media: true, labels: false });
    window.__ILG_QA__.setPointer(0, 0);
    window.__ILG_QA__.setOffset(0, 0);
    window.__ILG_QA__.pause();
  });
  for (const mode of ["cover", "contain", "stretch"]) {
    await page.evaluate((m) => window.__ILG_QA__.setMediaFitMode(m), mode);
    await page.waitForTimeout(320);
    await page.screenshot({ path: path.join(options.out, `calibration-${mode}${options.dpr === 1 ? "" : `-dpr${options.dpr}`}.png`) });
    const fits = await page.evaluate(() => window.__ILG_QA__.getMediaFits());
    report.modes.push({ mode, fits });
  }
  report.errors.push(...errors);
  await context.close();
}

// ---- the three real clips, cover, media only -----------------------------
{
  const { context, page, errors } = await session("");
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  await page.evaluate(() => {
    window.__ILG_QA__.setRenderLayers({ glass: false, media: true, labels: false });
    window.__ILG_QA__.setPointer(0, 0);
    window.__ILG_QA__.pause();
  });
  for (const mode of ["cover", "stretch"]) {
    await page.evaluate((m) => window.__ILG_QA__.setMediaFitMode(m), mode);
    await page.waitForTimeout(320);
    await page.evaluate(() => window.__ILG_QA__.setOffset(0, 0));
    await page.waitForTimeout(220);
    await page.screenshot({ path: path.join(options.out, `clips-${mode}.png`) });
  }
  await page.evaluate((m) => window.__ILG_QA__.setMediaFitMode(m), "cover");
  report.clips = await page.evaluate(() => window.__ILG_QA__.getMediaFits());
  // Beauty frame with the glass back on, for the shipping look.
  await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: true, media: false, labels: true }));
  await page.waitForTimeout(320);
  await page.screenshot({ path: path.join(options.out, "beauty-cover.png") });
  report.errors.push(...errors);
  await context.close();
}

await writeFile(path.join(options.out, "mediafit.json"), JSON.stringify(report, null, 2));
await browser.close();
console.log(JSON.stringify(report.clips, null, 2));
if (report.errors.length) console.error("page errors:\n" + report.errors.join("\n"));
console.log(`done -> ${options.out}`);
