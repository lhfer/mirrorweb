#!/usr/bin/env node
/**
 * The lane-equivalence gate (o2-selected-system.json,
 * laneMapping.equivalenceProofsBlocking + failure condition F8), run as
 * TWO procedure classes:
 *
 * 1. STRUCTURAL (BLOCKING, exact zero): ?systemB=off never passes the env
 *    texture, so the System B uniforms are never referenced and the
 *    generated shader is the pre-O2 one byte for byte.
 *      systemB=off + dispersionLaw=v1-taps    == 5159cf8 build
 *      systemB=off + dispersionLaw=o1-spectral == 62d3ac4 build
 *    These rows are cross-origin AND cross-build at zero, which also
 *    retires the historic same-commit-two-origin decode caveat -- no
 *    separate control row is needed.
 *
 * 2. RUNTIME-NEUTRALISED (RECORDED measurement): envMixScale=0, rimScale=0,
 *    shellMode=energy-controlled -- the registered floor state. The env
 *    code is dead at t=0 but PRESENT in the module, which changes compiler
 *    scheduling (FMA contraction): the observed envelope is a deterministic
 *    <=1/255 difference on isolated glass pixels. That envelope is
 *    DIAGNOSTIC, not a tolerance -- a run outside it means investigate,
 *    never excuse. The verdict script records both codings verbatim.
 *
 * Both sides consume the SAME deterministic asset through the shared-media
 * routes, frozen at the same time.
 *
 * Usage: o2-lane-equivalence.mjs --candidate=<origin> --v1base=<origin>
 *        --o1base=<origin> --out=<dir> [--asset=bw-split]
 *        [--vps=1440x900,390x844]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { candidate: null, v1base: null, o1base: null,
  out: path.join(REPO, "artifacts/optics-o2/lane-equivalence"),
  asset: "bw-split", vps: ["1440x900", "390x844"] };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "vps" ? v.split(",") : v;
}
if (!opts.candidate || !opts.v1base || !opts.o1base) {
  console.error("--candidate, --v1base, --o1base required"); process.exit(2);
}

const asset = loadAsset(opts.asset);
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });

async function capture(origin, extraQuery, neutralise, file, vp) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h } });
  await installLocalRoutes(ctx, asset, null);
  const page = await ctx.newPage();
  await page.goto(`${origin}/?composition=sourceExact&qa${extraQuery}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  if (neutralise) {
    await page.evaluate(() => {
      window.__ILG_QA__.setEnvMixScale(0);
      window.__ILG_QA__.setRimScale(0);
      window.__ILG_QA__.setShellMode("energy-controlled");
    });
  }
  await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), 4);
  await page.evaluate(() => window.__ILG_QA__.renderOnce());
  await page.waitForTimeout(400);
  const f = path.join(opts.out, `${file}-${vp}.png`);
  await page.screenshot({ path: f });
  await ctx.close();
  return f;
}

const pairs = [];
for (const vp of opts.vps) {
  pairs.push({ what: "STRUCTURAL v1-taps systemB=off vs 5159cf8", class: "structural", vp,
    a: await capture(opts.candidate,
      "&systemB=off&dispersionLaw=v1&shell=energy-controlled", false,
      "structural-v1", vp),
    b: await capture(opts.v1base, "", false, "base-5159cf8", vp) });
  pairs.push({ what: "STRUCTURAL o1-spectral systemB=off vs 62d3ac4", class: "structural", vp,
    a: await capture(opts.candidate,
      "&systemB=off&dispersionLaw=o1&shell=energy-controlled", false,
      "structural-o1", vp),
    b: await capture(opts.o1base, "", false, "base-62d3ac4", vp) });
  pairs.push({ what: "runtime-neutralised v1-taps vs 5159cf8", class: "runtime-neutralised", vp,
    a: await capture(opts.candidate, "&dispersionLaw=v1", true, "cand-v1-neutral", vp),
    b: await capture(opts.v1base, "", false, "base-5159cf8", vp) });
  pairs.push({ what: "runtime-neutralised o1-spectral vs 62d3ac4", class: "runtime-neutralised", vp,
    a: await capture(opts.candidate, "&dispersionLaw=o1", true, "cand-o1-neutral", vp),
    b: await capture(opts.o1base, "", false, "base-62d3ac4", vp) });
}
await writeFile(path.join(opts.out, "pairs.json"), JSON.stringify({ asset: opts.asset, pairs }, null, 1));
console.log(`${pairs.length} pairs -> ${opts.out}`);
await browser.close();
