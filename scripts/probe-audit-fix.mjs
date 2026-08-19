import { chromium } from "playwright";
import { writeFileSync, mkdirSync } from "node:fs";

mkdirSync("qa/local/audit-fix", { recursive: true });

const browser = await chromium.launch({
  channel: "chrome",
  headless: false,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
});

async function shot(path, url, w = 1440, h = 900, dpr = 1, background) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: dpr });
  await page.goto("http://127.0.0.1:5280" + url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState()?.ready, { timeout: 60000 });
  await page.evaluate(() => {
    window.__LIQUID_GLASS_QA__.reset?.();
    window.__LIQUID_GLASS_QA__.setPointer?.(0, 0);
  });
  if (background) {
    await page.evaluate((kind) => window.__LIQUID_GLASS_QA__.setBackground?.(kind), background);
  }
  await page.waitForTimeout(500);
  await page.screenshot({ path, type: "png" });
  const facts = await page.evaluate(() => ({
    state: window.__LIQUID_GLASS_QA__.getState(),
    assets: window.__LIQUID_GLASS_QA__.getAssetState(),
    pool: window.__LIQUID_GLASS_QA__.getPoolState(),
    videos: document.querySelectorAll("video").length,
  }));
  await page.close();
  return facts;
}

const jobs = [
  { path: "qa/local/audit-fix/A-1440x900-dpr1-rest.png", url: "/?qa=1" },
  { path: "qa/local/audit-fix/A-coverage.png", url: "/?debug=coverage&qa=1" },
  { path: "qa/local/audit-fix/D-390x844-rest.png", url: "/?qa=1", w: 390, h: 844 },
  { path: "qa/local/audit-fix/lab-hlines.png", url: "/glass-lab?qa=1", background: "h-lines" },
  { path: "qa/local/audit-fix/lab-checker.png", url: "/glass-lab?qa=1", background: "checker" },
];

const summary = [];
for (const job of jobs) {
  const facts = await shot(job.path, job.url, job.w, job.h, 1, job.background);
  const inside = (facts.state.landmarks || []).filter(
    (item) => item.nx >= 0 && item.nx <= 1 && item.ny >= 0 && item.ny <= 1,
  ).length;
  summary.push({
    path: job.path,
    url: job.url,
    assets: facts.assets,
    pool: facts.pool,
    videos: facts.videos,
    glass: facts.state.glass,
    samplesScene: facts.state.samplesScene,
    tile: facts.state.tile,
    inside,
  });
  console.log("wrote", job.path, "videos", facts.videos, "media", facts.assets.media, "inside", inside);
}

writeFileSync("qa/local/audit-fix/probe.json", JSON.stringify(summary, null, 2));
await browser.close();
