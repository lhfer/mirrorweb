#!/usr/bin/env node

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const SCRIPT_VERSION = "optics-lab-capture-v1";
const DEFAULT_URL = "http://127.0.0.1:5280/glass-lab-v4/?qa=1";
const DEFAULT_OUTPUT_DIR = path.join(REPO_ROOT, "qa-v4/results/optics-lab-foundation.private");
const DEFAULT_MANIFEST = path.join(REPO_ROOT, "qa-v4/results/optics-lab-foundation.capture.local.json");
const SOFTWARE_GPU_PATTERN = /swiftshader|llvmpipe|software|microsoft basic render/i;
const RUNTIME_SOURCE_FILES = [
  "glass-lab-v4.html",
  "vite.config.ts",
  "src/config.ts",
  "src/lab-v4/lab.css",
  "src/lab-v4/main.ts",
  "src/lab-v4/patterns.ts",
  "src/lab-v4/types.ts",
  "src/materials/LiquidGlassMaterial.ts",
  "src/materials/LiquidGlassMaterialV4.ts",
  "src/rendering/SceneColorTargetV4.ts",
  "src/scene/ConvexGlassGeometry.ts",
  "src/scene/ConvexGlassGeometryV4.ts",
  "src/v4/OpticsConfigV4.ts",
  "src/v4/StripLightEnvironmentV4.ts",
];

function parseArguments(argv) {
  const options = {
    url: process.env.ILG_V4_LAB_URL || DEFAULT_URL,
    outputDirectory: DEFAULT_OUTPUT_DIR,
    manifest: DEFAULT_MANIFEST,
    headed: process.env.ILG_LAB_HEADLESS !== "1",
  };
  for (const argument of argv) {
    if (argument.startsWith("--url=")) options.url = argument.slice("--url=".length);
    else if (argument.startsWith("--output=")) options.outputDirectory = path.resolve(REPO_ROOT, argument.slice("--output=".length));
    else if (argument.startsWith("--manifest=")) options.manifest = path.resolve(REPO_ROOT, argument.slice("--manifest=".length));
    else if (argument === "--headed") options.headed = true;
    else if (argument === "--headless") options.headed = false;
    else throw new Error(`Unknown argument: ${argument}`);
  }
  const url = new URL(options.url);
  if (!/^https?:$/.test(url.protocol)) throw new Error("Lab URL must use http or https");
  return options;
}

function repositoryPath(file) {
  const relative = path.relative(REPO_ROOT, file).split(path.sep).join("/");
  if (relative.startsWith("../") || path.isAbsolute(relative)) {
    throw new Error(`Output must remain inside the repository: ${file}`);
  }
  return relative;
}

function sha256Bytes(value) {
  return createHash("sha256").update(value).digest("hex");
}

async function sha256File(file) {
  return sha256Bytes(await readFile(file));
}

async function writeJson(file, value) {
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function gitText(args) {
  return execFileSync("git", args, { cwd: REPO_ROOT, encoding: "utf8" }).trim();
}

async function captureSourceIdentity() {
  const files = [];
  for (const relativePath of RUNTIME_SOURCE_FILES) {
    const file = path.join(REPO_ROOT, relativePath);
    await access(file);
    files.push({ path: relativePath, sha256: await sha256File(file) });
  }
  const status = gitText(["status", "--porcelain=v1", "--untracked-files=all", "--", ...RUNTIME_SOURCE_FILES]);
  return {
    head: gitText(["rev-parse", "HEAD"]),
    branch: gitText(["rev-parse", "--abbrev-ref", "HEAD"]),
    dirtyWithinRuntimeScope: status.length > 0,
    runtimeSourceSetSha256: sha256Bytes(files.map((entry) => `${entry.path}:${entry.sha256}`).join("\n")),
    files,
  };
}

function percentile(sorted, quantile) {
  if (!sorted.length) return null;
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * quantile) - 1))];
}

function summarizeRaf(timestamps) {
  const intervals = [];
  for (let index = 1; index < timestamps.length; index += 1) {
    const value = timestamps[index] - timestamps[index - 1];
    if (Number.isFinite(value) && value > 0 && value < 1000) intervals.push(value);
  }
  const sorted = intervals.toSorted((left, right) => left - right);
  return {
    metricName: "rafIntervalMs",
    metricMeaning: "browser requestAnimationFrame interval; not CPU frame cost or GPU execution time",
    gpuExecutionTimeMeasured: false,
    sampleCount: sorted.length,
    p50: percentile(sorted, 0.5),
    p95: percentile(sorted, 0.95),
    p99: percentile(sorted, 0.99),
    max: sorted.length ? sorted.at(-1) : null,
  };
}

async function installHooks(context) {
  await context.addInitScript(() => {
    const capture = { raf: [], contexts: [] };
    Object.defineProperty(window, "__ILG_OPTICS_CAPTURE__", {
      configurable: false,
      enumerable: false,
      writable: false,
      value: capture,
    });
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function captureContext(type, ...args) {
      capture.contexts.push(String(type));
      return Reflect.apply(original, this, [type, ...args]);
    };
    const tick = (now) => {
      if (capture.raf.length < 50000) capture.raf.push(now);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

async function waitForLab(page) {
  await page.waitForFunction(() => {
    const host = window;
    const qa = host.__ILG_V4_LAB_QA__ || host.__ILG_QA__ || host.__LIQUID_GLASS_QA__;
    if (!qa || typeof qa.getState !== "function") return false;
    try {
      return qa.getState()?.ready === true;
    } catch {
      return false;
    }
  }, null, { timeout: 30000 });
}

async function callLab(page, method, value) {
  const result = await page.evaluate(async ({ methodName, methodValue }) => {
    const host = window;
    const qa = host.__ILG_V4_LAB_QA__ || host.__ILG_QA__ || host.__LIQUID_GLASS_QA__;
    if (!qa) return { called: false, reason: "qa-hook-missing" };
    const aliases = {
      setPattern: ["setPattern", "setBackground"],
      setMode: ["setMode", "setView"],
      setDebug: ["setDebug", "setDebugView"],
      setPointer: ["setPointer"],
    };
    const name = (aliases[methodName] || [methodName]).find((candidate) => typeof qa[candidate] === "function");
    if (!name) return { called: false, reason: `method-missing:${methodName}` };
    await qa[name](...(Array.isArray(methodValue) ? methodValue : [methodValue]));
    return { called: true, method: name };
  }, { methodName: method, methodValue: value });
  if (!result.called) throw new Error(`Lab QA call failed: ${result.reason}`);
}

async function getLabState(page) {
  return page.evaluate(() => {
    const host = window;
    const qa = host.__ILG_V4_LAB_QA__ || host.__ILG_QA__ || host.__LIQUID_GLASS_QA__;
    return qa?.getState?.() ?? null;
  });
}

async function getLargestCanvas(page) {
  const canvases = page.locator("canvas");
  const count = await canvases.count();
  let selected = null;
  for (let index = 0; index < count; index += 1) {
    const locator = canvases.nth(index);
    const box = await locator.boundingBox();
    if (!box || box.width < 2 || box.height < 2) continue;
    const area = box.width * box.height;
    if (!selected || area > selected.area) selected = { index, box, area };
  }
  if (!selected) throw new Error("No visible lab canvas found");
  return { locator: canvases.nth(selected.index), index: selected.index, box: selected.box };
}

async function captureCanvas({ page, canvas, outputDirectory, id, specification }) {
  await callLab(page, "setPattern", specification.pattern);
  await callLab(page, "setMode", specification.mode);
  await callLab(page, "setDebug", specification.debug);
  if (specification.pointer) await callLab(page, "setPointer", specification.pointer);
  await page.waitForTimeout(specification.settleMs ?? 450);
  const state = await getLabState(page);
  const file = path.join(outputDirectory, `${id}.png`);
  await canvas.locator.screenshot({ path: file, animations: "disabled" });
  const dimensions = await canvas.locator.evaluate((element) => ({
    cssWidth: element.getBoundingClientRect().width,
    cssHeight: element.getBoundingClientRect().height,
    bufferWidth: element.width,
    bufferHeight: element.height,
  }));
  return {
    id,
    role: specification.role,
    pattern: specification.pattern,
    mode: specification.mode,
    debug: specification.debug,
    pointer: specification.pointer ?? null,
    file: repositoryPath(file),
    sha256: await sha256File(file),
    dimensions,
    state,
  };
}

function graphicsSummary(systemInfo, adapterInfo) {
  const devices = systemInfo?.gpu?.devices ?? [];
  const primary = devices[0] ?? {};
  const text = [
    adapterInfo?.vendor,
    adapterInfo?.architecture,
    adapterInfo?.device,
    adapterInfo?.description,
    primary.vendorString,
    primary.deviceString,
    primary.driverVendor,
    primary.driverVersion,
  ].filter(Boolean).join(" ");
  return {
    webgpuAvailable: Boolean(adapterInfo),
    adapter: adapterInfo ?? null,
    device: devices.length ? {
      vendorString: primary.vendorString ?? null,
      deviceString: primary.deviceString ?? null,
      driverVendor: primary.driverVendor ?? null,
      driverVersion: primary.driverVersion ?? null,
    } : null,
    softwareRendererDetected: adapterInfo?.isFallbackAdapter === true || SOFTWARE_GPU_PATTERN.test(text),
  };
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  repositoryPath(options.outputDirectory);
  repositoryPath(options.manifest);
  await mkdir(options.outputDirectory, { recursive: true });
  const sourceIdentity = await captureSourceIdentity();

  const browser = await chromium.launch({
    channel: process.env.ILG_BROWSER_CHANNEL || "chrome",
    headless: !options.headed,
    args: [
      "--enable-unsafe-webgpu",
      "--disable-background-timer-throttling",
      "--disable-backgrounding-occluded-windows",
      "--disable-renderer-backgrounding",
    ],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    colorScheme: "dark",
    reducedMotion: "no-preference",
    recordVideo: {
      dir: options.outputDirectory,
      size: { width: 1440, height: 900 },
    },
  });
  await installHooks(context);
  const page = await context.newPage();
  const pageVideo = page.video();
  const sessionVideoFile = path.join(options.outputDirectory, "lab-session.webm");
  const pageErrors = [];
  const servedResourceTasks = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("response", (response) => {
    const responseUrl = new URL(response.url());
    if (responseUrl.origin !== new URL(options.url).origin || response.status() !== 200) return;
    servedResourceTasks.push((async () => {
      const body = await response.body();
      return {
        path: responseUrl.pathname,
        bytes: body.byteLength,
        sha256: sha256Bytes(body),
      };
    })().catch(() => null));
  });

  let manifest;
  try {
    await page.goto(options.url, { waitUntil: "domcontentloaded", timeout: 30000 });
    await waitForLab(page);
    await page.waitForTimeout(1200);
    const canvas = await getLargestCanvas(page);
    const initialState = await getLabState(page);

    const captureSpecifications = [
      { id: "split-checker", role: "v3-v4-split", pattern: "checker", mode: "split", debug: "beauty" },
      { id: "v3-checker", role: "v3-control-crop", pattern: "checker", mode: "v3", debug: "beauty" },
      { id: "difference-checker", role: "v3-v4-difference", pattern: "checker", mode: "difference", debug: "beauty" },
      { id: "edge-mask-black", role: "zone-mask", pattern: "black", mode: "v4", debug: "edge-mask" },
      { id: "normals-checker", role: "surface-normal-debug", pattern: "checker", mode: "v4", debug: "normals" },
      { id: "thickness-checker", role: "optical-thickness-debug", pattern: "checker", mode: "v4", debug: "thickness" },
      { id: "refraction-offset-checker", role: "projected-refraction-debug", pattern: "checker", mode: "v4", debug: "refraction-offset" },
      { id: "fresnel-black", role: "fresnel-debug", pattern: "black", mode: "v4", debug: "fresnel" },
      { id: "adaptivity-flat", role: "content-adaptivity-debug", pattern: "low-frequency-flat-color", mode: "v4", debug: "adaptivity" },
      { id: "v4-checker", role: "sharpness-and-rim", pattern: "checker", mode: "v4", debug: "beauty" },
      { id: "v4-horizontal-lines", role: "horizontal-line-displacement", pattern: "horizontal-lines", mode: "v4", debug: "beauty" },
      { id: "v4-vertical-lines", role: "vertical-line-displacement", pattern: "vertical-lines", mode: "v4", debug: "beauty" },
      { id: "v4-high-frequency-photo", role: "high-frequency-adaptivity", pattern: "high-frequency-photo", mode: "v4", debug: "beauty" },
      { id: "v4-low-frequency-flat", role: "low-frequency-adaptivity", pattern: "low-frequency-flat-color", mode: "v4", debug: "beauty" },
      { id: "v4-white", role: "light-background-discernibility", pattern: "white", mode: "v4", debug: "beauty" },
      { id: "v4-black", role: "dark-background-discernibility", pattern: "black", mode: "v4", debug: "beauty" },
      { id: "dispersion-checker", role: "dispersion-localization", pattern: "checker", mode: "v4", debug: "dispersion" },
    ];
    const captures = [];
    for (const specification of captureSpecifications) {
      captures.push(await captureCanvas({
        page,
        canvas,
        outputDirectory: options.outputDirectory,
        id: specification.id,
        specification,
      }));
    }

    const pointerPositions = [
      [-0.85, 0],
      [-0.6, -0.5],
      [-0.3, 0.35],
      [0, 0],
      [0.3, -0.35],
      [0.6, 0.5],
      [0.85, 0],
    ];
    const pointerPath = [];
    for (let index = 0; index < pointerPositions.length; index += 1) {
      const pointer = pointerPositions[index];
      pointerPath.push(await captureCanvas({
        page,
        canvas,
        outputDirectory: options.outputDirectory,
        id: `reflection-pointer-${String(index).padStart(2, "0")}`,
        specification: {
          role: "pointer-highlight-path",
          pattern: "black",
          mode: "v4",
          debug: "reflection",
          pointer,
          settleMs: 350,
        },
      }));
    }

    await callLab(page, "setPattern", "checker");
    await callLab(page, "setMode", "split");
    await callLab(page, "setDebug", "beauty");
    await callLab(page, "setPointer", [0, 0]);
    await page.waitForTimeout(450);
    const uiPreviewFile = path.join(options.outputDirectory, "lab-ui-split.png");
    await page.screenshot({ path: uiPreviewFile, fullPage: true, animations: "disabled" });
    const uiPreview = {
      role: "reviewable-v3-v4-split-with-controls",
      file: repositoryPath(uiPreviewFile),
      sha256: await sha256File(uiPreviewFile),
    };

    const browserSession = await browser.newBrowserCDPSession();
    const [version, systemInfo] = await Promise.all([
      browserSession.send("Browser.getVersion").catch(() => null),
      browserSession.send("SystemInfo.getInfo").catch(() => null),
    ]);
    await browserSession.detach().catch(() => {});
    const adapterInfo = await page.evaluate(async () => {
      if (!navigator.gpu) return null;
      const adapter = await navigator.gpu.requestAdapter();
      if (!adapter) return null;
      const info = adapter.info;
      return {
        vendor: info.vendor || null,
        architecture: info.architecture || null,
        device: info.device || null,
        description: info.description || null,
        isFallbackAdapter: adapter.isFallbackAdapter ?? info.isFallbackAdapter ?? null,
      };
    });
    const graphics = graphicsSummary(systemInfo, adapterInfo);
    const servedResources = (await Promise.all(servedResourceTasks))
      .filter(Boolean)
      .sort((left, right) => left.path.localeCompare(right.path) || left.sha256.localeCompare(right.sha256));
    const hookEvidence = await page.evaluate(() => ({
      raf: window.__ILG_OPTICS_CAPTURE__?.raf ?? [],
      contexts: [...new Set(window.__ILG_OPTICS_CAPTURE__?.contexts ?? [])],
      viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
    }));
    const contractPassed = initialState?.normalPathDirectMedia === false
      && initialState?.sceneTarget?.type === "half-float"
      && initialState?.sceneTarget?.colorSpace === "linear"
      && initialState?.v3Preserved === true;

    manifest = {
      schemaVersion: 1,
      generator: SCRIPT_VERSION,
      generatedAt: new Date().toISOString(),
      status: contractPassed && graphics.webgpuAvailable && !graphics.softwareRendererDetected && pageErrors.length === 0
        ? "CAPTURED"
        : "BLOCKED",
      route: new URL(options.url).pathname,
      environment: {
        browser: {
          product: version?.product ?? `Chromium/${browser.version()}`,
          userAgent: version?.userAgent ?? null,
          playwrightBrowserVersion: browser.version(),
          headed: options.headed,
        },
        viewport: hookEvidence.viewport,
        canvas: {
          index: canvas.index,
          cssBounds: canvas.box,
          ...captures[0]?.dimensions,
        },
        graphics,
        observedCanvasContextTypes: hookEvidence.contexts,
      },
      runtimeContract: {
        passed: contractPassed,
        normalPathDirectMedia: initialState?.normalPathDirectMedia ?? null,
        sceneTarget: initialState?.sceneTarget ?? null,
        v3Preserved: initialState?.v3Preserved ?? null,
      },
      sourceIdentity,
      servedResourceIdentity: {
        resourceCount: servedResources.length,
        manifestSha256: sha256Bytes(servedResources.map((entry) => `${entry.path}:${entry.bytes}:${entry.sha256}`).join("\n")),
        resources: servedResources,
      },
      initialState,
      captures,
      pointerPath,
      uiPreview,
      performance: summarizeRaf(hookEvidence.raf),
      caveats: {
        naturalMediaTextureCoverage: false,
        naturalMediaTextureReason: "This structural round uses deterministic checker/line/flat-color patterns only.",
        gpuTimingMeasured: false,
        gpuTimingReason: "rAF intervals are scheduling observations and are not WebGPU timestamp-query measurements.",
        acceptanceScope: "Phase 1 optics-lab structural measurements; not final frozen-Golden visual acceptance.",
      },
      pageErrorCount: pageErrors.length,
      screenshotSetSha256: sha256Bytes(captures.concat(pointerPath).map(({ id, sha256 }) => `${id}:${sha256}`).join("\n")),
      captureScript: {
        path: repositoryPath(fileURLToPath(import.meta.url)),
        sha256: await sha256File(fileURLToPath(import.meta.url)),
        version: SCRIPT_VERSION,
      },
    };
  } catch (error) {
    manifest = {
      schemaVersion: 1,
      generator: SCRIPT_VERSION,
      generatedAt: new Date().toISOString(),
      status: "BLOCKED",
      route: new URL(options.url).pathname,
      error: error instanceof Error ? error.message : String(error),
      pageErrorCount: pageErrors.length,
      caveats: {
        naturalMediaTextureCoverage: false,
        gpuTimingMeasured: false,
        acceptanceScope: "No measurements may be inferred from a blocked capture.",
      },
    };
  } finally {
    await page.close().catch(() => {});
    await pageVideo?.saveAs(sessionVideoFile).catch(() => {});
    await context.close().catch(() => {});
    await browser.close().catch(() => {});
  }

  try {
    await access(sessionVideoFile);
    manifest.sessionVideo = {
      role: "private-optics-lab-session",
      file: repositoryPath(sessionVideoFile),
      sha256: await sha256File(sessionVideoFile),
    };
  } catch {
    manifest.sessionVideo = null;
  }

  await writeJson(options.manifest, manifest);
  console.log(JSON.stringify({
    status: manifest.status,
    manifest: repositoryPath(options.manifest),
    captureCount: manifest.captures?.length ?? 0,
    pointerSampleCount: manifest.pointerPath?.length ?? 0,
  }, null, 2));
  if (manifest.status !== "CAPTURED") process.exitCode = 2;
}

await access(REPO_ROOT);
await main();
