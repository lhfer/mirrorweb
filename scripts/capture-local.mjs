import path from "node:path";
import {
  LOCAL_URL,
  ROOT,
  VIEWPORTS,
  ensureDir,
  writeJson,
  launchChrome,
  newContext,
  attachCollectors,
  collectEnvironment,
  collectDom,
  screenshotState,
} from "./lib/capture-utils.mjs";

const OUT = path.join(ROOT, "artifacts", "local");
ensureDir(OUT);

async function waitForLocal(page) {
  await page.goto(LOCAL_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForFunction(() => window.__LIQUID_GLASS_QA__?.getState, { timeout: 45000 });
  await page.waitForTimeout(1200);
}

const browser = await launchChrome({ headless: false });
try {
  const summary = { startedAt: new Date().toISOString(), local: LOCAL_URL, viewports: {} };
  for (const key of ["A", "B", "C", "D", "E"]) {
    const viewport = VIEWPORTS[key];
    const dir = ensureDir(path.join(OUT, viewport.name));
    const context = await newContext(browser, viewport);
    const page = await context.newPage();
    attachCollectors(page);
    await waitForLocal(page);
    const states = [];
    states.push(await screenshotState(page, dir, "04-first-loaded-frame"));
    await page.waitForTimeout(1500);
    states.push(await screenshotState(page, dir, "06-rest-5s"));
    await page.mouse.move(viewport.width / 2, viewport.height / 2);
    states.push(await screenshotState(page, dir, "07-mouse-center"));
    await page.mouse.down();
    await page.mouse.move(viewport.width / 2 - 400, viewport.height / 2, { steps: 40 });
    states.push(await screenshotState(page, dir, "08-slow-drag-left-400"));
    await page.mouse.up();
    writeJson(path.join(dir, "environment.json"), await collectEnvironment(page));
    writeJson(path.join(dir, "dom.json"), await collectDom(page));
    writeJson(path.join(dir, "state.json"), await page.evaluate(() => window.__LIQUID_GLASS_QA__.getState()));
    writeJson(path.join(dir, "states.json"), states);
    summary.viewports[key] = states.map((s) => s.name);
    await context.close();
  }
  writeJson(path.join(OUT, "capture-summary.json"), summary);
  console.log(JSON.stringify(summary, null, 2));
} finally {
  await browser.close();
}
