#!/usr/bin/env node
/**
 * Screen-record a page while REAL input drives it, on the SAME gestures the
 * gate measured.
 *
 * The sequences come from m2_sequences.mjs, the module the trace recorder
 * imports. That is the point: a reviewer watching a clip and a gate reading a
 * number have to be looking at the same gesture, or the review is of one thing
 * and the verdict is about another. Two copies of a gesture drift; one import
 * cannot.
 *
 * Frames come from CDP's screencast, which captures the compositor without
 * blocking the page, and each frame carries the browser's own timestamp. That
 * matters twice: the page keeps its real frame timing while being recorded, so
 * the recording is of the motion rather than of the recorder; and the
 * timestamps let three recordings of the same gesture be aligned afterwards
 * instead of assumed to line up.
 *
 * No QA hook produces MOTION here. Every frame moved because of a mouse or
 * touch event dispatched through the automation protocol. Hooks set the fixed
 * state before a gesture starts and nothing else -- the media freeze on our own
 * page.
 *
 * Usage:
 *   m2-recording.mjs --out=<dir> --label=<name> [--url=<origin>]
 *                    [--vps=WxH:seq,seq;WxH:seq,seq]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { runSequence } from "./m2_sequences.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const TARGET = "https://infinite-liquid-glass.shader.se/?v=2";

// The clips the product brief asks for, and only those. A package that repeats
// every sequence at every size is bigger and says less.
const PLAN = [
  ["1440x900", ["slow-horizontal-drag", "fast-flick", "reverse-flick", "pointer-sweep"]],
  ["390x844", ["touch-drag-release", "long-drag-multi-wrap"]],
];

const opts = { url: TARGET, local: false, label: "target",
  out: path.join(REPO, "artifacts/motion/m2-recordings"), settle: 7000, plan: PLAN };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--label=")) opts.label = a.slice(8);
  else if (a.startsWith("--settle=")) opts.settle = Number(a.slice(9));
  else if (a.startsWith("--url=")) { opts.url = a.slice(6); opts.local = true; }
  else if (a.startsWith("--plan=")) {
    opts.plan = a.slice(7).split(";").map((s) => {
      const [vp, seqs] = s.split(":");
      return [vp, seqs.split(",")];
    });
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

const index = { label: opts.label, url: opts.url, startedAt: new Date().toISOString(),
  driver: "every frame moved because of a real mouse or touch event dispatched over "
        + "CDP, using the same sequence module the trace recorder imports. QA hooks set "
        + "the FIXED STATE before a gesture starts and nothing else: the media freeze on "
        + "our own page. No offset was ever written directly.",
  capture: "CDP Page.startScreencast, non-blocking, browser-timestamped",
  recordings: [] };

for (const [vp, seqs] of opts.plan) {
  const [w, h] = vp.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h },
    deviceScaleFactor: 1, hasTouch: true, isMobile: false });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await page.goto(opts.url, { waitUntil: "load", timeout: 120000 });
  if (opts.local) {
    await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
      undefined, { timeout: 180000 });
    await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  }
  await page.waitForTimeout(opts.settle);

  for (const seq of seqs) {
    const dir = path.join(opts.out, opts.label, `${vp}-${seq}`);
    await mkdir(dir, { recursive: true });
    // Rest first, or the previous clip's tail is inside this one's release.
    await page.mouse.move(Math.round(w / 2), Math.round(h / 2));
    await page.waitForTimeout(1800);

    const frames = [];
    let i = 0;
    cdp.on("Page.screencastFrame", async ({ data, sessionId, metadata }) => {
      const n = i++;
      frames.push({ i: n, timestampSec: metadata.timestamp });
      await writeFile(path.join(dir, `f${String(n).padStart(4, "0")}.jpg`),
                      Buffer.from(data, "base64"));
      try { await cdp.send("Page.screencastFrameAck", { sessionId }); } catch { /* stopped */ }
    });
    const t0 = Date.now();
    await cdp.send("Page.startScreencast", { format: "jpeg", quality: 82, everyNthFrame: 1 });
    const { tailMs } = await runSequence(page, cdp, seq, w, h);
    await sleep(tailMs);
    await cdp.send("Page.stopScreencast");
    await sleep(400);

    const base = frames.length ? frames[0].timestampSec : 0;
    index.recordings.push({ viewport: vp, sequence: seq, dir: path.relative(REPO, dir),
      frames: frames.length, wallMs: Date.now() - t0,
      relativeMs: frames.map((f) => +((f.timestampSec - base) * 1000).toFixed(1)) });
    process.stdout.write(`  ${opts.label} ${vp} ${seq}  frames=${frames.length}\n`);
    await page.setViewportSize({ width: w, height: h });
  }
  await ctx.close();
}
await browser.close();
await mkdir(opts.out, { recursive: true });
await writeFile(path.join(opts.out, `${opts.label}-index.json`), JSON.stringify(index, null, 2));
console.log(`recordings -> ${opts.out}  (${index.recordings.length} clips)`);
