#!/usr/bin/env node
/**
 * Manifest-driven capture with a proven-fair media freeze.
 *
 * Every state comes from qa/loop-a2/fixed-state-manifest.json and is never
 * chosen at capture time. Each state produces a beauty frame and a media-only
 * frame; the media-only hash is what proves two builds were compared on the
 * same clip, the same cell and the same decoded frame.
 */
import { spawn } from "node:child_process";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const arg = (k, d) => { const v = process.argv.find((a) => a.startsWith(`--${k}=`)); return v ? v.slice(k.length + 3) : d; };
const port = Number(arg("port", 5340));
const out = arg("out");
const manifestPath = arg("manifest", "qa/loop-a2/fixed-state-manifest.json");
if (!out) throw new Error("--out is required");

function startPreview() {
  const child = spawn("npx", ["vite", "preview", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd: REPO_ROOT, stdio: ["ignore", "pipe", "pipe"] });
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("preview did not start")), 30_000);
    const onData = (c) => { if (String(c).includes("Local:")) { clearTimeout(timer); resolve(child); } };
    child.stdout.on("data", onData); child.stderr.on("data", onData); child.once("error", reject);
  });
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sha = (b) => createHash("sha256").update(b).digest("hex");

const manifestRaw = await readFile(path.join(REPO_ROOT, manifestPath));
const manifest = JSON.parse(manifestRaw.toString());
const manifestSha = sha(manifestRaw);

let preview, browser;
const states = [];
try {
  preview = await startPreview();
  browser = await chromium.launch({ channel: "chrome", headless: process.env.ILG_CAPTURE_HEADLESS === "1",
    args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
  await mkdir(path.join(out, "beauty"), { recursive: true });
  await mkdir(path.join(out, "media-only"), { recursive: true });

  // One page per viewport, not one per state. A fresh context and page load for
  // every state made each state decode its clips independently, and two states
  // with byte-identical specs (rest and pointer-center) then produced different
  // frames. States that share a viewport now share one warmed-up page.
  let context = null; let page = null; let currentViewport = null; let errors = [];
  const ensurePage = async (spec) => {
    const key = spec.viewport.join("x");
    if (currentViewport === key) return;
    if (context) await context.close();
    const [w, h] = spec.viewport;
    const isMobile = w <= 844;
    context = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: spec.dpr, isMobile, hasTouch: isMobile });
    page = await context.newPage();
    errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    await page.goto(`http://127.0.0.1:${port}/?optics=v4&qa=1`, { waitUntil: "load" });
    await page.waitForFunction(() => window.__ILG_QA__?.getState()?.ready === true, undefined, { timeout: 90_000 });
    await sleep(2500);
    currentViewport = key;
  };

  for (const spec of manifest.states) {
    await ensurePage(spec);
    await page.evaluate(() => { window.__ILG_QA__.resume(); window.__ILG_QA__.reset(); });
    await sleep(900);

    // Position the grid BEFORE freezing. Freezing first pins whichever clips
    // happened to be decoded at that moment, and the slot remap that follows
    // can put different clips in front of the camera - which is exactly why the
    // four offset-[0,0] states disagreed between processes.
    await page.evaluate((s) => {
      window.__ILG_QA__.setOffset(s.offset[0], s.offset[1]);
      window.__ILG_QA__.setVelocity(s.velocity[0], s.velocity[1]);
      window.__ILG_QA__.setPointer(s.pointer[0], s.pointer[1]);
    }, spec);
    await sleep(600);
    const freeze = await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), spec.mediaTime);
    // A fixed settle delay is not enough: pointer and rotation ease toward
    // their targets, and pausing mid-ease leaves a slightly different frame in
    // each process. Poll the motion state until it stops changing instead.
    // "Stopped changing" is the wrong test for an exponential ease: the
    // per-sample delta shrinks forever, so a tolerance-based comparison of two
    // consecutive samples fires while the pointer is still far from its target,
    // at a different point in each process. Since states now share one page, a
    // leftover pointer from the previous state makes that worse - which is
    // exactly how pointer-right ended up 88% different between two runs with
    // identical media times. Wait for convergence TO THE TARGET instead.
    let settled = false;
    let previous = null;
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await sleep(100);
      const now = await page.evaluate(() => {
        const s = window.__ILG_QA__.getState();
        return {
          pose: [s.scrollX, s.scrollY, s.pointerX, s.pointerY, s.rotX, s.rotY, s.camX, s.camY, s.velocityX, s.velocityY],
          pointerGap: Math.max(Math.abs(s.pointerX - s.pointerTargetX), Math.abs(s.pointerY - s.pointerTargetY)),
          speed: Math.hypot(s.velocityX, s.velocityY),
        };
      });
      const stable = previous && now.pose.every((v, k) => Math.abs(v - previous[k]) < 1e-9);
      if (stable && now.pointerGap < 1e-4 && now.speed < 1e-4) { settled = true; break; }
      previous = now.pose;
    }
    // Freezing the media is not enough on its own: with the clips paused, the
    // media-only render still drifted over ~1s within a single run, so a beauty
    // shot followed by a media-only shot 450 ms later landed on an arbitrary
    // phase and two processes disagreed. Pausing the render loop as well makes
    // both frames come from one fully static app state.
    await page.evaluate(() => window.__ILG_QA__.pause());
    await sleep(250);

    // The full slot arrangement, so a layout difference can be told apart from
    // a media difference when two runs disagree.
    const landmarks = await page.evaluate(() => window.__ILG_QA__.getState().landmarks
      .map((l) => `${l.i},${l.j},${l.slotIndex},${l.nx.toFixed(6)},${l.ny.toFixed(6)}`).join("|"));
    const beauty = await page.screenshot();
    await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: false, media: true, labels: false }));
    await sleep(250);
    const mediaOnly = await page.screenshot();
    const mediaOnlyRepeat = await (async () => { await sleep(700); return page.screenshot(); })();
    // Read the media state BEFORE resuming; resume() restarts the clips, so
    // reading after it measures the resume, not the freeze.
    const after = await page.evaluate(() => window.__ILG_QA__.getMediaState());
    await page.evaluate(() => window.__ILG_QA__.setRenderLayers({ glass: true, media: true, labels: true }));
    await page.evaluate(() => window.__ILG_QA__.resume());
    const drift = Math.max(...after.map((v, i) => Math.abs(v.currentTime - freeze.videos[i].currentTime)));

    await writeFile(path.join(out, "beauty", `${spec.stateId}.png`), beauty);
    await writeFile(path.join(out, "media-only", `${spec.stateId}.png`), mediaOnly);
    states.push({
      stateId: spec.stateId, cell: spec.cell, clipIndex: spec.clipIndex, mediaTime: spec.mediaTime,
      viewport: spec.viewport, frozen: freeze.frozen, allPaused: freeze.allPaused,
      maxSeekError: freeze.maxSeekError, freezeDrift: freeze.maxDrift, captureDrift: drift,
      frameWait: freeze.videos.map((v) => v.frameWait),
      mediaTimes: freeze.videos.map((v) => v.mediaTime),
      motionSettled: settled,
      landmarksDigest: sha(Buffer.from(landmarks)),
      beautyHash: sha(beauty), mediaOnlyHash: sha(mediaOnly),
      mediaOnlySelfStable: sha(mediaOnly) === sha(mediaOnlyRepeat),
      errors,
    });
    console.log(`captured ${spec.stateId} frozen=${freeze.frozen} drift=${drift}`);
  }

  const blocked = states.filter((s) => !s.frozen || s.captureDrift > 1 / 120 || s.errors.length || !s.mediaOnlySelfStable || !s.motionSettled).map((s) => s.stateId);
  const report = {
    generator: "stage-h-capture",
    stateManifestHash: manifestSha,
    manifestPath,
    validStateCount: states.length - blocked.length,
    totalStateCount: states.length,
    blockedStates: blocked,
    highTexturePresent: states.some((s) => s.stateId === "high-texture" && !blocked.includes("high-texture")),
    mediaTimeDrift: { max: Math.max(...states.map((s) => s.captureDrift)), threshold: 1 / 120 },
    mediaOnlyHashes: Object.fromEntries(states.map((s) => [s.stateId, s.mediaOnlyHash])),
    beautyHashes: Object.fromEntries(states.map((s) => [s.stateId, s.beautyHash])),
    states,
  };
  await writeFile(path.join(out, "fairness-report.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(JSON.stringify({ validStateCount: report.validStateCount, blockedStates: blocked, highTexturePresent: report.highTexturePresent, maxDrift: report.mediaTimeDrift.max, stateManifestHash: manifestSha.slice(0, 16) }, null, 2));
} finally { await browser?.close(); preview?.kill("SIGTERM"); }
