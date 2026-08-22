#!/usr/bin/env node
/**
 * O4A — capture side of the compiled Body-path audit (§三).
 *
 * The question is whether the TSL shared-normal codegen issue O2
 * root-caused also reaches the CURRENT Beauty refraction path. It must be
 * answered from the generated program and from runtime probes, never from
 * TypeScript comments — so this script collects exactly those two things
 * and fixes nothing.
 *
 * Runtime probe design. The shipped debug chain already contains a perfect
 * discriminator, so no new code and no program change is needed:
 *
 *   `normals`  (debugCode 3) renders normalView directly. If the varying
 *              unpack is emitted anywhere it is emitted here, because this
 *              is the first branch that references it.
 *   `fresnel`  (debugCode 7) renders pow(1 - saturate(dot(normalView,
 *              positionViewDirection)), 5) — a DIFFERENT branch reading the
 *              same private. A zero normal gives dot = 0 and therefore a
 *              flat white card. A real normal gives a graded rim.
 *   `refraction-offset` (5) renders the offset whose projectedNormalOffset
 *              term is directly proportional to normalView.xy. GATE-005
 *              recorded this view as nearly flat; this audit either
 *              explains that or contradicts it.
 *   `optical-zones` (2) and `thickness` (4) read only vertex attributes
 *              that are NOT shared across branches. They are the CONTROL:
 *              if they vary correctly while the normal views disagree, the
 *              fault is specific to the shared-normal emission and not to
 *              the harness, the geometry or the capture.
 *
 * Quality levels are swept because codegen and geometry both change with
 * the quality preset, using the same `setQuality` hook every quality suite
 * uses.
 *
 * Usage: o4-body-code-audit.mjs --local=<origin> [--out=<dir>] [--freeze=4]
 */
import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, freeze: 4,
  out: path.join(REPO, "artifacts/optics-o4/audit") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = k === "freeze" ? Number(v) : v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const QUERY = "/?composition=sourceExact&qa&dispersionLaw=o1&reflectionSupport=geometry";
const VIEWS = ["beauty", "normals", "fresnel", "refraction-offset",
               "optical-zones", "thickness"];
const QUALITIES = ["high", "medium", "low"];

const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });
await mkdir(opts.out, { recursive: true });
const records = [];

const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await installLocalRoutes(ctx, loadAsset("bw-split"), null);
const page = await ctx.newPage();
await page.goto(`${opts.local}${QUERY}`, { waitUntil: "load", timeout: 60000 });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
  undefined, { timeout: 120000 });
await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));
await page.evaluate((t) => window.__ILG_QA__.setMediaTimeAndFreeze(t), opts.freeze);
await page.evaluate(() => {
  const qa = window.__ILG_QA__;
  qa.setOffset(0, 0); qa.setVelocity(0, 0); qa.jumpPointer(0, 0);
  // System B OFF -- this audit is about the BODY path.
  qa.setShellMode("off"); qa.setEnvMixScale(0); qa.setRimScale(0);
  qa.setRenderLayers({ labels: false });
});

for (const quality of QUALITIES) {
  await page.evaluate((q) => {
    window.__ILG_QA__.setQuality(q);
    window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
  }, quality);
  await page.waitForTimeout(600);

  const src = await page.evaluate(() =>
    (typeof window.__ILG_QA__.getGlassShaderSource === "function"
      ? window.__ILG_QA__.getGlassShaderSource() : null));
  let shader = null;
  if (src) {
    const frag = src.fragmentShader;
    await writeFile(path.join(opts.out, `program-${quality}.txt`), frag);
    // Where is the geometry normal actually UNPACKED, and where is it only
    // aliased? This is the whole static half of the audit.
    const unpackRe = /normalViewGeometry\s*=\s*normalize\(/g;
    const aliasRe = /normalView\s*=\s*normalViewGeometry\s*;/g;
    shader = {
      backend: src.backend,
      fragmentSha256: createHash("sha256").update(frag).digest("hex"),
      fragmentBytes: Buffer.byteLength(frag),
      declaresPrivateNormalViewGeometry:
        /var<private>\s+normalViewGeometry/.test(frag)
        || /^\s*vec3 normalViewGeometry\s*;/m.test(frag),
      unpackSites: (frag.match(unpackRe) || []).length,
      aliasSites: (frag.match(aliasRe) || []).length,
      unpackLineNumbers: frag.split("\n").reduce((acc, l, i) =>
        (/normalViewGeometry\s*=\s*normalize\(/.test(l) ? acc.concat(i + 1) : acc), []),
      aliasLineNumbers: frag.split("\n").reduce((acc, l, i) =>
        (/normalView\s*=\s*normalViewGeometry\s*;/.test(l) ? acc.concat(i + 1) : acc), []),
    };
  }

  for (const view of VIEWS) {
    await page.evaluate((v) => {
      window.__ILG_QA__.setDebugMode(v);
      window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
    }, view);
    await page.waitForTimeout(200);
    const file = `${quality}-${view}.png`;
    await page.screenshot({ path: path.join(opts.out, file) });
    records.push({ quality, view, file });
  }
  await page.evaluate(() => {
    window.__ILG_QA__.setDebugMode("beauty"); window.__ILG_QA__.renderOnce();
  });
  records.push({ quality, kind: "shader", shader });
  console.log(`${quality}: ${VIEWS.length} views, unpackSites=`
    + `${shader ? shader.unpackSites : "n/a"} aliasSites=`
    + `${shader ? shader.aliasSites : "n/a"}`);
}

await ctx.close();
await writeFile(path.join(opts.out, "audit-captures.json"), JSON.stringify({
  what: "O4A body-path audit captures — the shipped program and the debug "
      + "views that read the shared normal, at every quality level. Nothing "
      + "is fixed here.",
  origin: opts.local, query: QUERY, viewport: "1440x900",
  state: "System B OFF (envMixScale=0, rimScale=0, shell off), labels off, "
       + "deterministic bw-split frozen at 4.0s",
  probeDesign: {
    normals: "debugCode 3 — the FIRST branch to reference the normal",
    fresnel: "debugCode 7 — a DIFFERENT branch reading the same private; "
           + "a zero normal renders flat white",
    "refraction-offset": "debugCode 5 — carries projectedNormalOffset, "
           + "directly proportional to normalView.xy",
    controls: "optical-zones (2) and thickness (4) read unshared vertex "
           + "attributes; they isolate the fault to the shared normal",
  },
  records,
}, null, 1));
console.log(`-> ${opts.out}`);
await browser.close();
