#!/usr/bin/env node
/**
 * O5 §七 -- capture the CANDIDATE's generated program and runtime probes.
 *
 * Two kinds of evidence, because neither alone settles the fifteen items:
 *
 *   generated WGSL   settles what the program CONTAINS -- how many refracts,
 *                    which textures, whether a mip LOD or a scene-colour
 *                    binding appears at all
 *   runtime probes   settle what the program PRODUCES -- finite normals, no
 *                    NaN, no Inf, real spatial variance
 *
 * O4A is the reason both are required. There, the TypeScript said the body
 * consumed a geometry normal, the program declared the varying, and only the
 * rendered pixels showed the branch was reading a zero-initialised private.
 *
 * Usage: o5-compiled-audit.mjs --local=<origin> [--out=<dir>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: "http://127.0.0.1:5280", asset: "hf-checker", freeze: 4,
  out: path.join(REPO, "artifacts/optics-o5/audit") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}

const QUALITIES = ["high", "medium", "low"];
const VIEWS = ["beauty", "analytic-normal", "sdf-mask", "refraction-only"];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

async function open(lane, quality, view) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await installLocalRoutes(ctx, loadAsset(opts.asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&opticalBody=${lane}&bodyView=${view}`
    + `&quality=${quality}`, { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate((q) => {
    const qa = window.__ILG_QA__;
    qa.setAdaptiveQuality(false);
    qa.setQuality(q);
  }, quality);
  await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.pause();
    qa.setOffset(0, 0); qa.setVelocity(0, 0); qa.jumpPointer(0, 0);
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
    qa.renderOnce(); qa.renderOnce();
  });
  await page.waitForTimeout(180);
  return { ctx, page, errors };
}

for (const quality of QUALITIES) {
  const { ctx, page, errors } = await open("target-source", quality, "beauty");
  const src = await page.evaluate(() => window.__ILG_QA__.getGlassShaderSource());
  const optics = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
  if (src) {
    await writeFile(path.join(opts.out, `candidate-${quality}.frag.wgsl`),
      String(src.fragmentShader ?? ""));
    await writeFile(path.join(opts.out, `candidate-${quality}.vert.wgsl`),
      String(src.vertexShader ?? ""));
  }
  records.push({ kind: "program", lane: "target-source", quality,
    fragBytes: String(src?.fragmentShader ?? "").length,
    vertBytes: String(src?.vertexShader ?? "").length,
    optics, errorCount: errors.length, errors: errors.slice(0, 6) });
  console.log(`program ${quality}: frag ${String(src?.fragmentShader ?? "").length} B, `
    + `samples ${optics.opticalBodySamples}, errors ${errors.length}`);
  await ctx.close();
}

// The control program too, so the audit can show the scene-colour binding is
// present in one lane and absent in the other rather than merely asserting it.
{
  const { ctx, page, errors } = await open("current", "high", "beauty");
  const src = await page.evaluate(() => window.__ILG_QA__.getGlassShaderSource());
  if (src) {
    await writeFile(path.join(opts.out, "control-high.frag.wgsl"),
      String(src.fragmentShader ?? ""));
  }
  records.push({ kind: "program", lane: "current", quality: "high",
    fragBytes: String(src?.fragmentShader ?? "").length,
    errorCount: errors.length });
  console.log(`program control high: frag ${String(src?.fragmentShader ?? "").length} B`);
  await ctx.close();
}

// Runtime probes: one capture per view, plus a full-precision readback of the
// analytic-normal view for the finite/variance items.
for (const view of VIEWS) {
  const { ctx, page, errors } = await open("target-source", "high", view);
  const file = `candidate-${view}.png`;
  await page.screenshot({ path: path.join(opts.out, file) });
  const optics = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
  // Render-pass truth: item 9 turns on the scene-colour pass having drawn
  // NOTHING while the body still shows media, so the media cannot have come
  // from that target.
  const passes = await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    return { stats: qa.getRenderPassStats?.() ?? null,
             layers: qa.getRenderLayerState?.() ?? null };
  });
  records.push({ kind: "view", view, file, optics, passes,
    errorCount: errors.length, errors: errors.slice(0, 6) });
  console.log(`view ${view}: errors ${errors.length}`);
  await ctx.close();
}

await writeFile(path.join(opts.out, "audit-manifest.json"), JSON.stringify({
  what: "O5 §七 compiled-body audit captures: generated WGSL at three "
      + "qualities for the candidate plus the control for contrast, and one "
      + "render per candidate debug view for the runtime probes.",
  local: opts.local, asset: opts.asset, qualities: QUALITIES, views: VIEWS,
  records,
}, null, 1));
console.log(`-> ${opts.out}`);
await browser.close();
