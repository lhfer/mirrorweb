#!/usr/bin/env node
/**
 * Final Entry Convergence §四 -- the cold/warm load matrix, recorded.
 *
 * Four conditions a side, five runs each: desktop cold, desktop warm, mobile
 * cold, mobile warm. Each run records every frame from navigation start until
 * one second after the grid stops moving.
 *
 * WHY THIS RUNS WITHOUT THE MATCHED-MEDIA ROUTES. Every other recorder in this
 * repo installs `installTargetRoutes` / `installLocalRoutes` so both pages
 * decode one identical asset. That is right when the question is optical, and
 * wrong here: those routes are fulfilled from memory on every navigation, so
 * they erase exactly the cold/warm cache difference §四 asks us to measure --
 * and on the Target the loading percentage is 90% driven by video buffering.
 * So the forensics runs on each page's own media over the real network, and
 * the §七 visual gate, which does need matched pixels, runs with the routes.
 * The card TRAJECTORY is unaffected either way: geometry does not depend on
 * what is playing inside the card.
 *
 * Usage:
 *   fe-entry-trace.mjs --side=target|local [--repeats=5] [--out=<dir>]
 *                      [--local=<url>] [--label=<name>] [--conditions=...]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { TARGET_URL, LOCAL_ORIGIN, MOBILE_UA, MATCHED_COPY, COPY_INJECTOR, assetFor }
  from "./vc2_matched.mjs";
import { installTargetRoutes, installLocalRoutes, TARGET_VIDEO_HOOK }
  from "./o2_media_routes.mjs";
import { ENTRY_RECORDER } from "./fe_entry_instrument.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const opts = {
  side: "target", repeats: 5, label: "",
  out: path.join(REPO, "artifacts/final-entry/load"),
  local: `${LOCAL_ORIGIN}/?review=target&qa`,
  conditions: "desktop-cold,desktop-warm,mobile-cold,mobile-warm",
  // §七 needs matched pixels, §四 needs a real cold cache, and the two cannot
  // both be had in one run -- the media routes are fulfilled from memory on
  // every navigation. So the gate runs pass `--routes=<category>` and the
  // forensics runs do not; which one produced a file is recorded in it.
  routes: "", media: "high-texture",
  settleMs: 90000,
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--side=")) opts.side = a.slice(7);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--repeats=")) opts.repeats = Number(a.slice(10));
  else if (a.startsWith("--local=")) opts.local = a.slice(8);
  else if (a.startsWith("--label=")) opts.label = a.slice(8);
  else if (a.startsWith("--conditions=")) opts.conditions = a.slice(13);
  else if (a.startsWith("--routes=")) { opts.routes = "1"; opts.media = a.slice(9) || opts.media; }
}

/**
 * §四's four LOAD conditions are the first four. The last two are §七's other
 * two review viewports, which the gate needs and the cold/warm question does
 * not: a landscape phone and a square. Both are cold, because a viewport's
 * effect on the entry is a layout effect and the cache does not change it.
 */
const CONDITIONS = {
  "desktop-cold": { vp: [1440, 900], warm: false },
  "desktop-warm": { vp: [1440, 900], warm: true },
  "mobile-cold": { vp: [390, 844], warm: false },
  "mobile-warm": { vp: [390, 844], warm: true },
  "landscape-cold": { vp: [844, 390], warm: false },
  "square-cold": { vp: [700, 700], warm: false },
};

/**
 * Has the entry finished?
 *
 * "Finished" is the only definition a viewer would accept: no card has moved
 * for a while. Read off the recorder's own frames so it costs one evaluate per
 * poll rather than a second measurement.
 */
const SETTLED = ([quietFrames, tolPx]) => {
  const F = window.__FE && window.__FE.frames;
  if (!F || F.length < quietFrames + 8) return false;
  const tail = F.slice(-quietFrames);
  if (!tail.every((f) => f.cards && f.cards.length >= 3)) return false;
  // The loader must be out of the way. Without this a page that has drawn its
  // first cards but not yet started the entry reads as "settled" -- the cards
  // are indeed not moving, because nothing has told them to yet.
  const last = F[F.length - 1];
  if (last.loader && last.loader.inDom && last.loader.opacity > 0.01) return false;
  const key = (f) => { const m = new Map(); for (const c of f.cards) m.set(c[0], c); return m; };
  let prev = key(tail[0]);
  for (let i = 1; i < tail.length; i += 1) {
    const cur = key(tail[i]);
    for (const [code, c] of cur) {
      const p = prev.get(code);
      if (!p) continue;
      if (Math.abs(c[1] - p[1]) > tolPx || Math.abs(c[2] - p[2]) > tolPx) return false;
    }
    prev = cur;
  }
  return true;
};

const browser = await chromium.launch({
  channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"],
});
const url = opts.side === "target" ? TARGET_URL : opts.local;
const dir = path.join(opts.out, opts.side + (opts.label ? `-${opts.label}` : ""));
await mkdir(dir, { recursive: true });
const index = {
  side: opts.side, label: opts.label, url,
  mediaRoutes: Boolean(opts.routes),
  mediaCategory: opts.routes ? opts.media : null,
  mediaNote: opts.routes
    ? "ONE locally generated asset serves both pages, plus one injected copy set"
    : "each page's own media over the real network -- see the header",
  startedAt: new Date().toISOString(), runs: [],
};

for (const cond of opts.conditions.split(",").filter(Boolean)) {
  const spec = CONDITIONS[cond];
  if (!spec) throw new Error(`unknown condition ${cond}`);
  const [width, height] = spec.vp;
  const touch = width < 768;

  for (let rep = 0; rep < opts.repeats; rep += 1) {
    const ctx = await browser.newContext({
      viewport: { width, height }, deviceScaleFactor: 1,
      hasTouch: touch, isMobile: touch, ...(touch ? { userAgent: MOBILE_UA } : {}),
    });
    await ctx.addInitScript(ENTRY_RECORDER);
    if (opts.routes) {
      const { asset } = assetFor(opts.media);
      if (opts.side === "target") await installTargetRoutes(ctx, asset, []);
      else await installLocalRoutes(ctx, asset, []);
      if (opts.side === "target") await ctx.addInitScript(TARGET_VIDEO_HOOK);
      await ctx.addInitScript(COPY_INJECTOR);
    }
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text()}`); });

    // A warm run is the SECOND navigation in one context: the first fills the
    // HTTP cache and is thrown away, and only the second is recorded. A cold
    // run is the first navigation in a context that has never loaded anything.
    if (spec.warm) {
      await page.goto(url, { waitUntil: "load", timeout: 180000 });
      await page.waitForFunction(SETTLED, [30, 0.05], { timeout: opts.settleMs, polling: 400 })
        .catch(() => {});
      await sleep(500);
    }

    const t0 = Date.now();
    await page.goto(url, { waitUntil: "commit", timeout: 180000 });
    let settled = true;
    await page.waitForFunction(SETTLED, [30, 0.05], { timeout: opts.settleMs, polling: 200 })
      .catch(() => { settled = false; });
    await sleep(1000);
    // Copy identity is asserted and READ BACK, so "same copy" is a measurement
    // rather than an intention -- and it happens after the entry, so rewriting
    // the strings cannot perturb the frames the gate scores.
    let copy = null;
    if (opts.routes) {
      copy = await page.evaluate((c) => window.__VC2.apply(c), MATCHED_COPY)
        .catch(() => null);
    }
    await page.evaluate(() => window.__FE.stop());
    const trace = await page.evaluate(() => window.__FE.drain());
    const wall = Date.now() - t0;

    const name = `${cond}-${String(rep).padStart(2, "0")}.json`;
    await writeFile(path.join(dir, name),
      JSON.stringify({ side: opts.side, cond, rep, url, viewport: spec.vp,
                       mediaRoutes: Boolean(opts.routes),
                       mediaCategory: opts.routes ? opts.media : null, copy,
                       settled, wallMs: wall, errors, trace }, null, 1));
    index.runs.push({
      file: name, cond, rep, settled, wallMs: wall,
      frames: trace.frames.length, errors: errors.length,
      overheadMs: trace.instrumentOverheadMs,
      nav: trace.nav, resources: trace.resources, fromCache: trace.fromCache,
    });
    console.log(`${opts.side} ${cond} rep${rep}  frames=${trace.frames.length} `
      + `settled=${settled} wall=${wall}ms cached=${trace.fromCache}/${trace.resources} `
      + `err=${errors.length}`);
    await ctx.close();
  }
}

await writeFile(path.join(dir, "index.json"), JSON.stringify(index, null, 1));
await browser.close();
console.log(`-> ${dir}`);
