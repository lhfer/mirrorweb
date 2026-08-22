#!/usr/bin/env node
/**
 * O4 §六 inertness proof: adding the diagnostic factors must not change the
 * shipped program.
 *
 * With every flag false the material has to build the identical node graph
 * it built before the flags existed -- the same node objects, not
 * equivalent ones. That is what keeps the control lane's exact-zero proof
 * against the accepted O2 body intact, and it is checkable at the strongest
 * level available: the generated program's hash.
 *
 * The reference is `artifacts/optics-o4/audit/program-<quality>.txt`,
 * dumped during the O4A audit at the commit BEFORE any factor machinery
 * existed. Program-hash identity is a stronger statement than pixel
 * identity, and it is checked at every quality level.
 *
 * Usage: o4-factor-inertness.mjs --local=<origin> [--reference=<dir>]
 *        [--out=<json>]
 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { installLocalRoutes, loadAsset } from "./o2_media_routes.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null,
  reference: path.join(REPO, "artifacts/optics-o4/audit"),
  out: path.join(REPO, "artifacts/optics-o4/factor-inertness.json") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const sha = (s) => createHash("sha256").update(s).digest("hex");
const browser = await chromium.launch({ channel: "chrome", headless: true,
  args: ["--enable-unsafe-webgpu", "--enable-webgpu-developer-features"] });

const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await installLocalRoutes(ctx, loadAsset("bw-split"), null);
const page = await ctx.newPage();
await page.goto(`${opts.local}/?composition=sourceExact&qa&dispersionLaw=o1`
  + "&reflectionSupport=geometry&bodyDiag=000000",
  { waitUntil: "load", timeout: 60000 });
await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
  undefined, { timeout: 120000 });
await page.evaluate(() => window.__ILG_QA__.setAdaptiveQuality(false));

const rows = [];
for (const quality of ["high", "medium", "low"]) {
  await page.evaluate((q) => {
    window.__ILG_QA__.setQuality(q);
    window.__ILG_QA__.renderOnce(); window.__ILG_QA__.renderOnce();
  }, quality);
  await page.waitForTimeout(500);
  const src = await page.evaluate(() =>
    window.__ILG_QA__.getGlassShaderSource());
  const ref = await readFile(
    path.join(opts.reference, `program-${quality}.txt`), "utf8");
  const now = src.fragmentShader;
  rows.push({
    quality,
    referenceSha256: sha(ref), currentSha256: sha(now),
    referenceBytes: ref.length, currentBytes: now.length,
    identical: sha(ref) === sha(now),
    bodyDiag: src.bodyDiag ?? null,
    declaresO4BodyVarying: /v_o4BodyNormalView/.test(now),
  });
  console.log(`${quality}: identical=${rows.at(-1).identical} `
    + `(${rows.at(-1).referenceBytes} vs ${rows.at(-1).currentBytes} bytes)`);
}
await ctx.close();
await browser.close();

const doc = {
  what: "O4 §六 inertness -- with every diagnostic flag false the material "
      + "must emit the program it emitted before the flags existed.",
  reference: "artifacts/optics-o4/audit/program-<quality>.txt, dumped at the "
           + "commit before any factor machinery existed",
  query: "?bodyDiag=000000&reflectionSupport=geometry&dispersionLaw=o1",
  rows,
  pass: rows.every((r) => r.identical && r.declaresO4BodyVarying === false),
  note: "the repaired body varying must NOT appear in the all-off program; "
      + "if it does, the flag is not a build-time branch.",
};
await mkdir(path.dirname(opts.out), { recursive: true });
await writeFile(opts.out, JSON.stringify(doc, null, 1));
console.log(`pass: ${doc.pass}\n-> ${opts.out}`);
process.exit(doc.pass ? 0 : 1);
