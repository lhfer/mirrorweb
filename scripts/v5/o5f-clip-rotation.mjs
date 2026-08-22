#!/usr/bin/env node
/**
 * O5F §十A -- clip-rotation captures for the per-clip portrait attribution.
 *
 * The frozen clip-2 crop (focusY 0.46, zoom 1.06) is the one per-clip
 * difference in the candidate: clips 0 and 1 carry the Target's own centred
 * cover, and under the deterministic media routes all three clips play the
 * SAME content. So a per-clip residual difference can only come from the
 * crop -- if it is isolated to clip-2 cards, §十A classifies it as a FROZEN
 * MEDIA-CROP PRODUCT DEVIATION and optics are not touched.
 *
 * The layout is periodic in one cell: scrolling exactly +cellW moves every
 * card one column on, so the SAME screen rect is occupied by the next pool
 * slot -- same geometry, next clip. Three captures (offset 0, +cellW,
 * +2*cellW) put all three clips into each scored rect, against ONE sealed
 * Target reference for that rect (the Target's cards are all centred-cover
 * over identical media, so its reference is clip-independent). Nothing is
 * assumed: each capture records which slot/clip actually occupies each rect
 * and how far the rect moved, read off the engine.
 *
 * Usage: o5f-clip-rotation.mjs --local=<origin> --cellw=<vp:px,vp:px,...>
 *        [--out=<dir>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, asset: "bw-split", freeze: 4, cellw: null,
  out: path.join(REPO, "artifacts/optics-o5f/clip-rotation") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local || !opts.cellw) {
  console.error("--local and --cellw are required "
    + "(cellW per viewport, from source_layout.layout)");
  process.exit(2);
}
const CELLW = Object.fromEntries(opts.cellw.split(",").map((s) => {
  const [vp, px] = s.split(":");
  return [vp, Number(px)];
}));

// 844x390 has no fully-visible card and is reported NOT_APPLICABLE by the
// scorer; capturing it would measure nothing.
const VIEWPORTS = ["390x844", "1440x900", "700x700"];
const ROTATIONS = [0, 1, 2];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

for (const vp of VIEWPORTS) {
  const [w, h] = vp.split("x").map(Number);
  const mobile = w < 500 || h < 500;
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    hasTouch: mobile, ...(mobile ? { isMobile: true } : {}) });
  await installLocalRoutes(ctx, loadAsset(opts.asset), null);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
    + "&reflectionSupport=geometry&bodyFloorMode=current"
    + "&opticalBody=target-source-unclamped",
    { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(
    () => window.__ILG_QA__?.getState?.()?.ready === true, undefined,
    { timeout: 180000 });
  await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
  // Text-ink and footer boxes, read BEFORE the label layer is hidden: §十E
  // needs the boxes of the actual TYPE -- rule, title, deck -- not the
  // card-sized label container, and a hidden layer reads zero-sized boxes.
  // The frozen layout is the Target's own (source contract 36/36), so these
  // boxes describe the Target's typography footprint too.
  const labelTruth = await page.evaluate(() => {
    const box = (el) => {
      const r = el.getBoundingClientRect();
      return [r.x, r.y, r.x + r.width, r.y + r.height];
    };
    return {
      cards: [...document.querySelectorAll(".tile-card-se")].map((c) => ({
        card: box(c),
        visible: c.style.visibility !== "hidden",
        texts: [...c.querySelectorAll(".se-rule, .se-title, .se-deck")]
          .map((t) => ({ cls: t.className, box: box(t) })),
      })),
      footer: [...document.querySelectorAll(
        ".page-footer .experiment-link, .page-footer .cta-link, "
        + ".page-footer .cta-arrow, .page-footer .brand-word")]
        .map((t) => ({ cls: t.className, box: box(t) })),
    };
  });
  await page.evaluate((t) =>
    window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    qa.pause();
    qa.setShellMode("off");
    qa.setRenderLayers({ labels: false });
  });

  const shots = [];
  for (const rot of ROTATIONS) {
    const offsetX = rot * (CELLW[vp] ?? 0);
    await page.evaluate((x) => {
      const qa = window.__ILG_QA__;
      qa.setVelocity(0, 0);
      qa.setOffset(x, 0);
      qa.jumpPointer(0, 0);
      qa.setTime(4);
      qa.renderOnce(); qa.renderOnce();
    }, offsetX);
    await page.waitForTimeout(120);
    const file = `rot${rot}-${vp}.png`;
    await page.screenshot({ path: path.join(opts.out, file) });
    const truth = await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      const rects = qa.getCardPlaneRects?.() ?? [];
      const body = qa.getCardBodyTruth?.() ?? null;
      const cards = (body?.grid?.cards ?? body?.cards ?? []).map((c) => ({
        slotIndex: c.slotIndex, clipIndex: c.clipIndex, active: c.active,
      }));
      return { rects: JSON.parse(JSON.stringify(rects)), cards };
    });
    shots.push({ rot, offsetX, file, engine: truth });
  }
  records.push({ vp, cellW: CELLW[vp] ?? null, labelTruth, shots,
    errorCount: errors.length, errors: errors.slice(0, 4) });
  console.log(`${vp}: 3 rotations captured (errors ${errors.length})`);
  await ctx.close();
}

await writeFile(path.join(opts.out, "clip-rotation-manifest.json"),
  JSON.stringify({
    what: "O5F §十A clip-rotation captures: the candidate at scroll offsets "
        + "0, +cellW and +2*cellW, so every scored rect is occupied by each "
        + "of the three clips in turn while the geometry stays put. The "
        + "Target reference is the sealed rest capture -- its cards are "
        + "centred-cover over identical media, so it is clip-independent.",
    local: opts.local, asset: opts.asset, freeze: opts.freeze,
    lane: "target-source-unclamped",
    cellW: CELLW, viewports: VIEWPORTS, rotations: ROTATIONS,
    records,
  }, null, 1));
console.log(`-> ${opts.out}`);
await browser.close();
