#!/usr/bin/env node
/**
 * Did the motion work move anything on the routes it was not supposed to touch?
 *
 * `MotionController` and `InputController` are shared files: v1, v2 and the
 * bare route run through the same classes the source-exact path now branches
 * inside. "The legacy branch is untouched" is a claim about a diff; this is the
 * claim measured, by rendering both builds side by side under identical fixed
 * conditions and comparing the canvas bytes.
 *
 * Two servers: the candidate on one port, the pre-motion commit on another,
 * served from a git worktree so the comparison is against a real build of that
 * commit rather than against a memory of it.
 *
 * Usage:
 *   m1-legacy-invariance.mjs --before=<origin> --after=<origin> --out=<json>
 */
import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { before: "http://127.0.0.1:5281", after: "http://127.0.0.1:5280",
  out: path.join(REPO, "qa-v5/motion/legacy-invariance.json"),
  vps: ["1440x900", "390x844"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--before=")) opts.before = a.slice(9);
  else if (a.startsWith("--after=")) opts.after = a.slice(8);
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
}

const ROUTES = [
  { id: "bare", query: "qa=1", v4: false },
  { id: "composition=v1", query: "qa=1&composition=v1", v4: true },
  { id: "composition=v2", query: "qa=1&composition=v2", v4: true },
];

const sha = (buf) => createHash("sha256").update(buf).digest("hex");

async function capture(browser, origin, route, w, h) {
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(`${origin}/?${route.query}`, { waitUntil: "load", timeout: 120000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 180000 });
  await page.waitForTimeout(2600);
  // The identical fixed state on both builds. Quality pinned, sampler off,
  // media frozen at the same time, pointer at origin, motion paused.
  await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    // Optional-chained throughout: the bare route is the V3 shell and does not
    // carry every V4 hook. A TypeError here would abort the capture and the
    // row would read as a difference that was never measured.
    qa.setAdaptiveQuality?.(false);
    qa.setQuality?.("high");
    qa.setDpr?.(1);
    qa.setPointer?.(0, 0);
    qa.pause?.();
    qa.setOffset?.(0, 0);
  });
  await page.evaluate(() => window.__ILG_QA__.setMediaTimeAndFreeze?.(2));
  await page.evaluate(() => window.__ILG_QA__.renderOnce?.());
  await page.waitForTimeout(500);
  const shot = await page.screenshot({ type: "png" });
  const state = await page.evaluate(() => {
    const qa = window.__ILG_QA__;
    const s = qa.getState();
    return { ready: s.ready, composition: s.composition ?? null, app: s.app ?? null,
             scrollX: qa.getV4State?.().scrollX ?? null };
  }).catch(() => null);
  await ctx.close();
  return { sha: sha(shot), bytes: shot.length, errors, state };
}

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

const report = { checkedAt: new Date().toISOString(), before: opts.before, after: opts.after,
  what: "v1, v2 and the bare route rendered by the pre-motion commit and by the candidate, "
      + "under identical fixed conditions",
  fixed: { quality: "high", adaptiveSampler: "off", dpr: 1, pointer: [0, 0],
           mediaTimeSeconds: 2, motion: "paused", offset: [0, 0] },
  rows: [], assertions: [] };
const A = (n, ok, d) => report.assertions.push({ assertion: n, pass: !!ok, detail: d ?? null });

for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  for (const route of ROUTES) {
    const b = await capture(browser, opts.before, route, w, h);
    const a = await capture(browser, opts.after, route, w, h);
    const row = { viewport: vp, route: route.id, beforeSha: b.sha, afterSha: a.sha,
                  identical: b.sha === a.sha, beforeBytes: b.bytes, afterBytes: a.bytes,
                  beforeErrors: b.errors, afterErrors: a.errors };
    report.rows.push(row);
    A(`${vp} ${route.id}: byte-identical to the pre-motion commit`, row.identical, row);
    process.stdout.write(`  ${vp} ${route.id}  ${row.identical ? "identical" : "DIFFERS"}\n`);
  }
}
await browser.close();

report.passed = report.assertions.filter((x) => x.pass).length;
report.total = report.assertions.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(report, null, 2));
console.log(`legacy invariance ${report.verdict}  ${report.passed}/${report.total}`);
