import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

async function source(relativePath) {
  return readFile(path.join(ROOT, relativePath), "utf8");
}

async function json(relativePath) {
  return JSON.parse(await source(relativePath));
}

async function exists(relativePath) {
  try {
    await stat(path.join(ROOT, relativePath));
    return true;
  } catch {
    return false;
  }
}

test("the main page keeps V3 as its default and loads V4 only behind the flag", async () => {
  const main = await source("src/main.ts");
  // The V3 boot is intact.
  assert.match(main, /new App\(\)/);
  assert.match(main, /await app\.start\(\)/);
  assert.match(main, /installQAHooks\(app\)/);
  // V4 is opt-in, and dynamically imported so the default path never loads it.
  assert.match(main, /get\("optics"\) === "v4"/);
  assert.match(main, /await import\("\.\/v4\/preview\/entry"\)/);
  assert.ok(!/^import .*v4\/preview/m.test(main), "V4 must not be a static import on the default path");

  const calibration = await json("config/calibration.v4.json");
  assert.equal(calibration.routing.mainPageFlag.default, "v3");
  assert.equal(calibration.routing.mainPageFlag.queryKey, "optics");
  assert.equal(calibration.routing.mainPageFlag.loading, "dynamic-import-only-when-flagged");

  // The recorded patch hash must describe the file that is actually on disk.
  const { execFileSync } = await import("node:child_process");
  const patch = execFileSync(
    "git",
    ["diff", "--unified=0", calibration.baseline.sourceCommit, "--", "src/main.ts"],
    { cwd: ROOT, encoding: "utf8" },
  );
  const changed = patch.split("\n")
    .filter((line) => (line.startsWith("+") && !line.startsWith("+++")) || (line.startsWith("-") && !line.startsWith("---")))
    .map((line) => line.trim())
    .filter(Boolean);
  assert.equal(
    createHash("sha256").update(changed.join("\n")).digest("hex"),
    calibration.routing.mainPageFlag.patchSha256,
    "src/main.ts changed without re-pinning routing.mainPageFlag.patchSha256",
  );
});

test("/grid-lab-v4 is routed, built and points at the V4 preview", async () => {
  assert.ok(await exists("grid-lab-v4.html"));
  const html = await source("grid-lab-v4.html");
  assert.match(html, /src\/v4\/preview\/lab\.ts/);
  for (const id of ["viewport", "labels", "page-overlay", "loading-overlay"]) {
    assert.ok(html.includes(`id="${id}"`), `grid lab is missing #${id}`);
  }
  const vite = await source("vite.config.ts");
  assert.match(vite, /gridLabV4: resolve\(root, "grid-lab-v4\.html"\)/);
  assert.match(vite, /req\.url === "\/grid-lab-v4"/);
  const lab = await source("src/v4/preview/lab.ts");
  assert.match(lab, /startGridPreviewV4/);
  assert.match(lab, /hud/);
});

test("the V4 preview runs the real grid systems and none of the V3 optics", async () => {
  const grid = await source("src/v4/preview/InfiniteGlassGridV4.ts");
  // Real layout, curvature and catalog come from the untouched V3 modules.
  assert.match(grid, /from "\.\.\/\.\.\/scene\/GridCurvature"/);
  assert.match(grid, /from "\.\.\/\.\.\/content\/catalog"/);
  assert.match(grid, /GRID, TILE/);
  // Optics are V4 only.
  assert.match(grid, /createConvexGlassGeometryV4/);
  assert.match(grid, /createLiquidGlassMaterialV4/);
  assert.ok(!grid.includes("createGlassMaterial("), "V4 grid must not build the V3 glass material");
  assert.ok(!grid.includes("ConvexGlassGeometry\""), "V4 grid must not build the V3 geometry");

  const app = await source("src/v4/preview/GridAppV4.ts");
  // Motion, input and CSS3D typography stay the V3 systems for Round 1.
  assert.match(app, /MotionController/);
  assert.match(app, /InputController/);
  assert.match(app, /TileLabelLayer/);
  assert.match(app, /createStripLightEnvironmentV4/);
  assert.match(app, /updatePointerKeyLightV4/);
});

test("the V4 normal path has no media map and the optics bench is left at identity", async () => {
  const material = await source("src/materials/LiquidGlassMaterialV4.ts");
  assert.ok(!material.includes("mediaMap"));
  assert.ok(!material.includes("directMediaTexture"));
  assert.match(material, /sceneColorTexture/);
  // The scene-uv mapping is additive: default 1 keeps /glass-lab-v4 unchanged.
  assert.match(material, /sceneUvScale: uniform\(1\)/);
  assert.match(material, /setSceneUvScale/);
});

test("screen-UV clamping is impossible by construction at the preview overscan", async () => {
  const pipeline = await source("src/v4/preview/SceneColorPipelineV4.ts");
  const overscan = Number(/overscan: number = ([\d.]+)/.exec(pipeline)?.[1]);
  assert.ok(Number.isFinite(overscan), "pipeline must declare a default overscan");
  const config = await source("src/v4/OpticsConfigV4.ts");
  const value = (key) => Number(new RegExp(`${key}: ([\\d.]+)`).exec(config)?.[1]);
  const reach = 0.5 + value("maxRefractionUv") + value("dispersionUv") + value("adaptivityRadiusUv");
  const headroom = 0.5 - (1 / overscan) * reach;
  assert.ok(headroom > 0, `overscan ${overscan} leaves ${headroom} headroom; a border sample would clamp`);
  // Without overscan the same arithmetic must be negative, otherwise the check
  // would pass for the wrong reason.
  assert.ok(0.5 - reach < 0);
  assert.match(pipeline, /clampHeadroom/);
});

test("Round 1 gate result, when present, is a passing engineering gate that keeps pixel truth blocked", async (t) => {
  if (!(await exists("qa-v4/results/round1-grid-preview-gate.json"))) {
    t.skip("run npm run v4:round1:gate first");
    return;
  }
  const result = await json("qa-v4/results/round1-grid-preview-gate.json");
  assert.equal(result.round, 1);
  assert.equal(result.status, "PASS");
  assert.equal(result.humanAnnotation, "SKIPPED_BY_PRODUCT_OWNER");
  assert.equal(result.formalPixelTruth, "BLOCKED");
  assert.equal(result.finalTargetMatch, "BLOCKED");
  assert.equal(result.productVisualAcceptance, "PENDING_HUMAN_PREVIEW");
  const ids = result.checks.map((entry) => entry.id);
  for (const required of [
    "V3_PAGE_AVAILABLE",
    "V4_NORMAL_PATH_NO_DIRECT_MEDIA",
    "NO_FIXED_BLACK_BODY_RIM",
    "POINTER_CHANGES_REFLECTION",
    "NO_FULL_SCREEN_DISPERSION",
    "NO_BORDER_PIXEL_STREAK",
    "RESOURCE_COUNT_STABLE",
    "VIDEO_UPLOAD_NOT_PER_RENDER_FRAME",
    "NO_SUSTAINED_MEMORY_GROWTH",
    "CONSOLE_ERROR_FREE",
    "GPU_VALIDATION_ERROR_FREE",
    "DESKTOP_AND_MOBILE_RUN",
    "V4_CAN_RETURN_TO_V3",
  ]) {
    assert.ok(ids.includes(required), `gate is missing ${required}`);
  }
  assert.ok(result.sceneColor.clampHeadroom > 0);
  assert.equal(result.pool.materials, 5, "one refraction body, one shell, three media materials");
});

test("human annotation is recorded as skipped and pixel truth stays blocked", async () => {
  const calibration = await json("config/calibration.v4.json");
  assert.equal(calibration.v4.humanAnnotation.status, "SKIPPED_BY_PRODUCT_OWNER");
  assert.equal(calibration.v4.humanAnnotation.formalPixelTruth, "BLOCKED");
  assert.equal(calibration.v4.humanAnnotation.blocksVisualPreviewDevelopment, false);
  assert.equal(calibration.v4.humanAnnotation.reviewerModeStatus, "optional-diagnostic-tool");
  assert.equal(calibration.v4.productVisualAcceptance.finalMerge, "requires-explicit-human-approval");

  // The private annotation contract is still fully pending and untouched.
  if (await exists("qa-v4/reference/frozen-visual/annotations.private.json")) {
    const annotations = await json("qa-v4/reference/frozen-visual/annotations.private.json");
    assert.equal(annotations.reviewStatus, "PENDING");
    assert.ok(Object.values(annotations.roles).every((role) => role.reviewStatus === "PENDING"));
  }
});

test("round 1 scripts parse and keep their private output inside the ignored review bundle", async () => {
  const gate = await source("scripts/v4/round1-gate.mjs");
  const capture = await source("scripts/v4/capture-round1-preview.mjs");
  const sheets = await source("scripts/v4/build-round1-contact-sheets.py");
  assert.match(gate, /qa-v4\/review\/round-1/);
  assert.match(capture, /qa-v4\/review\/round-1/);
  assert.match(sheets, /assert_private_output/);
  // The public gate result must stay in qa-v4/results and carry no pixels.
  assert.match(gate, /qa-v4\/results\/round1-grid-preview-gate\.json/);
  if (await exists("qa-v4/results/round1-grid-preview-gate.json")) {
    const serialized = await source("qa-v4/results/round1-grid-preview-gate.json");
    assert.ok(!/\/Users\/|file:\/\/|\.png|\.webm/.test(serialized), "public gate result leaks a local path or asset");
  }
});
