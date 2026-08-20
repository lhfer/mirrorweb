#!/usr/bin/env node
/**
 * Beauty baseline: what the source-exact composition actually looks like.
 *
 * The FSX package was almost entirely grey foundation frames, which show the
 * layout and hide everything else. This captures four render states per
 * viewport so the remaining gap can be attributed to a system -- typography,
 * motion, optics or performance -- rather than argued about.
 *
 * Nothing in those systems is modified this round. This only records.
 *
 * Fixed conditions: quality high with the adaptive sampler OFF (it is working
 * now and would otherwise drift mid-capture), media frozen at t=2, motion
 * paused, pointer (0,0), DPR 1, source-exact defaults.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280", out: path.join(REPO, "artifacts/fsx-a/beauty"),
  vps: ["1440x900", "1920x1080", "390x844", "844x390", "700x700", "667x375", "780x470"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
}

const STATES = [
  { id: "1-foundation", foundation: true },
  { id: "2-media-only", layers: { glass: false, media: true, labels: false } },
  { id: "3-glass-media", layers: { glass: true, media: true, labels: false } },
  { id: "4-full-beauty", layers: { glass: true, media: true, labels: true } },
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const report = { capturedAt: new Date().toISOString(),
  fixedConditions: { quality: "high, adaptive sampler OFF", mediaTimeSeconds: 2,
    motion: "paused", pointer: [0, 0], dpr: 1, composition: "sourceExact (defaults)" },
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
    window.__ILG_QA__.setAdaptiveQuality?.(false);
    window.__ILG_QA__.setQuality("high");
    window.__ILG_QA__.setPointer(0, 0);
    window.__ILG_QA__.pause();
    window.__ILG_QA__.setOffset(0, 0);
  });
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  await page.waitForTimeout(900);
  return { ctx, page };
}

await mkdir(opts.out, { recursive: true });
for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  const entry = { id: vp, viewport: [w, h], shots: [] };
  for (const state of STATES) {
    const { ctx, page } = await open(w, h, Boolean(state.foundation));
    if (state.layers) {
      await page.evaluate((l) => window.__ILG_QA__.setRenderLayers(l), state.layers);
      await page.waitForTimeout(700);
    }
    const dir = path.join(opts.out, vp);
    await mkdir(dir, { recursive: true });
    const file = path.join(dir, `${state.id}.png`);
    await page.screenshot({ path: file });
    const metrics = await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      const m = qa.getMetrics();
      const v = qa.getV4State();
      return { fps: Math.round(m.fps), medianFrameMs: Number(m.medianFrameMs?.toFixed(2)),
               p95FrameMs: Number(m.p95FrameMs?.toFixed(2)), drawCalls: m.drawCalls,
               triangles: m.triangles, backend: m.backend,
               appliedQuality: qa.getAdaptiveState().appliedLevel,
               activeSlotCount: v.activeSlotCount,
               cols: v.sourceExactFrame.cols, rows: v.sourceExactFrame.rows };
    });
    entry.shots.push({ state: state.id, png: path.relative(REPO, file), metrics });
    console.log(`${vp} ${state.id}  fps=${metrics.fps} p95=${metrics.p95FrameMs}ms draws=${metrics.drawCalls} slots=${metrics.activeSlotCount}`);
    await ctx.close();
  }
  report.viewports.push(entry);
}
await browser.close();
await writeFile(path.join(opts.out, "beauty.json"), JSON.stringify(report, null, 2));
console.log(`beauty baseline done -> ${opts.out}  (${report.errors.length} errors)`);
