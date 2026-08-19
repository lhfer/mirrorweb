#!/usr/bin/env node

/**
 * Round 1 automated engineering gate for the V4 multi-card grid preview.
 *
 * Human optical-zone annotation is SKIPPED BY PRODUCT OWNER and formal pixel
 * truth stays BLOCKED, so this gate deliberately checks only engineering
 * properties that do not require a human target truth:
 *
 *   V3 still runs · V4 never samples media directly · no fixed black body rim ·
 *   pointer changes the reflection · no full-screen dispersion · zero console
 *   and GPU validation errors · stable resource counts · video uploads are not
 *   per-rAF · no border-pixel streaking on a partially off-screen card · no
 *   sustained memory growth over 60s · desktop and mobile both run · V4 can
 *   always fall back to V3.
 */

import { spawn } from "node:child_process";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const PRIVATE_DIR = path.join(REPO_ROOT, "qa-v4/review/round-1/gate");
const PUBLIC_RESULT = path.join(REPO_ROOT, "qa-v4/results/round1-grid-preview-gate.json");
const MEMORY_WINDOW_MS = 60_000;

const options = {
  port: 5287,
  headless: process.env.ILG_GATE_HEADLESS === "1",
  memoryMs: Number(process.env.ILG_GATE_MEMORY_MS ?? MEMORY_WINDOW_MS),
};
for (const argument of process.argv.slice(2)) {
  if (argument.startsWith("--port=")) options.port = Number(argument.slice("--port=".length));
  else if (argument === "--headless") options.headless = true;
  else if (argument.startsWith("--memory-ms=")) options.memoryMs = Number(argument.slice("--memory-ms=".length));
  else throw new Error(`Unknown argument: ${argument}`);
}

const checks = [];
function check(id, passed, evidence) {
  checks.push({ id, status: passed ? "PASSED" : "FAILED", evidence });
  console.log(`${passed ? "PASS" : "FAIL"} ${id} ${evidence === undefined ? "" : JSON.stringify(evidence)}`);
}

function startPreview(port) {
  const child = spawn(
    "npx",
    ["vite", "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"] },
  );
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("vite preview did not start")), 30_000);
    const onData = (chunk) => {
      if (String(chunk).includes("Local:")) {
        clearTimeout(timer);
        resolve(child);
      }
    };
    child.stdout.on("data", onData);
    child.stderr.on("data", onData);
    child.once("error", reject);
  });
}

async function newPage(browser, viewport, isMobile = false) {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    isMobile,
    hasTouch: isMobile,
  });
  const page = await context.newPage();
  const consoleErrors = [];
  const gpuErrors = [];
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    consoleErrors.push(text);
    if (/webgpu|validation|gpu/i.test(text)) gpuErrors.push(text);
  });
  page.on("pageerror", (error) => consoleErrors.push(`pageerror: ${error.message}`));
  return { context, page, consoleErrors, gpuErrors };
}

async function waitReady(page) {
  await page.waitForFunction(
    () => window.__ILG_QA__ !== undefined && (window.__ILG_QA__.getState()?.ready === true),
    undefined,
    { timeout: 90_000 },
  );
}

let preview;
let browser;
try {
  await rm(PRIVATE_DIR, { recursive: true, force: true });
  await mkdir(PRIVATE_DIR, { recursive: true });
  preview = await startPreview(options.port);
  const origin = `http://127.0.0.1:${options.port}`;
  browser = await chromium.launch({
    channel: "chrome",
    headless: options.headless,
    args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features", "--enable-precise-memory-info"],
  });

  /* ---------------------------------------------------------- V3 still runs */
  {
    const { context, page, consoleErrors } = await newPage(browser, { width: 1440, height: 900 });
    await page.goto(`${origin}/?qa=1`, { waitUntil: "load" });
    await waitReady(page);
    await page.waitForTimeout(2500);
    const state = await page.evaluate(() => window.__ILG_QA__.getState());
    const v4Present = await page.evaluate(() => window.__ILG_V4_GRID_QA__ !== undefined);
    check("V3_PAGE_AVAILABLE", state.ready === true && state.optics === undefined && v4Present === false, {
      glass: state.glass,
      milestone: state.milestone,
      backend: state.backend,
      v4GlobalsPresent: v4Present,
      consoleErrors: consoleErrors.length,
    });
    await context.close();
  }

  /* ------------------------------------------------- V4 preview, desktop run */
  const { context, page, consoleErrors, gpuErrors } = await newPage(browser, { width: 1440, height: 900 });
  await page.goto(`${origin}/grid-lab-v4?qa=1&hud=0`, { waitUntil: "load" });
  await waitReady(page);
  await page.waitForTimeout(5000);

  const v4State = await page.evaluate(() => window.__ILG_V4_GRID_QA__.getV4State());
  const poolBefore = await page.evaluate(() => window.__ILG_V4_GRID_QA__.getPoolState());
  const metrics = await page.evaluate(() => window.__ILG_V4_GRID_QA__.getMetrics());

  const materialSource = await readFile(path.join(REPO_ROOT, "src/materials/LiquidGlassMaterialV4.ts"), "utf8");
  check(
    "V4_NORMAL_PATH_NO_DIRECT_MEDIA",
    v4State.normalPathDirectMedia === false
      && !materialSource.includes("mediaMap")
      && !materialSource.includes("directMediaTexture")
      && materialSource.includes("sceneColorTexture"),
    { runtime: v4State.normalPathDirectMedia, sceneColor: v4State.sceneColor },
  );

  const frames = {};
  const shot = async (name) => {
    const file = path.join(PRIVATE_DIR, `${name}.png`);
    await page.screenshot({ path: file });
    frames[name] = `${name}.png`;
  };

  await page.evaluate(() => {
    window.__ILG_QA__.reset();
    window.__ILG_QA__.setPointer(0, 0);
  });
  await page.waitForTimeout(1200);
  await shot("rest");
  const cardQuads = await page.evaluate(() => window.__ILG_V4_GRID_QA__.getCardQuads());

  await page.evaluate(() => window.__ILG_QA__.setPointer(-0.9, 0));
  await page.waitForTimeout(900);
  await shot("pointer-left");
  await page.evaluate(() => window.__ILG_QA__.setPointer(0.9, 0));
  await page.waitForTimeout(900);
  await shot("pointer-right");

  // Half a grid cell puts cards across every frame border.
  await page.evaluate(() => {
    window.__ILG_QA__.setPointer(0, 0);
    window.__ILG_QA__.setOffset(278.86, 214);
  });
  await page.waitForTimeout(900);
  await shot("partial-viewport");

  // The material's own dispersion debug view isolates the chroma the glass
  // introduces from the chroma the video already had.
  await page.evaluate(() => {
    window.__ILG_QA__.reset();
    window.__ILG_V4_GRID_QA__.setDebugMode("dispersion");
  });
  await page.waitForTimeout(900);
  await shot("dispersion-debug");
  await page.evaluate(() => window.__ILG_V4_GRID_QA__.setDebugMode("beauty"));
  await page.waitForTimeout(600);

  const manifestPath = path.join(PRIVATE_DIR, "frames.local.json");
  await writeFile(manifestPath, `${JSON.stringify({ frames, cardQuads }, null, 2)}\n`, "utf8");
  const analysisPath = path.join(PRIVATE_DIR, "analysis.local.json");
  execFileSync("python3", [
    path.join(REPO_ROOT, "scripts/v4/analyze-round1-gate.py"),
    "--manifest", manifestPath,
    "--output", analysisPath,
  ], { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"] });
  const analysis = JSON.parse(await readFile(analysisPath, "utf8"));

  check(
    "NO_FIXED_BLACK_BODY_RIM",
    Boolean(analysis.bodyRim)
      && analysis.bodyRim.minRimLuma > 0.02
      && analysis.bodyRim.spread > 0.05,
    analysis.bodyRim,
  );
  check(
    "POINTER_CHANGES_REFLECTION",
    Boolean(analysis.pointer) && analysis.pointer.rimChangedPixelRatio > 0.02,
    analysis.pointer,
  );
  check(
    "NO_FULL_SCREEN_DISPERSION",
    Boolean(analysis.dispersionDebug)
      && analysis.dispersionDebug.interiorActiveRatio < 0.05
      && analysis.dispersionDebug.rimActiveRatio > analysis.dispersionDebug.interiorActiveRatio,
    analysis.dispersionDebug,
  );
  // Border smearing is a geometric property, not a statistical one: if the
  // furthest sample the material can request still lands inside the overscanned
  // scene target, screen-UV clamping cannot happen at all. The content-based
  // run measurement is kept as supporting evidence only, because flat video
  // content produces identical border pixels without any smearing.
  const causal = await (async () => {
    const probe = await newPage(browser, { width: 1440, height: 900 });
    await probe.page.goto(`${origin}/grid-lab-v4?qa=1&hud=0&overscan=1`, { waitUntil: "load" });
    await waitReady(probe.page);
    await probe.page.evaluate(() => window.__ILG_QA__.setOffset(278.86, 214));
    await probe.page.waitForTimeout(1500);
    const file = path.join(PRIVATE_DIR, "partial-viewport-no-overscan.png");
    await probe.page.screenshot({ path: file });
    const headroom = await probe.page.evaluate(
      () => window.__ILG_V4_GRID_QA__.getV4State().sceneColor.clampHeadroom,
    );
    await probe.context.close();
    return { file: path.basename(file), headroom };
  })();
  check(
    "NO_BORDER_PIXEL_STREAK",
    v4State.sceneColor.clampHeadroom > 0 && causal.headroom <= 0,
    {
      overscan: v4State.sceneColor.overscan,
      clampHeadroomWithOverscan: Number(v4State.sceneColor.clampHeadroom.toFixed(5)),
      clampHeadroomWithoutOverscan: Number(causal.headroom.toFixed(5)),
      contentRunRatioPartialViewport: analysis.borderStreak.worstRunRatio,
      contentRunRatioRest: analysis.borderStreakRest.worstRunRatio,
      note: "positive headroom means no screen-UV sample can leave the scene target",
    },
  );

  /* -------------------------------------------- resources, video and memory */
  const samples = [];
  const started = Date.now();
  await page.evaluate(() => window.__ILG_QA__.reset());
  while (Date.now() - started < options.memoryMs) {
    const elapsed = Date.now() - started;
    await page.evaluate((phase) => {
      // Keep the pool remapping so resource growth would show up.
      window.__ILG_QA__.setOffset(Math.sin(phase / 900) * 2200, Math.cos(phase / 1300) * 1600);
      window.__ILG_QA__.setPointer(Math.sin(phase / 700), Math.cos(phase / 1100));
    }, elapsed);
    await page.waitForTimeout(2500);
    samples.push(await page.evaluate(() => ({
      heap: performance.memory ? performance.memory.usedJSHeapSize : 0,
      pool: window.__ILG_V4_GRID_QA__.getPoolState(),
      v4: window.__ILG_V4_GRID_QA__.getV4State(),
    })));
  }
  const poolAfter = samples.at(-1).pool;
  const firstThird = samples.slice(0, Math.max(1, Math.floor(samples.length / 3)));
  const lastThird = samples.slice(-Math.max(1, Math.floor(samples.length / 3)));
  // A live heap sawtooths between collections, so the post-collection floor is
  // the only part of it that reveals a real leak.
  const floor = (values) => Math.min(...values.filter((value) => value > 0), Infinity);
  const heapStart = floor(firstThird.map((entry) => entry.heap));
  const heapEnd = floor(lastThird.map((entry) => entry.heap));
  check(
    "RESOURCE_COUNT_STABLE",
    poolAfter.slots === poolBefore.slots
      && poolAfter.materials === poolBefore.materials
      && poolAfter.geometries === poolBefore.geometries
      && poolAfter.textures === poolBefore.textures
      && poolAfter.created === poolBefore.created
      && poolAfter.destroyed === poolBefore.destroyed
      && poolAfter.remaps > poolBefore.remaps,
    { before: poolBefore, after: poolAfter },
  );
  const last = samples.at(-1).v4;
  // Frames are counted across all clips, so the per-clip rate is what has to
  // stay below the render rate.
  const clipCount = Math.max(1, Number(last.asset.videos) || 1);
  const perClipFrames = last.videoFrames / clipCount;
  check(
    "VIDEO_UPLOAD_NOT_PER_RENDER_FRAME",
    perClipFrames > 0 && perClipFrames < last.renderedFrames * 0.9,
    {
      videoFramesTotal: last.videoFrames,
      clips: clipCount,
      perClipFrames: Math.round(perClipFrames),
      renderedFrames: last.renderedFrames,
      ratio: Number((perClipFrames / Math.max(1, last.renderedFrames)).toFixed(3)),
      videoFrameCallback: last.asset.videoFrameCallback,
    },
  );
  check(
    "NO_SUSTAINED_MEMORY_GROWTH",
    !Number.isFinite(heapStart) || heapEnd <= heapStart * 1.25,
    {
      seconds: Math.round((Date.now() - started) / 1000),
      samples: samples.length,
      heapFloorStartMb: Number((heapStart / 1048576).toFixed(2)),
      heapFloorEndMb: Number((heapEnd / 1048576).toFixed(2)),
      growth: Number.isFinite(heapStart) ? Number((heapEnd / heapStart).toFixed(3)) : null,
      poolStable: poolAfter.created === poolBefore.created && poolAfter.destroyed === poolBefore.destroyed,
    },
  );

  check("CONSOLE_ERROR_FREE", consoleErrors.length === 0, consoleErrors.slice(0, 5));
  check("GPU_VALIDATION_ERROR_FREE", gpuErrors.length === 0, gpuErrors.slice(0, 5));
  await context.close();

  /* ------------------------------------------------------------------ mobile */
  {
    const mobile = await newPage(browser, { width: 390, height: 844 }, true);
    await mobile.page.goto(`${origin}/?optics=v4&qa=1`, { waitUntil: "load" });
    await waitReady(mobile.page);
    await mobile.page.waitForTimeout(4000);
    const mobileState = await mobile.page.evaluate(() => window.__ILG_V4_GRID_QA__.getV4State());
    const mobileMetrics = await mobile.page.evaluate(() => window.__ILG_QA__.getMetrics());
    await mobile.page.screenshot({ path: path.join(PRIVATE_DIR, "mobile-portrait.png") });
    check(
      "DESKTOP_AND_MOBILE_RUN",
      mobileState.mobileViewport === true && mobile.consoleErrors.length === 0 && metrics.backend !== undefined,
      {
        desktop: { backend: metrics.backend, medianFrameMs: metrics.medianFrameMs, quality: metrics.quality },
        mobile: {
          backend: mobileMetrics.backend,
          medianFrameMs: mobileMetrics.medianFrameMs,
          quality: mobileMetrics.quality,
          dpr: mobileState.dpr,
          consoleErrors: mobile.consoleErrors.length,
        },
      },
    );
    await mobile.context.close();
  }

  /* ------------------------------------------------------ fall back to V3 */
  {
    const fallback = await newPage(browser, { width: 1440, height: 900 });
    await fallback.page.goto(`${origin}/?optics=v4&qa=1`, { waitUntil: "load" });
    await waitReady(fallback.page);
    const asV4 = await fallback.page.evaluate(() => window.__ILG_QA__.getState().optics);
    await fallback.page.goto(`${origin}/?optics=v3&qa=1`, { waitUntil: "load" });
    await waitReady(fallback.page);
    const asV3 = await fallback.page.evaluate(() => ({
      optics: window.__ILG_QA__.getState().optics,
      glass: window.__ILG_QA__.getState().glass,
      v4Globals: window.__ILG_V4_GRID_QA__ !== undefined,
    }));
    check(
      "V4_CAN_RETURN_TO_V3",
      asV4 === "v4" && asV3.optics === undefined && asV3.glass === "volume" && asV3.v4Globals === false,
      { v4: asV4, v3: asV3, consoleErrors: fallback.consoleErrors.length },
    );
    await fallback.context.close();
  }

  const failed = checks.filter((entry) => entry.status === "FAILED");
  const result = {
    schemaVersion: 1,
    round: 1,
    scope: "v4-grid-preview",
    generator: "round1-gate-v1",
    humanAnnotation: "SKIPPED_BY_PRODUCT_OWNER",
    formalPixelTruth: "BLOCKED",
    finalTargetMatch: "BLOCKED",
    productVisualAcceptance: "PENDING_HUMAN_PREVIEW",
    status: failed.length === 0 ? "PASS" : "FAIL",
    failed: failed.map((entry) => entry.id),
    desktopMetrics: {
      backend: metrics.backend,
      medianFrameMs: metrics.medianFrameMs,
      p95FrameMs: metrics.p95FrameMs,
      drawCalls: metrics.drawCalls,
      triangles: metrics.triangles,
      quality: metrics.quality,
    },
    sceneColor: v4State.sceneColor,
    pool: poolBefore,
    checks,
  };
  await writeFile(PUBLIC_RESULT, `${JSON.stringify(result, null, 2)}\n`, "utf8");
  console.log(`\n${result.status} · ${checks.length - failed.length}/${checks.length} checks`);
  console.log(`Result: ${path.relative(REPO_ROOT, PUBLIC_RESULT)}`);
  process.exitCode = failed.length === 0 ? 0 : 1;
} finally {
  await browser?.close();
  preview?.kill("SIGTERM");
}
