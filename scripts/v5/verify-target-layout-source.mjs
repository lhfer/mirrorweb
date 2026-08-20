#!/usr/bin/env node
/**
 * `npm run v5:target-layout-source`
 *
 * The source contract is only worth anything if it is still true. This checks
 * three things and fails loudly on any of them:
 *
 *   1. The Target's app bundle still hashes to what the contract recorded.
 *      A redeploy can change the layout constants under us; when the hash
 *      moves this FAILS and asks for fresh forensics. It never rewrites the
 *      contract on its own, and it never relaxes a tolerance.
 *   2. TypeScript, Python and the live Target DOM agree.
 *      The TypeScript side is read from the RUNNING APP, not re-imported in
 *      Node: re-importing checks a copy, driving the app checks what ships.
 *   3. The contract file is the only place the constants live.
 *
 * Read-only against the Target.
 */
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const contractArg = process.argv.slice(2).find((a) => a.startsWith("--contract="));
// `--contract=` exists so the FAILURE path can be exercised for real rather than
// asserted. A gate whose red branch has never run is not a gate.
const CONTRACT_PATH = contractArg
  ? path.resolve(REPO, contractArg.slice(11))
  : path.join(REPO, "config/target-layout-source-v2.json");
const CONTRACT = JSON.parse(readFileSync(CONTRACT_PATH, "utf8"));
const opts = { origin: "http://127.0.0.1:5280", out: null, skipTarget: false,
  vps: ["1440x900", "1920x1080", "390x844", "667x375", "700x700", "960x500"] };
for (const a of process.argv.slice(2)) {
  if (a.startsWith("--origin=")) opts.origin = a.slice(9);
  else if (a.startsWith("--out=")) opts.out = path.resolve(REPO, a.slice(6));
  else if (a.startsWith("--vps=")) opts.vps = a.slice(6).split(",");
  else if (a === "--skip-target") opts.skipTarget = true;
  else if (a.startsWith("--contract=")) { /* handled above */ }
}

const report = { checkedAt: new Date().toISOString(), contract: path.relative(REPO, CONTRACT_PATH),
                 layoutVersion: CONTRACT.layoutVersion, checks: [] };
const add = (name, pass, detail) => report.checks.push({ check: name, pass: !!pass, detail });

// ---- 1. bundle hash -------------------------------------------------------
const bundleUrl = new URL(CONTRACT.target.appBundlePath, CONTRACT.target.url).toString();
let liveHash = null;
if (!opts.skipTarget) {
  const res = await fetch(bundleUrl);
  if (!res.ok) throw new Error(`bundle fetch failed: ${res.status}`);
  liveHash = createHash("sha256").update(Buffer.from(await res.arrayBuffer())).digest("hex");
  add("Target app bundle hash unchanged", liveHash === CONTRACT.target.appBundleSha256,
      { url: bundleUrl, recorded: CONTRACT.target.appBundleSha256, live: liveHash,
        onFailure: "The Target redeployed. Re-run source forensics and re-derive the contract "
          + "before trusting any layout number. Do NOT edit the hash to match." });
} else {
  add("Target app bundle hash unchanged", false, { skipped: true });
}

// ---- 2. Python model ------------------------------------------------------
const py = spawnSync("python3", ["-c", `
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("sl", "scripts/v5/source_layout.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
out = {}
for vp in ${JSON.stringify(opts.vps)}:
    w, h = (int(x) for x in vp.split("x"))
    f = m.layout(w, h)
    f["fovDeg"] = m.camera(f)["fovDeg"]
    out[vp] = f
print(json.dumps(out))
`], { cwd: REPO, encoding: "utf8" });
if (py.status !== 0) throw new Error(`python model failed: ${py.stderr}`);
const pyFrames = JSON.parse(py.stdout);

// ---- 3. TypeScript, read from the running app -----------------------------
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto(`${opts.origin}/?optics=v4&qa=1&composition=sourceExact&foundation=layout&annotate=0`,
                { waitUntil: "load", timeout: 120000 });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true, undefined, { timeout: 120000 });
await page.waitForTimeout(1500);
await page.evaluate(() => { window.__ILG_QA__.setPointer(0, 0); window.__ILG_QA__.pause(); });

const FIELDS = ["perspective", "sphereRadius", "planeWidth", "planeHeight", "cellW", "cellH",
                "periodX", "periodY", "cardScale"];
let worstTs = 0;
for (const vp of opts.vps) {
  const [w, h] = vp.split("x").map(Number);
  await page.setViewportSize({ width: w, height: h });
  await page.waitForTimeout(160);
  const ts = await page.evaluate(() => {
    const v = window.__ILG_QA__.getV4State();
    return { frame: v.sourceExactFrame, camera: v.sourceExactCamera };
  });
  const model = pyFrames[vp];
  for (const f of FIELDS) worstTs = Math.max(worstTs, Math.abs(ts.frame[f] - model[f]));
  const exact = ts.frame.cols === model.cols && ts.frame.rows === model.rows
    && ts.frame.activeSlotCount === model.activeSlotCount;
  add(`TypeScript matches Python at ${vp}`, exact && worstTs <= 1e-9,
      { cols: [ts.frame.cols, model.cols], rows: [ts.frame.rows, model.rows],
        worstFieldDelta: worstTs,
        fovDelta: Math.abs(ts.camera.actualFovDeg - model.fovDeg) });
  add(`Contract hash reaches the running app at ${vp}`,
      ts.frame.bundleHash === CONTRACT.target.appBundleSha256
      && ts.frame.layoutVersion === CONTRACT.layoutVersion,
      { bundleHash: ts.frame.bundleHash, layoutVersion: ts.frame.layoutVersion });
}
await ctx.close();

// ---- 4. Target DOM --------------------------------------------------------
if (!opts.skipTarget) {
  const tctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const tpage = await tctx.newPage();
  await tpage.goto(CONTRACT.target.url, { waitUntil: "load", timeout: 120000 });
  for (let i = 0; i < 240; i += 1) {
    const s = await tpage.evaluate(() => {
      const m = (document.body?.innerText || "").match(/(\d+)\s*%/);
      return { p: m ? Number(m[1]) : null, c: !!document.querySelector("canvas") };
    });
    if (s.c && (s.p === null || s.p >= 100)) break;
    await tpage.waitForTimeout(150);
  }
  await tpage.waitForTimeout(6000);
  const live = await tpage.evaluate(() => {
    let persp = null;
    for (const d of document.querySelectorAll("div")) {
      const cs = getComputedStyle(d);
      if (cs.perspective !== "none") { persp = parseFloat(cs.perspective); break; }
    }
    let plane = null;
    for (const d of document.querySelectorAll("div")) {
      const cs = getComputedStyle(d);
      if (!cs.transform.startsWith("matrix3d")) continue;
      const t = (d.innerText || "");
      if ((t.match(/ILG[—-]\s?\d+/g) || []).length !== 1) continue;
      plane = [parseFloat(cs.width), parseFloat(cs.height)];
      break;
    }
    return { persp, plane };
  });
  await tctx.close();
  const model = pyFrames["1440x900"];
  add("Live Target DOM matches the model at 1440x900",
      Math.abs(live.persp - model.perspective) <= 0.01
      && Math.abs(live.plane[0] - model.planeWidth) <= 0.05
      && Math.abs(live.plane[1] - model.planeHeight) <= 0.05,
      { targetPerspective: live.persp, modelPerspective: model.perspective,
        targetPlane: live.plane, modelPlane: [model.planeWidth, model.planeHeight] });
}
await browser.close();

report.passed = report.checks.filter((c) => c.pass).length;
report.total = report.checks.length;
report.verdict = report.passed === report.total ? "PASS" : "FAIL";
report.liveBundleSha256 = liveHash;
if (opts.out) {
  mkdirSync(path.dirname(opts.out), { recursive: true });
  writeFileSync(opts.out, JSON.stringify(report, null, 2));
}
console.log(`v5:target-layout-source ${report.verdict}  ${report.passed}/${report.total}`);
for (const c of report.checks) if (!c.pass) console.log(`  FAIL ${c.check}  ${JSON.stringify(c.detail)}`);
if (report.verdict !== "PASS") process.exit(1);
