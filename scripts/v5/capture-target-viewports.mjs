#!/usr/bin/env node

/**
 * Stage F2: capture the live Target at a sweep of viewports.
 *
 * The responsive scaling law cannot be extrapolated from 1440x900, so it is
 * measured directly: the same rest pose at many viewport sizes, on one machine,
 * in one session, so nothing but the viewport differs between samples.
 *
 * Read-only. It loads the public page, waits for the loader to finish, idles,
 * screenshots. It never interacts, never posts, never downloads assets.
 *
 * Output goes to artifacts/, which is git-ignored: these are Target pixels and
 * must never be committed or hotlinked.
 *
 * Usage: capture-target-viewports.mjs --out=<dir> [--only=WxH,WxH] [--headed]
 */

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";

/**
 * `mode` records the intent of each sample, not a measured fact: `desktop`
 * above the site's own lg breakpoint, `portrait` / `landscape` below it. The
 * fit is free to disagree with these labels.
 */
const VIEWPORTS = [
  // required by the F2 brief
  { w: 1100, h: 720, mode: "desktop", required: true },
  { w: 1366, h: 768, mode: "desktop", required: true },
  { w: 1440, h: 900, mode: "desktop", required: true },
  { w: 1920, h: 1080, mode: "desktop", required: true },
  { w: 390, h: 844, mode: "portrait", required: true, mobile: true },
  { w: 844, h: 390, mode: "landscape", required: true, mobile: true },
  // desktop sweep, for fitting a continuous law and cross-validating it
  { w: 1024, h: 768, mode: "desktop" },
  { w: 1152, h: 864, mode: "desktop" },
  { w: 1280, h: 800, mode: "desktop" },
  { w: 1536, h: 864, mode: "desktop" },
  { w: 1680, h: 1050, mode: "desktop" },
  { w: 2560, h: 1440, mode: "desktop" },
  // same width, different height: separates a width law from an area law
  { w: 1440, h: 700, mode: "desktop" },
  { w: 1440, h: 1080, mode: "desktop" },
  // around the breakpoint
  { w: 960, h: 720, mode: "unknown" },
  { w: 1000, h: 700, mode: "unknown" },
  // mobile sweeps
  { w: 360, h: 800, mode: "portrait", mobile: true },
  { w: 414, h: 896, mode: "portrait", mobile: true },
  { w: 430, h: 932, mode: "portrait", mobile: true },
  { w: 667, h: 375, mode: "landscape", mobile: true },
  { w: 926, h: 428, mode: "landscape", mobile: true },
  // Portrait aspect separators. 390/414/430 x their natural heights all share
  // an aspect near 0.462, so a width law and a height law fit them equally
  // well. These break the tie: same width, very different height, and vice
  // versa.
  { w: 390, h: 700, mode: "portrait", mobile: true },
  { w: 390, h: 1000, mode: "portrait", mobile: true },
  { w: 500, h: 900, mode: "portrait", mobile: true },
  { w: 320, h: 900, mode: "portrait", mobile: true },
  { w: 700, h: 900, mode: "portrait", mobile: false },
  // Controls.
  // 1. Same viewport, no mobile UA / touch: separates "the site branches on
  //    width" from "the site branches on user agent or touch". Only the first
  //    is reproducible locally, so this decides whether the law is geometry.
  { w: 844, h: 390, mode: "landscape", mobile: false, control: "no-mobile-ua" },
  // 2. Same viewport at DPR 3: confirms CSS-normalised layout is DPR
  //    invariant, which is what lets fresh DPR1 mobile samples be compared
  //    with the frozen DPR3 D/E captures.
  { w: 390, h: 844, mode: "portrait", mobile: true, dpr: 3, control: "dpr3" },
];

const options = { out: path.join(REPO_ROOT, "artifacts/v5-target"), headless: true, only: null, dpr: 1 };
for (const arg of process.argv.slice(2)) {
  if (arg.startsWith("--out=")) options.out = path.resolve(REPO_ROOT, arg.slice(6));
  else if (arg.startsWith("--only=")) options.only = arg.slice(7).split(",");
  else if (arg.startsWith("--dpr=")) options.dpr = Number(arg.slice(6));
  else if (arg === "--headed") options.headless = false;
}

async function waitForScene(page, timeoutMs = 90_000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const state = await page.evaluate(() => {
      const text = document.body?.innerText || "";
      const percent = text.match(/(\d+)\s*%/);
      return { percent: percent ? Number(percent[1]) : null, hasCanvas: Boolean(document.querySelector("canvas")) };
    });
    if (state.hasCanvas && (state.percent === null || state.percent >= 100)) {
      await page.waitForTimeout(1500);
      return { ready: true, ...state };
    }
    await page.waitForTimeout(120);
  }
  return { ready: false };
}

const browser = await chromium.launch({
  channel: "chrome",
  headless: options.headless,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
});
await mkdir(options.out, { recursive: true });

const report = { target: TARGET, capturedAt: new Date().toISOString(), samples: [], errors: [] };
const wanted = options.only
  ? VIEWPORTS.filter((v) => options.only.includes(`${v.w}x${v.h}`) || options.only.includes(v.control))
  : VIEWPORTS;

for (const vp of wanted) {
  const dpr = vp.dpr || options.dpr || 1;
  const context = await browser.newContext({
    viewport: { width: vp.w, height: vp.h },
    deviceScaleFactor: dpr,
    isMobile: Boolean(vp.mobile),
    hasTouch: Boolean(vp.mobile),
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message)));
  try {
    await page.goto(TARGET, { waitUntil: "load", timeout: 90_000 });
    const ready = await waitForScene(page);
    // Idle so the grid is at rest and only the video inside the cards moves.
    await page.waitForTimeout(5000);
    const id = `${vp.w}x${vp.h}-dpr${dpr}${vp.control ? `-${vp.control}` : ""}`;
    const file = path.join(options.out, `${id}.png`);
    await page.screenshot({ path: file });
    const env = await page.evaluate(() => {
      const c = document.querySelector("canvas");
      return {
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        devicePixelRatio: window.devicePixelRatio,
        canvasCss: c ? [c.clientWidth, c.clientHeight] : null,
        canvasBuffer: c ? [c.width, c.height] : null,
        overlayIds: [...document.body.innerText.matchAll(/ILG[—-]\s?(\d+)/g)].map((m) => m[1]).slice(0, 24),
        title: document.title,
      };
    });
    report.samples.push({ id, ...vp, dpr, ready: ready.ready, env, png: path.relative(REPO_ROOT, file) });
    console.log(`captured ${id}  ready=${ready.ready}  buffer=${env.canvasBuffer}`);
  } catch (error) {
    report.errors.push(`${vp.w}x${vp.h}: ${error.message}`);
    console.error(`FAILED ${vp.w}x${vp.h}: ${error.message}`);
  }
  if (errors.length) report.errors.push(...errors.map((e) => `${vp.w}x${vp.h}: ${e}`));
  await context.close();
}

await writeFile(path.join(options.out, "capture.json"), JSON.stringify(report, null, 2));
await browser.close();
console.log(`done -> ${options.out}  (${report.samples.length} samples, ${report.errors.length} errors)`);
