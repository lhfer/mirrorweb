#!/usr/bin/env node
/**
 * Long-scroll runtime integrity.
 *
 * v2 places rows on the composition's cellH while the pool derived its origin
 * row from GRID.cellH. Near the origin the two agree, so nothing showed; a few
 * dozen cells out they diverge by a whole row and the pool hands a slot the
 * wrong index -- a catalog jump and a parity break. This drives the offset far
 * enough for that to appear, and asserts it does not.
 */
import { writeFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280", out: path.join(REPO, "qa-v5/f26"),
  query: "composition=v2&verticalMode=tangent&portraitLaw=p1" };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--query=")) opts.query = a.slice(8);
}
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
const consoleErrors = [], pageErrors = [];
page.on("console", m => { if (m.type() === "error") consoleErrors.push(m.text()); });
page.on("pageerror", e => pageErrors.push(String(e.message)));
await page.goto(`${opts.origin}/?optics=v4&qa=1&${opts.query}`, { waitUntil: "load" });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 120000 });
await page.waitForTimeout(2500);
await page.evaluate(() => { window.__ILG_QA__.setQuality("high"); window.__ILG_QA__.setPointer(0, 0); window.__ILG_QA__.pause(); });
await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze(2));

const cellH = await page.evaluate(() => window.__ILG_QA__.getV4State().effectiveCellH);
const CH = cellH || 419.95;
const steps = [0, 0.49, -0.49, 0.51, -0.51, 10, -10, 50, -50, 100, -100].map(k => k * CH);
await mkdir(opts.out, { recursive: true });
const trace = [];
for (const sy of steps) {
  await page.evaluate(v => window.__ILG_QA__.setOffset(0, v), sy);
  await page.waitForTimeout(140);
  const st = await page.evaluate(() => {
    const q = window.__ILG_QA__, s = q.getState(), v = q.getV4State();
    const quads = q.getCardQuads();
    const rows = {};
    for (const c of quads) (rows[c.j] ??= []).push(c.i);
    const near = s.landmarks.map(l => ({ i: l.i, j: l.j, d: Math.hypot(l.nx - .5, l.ny - .5) }))
      .sort((a, b) => a.d - b.d)[0];
    return { scrollY: s.scrollY, pool: q.getPoolState(), asset: q.getAssetState(),
             centreCell: near ? [near.i, near.j] : null,
             jRange: [Math.min(...quads.map(c => c.j)), Math.max(...quads.map(c => c.j))],
             iRange: [Math.min(...quads.map(c => c.i)), Math.max(...quads.map(c => c.i))],
             rowsPerJ: Object.fromEntries(Object.entries(rows).map(([k, v]) => [k, v.length])),
             effectiveCellH: v.effectiveCellH, quads };
  });
  // overlap + blank check from the quads
  const on = st.quads.map(q => q.quad.map(([x, y]) => [x * 1440, y * 900]))
    .filter(p => Math.max(...p.map(q => q[0])) > 0 && Math.min(...p.map(q => q[0])) < 1440
              && Math.max(...p.map(q => q[1])) > 0 && Math.min(...p.map(q => q[1])) < 900);
  const sep = (a, b) => { let best = -Infinity;
    for (const poly of [a, b]) for (let k = 0; k < poly.length; k++) {
      const [x0, y0] = poly[k], [x1, y1] = poly[(k + 1) % poly.length];
      let nx = -(y1 - y0), ny = x1 - x0; const L = Math.hypot(nx, ny); if (L < 1e-9) continue;
      nx /= L; ny /= L;
      const pa = a.map(p => p[0] * nx + p[1] * ny), pb = b.map(p => p[0] * nx + p[1] * ny);
      best = Math.max(best, Math.max(Math.min(...pb) - Math.max(...pa), Math.min(...pa) - Math.max(...pb)));
    } return best; };
  let minSep = Infinity, overlaps = 0;
  for (let i = 0; i < on.length; i++) for (let j = i + 1; j < on.length; j++) {
    const d = sep(on[i], on[j]); minSep = Math.min(minSep, d); if (d <= 0) overlaps++;
  }
  const expectedJ = Math.round(st.scrollY / (st.effectiveCellH || CH));
  delete st.quads;
  trace.push({ ...st, cellsScrolled: +(sy / CH).toFixed(3), expectedOriginJ: expectedJ,
               centreJMatchesOrigin: st.centreCell ? Math.abs(st.centreCell[1] - expectedJ) <= 1 : null,
               onScreenCards: on.length, minSeparationPx: +minSep.toFixed(2), overlaps });
  const png = path.join(opts.out, "long-scroll", `s${String(trace.length - 1).padStart(2, "0")}.png`);
  await mkdir(path.dirname(png), { recursive: true });
  await page.screenshot({ path: png });
}
await ctx.close(); await browser.close();

const f = trace[0];
const A = [];
const add = (id, ok, detail) => A.push({ assertion: id, pass: !!ok, detail });
add("placementAndRecyclingAgree", trace.every(t => t.centreJMatchesOrigin !== false),
    "centre cell's row index tracks the pool's origin row at every offset");
add("poolSlotsStable", trace.every(t => t.pool.slots === f.pool.slots), `slots ${f.pool.slots}`);
add("createdNeverIncreases", trace.every(t => t.pool.created === f.pool.created), `created ${f.pool.created}`);
add("nothingDestroyed", trace.every(t => t.pool.destroyed === f.pool.destroyed), `destroyed ${f.pool.destroyed}`);
add("videoAndTextureCountsStable", trace.every(t => t.pool.videos === f.pool.videos && t.pool.textures === f.pool.textures), "");
add("assetsStayReady", trace.every(t => t.asset.ready === true), "");
add("rowsContiguous", trace.every(t => {
  const js = Object.keys(t.rowsPerJ).map(Number).sort((a, b) => a - b);
  return js.every((v, n) => n === 0 || v === js[n - 1] + 1);
}), "no missing or duplicated row index in the pool");
add("columnsPerRowConstant", trace.every(t => new Set(Object.values(t.rowsPerJ)).size === 1),
    "every row carries the same number of cells");
add("noCardOverlap", trace.every(t => t.overlaps === 0),
    `min separation ${Math.min(...trace.map(t => t.minSeparationPx)).toFixed(2)} px`);
add("noBlankRegion", trace.every(t => t.onScreenCards >= 6), "at least 6 cards cover the frame at every offset");
add("noConsoleErrors", consoleErrors.length === 0, consoleErrors.slice(0, 2).join(" | ") || "none");
add("noPageErrors", pageErrors.length === 0, pageErrors.slice(0, 2).join(" | ") || "none");
const payload = { query: opts.query, effectiveCellH: CH, steps: trace.length,
  verdict: A.every(a => a.pass) ? "PASS" : "FAIL", assertions: A, trace,
  consoleErrors, pageErrors };
await writeFile(path.join(opts.out, "long-scroll-runtime.json"), JSON.stringify(payload, null, 2));
console.log(`${payload.verdict}  ${A.filter(a => a.pass).length}/${A.length} assertions`);
for (const a of A) if (!a.pass) console.log("  FAIL", a.assertion, a.detail);
