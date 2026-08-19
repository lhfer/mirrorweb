import test from "node:test";
import assert from "node:assert/strict";
import {
  buildReferenceStatus,
  inspectCaptureCellSummary,
  sameStringSet,
} from "../../scripts/v4/lib/reference-status.mjs";
import { runSourceContract } from "../../scripts/v4/lib/source-contract.mjs";

const profile = {
  id: "desktop-1440x900-dpr1",
  width: 1440,
  height: 900,
  browserDpr: 1,
  expectedCanvasDpr: 1,
};
const site = {
  id: "target",
  referenceClass: "controlled-live",
  url: "https://example.invalid/?v=2",
};
const sha = "a".repeat(64);
const validCell = {
  status: "PASS",
  referenceClass: "controlled-live",
  url: site.url,
  profile: { ...profile },
  effectiveInputSha256: sha,
  identity: {
    finalUrl: site.url,
    screenshot: { sha256: sha },
    domSnapshotSha256: sha,
    network: {
      fullNetworkManifestSha256: sha,
      resourceCount: 1,
      validators: { resourceValidatorManifestSha256: sha },
    },
    environment: {
      webgpu: { available: true, isFallbackAdapter: false },
      observedCanvasContextTypes: ["webgpu"],
      viewport: { width: 1440, height: 900, browserDpr: 1 },
      refreshRate: { sampleCount: 119, estimatedHz: 120 },
      canvases: [{ effectiveDpr: { x: 1, y: 1 } }],
    },
  },
  interaction: {
    effectiveInputSha256: sha,
    validation: {
      passed: true,
      minimumObservedTrackedCardCorners: 8,
      landmarkSampleCount: 8,
    },
  },
  performance: {
    gpuExecutionTimeMeasured: false,
    idle: { p50: 8, p95: 9, p99: 10, sampleCount: 120 },
    interaction: { p50: 8, p95: 10, p99: 12, sampleCount: 120 },
  },
};

test("reference status is fail-closed when the private Frozen Golden is unavailable", async () => {
  const source = await runSourceContract();
  assert.equal(source.status, "PASSED");
  const result = await buildReferenceStatus({
    sourceStatus: source.status,
    goldenDirectory: "/definitely/not/a/mirrorweb/golden",
  });
  assert.equal(result.frozenVisualReference.status, "BLOCKED");
  assert.equal(result.phase1Allowed, false);
  assert.equal(result.finalQuantitativeAcceptance.status, "BLOCKED");
});

test("required profile sets reject missing or extra profiles", () => {
  assert.equal(sameStringSet(["a", "b"], ["b", "a"]), true);
  assert.equal(sameStringSet(["a", "b"], ["a"]), false);
  assert.equal(sameStringSet(["a"], ["a", "b"]), false);
});

test("capture cell summary binds URL, class, browser DPR, effective input and evidence coverage", () => {
  assert.equal(inspectCaptureCellSummary(validCell, profile, site, {}).passed, true);
  const wrong = structuredClone(validCell);
  wrong.url = "https://wrong.invalid/";
  wrong.identity.environment.viewport.browserDpr = 2;
  wrong.interaction.effectiveInputSha256 = "b".repeat(64);
  const result = inspectCaptureCellSummary(wrong, profile, site, {});
  assert.equal(result.passed, false);
  assert.ok(result.failures.includes("site-url"));
  assert.ok(result.failures.includes("browser-dpr"));
  assert.ok(result.failures.includes("effective-input-hash"));
});

test("current controlled references authorize optics only when private evidence is explicitly available", {
  skip: !process.env.ILG_GOLDEN_DIR,
}, async () => {
  const source = await runSourceContract();
  const result = await buildReferenceStatus({ sourceStatus: source.status });
  assert.equal(result.controlledLocalBaseline.status, "PASS");
  assert.equal(result.controlledLiveReference.status, "PASS");
  assert.equal(result.phase1Allowed, true);
  assert.equal(result.finalQuantitativeAcceptance.status, "BLOCKED");
});
