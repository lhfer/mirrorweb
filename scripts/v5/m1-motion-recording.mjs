#!/usr/bin/env node
/**
 * Screen-record a page while REAL input drives it.
 *
 * Frames come from CDP's screencast, which captures the compositor without
 * blocking the page, and each frame carries the browser's own timestamp. That
 * matters twice: the page keeps its real frame timing while being recorded, so
 * the recording is of the motion rather than of the recorder; and the
 * timestamps let three recordings of the same gesture be aligned afterwards
 * instead of assumed to line up.
 *
 * No QA hook produces MOTION here. Every frame in every recording moved because
 * of a mouse or touch event dispatched through the automation protocol -- a
 * recording assembled by stepping an offset would show the renderer working and
 * say nothing about the motion model, which is the thing under review. Hooks
 * set the fixed state before a gesture starts and nothing else: the media
 * freeze on our own page, and the media layer for the one sequence that says
 * so in its name.
 *
 * Usage:
 *   m1-motion-recording.mjs --out=<dir> --label=<name> [--url=<origin>]
 *                           [--vps=WxH,...] [--seqs=a,b,...]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";
const opts = { url: TARGET, local: false, label: "target",
  out: path.join(REPO, "artifacts/motion/recordings"),
  vps: ["1440x900", "390x844"], seqs: ["drag-flick", "pointer-sweep"], settle: 7000 };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--seqs=")) opts.seqs = a.slice(7).split(",");
  else if (a.startsWith("--label=")) opts.label = a.slice(8);
  else if (a.startsWith("--settle=")) opts.settle = Number(a.slice(9));
  else if (a.startsWith("--url=")) { opts.url = a.slice(6); opts.local = true; }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * The gestures the recordings show. Deliberately identical across all three
 * sides, expressed in fractions of the viewport so the same script produces the
 * same hand movement at every size.
 */
async function drive(page, cdp, seq, w, h) {
  const cx = Math.round(w / 2), cy = Math.round(h / 2);
  const span = Math.min(w, h);
  if (seq === "drag-flick") {
    await page.mouse.move(cx - span * 0.3, cy);
    await page.mouse.down();
    for (let i = 1; i <= 22; i += 1) {
      await page.mouse.move(cx - span * 0.3 + span * 0.026 * i, cy + span * 0.009 * i);
      await sleep(22);
    }
    await page.mouse.up();
    await sleep(1500);
    await page.mouse.move(cx + span * 0.34, cy);
    await page.mouse.down();
    for (let i = 1; i <= 8; i += 1) { await page.mouse.move(cx + span * 0.34 - span * 0.085 * i, cy); await sleep(6); }
    await page.mouse.up();
    await sleep(3200);
    return;
  }
  if (seq === "touch-drag-flick") {
    const pt = (x, y) => [{ x, y, radiusX: 12, radiusY: 12, force: 1 }];
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pt(cx + span * 0.3, cy + span * 0.2) });
    for (let i = 1; i <= 16; i += 1) {
      await cdp.send("Input.dispatchTouchEvent",
        { type: "touchMove", touchPoints: pt(cx + span * 0.3 - span * 0.035 * i, cy + span * 0.2 - span * 0.02 * i) });
      await sleep(18);
    }
    await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    await sleep(3400);
    return;
  }
  if (seq === "pointer-sweep") {
    const pad = 8;
    for (const [x, y] of [[cx, cy], [pad, pad], [w - pad, pad], [w - pad, h - pad],
                          [pad, h - pad], [cx, cy]]) {
      await page.mouse.move(x, y, { steps: 16 });
      await sleep(560);
    }
    await sleep(900);
    return;
  }
  if (seq === "pointer-sweep-noMedia") {
    // The same sweep with the media layer off, on our side only. The highlight
    // travel path is measured from luminance, and the Target's video is
    // playing while ours is frozen -- so a like-for-like centroid comparison is
    // contaminated by video content on one side and not the other. With the
    // media off the highlight is the only bright thing left, which makes the
    // path unambiguous on the side where it can be made unambiguous. The
    // Target-side comparison is still taken, with its caveat stated.
    await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: true, media: false, labels: true }));
    const pad2 = 8;
    for (const [x, y] of [[cx, cy], [pad2, pad2], [w - pad2, pad2], [w - pad2, h - pad2],
                          [pad2, h - pad2], [cx, cy]]) {
      await page.mouse.move(x, y, { steps: 16 });
      await sleep(560);
    }
    await sleep(900);
    await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: true, media: true, labels: true }));
    return;
  }
  if (seq === "wheel") {
    await page.mouse.move(cx, cy);
    for (let i = 0; i < 10; i += 1) { await page.mouse.wheel(0, 120); await sleep(70); }
    await sleep(1600);
    return;
  }
  throw new Error(`unknown recording sequence ${seq}`);
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

const index = { label: opts.label, url: opts.url, startedAt: new Date().toISOString(),
                driver: "every frame moved because of a real mouse, touch or wheel event "
                      + "dispatched over CDP. QA hooks set the FIXED STATE before a gesture "
                      + "starts and nothing else: the media freeze on our own page, and the "
                      + "media layer for the sequence that says so in its name. No hook "
                      + "produces motion in any recording.",
                capture: "CDP Page.startScreencast, non-blocking, browser-timestamped",
                recordings: [] };

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    deviceScaleFactor: 1, hasTouch: true });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await page.goto(opts.url, { waitUntil: "load", timeout: 120000 });
  if (opts.local) {
    await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
      undefined, { timeout: 180000 });
    await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  }
  await page.waitForTimeout(opts.settle);

  for (const seq of opts.seqs) {
    await page.mouse.move(Math.round(w / 2), Math.round(h / 2));
    await page.waitForTimeout(1200);
    const dir = path.join(opts.out, opts.label, vp, seq);
    await mkdir(dir, { recursive: true });
    const frames = [];
    let n = 0;
    const onFrame = async ({ data, metadata, sessionId }) => {
      const i = n; n += 1;
      frames.push({ i, timestampSec: metadata.timestamp });
      await writeFile(path.join(dir, `f${String(i).padStart(4, "0")}.jpg`),
                      Buffer.from(data, "base64"));
      try { await cdp.send("Page.screencastFrameAck", { sessionId }); } catch { /* stopped */ }
    };
    cdp.on("Page.screencastFrame", onFrame);
    await cdp.send("Page.startScreencast", { format: "jpeg", quality: 82, everyNthFrame: 1 });
    const t0 = Date.now();
    await drive(page, cdp, seq, w, h);
    await cdp.send("Page.stopScreencast");
    cdp.off("Page.screencastFrame", onFrame);
    await sleep(200);
    const base = frames.length ? frames[0].timestampSec : 0;
    index.recordings.push({ viewport: vp, sequence: seq, dir: path.relative(REPO, dir),
      frames: frames.length, wallMs: Date.now() - t0,
      relativeMs: frames.map((f) => +((f.timestampSec - base) * 1000).toFixed(1)) });
    process.stdout.write(`  ${opts.label} ${vp} ${seq}  frames=${frames.length}\n`);
  }
  await ctx.close();
}
await browser.close();
await mkdir(opts.out, { recursive: true });
await writeFile(path.join(opts.out, `${opts.label}-index.json`), JSON.stringify(index, null, 2));
console.log(`recordings -> ${opts.out}/${opts.label}-index.json  (${index.recordings.length})`);
