import path from "node:path";
import {
  TARGET_URL,
  ROOT,
  VIEWPORTS,
  ensureDir,
  writeJson,
  launchChrome,
  newContext,
  attachCollectors,
  collectEnvironment,
  collectDom,
  waitForScene,
  screenshotState,
} from "./lib/capture-utils.mjs";

const OUT = path.join(ROOT, "artifacts", "reference");
const TRACE = path.join(ROOT, "artifacts", "traces");
const VIDEO = path.join(ROOT, "artifacts", "video");
ensureDir(OUT);
ensureDir(TRACE);
ensureDir(VIDEO);

async function captureViewport(browser, key, options = {}) {
  const viewport = VIEWPORTS[key];
  const dir = ensureDir(path.join(OUT, viewport.name));
  const states = [];
  const context = await newContext(browser, viewport, {
    recordVideo: options.recordVideo
      ? { dir: path.join(VIDEO, "tmp"), size: { width: viewport.width, height: viewport.height } }
      : undefined,
  });
  const page = await context.newPage();
  const collectors = attachCollectors(page);

  if (options.trace) {
    await context.tracing.start({ screenshots: true, snapshots: false, sources: false });
  }

  const navStart = Date.now();
  await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
  states.push(await screenshotState(page, dir, "01-just-opened", { input: "navigate" }));

  let saw25 = false;
  let saw50 = false;
  const loadPollUntil = Date.now() + 20000;
  while (Date.now() < loadPollUntil) {
    const percent = await page.evaluate(() => {
      const match = (document.body?.innerText || "").match(/(\d+)\s*%/);
      return match ? Number(match[1]) : null;
    });
    if (!saw25 && percent !== null && percent >= 25) {
      states.push(await screenshotState(page, dir, "02-loading-25", { percent, input: "none" }));
      saw25 = true;
    }
    if (!saw50 && percent !== null && percent >= 50) {
      states.push(await screenshotState(page, dir, "03-loading-50", { percent, input: "none" }));
      saw50 = true;
    }
    if (percent === null || percent >= 100) break;
    await page.waitForTimeout(80);
  }

  const ready = await waitForScene(page);
  states.push(await screenshotState(page, dir, "04-first-loaded-frame", { ready, input: "none" }));

  await page.waitForTimeout(2000);
  states.push(await screenshotState(page, dir, "05-rest-2s", { input: "idle-2s" }));
  await page.waitForTimeout(3000);
  states.push(await screenshotState(page, dir, "06-rest-5s", { input: "idle-5s" }));

  const env = await collectEnvironment(page);
  const dom = await collectDom(page);
  writeJson(path.join(dir, "environment.json"), {
    capturedAt: new Date().toISOString(),
    os: "macOS 27.0 (26A5378n)",
    gpuHost: "Apple M5 Max 40-core Metal",
    browser: "Google Chrome 151.0.7922.138",
    loadMs: Date.now() - navStart,
    env,
    ready,
  });
  writeJson(path.join(dir, "dom.json"), dom);
  writeJson(path.join(dir, "console.json"), {
    console: collectors.consoleMessages,
    pageErrors: collectors.pageErrors,
    network: {
      count: collectors.network.length,
      byType: collectors.network.reduce((acc, item) => {
        acc[item.resourceType] = (acc[item.resourceType] || 0) + 1;
        return acc;
      }, {}),
      resources: collectors.network,
    },
  });

  if (options.staticOnly) {
    if (options.trace) {
      await context.tracing.stop({ path: path.join(TRACE, `reference-${viewport.name}-static.zip`) });
    }
    await context.close();
    return { viewport: viewport.name, states };
  }

  await page.mouse.move(viewport.width / 2, viewport.height / 2);
  states.push(await screenshotState(page, dir, "07-mouse-center", {
    input: `mousemove ${viewport.width / 2},${viewport.height / 2}`,
  }));

  await page.mouse.move(viewport.width / 2, viewport.height / 2);
  await page.mouse.down();
  await page.mouse.move(viewport.width / 2 - 400, viewport.height / 2, { steps: 40 });
  states.push(await screenshotState(page, dir, "08-slow-drag-left-400", {
    input: "mousedown + move -400px x over ~40 steps",
  }));
  await page.mouse.up();
  await page.waitForTimeout(1800);

  await page.mouse.move(viewport.width / 2, viewport.height / 2);
  await page.mouse.down();
  await page.mouse.move(viewport.width / 2 - 180, viewport.height / 2 - 140, { steps: 30 });
  states.push(await screenshotState(page, dir, "09-slow-diagonal-drag", {
    input: "mousedown + move -180x -140y",
  }));
  await page.mouse.up();
  await page.waitForTimeout(1800);

  await page.mouse.move(viewport.width / 2, viewport.height / 2);
  await page.mouse.down();
  await page.mouse.move(viewport.width / 2 - 520, viewport.height / 2, { steps: 4 });
  states.push(await screenshotState(page, dir, "10-flick-0ms", { input: "fast flick -520x" }));
  await page.mouse.up();
  await page.waitForTimeout(250);
  states.push(await screenshotState(page, dir, "11-flick-250ms", { input: "after flick 250ms" }));
  await page.waitForTimeout(250);
  states.push(await screenshotState(page, dir, "12-flick-500ms", { input: "after flick 500ms" }));
  await page.waitForTimeout(500);
  states.push(await screenshotState(page, dir, "13-flick-1000ms", { input: "after flick 1000ms" }));
  await page.waitForTimeout(2500);
  states.push(await screenshotState(page, dir, "14-flick-stopped", { input: "after flick settled" }));

  await page.mouse.move(viewport.width / 2, viewport.height / 2);
  await page.mouse.wheel(0, 900);
  await page.waitForTimeout(80);
  states.push(await screenshotState(page, dir, "15-wheel-vertical", { input: "wheel 0,900" }));
  await page.waitForTimeout(1200);
  await page.mouse.wheel(900, 0);
  await page.waitForTimeout(80);
  states.push(await screenshotState(page, dir, "16-wheel-horizontal", { input: "wheel 900,0" }));
  await page.waitForTimeout(1200);

  if (options.stress) {
    const originX = viewport.width / 2;
    const originY = viewport.height / 2;
    const end = Date.now() + 30000;
    while (Date.now() < end) {
      await page.mouse.move(originX, originY);
      await page.mouse.down();
      await page.mouse.move(originX - 280, originY + 90, { steps: 6 });
      await page.mouse.up();
      await page.mouse.move(originX + 220, originY - 70, { steps: 5 });
    }
    states.push(await screenshotState(page, dir, "17-stress-30s", { input: "continuous fast drag 30s" }));
  }

  if (options.resize) {
    await page.setViewportSize({ width: 1100, height: 720 });
    await page.waitForTimeout(400);
    states.push(await screenshotState(page, dir, "18-resize-1100x720", { input: "viewport resize" }));
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.waitForTimeout(400);
  }

  if (options.blur) {
    await page.evaluate(() => window.dispatchEvent(new Event("blur")));
    await page.waitForTimeout(800);
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await page.waitForTimeout(400);
    states.push(await screenshotState(page, dir, "19-blur-focus", { input: "window blur then focus" }));
  }

  writeJson(path.join(dir, "states.json"), states);

  if (options.trace) {
    await context.tracing.stop({ path: path.join(TRACE, `reference-${viewport.name}.zip`) });
  }

  const video = page.video();
  await context.close();
  if (video && options.videoName) {
    await video.saveAs(path.join(VIDEO, options.videoName));
  }
  return { viewport: viewport.name, states: states.map((s) => s.name) };
}

const VIDEO_ONLY = process.argv.includes("--video-only");

async function recordNamedVideo(browser, name, viewportKey, action) {
  const viewport = VIEWPORTS[viewportKey];
  const context = await newContext(browser, viewport, {
    recordVideo: { dir: path.join(VIDEO, "tmp"), size: { width: viewport.width, height: viewport.height } },
  });
  const page = await context.newPage();
  let video = null;
  try {
    await page.goto(TARGET_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
    await waitForScene(page);
    await page.waitForTimeout(800);
    await action(page, viewport);
    video = page.video();
  } finally {
    await context.close();
  }
  if (video) await video.saveAs(path.join(VIDEO, name));
}

async function tryRecordNamedVideo(browser, name, viewportKey, action) {
  try {
    await recordNamedVideo(browser, name, viewportKey, action);
    console.log(`video saved ${name}`);
    return { name, ok: true };
  } catch (error) {
    console.error(`video stage failed for ${name}:`, error);
    return { name, ok: false, error: String(error?.message || error) };
  }
}

const browser = await launchChrome({ headless: false });

try {
  const summary = {
    startedAt: new Date().toISOString(),
    target: TARGET_URL,
    localPreviewPort: 5280,
    localPreviewUrl: "http://127.0.0.1:5280",
    viewports: {},
    videoOnly: VIDEO_ONLY,
  };

  if (!VIDEO_ONLY) {
    summary.viewports.A = await captureViewport(browser, "A", {
      trace: true,
      stress: true,
      resize: true,
      blur: true,
    });
    summary.viewports.B = await captureViewport(browser, "B", { staticOnly: true });
    summary.viewports.C = await captureViewport(browser, "C", { staticOnly: true });
    summary.viewports.D = await captureViewport(browser, "D", { staticOnly: false });
    summary.viewports.E = await captureViewport(browser, "E", { staticOnly: true });
  }

  summary.videos = [];

  summary.videos.push(await tryRecordNamedVideo(browser, "reference-desktop-slow.mp4", "A", async (page, viewport) => {
    await page.waitForTimeout(1500);
    await page.mouse.move(viewport.width / 2, viewport.height / 2);
    await page.mouse.down();
    await page.mouse.move(viewport.width / 2 - 720, viewport.height / 2, { steps: 72 });
    await page.mouse.up();
    await page.waitForTimeout(2200);
    await page.mouse.move(viewport.width / 2, viewport.height / 2);
    await page.mouse.down();
    await page.mouse.move(viewport.width / 2 - 200, viewport.height / 2 - 180, { steps: 40 });
    await page.mouse.up();
    await page.waitForTimeout(2200);
  }));

  summary.videos.push(await tryRecordNamedVideo(browser, "reference-desktop-fast.mp4", "A", async (page, viewport) => {
    await page.waitForTimeout(600);
    for (let i = 0; i < 5; i += 1) {
      await page.mouse.move(viewport.width / 2, viewport.height / 2);
      await page.mouse.down();
      await page.mouse.move(
        viewport.width / 2 - 540,
        viewport.height / 2 + (i % 2 === 0 ? 120 : -120),
        { steps: 3 },
      );
      await page.mouse.up();
      await page.waitForTimeout(i === 4 ? 2500 : 900);
    }
  }));

  summary.videos.push(await tryRecordNamedVideo(browser, "reference-mobile.mp4", "D", async (page, viewport) => {
    await page.waitForTimeout(800);
    await page.touchscreen.tap(viewport.width / 2, viewport.height / 2);
    await page.mouse.move(viewport.width / 2, viewport.height / 2);
    await page.mouse.down();
    await page.mouse.move(viewport.width / 2 - 180, viewport.height / 2 + 40, { steps: 24 });
    await page.mouse.up();
    await page.waitForTimeout(1200);
    await page.mouse.move(viewport.width / 2, viewport.height / 2);
    await page.mouse.down();
    await page.mouse.move(viewport.width / 2 - 90, viewport.height / 2 - 140, { steps: 22 });
    await page.mouse.up();
    await page.waitForTimeout(1000);
    await page.mouse.move(viewport.width / 2, viewport.height / 2);
    await page.mouse.down();
    await page.mouse.move(viewport.width / 2 + 220, viewport.height / 2 - 90, { steps: 3 });
    await page.mouse.up();
    await page.waitForTimeout(2000);
  }));

  summary.finishedAt = new Date().toISOString();
  if (!VIDEO_ONLY) {
    writeJson(path.join(OUT, "capture-summary.json"), summary);
  }
  console.log(JSON.stringify(summary, null, 2));
} finally {
  await browser.close();
}
