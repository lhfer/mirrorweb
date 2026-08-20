#!/usr/bin/env node
/**
 * Proves Stage H changed no visual output.
 *
 * The optics bench renders a deterministic checker scene with no video, so two
 * builds that render identically must produce byte-identical frames. Any
 * difference here would mean Stage H touched the render path.
 */
import { spawn } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const port = Number(process.argv.find((a) => a.startsWith("--port="))?.slice(7) ?? 5330);
const out = process.argv.find((a) => a.startsWith("--out="))?.slice(6);
const label = process.argv.find((a) => a.startsWith("--label="))?.slice(8) ?? "unlabelled";
if (!out) throw new Error("--out is required");

function startPreview() {
  const child = spawn("npx", ["vite", "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"] });
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("preview did not start")), 30_000);
    const onData = (c) => { if (String(c).includes("Local:")) { clearTimeout(timer); resolve(child); } };
    child.stdout.on("data", onData); child.stderr.on("data", onData); child.once("error", reject);
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let preview, browser;
try {
  preview = await startPreview();
  browser = await chromium.launch({ channel: "chrome", headless: process.env.ILG_CAPTURE_HEADLESS === "1",
    args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const shots = {};
  // reset() restores the bench default, so the ?optics= value in the URL does
  // not survive it and both passes render the same default view. The labels are
  // kept as "passA"/"passB" rather than v4/v3 so nothing implies otherwise; the
  // comparison this script exists for is build-vs-build, which is unaffected.
  for (const optics of ["passA", "passB"]) {
    await page.goto(`http://127.0.0.1:${port}/glass-lab-v4?qa=1`, { waitUntil: "load" });
    await page.waitForFunction(() => window.__ILG_QA__?.ready === true, undefined, { timeout: 90_000 });
    await sleep(2500);
    // reset() and pause() both predate Stage H, so the same pin works on either
    // build. Without them the bench animates and two runs of ONE build already
    // differ, which would make a hash comparison meaningless.
    await page.evaluate(() => { window.__ILG_QA__.reset(); window.__ILG_QA__.setPointer(0, 0); });
    await sleep(1200);
    await page.evaluate(() => window.__ILG_QA__.pause());
    await sleep(600);
    const buf = await page.screenshot();
    const buf2 = await (async () => { await sleep(900); return page.screenshot(); })();
    shots[`${optics}-selfStable`] = createHash("sha256").update(buf).digest("hex") === createHash("sha256").update(buf2).digest("hex");
    shots[optics] = createHash("sha256").update(buf).digest("hex");
    await mkdir(path.dirname(out), { recursive: true });
    await writeFile(out.replace(/\.json$/, `-${label}-${optics}.png`), buf);
  }
  await writeFile(out, `${JSON.stringify({ label, page: "/glass-lab-v4 (deterministic checker scene, no video)", hashes: shots }, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ label, ...shots }));
  await context.close();
} finally { await browser?.close(); preview?.kill("SIGTERM"); }
