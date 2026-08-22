#!/usr/bin/env node
/**
 * O4 §九 gate captures.
 *
 * Two product lanes from ONE build and one page each:
 *   control    ?bodyFloorMode=current                  (accepted O2 body)
 *   candidate  ?bodyFloorMode=remove-adaptive-shaping
 *
 * Two states per lane:
 *   sysBOff  envMixScale 0, rimScale 0, shell off -- the PRIMARY gate state
 *            (§九's body floor), and the state the factorial attributed in
 *   sysBOn   envMixScale 1, rimScale 1, shell off -- the SHIPPED state, and
 *            the one the product-quality items (colour, rim, interior,
 *            gutter, high-frequency structure) are scored in, because that
 *            is the condition a user sees
 *
 * Labels are off everywhere, per the sealed instrument contract.
 *
 * --base captures the same control state on an e913aa6 worktree for §九.11.
 *
 * Usage: o4-gate-measure.mjs --local=<origin> [--base=<origin>] [--out=<dir>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, base: null, freeze: 4,
  out: path.join(REPO, "artifacts/optics-o4/gate") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const LANES = [["control", "current"],
               ["candidate", "remove-adaptive-shaping"]];
const DESKTOP = ["bw-split", "grayscale-step", "rgb-bars", "hf-checker",
                 "cool-blue", "warm-skin", "dark-highlight", "bright-lowsat"];
const MOBILE = ["bw-split", "rgb-bars"];
const STATES = [["sysBOff", 0, 0], ["sysBOn", 1, 1]];
const POINTER = [["pl", -0.99, 0], ["pbr", 0.99, 0.99], ["pr", 0.99, 0]];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

async function run(origin, laneTag, mode, vp, asset, opt = {}) {
  const [w, h] = vp.split("x").map(Number);
  const mobile = w < 500 || h < 500;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, loadAsset(asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${origin}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&bodyFloorMode=${mode}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  const freeze = await page.evaluate((t) =>
    window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.setOffset(0, 0); qa.setVelocity(0, 0); qa.jumpPointer(0, 0);
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
  });

  for (const [state, env, rim] of STATES) {
    await page.evaluate(([e, r]) => {
      const qa = window.__ILG_QA__;
      qa.setEnvMixScale(e); qa.setRimScale(r);
      qa.renderOnce(); qa.renderOnce();
    }, [env, rim]);
    await page.waitForTimeout(180);
    const optics = await page.evaluate(() => window.__ILG_QA__.getOpticsState());
    const file = `${laneTag}-${state}-${asset}-${vp}.png`;
    await page.screenshot({ path: path.join(opts.out, file) });
    records.push({ kind: "lane", lane: laneTag, bodyFloorMode: mode, state,
      asset, vp, file, optics, frozen: freeze?.frozen,
      maxSeekError: freeze?.maxSeekError });

    if (state === "sysBOn" && opt.pointer) {
      for (const [pn, nx, ny] of POINTER) {
        await page.evaluate(([x, y]) => {
          window.__ILG_QA__.jumpPointer(x, y);
          window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
        }, [nx, ny]);
        const pf = `${laneTag}-sysBOn-${pn}-${asset}-${vp}.png`;
        await page.screenshot({ path: path.join(opts.out, pf) });
        records.push({ kind: "pointer", lane: laneTag, state: `sysBOn-${pn}`,
          asset, vp, pointer: [nx, ny], file: pf });
      }
      await page.evaluate(() => {
        window.__ILG_QA__.jumpPointer(0, 0); window.__ILG_QA__.renderOnce();
      });
    }
  }

  if (opt.mediaOnly) {
    await page.evaluate(() => {
      window.__ILG_QA__.setRenderLayers({ glass: false });
      window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
    });
    const mf = `${laneTag}-mediaonly-${asset}-${vp}.png`;
    await page.screenshot({ path: path.join(opts.out, mf) });
    records.push({ kind: "media-only", lane: laneTag, asset, vp, file: mf });
    await page.evaluate(() => {
      window.__ILG_QA__.setRenderLayers({ glass: true });
      window.__ILG_QA__.renderOnce();
    });
  }
  records.push({ kind: "errors", lane: laneTag, asset, vp,
    errorCount: errors.length, samples: errors.slice(0, 10) });
  await ctx.close();
}

for (const asset of DESKTOP) {
  for (const [tag, mode] of LANES) {
    await run(opts.local, tag, mode, "1440x900", asset, {
      pointer: asset === "bw-split",
      mediaOnly: ["bw-split", "rgb-bars"].includes(asset) });
  }
  console.log(`desktop ${asset} done`);
}
for (const vp of ["390x844", "844x390"]) {
  for (const asset of MOBILE) {
    for (const [tag, mode] of LANES) {
      await run(opts.local, tag, mode, vp, asset,
        { mediaOnly: asset === "bw-split" });
    }
  }
  console.log(`${vp} done`);
}

// §九.11 -- the control lane against the accepted O2 baseline build.
if (opts.base) {
  for (const [vp, asset] of [["1440x900", "bw-split"], ["1440x900", "rgb-bars"],
                             ["1440x900", "grayscale-step"],
                             ["390x844", "bw-split"], ["844x390", "bw-split"]]) {
    await run(opts.base, "baseline-e913aa6", "current", vp, asset, {});
  }
  console.log("baseline done");
}

await writeFile(path.join(opts.out, "gate-manifest.json"), JSON.stringify({
  what: "O4 §九 gate captures. Two product lanes, one build, one page each; "
      + "System B OFF is the primary gate state, System B ON is the shipped "
      + "state the product-quality items are scored in. Labels off "
      + "throughout, per the sealed instrument contract.",
  local: opts.local, base: opts.base, freeze: opts.freeze, records,
}, null, 1));
console.log(`${records.length} records -> ${opts.out}`);
await browser.close();
