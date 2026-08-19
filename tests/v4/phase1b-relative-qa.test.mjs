import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

async function source(relativePath) {
  return readFile(path.join(REPO_ROOT, relativePath), "utf8");
}

function runPython(program) {
  const result = spawnSync("python3", ["-c", program], {
    cwd: REPO_ROOT,
    encoding: "utf8",
    maxBuffer: 8 * 1024 * 1024,
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return JSON.parse(result.stdout);
}

test("categorical optical-zone palette produces independent P10/P50/P90 widths", () => {
  const value = runPython(String.raw`
import json, numpy as np, sys
sys.path.insert(0, "scripts/v4")
from lib.roi_metrics import compute_optical_zone_metrics

height, width = 200, 320
rgb = np.zeros((height, width, 3), dtype=np.float32)
silhouette = np.zeros((height, width), dtype=bool)
silhouette[20:180, 40:280] = True
yy, xx = np.nonzero(silhouette)
depth = np.minimum.reduce((yy - 20, 179 - yy, xx - 40, 279 - xx))
colors = np.zeros((len(yy), 3), dtype=np.float32)
colors[depth < 4] = (0, 0, 1)
colors[(depth >= 4) & (depth < 12)] = (0, 1, 0)
colors[(depth >= 12) & (depth < 24)] = (1, 0, 0)
colors[depth >= 24] = (.25, .25, .25)
rgb[yy, xx] = colors
print(json.dumps(compute_optical_zone_metrics(rgb, silhouette)))
`);

  assert.match(value.method, /categorical optical-zones palette/);
  assert.match(value.paletteDecode.method, /nearest match plus RGB channel argmax/);
  assert.equal(value.paletteDecode.recognizedRatio, 1);
  assert.ok(Math.abs(value.sidewallScreenWidthRatio - 0.02) < 1e-9);
  assert.ok(Math.abs(value.strongLensRimWidthRatio - 0.04) < 1e-9);
  assert.ok(Math.abs(value.opticalShoulderWidthRatio - 0.06) < 1e-9);
  assert.ok(Math.abs(value.centerFaceRatio - 0.56) < 1e-9);
  for (const distribution of Object.values(value.widthDistributions)) {
    assert.ok(distribution.sampleCount >= 16);
    assert.ok(distribution.p10 <= distribution.p50);
    assert.ok(distribution.p50 <= distribution.p90);
  }
});

test("front optical zones permit an occluded sidewall without inventing a zero width", () => {
  const value = runPython(String.raw`
import json, numpy as np, sys
sys.path.insert(0, "scripts/v4")
from lib.roi_metrics import compute_optical_zone_metrics
height, width = 200, 320
rgb = np.zeros((height, width, 3), dtype=np.float32)
silhouette = np.zeros((height, width), dtype=bool)
silhouette[20:180, 40:280] = True
yy, xx = np.nonzero(silhouette)
depth = np.minimum.reduce((yy - 20, 179 - yy, xx - 40, 279 - xx))
colors = np.zeros((len(yy), 3), dtype=np.float32)
colors[depth < 10] = (0, 1, 0)
colors[(depth >= 10) & (depth < 28)] = (1, 0, 0)
colors[depth >= 28] = (.25, .25, .25)
rgb[yy, xx] = colors
result = compute_optical_zone_metrics(
    rgb,
    silhouette,
    required_zones=("centerFace", "opticalShoulder", "strongLensRim"),
)
print(json.dumps(result))
`);
  assert.equal(value.paletteDecode.pixelCounts.sidewall, 0);
  assert.equal(value.sidewallScreenWidthRatio, null);
  assert.equal(value.widthDistributions.sidewall, null);
  assert.ok(value.strongLensRimWidthRatio > 0);
});

test("sidewall width aggregation requires both tilted poses", () => {
  const value = runPython(String.raw`
import json, sys
sys.path.insert(0, "scripts/v4")
from lib.roi_metrics import MeasurementUnavailable, aggregate_pose_width_distributions
left = {"p10": .004, "p50": .006, "p90": .008, "sampleCount": 120, "resolutionLimited": False}
right = {"p10": .005, "p50": .007, "p90": .009, "sampleCount": 130, "resolutionLimited": False}
both = aggregate_pose_width_distributions({"left": left, "right": right})
try:
    aggregate_pose_width_distributions({"left": left})
    missingBlocked = False
except MeasurementUnavailable:
    missingBlocked = True
print(json.dumps({"both": both, "missingBlocked": missingBlocked}))
`);
  assert.equal(value.missingBlocked, true);
  assert.equal(value.both.poseCount, 2);
  assert.ok(Math.abs(value.both.p50 - 0.0065) < 1e-9);
  assert.equal(value.both.sampleCount, 250);
});

test("front context fails closed without the exact optical-zones capture", () => {
  const value = runPython(String.raw`
import importlib.util, json, sys
from pathlib import Path
sys.path.insert(0, "scripts/v4")
spec = importlib.util.spec_from_file_location("phase1b_measure", "scripts/v4/measure-frozen-calibration.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
entry = module.EvidenceEntry({"id": "edge-mask-black", "role": "zone-mask", "debug": "edge-mask"}, Path("unused.png"))
try:
    module.build_local_context({}, [entry])
    print(json.dumps({"blocked": False}))
except module.MeasurementUnavailable as error:
    print(json.dumps({"blocked": True, "reason": str(error)}))
`);
  assert.equal(value.blocked, true);
  assert.match(value.reason, /requires phase1b-optical-zones-front/);
});

test("pose silhouette yields a projective quad for matching beauty rectification", () => {
  const value = runPython(String.raw`
import json, numpy as np, sys
from skimage.draw import polygon
sys.path.insert(0, "scripts/v4")
from lib.roi_metrics import infer_card_quad_from_silhouette
expected = np.asarray([[50, 30], [280, 45], [255, 170], [65, 180]], dtype=float)
yy, xx = polygon(expected[:, 1], expected[:, 0], shape=(220, 340))
silhouette = np.zeros((220, 340), dtype=bool)
silhouette[yy, xx] = True
actual = infer_card_quad_from_silhouette(silhouette)
print(json.dumps({"actual": actual.tolist(), "maxErrorPx": float(np.max(np.linalg.norm(actual - expected, axis=1))) }))
`);
  assert.ok(value.maxErrorPx < 1);
  assert.equal(value.actual.length, 4);
});

test("provisional 4.75% rim prior can never exceed CONDITIONAL", () => {
  const value = runPython(String.raw`
import importlib.util, json, sys
sys.path.insert(0, "scripts/v4")
spec = importlib.util.spec_from_file_location("phase1b_measure", "scripts/v4/measure-frozen-calibration.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
priors = module.load_priors(module.DEFAULT_PRIORS)
local = {"opticalZones": module.measured({"strongLensRimWidthRatio": .0475})}
metrics = module.target_relative_metrics(local, None, priors, {}, {}, {})
print(json.dumps({"prior": priors["targetStrongLensRim"], "metrics": metrics}))
`);
  assert.equal(value.prior.status, "CONDITIONAL");
  assert.equal(value.prior.maximumResultStatus, "CONDITIONAL");
  assert.equal(value.prior.mayClaimPixelTruth, false);
  assert.deepEqual([value.prior.min, value.prior.max, value.prior.center], [0.046, 0.049, 0.0475]);
  assert.equal(value.metrics.rimWidthRelativeError.status, "CONDITIONAL");
  assert.equal(value.metrics.rimWidthRelativeError.value.withinTargetRange, true);
  for (const [name, metric] of Object.entries(value.metrics)) {
    if (name === "rimWidthRelativeError" || name === "targetLocalEdgeRoiOverlay") continue;
    assert.equal(metric.status, "BLOCKED", `${name} invented unavailable target truth`);
  }
});

test("approved quads do not promote unapproved natural feature metrics", () => {
  const value = runPython(String.raw`
import importlib.util, json, sys
sys.path.insert(0, "scripts/v4")
spec = importlib.util.spec_from_file_location("phase1b_measure", "scripts/v4/measure-frozen-calibration.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
annotations = {
  "reviewStatus": "APPROVED",
  "categories": {
    "high-texture": {
      "reviewStatus": "APPROVED",
      "quadReviewStatus": "APPROVED",
      "approvals": {"naturalFeatureSignature": False},
      "metrics": {"opticalShoulderWidthRatio": .9},
    }
  }
}
print(json.dumps({
  "quad": module.annotation_category(annotations, "high-texture") is not None,
  "feature": module.feature_annotation_category(annotations, "high-texture") is not None,
  "metric": module.annotation_metric(annotations, "high-texture", "opticalShoulderWidthRatio"),
}))
`);
  assert.equal(value.quad, true);
  assert.equal(value.feature, false);
  assert.equal(value.metric, null);
});

test("A/B pointer selection consumes shell metadata, excludes backgrounds, and sorts by x", () => {
  const value = runPython(String.raw`
import importlib.util, json, sys
from pathlib import Path
sys.path.insert(0, "scripts/v4")
spec = importlib.util.spec_from_file_location("phase1b_measure", "scripts/v4/measure-frozen-calibration.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

def entry(identifier, role, view, pointer, shell="additive", family="reflection-shell-ab-pointer"):
    return module.EvidenceEntry({
        "id": identifier,
        "role": role,
        "debug": view,
        "pointer": pointer,
        "shellMode": shell,
        "experimentVariant": {"family": family, "shellMode": shell, "view": view},
    }, Path("unused.png"))

entries = [
    entry("right", "phase1b-reflection-shell-ab-pointer", "reflection", [.85, 0]),
    entry("background", "phase1b-reflection-shell-ab", "beauty", [0, 0], family="reflection-shell-ab-background"),
    entry("center-beauty", "phase1b-reflection-shell-ab-pointer", "beauty", [0, 0]),
    entry("left", "phase1b-reflection-shell-ab-pointer", "reflection", [-.85, 0]),
    entry("center", "phase1b-reflection-shell-ab-pointer", "reflection", [0, 0]),
]
selected = module.select_ab_pointer_entries(entries, "additive")
mismatch = entry("mismatch", "phase1b-reflection-shell-ab-pointer", "reflection", [0, 0])
mismatch.raw["experimentVariant"]["shellMode"] = "energy-controlled"
print(json.dumps({
    "ids": [item.identifier for item in selected],
    "xs": [item.raw["pointer"][0] for item in selected],
    "mismatchVariant": module.variant_name(mismatch.raw),
}))
`);
  assert.deepEqual(value.ids, ["left", "center", "right"]);
  assert.deepEqual(value.xs, [-0.85, 0, 0.85]);
  assert.equal(value.mismatchVariant, null);
});

test("shell composition energy is measured against a matched shell-off beauty baseline", () => {
  const value = runPython(String.raw`
import json, numpy as np, sys
sys.path.insert(0, "scripts/v4")
from lib.roi_metrics import shell_composite_delta_metrics
height, width = 180, 280
silhouette = np.zeros((height, width), dtype=bool)
silhouette[20:160, 30:250] = True
off = np.full((height, width, 3), .25, dtype=np.float32)
additive = off.copy(); controlled = off.copy()
additive[30:48, 50:160] += .24
controlled[30:44, 60:150] += .12
a = shell_composite_delta_metrics(np.clip(additive, 0, 1), off, silhouette)
b = shell_composite_delta_metrics(np.clip(controlled, 0, 1), off, silhouette)
print(json.dumps({"additive": a, "controlled": b}))
`);
  assert.ok(value.additive.reflectionEnergy > value.controlled.reflectionEnergy);
  assert.ok(value.additive.rimMeanLumaDelta > value.controlled.rimMeanLumaDelta);
  assert.match(value.additive.method, /shell-off beauty baseline/);
});

test("runtime identity stays repo-relative and reproduces its source-set hash", () => {
  const value = runPython(String.raw`
import hashlib, importlib.util, json, sys
sys.path.insert(0, "scripts/v4")
spec = importlib.util.spec_from_file_location("phase1b_measure", "scripts/v4/measure-frozen-calibration.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
files = [{"path": "src/a.ts", "sha256": "a" * 64}, {"path": "src/b.ts", "sha256": "b" * 64}]
source_set = hashlib.sha256("\n".join(f"{item['path']}:{item['sha256']}" for item in files).encode()).hexdigest()
clean = module.sanitized_runtime_files({"files": files, "runtimeSourceSetSha256": source_set})
try:
    module.sanitized_runtime_files({"files": [{"path": "/private/a.ts", "sha256": "a" * 64}], "runtimeSourceSetSha256": source_set})
    absolute_blocked = False
except module.MeasurementUnavailable:
    absolute_blocked = True
print(json.dumps({"files": clean, "sourceSet": source_set, "absoluteBlocked": absolute_blocked}))
`);
  assert.equal(value.absoluteBlocked, true);
  assert.match(value.sourceSet, /^[0-9a-f]{64}$/);
  assert.deepEqual(value.files.map((entry) => entry.path), ["src/a.ts", "src/b.ts"]);
});

test("preview and capture-script attestation mismatches fail closed", () => {
  const value = runPython(String.raw`
import copy, importlib.util, json, sys
sys.path.insert(0, "scripts/v4")
spec = importlib.util.spec_from_file_location("phase1b_measure", "scripts/v4/measure-frozen-calibration.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
sha = "a" * 64
identity = {"head": "b" * 40, "runtimeSourceSetSha256": sha}
manifest = {
  "sourceIdentityCheck": {"passed": True},
  "sourceIdentityEnd": {**identity, "dirtyRepository": False, "dirtyWithinRuntimeScope": False},
  "previewIdentity": {"passed": True, "violations": []},
  "distIdentity": {"treeSha256": sha, "fileCount": 1},
  "runtimeContract": {"passed": True},
  "environment": {"graphics": {"webgpuAvailable": True, "softwareRendererDetected": False, "adapter": {"isFallbackAdapter": False}}},
  "pageErrorCount": 0,
  "servedResourceIdentity": {"manifestSha256": sha, "resourceCount": 1, "resources": [{}]},
  "screenshotSetSha256": sha,
  "sessionVideo": {"sha256": sha},
  "captureScript": {
    "path": "scripts/v4/capture-optics-lab.mjs",
    "sha256": module.sha256_file(module.REPO_ROOT / "scripts/v4/capture-optics-lab.mjs"),
    "version": "optics-lab-capture-phase1b-v2",
  },
}
module.verify_capture_attestation(manifest, identity)
def blocked(mutator):
  value = copy.deepcopy(manifest); mutator(value)
  try:
    module.verify_capture_attestation(value, identity); return False
  except module.MeasurementUnavailable: return True
print(json.dumps({
  "previewBlocked": blocked(lambda item: item["previewIdentity"].update(passed=False)),
  "scriptBlocked": blocked(lambda item: item["captureScript"].update(sha256="c" * 64)),
}))
`);
  assert.equal(value.previewBlocked, true);
  assert.equal(value.scriptBlocked, true);
});

test("relative QA scripts parse, CLI fails closed, and public JSON leaks no paths or pixels", async (t) => {
  const compile = spawnSync("python3", [
    "-m", "py_compile",
    "scripts/v4/lib/roi_metrics.py",
    "scripts/v4/measure-frozen-calibration.py",
  ], { cwd: REPO_ROOT, encoding: "utf8" });
  assert.equal(compile.status, 0, compile.stderr);

  const help = spawnSync("python3", ["scripts/v4/measure-frozen-calibration.py", "--help"], {
    cwd: REPO_ROOT,
    encoding: "utf8",
  });
  assert.equal(help.status, 0, help.stderr);

  const temporary = await mkdtemp(path.join(os.tmpdir(), "mirrorweb-phase1b-relative-"));
  t.after(() => rm(temporary, { recursive: true, force: true }));
  const output = path.join(temporary, "blocked.json");
  const blocked = spawnSync("python3", [
    "scripts/v4/measure-frozen-calibration.py",
    "--local-capture", path.join(temporary, "missing.local.json"),
    "--review-dir", path.join(temporary, "private-review"),
    "--output", output,
  ], { cwd: REPO_ROOT, encoding: "utf8" });
  assert.equal(blocked.status, 2, blocked.stderr);
  const publicSource = await readFile(output, "utf8");
  const publicResult = JSON.parse(publicSource);
  const resultSchema = JSON.parse(await source("qa-v4/results/frozen-visual-calibration.schema.json"));
  assert.equal(publicResult.status, "BLOCKED");
  assert.deepEqual(publicResult.sourceIdentity, { status: "UNAVAILABLE", files: [] });
  assert.deepEqual(publicResult.captureAttestation, { status: "BLOCKED" });
  assert.equal(publicResult.finalTargetMatch, "BLOCKED");
  assert.deepEqual(publicResult.privateReviewArtifacts.artifacts, {});
  assert.ok(!publicSource.includes(REPO_ROOT));
  assert.ok(!publicSource.includes(temporary));
  assert.doesNotMatch(publicSource, /data:image|base64|\.png|\.jpe?g/i);
  assert.equal(resultSchema.additionalProperties, false);
  assert.ok(resultSchema.required.includes("sourceIdentity"));
  assert.ok(resultSchema.required.includes("captureAttestation"));
  assert.equal(resultSchema.properties.finalTargetMatch.const, "BLOCKED");
  assert.deepEqual(resultSchema.$defs.metricEvidence.properties.status.enum, ["BLOCKED", "CONDITIONAL", "MEASURED"]);
  assert.match(resultSchema.$defs.sha256.pattern, /64/);

  const [measureSource, metricsSource] = await Promise.all([
    source("scripts/v4/measure-frozen-calibration.py"),
    source("scripts/v4/lib/roi_metrics.py"),
  ]);
  assert.doesNotMatch(`${measureSource}\n${metricsSource}`, /structural_similarity|compare_ssim|skimage\.metrics/i);
  assert.match(measureSource, /phase1b-optical-zones-front/);
  assert.match(measureSource, /phase1b-optical-zones-\{pose\}/);
  assert.match(measureSource, /phase1b-reflection-shell-ab-pointer/);
  assert.match(measureSource, /experimentVariant/);
  assert.match(measureSource, /"files": runtime_files/);

  const priorSource = await source("qa-v4/reference/frozen-visual/calibration-priors.sanitized.json");
  assert.equal(createHash("sha256").update(priorSource).digest("hex").length, 64);
});
