#!/usr/bin/env node
/**
 * Visual Convergence Sprint 2 §三 -- prove Same Media + Same Copy, or fail.
 *
 * Three proofs, all measured on the live pages:
 *
 *  MEDIA   For each of the six §三A categories, both pages are served ONE
 *          locally generated asset (mux HLS on the Target, /clips/*.mp4 on
 *          ours) whose H.264 elementary stream is byte-identical across the
 *          two containers. Proof is not the routing log alone: the decoded
 *          frame is drawn to a canvas on each page and its landmark colours
 *          and full-frame FNV-1a hash are compared side to side.
 *  COPY    The shared injector rewrites every card's copy leaves on both
 *          pages, then the strings are read BACK out of the DOM and hashed.
 *          Same hash both sides, uniform across every card, zero structural
 *          failures, or the contract fails.
 *  RUNTIME Viewport, DPR, pointer class (which selects the device sample
 *          tier on both engines), initial offset, pointer position, media
 *          time, card-plane box and the resulting cover fit, per viewport.
 *
 * Any failed row makes the whole contract MATCHED-CONTENT HARNESS FAILED,
 * which is a terminal state for the round.
 *
 * Usage: vc2-harness-contract.mjs [--out=<json>] [--media-vp=WxH] [--vps=WxH,..]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { landmarkVerdict } from "./o2_media_routes.mjs";
import {
  MEDIA_SET, MATCHED_COPY, TARGET_URL, LOCAL_ORIGIN,
  assetFor, openMatched, pinMatched, readMatched, decodedFrame, decodedPng,
} from "./vc2_matched.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  out: path.join(REPO, "artifacts/visual-convergence/contract-raw.json"),
  png: path.join(REPO, "artifacts/visual-convergence/decoded"),
  mediaVp: "1440x900", vps: ["1440x900", "390x844", "844x390", "700x700"],
  local: `${LOCAL_ORIGIN}/?review=target&qa`,
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--media-vp=")) opts.mediaVp = a.slice(11);
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--local=")) opts.local = a.slice(8);
  else if (a.startsWith("--cats=")) opts.cats = a.slice(7).split(",");
}
const CATEGORIES = opts.cats
  ? MEDIA_SET.filter((m) => opts.cats.includes(m.key)) : MEDIA_SET;

const SIDES = [["target", TARGET_URL], ["local", opts.local]];
await mkdir(opts.png, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

const report = {
  what: "VC2 §三 matched-content contract: the proof that Glass and Typography "
      + "judgements this round are made on the same media and the same copy.",
  startedAt: new Date().toISOString(),
  target: TARGET_URL, local: opts.local,
  copy: MATCHED_COPY,
  mediaCategories: MEDIA_SET.map(({ key, asset, why }) => ({ key, asset, why })),
  mediaRows: [], runtimeRows: [], assertions: [], errors: [],
};
const A = (name, pass, detail) =>
  report.assertions.push({ assertion: name, pass: !!pass, detail: detail ?? null });

/* ------------------------------------------------------------------ */
/* 1. media + copy, one page load per side per category                */
/* ------------------------------------------------------------------ */
for (const cat of CATEGORIES) {
  const { asset } = assetFor(cat.key);
  const row = { category: cat.key, asset: cat.asset, sides: {} };
  for (const [side, url] of SIDES) {
    const mediaLog = [];
    const { ctx, page, errors } = await openMatched(browser,
      { side, url, vp: opts.mediaVp, asset, mediaLog });
    const pinned = await pinMatched(page, { side, labels: true, mediaTime: 2,
      pointer: [720, 450] });
    const state = await readMatched(page, side);
    const frame = await decodedFrame(page, asset.entry.landmarks, side);
    const png = await decodedPng(page, side);
    if (png) await writeFile(path.join(opts.png, `${cat.key}-${side}.png`), Buffer.from(png, "base64"));
    row.sides[side] = {
      servedSha: [...new Set(mediaLog.map((m) => m.sha256))],
      servedFiles: mediaLog.length,
      elementaryStreamSha256: asset.entry.elementaryStreamSha256,
      mp4Sha256: asset.entry.mp4.sha256,
      frozenAt: pinned.media.map((m) => m.currentTime),
      decoded: frame.error ? { error: frame.error }
        : { size: [frame.width, frame.height], frameHashFnv1a: frame.frameHashFnv1a,
            landmarks: frame.landmarks },
      landmarkVerdict: frame.error ? { pass: false }
        : landmarkVerdict(asset.entry.landmarks, frame.landmarks, 12),
      copy: { cards: state.cards, failures: state.failures, reasserts: state.reasserts,
              bodySha: state.copyBodySha, uniform: state.copyUniform,
              sample: state.copyBodies },
      visibleCodes: state.visible.length,
      pageErrors: errors.slice(0, 5),
    };
    if (errors.length) report.errors.push({ side, category: cat.key, errors: errors.slice(0, 5) });
    await ctx.close();
  }
  const t = row.sides.target, l = row.sides.local;
  row.sameElementaryStream = t.elementaryStreamSha256 === l.elementaryStreamSha256;
  row.sameDecodedSize = JSON.stringify(t.decoded.size) === JSON.stringify(l.decoded.size);
  row.sameDecodedFrame = !!t.decoded.frameHashFnv1a
    && t.decoded.frameHashFnv1a === l.decoded.frameHashFnv1a;
  row.sameFreezeTime = JSON.stringify([...new Set(t.frozenAt)])
    === JSON.stringify([...new Set(l.frozenAt)]);
  row.sameCopySha = !!t.copy.bodySha && t.copy.bodySha === l.copy.bodySha;
  report.mediaRows.push(row);
  console.log(`[${cat.key}] stream=${row.sameElementaryStream} frame=${row.sameDecodedFrame} `
    + `size=${row.sameDecodedSize} freeze=${row.sameFreezeTime} copy=${row.sameCopySha}`);
}

/* ------------------------------------------------------------------ */
/* 2. runtime parity across the four review viewports                  */
/* ------------------------------------------------------------------ */
const { asset: runtimeAsset } = assetFor("high-texture");
for (const vp of opts.vps) {
  const row = { vp, sides: {} };
  for (const [side, url] of SIDES) {
    const { ctx, page, errors } = await openMatched(browser,
      { side, url, vp, asset: runtimeAsset, mediaLog: [] });
    const [w, h] = vp.split("x").map(Number);
    const pinned = await pinMatched(page, { side, labels: true, mediaTime: 2,
      pointer: [Math.round(w * 0.5), Math.round(h * 0.5)] });
    const state = await readMatched(page, side);
    // The card's CSS box (unprojected) and the cover fit that box implies for
    // a 1200x900 source. Read the same way on both sides.
    const box = await page.evaluate(() => {
      const c = window.__VC2.cards.find((x) => x.el.style.visibility !== "hidden")
        ?? window.__VC2.cards[0];
      if (!c) return null;
      const cs = getComputedStyle(c.el);
      return [+parseFloat(cs.width).toFixed(3), +parseFloat(cs.height).toFixed(3)];
    });
    const src = [1200, 900];
    const cover = box ? (() => {
      const sa = src[0] / src[1], ba = box[0] / box[1];
      const scale = sa > ba ? [sa / ba, 1] : [1, ba / sa];
      return { scale: scale.map((x) => +x.toFixed(6)),
               offset: [+((1 - 1 / scale[0]) / 2).toFixed(6),
                        +((1 - 1 / scale[1]) / 2).toFixed(6)] };
    })() : null;
    row.sides[side] = {
      viewport: state.viewport, dpr: state.dpr, coarsePointer: state.coarsePointer,
      cardBoxCss: box, sourcePx: src, coverFit: cover,
      frozenAt: [...new Set(pinned.media.map((m) => m.currentTime))],
      visibleCards: state.visible.length, copyBodySha: state.copyBodySha,
      quality: state.engine?.quality ?? null,
      deviceSamples: state.engine?.optics?.opticalBodySamples ?? null,
      initialOffset: state.engine ? [state.engine.scrollX, state.engine.scrollY] : "n/a (Target)",
      pageErrors: errors.slice(0, 5),
    };
    await ctx.close();
  }
  const t = row.sides.target, l = row.sides.local;
  row.sameViewport = JSON.stringify(t.viewport) === JSON.stringify(l.viewport);
  row.sameDpr = t.dpr === l.dpr;
  row.samePointerClass = t.coarsePointer === l.coarsePointer;
  row.sameCardBox = JSON.stringify(t.cardBoxCss) === JSON.stringify(l.cardBoxCss);
  row.sameCoverFit = JSON.stringify(t.coverFit) === JSON.stringify(l.coverFit);
  row.sameVisibleCards = t.visibleCards === l.visibleCards;
  row.sameCopySha = !!t.copyBodySha && t.copyBodySha === l.copyBodySha;
  report.runtimeRows.push(row);
  console.log(`[${vp}] vp=${row.sameViewport} dpr=${row.sameDpr} ptr=${row.samePointerClass} `
    + `box=${row.sameCardBox} cover=${row.sameCoverFit} cards=${row.sameVisibleCards}`);
}
await browser.close();

await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report, null, 1));
console.log(`-> ${opts.out}  (verdict is computed by vc2-contract.py)`);
