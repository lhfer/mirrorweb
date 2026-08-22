#!/usr/bin/env node
/**
 * O5R §十 -- capture the generated programs that prove what the source-environment
 * correction actually did.
 *
 * §十 makes three structural claims, and each is settled here by what the
 * PROGRAM contains rather than by what the TypeScript says:
 *
 *   1. the clamp is gone from the O5R lane and still present in the sealed one
 *   2. environmentMode=off omits the environment sample COMPLETELY -- no
 *      texture fetch, no Fresnel term, no mix -- rather than multiplying an
 *      already-sampled value by zero
 *   3. the three O5R measurement views are separate programs, not branches
 *
 * O4A is why this is done from the compiled program. There, the TypeScript
 * said the body consumed a geometry normal, the program declared the varying,
 * and only the rendered pixels showed a branch reading a zero-initialised
 * private.
 *
 * Usage: o5r-source-env.mjs --local=<origin> [--out=<dir>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, asset: "hf-checker", freeze: 4,
  out: path.join(REPO, "artifacts/optics-o5r/source-env") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const CASES = [
  { tag: "o5-clamped", lane: "target-source", env: "source", view: "beauty" },
  { tag: "o5r-unclamped", lane: "target-source-unclamped", env: "source",
    view: "beauty" },
  { tag: "o5r-env-off", lane: "target-source-unclamped", env: "off",
    view: "beauty" },
  { tag: "o5r-uv-unrefracted", lane: "target-source-unclamped", env: "source",
    view: "uv-unrefracted" },
  { tag: "o5r-uv-refracted", lane: "target-source-unclamped", env: "source",
    view: "uv-refracted" },
  { tag: "o5r-displacement", lane: "target-source-unclamped", env: "source",
    view: "refraction-displacement" },
  { tag: "o5r-sdf-mask", lane: "target-source-unclamped", env: "source",
    view: "sdf-mask" },
  { tag: "control", lane: "current", env: "source", view: "beauty" },
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

for (const c of CASES) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await installLocalRoutes(ctx, loadAsset(opts.asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&bodyFloorMode=current`
    + `&opticalBody=${c.lane}&environmentMode=${c.env}&bodyView=${c.view}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(
    () => window.__ILG_QA__?.getState?.()?.ready === true, undefined,
    { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t),
    opts.freeze);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.pause();
    qa.setOffset(0, 0); qa.setVelocity(0, 0); qa.jumpPointer(0, 0);
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
    qa.renderOnce(); qa.renderOnce();
  });
  await page.waitForTimeout(180);
  const src = await page.evaluate(() => window.__ILG_QA__.getGlassShaderSource());
  const optics = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
  const frag = String(src?.fragmentShader ?? "");
  await writeFile(path.join(opts.out, `${c.tag}.frag.wgsl`), frag);
  await page.screenshot({ path: path.join(opts.out, `${c.tag}.png`) });
  records.push({
    tag: c.tag, lane: c.lane, environmentMode: c.env, view: c.view,
    fragBytes: frag.length,
    fragFile: `${c.tag}.frag.wgsl`, shot: `${c.tag}.png`,
    optics: {
      opticalBody: optics.opticalBody, bodyView: optics.opticalBodyView,
      environmentMode: optics.environmentMode,
      envSampleClamped: optics.envSampleClamped,
      samples: optics.opticalBodySamples,
      envMixScale: optics.envMixScale, rimScale: optics.rimScale,
    },
    errorCount: errors.length, errors: errors.slice(0, 6),
  });
  console.log(`${c.tag.padEnd(20)} frag ${frag.length} B  clamped=`
    + `${optics.envSampleClamped} env=${optics.environmentMode} `
    + `errors=${errors.length}`);
  await ctx.close();
}

await writeFile(path.join(opts.out, "source-env-manifest.json"), JSON.stringify({
  what: "O5R §十 -- generated programs and one render per lane/mode/view, so "
      + "the environment correction is settled by what the program contains.",
  local: opts.local, asset: opts.asset, records,
}, null, 1));
console.log(`-> ${opts.out}`);
await browser.close();
