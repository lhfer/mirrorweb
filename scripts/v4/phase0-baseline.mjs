#!/usr/bin/env node
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { REPO_ROOT, writeJson } from "./lib/common.mjs";
import { verifyGolden, writeGoldenResult } from "./lib/golden.mjs";
import { runSourceContract } from "./lib/source-contract.mjs";

const knownFailures = [
  {
    id: "V4-GAP-OPTICS-01",
    severity: "P1",
    evidence: "src/materials/LiquidGlassMaterial.ts",
    finding: "Normal path mixes direct mediaMap with the scene target",
  },
  {
    id: "V4-GAP-OPTICS-02",
    severity: "P1",
    evidence: "src/materials/LiquidGlassMaterial.ts",
    finding: "Fixed dark body tint and fixed normal.y highlight remain",
  },
  {
    id: "V4-GAP-OPTICS-03",
    severity: "P1",
    evidence: "src/rendering/RenderPipeline.ts",
    finding: "Scene target is display-encoded/default type rather than linear half-float HDR",
  },
  {
    id: "V4-GAP-MOTION-01",
    severity: "P1",
    evidence: "src/interaction/MotionController.ts",
    finding: "Release velocity is not a weighted 80-120 ms regression and hard-stops below 70 px/s",
  },
  {
    id: "V4-GAP-GRID-01",
    severity: "P2",
    evidence: "src/scene/InfiniteGlassGrid.ts",
    finding: "Wrap can remap the full 9x9 pool instead of one entering row or column",
  },
  {
    id: "V4-GAP-DOM-01",
    severity: "P2",
    evidence: "src/ui/TileLabelLayer.ts",
    finding: "Rebinding rebuilds CSS3D card innerHTML",
  },
  {
    id: "V4-GAP-VIDEO-01",
    severity: "P2",
    evidence: "src/content/VideoClips.ts",
    finding: "VideoTexture update is called unconditionally from RAF",
  },
];

try {
  const source = await runSourceContract();
  const golden = await verifyGolden();
  const resultsDir = resolve(REPO_ROOT, "qa-v4/results");
  await mkdir(resultsDir, { recursive: true });
  await writeGoldenResult(resolve(resultsDir, "golden-manifest.local.json"), golden);

  const status = source.status !== "PASSED" ? "ERROR" : golden.status === "BLOCKED" ? "BLOCKED" : "FAILED";
  const result = {
    schemaVersion: 1,
    phase: 0,
    status,
    generatedAt: new Date().toISOString(),
    sourceContract: {
      status: source.status,
      failed: source.failed,
    },
    goldenPreflight: {
      status: golden.status,
      blockers: golden.blockers,
      comparisonRan: golden.comparisonRan,
    },
    frozenMedia: {
      targetVideo: golden.observed?.targetVideo?.video ?? null,
      currentVideo: golden.observed?.currentVideo?.video ?? null,
      comparison: {
        status: "NOT_RUN",
        reason: golden.status === "BLOCKED"
          ? "Golden provenance is incomplete; uncontrolled recordings must not be frame-aligned"
          : "Phase 0 records the failing V3 architecture and does not implement the Phase 1 comparator",
      },
    },
    frameTimeMs: {
      p50: null,
      p95: null,
      p99: null,
      status: "NOT_MEASURED",
      reason: "A 30 fps screen recording does not contain page render frame timing",
    },
    visualChange: {
      expected: false,
      beforeVideoRole: "frozen-current-baseline",
      afterVideo: null,
      status: "NOT_APPLICABLE_NO_VISUAL_CODE_CHANGED",
    },
    expectedV3Failures: knownFailures,
    nextPhaseAllowed: false,
    finalResult: status === "BLOCKED" ? "blocked" : "failed",
  };
  await writeJson(resolve(resultsDir, "phase-0-baseline.local.json"), result);
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = status === "BLOCKED" ? 2 : status === "ERROR" ? 1 : 1;
} catch (error) {
  console.error(JSON.stringify({
    schemaVersion: 1,
    phase: 0,
    status: "ERROR",
    error: error instanceof Error ? error.message : String(error),
  }, null, 2));
  process.exitCode = 1;
}
