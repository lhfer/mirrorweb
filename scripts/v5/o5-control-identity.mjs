#!/usr/bin/env node
/**
 * O5 §六 -- control identity.
 *
 * `opticalBody=current` at the O5 code commit must be EXACTLY the same pixels
 * as a 5a87751 build, on the same deterministic media, at five viewports and
 * seven states. If it is not, every later "candidate vs control" number is
 * measured against something that is no longer the accepted body, and the
 * round is over before it starts.
 *
 * Why the states are set through QA hooks rather than replayed as gestures.
 * The three motion states are compared as STATES -- a fixed (offset, velocity,
 * pointer) triple -- not as recorded gesture playback. Two servers cannot be
 * driven through a real drag and land on the same frame: the comparison would
 * measure scheduler jitter, not the body. Temporal behaviour has its own gate
 * (§九.12) with real events; this one asks whether the same inputs produce the
 * same pixels, and a fixed state is the only form of that question with a
 * definite answer. The velocities used are the ones the corresponding gestures
 * actually reach in m2_sequences.
 *
 * Usage: o5-control-identity.mjs --local=<origin> --base=<origin> [--out=<dir>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, base: null, asset: "bw-split", freeze: 4,
  out: path.join(REPO, "artifacts/optics-o5/control-identity") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local || !opts.base) {
  console.error("--local and --base are required");
  process.exit(2);
}

const VIEWPORTS = ["1440x900", "1920x1080", "390x844", "844x390", "700x700"];

/** name -> QA state. Velocities are those the named gesture actually reaches. */
const STATES = [
  ["rest", { offset: [0, 0], velocity: [0, 0], pointer: [0, 0] }],
  ["pointer-left", { offset: [0, 0], velocity: [0, 0], pointer: [-0.99, 0] }],
  ["pointer-right", { offset: [0, 0], velocity: [0, 0], pointer: [0.99, 0] }],
  ["pointer-corner", { offset: [0, 0], velocity: [0, 0], pointer: [0.99, 0.99] }],
  ["slow-drag", { offset: [180, 0], velocity: [42, 0], pointer: [-0.35, 0] }],
  ["fast-flick", { offset: [-620, 0], velocity: [-1750, 0], pointer: [0.4, 0] }],
  ["touch", { offset: [0, 240], velocity: [0, 310], pointer: [0, -0.4] }],
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

async function capture(origin, tag, vp) {
  const [w, h] = vp.split("x").map(Number);
  const mobile = w < 500 || h < 500;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, loadAsset(opts.asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${origin}/?composition=sourceExact&qa&dispersionLaw=o1`
    + `&reflectionSupport=geometry&bodyFloorMode=current&opticalBody=current`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  const freeze = await page.evaluate((t) =>
    window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    // PAUSE before any state is set. renderOnce() does not advance the motion
    // integrator, but the page's own RAF loop does, and it runs between our
    // evaluate() calls. Unpaused, a velocity-bearing state is integrated for a
    // scheduler-dependent dt on each server, so the comparison would measure
    // jitter rather than the body. Paused, the state we set is the state that
    // renders.
    qa.pause();
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
  });

  const out = [];
  for (const [state, s] of STATES) {
    await page.evaluate((st) => {
      const qa = window.__ILG_QA__;
      // Velocity first, then offset, then pointer: setOffset and jumpPointer
      // each render, so the last write wins and the rendered pose is exactly
      // the triple asked for.
      qa.setVelocity(st.velocity[0], st.velocity[1]);
      qa.setOffset(st.offset[0], st.offset[1]);
      qa.jumpPointer(st.pointer[0], st.pointer[1]);
      qa.setTime(4);
      qa.renderOnce(); qa.renderOnce();
    }, s);
    await page.waitForTimeout(120);
    const file = `${tag}-${state}-${vp}.png`;
    await page.screenshot({ path: path.join(opts.out, file) });
    const probe = await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      const st = qa.getState();
      const op = qa.getOpticsState();
      return {
        opticalBody: op.opticalBody ?? null,
        bodyFloorMode: op.bodyFloorMode ?? null,
        reflectionSupport: op.reflectionSupport ?? null,
        dispersionLaw: op.dispersionLaw ?? null,
        shellMode: op.shellModeApplied ?? op.shellMode ?? null,
        envMixScale: op.envMixScale ?? null,
        rimScale: op.rimScale ?? null,
        glassMeshesVisible: st.glassMeshesVisible ?? null,
        reflectionShellsVisible: st.reflectionShellsVisible ?? null,
        mediaMeshesVisible: st.mediaMeshesVisible ?? null,
        activeSlots: st.activeSlots ?? null,
        drawCallsFinal: st.drawCallsFinal ?? null,
        drawCallsSceneColor: st.drawCallsSceneColor ?? null,
      };
    });
    out.push({ state, file, probe });
  }
  await ctx.close();
  return { captures: out, errorCount: errors.length, errors: errors.slice(0, 6) };
}

for (const vp of VIEWPORTS) {
  const local = await capture(opts.local, "local", vp);
  const base = await capture(opts.base, "base", vp);
  records.push({ vp, local, base });
  console.log(`${vp}: captured (local errors ${local.errorCount}, `
    + `base errors ${base.errorCount})`);
}

await writeFile(path.join(opts.out, "identity-manifest.json"), JSON.stringify({
  what: "O5 §六 control identity captures. opticalBody=current at the O5 code "
      + "commit against a 5a87751 build, same deterministic media, same frozen "
      + "time, five viewports, seven fixed states.",
  local: opts.local, base: opts.base, asset: opts.asset, freeze: opts.freeze,
  statesAreFixedNotReplayed: "the three motion states are a fixed (offset, "
      + "velocity, pointer) triple, because two servers cannot be driven "
      + "through a real gesture onto the same frame; temporal behaviour is "
      + "gated separately in §九.12 with real events",
  states: STATES.map(([n, s]) => ({ state: n, ...s })),
  viewports: VIEWPORTS, records,
}, null, 1));
console.log(`-> ${opts.out}`);
await browser.close();
