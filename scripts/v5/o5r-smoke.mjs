#!/usr/bin/env node
/**
 * O5R smoke: the three lanes boot, the new QA views produce a program, the
 * structural environment control actually removes the environment, and the
 * live matrices needed by the CPU replay are readable.
 *
 * Usage: o5r-smoke.mjs --local=<origin> [--out=<dir>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, out: path.join(REPO, "artifacts/optics-o5r/smoke") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }
await mkdir(opts.out, { recursive: true });

const CASES = [
  { name: "control", q: "opticalBody=current" },
  { name: "o5-clamped", q: "opticalBody=target-source" },
  { name: "o5r-unclamped", q: "opticalBody=target-source-unclamped" },
  { name: "o5r-env-off", q: "opticalBody=target-source-unclamped&environmentMode=off" },
  { name: "view-uv-unrefracted",
    q: "opticalBody=target-source-unclamped&bodyView=uv-unrefracted" },
  { name: "view-uv-refracted",
    q: "opticalBody=target-source-unclamped&bodyView=uv-refracted" },
  { name: "view-displacement",
    q: "opticalBody=target-source-unclamped&bodyView=refraction-displacement" },
  { name: "view-sdf-mask",
    q: "opticalBody=target-source-unclamped&bodyView=sdf-mask" },
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const rows = [];
for (const c of CASES) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(
    `${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&bodyFloorMode=current&${c.q}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(
    () => window.__ILG_QA__?.getState?.()?.ready === true, undefined,
    { timeout: 120000 });
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.pause(); qa.setOffset(0, 0); qa.setVelocity(0, 0); qa.jumpPointer(0, 0);
    qa.setRenderLayers({ labels: false });
    qa.renderOnce(); qa.renderOnce();
  });
  await page.waitForTimeout(400);
  const optics = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
  const truth = await page.evaluate(() => window.__ILG_QA__.getCardBodyTruth());
  const shot = path.join(opts.out, `${c.name}.png`);
  await page.screenshot({ path: shot });
  rows.push({
    case: c.name, query: c.q, errors: errors.length,
    firstError: errors[0] ?? null,
    opticalBody: optics.opticalBody, bodyView: optics.opticalBodyView,
    environmentMode: optics.environmentMode,
    envSampleClamped: optics.envSampleClamped,
    samples: optics.opticalBodySamples,
    cards: Array.isArray(truth.cards) ? truth.cards.length : null,
    hasCamera: Boolean(truth.camera),
    frame: truth.frame, derived: truth.derived,
    shot: path.basename(shot),
  });
  console.log(`${c.name.padEnd(22)} body=${optics.opticalBody} `
    + `view=${optics.opticalBodyView} env=${optics.environmentMode} `
    + `clamped=${optics.envSampleClamped} cards=${rows.at(-1).cards} `
    + `errors=${errors.length}`);
  await ctx.close();
}
await browser.close();
await writeFile(path.join(opts.out, "smoke.json"),
  JSON.stringify({ what: "O5R smoke", rows }, null, 1));
console.log(`-> ${opts.out}`);
