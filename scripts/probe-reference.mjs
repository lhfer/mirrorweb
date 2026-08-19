import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");
const OUT = path.join(ROOT, "artifacts", "reference", "probe");
fs.mkdirSync(OUT, { recursive: true });

const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";

const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const useChrome = fs.existsSync(chromePath);

const browser = await chromium.launch({
  headless: false,
  channel: useChrome ? "chrome" : undefined,
  args: [
    "--enable-unsafe-webgpu",
    "--enable-webgpu-developer-features",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
  ],
});

const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 1,
});

const page = await context.newPage();
const consoleMessages = [];
page.on("console", (msg) => {
  consoleMessages.push({ type: msg.type(), text: msg.text() });
});

const network = [];
page.on("response", async (res) => {
  try {
    const url = res.url();
    const headers = res.headers();
    network.push({
      url,
      status: res.status(),
      type: headers["content-type"] || "",
      size: Number(headers["content-length"] || 0),
      resourceType: res.request().resourceType(),
    });
  } catch {
    // ignore
  }
});

const startedAt = new Date().toISOString();
await page.goto(TARGET, { waitUntil: "domcontentloaded", timeout: 60000 });
await page.screenshot({ path: path.join(OUT, "01-just-opened.png") });

await page.waitForTimeout(8000);
await page.screenshot({ path: path.join(OUT, "after-8s.png") });

const info = await page.evaluate(async () => {
  const canvases = [...document.querySelectorAll("canvas")].map((c) => {
    const rect = c.getBoundingClientRect();
    return {
      cssWidth: rect.width,
      cssHeight: rect.height,
      bufferWidth: c.width,
      bufferHeight: c.height,
      style: c.getAttribute("style"),
      className: c.className,
      id: c.id,
    };
  });

  let webgpu = { available: false };
  try {
    if (navigator.gpu) {
      const adapter = await navigator.gpu.requestAdapter();
      if (adapter) {
        const info = adapter.info || {};
        webgpu = {
          available: true,
          vendor: info.vendor,
          architecture: info.architecture,
          device: info.device,
          description: info.description,
          isFallbackAdapter: adapter.isFallbackAdapter ?? null,
        };
      }
    }
  } catch (error) {
    webgpu = { available: false, error: String(error) };
  }

  const gl = document.createElement("canvas").getContext("webgl2");
  const debugInfo = gl && gl.getExtension("WEBGL_debug_renderer_info");
  const renderer = debugInfo
    ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL)
    : null;

  return {
    title: document.title,
    url: location.href,
    userAgent: navigator.userAgent,
    viewport: { w: innerWidth, h: innerHeight, dpr: devicePixelRatio },
    bodyText: document.body?.innerText?.slice(0, 2000) || "",
    htmlPreview: document.documentElement.outerHTML.slice(0, 8000),
    canvases,
    webgpu,
    webglRenderer: renderer,
    touchAction: getComputedStyle(document.documentElement).touchAction,
    overflow: {
      html: getComputedStyle(document.documentElement).overflow,
      body: getComputedStyle(document.body).overflow,
    },
    links: [...document.querySelectorAll("a")].map((a) => ({
      text: a.textContent?.trim(),
      href: a.href,
      rect: a.getBoundingClientRect().toJSON(),
    })),
    fonts: [...document.fonts].slice(0, 20).map((f) => ({
      family: f.family,
      status: f.status,
      weight: f.weight,
      style: f.style,
    })),
  };
});

const env = {
  capturedAt: startedAt,
  os: "macOS 27.0 (26A5378n)",
  gpu: "Apple M5 Max, 40 cores, Metal supported",
  chromeChannel: useChrome,
  consoleMessages,
  networkSummary: {
    count: network.length,
    byType: network.reduce((acc, item) => {
      acc[item.resourceType] = (acc[item.resourceType] || 0) + 1;
      return acc;
    }, {}),
    resources: network.map((item) => ({
      ...item,
      url: item.resourceType === "script" ? "[script omitted]" : item.url,
    })),
  },
  page: info,
};

fs.writeFileSync(path.join(OUT, "probe.json"), JSON.stringify(env, null, 2));
await page.screenshot({ path: path.join(OUT, "loaded-or-current.png"), fullPage: true });
await browser.close();
console.log(JSON.stringify({
  title: info.title,
  webgpu: info.webgpu,
  canvases: info.canvases,
  renderer: info.webglRenderer,
  links: info.links,
  networkCount: network.length,
}, null, 2));
