#!/usr/bin/env node
/**
 * VC2 §八.6 -- the previously shipped default is still there.
 *
 * The chrome change lands on every route, because the footer is one component
 * shared by the V3 application and the V4 preview. What must NOT have moved is
 * the optical fallback: `?review=current` still has to pin the shipped optical
 * default, `?review=target` still has to pin the leading candidate, and the
 * no-query URL still has to boot the untouched V3 page without errors.
 *
 * Usage: vc2-route-check.mjs [--out=<json>] [--origin=http://127.0.0.1:5293]
 */
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { origin: "http://127.0.0.1:5293",
               out: path.join(REPO, "artifacts/visual-convergence/route-check.json") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k === "origin") opts.origin = v;
  else if (k === "out") opts.out = path.resolve(REPO, v);
}

const ROUTES = [
  { key: "shipped-default", url: "/", expectV4: false, expectBody: null },
  { key: "review-current", url: "/?review=current&qa", expectV4: true, expectBody: "current" },
  { key: "review-target", url: "/?review=target&qa", expectV4: true,
    expectBody: "target-source-unclamped" },
];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const report = { what: "VC2 §八.6 route check", origin: opts.origin,
                 checkedAt: new Date().toISOString(), rows: [], errors: [] };

for (const r of ROUTES) {
  for (const vp of ["1440x900", "390x844"]) {
    const [w, h] = vp.split("x").map(Number);
    const ctx = await browser.newContext({ viewport: { width: w, height: h },
      deviceScaleFactor: 1, hasTouch: w < 768, isMobile: w < 768 });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(`${r.key} ${vp} pageerror: ${e.message}`));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(`${r.key} ${vp} console: ${m.text()}`);
    });
    await page.goto(opts.origin + r.url, { waitUntil: "load", timeout: 150000 });
    await page.waitForTimeout(r.expectV4 ? 9000 : 9000);
    const state = await page.evaluate(() => {
      const qa = window.__ILG_QA__;
      const scrim = document.querySelector(".page-chrome-scrim");
      const foot = document.querySelector(".page-footer");
      const mark = document.querySelector(".footer-wordmark");
      const box = (el) => {
        if (!el) return null;
        const b = el.getBoundingClientRect();
        return [+b.x.toFixed(2), +b.y.toFixed(2), +b.width.toFixed(2), +b.height.toFixed(2)];
      };
      let optics = null;
      try { optics = qa?.getOpticsState?.() ?? null; } catch { optics = null; }
      return {
        hasQa: !!qa,
        opticalBody: optics?.opticalBody ?? null,
        toneMappingExposure: optics?.toneMappingExposure ?? null,
        scrim: box(scrim), footer: box(foot), wordmark: box(mark),
        scrimBackground: scrim ? getComputedStyle(scrim).backgroundImage.slice(0, 90) : null,
        canvas: !!document.querySelector("#viewport canvas"),
      };
    });
    report.rows.push({ route: r.key, vp, url: r.url, ...state,
      opticalBodyExpected: r.expectBody,
      opticalBodyOk: r.expectBody === null ? true : state.opticalBody === r.expectBody,
      chromePresent: !!state.scrim && !!state.footer && !!state.wordmark,
      errors });
    report.errors.push(...errors);
    await ctx.close();
  }
}
await browser.close();
report.pass = report.rows.every((x) => x.opticalBodyOk && x.chromePresent && x.canvas)
  && report.errors.length === 0;
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report, null, 1));
for (const x of report.rows) {
  console.log(`${x.route} ${x.vp}: body=${x.opticalBody} scrim=${JSON.stringify(x.scrim)} `
    + `chrome=${x.chromePresent} errors=${x.errors.length}`);
}
console.log(report.pass ? "ROUTE CHECK PASS" : "ROUTE CHECK FAIL");
console.log(`-> ${opts.out}`);
process.exit(report.pass ? 0 : 1);
