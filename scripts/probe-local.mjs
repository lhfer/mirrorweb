import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const OUT = path.resolve("artifacts/local/probe");
fs.mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({
  headless: false,
  channel: "chrome",
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const logs = [];
page.on("console", (msg) => logs.push({ type: msg.type(), text: msg.text() }));
page.on("pageerror", (err) => logs.push({ type: "pageerror", text: String(err) }));
await page.goto("http://127.0.0.1:5280", { waitUntil: "domcontentloaded", timeout: 30000 });
await page.screenshot({ path: path.join(OUT, "01-open.png") });
await page.waitForTimeout(8000);
await page.screenshot({ path: path.join(OUT, "02-after-8s.png") });
const state = await page.evaluate(() => ({
  title: document.title,
  text: document.body.innerText.slice(0, 400),
  canvases: [...document.querySelectorAll("canvas")].map((c) => ({
    w: c.width,
    h: c.height,
    css: c.getBoundingClientRect().toJSON(),
  })),
  qa: window.__LIQUID_GLASS_QA__ ? window.__LIQUID_GLASS_QA__.getState() : null,
  metrics: window.__LIQUID_GLASS_QA__ ? window.__LIQUID_GLASS_QA__.getMetrics() : null,
}));
fs.writeFileSync(path.join(OUT, "probe.json"), JSON.stringify({ logs, state }, null, 2));
console.log(JSON.stringify({ logs, state }, null, 2));
await browser.close();
