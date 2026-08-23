#!/usr/bin/env node
/**
 * Final Entry §七 -- the entry, frame by frame, at matched progress.
 *
 * A recording shows the entry at speed. This shows it at the five moments the
 * gate scores, side by side, so a reviewer can see WHERE the two pages are at
 * the same point rather than trusting a millisecond table.
 *
 * The shots are taken relative to READY, detected in the page itself by the
 * same rule the gate uses -- the loading overlay stopping pointer events or
 * beginning to fade -- so the two sides are sampled at the same point in their
 * own entries and not at the same wall-clock time, which would only compare
 * how fast each one loaded.
 *
 * Matched: one media asset for both pages, one injected copy set, same
 * viewport, DPR 1, labels on, footer on, no debug overlay.
 *
 * Usage: fe-stills.mjs --side=target|local [--local=<origin>] [--out=<dir>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { TARGET_URL, LOCAL_ORIGIN, MOBILE_UA, MATCHED_COPY, COPY_INJECTOR, assetFor }
  from "./vc2_matched.mjs";
import { installTargetRoutes, installLocalRoutes, TARGET_VIDEO_HOOK }
  from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { side: "target", local: LOCAL_ORIGIN, media: "high-texture",
               out: path.join(REPO, "artifacts/final-entry/stills") };
for (const a of process.argv.slice(2)) {
  const eq = a.indexOf("=");
  const k = (eq < 0 ? a : a.slice(0, eq)).replace(/^--/, "");
  if (k in opts) opts[k] = a.slice(eq + 1);
}

const VIEWPORTS = [[1440, 900], [390, 844], [844, 390], [700, 700]];
/** Relative to ready. 0 is the first frame of the entry; 1400 is settled. */
const OFFSETS = [0, 120, 250, 420, 1400];

/**
 * Watch for ready in the page, by the gate's own rule. Installed before
 * navigation so it cannot miss the transition.
 */
const READY_WATCH = `(() => {
  const W = { readyAt: null };
  window.__FES = W;
  const raf = window.requestAnimationFrame.bind(window);
  const loader = () => {
    if (!document.body) return null;
    for (const el of document.body.querySelectorAll("div")) {
      const cs = getComputedStyle(el);
      if (cs.position !== "fixed") continue;
      const r = el.getBoundingClientRect();
      if (r.width < innerWidth * 0.9 || r.height < innerHeight * 0.9) continue;
      if (!/\\d{1,3}\\s*%/.test(el.textContent || "")) continue;
      return el;
    }
    return null;
  };
  const tick = () => {
    if (W.readyAt === null) {
      const el = loader();
      if (el) {
        const cs = getComputedStyle(el);
        if (cs.pointerEvents === "none" || parseFloat(cs.opacity) < 0.999) {
          W.readyAt = performance.now();
        }
      }
    }
    raf(tick);
  };
  raf(tick);
})();`;

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const { asset } = assetFor(opts.media);
const index = { side: opts.side, media: opts.media, offsetsMs: OFFSETS, shots: [] };

for (const [width, height] of VIEWPORTS) {
  const touch = width < 768;
  const ctx = await browser.newContext({
    viewport: { width, height }, deviceScaleFactor: 1,
    hasTouch: touch, isMobile: touch, ...(touch ? { userAgent: MOBILE_UA } : {}),
  });
  await ctx.addInitScript(READY_WATCH);
  if (opts.side === "target") await installTargetRoutes(ctx, asset, []);
  else await installLocalRoutes(ctx, asset, []);
  if (opts.side === "target") await ctx.addInitScript(TARGET_VIDEO_HOOK);
  await ctx.addInitScript(COPY_INJECTOR);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message)));
  const url = opts.side === "target" ? TARGET_URL : `${opts.local}/?review=target&qa`;
  const dir = path.join(opts.out, opts.side, `${width}x${height}`);
  await mkdir(dir, { recursive: true });

  await page.goto(url, { waitUntil: "commit", timeout: 180000 });
  await page.waitForFunction(() => window.__FES && window.__FES.readyAt !== null,
                             undefined, { timeout: 180000, polling: 8 });
  // Matched copy goes on BEFORE the shots, not after. These stills are what a
  // reviewer actually looks at, and §七 asks for the same copy on both sides;
  // a pair photographed with each page's own headlines is not a comparison of
  // anything but the headlines. The cards are all mounted by ready, so there
  // is something to write to. It costs a few milliseconds of the first entry
  // frame and it is paid on both pages -- the TIMING runs, which must not be
  // perturbed, are separate captures and apply their copy at the end.
  const copy = await page.evaluate((c) => window.__VC2.apply(c), MATCHED_COPY)
    .catch(() => null);

  for (const off of OFFSETS) {
    // Wait in the PAGE's own clock, so the offset is measured from its ready
    // and not from when this process noticed.
    await page.waitForFunction(
      (o) => performance.now() - window.__FES.readyAt >= o, off,
      { timeout: 60000, polling: 4 });
    // Re-apply before every shot. The injector rewrites the cards it has
    // DISCOVERED, and discovery needs a card to carry a transform -- which on
    // both pages means it has been drawn at least once. During the entry that
    // set grows: cards that were off-screen at ready arrive later still
    // carrying their own page's headlines. One application at ready therefore
    // leaves the late arrivals unmatched in exactly the frames a reviewer looks
    // at hardest. Re-applying is idempotent for the cards already rewritten and
    // is done identically on both pages.
    await page.evaluate((c) => window.__VC2.apply(c), MATCHED_COPY).catch(() => {});
    const at = await page.evaluate(() => performance.now() - window.__FES.readyAt);
    const file = path.join(dir, `t+${String(off).padStart(4, "0")}.png`);
    await page.screenshot({ path: file });
    index.shots.push({ vp: `${width}x${height}`, offsetMs: off,
                       actualRelMs: Math.round(at),
                       file: path.relative(REPO, file) });
  }
  // Read the strings back off the DOM once the shots are taken, so "same copy"
  // is a measurement of what was photographed rather than an intention. The
  // injector's MutationObserver re-asserts them if either page's own renderer
  // writes over them mid-entry, and this is what proves it did.
  const copyAfter = await page.evaluate(() => window.__VC2.read())
    .catch(() => null);
  index.shots.filter((s) => s.vp === `${width}x${height}`)
    .forEach((s) => { s.copyApplied = copy; s.copyReadBack = copyAfter; });
  console.log(`${opts.side} ${width}x${height}  ${OFFSETS.length} shots  err=${errors.length}`);
  await ctx.close();
}

await browser.close();
await mkdir(path.join(opts.out, opts.side), { recursive: true });
await writeFile(path.join(opts.out, opts.side, "index.json"),
                JSON.stringify(index, null, 1));
console.log(`-> ${path.join(opts.out, opts.side)}`);
