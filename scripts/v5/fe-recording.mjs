#!/usr/bin/env node
/**
 * Final Entry §十一 -- the six required recordings.
 *
 * Every other recorder in this repo starts filming after the page has settled.
 * Three of these six are of the load itself, so the context has to be recording
 * before the first navigation -- which is why this exists rather than a flag on
 * an existing script.
 *
 *   1 cold desktop load        both sides
 *   2 warm desktop load        both sides
 *   3 cold mobile load         both sides
 *   4 slow drag after entry    both sides
 *   5 orientation change       both sides
 *   6 candidate frame pacing   candidate only, and deliberately WITH the
 *                              status readout visible -- it is the subject of
 *                              the clip, not a contaminant. It is the only one
 *                              of the six that is not a comparison, and it is
 *                              labelled that way in the package.
 *
 * Matched on both sides for 1-5: one locally generated media asset serves both
 * pages, one injected copy set, same viewport, DPR 1, labels on, footer on, no
 * debug overlay. Normal speed -- nothing here slows a gesture down or steps a
 * frame at a time.
 *
 * Usage: fe-recording.mjs --side=target|local [--local=<origin>] [--out=<dir>]
 *                         [--only=1,2,3]
 */
import { mkdir, writeFile, rename } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { TARGET_URL, LOCAL_ORIGIN, MOBILE_UA, MATCHED_COPY, COPY_INJECTOR, assetFor }
  from "./vc2_matched.mjs";
import { installTargetRoutes, installLocalRoutes, TARGET_VIDEO_HOOK }
  from "./o2_media_routes.mjs";
import { runSequence, sleep } from "./m2_sequences.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { side: "target", local: LOCAL_ORIGIN, only: "",
               out: path.join(REPO, "artifacts/final-entry/recordings"),
               media: "high-texture" };
for (const a of process.argv.slice(2)) {
  const eq = a.indexOf("=");
  const k = (eq < 0 ? a : a.slice(0, eq)).replace(/^--/, "");
  const v = eq < 0 ? "" : a.slice(eq + 1);
  if (k in opts) opts[k] = v;
}

const PLAN = [
  { id: 1, name: "cold-desktop-load", vp: [1440, 900], warm: false, scene: "load" },
  { id: 2, name: "warm-desktop-load", vp: [1440, 900], warm: true, scene: "load" },
  { id: 3, name: "cold-mobile-load", vp: [390, 844], warm: false, scene: "load" },
  { id: 4, name: "slow-drag-after-entry", vp: [1440, 900], warm: false,
    scene: "sequence", sequence: "slow-horizontal-drag" },
  { id: 5, name: "orientation-change", vp: [390, 844], warm: false,
    scene: "orientation", to: [844, 390] },
  { id: 6, name: "candidate-frame-pacing", vp: [1440, 900], warm: false,
    scene: "pacing", localOnly: true, status: true },
];

const only = opts.only ? new Set(opts.only.split(",").map(Number)) : null;
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const { asset } = assetFor(opts.media);
const index = { side: opts.side, media: opts.media, clips: [] };

for (const step of PLAN) {
  if (only && !only.has(step.id)) continue;
  if (step.localOnly && opts.side !== "local") continue;
  const [width, height] = step.vp;
  const touch = width < 768;
  const dir = path.join(opts.out, opts.side, step.name);
  await mkdir(dir, { recursive: true });
  const ctx = await browser.newContext({
    viewport: { width, height }, deviceScaleFactor: 1,
    hasTouch: touch, isMobile: touch, ...(touch ? { userAgent: MOBILE_UA } : {}),
    recordVideo: { dir, size: { width, height } },
  });
  if (opts.side === "target") await installTargetRoutes(ctx, asset, []);
  else await installLocalRoutes(ctx, asset, []);
  if (opts.side === "target") await ctx.addInitScript(TARGET_VIDEO_HOOK);
  await ctx.addInitScript(COPY_INJECTOR);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message)));

  const url = opts.side === "target" ? TARGET_URL
    : `${opts.local}/?review=target${step.status ? "&status=1" : ""}&qa`;

  // A warm clip needs a first navigation to fill the cache. It is thrown away,
  // but it happens inside the recorded context, so the finished clip carries it
  // as a lead-in. Clips ship whole -- nothing here or in fe-package.py trims
  // them -- so the two sides of a warm pair start at different wall-clock
  // offsets. That difference is real and unaltered; the entry windows the gate
  // scores come from the traces, not from the video.
  if (step.warm) {
    await page.goto(url, { waitUntil: "load", timeout: 180000 });
    await sleep(opts.side === "target" ? 9000 : 5000);
    index.clips.push({ warmLeadIn: true });
  }

  const t0 = Date.now();
  await page.goto(url, { waitUntil: "commit", timeout: 180000 });
  const settleMs = opts.side === "target" ? 11000 : 7000;
  await sleep(settleMs);

  if (step.scene === "sequence" || step.scene === "pacing") {
    await page.evaluate((c) => window.__VC2?.apply(c), MATCHED_COPY).catch(() => {});
    const cdp = await ctx.newCDPSession(page);
    const seqs = step.scene === "pacing"
      ? ["slow-horizontal-drag", "fast-flick", "reverse-flick"]
      : [step.sequence];
    for (const s of seqs) {
      const { tailMs } = await runSequence(page, cdp, s, width, height);
      await sleep(tailMs);
    }
  } else if (step.scene === "orientation") {
    await page.evaluate((c) => window.__VC2?.apply(c), MATCHED_COPY).catch(() => {});
    const cdp = await ctx.newCDPSession(page);
    await runSequence(page, cdp, "touch-drag-release", width, height).catch(() => {});
    await sleep(1200);
    await page.setViewportSize({ width: step.to[0], height: step.to[1] });
    await sleep(2600);
    await runSequence(page, cdp, "touch-drag-release", step.to[0], step.to[1])
      .catch(() => {});
    await sleep(2200);
  }

  const video = page.video();
  await ctx.close();
  const raw = video ? await video.path() : null;
  let file = null;
  if (raw) {
    file = path.join(dir, "clip.webm");
    await rename(raw, file).catch(() => { file = raw; });
  }
  index.clips.push({
    id: step.id, name: step.name, viewport: step.vp, warm: Boolean(step.warm),
    scene: step.scene, statusReadout: Boolean(step.status),
    file: file ? path.relative(REPO, file) : null,
    wallMs: Date.now() - t0, errors,
  });
  console.log(`${opts.side} ${step.id} ${step.name}  ${file ? "ok" : "NO VIDEO"} `
    + `err=${errors.length}`);
}

await browser.close();
await writeFile(path.join(opts.out, opts.side, "index.json"),
                JSON.stringify(index, null, 1));
console.log(`-> ${path.join(opts.out, opts.side)}`);
