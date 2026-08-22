#!/usr/bin/env node
/**
 * O2 review recordings: REAL input over pages whose media is the
 * deterministic shared-media rendition, frozen at the same time the gates
 * measured. Sequences come from m2_sequences.mjs -- the same module every
 * motion gate imports -- so a reviewer watching a clip and a gate reading
 * a number see the same gesture.
 *
 * Lanes: target (routed) / before (V1-accepted worktree) / b-only / a-plus-b.
 * Frames: CDP screencast, browser-timestamped (the m2 pattern).
 *
 * Usage: o2-recording.mjs --local=<origin> --v1base=<origin>
 *        [--target=<url>] [--out=<dir>] [--lanes=a,b,c]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { runSequence } from "./m2_sequences.mjs";
import { installLocalRoutes, installTargetRoutes, loadAsset,
  TARGET_VIDEO_HOOK, freezeTarget } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, v1base: null,
  target: "https://infinite-liquid-glass.shader.se/?v=2",
  out: path.join(REPO, "artifacts/optics-o2/recordings"),
  lanes: ["target", "before", "b-only", "a-plus-b"] };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "lanes" ? v.split(",") : v;
}
if (!opts.local || !opts.v1base) { console.error("--local, --v1base required"); process.exit(2); }

// [vp, sequence, asset, lanes]
const ALL = opts.lanes;
const CMP = ["target", "before", "a-plus-b"];
const PLAN = [
  ["1440x900", "pointer-sweep", "bw-split", ALL],
  ["1440x900", "slow-horizontal-drag", "bw-split", ALL],
  ["1440x900", "fast-flick", "bw-split", ALL],
  ["390x844", "touch-drag-release", "bw-split", ALL],
  ["1440x900", "pointer-sweep", "dark-highlight", CMP],
  ["1440x900", "pointer-sweep", "bright-lowsat", CMP],
  ["1440x900", "pointer-sweep", "hf-checker", CMP],
  ["1440x900", "pointer-sweep", "grayscale-step", CMP],
];

const LANE = {
  target: { url: opts.target, kind: "target" },
  before: { url: `${opts.v1base}/?composition=sourceExact&qa`, kind: "local" },
  "b-only": { url: `${opts.local}/?composition=sourceExact&qa&dispersionLaw=v1`, kind: "local" },
  "a-plus-b": { url: `${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`, kind: "local" },
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const index = { capturedAtHead: "e913aa6", freeze: 4,
  driver: "every frame moved because of a real mouse or touch event over CDP "
        + "(m2_sequences.mjs); QA hooks set only the fixed state -- the media "
        + "freeze on the deterministic shared-media rendition",
  capture: "CDP Page.startScreencast, browser-timestamped", recordings: [] };

for (const [vp, seq, asset, lanes] of PLAN) {
  const [w, h] = vp.split("x").map(Number);
  for (const lane of lanes) {
    const L = LANE[lane];
    const mobile = w < 500;
    const ctx = await browser.newContext({ viewport: { width: w, height: h },
      deviceScaleFactor: 1, hasTouch: true, ...(mobile ? { isMobile: true } : {}) });
    const asset_ = loadAsset(asset);
    if (L.kind === "target") {
      await installTargetRoutes(ctx, asset_, null);
      await ctx.addInitScript(TARGET_VIDEO_HOOK);
    } else {
      await installLocalRoutes(ctx, asset_, null);
    }
    const page = await ctx.newPage();
    const cdp = await ctx.newCDPSession(page);
    await page.goto(L.url, { waitUntil: "load", timeout: 120000 });
    if (L.kind === "target") {
      await page.waitForFunction(() =>
        (window.__o2vids?.length ?? 0) >= 8 &&
        window.__o2vids.every((v) => v.readyState >= 2), undefined,
        { timeout: 90000 });
      await page.waitForTimeout(4000);
      await freezeTarget(page, 4);
    } else {
      await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
        undefined, { timeout: 180000 });
      await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
      await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), 4);
    }
    await page.waitForTimeout(1500);
    await page.mouse.move(Math.round(w / 2), Math.round(h / 2));
    await page.waitForTimeout(1500);

    const dir = path.join(opts.out, lane, `${vp}-${seq}-${asset}`);
    await mkdir(dir, { recursive: true });
    const frames = [];
    let i = 0;
    const onFrame = async ({ data, sessionId, metadata }) => {
      const n = i++;
      frames.push({ i: n, timestampSec: metadata.timestamp });
      await writeFile(path.join(dir, `f${String(n).padStart(4, "0")}.jpg`),
        Buffer.from(data, "base64"));
      try { await cdp.send("Page.screencastFrameAck", { sessionId }); } catch { /* stopped */ }
    };
    cdp.on("Page.screencastFrame", onFrame);
    await cdp.send("Page.startScreencast", { format: "jpeg", quality: 82, everyNthFrame: 1 });
    const { tailMs } = await runSequence(page, cdp, seq, w, h);
    await sleep(tailMs);
    await cdp.send("Page.stopScreencast");
    cdp.off("Page.screencastFrame", onFrame);
    await sleep(400);
    const base = frames.length ? frames[0].timestampSec : 0;
    index.recordings.push({ lane, viewport: vp, sequence: seq, asset,
      dir: path.relative(REPO, dir), frames: frames.length,
      relativeMs: frames.map((f) => +((f.timestampSec - base) * 1000).toFixed(1)) });
    console.log(`${lane} ${vp} ${seq} ${asset} frames=${frames.length}`);
    await ctx.close();
  }
}
await browser.close();
await writeFile(path.join(opts.out, "recordings-index.json"), JSON.stringify(index, null, 1));
console.log(`${index.recordings.length} clips -> ${opts.out}`);
