#!/usr/bin/env node
/**
 * O5F §十B -- read the LIVE Target runtime's spectral sample tier.
 *
 * The question is what the Target actually compiled in the EXACT context our
 * 390x844 captures ran -- not what a viewport rule would predict. §十B is
 * explicit: do not infer from viewport dimensions. So each probe context is
 * built with the same settings o5r-measure.mjs's targetLane used (mobile
 * emulation exactly when w or h < 500), the same media routes, and the tier
 * is read from three independent places:
 *
 *   1. the compiled programs themselves -- GPUDevice.createShaderModule is
 *      hooked before any page script runs, and the card body program is the
 *      module that calls refract(); its refract count IS the sample count
 *      (the O5 compiled audit established exactly this equivalence on our
 *      own programs: five at high, three at low);
 *   2. the device-tier predicate's inputs, evaluated live in the page:
 *      matchMedia("(pointer: coarse)"), hardwareConcurrency, deviceMemory;
 *   3. the bundle the live page actually loaded -- every response carrying
 *      "maxDispersionSamples" is hashed so the scorer can prove the live
 *      runtime is the archived bundle the source contract was read from.
 *
 * Output: artifacts/optics-o5f/target-tier/target-tier-raw.json
 * (scored by o5f-target-tier.py into qa-v5/optics-o5f/target-mobile-tier.json)
 *
 * Usage: o5f-target-tier.mjs [--target=<url>] [--out=<dir>]
 */
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import {
  installTargetRoutes, loadAsset, TARGET_VIDEO_HOOK, freezeTarget,
} from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  target: "https://infinite-liquid-glass.shader.se/?v=2",
  asset: "bw-split",
  out: path.join(REPO, "artifacts/optics-o5f/target-tier"),
};
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = v;
}

const VIEWPORTS = [[1440, 900], [390, 844], [844, 390], [700, 700]];
const sha256 = (b) => createHash("sha256").update(b).digest("hex");

// Hooked before any page script. WGSL first (the Target runs three's WebGPU
// renderer, like us); the WebGL hook is the fallback so a driver that fell
// back to WebGL still yields programs rather than an empty probe.
const SHADER_HOOK = `(() => {
  window.__o5fShaders = [];
  window.__o5fEnvAtLoad = {
    pointerCoarse: window.matchMedia("(pointer: coarse)").matches,
    anyPointerCoarse: window.matchMedia("(any-pointer: coarse)").matches,
    hardwareConcurrency: navigator.hardwareConcurrency ?? null,
    deviceMemory: navigator.deviceMemory ?? null,
    maxTouchPoints: navigator.maxTouchPoints ?? null,
    userAgent: navigator.userAgent,
    webgpu: !!navigator.gpu,
  };
  if (window.GPUDevice) {
    const orig = GPUDevice.prototype.createShaderModule;
    GPUDevice.prototype.createShaderModule = function (desc) {
      try { window.__o5fShaders.push(String(desc && desc.code || "")); }
      catch (e) { /* never break the page */ }
      return orig.call(this, desc);
    };
  }
  for (const C of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
    if (!C) continue;
    const orig = C.prototype.shaderSource;
    C.prototype.shaderSource = function (shader, source) {
      try { window.__o5fShaders.push(String(source)); }
      catch (e) { /* never break the page */ }
      return orig.call(this, shader, source);
    };
  }
})();`;

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

for (const [w, h] of VIEWPORTS) {
  const tag = `${w}x${h}`;
  const mobile = w < 500 || h < 500;   // o5r-measure's own rule, unchanged
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installTargetRoutes(ctx, loadAsset(opts.asset), null);
  await ctx.addInitScript(TARGET_VIDEO_HOOK);
  await ctx.addInitScript(SHADER_HOOK);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const bundles = [];
  page.on("response", async (resp) => {
    try {
      const url = resp.url();
      if (!/\.js(\?|$)/.test(url)) return;
      const body = await resp.body();
      if (body.includes("maxDispersionSamples")) {
        bundles.push({ url, bytes: body.length, sha256: sha256(body) });
      }
    } catch { /* detached responses at teardown are fine */ }
  });

  let loaded = true;
  try {
    await page.goto(opts.target, { waitUntil: "load", timeout: 60000 });
    await page.waitForFunction(() =>
      (window.__o2vids?.length ?? 0) >= 8
      && window.__o2vids.every((v) => v.readyState >= 2), undefined,
      { timeout: 90000 });
    await page.waitForTimeout(4000);
    await freezeTarget(page, 4);
  } catch (e) {
    loaded = false;
    errors.push(`load: ${String(e).slice(0, 200)}`);
  }

  const probe = loaded ? await page.evaluate(() => {
    const shaders = window.__o5fShaders ?? [];
    const refractModules = shaders
      .filter((s) => s.includes("refract"))
      .map((s) => ({
        length: s.length,
        refractCalls: (s.match(/refract/g) || []).length,
        textureSamples: (s.match(/textureSample\s*\(/g) || []).length
          + (s.match(/texture2D\s*\(|texture\s*\(/g) || []).length,
        isFragment: s.includes("@fragment") || s.includes("gl_FragColor")
          || s.includes("fragmentMain") || s.includes("main_fragment"),
        head: s.slice(0, 120),
      }));
    return {
      envAtLoad: window.__o5fEnvAtLoad ?? null,
      envNow: {
        pointerCoarse: window.matchMedia("(pointer: coarse)").matches,
        hardwareConcurrency: navigator.hardwareConcurrency ?? null,
        deviceMemory: navigator.deviceMemory ?? null,
      },
      shaderModuleCount: shaders.length,
      refractModules,
      videoCount: (window.__o2vids ?? []).length,
    };
  }) : null;

  // The card body program's full text, for the output-transform check (§十D)
  // and the archive: the module with the most refract() calls.
  let bodyProgram = null;
  if (loaded) {
    bodyProgram = await page.evaluate(() => {
      const shaders = (window.__o5fShaders ?? []).filter(
        (s) => s.includes("refract"));
      if (!shaders.length) return null;
      let best = shaders[0];
      for (const s of shaders) {
        if ((s.match(/refract/g) || []).length
            > (best.match(/refract/g) || []).length) best = s;
      }
      return best;
    });
    if (bodyProgram) {
      const f = `target-body-program-${tag}.wgsl.txt`;
      await writeFile(path.join(opts.out, f), bodyProgram);
      bodyProgram = { file: f, sha256: sha256(bodyProgram),
        length: bodyProgram.length };
    }
    const shot = `target-tier-${tag}.png`;
    await page.screenshot({ path: path.join(opts.out, shot) });
  }

  records.push({ vp: tag, mobileEmulation: mobile, loaded, probe,
    bodyProgram, bundlesWithPredicate: bundles,
    errorCount: errors.length, errors: errors.slice(0, 4) });
  console.log(`${tag}: loaded=${loaded} pointerCoarse=`
    + `${probe?.envAtLoad?.pointerCoarse} modules=${probe?.shaderModuleCount} `
    + `refractModules=${probe?.refractModules?.length}`);
  await ctx.close();
}

await writeFile(path.join(opts.out, "target-tier-raw.json"), JSON.stringify({
  what: "O5F §十B raw probe -- the live Target runtime under the exact "
      + "capture contexts, its compiled programs, its tier-predicate inputs "
      + "and the bundles it loaded.",
  target: opts.target, asset: opts.asset,
  contextRule: "mobile emulation exactly when w or h < 500 -- "
      + "o5r-measure.mjs's own rule",
  records,
}, null, 1));
console.log(`-> ${opts.out}/target-tier-raw.json`);
await browser.close();
