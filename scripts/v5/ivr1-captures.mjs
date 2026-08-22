#!/usr/bin/env node
/**
 * Integrated Visual Sprint 1, §四 -- full-page captures and real-input
 * recordings, one script for all three sides:
 *
 *   target          the live Target
 *   review-target   http://127.0.0.1:5293/?review=target   (the candidate)
 *   review-current  http://127.0.0.1:5293/?review=current  (the old default)
 *
 * Stills: the complete page (labels ON, footer ON, loading finished, no
 * overlay of any kind) at 1440x900 / 700x700 (fine pointer) and 390x844 /
 * 844x390 (touch context), media frozen at --freeze seconds on BOTH runtimes
 * so a pair shows the same completion state. Each side freezes ITS OWN
 * media; the product ships different clips than the Target by design.
 *
 * Recordings: the six §四 scenarios, driven by real CDP mouse/touch events
 * only -- no setOffset, no synthetic motion. Media runs live. Frames come
 * from CDP screencast with browser timestamps and are assembled to mp4 at
 * the measured rate. Desktop scenarios run in a fine-pointer context and
 * mobile scenarios in a touch context, because both runtimes decide their
 * sample tier from the pointer capability.
 *
 * Usage:
 *   node scripts/v5/ivr1-captures.mjs --mode=stills --side=<side> [--freeze=2]
 *   node scripts/v5/ivr1-captures.mjs --mode=record --side=<side> [--only=name]
 */
import { mkdir, writeFile, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { TARGET_VIDEO_HOOK, freezeTarget } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = path.join(REPO, "artifacts/integrated-review");
const SIDES = {
  "target": { url: "https://infinite-liquid-glass.shader.se/?v=2", local: false },
  "review-target": { url: "http://127.0.0.1:5293/?review=target&qa", local: true },
  "review-current": { url: "http://127.0.0.1:5293/?review=current&qa", local: true },
};
const MOBILE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
  + "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1";
const STILL_VIEWPORTS = [
  { w: 1440, h: 900, touch: false },
  { w: 700, h: 700, touch: false },
  { w: 390, h: 844, touch: true },
  { w: 844, h: 390, touch: true },
];

const args = Object.fromEntries(process.argv.slice(2)
  .map((a) => a.replace(/^--/, "").split("=")).map(([k, v]) => [k, v ?? true]));
const side = SIDES[args.side];
if (!side) { console.error("--side=target|review-target|review-current"); process.exit(2); }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function makeContextOptions(w, h, touch) {
  return {
    viewport: { width: w, height: h }, deviceScaleFactor: 1,
    hasTouch: touch, isMobile: touch, ...(touch ? { userAgent: MOBILE_UA } : {}),
  };
}

async function waitReady(page) {
  if (side.local) {
    await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true
      && window.__ILG_QA__?.getAssetState?.()?.ready === true, undefined, { timeout: 180000 });
  } else {
    await page.waitForFunction(() => {
      const text = document.body?.innerText || "";
      const m = text.match(/(\d+)\s*%/);
      return Boolean(document.querySelector("canvas")) && (!m || Number(m[1]) >= 100);
    }, undefined, { timeout: 120000 });
  }
  await sleep(2500);
}

/** Optics provenance for local sides: proves WHICH lane the pixels show. */
async function provenance(page) {
  if (!side.local) return { side: "live-target" };
  return page.evaluate(() => {
    const qa = window.__ILG_QA__;
    const cache = qa.getBodyMaterialCacheTruth();
    return {
      search: location.search,
      opticalBody: qa.getOpticsState().opticalBody ?? null,
      sampleLaw: cache.sampleLaw ?? null,
      deviceTier: cache.deviceTier ?? null,
      quality: qa.getState().quality,
      adaptive: qa.getAdaptiveState().enabled,
    };
  });
}

async function stills(browser) {
  const freeze = Number(args.freeze ?? 2);
  const dir = path.join(OUT, args.side, "stills");
  await mkdir(dir, { recursive: true });
  const index = { side: args.side, url: side.url, freezeSeconds: freeze,
                  capturedAt: new Date().toISOString(), shots: [] };
  for (const vp of STILL_VIEWPORTS) {
    const ctx = await browser.newContext(makeContextOptions(vp.w, vp.h, vp.touch));
    if (!side.local) await ctx.addInitScript(TARGET_VIDEO_HOOK);
    const page = await ctx.newPage();
    await page.goto(side.url, { waitUntil: "load", timeout: 120000 });
    await waitReady(page);
    let media;
    if (side.local) {
      media = await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), freeze);
      await page.evaluate(() => window.__ILG_QA__.renderOnce());
      await sleep(400);
    } else {
      media = await freezeTarget(page, freeze);
      await sleep(600);
    }
    const file = `${vp.w}x${vp.h}.png`;
    await page.screenshot({ path: path.join(dir, file) });
    index.shots.push({ vp: `${vp.w}x${vp.h}`, touch: vp.touch, file,
                       media, provenance: await provenance(page) });
    console.log(`${args.side} ${vp.w}x${vp.h} captured`);
    await ctx.close();
  }
  await writeFile(path.join(dir, "index.json"), JSON.stringify(index, null, 1));
}

// ---------------------------------------------------------------- recordings

/** Smooth eased drag path from (x0,y0) by (dx,dy) over `ms`. */
function dragPath(x0, y0, dx, dy, ms, steps) {
  const pts = [];
  for (let i = 1; i <= steps; i++) {
    const t = i / steps, e = t < 0.5 ? 2 * t * t : 1 - (1 - t) * (2 - 2 * t); // easeInOut
    pts.push({ x: x0 + dx * e, y: y0 + dy * e, wait: ms / steps });
  }
  return pts;
}

async function mouseDrag(page, x0, y0, dx, dy, ms, steps = 48) {
  await page.mouse.move(x0, y0);
  await sleep(120);
  await page.mouse.down();
  for (const p of dragPath(x0, y0, dx, dy, ms, steps)) {
    await page.mouse.move(p.x, p.y); await sleep(p.wait);
  }
  await page.mouse.up();
}

async function touchDrag(cdp, x0, y0, dx, dy, ms, steps = 40, release = true) {
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart",
    touchPoints: [{ x: x0, y: y0, id: 1 }] });
  for (const p of dragPath(x0, y0, dx, dy, ms, steps)) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove",
      touchPoints: [{ x: p.x, y: p.y, id: 1 }] });
    await sleep(p.wait);
  }
  if (release) await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

/** The six §四 scenarios. `vp` decides the context; every event is real. */
const SCENARIOS = {
  "desktop-slow-drag": { vp: { w: 1440, h: 900, touch: false },
    run: async ({ page }) => {
      await mouseDrag(page, 1000, 450, -640, -40, 3600, 72);
      await sleep(2600);
    } },
  "desktop-fast-flick": { vp: { w: 1440, h: 900, touch: false },
    run: async ({ page }) => {
      await page.mouse.move(1050, 460); await sleep(300);
      await page.mouse.down();
      for (const p of dragPath(1050, 460, -420, -20, 110, 7)) {
        await page.mouse.move(p.x, p.y); await sleep(p.wait);
      }
      await page.mouse.up();
      await sleep(4800);
    } },
  "desktop-pointer-sweep": { vp: { w: 1440, h: 900, touch: false },
    run: async ({ page }) => {
      await page.mouse.move(120, 780); await sleep(300);
      for (let i = 0; i <= 120; i++) {
        const t = i / 120;
        await page.mouse.move(120 + 1200 * t, 780 - 660 * t + 180 * Math.sin(t * Math.PI * 2));
        await sleep(34);
      }
      await sleep(1600);
    } },
  "mobile-touch-drag": { vp: { w: 390, h: 844, touch: true },
    run: async ({ cdp }) => {
      await touchDrag(cdp, 300, 560, -220, -120, 1300, 40);
      await sleep(3200);
    } },
  "mobile-long-drag-wrap": { vp: { w: 390, h: 844, touch: true },
    run: async ({ cdp }) => {
      await touchDrag(cdp, 350, 480, -300, -30, 1500, 40, true);
      await sleep(500);
      await touchDrag(cdp, 350, 480, -300, -30, 1500, 40, true);
      await sleep(500);
      await touchDrag(cdp, 350, 480, -300, -30, 900, 30, true);
      await sleep(3000);
    } },
  "orientation-change": { vp: { w: 390, h: 844, touch: true },
    run: async ({ page, cdp }) => {
      await touchDrag(cdp, 300, 560, -180, -60, 1100, 32);
      await sleep(1500);
      await page.setViewportSize({ width: 844, height: 390 });
      await sleep(2200);
      await touchDrag(cdp, 640, 220, -260, -20, 1100, 32);
      await sleep(2400);
    } },
};

async function record(browser) {
  const wanted = args.only ? [args.only] : Object.keys(SCENARIOS);
  for (const name of wanted) {
    const sc = SCENARIOS[name];
    if (!sc) { console.error(`unknown scenario ${name}`); process.exit(2); }
    const ctx = await browser.newContext(makeContextOptions(sc.vp.w, sc.vp.h, sc.vp.touch));
    if (!side.local) await ctx.addInitScript(TARGET_VIDEO_HOOK);
    const page = await ctx.newPage();
    const cdp = await ctx.newCDPSession(page);
    await page.goto(side.url, { waitUntil: "load", timeout: 120000 });
    await waitReady(page);
    const prov = await provenance(page);

    const dir = path.join(OUT, args.side, "recordings", name);
    await rm(dir, { recursive: true, force: true });
    await mkdir(dir, { recursive: true });
    const frames = [];
    let n = 0;
    cdp.on("Page.screencastFrame", async ({ data, sessionId, metadata }) => {
      const i = n++;
      frames.push({ i, timestampSec: metadata.timestamp });
      await writeFile(path.join(dir, `${String(i).padStart(5, "0")}.jpg`),
                      Buffer.from(data, "base64"));
      try { await cdp.send("Page.screencastFrameAck", { sessionId }); } catch { /* stopped */ }
    });
    await cdp.send("Page.startScreencast", { format: "jpeg", quality: 82,
      maxWidth: sc.vp.touch ? 900 : 1440, maxHeight: sc.vp.touch ? 900 : 1440,
      everyNthFrame: 1 });
    await sleep(900); // rest head, so the gesture start is inside the clip
    const t0 = Date.now();
    await sc.run({ page, cdp });
    const inputMs = Date.now() - t0;
    await sleep(400);
    try { await cdp.send("Page.stopScreencast"); } catch { /* closed */ }
    await sleep(500);

    const span = frames.length > 1
      ? frames[frames.length - 1].timestampSec - frames[0].timestampSec : 0;
    const fps = span > 0 ? (frames.length - 1) / span : 30;
    await writeFile(path.join(dir, "index.json"), JSON.stringify({
      side: args.side, scenario: name, url: side.url, vp: `${sc.vp.w}x${sc.vp.h}`,
      touchContext: sc.vp.touch, provenance: prov,
      driver: "real CDP mouse/touch events only; no setOffset, no synthetic motion",
      frames: frames.length, spanSec: +span.toFixed(3), fps: +fps.toFixed(2),
      inputMs, recordedAt: new Date().toISOString(),
    }, null, 1));
    const mp4 = path.join(OUT, args.side, "recordings", `${name}.mp4`);
    const r = spawnSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y",
      "-framerate", fps.toFixed(2), "-i", path.join(dir, "%05d.jpg"),
      "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
      "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-movflags", "+faststart", mp4]);
    if (r.status !== 0) console.error(r.stderr?.toString());
    console.log(`${args.side} ${name}: ${frames.length} frames @ ${fps.toFixed(1)} fps -> ${path.relative(REPO, mp4)}`);
    await ctx.close();
  }
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
try {
  if (args.mode === "stills") await stills(browser);
  else if (args.mode === "record") await record(browser);
  else { console.error("--mode=stills|record"); process.exit(2); }
} finally {
  await browser.close();
}
