#!/usr/bin/env node
/**
 * Final Motion Convergence §四 -- the fast flick, ten times, with the release
 * scheduling recorded rather than inferred.
 *
 * The §五 recording found the candidate's flick is BIMODAL: three runs travel
 * ~815.6 px, inside the Target's own 814.75-817.18 spread, and two travel
 * ~832-833. Two runs in five overshoot by ~17.4 px on identical dispatched
 * input, where the Target shows one mode. §四 forbids calling that "the fling
 * constant is too large" -- a constant cannot produce two modes -- and asks
 * which scheduling fact separates them.
 *
 * So this records, per run and on BOTH pages with one instrument:
 *
 *   input        every pointer event the page's own handlers received, with
 *                the event's timeStamp, the listener entry time and the
 *                client point
 *   frames       every rAF callback, timed, in the same seq space -- so
 *                "did a frame dispatch fall between the last move and the
 *                release" is a subtraction, not a guess
 *   trajectory   the §五 tracked block, per frame, so travel is measured the
 *                same way §五 measured it
 *   release      candidate only: the model's own release record -- history as
 *                it stood, the two points the velocity window used, the
 *                window dt, the velocity that came out, the fling delta and
 *                the frame it committed on. The Target's equivalent is not
 *                readable from outside, which is exactly why the frame/event
 *                interleave above is recorded identically on both sides.
 *
 * Usage:
 *   fm-flick-trace.mjs --side=target|local [--repeats=10] [--local=<url>]
 *                      [--label=<name>] [--out=<dir>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { sleep } from "./vc2_scenarios.mjs";
import { TARGET_URL, LOCAL_ORIGIN, assetFor, openMatched, pinMatched, readMatched }
  from "./vc2_matched.mjs";
import { RESIZE_INSTRUMENT, FRAME_RECORDER } from "./fm_resize_instrument.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  side: "target", repeats: 10, track: 10, label: "",
  out: path.join(REPO, "artifacts/final-motion/flick"),
  local: `${LOCAL_ORIGIN}/?review=target&qa`,
  media: "high-texture", vp: "1440x900",
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--side=")) opts.side = a.slice(7);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--repeats=")) opts.repeats = Number(a.slice(10));
  else if (a.startsWith("--local=")) opts.local = a.slice(8);
  else if (a.startsWith("--label=")) opts.label = a.slice(8);
  else if (a.startsWith("--track=")) opts.track = Number(a.slice(8));
}

/** The §五 `desktop-fast-flick` gesture, verbatim: 7 steps, 8 ms apart, -430 px. */
async function mouseDrag(page, from, dx, dy, steps, gap) {
  await page.mouse.move(from[0], from[1]);
  await page.mouse.down();
  for (let i = 1; i <= steps; i += 1) {
    await page.mouse.move(from[0] + (dx * i) / steps, from[1] + (dy * i) / steps);
    if (gap > 0) await sleep(gap);
  }
  await page.mouse.up();
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const { asset } = assetFor(opts.media);
const url = opts.side === "target" ? TARGET_URL : opts.local;
const dir = path.join(opts.out, opts.side + (opts.label ? `-${opts.label}` : ""));
await mkdir(dir, { recursive: true });
const index = { side: opts.side, label: opts.label, url, media: opts.media, vp: opts.vp,
                gesture: "mouse, 7 steps of -61.43 px, 8 ms apart, from (1020,460)",
                startedAt: new Date().toISOString(), runs: [] };
const [w, h] = opts.vp.split("x").map(Number);

for (let rep = 0; rep < opts.repeats; rep += 1) {
  const { ctx, page, errors } = await openMatched(browser, {
    side: opts.side, url, vp: opts.vp, asset, mediaLog: [],
    initScripts: [RESIZE_INSTRUMENT],
  });
  await pinMatched(page, { side: opts.side, labels: true, mediaTime: 2,
    pointer: [Math.round(w / 2), Math.round(h / 2)] });
  const matched = await readMatched(page, opts.side);
  await page.evaluate(FRAME_RECORDER);
  await sleep(1200);
  const tracked = await page.evaluate((n) => window.__FMF.select(n), opts.track);
  await page.evaluate(() => { window.__FMT.reset(); window.__FMF.start(); });

  await mouseDrag(page, [1020, 460], -430, 0, 7, 8);
  await sleep(3400);

  const frames = await page.evaluate(() => window.__FMF.stop());
  const data = await page.evaluate(() => window.__FMF.frames);
  const trace = await page.evaluate(() => window.__FMT.drain());
  const release = opts.side === "local"
    ? await page.evaluate(() => {
        const m = window.__ILG_QA__.getMotionTruth();
        return { releaseRecords: m.releaseRecords ?? null,
                 motionSteps: m.motionSteps ?? null,
                 lastReleaseStep: m.lastReleaseStep ?? null,
                 releaseVelocity: [m.releaseVelocityX ?? null, m.releaseVelocityY ?? null] };
      })
    : null;
  const file = `flick-r${rep}.json`;
  await writeFile(path.join(dir, file), JSON.stringify({
    side: opts.side, label: opts.label, repeat: rep, vp: opts.vp,
    copyBodySha: matched.copyBodySha,
    mediaFrozenAt: matched.videos.concat(matched.targetVideos).map((v) => v.t),
    tracked, frames: data, trace, release, errors: errors.slice(0, 5),
  }));
  index.runs.push({ repeat: rep, file: `${path.basename(dir)}/${file}`, frames,
    input: trace.input.length, errors: errors.slice(0, 3) });
  console.log(`[${opts.side}${opts.label ? "/" + opts.label : ""}] r${rep}: `
    + `${frames} frames, ${trace.input.length} input callbacks, ${errors.length} errors`);
  await ctx.close();
}
await browser.close();
const idx = path.join(opts.out, `index-${opts.side}${opts.label ? "-" + opts.label : ""}.json`);
await writeFile(idx, JSON.stringify(index, null, 1));
console.log(`-> ${idx}`);
