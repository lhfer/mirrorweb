#!/usr/bin/env node

/**
 * V5 foundation capture: layout states from the running local page.
 *
 * Drives offsets programmatically (setOffset), never through synthetic input,
 * so the frames compare layout at equal world state and are not contaminated by
 * the known-wrong dragGain. Media is frozen to a fixed timestamp so repeated
 * runs are byte-comparable.
 *
 * Usage:
 *   node scripts/v5/capture-layout.mjs --out=<dir> [--origin=http://127.0.0.1:5280]
 *                                      [--route=/?optics=v4] [--width=1440] [--height=900]
 *                                      [--states=rest,drag1,...] [--headless]
 */

import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

const options = {
  origin: "http://127.0.0.1:5280",
  route: "/?optics=v4",
  width: 1440,
  height: 900,
  dpr: 1,
  out: path.join(REPO_ROOT, "qa-v5/local"),
  headless: process.env.ILG_CAPTURE_HEADLESS === "1",
  mediaTime: 2,
  states: null,
};
for (const arg of process.argv.slice(2)) {
  if (arg.startsWith("--origin=")) options.origin = arg.slice(9);
  else if (arg.startsWith("--route=")) options.route = arg.slice(8);
  else if (arg.startsWith("--width=")) options.width = Number(arg.slice(8));
  else if (arg.startsWith("--height=")) options.height = Number(arg.slice(9));
  else if (arg.startsWith("--dpr=")) options.dpr = Number(arg.slice(6));
  else if (arg.startsWith("--out=")) options.out = path.resolve(REPO_ROOT, arg.slice(6));
  else if (arg.startsWith("--media-time=")) options.mediaTime = Number(arg.slice(13));
  else if (arg.startsWith("--states=")) options.states = arg.slice(9).split(",").filter(Boolean);
  else if (arg === "--headless") options.headless = true;
  else throw new Error(`Unknown argument: ${arg}`);
}

/**
 * Rest plus a five-sample slow-drag sweep. The drag samples are pure world
 * offsets, so the same list reproduces on any build regardless of input tuning.
 */
const STATES = [
  { id: "01-rest", offset: [0, 0] },
  { id: "02-drag-x-110", offset: [110, 0] },
  { id: "03-drag-x-220", offset: [220, 0] },
  { id: "04-drag-x-330", offset: [330, 0] },
  { id: "05-drag-x-440", offset: [440, 0] },
  { id: "06-drag-xy-260-180", offset: [260, 180] },
];

const url = `${options.origin}${options.route}${options.route.includes("?") ? "&" : "?"}qa=1`;

const browser = await chromium.launch({
  channel: "chrome",
  headless: options.headless,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
});
const context = await browser.newContext({
  viewport: { width: options.width, height: options.height },
  deviceScaleFactor: options.dpr,
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e.message)));
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
});

await page.goto(url, { waitUntil: "load" });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 120_000 });
await page.waitForTimeout(2000);

const freeze = await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), options.mediaTime);
await page.evaluate(() => window.__ILG_QA__.pause());
await page.waitForTimeout(400);

await mkdir(options.out, { recursive: true });
// `out` is deliberately stored repo-relative: a manifest is committed evidence
// and must not carry the capture machine's absolute paths.
const manifest = {
  url,
  viewport: { ...options, out: path.relative(REPO_ROOT, options.out), states: undefined },
  freeze,
  states: [],
  errors,
};

const wanted = options.states ? STATES.filter((s) => options.states.includes(s.id)) : STATES;
for (const state of wanted) {
  await page.evaluate((o) => {
    window.__ILG_QA__.setPointer(0, 0);
    window.__ILG_QA__.setOffset(o[0], o[1]);
  }, state.offset);
  await page.waitForTimeout(320);
  const file = path.join(options.out, `${state.id}.png`);
  await page.screenshot({ path: file });
  const data = await page.evaluate(() => ({
    state: window.__ILG_QA__.getState(),
    quads: window.__ILG_QA__.getCardQuads?.() ?? [],
    media: window.__ILG_QA__.getMediaState(),
  }));
  await writeFile(path.join(options.out, `${state.id}.json`), JSON.stringify(data, null, 2));
  manifest.states.push({ id: state.id, offset: state.offset, png: path.relative(REPO_ROOT, file) });
  console.log(`captured ${state.id}`);
}

await writeFile(path.join(options.out, "manifest.json"), JSON.stringify(manifest, null, 2));
await context.close();
await browser.close();
if (errors.length) {
  console.error("page errors:\n" + errors.join("\n"));
}
console.log(`done -> ${options.out}`);
