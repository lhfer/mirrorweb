import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const dir = path.resolve("artifacts/local/A-1440x900-dpr1");
fs.mkdirSync(dir, { recursive: true });
const browser = await chromium.launch({
  headless: false,
  channel: "chrome",
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
});
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
await page.goto("http://127.0.0.1:5280/?qa=1", { waitUntil: "domcontentloaded" });
await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 45000 });
await page.evaluate(() => window.__LIQUID_GLASS_QA__.reset());
await page.waitForTimeout(800);
await page.screenshot({ path: path.join(dir, "06-rest-5s.png") });
const state = await page.evaluate(() => ({
  state: window.__LIQUID_GLASS_QA__.getState(),
  metrics: window.__LIQUID_GLASS_QA__.getMetrics(),
}));
fs.writeFileSync(path.join(dir, "state.json"), JSON.stringify(state, null, 2));
console.log(JSON.stringify({
  backend: state.state.backend,
  scroll: [state.state.scrollX, state.state.scrollY],
  fps: state.metrics.fps,
  draws: state.metrics.drawCalls,
  visible: state.state.landmarks.filter((item) => item.nx > 0 && item.nx < 1 && item.ny > 0 && item.ny < 1),
}, null, 2));
await browser.close();
