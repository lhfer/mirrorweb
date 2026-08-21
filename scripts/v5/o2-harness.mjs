#!/usr/bin/env node
/**
 * O2 deterministic shared-media harness -- capture half.
 *
 * For every generated asset, drive BOTH pages with identical bytes
 * (o2_media_routes.mjs), freeze both at the same media time, and record:
 * served-response SHAs, frozen video state, decoded-frame landmark reads
 * (canvas, pre-glass), full decoded-frame hashes, cover-fit readbacks
 * (local: getMediaFits; target: the source-read law), and a full-frame
 * screenshot per lane for the rendered-edge cover verification
 * (o2-harness-verify.py).
 *
 * Usage: o2-harness.mjs --local=<origin> --out=<dir>
 *        [--target=<origin>] [--freeze=4]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import {
  MEDIA_DIR, TARGET_VIDEO_HOOK, decodedFrame, freezeTarget,
  installLocalRoutes, installTargetRoutes, landmarkVerdict, loadAsset,
} from "./o2_media_routes.mjs";
import { readFileSync } from "node:fs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  local: null, target: "https://infinite-liquid-glass.shader.se/?v=2",
  out: path.join(REPO, "artifacts/optics-o2/harness"), freeze: 4,
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--local=")) opts.local = a.slice(8);
  else if (a.startsWith("--target=")) opts.target = a.slice(9);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--freeze=")) opts.freeze = Number(a.slice(9));
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const manifest = JSON.parse(
  readFileSync(path.join(MEDIA_DIR, "media-manifest.json"), "utf8"));
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });

const records = [];
for (const entry of manifest.assets) {
  const asset = loadAsset(entry.name);
  // rgb-bars additionally proves the mobile (coarse-pointer, 8-video) path.
  const vps = entry.name === "rgb-bars"
    ? [[1440, 900, false], [390, 844, true]] : [[1440, 900, false]];
  for (const [w, h, mobile] of vps) {
    const rec = { asset: entry.name, viewport: `${w}x${h}`, mobile,
                  frozenMediaTime: opts.freeze };
    // ---- Target lane ----
    {
      const ctx = await browser.newContext({
        viewport: { width: w, height: h }, hasTouch: mobile,
        ...(mobile ? { isMobile: true } : {}) });
      const log = [];
      await installTargetRoutes(ctx, asset, log);
      const page = await ctx.newPage();
      await page.addInitScript(TARGET_VIDEO_HOOK);
      await page.goto(opts.target, { waitUntil: "load", timeout: 60000 });
      await page.waitForTimeout(11000);
      const frozen = await freezeTarget(page, opts.freeze);
      const decoded = await decodedFrame(page, entry.landmarks, "target");
      await page.waitForTimeout(600);
      const shot = path.join(opts.out, `target-${entry.name}-${w}x${h}.png`);
      await page.screenshot({ path: shot });
      const kinds = {};
      for (const l of log) kinds[l.file] = (kinds[l.file] ?? 0) + 1;
      rec.target = {
        videos: frozen.length,
        allFrozenAt: frozen.every((v) => Math.abs(v.currentTime - opts.freeze) < 0.05
                                          && v.paused),
        videoState: frozen.slice(0, 2),
        allDims: [...new Set(frozen.map((v) => `${v.videoWidth}x${v.videoHeight}`))],
        allDurations: [...new Set(frozen.map((v) => v.duration))],
        requestsIntercepted: log.length,
        servedFiles: Object.entries(kinds).map(([file, count]) => ({
          file, count, sha256: log.find((l) => l.file === file).sha256 })),
        interceptedUrlSample: log.slice(0, 2).map((l) => l.url),
        decoded, landmarkVerdict: landmarkVerdict(entry.landmarks, decoded.landmarks),
        screenshot: path.basename(shot),
      };
      await ctx.close();
    }
    // ---- Local lane ----
    {
      const ctx = await browser.newContext({
        viewport: { width: w, height: h }, hasTouch: mobile,
        ...(mobile ? { isMobile: true } : {}) });
      const log = [];
      await installLocalRoutes(ctx, asset, log);
      const page = await ctx.newPage();
      await page.goto(opts.local + "/?composition=sourceExact&qa",
        { waitUntil: "load", timeout: 60000 });
      await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
        undefined, { timeout: 120000 });
      await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
      const freeze = await page.evaluate(
        (t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
      await page.evaluate(() => window.__ILG_QA__.renderOnce());
      const fits = await page.evaluate(() => window.__ILG_QA__.getMediaFits());
      const v4 = await page.evaluate(() => {
        const s = window.__ILG_QA__.getV4State();
        const f = s.sourceExactFrame ?? {};
        return { planeWidth: f.planeWidth, planeHeight: f.planeHeight,
                 composition: s.composition, quality: s.quality,
                 layoutVersion: f.layoutVersion, bundleHash: f.bundleHash };
      });
      const decoded = await decodedFrame(page, entry.landmarks, "local");
      const shot = path.join(opts.out, `local-${entry.name}-${w}x${h}.png`);
      await page.screenshot({ path: shot });
      const kinds = {};
      for (const l of log) kinds[l.url.split("/clips/")[1]] = (kinds[l.url.split("/clips/")[1]] ?? 0) + 1;
      rec.local = {
        origin: opts.local,
        freezeReport: { frozen: freeze?.frozen, maxSeekError: freeze?.maxSeekError,
                        maxDrift: freeze?.maxDrift, allPaused: freeze?.allPaused },
        clipUrlsIntercepted: Object.entries(kinds).map(([clip, count]) => ({ clip, count })),
        servedSha256: asset.mp4Sha,
        mediaFits: fits, frame: v4,
        decoded, landmarkVerdict: landmarkVerdict(entry.landmarks, decoded.landmarks),
        screenshot: path.basename(shot),
      };
      await ctx.close();
    }
    rec.decodedFrameHashesEqual =
      rec.target.decoded?.frameHashFnv1a !== undefined &&
      rec.target.decoded.frameHashFnv1a === rec.local.decoded?.frameHashFnv1a;
    records.push(rec);
    console.log(`${entry.name} ${w}x${h}: target videos=${rec.target.videos} ` +
      `frozen=${rec.target.allFrozenAt} lm=${rec.target.landmarkVerdict.pass} | ` +
      `local frozen=${rec.local.freezeReport.frozen} lm=${rec.local.landmarkVerdict.pass} | ` +
      `decodedHashEq=${rec.decodedFrameHashesEqual}`);
  }
}
await writeFile(path.join(opts.out, "harness-raw.json"),
  JSON.stringify({ freeze: opts.freeze, records }, null, 1));
console.log(`-> ${opts.out}/harness-raw.json (${records.length} records)`);
await browser.close();
