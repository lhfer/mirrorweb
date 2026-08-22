#!/usr/bin/env node
/**
 * O5F §九 -- capture the term-decomposition programs.
 *
 * One page load per (viewport, view): every view is a SEPARATE PROGRAM
 * selected at build time by `bodyView=`, never a runtime branch inside
 * Beauty -- the O4A shared-varying hazard has no surface here, and the
 * sealed Beauty program contains none of the measurement expressions.
 *
 * Per capture: the still, the generated program's sha256 (vertex+fragment),
 * and the card body truth -- so the scorer can prove every view rendered
 * the SAME card matrix, camera, planeSize, cardScale and media time before
 * comparing anything. The full WGSL text of the beauty program is saved for
 * the §十D output-transform comparison against the Target's captured
 * program.
 *
 * Usage: o5f-decomposition.mjs --local=<origin> [--out=<dir>]
 */
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, asset: "bw-split", freeze: 4,
  out: path.join(REPO, "artifacts/optics-o5f/decomposition") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const VIEWPORTS = ["1440x900", "390x844"];
// §九's nine programs. body-refracted is the existing refraction-only view
// (the spectral accumulator before environment and rim); final-colour is
// Beauty itself.
const VIEWS = [
  "beauty", "refraction-only", "analytic-normal",
  "raw-env-sample", "reflection-vector", "equirect-uv",
  "fresnel", "env-mix-factor", "white-rim",
];

const sha256 = (s) => createHash("sha256").update(s).digest("hex");
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

for (const vp of VIEWPORTS) {
  const [w, h] = vp.split("x").map(Number);
  const mobile = w < 500 || h < 500;
  for (const view of VIEWS) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h },
      hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
    await installLocalRoutes(ctx, loadAsset(opts.asset), null);
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    await page.goto(`${opts.local}/?composition=sourceExact&qa`
      + "&dispersionLaw=o1&reflectionSupport=geometry&bodyFloorMode=current"
      + `&opticalBody=target-source-unclamped&bodyView=${view}`,
      { waitUntil: "load", timeout: 120000 });
    await page.waitForFunction(
      () => window.__ILG_QA__?.getState?.()?.ready === true, undefined,
      { timeout: 180000 });
    await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
    await page.evaluate((t) =>
      window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
    await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      qa.pause();
      qa.setShellMode("off");
      qa.setRenderLayers({ labels: false });
      qa.setVelocity(0, 0); qa.setOffset(0, 0); qa.jumpPointer(0, 0);
      qa.setTime(4);
      qa.renderOnce(); qa.renderOnce();
    });
    await page.waitForTimeout(120);

    const file = `${view}-${vp}.png`;
    await page.screenshot({ path: path.join(opts.out, file) });
    const truth = await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      return JSON.parse(JSON.stringify({
        body: qa.getCardBodyTruth(),
        optics: {
          opticalBody: qa.getOpticsState().opticalBody,
          opticalBodyView: qa.getOpticsState().opticalBodyView,
          samples: qa.getOpticsState().opticalBodySamples,
          environmentMode: qa.getOpticsState().environmentMode,
          envSampleClamped: qa.getOpticsState().envSampleClamped,
          envMixScale: qa.getOpticsState().envMixScale,
          rimScale: qa.getOpticsState().rimScale,
        },
        media: qa.getMediaState(),
      }));
    });
    const src = await page.evaluate(() =>
      window.__ILG_QA__.getGlassShaderSource());
    const program = src ? {
      vertexSha256: sha256(src.vertexShader),
      fragmentSha256: sha256(src.fragmentShader),
      fragmentLength: src.fragmentShader.length,
    } : null;
    if (src && (view === "beauty" || view === "raw-env-sample")) {
      const pf = `${view}-${vp}-program.wgsl.txt`;
      await writeFile(path.join(opts.out, pf),
        `// vertex\n${src.vertexShader}\n// fragment\n${src.fragmentShader}`);
      program.file = pf;
    }

    // The media plane, for the image-based body-refracted replay: the same
    // page, glass hidden, media shown.
    let mediaFile = null;
    if (view === "beauty") {
      await page.evaluate(() => {
        const qa = window.__ILG_QA__;
        qa.setRenderLayers({ glass: false, media: true });
        qa.renderOnce(); qa.renderOnce();
      });
      await page.waitForTimeout(80);
      mediaFile = `media-only-${vp}.png`;
      await page.screenshot({ path: path.join(opts.out, mediaFile) });
    }

    const truthFile = `truth-${view}-${vp}.json`;
    await writeFile(path.join(opts.out, truthFile),
      JSON.stringify(truth, null, 1));
    records.push({ vp, view, file, truthFile, mediaFile, program,
      errorCount: errors.length, errors: errors.slice(0, 4) });
    console.log(`${vp} ${view}: captured (samples ${truth.optics.samples}, `
      + `errors ${errors.length})`);
    await ctx.close();
  }
}

await writeFile(path.join(opts.out, "decomposition-manifest.json"),
  JSON.stringify({
    what: "O5F §九 decomposition captures: nine separate programs per "
        + "viewport, same frozen media time, same rest state, plus the card "
        + "body truth per capture so the scorer can prove the inputs were "
        + "identical before comparing terms.",
    local: opts.local, asset: opts.asset, freeze: opts.freeze,
    lane: "target-source-unclamped",
    viewports: VIEWPORTS, views: VIEWS, records,
  }, null, 1));
console.log(`-> ${opts.out}`);
await browser.close();
