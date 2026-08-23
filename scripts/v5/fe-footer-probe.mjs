#!/usr/bin/env node
/**
 * Final Entry §七.10 -- "the footer does not appear too early or too late".
 *
 * The card recorder does not watch the footer, and adding it there would mean
 * re-running the whole load matrix to answer one question. This is that one
 * question: from navigation start, per frame, is the page chrome in the
 * document, what is its opacity, and where is its top edge?
 *
 * "Too early" and "too late" both need a reference, and the reference is the
 * Target: its footer (`PW`) is plain markup with no entry animation and no
 * ready gate, so it is in the tree from the first render and simply sits
 * behind the loading overlay until the overlay leaves. If ours does the same,
 * the two appear together because they appear the same way -- and if either
 * fades, ramps or waits, this shows it.
 *
 * Found by role rather than selector, so one predicate works on both pages: a
 * fixed, bottom-anchored, full-width element whose text contains the studio
 * link's caption. Both pages have exactly one.
 *
 * Usage: fe-footer-probe.mjs --side=target|local [--local=<url>] [--out=<json>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { TARGET_URL, LOCAL_ORIGIN } from "./vc2_matched.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { side: "target", local: `${LOCAL_ORIGIN}/?review=target&qa`,
               out: path.join(REPO, "artifacts/final-entry/footer"), reps: 2 };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--side=")) opts.side = a.slice(7);
  else if (a.startsWith("--local=")) opts.local = a.slice(8);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--reps=")) opts.reps = Number(a.slice(7));
}

const PROBE = `(() => {
  const R = { frames: [] };
  window.__FEF = R;
  const raf = window.requestAnimationFrame.bind(window);
  const find = () => {
    if (!document.body) return null;
    for (const el of document.body.querySelectorAll("footer, div")) {
      const t = (el.textContent || "").toUpperCase();
      if (!t.includes("AN EXPERIMENT BY")) continue;
      const cs = getComputedStyle(el);
      if (cs.position !== "fixed") continue;
      return el;
    }
    return null;
  };
  const tick = () => {
    const t = +performance.now().toFixed(2);
    const el = find();
    if (!el) R.frames.push({ t, present: false });
    else {
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      R.frames.push({ t, present: true, opacity: +parseFloat(cs.opacity).toFixed(4),
                      visibility: cs.visibility, display: cs.display,
                      top: +r.top.toFixed(1), height: +r.height.toFixed(1),
                      transform: cs.transform === "none" ? "none" : "set" });
    }
    if (R.frames.length < 4000 && !R.stop) raf(tick);
  };
  raf(tick);
})();`;

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const url = opts.side === "target" ? TARGET_URL : opts.local;
await mkdir(opts.out, { recursive: true });
const runs = [];
for (let rep = 0; rep < opts.reps; rep += 1) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 },
                                         deviceScaleFactor: 1 });
  await ctx.addInitScript(PROBE);
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: "commit", timeout: 180000 });
  await page.waitForTimeout(opts.side === "target" ? 14000 : 8000);
  const frames = await page.evaluate(() => { window.__FEF.stop = 1; return window.__FEF.frames; });
  const seen = frames.filter((f) => f.present);
  const ops = seen.map((f) => f.opacity);
  runs.push({
    rep,
    firstFrameAtMs: frames.length ? frames[0].t : null,
    firstPresentAtMs: seen.length ? seen[0].t : null,
    presentOnEveryFrameOnceSeen: seen.length
      ? frames.slice(frames.indexOf(seen[0])).every((f) => f.present) : false,
    opacityMin: ops.length ? Math.min(...ops) : null,
    opacityMax: ops.length ? Math.max(...ops) : null,
    opacityConstant: ops.length ? new Set(ops).size === 1 : null,
    transformStates: [...new Set(seen.map((f) => f.transform))],
    topEdgeStates: [...new Set(seen.map((f) => f.top))].slice(0, 6),
    heightStates: [...new Set(seen.map((f) => f.height))].slice(0, 6),
    frames: frames.length,
  });
  await ctx.close();
}
await browser.close();
const out = path.join(opts.out, `${opts.side}.json`);
await writeFile(out, JSON.stringify({ side: opts.side, url, runs }, null, 1));
for (const r of runs) {
  console.log(`${opts.side} rep${r.rep}  firstPresent=${r.firstPresentAtMs}ms `
    + `opacity ${r.opacityMin}..${r.opacityMax} constant=${r.opacityConstant} `
    + `transform=${r.transformStates.join("/")} tops=${r.topEdgeStates.length}`);
}
console.log(`-> ${out}`);
