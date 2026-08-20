#!/usr/bin/env node
/**
 * Which application and which composition does each route actually resolve to?
 *
 * `?composition=sourceExact` used to fall through to V3, so the route named in
 * every brief and every preview link only worked when `optics=v4` was passed
 * beside it. This loads each route for real and reports what booted, rather than
 * reading the routing condition and believing it.
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5280", out: path.join(REPO, "qa-v5/fsx-a/route-proof.json") };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--origin=")) opts.origin = a.slice(9);
}

const ROUTES = [
  { id: "bare", query: "", expect: { app: "v3", composition: null },
    why: "the page default must not change: no composition and no optics still boots V3" },
  { id: "composition=v1", query: "composition=v1", expect: { app: "v4", composition: "v1" } },
  { id: "composition=v2", query: "composition=v2", expect: { app: "v4", composition: "v2" } },
  { id: "composition=sourceExact", query: "composition=sourceExact",
    expect: { app: "v4", composition: "sourceExact" },
    why: "must reach V4 source-exact WITHOUT optics=v4" },
  { id: "optics=v4&composition=sourceExact", query: "optics=v4&composition=sourceExact",
    expect: { app: "v4", composition: "sourceExact" } },
  { id: "optics=v4", query: "optics=v4", expect: { app: "v4", composition: "v1" },
    why: "V4 with no composition keeps the accepted v1 baseline" },
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const report = { checkedAt: new Date().toISOString(), origin: opts.origin, routes: [] };

for (const r of ROUTES) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message)));
  const url = `${opts.origin}/?qa=1${r.query ? `&${r.query}` : ""}`;
  await page.goto(url, { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 180000 })
    .catch(() => {});
  await page.waitForTimeout(2500);
  const seen = await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    const v4 = typeof qa?.getV4State === "function" ? qa.getV4State() : null;
    return {
      app: document.body?.dataset?.optics === "v4" ? "v4" : "v3",
      hasV4State: Boolean(v4),
      composition: v4 ? v4.composition : null,
      sourceExact: v4 ? Boolean(v4.sourceExact) : null,
      frame: v4?.sourceExactFrame
        ? { cols: v4.sourceExactFrame.cols, rows: v4.sourceExactFrame.rows,
            planeWidth: v4.sourceExactFrame.planeWidth, layoutVersion: v4.sourceExactFrame.layoutVersion }
        : null,
      cameraOnAxis: v4?.sourceExactCamera ? v4.sourceExactCamera.cameraOnAxis : null,
      ready: Boolean(qa?.getState?.()?.ready),
    };
  });
  const pass = seen.app === r.expect.app
    && (r.expect.composition === null || seen.composition === r.expect.composition);
  report.routes.push({ ...r, url, resolved: seen, pass, pageErrors: errors });
  console.log(`${pass ? "PASS" : "FAIL"}  ${r.id.padEnd(32)} -> app=${seen.app} composition=${seen.composition}`);
  await ctx.close();
}
await browser.close();
report.passed = report.routes.filter((r) => r.pass).length;
report.total = report.routes.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
report.note = "sourceExact is reachable by its own route but is still NOT the bare-page "
  + "default, and this branch is not merged to main.";
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report, null, 2));
console.log(`route proof ${report.verdict}  ${report.passed}/${report.total}`);
