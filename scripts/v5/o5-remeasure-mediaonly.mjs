#!/usr/bin/env node
/**
 * Re-capture ONLY the media-only and glass-only renders.
 *
 * Why this exists, stated plainly. The candidate's QA media plane was placed
 * at a different depth from the control's, so the two lanes projected the same
 * media at slightly different sizes and their media-only captures were not
 * comparable -- which the O2 Media-only Controls suite caught. The plane is
 * hidden in the candidate's Beauty path, so no optical measurement reads it;
 * what reads it is the true-silhouette derivation and the edge-compression
 * baseline check, both of which compare lanes.
 *
 * This re-captures those two render layers and nothing else. Every Beauty
 * capture on disk is left untouched, so items 1-6 and 9-14 are scored on
 * exactly the pixels they were scored on before, by construction rather than
 * by assertion.
 *
 * Usage: o5-remeasure-mediaonly.mjs --local=<origin> [--out=<dir>]
 */
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, freeze: 4,
  out: path.join(REPO, "artifacts/optics-o5/measure") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const manPath = path.join(opts.out, "measure-manifest.json");
const man = JSON.parse(await readFile(manPath, "utf8"));
const targets = man.records.filter(
  (r) => r.kind === "media-only" || r.kind === "glass-only");
console.log(`${targets.length} layer captures to redo`);

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

// Group by (lane, vp, asset) so each page load redoes both layers at once.
const groups = new Map();
for (const r of targets) {
  const key = `${r.lane}|${r.vp}|${r.asset}`;
  if (!groups.has(key)) groups.set(key, []);
  groups.get(key).push(r);
}

for (const [key, recs] of groups) {
  const [lane, vp, asset] = key.split("|");
  const [w, h] = vp.split("x").map(Number);
  const mobile = w < 500 || h < 500;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, loadAsset(asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&bodyFloorMode=current&opticalBody=`
    + `${lane === "candidate" ? "target-source" : "current"}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.pause();
    qa.setOffset(0, 0); qa.setVelocity(0, 0); qa.jumpPointer(0, 0);
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
    qa.renderOnce(); qa.renderOnce();
  });
  await page.waitForTimeout(160);

  for (const rec of recs) {
    const layers = rec.kind === "media-only"
      ? { glass: false, media: true }
      : { glass: true, media: false };
    await page.evaluate((l) => {
      const qa = window.__ILG_QA__;
      qa.setRenderLayers(l);
      qa.renderOnce(); qa.renderOnce();
    }, layers);
    await page.waitForTimeout(120);
    await page.screenshot({ path: path.join(opts.out, rec.file) });
  }
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.setRenderLayers({ glass: true, media: true });
    qa.renderOnce();
  });
  if (errors.length) console.log(`  ${key}: ${errors.length} errors`);
  await ctx.close();
}

man.mediaPlaneParityRecapture = {
  what: "media-only and glass-only layers re-captured after the candidate's "
      + "QA media plane was given the control's depth. Beauty captures were "
      + "NOT re-taken, so every optical item is scored on its original pixels.",
  layersRedone: targets.length,
};
await writeFile(manPath, JSON.stringify(man, null, 1));
console.log(`redone -> ${opts.out}`);
await browser.close();
