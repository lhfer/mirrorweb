#!/usr/bin/env node
/**
 * O5F §七.1 -- 1,200 quality changes: high -> medium -> low -> high, 300
 * cycles, on a paused, media-frozen candidate page.
 *
 * The pixel check is the contract's check 9: a reference still per tier on
 * its FIRST post-warm-up visit, then every later visit must equal that
 * reference exactly. The first full cycle is the declared warm-up -- it is
 * where the 3-sample program compiles -- and is excluded from references.
 * Screenshots are hashed rather than stored (1,200 stills would be a
 * package, not a measurement); any mismatching frame IS stored, with its
 * step number, for the scorer to pixel-diff.
 *
 * Cross-tier (high vs medium) equality is recorded as a DIAGNOSTIC only:
 * the two tiers share the 5-sample set, so they are expected to match, but
 * the sealed check is within-tier identity.
 *
 * Usage: o5f-quality-cycle.mjs --local=<origin> [--cycles=300] [--out=<dir>]
 */
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, asset: "bw-split", freeze: 4, cycles: 300,
  out: path.join(REPO, "artifacts/optics-o5f/quality-cycle") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = (k === "cycles" || k === "freeze") ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const ORDER = ["high", "medium", "low", "high"];
const sha256 = (b) => createHash("sha256").update(b).digest("hex");

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });

const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await installLocalRoutes(ctx, loadAsset(opts.asset), null);
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
  + "&reflectionSupport=geometry&bodyFloorMode=current"
  + "&opticalBody=target-source-unclamped",
  { waitUntil: "load", timeout: 120000 });
await page.waitForFunction(
  () => window.__ILG_QA__?.getState?.()?.ready === true, undefined,
  { timeout: 180000 });
await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t),
  opts.freeze);
await page.evaluate(() => {
  const qa = window.__ILG_QA__;
  qa.pause();
  qa.setShellMode("off");
  qa.setRenderLayers({ labels: false });
  qa.setVelocity(0, 0); qa.setOffset(0, 0); qa.jumpPointer(0, 0);
  qa.setTime(4);
  qa.renderOnce(); qa.renderOnce();
});

const truth = async () => page.evaluate(() => {
  const qa = window.__ILG_QA__;
  const t = qa.getBodyMaterialCacheTruth();
  return {
    activeKey: t.activeKey, cacheSize: t.cacheSize,
    materialCreationCount: t.materialCreationCount,
    materialDisposalCount: t.materialDisposalCount,
    cacheSwitchCount: t.cacheSwitchCount,
    activeMaterialUuids: t.activeMaterialUuids,
    videoTextureUuids: t.videoTextureUuids,
    environmentUuid: t.environmentUuid,
    rendererPrograms: t.rendererPrograms,
    rendererTextures: t.rendererTextures,
    rendererGeometries: t.rendererGeometries,
    samples: qa.getOpticsState().opticalBodySamples,
    quality: t.quality,
    // §十四 -- this context's device-predicate inputs plus the engine's own
    // sample-law reading, recorded so the post-fix scorer verifies the
    // context's expectation from truth.
    sampleLaw: t.sampleLaw ?? null,
    deviceTier: t.deviceTier ?? null,
    contextPredicate: {
      pointerCoarse: matchMedia("(pointer: coarse)").matches,
      hardwareConcurrency: navigator.hardwareConcurrency ?? 8,
      deviceMemory: navigator.deviceMemory ?? 8,
    },
    heapMB: performance.memory
      ? +(performance.memory.usedJSHeapSize / 1048576).toFixed(2) : null,
  };
});

const setLevel = async (level) => page.evaluate((l) => {
  window.__ILG_QA__.setQuality(l);
  window.__ILG_QA__.renderOnce();
}, level);

// --- declared warm-up: one full cycle so every tier's program is compiled
// before any reference is pinned. Recorded, excluded from references.
const warmup = [];
for (const level of ORDER) {
  await setLevel(level);
  warmup.push({ level, ...(await truth()) });
}

// --- references: first post-warm-up visit per tier -----------------------
const refs = {};
async function shotHash() {
  const buf = await page.screenshot();
  return { hash: sha256(buf), buf };
}
for (const level of ["high", "medium", "low"]) {
  await setLevel(level);
  const { hash, buf } = await shotHash();
  const file = `ref-${level}.png`;
  await writeFile(path.join(opts.out, file), buf);
  refs[level] = { file, hash, truth: await truth() };
}
await setLevel("high");

// --- the 1,200 steps ------------------------------------------------------
const steps = [];
const mismatches = [];
const uuidByTier = { high: refs.high.truth.activeMaterialUuids,
  medium: refs.medium.truth.activeMaterialUuids,
  low: refs.low.truth.activeMaterialUuids };
let stepN = 0;
const t0 = Date.now();
for (let cycle = 1; cycle <= opts.cycles; cycle += 1) {
  for (const level of ORDER) {
    stepN += 1;
    await setLevel(level);
    const { hash, buf } = await shotHash();
    const t = await truth();
    const pixelOk = hash === refs[level].hash;
    const uuidOk = JSON.stringify(t.activeMaterialUuids)
      === JSON.stringify(uuidByTier[level]);
    if (!pixelOk) {
      const file = `mismatch-step${stepN}-${level}.png`;
      await writeFile(path.join(opts.out, file), buf);
      mismatches.push({ step: stepN, cycle, level, file,
        expected: refs[level].file });
    }
    const rec = { step: stepN, cycle, level, pixelOk, uuidOk,
      samples: t.samples,
      creation: t.materialCreationCount, switches: t.cacheSwitchCount,
      cacheSize: t.cacheSize, programs: t.rendererPrograms,
      // §十四 -- per-step so the post-fix scorer verifies the sample law
      // against the recorded predicate on every step.
      sampleLaw: t.sampleLaw ?? null, deviceTier: t.deviceTier ?? null,
      contextPredicate: t.contextPredicate ?? null,
      heapMB: t.heapMB };
    // The full truth travels on a sampled cadence; the scored fields above
    // travel on every step.
    if (stepN % 40 === 0 || !pixelOk || !uuidOk) rec.fullTruth = t;
    steps.push(rec);
  }
  if (cycle % 25 === 0) {
    const last = steps.at(-1);
    console.log(`cycle ${cycle}/${opts.cycles}: creation ${last.creation}, `
      + `switches ${last.switches}, programs ${last.programs}, heap `
      + `${last.heapMB} MB, mismatches ${mismatches.length}`);
  }
}
const elapsedMs = Date.now() - t0;

// Cross-tier diagnostic: the 5-sample tiers are expected to match each
// other; reported, never scored.
const crossTier = { highVsMedium: refs.high.hash === refs.medium.hash,
  highVsLow: refs.high.hash === refs.low.hash };

await writeFile(path.join(opts.out, "quality-cycle.json"), JSON.stringify({
  what: "O5F §七.1 -- 1,200 quality changes on a paused, media-frozen "
      + "candidate page. Reference still per tier on first post-warm-up "
      + "visit; every later visit hashed against it. Mismatching frames are "
      + "stored for the scorer to pixel-diff.",
  local: opts.local, asset: opts.asset, freeze: opts.freeze,
  cycles: opts.cycles, stepsTotal: stepN, order: ORDER, elapsedMs,
  warmup,
  references: Object.fromEntries(Object.entries(refs).map(([k, v]) =>
    [k, { file: v.file, hash: v.hash, truth: v.truth }])),
  crossTierDiagnostic: crossTier,
  mismatches,
  errorCount: errors.length, errors: errors.slice(0, 10),
  steps,
}, null, 1));
console.log(`\n${stepN} steps in ${(elapsedMs / 60000).toFixed(1)} min, `
  + `${mismatches.length} pixel mismatches, errors ${errors.length}`);
console.log(`cross-tier: high==medium ${crossTier.highVsMedium}, `
  + `high==low ${crossTier.highVsLow}`);
console.log(`-> ${opts.out}/quality-cycle.json`);
await browser.close();
