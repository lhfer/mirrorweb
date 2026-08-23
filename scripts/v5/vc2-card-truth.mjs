#!/usr/bin/env node
/**
 * Visual Convergence Sprint 2 §五 -- dynamic card geometry, per frame, per card.
 *
 * Sprint 1 answered "does the grid move the same way?" with a global FFT
 * phase correlation over the whole frame. §一.6 rejected that answer, and
 * correctly: a global displacement is blind to the things a viewer actually
 * sees come apart -- one card's own path, the gap between two cards, the
 * dolly's effect on projected size, and the stagger between rows. A global
 * correlation would read identically whether the cards moved together or
 * drifted apart around a common mean.
 *
 * So this instrument reads the cards themselves. On BOTH pages, with ONE
 * reader: a block of up to ten neighbouring cards around the viewport centre
 * is selected by a purely geometric rule at rest (nearest to centre, then the
 * nine nearest to that anchor, ordered row-major), and every animation frame
 * records, for each of them, the full sixteen numbers of its CSS3D matrix and
 * the browser's own projected screen rect. Everything §五 asks for -- centre,
 * projected size, scale, rotation, depth, neighbours, gutters, stagger,
 * distance to centre -- is derived from those two records offline, so the
 * derivation is one piece of code applied to two identical inputs.
 *
 * Media and copy are matched (§三) for every run, so nothing recorded here can
 * be an artefact of different content.
 *
 * Usage:
 *   vc2-card-truth.mjs --side=target|local [--out=<dir>] [--repeats=N]
 *                      [--scenarios=a,b,..] [--local=<url>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { SCENARIOS, sleep } from "./vc2_scenarios.mjs";
import { TARGET_URL, LOCAL_ORIGIN, assetFor, openMatched, pinMatched, readMatched }
  from "./vc2_matched.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  side: "target", repeats: 1, track: 10,
  out: path.join(REPO, "artifacts/visual-convergence/card-truth"),
  local: `${LOCAL_ORIGIN}/?review=target&qa`,
  scenarios: SCENARIOS.map((s) => s.key),
  media: "high-texture",
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--side=")) opts.side = a.slice(7);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--repeats=")) opts.repeats = Number(a.slice(10));
  else if (a.startsWith("--scenarios=")) opts.scenarios = a.slice(12).split(",");
  else if (a.startsWith("--local=")) opts.local = a.slice(8);
  else if (a.startsWith("--media=")) opts.media = a.slice(8);
  else if (a.startsWith("--track=")) opts.track = Number(a.slice(8));
}

/**
 * In-page recorder. Installed after the page has settled, so its rAF callback
 * is registered after the page's own and therefore runs after the page has
 * written this frame's transforms.
 */
function installCardRecorder() {
  const R = { armed: false, frames: [], tracked: [], t0: 0, resizes: [] };
  window.__VC2T = R;

  const centreOf = (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2, r };
  };

  /** Geometric, side-agnostic selection of the tracked block. */
  R.select = (n) => {
    const S = window.__VC2;
    S.discover();
    const vis = S.cards.filter((c) => c.el.style.visibility !== "hidden");
    const rows = vis.map((c) => ({ c, ...centreOf(c.el) }))
      .filter((x) => x.r.width > 1 && x.r.height > 1);
    if (!rows.length) return [];
    const vcx = innerWidth / 2, vcy = innerHeight / 2;
    const anchor = rows.slice().sort((a, b) =>
      Math.hypot(a.x - vcx, a.y - vcy) - Math.hypot(b.x - vcx, b.y - vcy))[0];
    const near = rows.slice().sort((a, b) =>
      Math.hypot(a.x - anchor.x, a.y - anchor.y)
      - Math.hypot(b.x - anchor.x, b.y - anchor.y)).slice(0, n);
    const rowTol = Math.max(...near.map((x) => x.r.height)) * 0.6;
    near.sort((a, b) => (Math.round(a.y / rowTol) - Math.round(b.y / rowTol)) || (a.x - b.x));
    R.tracked = near.map((x, i) => ({ rank: i, code: x.c.code, el: x.c.el }));
    return near.map((x, i) => ({
      rank: i, code: x.c.code,
      restCentre: [+x.x.toFixed(3), +x.y.toFixed(3)],
      restRect: [+x.r.x.toFixed(3), +x.r.y.toFixed(3),
                 +x.r.width.toFixed(3), +x.r.height.toFixed(3)],
    }));
  };

  const mat = (s) => {
    if (!s) return null;
    const k = s.indexOf("matrix3d(");
    if (k < 0) return null;
    const parts = s.slice(k + 9, s.indexOf(")", k)).split(",");
    if (parts.length !== 16) return null;
    return parts.map((p) => +(+p).toFixed(4));
  };

  const loop = (rafTime) => {
    if (!R.armed) return;
    const t = +((rafTime ?? performance.now()) - R.t0).toFixed(2);
    const cards = [];
    for (const tr of R.tracked) {
      const hidden = tr.el.style.visibility === "hidden";
      const m = mat(tr.el.style.transform);
      const r = tr.el.getBoundingClientRect();
      cards.push([tr.rank, hidden ? 1 : 0, m,
        [+r.x.toFixed(3), +r.y.toFixed(3), +r.width.toFixed(3), +r.height.toFixed(3)]]);
    }
    R.frames.push([t, innerWidth, innerHeight, cards]);
    requestAnimationFrame(loop);
  };

  R.start = () => {
    R.frames.length = 0;
    R.t0 = performance.now();
    R.armed = true;
    requestAnimationFrame(loop);
  };
  R.stop = () => { R.armed = false; return R.frames.length; };
  return true;
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const { asset } = assetFor(opts.media);
const url = opts.side === "target" ? TARGET_URL : opts.local;
await mkdir(path.join(opts.out, opts.side), { recursive: true });
const index = { side: opts.side, url, media: opts.media, track: opts.track,
                startedAt: new Date().toISOString(), runs: [] };

for (const sc of SCENARIOS.filter((s) => opts.scenarios.includes(s.key))) {
  for (let rep = 0; rep < opts.repeats; rep += 1) {
    const { ctx, page, errors } = await openMatched(browser,
      { side: opts.side, url, vp: sc.vp, asset, mediaLog: [] });
    const [w, h] = sc.vp.split("x").map(Number);
    await pinMatched(page, { side: opts.side, labels: true, mediaTime: 2,
      pointer: [Math.round(w / 2), Math.round(h / 2)] });
    const matched = await readMatched(page, opts.side);
    await page.evaluate(installCardRecorder);
    await sleep(1200);
    const tracked = await page.evaluate((n) => window.__VC2T.select(n), opts.track);
    const cdp = sc.touch ? await ctx.newCDPSession(page) : null;
    await page.evaluate(() => window.__VC2T.start());
    await sc.run(page, cdp, w, h);
    await sleep(sc.tailMs);
    const frames = await page.evaluate(() => window.__VC2T.stop());
    const data = await page.evaluate(() => window.__VC2T.frames);
    const file = `${sc.key}${opts.repeats > 1 ? `-r${rep}` : ""}.json`;
    await writeFile(path.join(opts.out, opts.side, file), JSON.stringify({
      side: opts.side, scenario: sc.key, repeat: rep, vp: sc.vp,
      resizeTo: sc.resizeTo ?? null, what: sc.what,
      copyBodySha: matched.copyBodySha, mediaFrozenAt: matched.videos.concat(matched.targetVideos)
        .map((v) => v.t), tracked, frames: data,
    }));
    index.runs.push({ scenario: sc.key, repeat: rep, file: `${opts.side}/${file}`,
                      vp: sc.vp, frames, tracked: tracked.length,
                      copyBodySha: matched.copyBodySha, errors: errors.slice(0, 3) });
    console.log(`[${opts.side}] ${sc.key} r${rep}: ${frames} frames, ${tracked.length} cards`);
    await ctx.close();
  }
}
await browser.close();
await writeFile(path.join(opts.out, `index-${opts.side}.json`), JSON.stringify(index, null, 1));
console.log(`-> ${opts.out}/index-${opts.side}.json`);
