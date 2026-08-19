#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { performance as nodePerformance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import {
  REPO_ROOT,
  execText,
  readJson,
  sha256File,
  sha256Value,
  stable,
} from "./lib/common.mjs";

const SCRIPT_VERSION = "controlled-reference-v6";
const SCRIPT_PATH = fileURLToPath(import.meta.url);
const MATRIX_PATH = path.join(REPO_ROOT, "qa-v4/reference/capture-matrix.json");
const PRIVATE_REFERENCE_ROOT = path.join(REPO_ROOT, "qa-v4/reference");
const SOFTWARE_GPU_PATTERN = /swiftshader|llvmpipe|software|microsoft basic render/i;
const MEDIA_URL_PATTERN = /(?:stream\.mux|fastly\.mux|cfcdn\.mux|\.(?:m3u8|mp4|m4s|ts|webm)(?:[?#]|$))/i;

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));
}

async function ensureDirectory(directory) {
  await mkdir(directory, { recursive: true });
  return directory;
}

async function writeJsonFile(file, value) {
  await ensureDirectory(path.dirname(file));
  await writeFile(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function toRepositoryPath(file) {
  return path.relative(REPO_ROOT, file).split(path.sep).join("/");
}

function safeId(value, label) {
  if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]*$/.test(value)) {
    throw new Error(`${label} contains unsupported characters`);
  }
  return value;
}

function captureIdNow() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function parseArguments(argv) {
  const options = { profile: null, site: null, captureId: captureIdNow() };
  for (const argument of argv) {
    if (argument.startsWith("--profile=")) options.profile = safeId(argument.slice(10), "profile");
    else if (argument.startsWith("--site=")) options.site = safeId(argument.slice(7), "site");
    else if (argument.startsWith("--capture-id=")) options.captureId = safeId(argument.slice(13), "capture id");
    else throw new Error(`Unknown argument: ${argument}`);
  }
  return options;
}

function percentile(sorted, quantile) {
  if (!sorted.length) return null;
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * quantile) - 1));
  return sorted[index];
}

function summarizeRafTimestamps(timestamps) {
  const intervals = [];
  for (let index = 1; index < timestamps.length; index += 1) {
    const delta = timestamps[index] - timestamps[index - 1];
    if (Number.isFinite(delta) && delta > 0) intervals.push(delta);
  }
  const sorted = [...intervals].sort((a, b) => a - b);
  const median = percentile(sorted, 0.5);
  const overBudgetThresholdMs = median === null ? null : median * 1.5;
  return {
    metricName: "rafIntervalMs",
    metricMeaning: "browser requestAnimationFrame interval; not GPU execution time",
    gpuExecutionTimeMeasured: false,
    sampleCount: intervals.length,
    p50: median,
    p95: percentile(sorted, 0.95),
    p99: percentile(sorted, 0.99),
    max: sorted.length ? sorted[sorted.length - 1] : null,
    estimatedRefreshHz: median ? 1000 / median : null,
    over20msCount: intervals.filter((value) => value > 20).length,
    over50msCount: intervals.filter((value) => value > 50).length,
    overBudgetThresholdMs,
    overBudgetRatio: overBudgetThresholdMs && intervals.length
      ? intervals.filter((value) => value > overBudgetThresholdMs).length / intervals.length
      : null,
  };
}

function commandValue(command, args) {
  try {
    return execText(command, args);
  } catch {
    return null;
  }
}

function hostEnvironment() {
  return {
    os: "macOS",
    osVersion: commandValue("sw_vers", ["-productVersion"]),
    osBuild: commandValue("sw_vers", ["-buildVersion"]),
    architecture: commandValue("uname", ["-m"]),
  };
}

async function browserEnvironment(browser) {
  const session = await browser.newBrowserCDPSession();
  let version = null;
  let systemInfo = null;
  try {
    version = await session.send("Browser.getVersion");
  } catch (error) {
    version = { error: String(error) };
  }
  try {
    systemInfo = await session.send("SystemInfo.getInfo");
  } catch (error) {
    systemInfo = { error: String(error) };
  }
  await session.detach().catch(() => {});
  return {
    playwrightBrowserVersion: browser.version(),
    cdp: version,
    systemInfo,
  };
}

async function installCaptureHooks(context) {
  await context.addInitScript(() => {
    const capture = {
      contextTypes: [],
      events: [],
      raf: [],
      longTasks: [],
      calibrationMode: null,
      calibrationEvents: [],
    };
    Object.defineProperty(window, "__ILG_CONTROLLED_CAPTURE__", {
      configurable: false,
      enumerable: false,
      writable: false,
      value: capture,
    });

    const originalGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function controlledGetContext(type, ...args) {
      capture.contextTypes.push({ type: String(type), at: performance.now() });
      return Reflect.apply(originalGetContext, this, [type, ...args]);
    };

    const blockCalibrationEvent = (event) => {
      if (capture.calibrationMode !== "touch") return;
      capture.calibrationEvents.push({
        type: event.type,
        eventTimeStamp: event.timeStamp,
        isTrusted: event.isTrusted,
      });
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    for (const type of [
      "pointerdown", "pointermove", "pointerup", "pointercancel",
      "touchstart", "touchmove", "touchend", "touchcancel",
    ]) {
      window.addEventListener(type, blockCalibrationEvent, { capture: true, passive: false });
    }

    const recordEvent = (event) => {
      if (capture.events.length >= 50000) return;
      const row = {
        type: event.type,
        at: performance.now(),
        eventTimeStamp: event.timeStamp,
        isTrusted: event.isTrusted,
      };
      if (event instanceof PointerEvent) {
        Object.assign(row, {
          pointerType: event.pointerType,
          clientX: event.clientX,
          clientY: event.clientY,
          buttons: event.buttons,
        });
      } else if (event instanceof WheelEvent) {
        Object.assign(row, {
          deltaX: event.deltaX,
          deltaY: event.deltaY,
          deltaMode: event.deltaMode,
        });
      } else if (event instanceof TouchEvent) {
        row.touches = [...event.touches].map((touch) => ({
          identifier: touch.identifier,
          clientX: touch.clientX,
          clientY: touch.clientY,
        }));
      }
      capture.events.push(row);
    };

    for (const type of [
      "pointerdown", "pointermove", "pointerup", "pointercancel",
      "wheel", "touchstart", "touchmove", "touchend", "touchcancel",
      "visibilitychange", "blur", "focus",
    ]) {
      const target = type === "visibilitychange" ? document : window;
      target.addEventListener(type, recordEvent, { capture: true, passive: true });
    }

    try {
      const observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          capture.longTasks.push({ startTime: entry.startTime, duration: entry.duration });
        }
      });
      observer.observe({ entryTypes: ["longtask"] });
    } catch {
      // Long Task API is optional. The absence is represented by an empty array.
    }

    const tick = (time) => {
      if (capture.raf.length < 250000) capture.raf.push(time);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

async function resetTelemetry(page) {
  await page.evaluate(() => {
    const capture = window.__ILG_CONTROLLED_CAPTURE__;
    if (!capture) return;
    capture.events.length = 0;
    capture.raf.length = 0;
    capture.longTasks.length = 0;
  });
}

async function readTelemetry(page) {
  return page.evaluate(() => {
    const capture = window.__ILG_CONTROLLED_CAPTURE__;
    return capture
      ? {
          contextTypes: [...capture.contextTypes],
          events: [...capture.events],
          raf: [...capture.raf],
          longTasks: [...capture.longTasks],
        }
      : { contextTypes: [], events: [], raf: [], longTasks: [] };
  });
}

async function newCaptureContext(browser, profile, videoDirectory = null) {
  if (videoDirectory) await ensureDirectory(videoDirectory);
  const options = {
    viewport: { width: profile.width, height: profile.height },
    screen: { width: profile.width, height: profile.height },
    deviceScaleFactor: profile.browserDpr,
    isMobile: profile.mobile,
    hasTouch: profile.hasTouch,
    reducedMotion: "no-preference",
    colorScheme: "dark",
  };
  if (videoDirectory) {
    options.recordVideo = {
      dir: videoDirectory,
      size: { width: profile.width, height: profile.height },
    };
  }
  const context = await browser.newContext(options);
  await installCaptureHooks(context);
  return context;
}

function headerValue(headers, name) {
  const wanted = name.toLowerCase();
  for (const [key, value] of Object.entries(headers || {})) {
    if (key.toLowerCase() === wanted) return Array.isArray(value) ? value.join(", ") : String(value);
  }
  return null;
}

function isMediaResource(record) {
  return record.resourceType === "Media"
    || /^(?:video|audio)\//i.test(record.mimeType || "")
    || MEDIA_URL_PATTERN.test(record.url || "");
}

function validatorSummary(canonical) {
  const validators = canonical
    .filter((record) => record.etag || record.lastModified)
    .map((record) => ({
      resourceType: record.resourceType,
      mimeType: record.mimeType,
      encodedDataLength: record.encodedDataLength,
      etag: record.etag,
      lastModified: record.lastModified,
    }));
  const document = canonical.find((record) => record.resourceType === "Document") || null;
  return {
    document: document
      ? { status: document.status, etag: document.etag, lastModified: document.lastModified }
      : null,
    resourceValidatorCount: validators.length,
    resourceValidatorManifestSha256: sha256Value(validators),
  };
}

async function createNetworkRecorder(context, page) {
  const cdp = await context.newCDPSession(page);
  const records = new Map();
  const get = (requestId) => {
    if (!records.has(requestId)) records.set(requestId, { requestId });
    return records.get(requestId);
  };

  cdp.on("Network.requestWillBeSent", (event) => {
    Object.assign(get(event.requestId), {
      requestId: event.requestId,
      url: event.request.url,
      method: event.request.method,
      resourceType: event.type || null,
      requestTimestamp: event.timestamp,
      documentURL: event.documentURL,
    });
  });
  cdp.on("Network.responseReceived", (event) => {
    Object.assign(get(event.requestId), {
      resourceType: event.type || get(event.requestId).resourceType || null,
      status: event.response.status,
      statusText: event.response.statusText,
      mimeType: event.response.mimeType,
      protocol: event.response.protocol,
      fromDiskCache: event.response.fromDiskCache,
      fromServiceWorker: event.response.fromServiceWorker,
      responseHeaders: event.response.headers || {},
      responseTimestamp: event.timestamp,
    });
  });
  cdp.on("Network.responseReceivedExtraInfo", (event) => {
    Object.assign(get(event.requestId), {
      statusCodeFromExtraInfo: event.statusCode,
      responseExtraHeaders: event.headers || {},
    });
  });
  cdp.on("Network.loadingFinished", (event) => {
    Object.assign(get(event.requestId), {
      finished: true,
      finishTimestamp: event.timestamp,
      encodedDataLength: event.encodedDataLength,
    });
  });
  cdp.on("Network.loadingFailed", (event) => {
    Object.assign(get(event.requestId), {
      finished: false,
      failed: true,
      errorText: event.errorText,
      canceled: event.canceled,
    });
  });
  await cdp.send("Network.enable");

  const snapshot = () => {
    const raw = [...records.values()].map((record) => {
      const headers = { ...(record.responseHeaders || {}), ...(record.responseExtraHeaders || {}) };
      return {
        ...record,
        contentLength: Number(headerValue(headers, "content-length") || 0),
        etag: headerValue(headers, "etag"),
        lastModified: headerValue(headers, "last-modified"),
      };
    });
    raw.sort((left, right) => String(left.requestId).localeCompare(String(right.requestId)));
    const canonical = raw.map((record) => ({
      url: record.url || null,
      method: record.method || null,
      resourceType: record.resourceType || null,
      status: record.status ?? record.statusCodeFromExtraInfo ?? null,
      mimeType: record.mimeType || null,
      protocol: record.protocol || null,
      encodedDataLength: Number(record.encodedDataLength || 0),
      contentLength: Number(record.contentLength || 0),
      etag: record.etag || null,
      lastModified: record.lastModified || null,
      fromDiskCache: Boolean(record.fromDiskCache),
      fromServiceWorker: Boolean(record.fromServiceWorker),
      failed: Boolean(record.failed),
    })).sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)));
    const core = canonical.filter((record) => !isMediaResource(record));
    const byType = {};
    for (const record of canonical) {
      const type = record.resourceType || "Other";
      byType[type] = (byType[type] || 0) + 1;
    }
    return {
      raw,
      canonical,
      core,
      summary: {
        resourceCount: canonical.length,
        coreResourceCount: core.length,
        mediaResourceCount: canonical.length - core.length,
        encodedBytes: canonical.reduce((sum, record) => sum + record.encodedDataLength, 0),
        byType,
        fullNetworkManifestSha256: sha256Value(canonical),
        coreResourceManifestSha256: sha256Value(core),
        originsSha256: sha256Value([...new Set(canonical.map((record) => {
          try {
            return new URL(record.url).origin;
          } catch {
            return "invalid";
          }
        }))].sort()),
        validators: validatorSummary(canonical),
      },
    };
  };

  return { cdp, snapshot };
}

async function waitForPageReady(page, site, matrix) {
  const navigationStartedAt = new Date().toISOString();
  const start = nodePerformance.now();
  await page.goto(site.url, { waitUntil: "domcontentloaded", timeout: 90000 });
  if (site.id === "local") {
    await page.waitForFunction(() => {
      const qa = window.__LIQUID_GLASS_QA__ || window.__ILG_QA__;
      return Boolean(qa?.getState?.()?.ready);
    }, null, { timeout: 90000 });
  } else {
    await page.waitForFunction(() => {
      const canvas = document.querySelector("canvas");
      return Boolean(canvas && canvas.width > 64 && canvas.height > 64);
    }, null, { timeout: 90000 });
    await page.waitForTimeout(matrix.capture.targetWarmupMs);
  }
  await page.evaluate(() => document.fonts?.ready || Promise.resolve());
  let localSourceIdentity = null;
  if (site.id === "local") {
    localSourceIdentity = await page.evaluate(async () => {
      const response = await fetch("/__ilg_capture_identity.json", { cache: "no-store" });
      if (!response.ok) throw new Error(`source identity endpoint returned ${response.status}`);
      return response.json();
    });
    if (localSourceIdentity.sourceCommit !== site.expectedSourceCommit
      || localSourceIdentity.sourceTree !== site.expectedSourceTree
      || localSourceIdentity.trackedTreeClean !== true) {
      throw new Error("LOCAL_SOURCE_ATTESTATION_GATE: server identity does not match the controlled baseline");
    }
  }
  return {
    navigationStartedAt,
    readyAt: new Date().toISOString(),
    readyElapsedMs: nodePerformance.now() - start,
    finalUrl: page.url(),
    localSourceIdentity,
  };
}

async function collectPageEnvironment(page) {
  return page.evaluate(async () => {
    let highEntropyUserAgent = null;
    try {
      highEntropyUserAgent = await navigator.userAgentData?.getHighEntropyValues?.([
        "architecture", "bitness", "fullVersionList", "model", "platformVersion", "wow64",
      ]);
    } catch {
      highEntropyUserAgent = null;
    }

    let webgpu = { available: false };
    try {
      if (navigator.gpu) {
        const adapter = await navigator.gpu.requestAdapter({ powerPreference: "high-performance" });
        if (adapter) {
          const info = adapter.info || {};
          webgpu = {
            available: true,
            vendor: info.vendor || null,
            architecture: info.architecture || null,
            device: info.device || null,
            description: info.description || null,
            isFallbackAdapter: adapter.isFallbackAdapter ?? null,
            inferredBackend: /metal/i.test(`${info.architecture || ""} ${info.description || ""}`) ? "metal" : null,
          };
        }
      }
    } catch (error) {
      webgpu = { available: false, error: String(error) };
    }

    const timestamps = [];
    await new Promise((resolve) => {
      const tick = (time) => {
        timestamps.push(time);
        if (timestamps.length >= 120) resolve();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    const intervals = [];
    for (let index = 1; index < timestamps.length; index += 1) intervals.push(timestamps[index] - timestamps[index - 1]);
    intervals.sort((a, b) => a - b);
    const median = intervals[Math.floor(intervals.length / 2)] || null;

    const canvases = [...document.querySelectorAll("canvas")].map((canvas) => {
      const rect = canvas.getBoundingClientRect();
      return {
        css: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        buffer: { width: canvas.width, height: canvas.height },
        effectiveDpr: {
          x: rect.width ? canvas.width / rect.width : null,
          y: rect.height ? canvas.height / rect.height : null,
        },
      };
    });
    const qa = window.__LIQUID_GLASS_QA__ || window.__ILG_QA__;
    let qaBackend = null;
    try {
      qaBackend = qa?.getState?.()?.backend || null;
    } catch {
      qaBackend = null;
    }
    return {
      url: location.href,
      title: document.title,
      userAgent: navigator.userAgent,
      highEntropyUserAgent,
      language: navigator.language,
      hardwareConcurrency: navigator.hardwareConcurrency,
      deviceMemory: navigator.deviceMemory || null,
      viewport: {
        width: innerWidth,
        height: innerHeight,
        browserDpr: devicePixelRatio,
        screenWidth: screen.width,
        screenHeight: screen.height,
      },
      canvases,
      webgpu,
      qaBackend,
      observedCanvasContextTypes: [...new Set((window.__ILG_CONTROLLED_CAPTURE__?.contextTypes || []).map((entry) => entry.type))],
      refreshRate: {
        method: "120 requestAnimationFrame timestamps",
        sampleCount: intervals.length,
        medianIntervalMs: median,
        estimatedHz: median ? 1000 / median : null,
        p95IntervalMs: intervals[Math.min(intervals.length - 1, Math.ceil(intervals.length * 0.95) - 1)] || null,
      },
    };
  });
}

function assertRealGpu(environment, site) {
  const adapter = environment.webgpu;
  const fingerprint = `${adapter?.vendor || ""} ${adapter?.architecture || ""} ${adapter?.description || ""}`;
  if (!adapter?.available) throw new Error("REAL_GPU_GATE: WebGPU adapter is unavailable");
  if (adapter.isFallbackAdapter === true || SOFTWARE_GPU_PATTERN.test(fingerprint)) {
    throw new Error("REAL_GPU_GATE: WebGPU adapter is a software or fallback adapter");
  }
  if (site.id === "local" && environment.qaBackend !== "webgpu") {
    throw new Error(`REAL_GPU_GATE: local renderer backend is ${environment.qaBackend || "unknown"}`);
  }
}

function assertCaptureProfile(environment, profile, matrix) {
  const failures = [];
  if (environment.viewport.width !== profile.width || environment.viewport.height !== profile.height) {
    failures.push(`viewport ${environment.viewport.width}x${environment.viewport.height}`);
  }
  if (Math.abs(environment.viewport.browserDpr - profile.browserDpr) > 0.01) {
    failures.push(`browser DPR ${environment.viewport.browserDpr}`);
  }
  const canvas = environment.canvases[0];
  const tolerance = matrix.capture.validation.canvasDprTolerance;
  if (!canvas) failures.push("missing canvas");
  else if (Math.abs(canvas.effectiveDpr.x - profile.expectedCanvasDpr) > tolerance
    || Math.abs(canvas.effectiveDpr.y - profile.expectedCanvasDpr) > tolerance) {
    failures.push(`canvas DPR ${canvas.effectiveDpr.x}x${canvas.effectiveDpr.y}`);
  }
  if (failures.length) throw new Error(`CAPTURE_PROFILE_GATE: ${failures.join(", ")}`);
}

async function captureScreenshot(page, directory, id) {
  const file = path.join(directory, "screenshots", `${safeId(id, "screenshot id")}.png`);
  await ensureDirectory(path.dirname(file));
  const capturedAt = new Date().toISOString();
  const pageTimeMs = await page.evaluate(() => performance.now());
  await page.screenshot({ path: file, type: "png" });
  return {
    id,
    capturedAt,
    pageTimeMs,
    path: toRepositoryPath(file),
    sha256: await sha256File(file),
    viewport: await page.evaluate(() => ({ width: innerWidth, height: innerHeight, dpr: devicePixelRatio })),
  };
}

async function captureDomSnapshot(cdp) {
  return cdp.send("DOMSnapshot.captureSnapshot", {
    computedStyles: [
      "display", "position", "transform", "perspective", "opacity",
      "font-family", "font-size", "font-weight", "line-height", "letter-spacing",
    ],
    includePaintOrder: true,
    includeDOMRects: true,
  });
}

function sanitizedEnvironment(environment) {
  return {
    userAgent: environment.userAgent,
    highEntropyUserAgent: environment.highEntropyUserAgent,
    viewport: environment.viewport,
    canvases: environment.canvases,
    webgpu: environment.webgpu,
    qaBackend: environment.qaBackend,
    observedCanvasContextTypes: environment.observedCanvasContextTypes,
    refreshRate: environment.refreshRate,
  };
}

async function sampleLandmarks(page) {
  return page.evaluate(() => {
    const quadFor = (element) => {
      if (typeof element.getBoxQuads === "function") {
        const quad = element.getBoxQuads()[0];
        if (quad) return [quad.p1, quad.p2, quad.p3, quad.p4].map((point) => ({ x: point.x, y: point.y }));
      }
      const rect = element.getBoundingClientRect();
      return [
        { x: rect.left, y: rect.top },
        { x: rect.right, y: rect.top },
        { x: rect.right, y: rect.bottom },
        { x: rect.left, y: rect.bottom },
      ];
    };

    let candidates = [...document.querySelectorAll(".tile-card")];
    if (!candidates.length) {
      candidates = [...document.querySelectorAll("body *")].filter((element) => {
        const style = getComputedStyle(element);
        if (style.position !== "absolute" && style.position !== "fixed") return false;
        const rect = element.getBoundingClientRect();
        return rect.width > 160
          && rect.height > 100
          && rect.right > 0
          && rect.bottom > 0
          && rect.left < innerWidth
          && rect.top < innerHeight
          && /[A-Za-z]{3,}/.test(element.textContent || "");
      });
    }

    const deduplicated = new Map();
    for (const element of candidates) {
      const rect = element.getBoundingClientRect();
      if (rect.width <= 8 || rect.height <= 8 || rect.right <= 0 || rect.bottom <= 0 || rect.left >= innerWidth || rect.top >= innerHeight) continue;
      const text = (element.textContent || "").replace(/\s+/g, " ").trim().slice(0, 120);
      const geometryKey = [rect.x, rect.y, rect.width, rect.height].map((value) => Math.round(value * 2) / 2).join(":");
      if (!deduplicated.has(geometryKey)) deduplicated.set(geometryKey, { element, text });
    }

    const keyCounts = new Map();
    const cards = [...deduplicated.values()].map(({ element, text }) => {
      const baseKey = `${text}|${element.id || ""}|${String(element.className || "")}`;
      const occurrence = keyCounts.get(baseKey) || 0;
      keyCounts.set(baseKey, occurrence + 1);
      const key = `${baseKey}#${occurrence}`;
      const quad = quadFor(element);
      const center = {
        x: quad.reduce((sum, point) => sum + point.x, 0) / quad.length,
        y: quad.reduce((sum, point) => sum + point.y, 0) / quad.length,
      };
      return { key, center, quad };
    });
    cards.sort((left, right) => {
      const leftDistance = Math.hypot(left.center.x - innerWidth / 2, left.center.y - innerHeight / 2);
      const rightDistance = Math.hypot(right.center.x - innerWidth / 2, right.center.y - innerHeight / 2);
      return leftDistance - rightDistance;
    });

    const qa = window.__LIQUID_GLASS_QA__ || window.__ILG_QA__;
    let qaState = null;
    try {
      qaState = qa?.getState?.() || null;
    } catch {
      qaState = null;
    }
    return {
      capturedAtPageTimeMs: performance.now(),
      cards: cards.slice(0, 8),
      qaState,
      highlightCentroid: qaState?.highlightCentroid || null,
    };
  });
}

function ndcToPoint(positionNdc, profile) {
  return [
    Math.round(((positionNdc[0] + 1) / 2) * profile.width),
    Math.round(((positionNdc[1] + 1) / 2) * profile.height),
  ];
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function resolveDelta(delta, profile, matrix) {
  const fraction = matrix.capture.inputResolution.maxDeltaViewportFraction;
  return [
    Math.sign(delta[0]) * Math.min(Math.abs(delta[0]), profile.width * fraction),
    Math.sign(delta[1]) * Math.min(Math.abs(delta[1]), profile.height * fraction),
  ];
}

function resolveInputScript(inputScript, profile, matrix) {
  const start = ndcToPoint(matrix.capture.inputResolution.startPositionNdc, profile);
  const steps = inputScript.steps.map((step) => {
    if (["pointer-drag", "pointer-drag-release", "touch-drag-release"].includes(step.type)) {
      const requestedDelta = step.deltaCssPx;
      const effectiveDelta = resolveDelta(requestedDelta, profile, matrix);
      const from = [
        clamp(start[0], 2, profile.width - 2),
        clamp(start[1], 2, profile.height - 2),
      ];
      const to = [
        clamp(from[0] + effectiveDelta[0], 2, profile.width - 2),
        clamp(from[1] + effectiveDelta[1], 2, profile.height - 2),
      ];
      return {
        ...step,
        requestedDeltaCssPx: requestedDelta,
        effectiveDeltaCssPx: [to[0] - from[0], to[1] - from[1]],
        fromCssPx: from,
        toCssPx: to,
      };
    }
    return { ...step };
  });
  return {
    schemaVersion: 1,
    sourceInputId: inputScript.id,
    profile: profile.id,
    viewport: { width: profile.width, height: profile.height, browserDpr: profile.browserDpr },
    pointerPositions: matrix.capture.pointerPositions,
    releaseCheckpointsMs: matrix.capture.releaseCheckpointsMs,
    steps,
  };
}

async function timedMouseDrag(cdp, step) {
  const sampleHz = step.sampleHz || 60;
  const requestedSamples = Math.max(2, Math.round((step.durationMs / 1000) * sampleHz));
  const [fromX, fromY] = step.fromCssPx;
  const [toX, toY] = step.toCssPx;
  await cdp.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: fromX, y: fromY });
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mousePressed", x: fromX, y: fromY, button: "left", buttons: 1, clickCount: 1,
  });
  const startedAt = nodePerformance.now();
  let deliveredSamples = 0;
  let slot = 1;
  while (slot < requestedSamples) {
    const dueAt = startedAt + (step.durationMs * slot) / requestedSamples;
    await sleep(dueAt - nodePerformance.now());
    const elapsed = nodePerformance.now() - startedAt;
    if (elapsed >= step.durationMs) break;
    const progress = elapsed / step.durationMs;
    await cdp.send("Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: fromX + (toX - fromX) * progress,
      y: fromY + (toY - fromY) * progress,
      button: "left",
      buttons: 1,
    });
    deliveredSamples += 1;
    slot = Math.max(slot + 1, Math.floor((elapsed / step.durationMs) * requestedSamples) + 1);
  }
  await sleep(startedAt + step.durationMs - nodePerformance.now());
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mouseMoved", x: toX, y: toY, button: "left", buttons: 1,
  });
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mouseReleased", x: toX, y: toY, button: "left", buttons: 0, clickCount: 1,
  });
  const releasedAtMonotonicMs = nodePerformance.now();
  return {
    delivery: "cdp-trusted-mouse-wall-clock",
    requestedDurationMs: step.durationMs,
    actualDurationMs: releasedAtMonotonicMs - startedAt,
    releasedAtMonotonicMs,
    requestedSamples,
    deliveredSamples: deliveredSamples + 1,
    skippedOverdueSamples: requestedSamples - deliveredSamples - 1,
  };
}

async function calibrateTrustedTouch(page, cdp, profile) {
  const probeDurationMs = 60;
  const point = await page.evaluate(() => ({ x: innerWidth / 2, y: innerHeight / 2 }));
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await page.evaluate(() => {
    const capture = window.__ILG_CONTROLLED_CAPTURE__;
    capture.calibrationEvents.length = 0;
    capture.calibrationMode = "touch";
  });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [{ x: point.x, y: point.y, radiusX: 1, radiusY: 1, force: 1, id: 9 }],
  });
  await sleep(probeDurationMs);
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchMove",
    touchPoints: [{ x: point.x + 1, y: point.y, radiusX: 1, radiusY: 1, force: 1, id: 9 }],
  });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await page.waitForFunction(() => window.__ILG_CONTROLLED_CAPTURE__?.calibrationEvents
    .some((event) => event.type === "touchend"), null, { timeout: 2000 });
  const events = await page.evaluate(() => {
    const capture = window.__ILG_CONTROLLED_CAPTURE__;
    capture.calibrationMode = null;
    return [...capture.calibrationEvents];
  });
  const start = events.find((event) => event.type === "touchstart");
  const end = [...events].reverse().find((event) => event.type === "touchend");
  const observedDurationMs = end && start ? end.eventTimeStamp - start.eventTimeStamp : null;
  if (!start?.isTrusted || !end?.isTrusted || !Number.isFinite(observedDurationMs)) {
    throw new Error("TOUCH_CALIBRATION_GATE: trusted touch timestamps unavailable");
  }
  const dispatchLeadMs = clamp(observedDurationMs - probeDurationMs, 0, 80);
  return { probeDurationMs, observedDurationMs, dispatchLeadMs, profileHasTouch: profile.hasTouch };
}

async function timedTouchDrag(page, cdp, step, profile, calibration) {
  const sampleHz = step.sampleHz || 60;
  const requestedSamples = Math.max(2, Math.round((step.durationMs / 1000) * sampleHz));
  const [fromX, fromY] = step.fromCssPx;
  const [toX, toY] = step.toCssPx;
  const eventIndex = await page.evaluate(() => window.__ILG_CONTROLLED_CAPTURE__?.events.length || 0);
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchStart",
    touchPoints: [{ x: fromX, y: fromY, radiusX: 1, radiusY: 1, force: 1, id: 1 }],
  });
  const startedAt = nodePerformance.now();
  const finalDispatchAt = step.durationMs - Math.min(calibration.dispatchLeadMs, step.durationMs * 0.45);
  let deliveredSamples = 0;
  let slot = 1;
  while (slot < requestedSamples) {
    const dueAt = startedAt + Math.min(finalDispatchAt, (step.durationMs * slot) / requestedSamples);
    await sleep(dueAt - nodePerformance.now());
    const elapsed = nodePerformance.now() - startedAt;
    if (elapsed >= finalDispatchAt) break;
    const progress = elapsed / step.durationMs;
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{
        x: fromX + (toX - fromX) * progress,
        y: fromY + (toY - fromY) * progress,
        radiusX: 1,
        radiusY: 1,
        force: 1,
        id: 1,
      }],
    });
    deliveredSamples += 1;
    slot = Math.max(slot + 1, Math.floor((elapsed / step.durationMs) * requestedSamples) + 1);
  }
  await sleep(startedAt + finalDispatchAt - nodePerformance.now());
  await cdp.send("Input.dispatchTouchEvent", {
    type: "touchMove",
    touchPoints: [{ x: toX, y: toY, radiusX: 1, radiusY: 1, force: 1, id: 1 }],
  });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  if (!profile.hasTouch) await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: false, maxTouchPoints: 1 });
  const releasedAtMonotonicMs = nodePerformance.now();
  const observed = await page.evaluate((fromIndex) => {
    const events = (window.__ILG_CONTROLLED_CAPTURE__?.events || []).slice(fromIndex);
    const start = events.find((event) => event.type === "touchstart");
    const end = [...events].reverse().find((event) => event.type === "touchend");
    return start && end
      ? { start: start.eventTimeStamp, end: end.eventTimeStamp, durationMs: end.eventTimeStamp - start.eventTimeStamp }
      : null;
  }, eventIndex);
  return {
    delivery: "cdp-trusted-touch-wall-clock",
    requestedDurationMs: step.durationMs,
    actualDurationMs: observed?.durationMs ?? releasedAtMonotonicMs - startedAt,
    dispatchDurationMs: releasedAtMonotonicMs - startedAt,
    observedEventTiming: observed,
    calibration,
    releasedAtMonotonicMs,
    requestedSamples,
    deliveredSamples: deliveredSamples + 1,
    skippedOverdueSamples: requestedSamples - deliveredSamples - 1,
  };
}

async function armWheelObservation(page, blockApplication) {
  await page.evaluate(({ block }) => {
    const capture = window.__ILG_CONTROLLED_CAPTURE__;
    capture.wheelObservation = null;
    const handler = (event) => {
      if (block) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      capture.wheelObservation = {
        deltaX: event.deltaX,
        deltaY: event.deltaY,
        deltaMode: event.deltaMode,
        isTrusted: event.isTrusted,
      };
    };
    window.addEventListener("wheel", handler, { capture: true, passive: false, once: true });
  }, { block: blockApplication });
}

async function readWheelObservation(page) {
  await page.waitForFunction(() => window.__ILG_CONTROLLED_CAPTURE__?.wheelObservation !== null, null, { timeout: 2000 });
  return page.evaluate(() => window.__ILG_CONTROLLED_CAPTURE__.wheelObservation);
}

async function calibrateTrustedWheel(page, cdp) {
  const point = await page.evaluate(() => ({ x: innerWidth / 2, y: innerHeight / 2 }));
  const dispatchedProbe = 100;
  await armWheelObservation(page, true);
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mouseWheel", x: point.x, y: point.y, deltaX: 0, deltaY: dispatchedProbe,
  });
  const observed = await readWheelObservation(page);
  if (!observed?.isTrusted || observed.deltaMode !== 0 || !Number.isFinite(observed.deltaY) || observed.deltaY === 0) {
    throw new Error("PIXEL_WHEEL_CALIBRATION_GATE: no trusted pixel wheel observation");
  }
  return {
    point,
    dispatchedProbe,
    observedProbe: observed.deltaY,
    hostScale: observed.deltaY / dispatchedProbe,
  };
}

async function dispatchTrustedPixelWheel(page, cdp, step, calibration, tolerance) {
  const requested = step.deltaCssPx || step.delta || [0, 0];
  const dispatched = requested.map((value) => value / calibration.hostScale);
  await armWheelObservation(page, false);
  await cdp.send("Input.dispatchMouseEvent", {
    type: "mouseWheel",
    x: calibration.point.x,
    y: calibration.point.y,
    deltaX: dispatched[0],
    deltaY: dispatched[1],
  });
  const observed = await readWheelObservation(page);
  const verified = Boolean(observed?.isTrusted)
    && observed.deltaMode === 0
    && Math.abs(observed.deltaX - requested[0]) <= tolerance
    && Math.abs(observed.deltaY - requested[1]) <= tolerance;
  return {
    delivery: "cdp-trusted-pixel-wheel-calibrated",
    requested,
    dispatched,
    observed,
    calibration: {
      dispatchedProbe: calibration.dispatchedProbe,
      observedProbe: calibration.observedProbe,
      hostScale: calibration.hostScale,
    },
    verified,
  };
}

async function dispatchSyntheticLineWheel(page, step) {
  return page.evaluate(({ deltaX, deltaY }) => {
    const target = document.elementFromPoint(innerWidth / 2, innerHeight / 2) || document.body;
    const event = new WheelEvent("wheel", {
      bubbles: true,
      cancelable: true,
      composed: true,
      deltaX,
      deltaY,
      deltaMode: WheelEvent.DOM_DELTA_LINE,
      clientX: innerWidth / 2,
      clientY: innerHeight / 2,
    });
    const isTrusted = event.isTrusted;
    const notCanceled = target.dispatchEvent(event);
    return {
      delivery: "synthetic-dom-wheel-event",
      isTrusted,
      deltaMode: event.deltaMode,
      deltaX: event.deltaX,
      deltaY: event.deltaY,
      notCanceled,
      strictMotionEvidence: false,
    };
  }, { deltaX: step.delta?.[0] || 0, deltaY: step.delta?.[1] || 0 });
}

function maximumLandmarkDelta(previous, current) {
  if (!previous?.cards?.length || !current?.cards?.length) return null;
  const previousByKey = new Map(previous.cards.map((card) => [card.key, card]));
  const deltas = [];
  for (const card of current.cards) {
    const before = previousByKey.get(card.key);
    if (!before) continue;
    for (let index = 0; index < Math.min(before.quad.length, card.quad.length); index += 1) {
      deltas.push(Math.hypot(card.quad[index].x - before.quad[index].x, card.quad[index].y - before.quad[index].y));
    }
  }
  return deltas.length ? Math.max(...deltas) : null;
}

async function waitForVisualSettle(page, settleConfig) {
  const startedAt = nodePerformance.now();
  let previous = await sampleLandmarks(page);
  let stableSamples = 0;
  const samples = [];
  while (nodePerformance.now() - startedAt < settleConfig.maxWaitMs) {
    await sleep(settleConfig.sampleEveryMs);
    const current = await sampleLandmarks(page);
    const maxCornerDeltaCssPx = maximumLandmarkDelta(previous, current);
    samples.push({
      elapsedMs: nodePerformance.now() - startedAt,
      maxCornerDeltaCssPx,
      qaVelocity: current.qaState
        ? { x: current.qaState.velocityX ?? null, y: current.qaState.velocityY ?? null }
        : null,
    });
    if (maxCornerDeltaCssPx !== null && maxCornerDeltaCssPx <= settleConfig.maxCornerDeltaCssPx) stableSamples += 1;
    else stableSamples = 0;
    if (stableSamples >= settleConfig.stableSampleCount) {
      return { settled: true, elapsedMs: nodePerformance.now() - startedAt, samples };
    }
    previous = current;
  }
  return { settled: false, elapsedMs: nodePerformance.now() - startedAt, samples };
}

async function runPointerMatrix(page, profile, matrix, options) {
  const rows = [];
  const positions = options.positions || matrix.capture.pointerPositions;
  for (const pointer of positions) {
    const point = ndcToPoint(pointer.positionNdc, profile);
    const startedAt = nodePerformance.now();
    await page.mouse.move(point[0], point[1]);
    await sleep(matrix.capture.pointerSettleMs);
    const row = {
      id: pointer.id,
      positionNdc: pointer.positionNdc,
      pointCssPx: point,
      requestedSettleMs: matrix.capture.pointerSettleMs,
      actualElapsedMs: nodePerformance.now() - startedAt,
    };
    if (options.measure) row.landmarks = await sampleLandmarks(page);
    if (options.screenshotDirectory) {
      row.screenshot = await captureScreenshot(page, options.screenshotDirectory, `pointer-${pointer.id}`);
    }
    rows.push(row);
  }
  return rows;
}

async function runBlurResumeCycle(context, page, cdp, step) {
  await page.bringToFront();
  await cdp.send("Emulation.setFocusEmulationEnabled", { enabled: true });
  await sleep(100);
  const before = await page.evaluate(() => ({
    visibilityState: document.visibilityState,
    hasFocus: document.hasFocus(),
    eventIndex: window.__ILG_CONTROLLED_CAPTURE__?.events.length || 0,
  }));
  const controlPage = await context.newPage();
  await controlPage.goto("data:text/html,<title>ilg-capture-control</title>", { waitUntil: "domcontentloaded" });
  await controlPage.bringToFront();
  await cdp.send("Emulation.setFocusEmulationEnabled", { enabled: false });
  await sleep(100);
  const whileBlurred = await page.evaluate(() => ({
    visibilityState: document.visibilityState,
    hasFocus: document.hasFocus(),
  }));
  await sleep(step.hiddenMs);
  await controlPage.close();
  await page.bringToFront();
  await cdp.send("Emulation.setFocusEmulationEnabled", { enabled: true });
  await sleep(step.settleMs || 0);
  const after = await page.evaluate((eventIndex) => ({
    visibilityState: document.visibilityState,
    hasFocus: document.hasFocus(),
    events: (window.__ILG_CONTROLLED_CAPTURE__?.events || []).slice(eventIndex)
      .filter((event) => event.type === "blur" || event.type === "focus" || event.type === "visibilitychange"),
  }), before.eventIndex);
  const blur = after.events.find((event) => event.type === "blur");
  const focus = after.events.find((event) => event.type === "focus");
  return {
    delivery: "headed-browser-tab-focus-cycle-with-cdp-focus-state",
    hiddenMs: step.hiddenMs,
    settleMs: step.settleMs || 0,
    states: { before, whileBlurred, after: { ...after, events: undefined } },
    events: after.events,
    visibilityChanged: after.events.some((event) => event.type === "visibilitychange"),
    verified: before.hasFocus === true
      && whileBlurred.hasFocus === false
      && after.hasFocus === true
      && blur?.isTrusted === true
      && focus?.isTrusted === true,
  };
}

async function executeInputScript(context, page, cdp, profile, matrix, resolvedInput, options) {
  const rows = [];
  let lastReleaseAt = null;
  for (const step of resolvedInput.steps) {
    const startedAt = nodePerformance.now();
    const row = { id: step.id, type: step.type, startedAt: new Date().toISOString() };
    if (step.type === "pointer-move") {
      const point = ndcToPoint(step.positionNdc, profile);
      await page.mouse.move(point[0], point[1]);
      await sleep(step.settleMs || 0);
      row.delivery = "playwright-trusted-mouse";
      row.pointCssPx = point;
    } else if (step.type === "pointer-drag") {
      row.input = await timedMouseDrag(cdp, step);
    } else if (step.type === "pointer-drag-release") {
      row.input = await timedMouseDrag(cdp, step);
      lastReleaseAt = row.input.releasedAtMonotonicMs;
      row.releaseCheckpoints = [];
      const releaseCheckpointsMs = step.releaseSamplesMs || matrix.capture.releaseCheckpointsMs;
      for (const checkpointMs of releaseCheckpointsMs) {
        await sleep(lastReleaseAt + checkpointMs - nodePerformance.now());
        const checkpoint = {
          requestedElapsedMs: checkpointMs,
          actualElapsedMs: nodePerformance.now() - lastReleaseAt,
        };
        if (options.measure) checkpoint.landmarks = await sampleLandmarks(page);
        if (options.screenshotDirectory) {
          checkpoint.screenshot = await captureScreenshot(page, options.screenshotDirectory, `flick-${checkpointMs}ms`);
        }
        row.releaseCheckpoints.push(checkpoint);
      }
      if (options.measure) {
        const settle = {
          ...matrix.capture.settle,
          maxWaitMs: step.settle?.maxWaitMs || matrix.capture.settle.maxWaitMs,
          stableSampleCount: step.settle?.stableFrames || matrix.capture.settle.stableSampleCount,
          maxCornerDeltaCssPx: step.settle?.maxCenterDeltaCssPx || matrix.capture.settle.maxCornerDeltaCssPx,
        };
        row.settle = await waitForVisualSettle(page, settle);
        if (options.screenshotDirectory) {
          row.settledScreenshot = await captureScreenshot(page, options.screenshotDirectory, "flick-settled");
        }
      }
    } else if (step.type === "wait") {
      const remaining = lastReleaseAt === null
        ? step.durationMs
        : Math.max(0, step.durationMs - (nodePerformance.now() - lastReleaseAt));
      await sleep(remaining);
      row.requestedDurationMs = step.durationMs;
      row.waitedMs = remaining;
      row.measuredFromLastRelease = lastReleaseAt !== null;
    } else if (step.type === "wheel" && step.deltaMode === 0) {
      row.input = await dispatchTrustedPixelWheel(
        page,
        cdp,
        step,
        options.wheelCalibration,
        matrix.capture.validation.wheelDeltaToleranceCssPx,
      );
    } else if (step.type === "wheel" && step.deltaMode === 1) {
      row.input = await dispatchSyntheticLineWheel(page, step);
    } else if (step.type === "touch-drag-release") {
      const touchCalibration = await calibrateTrustedTouch(page, cdp, profile);
      row.input = await timedTouchDrag(page, cdp, step, profile, touchCalibration);
      lastReleaseAt = row.input.releasedAtMonotonicMs;
    } else if (step.type === "viewport-resize") {
      const before = page.viewportSize();
      await page.setViewportSize({ width: step.to.width, height: step.to.height });
      await sleep(step.settleMs || 0);
      row.viewport = { before, resized: page.viewportSize() };
      if (options.screenshotDirectory) {
        row.resizedScreenshot = await captureScreenshot(page, options.screenshotDirectory, "resize");
      }
      await page.setViewportSize({ width: profile.width, height: profile.height });
      await sleep(step.settleMs || 0);
      row.viewport.restored = page.viewportSize();
    } else if (step.type === "visibility-cycle") {
      row.input = await runBlurResumeCycle(context, page, cdp, step);
    } else {
      row.unsupported = true;
    }
    if (options.measure && !row.releaseCheckpoints) row.landmarks = await sampleLandmarks(page);
    if (options.screenshotDirectory && !["pointer-drag-release", "viewport-resize"].includes(step.type)) {
      row.screenshot = await captureScreenshot(page, options.screenshotDirectory, `step-${step.id}`);
    }
    row.actualElapsedMs = nodePerformance.now() - startedAt;
    rows.push(row);
  }
  return rows;
}

function validateInteraction(sequence, restLandmarks, telemetry, matrix) {
  const failures = [];
  const tolerance = matrix.capture.validation.timedInputToleranceFraction;
  const minimumTrackedCardCorners = matrix.capture.validation.minimumTrackedCardCorners;
  const minimumTrackedCards = Math.ceil(minimumTrackedCardCorners / 4);
  const landmarkSamples = [restLandmarks];
  const timedTypes = new Set(["pointer-drag", "pointer-drag-release", "touch-drag-release"]);

  for (const row of sequence) {
    if (row.unsupported) failures.push(`${row.id}: unsupported input step`);
    if (timedTypes.has(row.type)) {
      const requested = row.input?.requestedDurationMs;
      const actual = row.input?.actualDurationMs;
      if (!Number.isFinite(requested) || !Number.isFinite(actual)
        || Math.abs(actual - requested) / requested > tolerance) {
        failures.push(`${row.id}: timed input ${actual ?? "missing"}ms for ${requested ?? "missing"}ms request`);
      }
    }
    if (row.type === "wheel" && row.input?.delivery === "cdp-trusted-pixel-wheel-calibrated"
      && row.input.verified !== true) {
      failures.push(`${row.id}: trusted pixel wheel delta was not reproduced`);
    }
    if (row.type === "visibility-cycle" && row.input?.verified !== true) {
      failures.push(`${row.id}: browser blur/resume was not verified`);
    }
    if (row.landmarks) landmarkSamples.push(row.landmarks);
    for (const checkpoint of row.releaseCheckpoints || []) {
      if (checkpoint.landmarks) landmarkSamples.push(checkpoint.landmarks);
    }
  }

  const insufficient = landmarkSamples.filter((sample) => (sample?.cards?.length || 0) < minimumTrackedCards);
  if (insufficient.length) {
    failures.push(`${insufficient.length} landmark samples tracked fewer than ${minimumTrackedCards} cards`);
  }
  const trustedEventTypes = [...new Set(telemetry.events.filter((event) => event.isTrusted).map((event) => event.type))];
  for (const required of ["pointerdown", "pointerup", "wheel", "touchstart", "touchend", "blur", "focus"]) {
    if (!trustedEventTypes.includes(required)) failures.push(`missing trusted ${required} event`);
  }
  const qaSamples = landmarkSamples.map((sample) => sample?.qaState).filter(Boolean);
  return {
    passed: failures.length === 0,
    failures,
    timedInputToleranceFraction: tolerance,
    minimumTrackedCards,
    minimumTrackedCardCorners,
    landmarkSampleCount: landmarkSamples.length,
    minimumObservedTrackedCards: Math.min(...landmarkSamples.map((sample) => sample?.cards?.length || 0)),
    minimumObservedTrackedCardCorners: Math.min(...landmarkSamples.map((sample) => (sample?.cards?.length || 0) * 4)),
    trustedEventTypes,
    coverage: {
      tileCornersAndCenters: "derived-from-dom",
      gridOffset: qaSamples.some((state) => Number.isFinite(state.scrollX) && Number.isFinite(state.scrollY))
        ? "qa-hook"
        : "unavailable",
      rotation: qaSamples.some((state) => Number.isFinite(state.rotX) && Number.isFinite(state.rotY))
        ? "qa-hook"
        : "unavailable",
      cameraPosition: qaSamples.some((state) => Number.isFinite(state.camX) && Number.isFinite(state.camY))
        ? "qa-hook"
        : "unavailable",
      highlightCentroid: landmarkSamples.some((sample) => sample?.highlightCentroid)
        ? "qa-hook"
        : "unavailable",
      releaseVelocity: qaSamples.some((state) => Number.isFinite(state.velocityX) && Number.isFinite(state.velocityY))
        ? "qa-hook"
        : "derived-from-landmarks-only",
    },
  };
}

function collectScreenshots(value, output = []) {
  if (Array.isArray(value)) {
    for (const item of value) collectScreenshots(item, output);
  } else if (value && typeof value === "object") {
    if (value.path && value.sha256 && String(value.path).endsWith(".png")) {
      output.push({ id: value.id || null, sha256: value.sha256 });
    }
    for (const child of Object.values(value)) collectScreenshots(child, output);
  }
  return output;
}

function probeVideo(file) {
  const result = spawnSync("ffprobe", [
    "-v", "error",
    "-show_entries", "format=duration,size:stream=codec_name,width,height,avg_frame_rate,r_frame_rate,pix_fmt,color_space,color_transfer,color_primaries",
    "-of", "json",
    file,
  ], { encoding: "utf8" });
  if (result.status !== 0) return { available: false, error: "ffprobe failed" };
  const data = JSON.parse(result.stdout);
  return { available: true, streams: data.streams || [], format: data.format || {} };
}

async function finishVideo(page, context, destination) {
  const video = page.video();
  await context.close();
  if (!video) return null;
  await ensureDirectory(path.dirname(destination));
  await video.saveAs(destination);
  return {
    path: toRepositoryPath(destination),
    sha256: await sha256File(destination),
    probe: probeVideo(destination),
    use: "human QA only; not frame-time or motion telemetry",
  };
}

async function captureIdentity(browser, site, profile, matrix, directories, sharedEnvironment) {
  const passDirectory = await ensureDirectory(path.join(directories.siteProfile, "identity"));
  const context = await newCaptureContext(browser, profile);
  const page = await context.newPage();
  const network = await createNetworkRecorder(context, page);
  const readiness = await waitForPageReady(page, site, matrix);
  await page.waitForTimeout(matrix.capture.restMs);
  const environment = await collectPageEnvironment(page);
  assertRealGpu(environment, site);
  assertCaptureProfile(environment, profile, matrix);
  const screenshot = await captureScreenshot(page, passDirectory, "rest-5s");
  const domSnapshot = await captureDomSnapshot(network.cdp);
  const domSnapshotFile = path.join(passDirectory, "dom-snapshot.raw.json");
  await writeJsonFile(domSnapshotFile, domSnapshot);
  const networkData = network.snapshot();
  const networkFile = path.join(passDirectory, "network.raw.json");
  await writeJsonFile(networkFile, networkData.raw);
  const raw = {
    schemaVersion: 1,
    pass: "identity",
    capturedAt: new Date().toISOString(),
    site,
    profile,
    readiness,
    host: sharedEnvironment.host,
    browser: sharedEnvironment.browser,
    environment,
    screenshot,
    domSnapshot: {
      path: toRepositoryPath(domSnapshotFile),
      sha256: sha256Value(domSnapshot),
    },
    network: {
      path: toRepositoryPath(networkFile),
      ...networkData.summary,
    },
  };
  const rawFile = path.join(passDirectory, "identity.raw.json");
  await writeJsonFile(rawFile, raw);
  const rawManifestSha256 = await sha256File(rawFile);
  await network.cdp.detach().catch(() => {});
  await context.close();
  return {
    status: "PASS",
    capturedAt: raw.capturedAt,
    finalUrl: readiness.finalUrl,
    sourceIdentity: readiness.localSourceIdentity,
    environment: sanitizedEnvironment(environment),
    screenshot: { sha256: screenshot.sha256 },
    domSnapshotSha256: raw.domSnapshot.sha256,
    network: networkData.summary,
    rawManifestSha256,
  };
}

async function captureInteraction(browser, site, profile, matrix, resolvedInput, directories) {
  const passDirectory = await ensureDirectory(path.join(directories.siteProfile, "interaction"));
  const videoTemp = await ensureDirectory(path.join(passDirectory, "video-tmp"));
  const context = await newCaptureContext(browser, profile, videoTemp);
  const page = await context.newPage();
  const network = await createNetworkRecorder(context, page);
  const readiness = await waitForPageReady(page, site, matrix);
  await page.waitForTimeout(matrix.capture.restMs);
  const wheelCalibration = await calibrateTrustedWheel(page, network.cdp);
  await resetTelemetry(page);
  const rest = await captureScreenshot(page, passDirectory, "rest-5s");
  const restLandmarks = await sampleLandmarks(page);
  const scriptedPointerIds = new Set(resolvedInput.steps
    .filter((step) => step.type === "pointer-move")
    .map((step) => step.id.replace(/^pointer-/, "")));
  const missingPointerPositions = matrix.capture.pointerPositions
    .filter((pointer) => !scriptedPointerIds.has(pointer.id));
  const pointerMatrix = missingPointerPositions.length
    ? await runPointerMatrix(page, profile, matrix, {
        measure: true,
        screenshotDirectory: passDirectory,
        positions: missingPointerPositions,
      })
    : [];
  const sequence = await executeInputScript(context, page, network.cdp, profile, matrix, resolvedInput, {
    measure: true,
    screenshotDirectory: passDirectory,
    wheelCalibration,
  });
  const telemetry = await readTelemetry(page);
  const validation = validateInteraction(sequence, restLandmarks, telemetry, matrix);
  const networkData = network.snapshot();
  const networkFile = path.join(passDirectory, "network.raw.json");
  await writeJsonFile(networkFile, networkData.raw);
  const telemetryFile = path.join(passDirectory, "telemetry.raw.json");
  await writeJsonFile(telemetryFile, telemetry);
  await network.cdp.detach().catch(() => {});
  const videoDestination = path.join(passDirectory, "video", "interaction.webm");
  const video = await finishVideo(page, context, videoDestination);
  const raw = {
    schemaVersion: 1,
    pass: "interaction",
    capturedAt: new Date().toISOString(),
    site,
    profile,
    readiness,
    effectiveInput: resolvedInput,
    effectiveInputSha256: sha256Value(resolvedInput),
    rest,
    restLandmarks,
    pointerMatrix,
    sequence,
    validation,
    telemetry: {
      path: toRepositoryPath(telemetryFile),
      sha256: sha256Value(telemetry),
      rafIntervalMs: summarizeRafTimestamps(telemetry.raf),
    },
    network: {
      path: toRepositoryPath(networkFile),
      ...networkData.summary,
    },
    video,
  };
  const rawFile = path.join(passDirectory, "interaction.raw.json");
  await writeJsonFile(rawFile, raw);
  const screenshots = collectScreenshots(raw);
  if (!validation.passed) {
    throw new Error(`INTERACTION_VALIDATION_GATE: ${validation.failures.join("; ")}`);
  }
  return {
    status: "PASS",
    capturedAt: raw.capturedAt,
    effectiveInputSha256: raw.effectiveInputSha256,
    screenshotCount: screenshots.length,
    screenshotSetSha256: sha256Value(screenshots),
    landmarkSampleCount: pointerMatrix.length + sequence.length + 1,
    validation,
    telemetrySha256: raw.telemetry.sha256,
    network: networkData.summary,
    video: video ? { sha256: video.sha256, probe: video.probe, use: video.use } : null,
    rawManifestSha256: await sha256File(rawFile),
  };
}

async function capturePerformance(browser, site, profile, matrix, resolvedInput, directories) {
  const passDirectory = await ensureDirectory(path.join(directories.siteProfile, "performance"));
  const context = await newCaptureContext(browser, profile);
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  const readiness = await waitForPageReady(page, site, matrix);
  await page.waitForTimeout(matrix.capture.restMs);
  const wheelCalibration = await calibrateTrustedWheel(page, cdp);

  await resetTelemetry(page);
  await page.waitForTimeout(matrix.capture.performance.idleDurationMs);
  const idleTelemetry = await readTelemetry(page);

  await resetTelemetry(page);
  const sequence = await executeInputScript(context, page, cdp, profile, matrix, resolvedInput, {
    measure: false,
    screenshotDirectory: null,
    wheelCalibration,
  });
  const interactionTelemetry = await readTelemetry(page);
  await cdp.detach().catch(() => {});
  await context.close();

  const raw = {
    schemaVersion: 1,
    pass: "performance",
    capturedAt: new Date().toISOString(),
    site,
    profile,
    readiness,
    warning: "RAF interval telemetry is browser cadence, not GPU execution time.",
    effectiveInputSha256: sha256Value(resolvedInput),
    sequence,
    idle: {
      rafTimestamps: idleTelemetry.raf,
      longTasks: idleTelemetry.longTasks,
      rafIntervalMs: summarizeRafTimestamps(idleTelemetry.raf),
    },
    interaction: {
      rafTimestamps: interactionTelemetry.raf,
      longTasks: interactionTelemetry.longTasks,
      inputEvents: interactionTelemetry.events,
      rafIntervalMs: summarizeRafTimestamps(interactionTelemetry.raf),
    },
  };
  const rawFile = path.join(passDirectory, "performance.raw.json");
  await writeJsonFile(rawFile, raw);
  return {
    status: "PASS",
    capturedAt: raw.capturedAt,
    metricName: "rafIntervalMs",
    metricMeaning: "browser requestAnimationFrame interval; not GPU execution time",
    gpuExecutionTimeMeasured: false,
    idle: raw.idle.rafIntervalMs,
    interaction: raw.interaction.rafIntervalMs,
    rawManifestSha256: await sha256File(rawFile),
  };
}

function sanitizedBrowserEnvironment(environment) {
  return {
    playwrightBrowserVersion: environment.playwrightBrowserVersion,
    product: environment.cdp?.product || null,
    protocolVersion: environment.cdp?.protocolVersion || null,
    revision: environment.cdp?.revision || null,
    jsVersion: environment.cdp?.jsVersion || null,
  };
}

function assertSanitizedManifest(value) {
  const walk = (current, trail) => {
    if (Array.isArray(current)) {
      current.forEach((item, index) => walk(item, `${trail}[${index}]`));
      return;
    }
    if (current && typeof current === "object") {
      for (const [key, child] of Object.entries(current)) walk(child, `${trail}.${key}`);
      return;
    }
    if (typeof current !== "string") return;
    if (/file:\/\/|\/Users\/|\/var\/folders\/|\/private\/var\//.test(current)) {
      throw new Error(`Sanitized manifest contains an absolute private path at ${trail}`);
    }
    if (MEDIA_URL_PATTERN.test(current)) {
      throw new Error(`Sanitized manifest contains a full media URL at ${trail}`);
    }
  };
  walk(value, "manifest");
}

function captureErrorCode(error) {
  const message = String(error);
  if (message.includes("REAL_GPU_GATE")) return "REAL_GPU_UNAVAILABLE";
  if (message.includes("LOCAL_SOURCE_ATTESTATION_GATE") || message.includes("LOCAL_COMMIT_GATE")) {
    return "LOCAL_SOURCE_IDENTITY_FAILED";
  }
  if (message.includes("CAPTURE_PROFILE_GATE")) return "CAPTURE_PROFILE_MISMATCH";
  if (message.includes("INTERACTION_VALIDATION_GATE")) return "INPUT_REPLAY_INVALID";
  return "CAPTURE_FAILED";
}

function captureDirectories(site, profile, captureId, matrix) {
  const siteRoot = path.resolve(REPO_ROOT, site.outputDirectory);
  const relative = path.relative(PRIVATE_REFERENCE_ROOT, siteRoot);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error("Capture output must remain under qa-v4/reference");
  }
  return {
    siteProfile: path.join(siteRoot, captureId, profile.id),
    sanitizedRoot: path.join(REPO_ROOT, matrix.privacy.sanitizedManifestDirectory, captureId),
  };
}

async function localCommitGate(sites) {
  const local = sites.find((site) => site.id === "local");
  if (!local) return null;
  if (!process.env.ILG_LOCAL_SOURCE_DIR?.trim()) {
    throw new Error("LOCAL_COMMIT_GATE: ILG_LOCAL_SOURCE_DIR is required when capturing the local baseline");
  }
  const sourceDirectory = path.resolve(process.env.ILG_LOCAL_SOURCE_DIR.trim());
  await access(sourceDirectory);
  const sourceCommit = execText("git", ["rev-parse", "HEAD"], { cwd: sourceDirectory });
  const sourceTree = execText("git", ["rev-parse", "HEAD^{tree}"], { cwd: sourceDirectory });
  const trackedStatus = execText("git", ["status", "--porcelain", "--untracked-files=no"], { cwd: sourceDirectory });
  if (sourceCommit !== local.expectedSourceCommit || sourceTree !== local.expectedSourceTree || trackedStatus) {
    throw new Error(
      `LOCAL_COMMIT_GATE: expected ${local.expectedSourceCommit}/${local.expectedSourceTree}, `
      + `observed ${sourceCommit}/${sourceTree}, trackedClean=${trackedStatus === ""}`,
    );
  }
  return { sourceCommit, sourceTree, trackedTreeClean: true };
}

async function captureCell(browser, site, profile, matrix, inputScript, sharedEnvironment, captureId) {
  const directories = captureDirectories(site, profile, captureId, matrix);
  await ensureDirectory(directories.siteProfile);
  const resolvedInput = resolveInputScript(inputScript, profile, matrix);
  const identity = await captureIdentity(browser, site, profile, matrix, directories, sharedEnvironment);
  const interaction = await captureInteraction(browser, site, profile, matrix, resolvedInput, directories);
  const performance = await capturePerformance(browser, site, profile, matrix, resolvedInput, directories);
  return {
    status: "PASS",
    referenceClass: site.referenceClass,
    url: site.url,
    sourceCommit: site.sourceCommitRequired ? site.expectedSourceCommit : null,
    profile: {
      width: profile.width,
      height: profile.height,
      browserDpr: profile.browserDpr,
      expectedCanvasDpr: profile.expectedCanvasDpr,
      mobile: profile.mobile,
    },
    effectiveInputSha256: sha256Value(resolvedInput),
    identity,
    interaction,
    performance,
  };
}

async function main() {
  const options = parseArguments(process.argv.slice(2));
  const matrix = await readJson(MATRIX_PATH);
  if (matrix.browser.headless !== false) throw new Error("Controlled capture requires headed Chrome");
  const inputPath = path.resolve(REPO_ROOT, matrix.inputScript);
  const inputScript = JSON.parse(await readFile(inputPath, "utf8"));
  const selectedProfiles = options.profile
    ? matrix.profiles.filter((profile) => profile.id === options.profile)
    : matrix.profiles;
  const configuredSites = matrix.sites.map((site) => {
    if (site.id !== "local" || !process.env.ILG_LOCAL_URL?.trim()) return site;
    const url = new URL(process.env.ILG_LOCAL_URL.trim());
    if (!url.searchParams.has("optics")) url.searchParams.set("optics", "v3");
    if (!url.searchParams.has("qa")) url.searchParams.set("qa", "1");
    return { ...site, url: url.href };
  });
  const selectedSites = options.site
    ? configuredSites.filter((site) => site.id === options.site)
    : configuredSites;
  if (!selectedProfiles.length) throw new Error(`Unknown profile: ${options.profile}`);
  if (!selectedSites.length) throw new Error(`Unknown site: ${options.site}`);
  const localSourceIdentity = await localCommitGate(selectedSites);

  const sanitizedRoot = path.join(REPO_ROOT, matrix.privacy.sanitizedManifestDirectory, options.captureId);
  const sanitizedFile = path.join(sanitizedRoot, "manifest.sanitized.json");
  try {
    await access(sanitizedFile);
    throw new Error(`CAPTURE_ID_EXISTS: ${options.captureId} already has evidence; use a new attempt id`);
  } catch (error) {
    if (!String(error).includes("ENOENT")) throw error;
  }

  const browser = await chromium.launch({
    channel: matrix.browser.channel,
    headless: false,
    args: matrix.browser.launchArgs,
  });
  const sharedEnvironment = {
    host: hostEnvironment(),
    browser: await browserEnvironment(browser),
  };
  await ensureDirectory(sanitizedRoot);
  const manifest = {
    $schema: "qa-v4/reference/controlled-reference.schema.json",
    schemaVersion: 1,
    generator: SCRIPT_VERSION,
    captureId: options.captureId,
    startedAt: new Date().toISOString(),
    finishedAt: null,
    matrix: {
      path: "qa-v4/reference/capture-matrix.json",
      sha256: await sha256File(MATRIX_PATH),
    },
    inputScript: {
      path: matrix.inputScript,
      fileSha256: await sha256File(inputPath),
      canonicalSha256: sha256Value(inputScript),
    },
    host: sharedEnvironment.host,
    browser: sanitizedBrowserEnvironment(sharedEnvironment.browser),
    harness: {
      baseCommit: execText("git", ["rev-parse", "HEAD"]),
      captureScriptSha256: await sha256File(SCRIPT_PATH),
      captureScriptVersion: SCRIPT_VERSION,
    },
    launch: {
      headed: true,
      channel: matrix.browser.channel,
      args: matrix.browser.launchArgs,
      realGpuRequired: true,
    },
    localSourceIdentity,
    profiles: {},
    errors: [],
  };

  try {
    for (const profile of selectedProfiles) {
      manifest.profiles[profile.id] = {};
      for (const site of selectedSites) {
        try {
          manifest.profiles[profile.id][site.id] = await captureCell(
            browser,
            site,
            profile,
            matrix,
            inputScript,
            sharedEnvironment,
            options.captureId,
          );
        } catch (error) {
          const rawErrorFile = path.join(
            captureDirectories(site, profile, options.captureId, matrix).siteProfile,
            "capture-error.raw.json",
          );
          await writeJsonFile(rawErrorFile, {
            capturedAt: new Date().toISOString(),
            error: String(error),
            stack: error instanceof Error ? error.stack : null,
          });
          manifest.profiles[profile.id][site.id] = {
            status: "BLOCKED",
            referenceClass: site.referenceClass,
            url: site.url,
            code: captureErrorCode(error),
            rawErrorSha256: await sha256File(rawErrorFile),
          };
          manifest.errors.push({ profile: profile.id, site: site.id, code: manifest.profiles[profile.id][site.id].code });
        }
        manifest.finishedAt = new Date().toISOString();
        assertSanitizedManifest(manifest);
        await writeJsonFile(sanitizedFile, stable(manifest));
      }
    }
  } finally {
    await browser.close();
  }

  manifest.finishedAt = new Date().toISOString();
  manifest.status = manifest.errors.length ? "BLOCKED" : "PASS";
  assertSanitizedManifest(manifest);
  await writeJsonFile(sanitizedFile, stable(manifest));
  console.log(JSON.stringify({
    status: manifest.status,
    captureId: manifest.captureId,
    sanitizedManifest: toRepositoryPath(sanitizedFile),
    errors: manifest.errors,
  }, null, 2));
  if (manifest.errors.length) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
