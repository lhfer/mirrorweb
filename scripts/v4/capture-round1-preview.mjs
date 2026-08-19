#!/usr/bin/env node

/**
 * Round 1 human-review capture package for the V4 multi-card grid preview.
 *
 * Produces, for the fixed review states, matched V3 and V4 frames plus desktop
 * and mobile session videos. Everything it writes contains Target-adjacent or
 * local pixels, so it all stays under qa-v4/review/, which is ignored.
 *
 * This is preview evidence for a human product decision. It is NOT a pixel
 * comparison against the Golden target: formal pixel truth remains BLOCKED and
 * human optical-zone annotation is SKIPPED BY PRODUCT OWNER.
 */

import { spawn } from "node:child_process";
import { mkdir, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DEFAULT_OUT_ROOT = path.join(REPO_ROOT, "qa-v4/review/round-1");

// Grid geometry, mirrored from src/config.ts so the harness can centre a chosen
// card without reaching into the page.
const CELL_W = 557.72;
const CELL_H = 428;
const REST_Y0 = -211.05;
const brickColumn = (i, j) => i + (((j % 2) + 2) % 2 === 1 ? 0.5 : 0);
const centerOn = (i, j) => ({ x: brickColumn(i, j) * CELL_W, y: j * CELL_H + REST_Y0 });

const options = {
  port: 5288,
  headless: process.env.ILG_CAPTURE_HEADLESS === "1",
  videoSeconds: 26,
  out: DEFAULT_OUT_ROOT,
};
for (const argument of process.argv.slice(2)) {
  if (argument.startsWith("--port=")) options.port = Number(argument.slice("--port=".length));
  else if (argument === "--headless") options.headless = true;
  else if (argument.startsWith("--video-seconds=")) options.videoSeconds = Number(argument.slice("--video-seconds=".length));
  else if (argument.startsWith("--out=")) options.out = path.resolve(REPO_ROOT, argument.slice("--out=".length));
  else throw new Error(`Unknown argument: ${argument}`);
}
const OUT_ROOT = options.out;
const STATES_DIR = path.join(OUT_ROOT, "states");
const VIDEO_DIR = path.join(OUT_ROOT, "session");

function startPreview(port) {
  const child = spawn("npx", ["vite", "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"], {
    cwd: REPO_ROOT,
    stdio: ["ignore", "pipe", "pipe"],
  });
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

async function readyPage(browser, url, viewport, isMobile = false) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, isMobile, hasTouch: isMobile });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto(url, { waitUntil: "load" });
  await page.waitForFunction(
    () => window.__ILG_QA__ !== undefined && window.__ILG_QA__.getState()?.ready === true,
    undefined,
    { timeout: 90_000 },
  );
  await page.waitForTimeout(2500);
  return { context, page, errors };
}

/** Fixed video timestamp so V3 and V4 show the same clip frame. */
async function settle(page, seconds = 2) {
  await page.evaluate((value) => window.__ILG_QA__.setTime(value), seconds);
  await page.waitForTimeout(650);
}

async function probeCardCells(page) {
  // Candidate cells, one per clip plus neighbours, measured on the real frame.
  const cells = [[0, 0], [1, 0], [2, 0], [0, 1], [1, 1], [2, 1], [3, 0], [4, 0]];
  const measured = [];
  for (const [i, j] of cells) {
    const offset = centerOn(i, j);
    await page.evaluate((value) => {
      window.__ILG_QA__.setPointer(0, 0);
      window.__ILG_QA__.setOffset(value.x, value.y);
    }, offset);
    await settle(page);
    const buffer = await page.screenshot();
    measured.push({ i, j, offset, buffer });
  }
  return measured;
}

const results = { states: [], videos: [], errors: [] };

let preview;
let browser;
try {
  await rm(OUT_ROOT, { recursive: true, force: true }).catch(() => {});
  await mkdir(STATES_DIR, { recursive: true });
  await mkdir(VIDEO_DIR, { recursive: true });
  preview = await startPreview(options.port);
  const origin = `http://127.0.0.1:${options.port}`;
  browser = await chromium.launch({
    channel: "chrome",
    headless: options.headless,
    args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
  });

  // ---------------------------------------------------------------- probe V4
  const probe = await readyPage(browser, `${origin}/?optics=v4&qa=1`, { width: 1440, height: 900 });
  const probes = await probeCardCells(probe.page);
  const { analyzeBuffers } = await import("./lib/round1-frame-stats.mjs");
  const stats = await analyzeBuffers(probes.map((entry) => entry.buffer));
  const scored = probes.map((entry, index) => ({ ...entry, ...stats[index], buffer: undefined }));
  const byLuma = [...scored].sort((a, b) => b.centerLuma - a.centerLuma);
  const byTexture = [...scored].sort((a, b) => b.centerTexture - a.centerTexture);
  const cardStates = {
    "bright-card": byLuma[0],
    "dark-card": byLuma.at(-1),
    "high-texture-card": byTexture[0],
    "low-texture-card": byTexture.at(-1),
  };
  await probe.context.close();

  const restOffset = { x: 0, y: 0 };
  const leftTilt = centerOn(-3, 0);
  const rightTilt = centerOn(3, 0);
  const partial = { x: CELL_W * 0.5, y: CELL_H * 0.5 };

  /** The fixed review states, identical for V3 and V4. */
  const STATES = [
    { id: "01-rest-5s", async run(page) { await page.evaluate(() => window.__ILG_QA__.reset()); await page.waitForTimeout(5000); await settle(page); } },
    { id: "02-pointer-left", async run(page) { await page.evaluate((o) => { window.__ILG_QA__.setOffset(o.x, o.y); window.__ILG_QA__.setPointer(-0.9, 0); }, restOffset); await settle(page); } },
    { id: "03-pointer-center", async run(page) { await page.evaluate(() => window.__ILG_QA__.setPointer(0, 0)); await settle(page); } },
    { id: "04-pointer-right", async run(page) { await page.evaluate(() => window.__ILG_QA__.setPointer(0.9, 0)); await settle(page); } },
    // Drag and flick stills are reproduced by setting the same mid-interaction
    // offset and velocity on both versions. Replaying raw mouse input would
    // land V3 and V4 on different offsets and the split sheet would compare
    // two different scroll positions. Real input is exercised in the session
    // videos instead.
    {
      id: "05-slow-drag",
      async run(page) {
        await page.evaluate(() => {
          window.__ILG_QA__.reset();
          window.__ILG_QA__.setOffset(214.5, 82.4);
          window.__ILG_QA__.setVelocity(180, 70);
          window.__ILG_QA__.setPointer(-0.35, 0.12);
        });
        await settle(page);
      },
    },
    {
      id: "06-fast-flick",
      async run(page) {
        await page.evaluate(() => {
          window.__ILG_QA__.reset();
          window.__ILG_QA__.setOffset(1486.3, 402.8);
          window.__ILG_QA__.setVelocity(1420, 430);
          window.__ILG_QA__.setPointer(0.55, -0.2);
        });
        await settle(page);
      },
    },
    { id: "07-bright-card", offset: () => cardStates["bright-card"].offset },
    { id: "08-dark-card", offset: () => cardStates["dark-card"].offset },
    { id: "09-high-texture-card", offset: () => cardStates["high-texture-card"].offset },
    { id: "10-low-texture-card", offset: () => cardStates["low-texture-card"].offset },
    { id: "11-left-tilt", offset: () => leftTilt, pointer: [-0.85, 0] },
    { id: "12-right-tilt", offset: () => rightTilt, pointer: [0.85, 0] },
    { id: "13-partial-viewport-card", offset: () => partial },
  ];

  for (const optics of ["v3", "v4"]) {
    const url = optics === "v4" ? `${origin}/?optics=v4&qa=1` : `${origin}/?optics=v3&qa=1`;
    const session = await readyPage(browser, url, { width: 1440, height: 900 });
    await mkdir(path.join(STATES_DIR, optics), { recursive: true });
    for (const state of STATES) {
      if (state.offset) {
        const offset = state.offset();
        const pointer = state.pointer ?? [0, 0];
        await session.page.evaluate(({ o, p }) => {
          window.__ILG_QA__.setOffset(o.x, o.y);
          window.__ILG_QA__.setPointer(p[0], p[1]);
        }, { o: offset, p: pointer });
        await settle(session.page);
      } else {
        await state.run(session.page);
      }
      const file = path.join(STATES_DIR, optics, `${state.id}.png`);
      await session.page.screenshot({ path: file });
      await state.after?.(session.page);
      if (optics === "v4") {
        const centreQuad = await session.page.evaluate(() => {
          const quads = window.__ILG_V4_GRID_QA__?.getCardQuads?.() ?? [];
          let best = null;
          let bestDistance = Infinity;
          for (const entry of quads) {
            const xs = entry.quad.map((point) => point[0]);
            const ys = entry.quad.map((point) => point[1]);
            if (xs.some((value) => value < -1 || value > 2)) continue;
            const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
            const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
            const distance = Math.hypot(cx - 0.5, cy - 0.5);
            if (distance < bestDistance) {
              bestDistance = distance;
              best = entry.quad;
            }
          }
          return best;
        });
        results.states.push({ id: state.id, file: path.relative(REPO_ROOT, file), centreQuad });
      }
      console.log(`captured ${optics}/${state.id}`);
    }
    results.errors.push(...session.errors.map((message) => `${optics}: ${message}`));
    await session.context.close();
  }

  // ---------------------------------------------------------- mobile states
  for (const [id, viewport] of [
    ["14-mobile-portrait", { width: 390, height: 844 }],
    ["15-mobile-landscape", { width: 844, height: 390 }],
  ]) {
    for (const optics of ["v3", "v4"]) {
      const url = optics === "v4" ? `${origin}/?optics=v4&qa=1` : `${origin}/?optics=v3&qa=1`;
      const mobile = await readyPage(browser, url, viewport, true);
      await mobile.page.evaluate(() => window.__ILG_QA__.reset());
      await mobile.page.waitForTimeout(2500);
      await settle(mobile.page);
      const file = path.join(STATES_DIR, optics, `${id}.png`);
      await mobile.page.screenshot({ path: file });
      if (optics === "v4") results.states.push({ id, file: path.relative(REPO_ROOT, file) });
      results.errors.push(...mobile.errors.map((message) => `${optics}/${id}: ${message}`));
      await mobile.context.close();
      console.log(`captured ${optics}/${id}`);
    }
  }

  // --------------------------------------------------------- session videos
  const recordSession = async (name, viewport, isMobile, script) => {
    const context = await browser.newContext({
      viewport,
      deviceScaleFactor: 1,
      isMobile,
      hasTouch: isMobile,
      recordVideo: { dir: VIDEO_DIR, size: viewport },
    });
    const page = await context.newPage();
    await page.goto(`${origin}/?optics=v4&qa=1`, { waitUntil: "load" });
    await page.waitForFunction(
      () => window.__ILG_QA__?.getState()?.ready === true,
      undefined,
      { timeout: 90_000 },
    );
    await page.waitForTimeout(1500);
    await script(page);
    const video = page.video();
    await context.close();
    const source = await video?.path();
    const target = path.join(VIDEO_DIR, `${name}.webm`);
    if (source) await rename(source, target);
    results.videos.push(path.relative(REPO_ROOT, target));
    console.log(`recorded ${name}`);
  };

  await recordSession("desktop-session", { width: 1440, height: 900 }, false, async (page) => {
    await page.waitForTimeout(5000);                       // rest
    for (const x of [-0.9, 0, 0.9, 0]) {                   // pointer sweep
      await page.evaluate((value) => window.__ILG_QA__.setPointer(value, 0), x);
      await page.waitForTimeout(1400);
    }
    await page.mouse.move(1000, 520);                      // slow drag
    await page.mouse.down();
    for (let step = 0; step < 24; step += 1) {
      await page.mouse.move(1000 - step * 18, 520 - step * 7);
      await page.waitForTimeout(45);
    }
    await page.mouse.up();
    await page.waitForTimeout(1800);
    await page.mouse.move(1150, 600);                      // fast flick
    await page.mouse.down();
    for (let step = 0; step < 8; step += 1) {
      await page.mouse.move(1150 - step * 105, 600 - step * 30);
      await page.waitForTimeout(8);
    }
    await page.mouse.up();
    await page.waitForTimeout(4200);                       // inertia and stop
  });

  await recordSession("mobile-session", { width: 390, height: 844 }, true, async (page) => {
    await page.waitForTimeout(4000);
    await page.touchscreen.tap(195, 420);
    for (let round = 0; round < 2; round += 1) {
      await page.mouse.move(300, 620);
      await page.mouse.down();
      for (let step = 0; step < 14; step += 1) {
        await page.mouse.move(300 - step * 14, 620 - step * 22);
        await page.waitForTimeout(28);
      }
      await page.mouse.up();
      await page.waitForTimeout(2200);
    }
    await page.setViewportSize({ width: 844, height: 390 });
    await page.waitForTimeout(3500);
  });

  const manifest = {
    schemaVersion: 1,
    private: true,
    round: 1,
    generator: "round1-preview-capture-v1",
    note: "Preview evidence for a human product decision. Formal pixel truth remains BLOCKED.",
    cardStateSelection: Object.fromEntries(
      Object.entries(cardStates).map(([key, value]) => [key, {
        cell: [value.i, value.j],
        centerLuma: Number(value.centerLuma.toFixed(4)),
        centerTexture: Number(value.centerTexture.toFixed(4)),
      }]),
    ),
    states: results.states,
    videos: results.videos,
    errors: results.errors,
  };
  await writeFile(
    path.join(OUT_ROOT, "capture-manifest.local.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );
  console.log(`\nStates: ${results.states.length} · videos: ${results.videos.length} · errors: ${results.errors.length}`);
  console.log(`Output: ${path.relative(REPO_ROOT, OUT_ROOT)}`);
} finally {
  await browser?.close();
  preview?.kill("SIGTERM");
}
