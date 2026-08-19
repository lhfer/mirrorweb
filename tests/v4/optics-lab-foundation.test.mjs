import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const BASE_COMMIT = "e37bc539e127870d4c1428f12402319f1c98fbc3";
const CLEAN_FOUNDATION_COMMIT = "3f57807cd6927935bd854a8a5ae7dbb1e551f4dd";

async function source(relativePath) {
  return readFile(path.join(REPO_ROOT, relativePath), "utf8");
}

async function sha256File(relativePath) {
  return createHash("sha256").update(await readFile(path.join(REPO_ROOT, relativePath))).digest("hex");
}

test("the V4 lab publishes a fail-closed normal-path optics contract", async () => {
  const lab = await source("src/lab-v4/main.ts");
  assert.match(lab, /normalPathDirectMedia\s*:\s*false\b/);
  assert.match(lab, /v3Preserved\s*:\s*true\b/);
  assert.match(lab, /target\.type\s*===\s*HalfFloatType\s*\?\s*["']half-float["']/);
  assert.match(lab, /target\.colorSpace\s*===\s*LinearSRGBColorSpace\s*\?\s*["']linear["']/);
  assert.match(lab, /__ILG_V4_LAB_QA__/);
  assert.match(lab, /query\.get\(["']optics["']\)/);
  for (const method of ["setPattern", "setMode", "setDebug", "setPointer", "getState", "getMeasurementState"]) {
    assert.match(lab, new RegExp(`\\b${method}\\b`), `missing QA method ${method}`);
  }
});

test("the V4 scene target is linear half-float and normal refraction is scene-color driven", async () => {
  const target = await source("src/rendering/SceneColorTargetV4.ts");
  const material = await source("src/materials/LiquidGlassMaterialV4.ts");
  const lab = await source("src/lab-v4/main.ts");
  assert.match(target, /HalfFloatType/);
  assert.match(target, /LinearSRGBColorSpace/);
  assert.match(lab, /renderer\.toneMapping\s*=\s*NoToneMapping/);
  assert.match(lab, /worldScene\.environment\s*=\s*stripLightEnvironment/);
  assert.match(lab, /scenePatternTexture\.repeat\.set/);
  assert.match(material, /sceneColor/i);
  assert.doesNotMatch(material, /mix\s*\(\s*directMediaTexture\s*,\s*refractedScene/i);
});

test("the protected V3 runtime remains byte-identical to the accepted baseline", async () => {
  const protectedFiles = [
    "src/main.ts",
    "src/app/App.ts",
    "src/lab/main.ts",
    "src/materials/LiquidGlassMaterial.ts",
    "src/interaction/MotionController.ts",
    "src/scene/ConvexGlassGeometry.ts",
    "src/scene/InfiniteGlassGrid.ts",
    "src/ui/TileLabelLayer.ts",
  ];
  for (const relativePath of protectedFiles) {
    const baseline = execFileSync("git", ["show", `${BASE_COMMIT}:${relativePath}`], {
      cwd: REPO_ROOT,
      encoding: "utf8",
    });
    assert.equal(await source(relativePath), baseline, `${relativePath} changed outside the isolated V4 lab`);
  }
});

test("the optics capture matrix covers required views, patterns and pointer motion", async () => {
  const capture = await source("scripts/v4/capture-optics-lab.mjs");
  for (const identifier of [
    "split-checker",
    "v3-checker",
    "difference-checker",
    "edge-mask-black",
    "normals-checker",
    "thickness-checker",
    "refraction-offset-checker",
    "fresnel-black",
    "adaptivity-flat",
    "v4-checker",
    "v4-horizontal-lines",
    "v4-vertical-lines",
    "v4-high-frequency-photo",
    "v4-low-frequency-flat",
    "v4-white",
    "v4-black",
    "dispersion-checker",
    "reflection-pointer-",
  ]) {
    assert.ok(capture.includes(identifier), `capture matrix is missing ${identifier}`);
  }
  assert.match(capture, /gpuExecutionTimeMeasured:\s*false/);
  assert.match(capture, /naturalMediaTextureCoverage:\s*false/);
  assert.match(capture, /isFallbackAdapter\s*===\s*true/);
  assert.match(capture, /runtimeSourceSetSha256/);
  assert.match(capture, /servedResourceIdentity/);
});

test("capture and measurement scripts parse, and blocked results contain no invented metrics", async () => {
  const nodeCheck = spawnSync(process.execPath, ["--check", "scripts/v4/capture-optics-lab.mjs"], {
    cwd: REPO_ROOT,
    encoding: "utf8",
  });
  assert.equal(nodeCheck.status, 0, nodeCheck.stderr);
  const pythonCheck = spawnSync("python3", [
    "-c",
    "from pathlib import Path; compile(Path('scripts/v4/measure-optics-lab.py').read_text(), 'measure-optics-lab.py', 'exec')",
  ], { cwd: REPO_ROOT, encoding: "utf8" });
  assert.equal(pythonCheck.status, 0, pythonCheck.stderr);

  const result = JSON.parse(await source("qa-v4/results/optics-lab-foundation.json"));
  assert.equal(result.finalQuantitativeAcceptance, "BLOCKED");
  assert.equal(result.caveats.gpuExecutionTimeMeasured, false);
  assert.equal(result.caveats.naturalMediaTextureCoverage, false);
  if (result.measurementRun.executed === false) {
    assert.equal(result.status, "BLOCKED");
    assert.deepEqual(result.metrics, {});
    assert.deepEqual(result.checks, []);
  } else {
    assert.ok(["PASS", "FAIL"].includes(result.status));
    assert.ok(result.measurementRun.inputManifestSha256);
    assert.match(result.measurementRun.privateSessionVideoSha256, /^[a-f0-9]{64}$/);
    assert.match(result.measurementRun.privateUiPreviewSha256, /^[a-f0-9]{64}$/);
    assert.ok(result.metrics.centerSharpness);
    assert.ok(result.metrics.highlightPath);
    assert.ok(result.metrics.dispersionLocalization);
    assert.equal(result.sourceIdentity.head, CLEAN_FOUNDATION_COMMIT);
    assert.equal(result.sourceIdentity.dirtyWithinRuntimeScope, false);
    assert.match(result.sourceIdentity.runtimeSourceSetSha256, /^[a-f0-9]{64}$/);
    const capturedRuntimeIdentityLines = [];
    for (const entry of result.sourceIdentity.files) {
      const committedBytes = execFileSync("git", ["show", `${CLEAN_FOUNDATION_COMMIT}:${entry.path}`], {
        cwd: REPO_ROOT,
      });
      const committedHash = createHash("sha256").update(committedBytes).digest("hex");
      assert.equal(committedHash, entry.sha256, `clean foundation source mismatch: ${entry.path}`);
      capturedRuntimeIdentityLines.push(`${entry.path}:${committedHash}`);
    }
    assert.equal(
      createHash("sha256").update(capturedRuntimeIdentityLines.join("\n")).digest("hex"),
      result.sourceIdentity.runtimeSourceSetSha256,
      "clean foundation runtime source-set identity drifted",
    );
    assert.match(result.servedResourceIdentity.manifestSha256, /^[a-f0-9]{64}$/);
    assert.equal(
      result.servedResourceIdentity.resourceCount,
      result.servedResourceIdentity.resources.length,
    );
    for (const artifact of Object.values(result.artifacts)) {
      assert.match(artifact.path, /^qa-v4\/results\/optics-lab-foundation-artifacts\/[^/]+\.svg$/);
      assert.equal(await sha256File(artifact.path), artifact.sha256);
      const svg = await source(artifact.path);
      assert.doesNotMatch(svg, /data:image|<image\b|\.png\b|\.jpe?g\b/i);
    }
  }
});

test("symmetric edge compression cannot cancel into a zero line-displacement pass", async () => {
  const program = String.raw`
import importlib.util, json, numpy as np
spec = importlib.util.spec_from_file_location("measure", "scripts/v4/measure-optics-lab.py")
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)
height, width = 240, 360
rgb = np.ones((height, width, 3), dtype=np.float32)
line_centers = list(range(40, 201, 20))
for line in line_centers:
    rgb[line - 2:line + 2, :, :] = 0
silhouette = np.zeros((height, width), dtype=bool)
silhouette[30:210, 60:300] = True
rgb[30:210, 60:300, :] = 1
for x in range(60, 300):
    strength = abs((x - 180) / 120) ** 3 * 5
    for line in line_centers:
        # Upper and lower lines move in opposite directions toward center.
        shifted = line + round(-((line - 120) / 90) * strength)
        rgb[max(30, shifted - 2):min(210, shifted + 2), x, :] = 0
zones = {"bbox": (60, 30, 300, 210), "silhouette": silhouette}
horizontal = measure.line_displacement_metrics(rgb, zones, "horizontal")
vertical = measure.line_displacement_metrics(
    np.transpose(rgb, (1, 0, 2)),
    {"bbox": (30, 60, 210, 300), "silhouette": silhouette.T},
    "vertical",
)
displacement_svg = measure.displacement_plot_svg({"horizontal": horizontal, "vertical": vertical})
highlight_svg = measure.highlight_path_svg({"samples": [
    {"pointer": [-0.8, 0], "centroidNormalized": [0.2, 0.5]},
    {"pointer": [0.8, 0], "centroidNormalized": [0.8, 0.5]},
]})
print(json.dumps({
    "horizontal": horizontal,
    "vertical": vertical,
    "svgSafe": all("<image" not in svg and "data:image" not in svg for svg in (displacement_svg, highlight_svg)),
}))
`;
  const run = spawnSync("python3", ["-c", program], { cwd: REPO_ROOT, encoding: "utf8" });
  assert.equal(run.status, 0, run.stderr);
  const metrics = JSON.parse(run.stdout);
  assert.equal(metrics.svgSafe, true);
  for (const orientation of ["horizontal", "vertical"]) {
    const value = metrics[orientation];
    assert.ok(value.outerSymmetricCompressionPx > 0);
    assert.ok(value.outerLineBendingP90Px > 0);
    assert.ok(value.effectiveOuterDisplacementPx >= 1.5);
    assert.ok(value.continuityScore >= 0.70);
  }
  const measureSource = await source("scripts/v4/measure-optics-lab.py");
  assert.match(measureSource, /OUTER-LINE P90/);
  assert.match(measureSource, /EFFECTIVE OUTER/);
  assert.doesNotMatch(measureSource, />MEDIAN ABS</);
});
