#!/usr/bin/env node
/**
 * O3 gate 18: prove from the GENERATED PROGRAM which support each lane's
 * beauty path actually consumes.
 *
 * The TypeScript says the geometry lane reads `v_o2NormalView` and the
 * target-sdf lane reads the analytic bevel normal. TSL codegen is exactly
 * the layer where that stopped being true once already -- O2 root-caused a
 * varying whose unpack was emitted into only the first debug branch that
 * referenced it, so the beauty path silently read zeros. So this reads the
 * shader, not the source.
 *
 * It also dumps both lanes' programs so gate 1's claim -- that the geometry
 * lane emits the O2 program -- can be checked byte for byte against the
 * pre-O3 build.
 *
 * Usage: o3-shader-proof.mjs --local=<origin> [--base=<origin>] [--out=<dir>]
 */
import { mkdir, writeFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const opts = { local: null, base: null,
  out: path.join(REPO, "artifacts/optics-o3/shader") };
for (const a of process.argv.slice(2)) {
  const [k, v] = a.replace(/^--/, "").split("=");
  if (k in opts) opts[k] = v;
}
if (!opts.local) { console.error("--local required"); process.exit(2); }

const browser = await chromium.launch({ channel: "chrome", headless: true });
await mkdir(opts.out, { recursive: true });

async function dump(origin, query, label) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(`${origin}/?composition=sourceExact&qa${query}`,
    { waitUntil: "load", timeout: 60000 });
  await page.waitForFunction(() => window.__ILG_QA__?.getState?.()?.ready === true,
    undefined, { timeout: 120000 });
  const src = await page.evaluate(() =>
    (typeof window.__ILG_QA__.getGlassShaderSource === "function"
      ? window.__ILG_QA__.getGlassShaderSource()
      : null));
  await ctx.close();
  if (!src) {
    // The pre-O3 build predates this QA readback, so its program cannot be
    // dumped. Recorded rather than fatal: gate 1 rests on the PIXEL proof,
    // and this dump is gate 18's evidence about the candidate build.
    return { label, query, shaderReadbackUnavailable: true };
  }
  const frag = src.fragmentShader;
  await writeFile(path.join(opts.out, `${label}-fragment.glsl`), frag);
  await writeFile(path.join(opts.out, `${label}-vertex.glsl`), src.vertexShader);
  return {
    label, query,
    backend: src.backend,
    reflectionSupport: src.reflectionSupport ?? null,
    dispersionLaw: src.dispersionLaw ?? null,
    fragmentSha256: createHash("sha256").update(frag).digest("hex"),
    vertexSha256: createHash("sha256").update(src.vertexShader).digest("hex"),
    fragmentBytes: Buffer.byteLength(frag),
    declaresO2Varying: /v_o2NormalView/.test(frag),
    declaresO3Varying: /v_o3CardUv\b/.test(frag),
    declaresO3RimDebugVarying: /v_o3CardUvRim/.test(frag),
    declaresO3NormalDebugVarying: /v_o3CardUvNormal/.test(frag),
    mentionsBevelMaxSlope: /1\.74/.test(frag),
    mentionsBevelPower: /3\.9/.test(frag),
  };
}

const rows = [];
rows.push(await dump(opts.local, "&reflectionSupport=geometry&dispersionLaw=o1",
  "candidate-build-geometry-lane"));
rows.push(await dump(opts.local, "&reflectionSupport=target-sdf&dispersionLaw=o1",
  "candidate-build-target-sdf-lane"));
if (opts.base) {
  rows.push(await dump(opts.base, "&dispersionLaw=o1", "pre-o3-build-o2-program"));
}

const byLabel = Object.fromEntries(rows.map((r) => [r.label, r]));
const geom = byLabel["candidate-build-geometry-lane"];
const cand = byLabel["candidate-build-target-sdf-lane"];
const base = byLabel["pre-o3-build-o2-program"];

const proof = {
  what: "O3 gate 18 -- which support each lane's generated program consumes, "
        + "and whether the geometry lane still emits the O2 program.",
  dumps: rows,
  gate1Note: (base && base.shaderReadbackUnavailable)
    ? "the pre-O3 build predates getGlassShaderSource, so its program could "
      + "not be dumped for a hash comparison. Gate 1 is the PIXEL proof "
      + "against that build; this file proves what the candidate build's two "
      + "lanes consume."
    : null,
  checks: {
    geometryLaneDeclaresO2Varying: geom.declaresO2Varying === true,
    geometryLaneHasNoO3Field:
      geom.declaresO3Varying === false
      && geom.declaresO3RimDebugVarying === false
      && geom.declaresO3NormalDebugVarying === false,
    candidateLaneDeclaresO3Varying: cand.declaresO3Varying === true,
    candidateLaneHasNoO2Varying: cand.declaresO2Varying === false,
    candidateLaneCarriesBevelConstants:
      cand.mentionsBevelMaxSlope === true && cand.mentionsBevelPower === true,
    lanesDifferAsExpected: geom.fragmentSha256 !== cand.fragmentSha256,
    geometryLaneEqualsPreO3Program: (base && !base.shaderReadbackUnavailable)
      ? geom.fragmentSha256 === base.fragmentSha256
        && geom.vertexSha256 === base.vertexSha256
      : null,
  },
};
proof.pass = Object.entries(proof.checks)
  .every(([, v]) => v === true || v === null);

await writeFile(path.join(opts.out, "shader-proof.json"),
  JSON.stringify(proof, null, 1));
for (const [k, v] of Object.entries(proof.checks)) console.log(`${v}  ${k}`);
console.log("pass:", proof.pass);
await browser.close();
process.exit(proof.pass ? 0 : 1);
