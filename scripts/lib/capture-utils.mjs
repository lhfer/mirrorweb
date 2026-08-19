import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";

export const TARGET_URL = "https://infinite-liquid-glass.shader.se/?v=2";
export const LOCAL_URL = "http://127.0.0.1:5280";
export const ROOT = path.resolve(import.meta.dirname, "../..");

export const VIEWPORTS = {
  A: { name: "A-1440x900-dpr1", width: 1440, height: 900, dpr: 1, isMobile: false },
  B: { name: "B-1920x1080-dpr1", width: 1920, height: 1080, dpr: 1, isMobile: false },
  C: { name: "C-1440x900-dpr2", width: 1440, height: 900, dpr: 2, isMobile: false },
  D: { name: "D-390x844-mobile", width: 390, height: 844, dpr: 3, isMobile: true },
  E: { name: "E-844x390-mobile-land", width: 844, height: 390, dpr: 3, isMobile: true },
};

export function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

export function writeJson(file, data) {
  ensureDir(path.dirname(file));
  fs.writeFileSync(file, JSON.stringify(data, null, 2));
}

export async function launchChrome(options = {}) {
  return chromium.launch({
    headless: options.headless ?? false,
    channel: "chrome",
    args: [
      "--enable-unsafe-webgpu",
      "--enable-webgpu-developer-features",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
    ],
  });
}

export async function newContext(browser, viewport, extra = {}) {
  return browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: viewport.dpr,
    isMobile: viewport.isMobile,
    hasTouch: viewport.isMobile,
    recordVideo: extra.recordVideo,
  });
}

export function attachCollectors(page) {
  const consoleMessages = [];
  const network = [];
  const pageErrors = [];

  page.on("console", (msg) => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text(),
      time: new Date().toISOString(),
    });
  });
  page.on("pageerror", (error) => {
    pageErrors.push({ message: String(error), time: new Date().toISOString() });
  });
  page.on("response", (res) => {
    const resourceType = res.request().resourceType();
    network.push({
      url: resourceType === "script" ? "[script omitted]" : res.url(),
      status: res.status(),
      type: res.headers()["content-type"] || "",
      size: Number(res.headers()["content-length"] || 0),
      resourceType,
    });
  });

  return { consoleMessages, network, pageErrors };
}

export async function collectEnvironment(page) {
  return page.evaluate(async () => {
    let webgpu = { available: false };
    try {
      if (navigator.gpu) {
        const adapter = await navigator.gpu.requestAdapter();
        if (adapter) {
          const info = adapter.info || {};
          webgpu = {
            available: true,
            vendor: info.vendor || null,
            architecture: info.architecture || null,
            device: info.device || null,
            description: info.description || null,
            isFallbackAdapter: adapter.isFallbackAdapter ?? null,
          };
        }
      }
    } catch (error) {
      webgpu = { available: false, error: String(error) };
    }

    const gl = document.createElement("canvas").getContext("webgl2");
    const debugInfo = gl && gl.getExtension("WEBGL_debug_renderer_info");
    const webglRenderer = debugInfo
      ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL)
      : null;

    const frames = [];
    await new Promise((resolve) => {
      let last = performance.now();
      let count = 0;
      const tick = (now) => {
        frames.push(now - last);
        last = now;
        count += 1;
        if (count >= 40) resolve();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    const median = [...frames].sort((a, b) => a - b)[Math.floor(frames.length / 2)];

    return {
      url: location.href,
      title: document.title,
      userAgent: navigator.userAgent,
      language: navigator.language,
      hardwareConcurrency: navigator.hardwareConcurrency,
      deviceMemory: navigator.deviceMemory || null,
      viewport: {
        innerWidth: innerWidth,
        innerHeight: innerHeight,
        dpr: devicePixelRatio,
        screenWidth: screen.width,
        screenHeight: screen.height,
      },
      webgpu,
      webglRenderer,
      online: navigator.onLine,
      estimatedRefreshHz: Math.round(1000 / median),
      frameIntervalsMs: frames.slice(0, 12),
    };
  });
}

export async function collectDom(page) {
  return page.evaluate(() => {
    const styleOf = (el) => {
      if (!el) return null;
      const s = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return {
        tag: el.tagName,
        id: el.id,
        className: el.className,
        text: (el.innerText || "").slice(0, 240),
        href: el.href || null,
        rect: { x: r.x, y: r.y, w: r.width, h: r.height },
        fontFamily: s.fontFamily,
        fontSize: s.fontSize,
        fontWeight: s.fontWeight,
        letterSpacing: s.letterSpacing,
        lineHeight: s.lineHeight,
        color: s.color,
        background: s.background,
        borderRadius: s.borderRadius,
        padding: s.padding,
        margin: s.margin,
        zIndex: s.zIndex,
        pointerEvents: s.pointerEvents,
        mixBlendMode: s.mixBlendMode,
        opacity: s.opacity,
        position: s.position,
      };
    };

    const canvases = [...document.querySelectorAll("canvas")].map((c) => {
      const r = c.getBoundingClientRect();
      return {
        id: c.id,
        className: c.className,
        css: { w: r.width, h: r.height, x: r.x, y: r.y },
        buffer: { w: c.width, h: c.height },
        style: c.getAttribute("style"),
      };
    });

    return {
      htmlOverflow: getComputedStyle(document.documentElement).overflow,
      bodyOverflow: getComputedStyle(document.body).overflow,
      htmlTouchAction: getComputedStyle(document.documentElement).touchAction,
      bodyTouchAction: getComputedStyle(document.body).touchAction,
      bodyUserSelect: getComputedStyle(document.body).userSelect,
      overscrollBehavior: getComputedStyle(document.documentElement).overscrollBehavior,
      canvases,
      links: [...document.querySelectorAll("a")].map(styleOf),
      buttons: [...document.querySelectorAll("button")].map(styleOf),
      images: [...document.querySelectorAll("img")].map((img) => ({
        src: img.src.includes("shader.se") ? "[brand asset not copied]" : img.src,
        alt: img.alt,
        rect: img.getBoundingClientRect().toJSON(),
      })),
      overlayCandidates: [...document.querySelectorAll("body *")]
        .filter((el) => {
          const s = getComputedStyle(el);
          return (
            (s.position === "fixed" || s.position === "absolute") &&
            el.getBoundingClientRect().width > 8 &&
            (el.innerText || "").trim().length > 0
          );
        })
        .slice(0, 40)
        .map(styleOf),
      fonts: [...document.fonts].map((f) => ({
        family: f.family,
        weight: f.weight,
        style: f.style,
        status: f.status,
      })),
    };
  });
}

export async function waitForScene(page, timeoutMs = 45000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const state = await page.evaluate(() => {
      const text = document.body?.innerText || "";
      const percent = text.match(/(\d+)\s*%/);
      const canvas = document.querySelector("canvas");
      return {
        percent: percent ? Number(percent[1]) : null,
        hasCanvas: Boolean(canvas),
        textPreview: text.slice(0, 200),
      };
    });
    if (state.hasCanvas && (state.percent === null || state.percent >= 100)) {
      await page.waitForTimeout(1200);
      return { ready: true, ...state };
    }
    await page.waitForTimeout(120);
  }
  return { ready: false };
}

export async function screenshotState(page, dir, name, extra = {}) {
  ensureDir(dir);
  const file = path.join(dir, `${name}.png`);
  await page.screenshot({ path: file, type: "png" });
  return {
    name,
    file,
    time: new Date().toISOString(),
    viewport: await page.evaluate(() => ({
      w: innerWidth,
      h: innerHeight,
      dpr: devicePixelRatio,
    })),
    ...extra,
  };
}
