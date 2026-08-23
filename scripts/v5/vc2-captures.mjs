#!/usr/bin/env node
/**
 * Visual Convergence Sprint 2 §四 -- full-page evidence, matched and natural.
 *
 * Stills mode captures a complete page (never a crop, never a HUD) at each
 * review viewport, in two label states from ONE page load, so the glass pass
 * (labels off, both sides) and the typography pass (labels on, identical
 * strings, both sides) are the same page seconds apart rather than two
 * differently-settled pages.
 *
 * Record mode drives the shared §四/§五 scenarios with real pointer and touch
 * input and captures a CDP screencast, stamping every frame with the browser's
 * own timestamp so the assembled mp4 runs at the measured rate rather than an
 * assumed one. Media and copy are matched for every recording.
 *
 * Natural mode captures the same pages with their OWN media and their OWN
 * copy -- the product as each side actually ships it -- because a matched-
 * content review answers "is our glass right" and a natural review answers
 * "is our page right", and §四 asks for both.
 *
 * Usage:
 *   vc2-captures.mjs --mode=stills --side=target|review-target|review-current
 *                    [--media=<category>|natural] [--vps=WxH,..] [--tag=before]
 *   vc2-captures.mjs --mode=record --side=... [--media=<category>]
 *                    [--scenarios=a,b] [--tag=before]
 */
import { mkdir, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { RECORDED_SCENARIOS, sleep } from "./vc2_scenarios.mjs";
import { TARGET_URL, LOCAL_ORIGIN, assetFor, openMatched, pinMatched, readMatched }
  from "./vc2_matched.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const OUT = path.join(REPO, "artifacts/visual-convergence");
const args = { mode: "stills", side: "target", media: "dark-cinematic", tag: "",
               vps: ["1440x900", "390x844", "844x390", "700x700"], scenarios: null };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k === "vps" || k === "scenarios") args[k] = v.split(",");
  else args[k] = v ?? true;
}
const SIDE = {
  "target": { side: "target", url: TARGET_URL },
  "review-target": { side: "local", url: `${LOCAL_ORIGIN}/?review=target&qa` },
  "review-current": { side: "local", url: `${LOCAL_ORIGIN}/?review=current&qa` },
}[args.side];
if (!SIDE) throw new Error(`unknown side ${args.side}`);

const natural = args.media === "natural";
const asset = natural ? null : assetFor(args.media).asset;
const suffix = args.tag ? `-${args.tag}` : "";
const setDir = natural ? "natural" : `matched-${args.media}`;

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

async function stills() {
  const base = path.join(OUT, "stills" + suffix, setDir, args.side);
  await mkdir(base, { recursive: true });
  const index = { side: args.side, url: SIDE.url, media: args.media, tag: args.tag || null,
                  capturedAt: new Date().toISOString(), shots: [] };
  for (const vp of args.vps) {
    const [w, h] = vp.split("x").map(Number);
    const mediaLog = [];
    const { ctx, page, errors } = await openMatched(browser,
      { side: SIDE.side, url: SIDE.url, vp, asset, mediaLog });
    const pointer = [Math.round(w * 0.5), Math.round(h * 0.5)];
    let state = null, pinned = null;
    if (natural) {
      // Natural: no routing, no injection. The pointer is still parked at the
      // same place on both sides so the pose term is not a free variable.
      await page.mouse.move(pointer[0], pointer[1]);
      await sleep(1200);
      state = await readMatched(page, SIDE.side);
    } else {
      pinned = await pinMatched(page, { side: SIDE.side, labels: true, mediaTime: 2, pointer });
      state = await readMatched(page, SIDE.side);
    }
    for (const labels of natural ? [true] : [true, false]) {
      if (!natural) {
        await page.evaluate((on) => window.__VC2.setLabels(on), labels);
        await sleep(600);
      }
      const name = `${vp}${natural ? "" : labels ? "-labels-on" : "-labels-off"}.png`;
      await page.screenshot({ path: path.join(base, name) });
      index.shots.push({ file: name, vp, labels,
        visibleCards: state.visible.length, copyBodySha: state.copyBodySha,
        mediaFrozenAt: [...new Set((pinned?.media ?? []).map((m) => m.currentTime))],
        videoTimes: state.videos.concat(state.targetVideos).map((v) => v.t).slice(0, 6),
        quality: state.engine?.quality ?? null,
        servedShas: [...new Set(mediaLog.map((m) => m.sha256))].slice(0, 3),
        errors: errors.slice(0, 3) });
      console.log(`${args.side} ${setDir} ${name}`);
    }
    await ctx.close();
  }
  await writeFile(path.join(base, "index.json"), JSON.stringify(index, null, 1));
}

async function record() {
  const want = args.scenarios
    ? RECORDED_SCENARIOS.filter((s) => args.scenarios.includes(s.key)) : RECORDED_SCENARIOS;
  const root = path.join(OUT, "recordings" + suffix, args.side);
  await mkdir(root, { recursive: true });
  for (const sc of want) {
    const [w, h] = sc.vp.split("x").map(Number);
    const { ctx, page, errors } = await openMatched(browser,
      { side: SIDE.side, url: SIDE.url, vp: sc.vp, asset, mediaLog: [] });
    const pinned = await pinMatched(page, { side: SIDE.side, labels: true, mediaTime: 2,
      pointer: [Math.round(w / 2), Math.round(h / 2)] });
    const state = await readMatched(page, SIDE.side);
    const cdp = await ctx.newCDPSession(page);
    const dir = path.join(root, sc.key);
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
      maxWidth: 1440, maxHeight: 1440, everyNthFrame: 1 });
    await sleep(900);
    const t0 = Date.now();
    await sc.run(page, cdp, w, h);
    await sleep(sc.tailMs);
    const inputMs = Date.now() - t0;
    try { await cdp.send("Page.stopScreencast"); } catch { /* closed */ }
    await sleep(400);
    const span = frames.length > 1
      ? frames[frames.length - 1].timestampSec - frames[0].timestampSec : 0;
    const fps = span > 0 ? (frames.length - 1) / span : 30;
    await writeFile(path.join(dir, "index.json"), JSON.stringify({
      side: args.side, scenario: sc.key, url: SIDE.url, vp: sc.vp,
      resizeTo: sc.resizeTo ?? null, what: sc.what, media: args.media,
      copyBodySha: state.copyBodySha,
      mediaFrozenAt: [...new Set(pinned.media.map((m) => m.currentTime))],
      driver: "real page.mouse / CDP Input.dispatchTouchEvent only; no setOffset, "
            + "no synthetic motion, labels on, no debug HUD",
      frames: frames.length, spanSec: +span.toFixed(3), fps: +fps.toFixed(2), inputMs,
      errors: errors.slice(0, 3), recordedAt: new Date().toISOString(),
    }, null, 1));
    const mp4 = path.join(root, `${sc.key}.mp4`);
    const r = spawnSync("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y",
      "-framerate", fps.toFixed(2), "-i", path.join(dir, "%05d.jpg"),
      "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
      "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", "-movflags", "+faststart", mp4]);
    if (r.status !== 0) console.error(r.stderr?.toString());
    console.log(`${args.side} ${sc.key}: ${frames.length} frames @ ${fps.toFixed(1)} fps`);
    await ctx.close();
  }
}

if (args.mode === "stills") await stills();
else if (args.mode === "record") await record();
else throw new Error(`unknown mode ${args.mode}`);
await browser.close();
