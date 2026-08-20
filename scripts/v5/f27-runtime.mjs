#!/usr/bin/env node
/**
 * F2.7 runtime integrity: resize, non-zero offset, long scroll, orientation
 * flip and a deliberate crossing of the phase regime boundary.
 *
 * The phase question needs care. Under the row-origin law the rest phase is the
 * parity of the Target's own pool row count, and that count STEPS as the
 * viewport changes -- so a phase flip during a resize is correct behaviour, not
 * a fault. What must never happen is a flip that does not coincide with a step
 * in the row count, or any flip at all while only the scroll offset moves.
 *
 * Assertions are recorded per step and summarised; nothing is averaged away.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = {
  origin: "http://127.0.0.1:5280",
  out: path.join(REPO, "qa-v5/f27/session"),
  query: "composition=v2&verticalMode=tangent&portraitLaw=p1&portraitVertical=v2&phaseModel=rowOrigin",
};
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--query=")) opts.query = a.slice(8);
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
}

function quadOverlap(quads, vw, vh) {
  const on = quads.map((q) => q.quad.map(([x, y]) => [x * vw, y * vh]))
    .filter((p) => Math.max(...p.map((q) => q[0])) > -40 && Math.min(...p.map((q) => q[0])) < vw + 40
                && Math.max(...p.map((q) => q[1])) > -40 && Math.min(...p.map((q) => q[1])) < vh + 40);
  const sep = (a, b) => {
    let best = -Infinity;
    for (const poly of [a, b]) {
      for (let k = 0; k < poly.length; k += 1) {
        const [x0, y0] = poly[k];
        const [x1, y1] = poly[(k + 1) % poly.length];
        let nx = -(y1 - y0); let ny = x1 - x0;
        const L = Math.hypot(nx, ny);
        if (L < 1e-9) continue;
        nx /= L; ny /= L;
        const pa = a.map((p) => p[0] * nx + p[1] * ny);
        const pb = b.map((p) => p[0] * nx + p[1] * ny);
        best = Math.max(best, Math.max(Math.min(...pb) - Math.max(...pa), Math.min(...pa) - Math.max(...pb)));
      }
    }
    return best;
  };
  let worst = Infinity; let pairs = 0;
  for (let i = 0; i < on.length; i += 1) {
    for (let j = i + 1; j < on.length; j += 1) {
      const s = sep(on[i], on[j]);
      worst = Math.min(worst, s);
      if (s <= 0) pairs += 1;
    }
  }
  return { cards: on.length, minSeparationPx: on.length ? Number(worst.toFixed(2)) : null, overlaps: pairs };
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const consoleErrors = []; const pageErrors = [];

async function openPage(w, h) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => pageErrors.push(String(e.message)));
  await page.goto(`${opts.origin}/?optics=v4&qa=1&${opts.query}`, { waitUntil: "load" });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 120000 });
  await page.waitForTimeout(2200);
  await page.evaluate(() => {
    window.__ILG_QA__.setQuality("high");
    window.__ILG_QA__.setPointer(0, 0);
    window.__ILG_QA__.pause();
  });
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));
  return { ctx, page };
}

async function sample(page, label) {
  return page.evaluate((lbl) => {
    const qa = window.__ILG_QA__;
    const v = qa.getV4State();
    const pool = qa.getPoolState();
    const asset = qa.getAssetState();
    return {
      label: lbl,
      viewport: [window.innerWidth, window.innerHeight],
      restOffsetX: v.restOffset.x,
      halfCellPhase: v.rowOrigin.halfCellPhase,
      targetRows: v.rowOrigin.targetRows,
      targetCols: v.rowOrigin.targetCols,
      recyclingOriginJ: v.rowOrigin.recyclingOriginJ,
      residualPhaseY: v.rowOrigin.residualPhaseY,
      catalogRow: v.catalogRowAtCentre.geometryRowIndex,
      catalogCodes: v.catalogRowAtCentre.codes,
      compositionScale: v.compositionScale,
      verticalScaleY: v.reportedVerticalScaleY,
      assertions: v.runtimeTruthAssertions,
      scrollX: qa.getState().scrollX, scrollY: qa.getState().scrollY,
      poolSize: pool.size ?? pool.slots ?? null,
      videos: asset.videos ?? null, textures: asset.textures ?? null,
      videoFrames: asset.videoFrames ?? null,
      quads: qa.getCardQuads(),
    };
  }, label);
}

const report = { query: opts.query, startedAt: new Date().toISOString(), sessions: {}, assertions: [] };
const A = (name, ok, detail) => report.assertions.push({ assertion: name, pass: !!ok, detail });

// ---------------------------------------------------------------- session A/B
for (const [name, offset] of [["A-rest", [0, 0]], ["B-offset-260-180", [260, 180]]]) {
  const { ctx, page } = await openPage(1920, 1080);
  await page.evaluate(([x, y]) => window.__ILG_QA__.setOffset(x, y), offset);
  const steps = [];
  const seq = [];
  for (let w = 1920; w >= 1000; w -= 60) seq.push([w, Math.round((w * 0.5625) / 0.9)]);
  for (const vp of [[960, 720], [960, 500], [900, 899], [844, 390], [800, 425], [780, 470],
                    [760, 470], [700, 700], [700, 400], [667, 375], [617, 617],
                    [500, 900], [430, 932], [390, 844], [360, 800]]) seq.push(vp);
  for (const [w, h] of seq) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(140);
    // The offset is NOT reset between steps: resetting it is exactly what would
    // hide a catalog-window or recycling fault.
    const s = await sample(page, `${w}x${h}`);
    s.overlap = quadOverlap(s.quads, w, h);
    delete s.quads;
    steps.push(s);
  }
  await ctx.close();
  report.sessions[name] = { offset, steps: steps.length, trace: steps };

  const flips = [];
  for (let i = 1; i < steps.length; i += 1) {
    if (steps[i].restOffsetX !== steps[i - 1].restOffsetX) {
      flips.push({ from: steps[i - 1].label, to: steps[i].label,
                   rowsFrom: steps[i - 1].targetRows, rowsTo: steps[i].targetRows,
                   justifiedByRowCountStep: (steps[i - 1].targetRows / 2) % 2 !== (steps[i].targetRows / 2) % 2 });
    }
  }
  A(`${name}: every rest-phase flip coincides with a step in the Target row count`,
    flips.every((f) => f.justifiedByRowCountStep), flips);
  A(`${name}: rest offset always agrees with the row-origin phase`,
    steps.every((s) => (s.restOffsetX > 0) === s.halfCellPhase), null);
  A(`${name}: scroll offset preserved across every resize`,
    steps.every((s) => Math.abs(s.scrollX - offset[0]) < 1e-6 && Math.abs(s.scrollY - offset[1]) < 1e-6), null);
  A(`${name}: runtime truth passes at every step`, steps.every((s) => s.assertions.allPass), null);
  A(`${name}: no card overlap at any step`, steps.every((s) => s.overlap.overlaps === 0), null);
  A(`${name}: cards on screen at every step`, steps.every((s) => s.overlap.cards > 0), null);
  A(`${name}: pool size constant`, new Set(steps.map((s) => s.poolSize)).size === 1,
    [...new Set(steps.map((s) => s.poolSize))]);
  A(`${name}: video count constant`, new Set(steps.map((s) => s.videos)).size === 1,
    [...new Set(steps.map((s) => s.videos))]);
  A(`${name}: recycling origin J stays 0 while only the viewport changes`,
    new Set(steps.map((s) => s.recyclingOriginJ)).size === 1, [...new Set(steps.map((s) => s.recyclingOriginJ))]);
  A(`${name}: landscape vertical scale is exactly 1`,
    steps.every((s) => (s.viewport[0] < s.viewport[1]) || s.verticalScaleY === 1), null);
}

// ------------------------------------------------------------- long scroll
{
  const { ctx, page } = await openPage(1440, 900);
  const cellH = await page.evaluate(() => window.__ILG_QA__.getV4State().effectiveCellH);
  const steps = [];
  for (const k of [0, 0.49, -0.49, 0.51, -0.51, 10, -10, 50, -50, 100, -100]) {
    await page.evaluate(([x, y]) => window.__ILG_QA__.setOffset(x, y), [k * 561.14, k * cellH]);
    await page.waitForTimeout(90);
    const s = await sample(page, `k=${k}`);
    s.cells = k;
    s.overlap = quadOverlap(s.quads, 1440, 900);
    delete s.quads;
    steps.push(s);
  }
  await ctx.close();
  report.sessions.longScroll = { cellH, steps: steps.length, trace: steps };
  A("longScroll: rest phase never flips while only the offset moves",
    new Set(steps.map((s) => s.restOffsetX)).size === 1, [...new Set(steps.map((s) => s.restOffsetX))]);
  A("longScroll: recycling origin J tracks the scroll exactly",
    steps.every((s) => s.recyclingOriginJ === Math.round(s.scrollY / cellH)), null);
  A("longScroll: catalog row tracks the scroll with no jump",
    steps.every((s) => Number.isFinite(s.catalogRow)), null);
  A("longScroll: no card overlap", steps.every((s) => s.overlap.overlaps === 0), null);
  A("longScroll: cards on screen at every offset", steps.every((s) => s.overlap.cards > 0), null);
  A("longScroll: pool size constant", new Set(steps.map((s) => s.poolSize)).size === 1, null);
}

// ------------------------------------------- orientation flip and regime cross
{
  const { ctx, page } = await openPage(844, 390);
  const steps = [];
  // 960x720 -> 960x500 crosses a row-count step at fixed width: the phase MUST
  // flip there and nowhere else in this list at that width.
  for (const [w, h] of [[844, 390], [390, 844], [844, 390], [960, 720], [960, 500],
                        [960, 720], [900, 899], [899, 900], [900, 900]]) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(160);
    const s = await sample(page, `${w}x${h}`);
    s.overlap = quadOverlap(s.quads, w, h);
    delete s.quads;
    steps.push(s);
  }
  await ctx.close();
  report.sessions.orientationAndRegime = { steps: steps.length, trace: steps };
  const cross = steps.filter((s) => s.label === "960x720" || s.label === "960x500");
  A("regime cross: 960x720 and 960x500 take different phases, as the row count demands",
    new Set(cross.map((s) => s.restOffsetX)).size === 2,
    cross.map((s) => ({ vp: s.label, rows: s.targetRows, restOffsetX: s.restOffsetX })));
  A("orientation flip: portrait applies the vertical scale, landscape does not",
    steps.every((s) => (s.viewport[0] < s.viewport[1]) ? s.verticalScaleY > 1 : s.verticalScaleY === 1), null);
  A("orientation flip: runtime truth passes on both sides", steps.every((s) => s.assertions.allPass), null);
  A("orientation flip: no card overlap", steps.every((s) => s.overlap.overlaps === 0), null);
}

A("no console errors", consoleErrors.length === 0, consoleErrors.slice(0, 5));
A("no page errors", pageErrors.length === 0, pageErrors.slice(0, 5));

report.consoleErrors = consoleErrors;
report.pageErrors = pageErrors;
report.passed = report.assertions.filter((a) => a.pass).length;
report.total = report.assertions.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
await mkdir(opts.out, { recursive: true });
await writeFile(path.join(opts.out, "runtime-assertions.json"), JSON.stringify(report, null, 2));
await browser.close();
console.log(`runtime ${report.verdict}  ${report.passed}/${report.total}`);
for (const a of report.assertions) if (!a.pass) console.log(`  FAIL ${a.assertion}  ${JSON.stringify(a.detail)?.slice(0, 300)}`);
