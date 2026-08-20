#!/usr/bin/env node
/** Stage H smoke test: does setMediaTimeAndFreeze actually stop the clips, and
 *  is a media-only render reproducible across two independent page loads? */
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const port = Number(process.argv.find((a) => a.startsWith("--port="))?.slice(7) ?? 5320);
const url = process.argv.find((a) => a.startsWith("--url="))?.slice(6) ?? `/?optics=v4&qa=1`;
const mediaTime = Number(process.argv.find((a) => a.startsWith("--time="))?.slice(7) ?? 2.0);

function startPreview() {
  const child = spawn("npx", ["vite", "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"] });
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("preview did not start")), 30_000);
    const onData = (c) => { if (String(c).includes("Local:")) { clearTimeout(timer); resolve(child); } };
    child.stdout.on("data", onData); child.stderr.on("data", onData); child.once("error", reject);
  });
}

let preview, browser;
try {
  preview = await startPreview();
  browser = await chromium.launch({ channel: "chrome", headless: process.env.ILG_CAPTURE_HEADLESS === "1",
    args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

  const run = async (label) => {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${port}${url}`, { waitUntil: "load" });
    await page.waitForFunction(() => window.__ILG_QA__?.getState()?.ready === true, undefined, { timeout: 90_000 });
    await page.evaluate(() => { window.__ILG_QA__.reset(); window.__ILG_QA__.setPointer(0, 0); });
    await page.waitForTimeout(1500);

    const freeze = await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), mediaTime);
    await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: false, media: true, labels: false }));
    await page.waitForTimeout(400);
    const mediaOnly = await page.screenshot();
    await page.waitForTimeout(1200);
    const mediaOnlyAgain = await page.screenshot();
    const after = await page.evaluate(() => window.__ILG_QA__.getMediaState());
    await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: true, media: true, labels: true }));
    await context.close();
    const h = (b) => createHash("sha256").update(b).digest("hex").slice(0, 16);
    return { label, freeze, mediaOnlyHash: h(mediaOnly), stableUnderTime: h(mediaOnly) === h(mediaOnlyAgain), after };
  };

  const a = await run("load-1");
  const b = await run("load-2");
  console.log(JSON.stringify({
    frozen: a.freeze.frozen && b.freeze.frozen,
    maxSeekError: [a.freeze.maxSeekError, b.freeze.maxSeekError],
    maxDrift: [a.freeze.maxDrift, b.freeze.maxDrift],
    allPaused: [a.freeze.allPaused, b.freeze.allPaused],
    frameWait: a.freeze.videos.map((v) => v.frameWait),
    currentTimes: a.freeze.videos.map((v) => Number(v.currentTime.toFixed(5))),
    mediaTimesRun1: a.freeze.videos.map((v) => v.mediaTime),
    mediaTimesRun2: b.freeze.videos.map((v) => v.mediaTime),
    presentedRun1: a.freeze.videos.map((v) => v.presentedFrames),
    presentedRun2: b.freeze.videos.map((v) => v.presentedFrames),
    stableUnderTime: [a.stableUnderTime, b.stableUnderTime],
    mediaOnlyHashMatchAcrossLoads: a.mediaOnlyHash === b.mediaOnlyHash,
    hashes: [a.mediaOnlyHash, b.mediaOnlyHash],
  }, null, 2));
} finally { await browser?.close(); preview?.kill("SIGTERM"); }
