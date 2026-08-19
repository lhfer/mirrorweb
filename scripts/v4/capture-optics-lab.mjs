#!/usr/bin/env node

import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { access, mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const SCRIPT_VERSION = "optics-lab-capture-phase1b-v2";
const DEFAULT_URL = "http://127.0.0.1:5280/glass-lab-v4?qa=1";
const DEFAULT_OUTPUT_DIR = path.join(REPO_ROOT, "qa-v4/results/optics-lab-foundation.private");
const DEFAULT_MANIFEST = path.join(REPO_ROOT, "qa-v4/results/optics-lab-foundation.capture.local.json");
const DIST_DIR = path.join(REPO_ROOT, "dist");
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
  const repositoryStatus = gitText(["status", "--porcelain=v1", "--untracked-files=all"]);
  const runtimeStatus = gitText(["status", "--porcelain=v1", "--untracked-files=all", "--", ...RUNTIME_SOURCE_FILES]);
  return {
    head: gitText(["rev-parse", "HEAD"]),
    headTree: gitText(["rev-parse", "HEAD^{tree}"]),
    branch: gitText(["rev-parse", "--abbrev-ref", "HEAD"]),
    dirtyRepository: repositoryStatus.length > 0,
    dirtyWithinRuntimeScope: runtimeStatus.length > 0,
    runtimeSourceSetSha256: sha256Bytes(files.map((entry) => `${entry.path}:${entry.sha256}`).join("\n")),
    files,
  };
}

function sourceIdentityComparable(identity) {
  return {
    head: identity.head,
    headTree: identity.headTree,
    branch: identity.branch,
    dirtyRepository: identity.dirtyRepository,
    dirtyWithinRuntimeScope: identity.dirtyWithinRuntimeScope,
    runtimeSourceSetSha256: identity.runtimeSourceSetSha256,
    files: identity.files,
  };
}

function compareSourceIdentities(start, end) {
  const startDigest = sha256Bytes(JSON.stringify(sourceIdentityComparable(start)));
  const endDigest = sha256Bytes(JSON.stringify(sourceIdentityComparable(end)));
  return {
    passed: startDigest === endDigest
      && start.dirtyRepository === false
      && start.dirtyWithinRuntimeScope === false
      && end.dirtyRepository === false
      && end.dirtyWithinRuntimeScope === false,
    sameIdentity: startDigest === endDigest,
    cleanAtStart: start.dirtyRepository === false && start.dirtyWithinRuntimeScope === false,
    cleanAtEnd: end.dirtyRepository === false && end.dirtyWithinRuntimeScope === false,
    startDigest,
    endDigest,
  };
}

async function listFilesRecursively(directory, relative = "") {
  const entries = await readdir(path.join(directory, relative), { withFileTypes: true });
  const files = [];
  for (const entry of entries.toSorted((left, right) => left.name.localeCompare(right.name))) {
    const child = path.join(relative, entry.name);
    if (entry.isDirectory()) files.push(...await listFilesRecursively(directory, child));
    else if (entry.isFile()) files.push(child);
  }
  return files;
}

async function captureDistIdentity() {
  await access(DIST_DIR);
  const relativePaths = await listFilesRecursively(DIST_DIR);
  const files = [];
  for (const relativePath of relativePaths) {
    const bytes = await readFile(path.join(DIST_DIR, relativePath));
    files.push({
      path: relativePath.split(path.sep).join("/"),
      bytes: bytes.byteLength,
      sha256: sha256Bytes(bytes),
    });
  }
  return {
    root: "dist",
    fileCount: files.length,
    treeSha256: sha256Bytes(files.map((entry) => `${entry.path}:${entry.bytes}:${entry.sha256}`).join("\n")),
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
      setShellMode: ["setShellMode"],
      setPose: ["setPose"],
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
  if (specification.shellMode) await callLab(page, "setShellMode", specification.shellMode);
  if (specification.pose) await callLab(page, "setPose", specification.pose);
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
    shellMode: specification.shellMode ?? null,
    pose: specification.pose ?? null,
    reviewName: specification.reviewName ?? null,
    experimentVariant: specification.experimentVariant ?? null,
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

function distPathForResource(pathname) {
  if (pathname === "/" || pathname === "/index.html") return "index.html";
  if (pathname === "/glass-lab-v4" || pathname === "/glass-lab-v4/" || pathname === "/glass-lab-v4.html") {
    return "glass-lab-v4.html";
  }
  if (pathname === "/glass-lab" || pathname === "/glass-lab/" || pathname === "/glass-lab.html") {
    return "glass-lab.html";
  }
  let decoded;
  try {
    decoded = decodeURIComponent(pathname).replace(/^\/+/, "");
  } catch {
    return null;
  }
  const normalized = path.posix.normalize(decoded);
  if (!normalized || normalized === "." || normalized.startsWith("../") || path.posix.isAbsolute(normalized)) return null;
  return normalized;
}

function summarizeServedResources(records, expectedOrigin, requestFailures, distIdentity) {
  const unique = new Map();
  for (const record of records) {
    const key = [record.origin, record.path, record.status, record.bytes, record.sha256, record.bodyError].join(":");
    const existing = unique.get(key);
    if (existing) existing.requestCount += 1;
    else unique.set(key, { ...record, requestCount: 1 });
  }
  const resources = [...unique.values()].sort((left, right) => (
    left.origin.localeCompare(right.origin)
    || left.path.localeCompare(right.path)
    || left.status - right.status
    || String(left.sha256).localeCompare(String(right.sha256))
  ));
  const distFiles = new Map((distIdentity.files ?? []).map((entry) => [entry.path, entry]));
  const violations = [];
  let sameOriginResourceCount = 0;
  let matchedDistResourceCount = 0;

  for (const resource of resources) {
    if (resource.origin !== expectedOrigin) {
      violations.push({ type: "external-origin", origin: resource.origin, path: resource.path });
      continue;
    }
    sameOriginResourceCount += 1;
    if (resource.status < 200 || resource.status >= 300) {
      violations.push({ type: "non-2xx-response", path: resource.path, status: resource.status });
      continue;
    }
    if (resource.bodyError || !resource.sha256) {
      violations.push({ type: "response-body-unavailable", path: resource.path });
      continue;
    }
    if (resource.path.startsWith("/@vite") || resource.path.startsWith("/src/")) {
      violations.push({ type: "development-resource", path: resource.path });
      continue;
    }
    const distPath = distPathForResource(resource.path);
    const distEntry = distPath ? distFiles.get(distPath) : null;
    resource.distPath = distPath;
    resource.distSha256Match = Boolean(distEntry && distEntry.sha256 === resource.sha256);
    if (!distEntry) violations.push({ type: "resource-missing-from-dist", path: resource.path, distPath });
    else if (!resource.distSha256Match) {
      violations.push({ type: "served-resource-dist-hash-mismatch", path: resource.path, distPath });
    } else matchedDistResourceCount += 1;
  }
  for (const failure of requestFailures) violations.push({ type: "request-failed", ...failure });
  if (sameOriginResourceCount === 0) violations.push({ type: "no-same-origin-resources" });

  const identityResources = resources.map((resource) => ({
    origin: resource.origin,
    path: resource.path,
    status: resource.status,
    bytes: resource.bytes,
    sha256: resource.sha256,
    requestCount: resource.requestCount,
    distPath: resource.distPath ?? null,
    distSha256Match: resource.distSha256Match ?? false,
  }));
  return {
    servedResourceIdentity: {
      resourceCount: identityResources.length,
      sameOriginResourceCount,
      manifestSha256: sha256Bytes(identityResources.map((entry) => (
        `${entry.origin}:${entry.path}:${entry.status}:${entry.bytes}:${entry.sha256}:${entry.requestCount}`
      )).join("\n")),
      resources: identityResources,
    },
    previewIdentity: {
      passed: violations.length === 0 && matchedDistResourceCount === sameOriginResourceCount,
      serverKind: "vite-preview-compatible-static-dist",
      expectedOrigin,
      distTreeSha256: distIdentity.treeSha256 ?? null,
      distFileCount: distIdentity.fileCount ?? 0,
      matchedDistResourceCount,
      violations,
    },
  };
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  repositoryPath(options.outputDirectory);
  repositoryPath(options.manifest);
  await mkdir(options.outputDirectory, { recursive: true });
  const sourceIdentityStart = await captureSourceIdentity();
  const distIdentity = await captureDistIdentity().catch((error) => ({
    root: "dist",
    fileCount: 0,
    treeSha256: null,
    files: [],
    error: error instanceof Error ? error.message : String(error),
  }));
  const expectedOrigin = new URL(options.url).origin;

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
  const requestFailures = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("response", (response) => {
    let responseUrl;
    try {
      responseUrl = new URL(response.url());
    } catch {
      return;
    }
    servedResourceTasks.push((async () => {
      const status = response.status();
      let body = null;
      let bodyError = null;
      if (responseUrl.origin === expectedOrigin && status >= 200 && status < 300) {
        try {
          body = await response.body();
        } catch (error) {
          bodyError = error instanceof Error ? error.message : String(error);
        }
      }
      return {
        origin: responseUrl.origin,
        path: responseUrl.pathname,
        status,
        bytes: body?.byteLength ?? null,
        sha256: body ? sha256Bytes(body) : null,
        bodyError,
      };
    })());
  });
  page.on("requestfailed", (request) => {
    let requestUrl;
    try {
      requestUrl = new URL(request.url());
    } catch {
      return;
    }
    requestFailures.push({
      origin: requestUrl.origin,
      path: requestUrl.pathname,
      errorText: request.failure()?.errorText ?? "unknown",
    });
  });

  let manifest;
  try {
    if (sourceIdentityStart.dirtyRepository || sourceIdentityStart.dirtyWithinRuntimeScope) {
      throw new Error("Capture requires a clean repository and clean runtime source scope");
    }
    if (distIdentity.error || !distIdentity.treeSha256 || distIdentity.fileCount === 0) {
      throw new Error("Capture requires a completed dist build identity");
    }
    await page.goto(options.url, { waitUntil: "domcontentloaded", timeout: 30000 });
    await waitForLab(page);
    await page.waitForTimeout(1200);
    const canvas = await getLargestCanvas(page);
    const initialState = await getLabState(page);

    const captureSpecifications = [
      { id: "split-checker", role: "v3-v4-split", reviewName: "v3-v4-split-checker.png", pattern: "checker", mode: "split", debug: "beauty" },
      { id: "v3-checker", role: "v3-control-crop", pattern: "checker", mode: "v3", debug: "beauty" },
      { id: "difference-checker", role: "v3-v4-difference", pattern: "checker", mode: "difference", debug: "beauty" },
      { id: "edge-mask-black", role: "zone-mask", reviewName: "v4-edge-mask.png", pattern: "black", mode: "v4", debug: "edge-mask" },
      { id: "normals-checker", role: "surface-normal-debug", pattern: "checker", mode: "v4", debug: "normals" },
      { id: "thickness-checker", role: "optical-thickness-debug", pattern: "checker", mode: "v4", debug: "thickness" },
      { id: "refraction-offset-checker", role: "projected-refraction-debug", reviewName: "v4-refraction-offset.png", pattern: "checker", mode: "v4", debug: "refraction-offset" },
      { id: "fresnel-black", role: "fresnel-debug", pattern: "black", mode: "v4", debug: "fresnel" },
      { id: "adaptivity-flat", role: "content-adaptivity-debug", pattern: "low-frequency-flat-color", mode: "v4", debug: "adaptivity" },
      { id: "v4-checker", role: "sharpness-and-rim", reviewName: "v4-checker.png", pattern: "checker", mode: "v4", debug: "beauty" },
      { id: "v4-horizontal-lines", role: "horizontal-line-displacement", reviewName: "v4-horizontal-lines.png", pattern: "horizontal-lines", mode: "v4", debug: "beauty" },
      { id: "v4-vertical-lines", role: "vertical-line-displacement", reviewName: "v4-vertical-lines.png", pattern: "vertical-lines", mode: "v4", debug: "beauty" },
      { id: "v4-high-frequency-photo", role: "high-frequency-adaptivity", reviewName: "v4-high-frequency.png", pattern: "high-frequency-photo", mode: "v4", debug: "beauty" },
      { id: "v4-low-frequency-flat", role: "low-frequency-adaptivity", reviewName: "v4-low-frequency.png", pattern: "low-frequency-flat-color", mode: "v4", debug: "beauty" },
      { id: "v4-white", role: "light-background-discernibility", reviewName: "v4-white.png", pattern: "white", mode: "v4", debug: "beauty" },
      { id: "v4-black", role: "dark-background-discernibility", reviewName: "v4-black.png", pattern: "black", mode: "v4", debug: "beauty" },
      { id: "dispersion-checker", role: "dispersion-localization", reviewName: "v4-dispersion.png", pattern: "checker", mode: "v4", debug: "dispersion" },
    ];
    const captures = [];
    for (const specification of captureSpecifications) {
      const calibratedSpecification = specification.reviewName ? {
        shellMode: "energy-controlled",
        pose: "front",
        pointer: [0, 0],
        ...specification,
      } : specification;
      captures.push(await captureCanvas({
        page,
        canvas,
        outputDirectory: options.outputDirectory,
        id: specification.id,
        specification: calibratedSpecification,
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
          shellMode: "energy-controlled",
          pose: "front",
          pointer,
          settleMs: 350,
        },
      }));
    }

    const phase1bSpecifications = [];
    const shellBackgrounds = [
      { id: "black", pattern: "black" },
      { id: "white", pattern: "white" },
      { id: "color", pattern: "low-frequency-flat-color" },
    ];
    for (const shellMode of ["additive", "energy-controlled", "off"]) {
      for (const background of shellBackgrounds) {
        phase1bSpecifications.push({
          id: `phase1b-shell-${shellMode}-${background.id}`,
          role: "phase1b-reflection-shell-ab",
          pattern: background.pattern,
          mode: "v4",
          debug: "beauty",
          shellMode,
          pose: "front",
          pointer: [0, 0],
          experimentVariant: {
            family: "reflection-shell-ab-background",
            shellMode,
            background: background.id,
            view: "beauty",
            pointer: "center",
          },
        });
      }
    }
    const shellPointerPositions = [
      { id: "left", value: [-0.85, 0] },
      { id: "center", value: [0, 0] },
      { id: "right", value: [0.85, 0] },
    ];
    for (const shellMode of ["additive", "energy-controlled"]) {
      for (const view of ["reflection", "beauty"]) {
        for (const pointer of shellPointerPositions) {
          phase1bSpecifications.push({
            id: view === "reflection"
              ? `phase1b-shell-${shellMode}-pointer-${pointer.id}`
              : `phase1b-shell-${shellMode}-beauty-pointer-${pointer.id}`,
            role: "phase1b-reflection-shell-ab-pointer",
            pattern: "black",
            mode: "v4",
            debug: view,
            shellMode,
            pose: "front",
            pointer: pointer.value,
            experimentVariant: {
              family: "reflection-shell-ab-pointer",
              shellMode,
              background: "black",
              view,
              pointer: pointer.id,
            },
          });
        }
      }
    }
    for (const reflection of [
      { id: "left", pointer: [-0.85, 0], reviewName: "v4-reflection-left.png" },
      { id: "center", pointer: [0, 0], reviewName: "v4-reflection-center.png" },
      { id: "right", pointer: [0.85, 0], reviewName: "v4-reflection-right.png" },
    ]) {
      phase1bSpecifications.push({
        id: `phase1b-reflection-${reflection.id}`,
        role: "phase1b-reflection-pointer",
        reviewName: reflection.reviewName,
        pattern: "black",
        mode: "v4",
        debug: "reflection",
        shellMode: "energy-controlled",
        pose: "front",
        pointer: reflection.pointer,
      });
    }
    for (const pose of ["front", "left", "right"]) {
      phase1bSpecifications.push({
        id: `phase1b-pose-${pose}`,
        role: "phase1b-card-pose",
        pattern: "high-frequency-photo",
        mode: "v4",
        debug: "beauty",
        shellMode: "energy-controlled",
        pose,
        pointer: [0, 0],
      });
    }
    for (const pose of ["left", "right"]) {
      for (const pattern of ["horizontal-lines", "vertical-lines"]) {
        phase1bSpecifications.push({
          id: `phase1b-sidewall-${pose}-${pattern}`,
          role: "phase1b-sidewall-lines",
          pattern,
          mode: "v4",
          debug: "beauty",
          shellMode: "energy-controlled",
          pose,
          pointer: [0, 0],
          experimentVariant: {
            family: "sidewall-content-compression",
            shellMode: "energy-controlled",
            background: pattern,
            view: "beauty",
            pose,
          },
        });
      }
    }
    for (const pose of ["front", "left", "right"]) {
      phase1bSpecifications.push({
        id: `phase1b-optical-zones-${pose}`,
        role: "phase1b-optical-zones",
        pattern: "black",
        mode: "v4",
        debug: "optical-zones",
        shellMode: "energy-controlled",
        pose,
        pointer: [0, 0],
        experimentVariant: {
          family: "optical-zones-pose",
          shellMode: "energy-controlled",
          background: "black",
          view: "optical-zones",
          pose,
        },
      });
    }
    for (const specification of phase1bSpecifications) {
      captures.push(await captureCanvas({
        page,
        canvas,
        outputDirectory: options.outputDirectory,
        id: specification.id,
        specification,
      }));
    }

    await callLab(page, "setPattern", "checker");
    await callLab(page, "setMode", "split");
    await callLab(page, "setShellMode", "energy-controlled");
    await callLab(page, "setPose", "front");
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
    await page.waitForTimeout(100);
    const servedResources = await Promise.all(servedResourceTasks);
    const { servedResourceIdentity, previewIdentity } = summarizeServedResources(
      servedResources,
      expectedOrigin,
      requestFailures,
      distIdentity,
    );
    const hookEvidence = await page.evaluate(() => ({
      raf: window.__ILG_OPTICS_CAPTURE__?.raf ?? [],
      contexts: [...new Set(window.__ILG_OPTICS_CAPTURE__?.contexts ?? [])],
      viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
    }));
    const contractPassed = initialState?.normalPathDirectMedia === false
      && initialState?.sceneTarget?.type === "half-float"
      && initialState?.sceneTarget?.colorSpace === "linear"
      && initialState?.v3Preserved === true;
    const sourceIdentityEnd = await captureSourceIdentity();
    const sourceIdentityCheck = compareSourceIdentities(sourceIdentityStart, sourceIdentityEnd);
    const capturePassed = contractPassed
      && sourceIdentityCheck.passed
      && previewIdentity.passed
      && graphics.webgpuAvailable
      && !graphics.softwareRendererDetected
      && pageErrors.length === 0;

    manifest = {
      schemaVersion: 1,
      generator: SCRIPT_VERSION,
      generatedAt: new Date().toISOString(),
      status: capturePassed ? "CAPTURED" : "BLOCKED",
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
      sourceIdentity: sourceIdentityStart,
      sourceIdentityEnd,
      sourceIdentityCheck,
      distIdentity,
      servedResourceIdentity,
      previewIdentity,
      initialState,
      captures,
      phase1bCaptureIds: phase1bSpecifications.map((entry) => entry.id),
      pointerPath,
      uiPreview,
      performance: summarizeRaf(hookEvidence.raf),
      caveats: {
        naturalMediaTextureCoverage: false,
        naturalMediaTextureReason: "This calibration round uses local deterministic lab patterns; no uploaded natural-media Golden is embedded.",
        gpuTimingMeasured: false,
        gpuTimingReason: "rAF intervals are scheduling observations and are not WebGPU timestamp-query measurements.",
        acceptanceScope: "Phase 1B optics-lab calibration evidence; not final frozen-Golden visual acceptance.",
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
    const sourceIdentityEnd = await captureSourceIdentity().catch(() => null);
    manifest = {
      schemaVersion: 1,
      generator: SCRIPT_VERSION,
      generatedAt: new Date().toISOString(),
      status: "BLOCKED",
      route: new URL(options.url).pathname,
      error: error instanceof Error ? error.message : String(error),
      pageErrorCount: pageErrors.length,
      sourceIdentity: sourceIdentityStart,
      sourceIdentityEnd,
      sourceIdentityCheck: sourceIdentityEnd ? compareSourceIdentities(sourceIdentityStart, sourceIdentityEnd) : null,
      distIdentity,
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
