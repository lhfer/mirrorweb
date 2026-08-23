#!/usr/bin/env node
/**
 * Final Motion Convergence §三 -- the orientation relayout, recorded.
 *
 * Same scenario the §五 recorder ran (`orientation-change`: drag, live
 * portrait -> landscape resize, drag again), same matched media and copy, same
 * tracked block -- plus the scheduling instrument, which is what §三 actually
 * asks for and what the geometry recorder alone could not see: which callback
 * ran, in what order, and for how long.
 *
 * Both sides get the identical instrument. A difference in the output is a
 * difference in the pages.
 *
 * `--suppress` is the attribution control. A frame gap at the flip says the
 * page stalled; it does not say which layer stalled it. Taking one layer out
 * of the document immediately before the flip and re-measuring does. The
 * suppressed run is a MEASUREMENT ONLY -- it is not a candidate state and its
 * geometry is not compared with anything.
 *
 * Usage:
 *   fm-orientation-trace.mjs --side=target|local [--repeats=5] [--out=<dir>]
 *                            [--local=<url>] [--label=<name>]
 *                            [--suppress=labels|canvas]
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
  side: "target", repeats: 5, track: 10, label: "", suppress: "", flip: "single",
  out: path.join(REPO, "artifacts/final-motion/orientation"),
  local: `${LOCAL_ORIGIN}/?review=target&qa`,
  media: "high-texture",
  vp: "390x844", to: "844x390",
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--side=")) opts.side = a.slice(7);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--repeats=")) opts.repeats = Number(a.slice(10));
  else if (a.startsWith("--local=")) opts.local = a.slice(8);
  else if (a.startsWith("--label=")) opts.label = a.slice(8);
  else if (a.startsWith("--track=")) opts.track = Number(a.slice(8));
  else if (a.startsWith("--suppress=")) opts.suppress = a.slice(11);
  else if (a.startsWith("--flip=")) opts.flip = a.slice(7);
}

/**
 * `single` is `page.setViewportSize` once -- one resize event, which is what
 * the §五 scenario dispatched and what the pre-registered numbers were taken
 * on. `settling` is the shape a real device rotation actually has: the
 * interface passes through an intermediate box and the page receives several
 * resize events before the final one. Both are dispatched identically on both
 * pages; neither is a candidate-only condition.
 */
const FLIP_STEPS = {
  single: (a, b) => [b],
  settling: (a, b) => [[b[0], a[1]], [b[0], Math.round((a[1] + b[1]) / 2)], b],
};

/**
 * Take one layer out of the document, by its role rather than by any
 * page-specific id: the CSS3D card layer is the common ancestor of the cards
 * the copy injector already found, and the canvas is the canvas.
 */
const SUPPRESS = (which) => {
  const S = window.__VC2;
  if (which === "labels") {
    S.discover();
    const els = S.cards.map((c) => c.el);
    if (!els.length) return { suppressed: null, n: 0 };
    let host = els[0].parentElement;
    while (host && !els.every((e) => host.contains(e))) host = host.parentElement;
    if (!host) return { suppressed: null, n: 0 };
    host.style.display = "none";
    return { suppressed: "labels", n: els.length, host: host.className || host.tagName };
  }
  if (which === "canvas") {
    const cs = [...document.querySelectorAll("canvas")];
    cs.forEach((c) => { c.style.display = "none"; });
    return { suppressed: "canvas", n: cs.length };
  }
  return { suppressed: null, n: 0 };
};

/** The §五 `orientation-change` gesture, verbatim. */
async function touchDrag(cdp, from, dx, dy, steps, gap) {
  const pt = (x, y) => [{ x, y, radiusX: 12, radiusY: 12, force: 1 }];
  await cdp.send("Input.dispatchTouchEvent",
    { type: "touchStart", touchPoints: pt(from[0], from[1]) });
  for (let i = 1; i <= steps; i += 1) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove",
      touchPoints: pt(from[0] + (dx * i) / steps, from[1] + (dy * i) / steps) });
    if (gap > 0) await sleep(gap);
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const { asset } = assetFor(opts.media);
const url = opts.side === "target" ? TARGET_URL : opts.local;
const dir = path.join(opts.out, opts.side + (opts.label ? `-${opts.label}` : ""));
await mkdir(dir, { recursive: true });
const index = { side: opts.side, label: opts.label, url, media: opts.media,
                vp: opts.vp, resizeTo: opts.to,
                startedAt: new Date().toISOString(), runs: [] };

const [w, h] = opts.vp.split("x").map(Number);
const [w2, h2] = opts.to.split("x").map(Number);

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
  const cdp = await ctx.newCDPSession(page);

  // Everything before this point -- load, freeze, copy injection, selection --
  // is setup, and its callbacks would drown the twenty that matter.
  await page.evaluate(() => { window.__FMT.reset(); window.__FMF.start(); });

  await touchDrag(cdp, [320, 560], -200, 0, 20, 24);
  await sleep(700);
  const suppressed = opts.suppress
    ? await page.evaluate(SUPPRESS, opts.suppress)
    : null;
  if (opts.suppress) await sleep(400);
  const flipAt = await page.evaluate(() => performance.now() - window.__FMT.t0);
  const steps = (FLIP_STEPS[opts.flip] ?? FLIP_STEPS.single)([w, h], [w2, h2]);
  for (const [sw, sh] of steps) {
    await page.setViewportSize({ width: sw, height: sh });
    if (steps.length > 1) await sleep(40);
  }
  await sleep(1800);
  await touchDrag(cdp, [700, 200], -260, 0, 22, 24);
  await sleep(2000);

  const frames = await page.evaluate(() => window.__FMF.stop());
  const data = await page.evaluate(() => window.__FMF.frames);
  const trace = await page.evaluate(() => window.__FMT.drain());
  const file = `orientation-r${rep}.json`;
  await writeFile(path.join(dir, file), JSON.stringify({
    side: opts.side, label: opts.label, repeat: rep, vp: opts.vp, resizeTo: opts.to,
    what: "drag, then a live portrait -> landscape resize, then drag again",
    copyBodySha: matched.copyBodySha,
    mediaFrozenAt: matched.videos.concat(matched.targetVideos).map((v) => v.t),
    // Where the harness asked for the flip, in the instrument's own clock.
    flipRequestedAtMs: +flipAt.toFixed(3), flipMode: opts.flip, flipSteps: steps,
    suppress: opts.suppress || null, suppressed,
    // Present only on a build that carries the guard; null everywhere else,
    // which is itself the before/after distinction.
    resizeScheduling: opts.side === "local"
      ? await page.evaluate(() => window.__ILG_QA__.getV4State().resizeScheduling ?? null)
      : null,
    tracked, frames: data, trace, errors: errors.slice(0, 5),
  }));
  index.runs.push({ repeat: rep, file: `${path.basename(dir)}/${file}`, frames,
    tracked: tracked.length, listeners: trace.listeners.length,
    longtasks: trace.longtasks.length, errors: errors.slice(0, 3) });
  console.log(`[${opts.side}${opts.label ? "/" + opts.label : ""}] r${rep}: `
    + `${frames} frames, ${trace.listeners.length} resize listener calls, `
    + `${trace.longtasks.length} longtasks, ${errors.length} errors`);
  await ctx.close();
}
await browser.close();
const idx = path.join(opts.out, `index-${opts.side}${opts.label ? "-" + opts.label : ""}.json`);
await writeFile(idx, JSON.stringify(index, null, 1));
console.log(`-> ${idx}`);
