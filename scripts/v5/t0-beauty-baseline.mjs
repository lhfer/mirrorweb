#!/usr/bin/env node
/**
 * Beauty baseline: what the source-exact composition actually looks like.
 *
 * Supersedes `fsxa-beauty-baseline.mjs`. That script ran every capture with the
 * adaptive sampler off, and at the time the render loop returned early in
 * exactly that state -- so `setRenderLayers` changed the scene graph and the
 * canvas never redrew. The media-only and glass+media frames it produced were
 * the same stale pixels, which is why their hashes matched.
 *
 * Three things are different here:
 *   1. every state change is followed by an explicit `renderOnce()`;
 *   2. the render-layer state is READ BACK off the scene and written into the
 *      JSON, so a frame labelled "glass off" can be shown to have had its glass
 *      meshes invisible;
 *   3. every PNG is hashed, and the media-only / glass+media pair is diffed in
 *      pixels by `t0-beauty-diff.py` rather than compared by hash alone.
 *
 * Fixed conditions: quality high, adaptive sampler OFF, media frozen at t=2,
 * motion paused, pointer (0,0), DPR 1, source-exact defaults.
 */
import { createHash } from "node:crypto";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280", out: path.join(REPO, "artifacts/t1/beauty"),
  tag: "candidate",
  vps: ["1440x900", "1920x1080", "390x844", "844x390", "700x700", "667x375", "780x470"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a.startsWith("--tag=")) opts.tag = a.slice(6);
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
}

const STATES = [
  { id: "1-foundation", foundation: true },
  { id: "2-media-only", layers: { glass: false, media: true, labels: false } },
  { id: "3-glass-media", layers: { glass: true, media: true, labels: false } },
  { id: "4-full-beauty", layers: { glass: true, media: true, labels: true } },
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const report = { tag: opts.tag, capturedAt: new Date().toISOString(),
  supersedes: "qa-v5/fsx-a/beauty (captured against a frozen canvas)",
  fixedConditions: { quality: "high, adaptive sampler OFF", mediaTimeSeconds: 2,
    motion: "paused", pointer: [0, 0], dpr: 1, composition: "sourceExact (defaults)",
    redraw: "explicit renderOnce() after every state change" },
  states: STATES.map((s) => s.id), viewports: [], errors: [] };

async function open(w, h, foundation) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => report.errors.push(`${w}x${h}: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") report.errors.push(`${w}x${h}: ${m.text()}`); });
  const q = foundation ? "&foundation=layout&annotate=0" : "";
  await page.goto(`${opts.origin}/?qa=1&composition=sourceExact${q}`, { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 180000 });
  await page.waitForTimeout(3200);
  await page.evaluate(() => {
    window.__ILG_QA__.setAdaptiveQuality(false);
    window.__ILG_QA__.setQuality("high");
    window.__ILG_QA__.setPointer(0, 0);
    window.__ILG_QA__.pause();
    window.__ILG_QA__.setOffset(0, 0);
  });
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  await page.waitForTimeout(900);
  await page.evaluate(() => window.__ILG_QA__.renderOnce());
  return { ctx, page };
}

await mkdir(opts.out, { recursive: true });
for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const entry = { id: vp, viewport: [w, h], shots: [] };
  for (const state of STATES) {
    const { ctx, page } = await open(w, h, Boolean(state.foundation));
    let stamp = null;
    if (state.layers) {
      stamp = await page.evaluate((l) => {
        const qa = window.__ILG_QA__;
        const before = qa.getRenderStamp();
        qa.setRenderLayers(l);
        // setRenderLayers already draws; a second explicit call makes the
        // capture independent of that implementation detail.
        qa.renderOnce();
        return { before, after: qa.getRenderStamp() };
      }, state.layers);
      await page.waitForTimeout(400);
    }
    const dir = path.join(opts.out, vp);
    await mkdir(dir, { recursive: true });
    const file = path.join(dir, `${state.id}.png`);
    await page.screenshot({ path: file });
    const png = await readFile(file);
    const layerState = state.foundation ? null
      : await page.evaluate(() => window.__ILG_QA__.getRenderLayerState());
    const metrics = await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      const m = qa.getMetrics();
      const v = qa.getV4State();
      return { fps: Math.round(m.fps), medianFrameMs: Number(m.medianFrameMs?.toFixed(2)),
               p95FrameMs: Number(m.p95FrameMs?.toFixed(2)), drawCalls: m.drawCalls,
               triangles: m.triangles, backend: m.backend,
               renderedFrames: m.renderedFrames, renderStamp: m.renderStamp,
               appliedQuality: qa.getAdaptiveState().appliedLevel,
               activeSlotCount: v.activeSlotCount,
               cols: v.sourceExactFrame?.cols, rows: v.sourceExactFrame?.rows };
    });
    entry.shots.push({ state: state.id, png: path.relative(REPO, file),
                       sha256: createHash("sha256").update(png).digest("hex"),
                       requestedLayers: state.layers ?? "foundation route",
                       renderLayerState: layerState, renderStamp: stamp, metrics });
    console.log(`${vp} ${state.id}  draws=${metrics.drawCalls} glassVisible=${layerState?.actual?.glassMeshesVisible ?? "-"} loopFrames=${metrics.renderedFrames}`);
    await ctx.close();
  }
  report.viewports.push(entry);
}
await browser.close();
await writeFile(path.join(opts.out, "beauty.json"), JSON.stringify(report, null, 2));
console.log(`beauty baseline (${opts.tag}) -> ${opts.out}  (${report.errors.length} errors)`);
