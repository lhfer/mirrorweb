import { access } from "node:fs/promises";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { REPO_ROOT, readJson, sha256File, sha256Value } from "./common.mjs";

const SHA256 = /^[a-f0-9]{64}$/;
const MEDIA_URL_PATTERN = /(?:stream\.mux|fastly\.mux|cfcdn\.mux|\.(?:m3u8|mp4|m4s|ts|webm)(?:[?#]|$))/i;

async function exists(path) {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function pass(status, details = {}) {
  return { status, ...details };
}

function finiteQuantiles(summary) {
  return [summary?.p50, summary?.p95, summary?.p99].every(Number.isFinite);
}

export function sameStringSet(left, right) {
  return left.length === right.length && [...left].sort().every((value, index) => value === [...right].sort()[index]);
}

async function fileHashMatches(file, expected) {
  return SHA256.test(expected || "") && await exists(file) && await sha256File(file) === expected;
}

function isMediaResource(record) {
  return record.resourceType === "Media"
    || /^(?:video|audio)\//i.test(record.mimeType || "")
    || MEDIA_URL_PATTERN.test(record.url || "");
}

function canonicalNetwork(raw) {
  return raw.map((record) => ({
    url: record.url || null,
    method: record.method || null,
    resourceType: record.resourceType || null,
    status: record.status ?? record.statusCodeFromExtraInfo ?? null,
    mimeType: record.mimeType || null,
    protocol: record.protocol || null,
    encodedDataLength: Number(record.encodedDataLength || 0),
    contentLength: Number(record.contentLength || 0),
    etag: record.etag || null,
    lastModified: record.lastModified || null,
    fromDiskCache: Boolean(record.fromDiskCache),
    fromServiceWorker: Boolean(record.fromServiceWorker),
    failed: Boolean(record.failed),
  })).sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)));
}

async function verifyNetworkRaw(file, expected) {
  if (!(await exists(file))) return false;
  const canonical = canonicalNetwork(await readJson(file));
  const core = canonical.filter((record) => !isMediaResource(record));
  return canonical.length === expected?.resourceCount
    && core.length === expected?.coreResourceCount
    && sha256Value(canonical) === expected?.fullNetworkManifestSha256
    && sha256Value(core) === expected?.coreResourceManifestSha256;
}

function collectScreenshotRefs(value, output = []) {
  if (Array.isArray(value)) {
    for (const item of value) collectScreenshotRefs(item, output);
  } else if (value && typeof value === "object") {
    if (value.path && value.sha256 && String(value.path).endsWith(".png")) {
      output.push({ id: value.id || null, path: value.path, sha256: value.sha256 });
    }
    for (const child of Object.values(value)) collectScreenshotRefs(child, output);
  }
  return output;
}

async function inspectFrozenReference(calibration, frozenPath, goldenDirectory) {
  if (!(await exists(frozenPath))) {
    return pass("BLOCKED", { reasons: ["sanitized-frozen-visual-manifest-missing"] });
  }
  const frozen = await readJson(frozenPath);
  const reasons = [];
  const expectedCategories = [
    "bright-front", "dark-front", "high-texture", "low-texture",
    "left-tilt", "right-tilt", "pointer-before", "pointer-after",
  ];
  if (frozen.$schema !== "../roi-mask.schema.json") reasons.push("frozen-schema-reference");
  if (!["PASS", "CONDITIONAL"].includes(frozen.summary?.status)) reasons.push("frozen-summary-status");
  if (frozen.source?.videoSha256 !== calibration.referenceClasses.frozenVisual.videoSha256) {
    reasons.push("frozen-source-hash-lock");
  }
  const categoryIds = (frozen.categories || []).map((category) => category.id);
  if (!sameStringSet(categoryIds, expectedCategories)) reasons.push("frozen-category-set");

  const artifactRoot = dirname(frozenPath);
  let validArtifactCount = 0;
  let recomputedCleanCount = 0;
  for (const category of frozen.categories || []) {
    const checks = [
      [resolve(artifactRoot, "frames", `${category.id}.png`), category.frameSha256],
      [resolve(artifactRoot, "crops", `${category.id}.png`), category.cropSha256],
      [resolve(artifactRoot, "overlays", `${category.id}.png`), category.overlaySha256],
      ...Object.entries(category.masks || {}).map(([name, value]) => [
        resolve(artifactRoot, "masks", category.id, `${name}.png`),
        value.sha256,
      ]),
    ];
    const valid = (await Promise.all(checks.map(([file, hash]) => fileHashMatches(file, hash)))).every(Boolean);
    if (valid) validArtifactCount += 1;
    if (valid && category.needsHumanReview === false && category.geometry?.clipped === false
      && category.masks?.["card-silhouette"]?.confidence >= 0.65) {
      recomputedCleanCount += 1;
    }
  }
  if (validArtifactCount !== expectedCategories.length) reasons.push("frozen-private-roi-artifacts-missing-or-mismatched");
  if (recomputedCleanCount < 1
    || frozen.summary?.validCleanOpticalRoiCount !== recomputedCleanCount) {
    reasons.push("frozen-clean-roi-recomputation");
  }

  let privateVideoVerified = false;
  if (!goldenDirectory) {
    reasons.push("ilg-golden-dir-not-set");
  } else {
    const root = resolve(REPO_ROOT, goldenDirectory);
    const lockPath = resolve(root, calibration.golden.lockFilename);
    if (!(await exists(lockPath))) {
      reasons.push("private-golden-lock-missing");
    } else {
      const lock = await readJson(lockPath);
      const asset = lock.assets?.targetVideo;
      const relativePath = asset?.path;
      const resolvedAsset = typeof relativePath === "string" ? resolve(root, relativePath) : null;
      const escape = !resolvedAsset || isAbsolute(relativePath)
        || relative(root, resolvedAsset).startsWith("..");
      if (escape
        || asset?.sha256 !== frozen.source.videoSha256
        || !(await fileHashMatches(resolvedAsset, frozen.source.videoSha256))) {
        reasons.push("private-frozen-video-unreadable-or-hash-mismatched");
      } else {
        privateVideoVerified = true;
      }
    }
  }

  const status = reasons.length
    ? "BLOCKED"
    : frozen.summary.status === "PASS" ? "PASS" : "CONDITIONAL";
  return pass(status, {
    sourceVideoSha256: frozen.source?.videoSha256 || null,
    privateVideoVerified,
    artifactSetSha256: frozen.summary?.artifactSetSha256 || null,
    selectedCategoryCount: frozen.summary?.selectedCategoryCount || 0,
    verifiedArtifactCategoryCount: validArtifactCount,
    cleanOpticalRoiCount: recomputedCleanCount,
    opticalZoneWidthsMeasured: frozen.summary?.opticalZoneWidthsMeasured === true,
    needsHumanReviewCount: frozen.summary?.needsHumanReviewCount || 0,
    reasons,
  });
}

export function inspectCaptureCellSummary(cell, profile, site, expectedLocal) {
  const failures = [];
  if (cell?.status !== "PASS") failures.push("cell-status");
  if (cell?.referenceClass !== site.referenceClass) failures.push("reference-class");
  if (cell?.url !== site.url || cell?.identity?.finalUrl !== site.url) failures.push("site-url");
  if (cell?.profile?.width !== profile.width || cell?.profile?.height !== profile.height
    || cell?.profile?.browserDpr !== profile.browserDpr
    || cell?.profile?.expectedCanvasDpr !== profile.expectedCanvasDpr) {
    failures.push("cell-profile-binding");
  }
  if (!SHA256.test(cell?.effectiveInputSha256 || "")
    || cell?.effectiveInputSha256 !== cell?.interaction?.effectiveInputSha256) {
    failures.push("effective-input-hash");
  }
  if (!SHA256.test(cell?.identity?.screenshot?.sha256 || "")) failures.push("screenshot-hash");
  if (!SHA256.test(cell?.identity?.domSnapshotSha256 || "")) failures.push("dom-hash");
  if (!SHA256.test(cell?.identity?.network?.fullNetworkManifestSha256 || "")) failures.push("network-hash");
  if ((cell?.identity?.network?.resourceCount || 0) < 1) failures.push("network-resource-count");
  if (!SHA256.test(cell?.identity?.network?.validators?.resourceValidatorManifestSha256 || "")) {
    failures.push("network-validator-hash");
  }
  const environment = cell?.identity?.environment;
  if (environment?.webgpu?.available !== true || environment?.webgpu?.isFallbackAdapter === true) {
    failures.push("real-webgpu");
  }
  if (!environment?.observedCanvasContextTypes?.includes("webgpu")) failures.push("webgpu-context");
  if (environment?.viewport?.width !== profile.width || environment?.viewport?.height !== profile.height) {
    failures.push("viewport");
  }
  if (environment?.viewport?.browserDpr !== profile.browserDpr) failures.push("browser-dpr");
  if ((environment?.refreshRate?.sampleCount || 0) < 60
    || !Number.isFinite(environment?.refreshRate?.estimatedHz)) {
    failures.push("refresh-rate-samples");
  }
  const canvas = environment?.canvases?.[0];
  if (!canvas || Math.abs(canvas.effectiveDpr.x - profile.expectedCanvasDpr) > 0.05
    || Math.abs(canvas.effectiveDpr.y - profile.expectedCanvasDpr) > 0.05) {
    failures.push("canvas-dpr");
  }
  if (cell?.interaction?.validation?.passed !== true) failures.push("interaction-validation");
  if ((cell?.interaction?.validation?.minimumObservedTrackedCardCorners || 0) < 8) {
    failures.push("tracked-card-corners");
  }
  if ((cell?.interaction?.validation?.landmarkSampleCount || 0) < 8) failures.push("landmark-sample-count");
  if (!finiteQuantiles(cell?.performance?.idle) || !finiteQuantiles(cell?.performance?.interaction)) {
    failures.push("raf-quantiles");
  }
  if ((cell?.performance?.idle?.sampleCount || 0) < 120
    || (cell?.performance?.interaction?.sampleCount || 0) < 120) {
    failures.push("raf-sample-count");
  }
  if (cell?.performance?.gpuExecutionTimeMeasured !== false) failures.push("performance-label");
  if (site.id === "local") {
    if (cell?.sourceCommit !== expectedLocal.sourceCommit) failures.push("local-cell-source-commit");
    const identity = cell?.identity?.sourceIdentity;
    if (identity?.sourceCommit !== expectedLocal.sourceCommit
      || identity?.sourceTree !== expectedLocal.sourceTree
      || identity?.trackedTreeClean !== true) {
      failures.push("local-source-identity");
    }
    if (environment?.qaBackend !== "webgpu") failures.push("v3-webgpu-smoke");
  }
  return {
    passed: failures.length === 0,
    failures,
    rafIntervalMs: {
      idle: cell?.performance?.idle || null,
      interaction: cell?.performance?.interaction || null,
      gpuExecutionTimeMeasured: false,
    },
  };
}

async function inspectRawCaptureEvidence(cell, captureId, profile, site) {
  const failures = [];
  const root = resolve(REPO_ROOT, site.outputDirectory, captureId, profile.id);
  const rawManifests = [
    [resolve(root, "identity/identity.raw.json"), cell?.identity?.rawManifestSha256],
    [resolve(root, "interaction/interaction.raw.json"), cell?.interaction?.rawManifestSha256],
    [resolve(root, "performance/performance.raw.json"), cell?.performance?.rawManifestSha256],
  ];
  for (const [file, hash] of rawManifests) {
    if (!(await fileHashMatches(file, hash))) failures.push(`raw-manifest:${relative(root, file)}`);
  }
  const identityRawFile = rawManifests[0][0];
  const interactionRawFile = rawManifests[1][0];
  const identityRaw = await exists(identityRawFile) ? await readJson(identityRawFile) : null;
  const interactionRaw = await exists(interactionRawFile) ? await readJson(interactionRawFile) : null;
  const directFiles = [
    [resolve(root, "identity/screenshots/rest-5s.png"), cell?.identity?.screenshot?.sha256],
    [resolve(root, "interaction/video/interaction.webm"), cell?.interaction?.video?.sha256],
  ];
  for (const [file, hash] of directFiles) {
    if (!(await fileHashMatches(file, hash))) failures.push(`raw-artifact:${relative(root, file)}`);
  }
  if (!(await verifyNetworkRaw(resolve(root, "identity/network.raw.json"), cell?.identity?.network))) {
    failures.push("raw-identity-network");
  }
  if (!(await verifyNetworkRaw(resolve(root, "interaction/network.raw.json"), cell?.interaction?.network))) {
    failures.push("raw-interaction-network");
  }
  const screenshots = collectScreenshotRefs(interactionRaw || {});
  const screenshotSet = screenshots.map(({ id, sha256 }) => ({ id, sha256 }));
  if (screenshots.length !== cell?.interaction?.screenshotCount
    || sha256Value(screenshotSet) !== cell?.interaction?.screenshotSetSha256) {
    failures.push("raw-interaction-screenshot-set");
  }
  for (const screenshot of screenshots) {
    const file = resolve(REPO_ROOT, screenshot.path);
    const escaped = isAbsolute(screenshot.path) || relative(REPO_ROOT, file).startsWith("..");
    if (escaped || !(await fileHashMatches(file, screenshot.sha256))) {
      failures.push("raw-interaction-screenshot-file");
      break;
    }
  }
  const domFile = resolve(root, "identity/dom-snapshot.raw.json");
  if (!(await exists(domFile)) || sha256Value(await readJson(domFile)) !== cell?.identity?.domSnapshotSha256) {
    failures.push("raw-dom-snapshot");
  }
  const telemetryFile = resolve(root, "interaction/telemetry.raw.json");
  if (!(await exists(telemetryFile)) || sha256Value(await readJson(telemetryFile)) !== cell?.interaction?.telemetrySha256) {
    failures.push("raw-telemetry");
  }
  if (identityRaw?.domSnapshot?.sha256 !== cell?.identity?.domSnapshotSha256
    || interactionRaw?.telemetry?.sha256 !== cell?.interaction?.telemetrySha256) {
    failures.push("raw-manifest-cross-link");
  }
  return { passed: failures.length === 0, failures };
}

export async function buildReferenceStatus({ sourceStatus = "BLOCKED", goldenDirectory = process.env.ILG_GOLDEN_DIR } = {}) {
  const calibration = await readJson(resolve(REPO_ROOT, "config/calibration.v4.json"));
  const matrixPath = resolve(REPO_ROOT, "qa-v4/reference/capture-matrix.json");
  const inputPath = resolve(REPO_ROOT, calibration.golden.inputScript);
  const frozenPath = resolve(REPO_ROOT, calibration.referenceClasses.frozenVisual.sanitizedManifest);
  const capturePath = resolve(REPO_ROOT, calibration.referenceClasses.controlledCapture.sanitizedManifest);
  const blockers = [];

  const sourceConsistency = sourceStatus === "PASSED"
    ? pass("PASS")
    : pass("BLOCKED", { reasons: ["source-contract-failed"] });

  const frozenVisualReference = await inspectFrozenReference(calibration, frozenPath, goldenDirectory);

  let controlledLiveReference = pass("BLOCKED", { reasons: ["controlled-capture-missing"] });
  let controlledLocalBaseline = pass("BLOCKED", { reasons: ["controlled-capture-missing"] });
  let capture = null;
  if (await exists(capturePath)) {
    capture = await readJson(capturePath);
    const matrixHashMatches = capture.matrix?.sha256 === await sha256File(matrixPath);
    const inputHashMatches = capture.inputScript?.fileSha256 === await sha256File(inputPath);
    const captureEnvelopeValid = capture.$schema === "qa-v4/reference/controlled-reference.schema.json"
      && capture.status === "PASS"
      && capture.captureId === calibration.referenceClasses.controlledCapture.captureId
      && Array.isArray(capture.errors)
      && capture.errors.length === 0
      && /^Chrome\/\d+\.\d+\.\d+\.\d+$/.test(capture.browser?.product || "")
      && capture.harness?.captureScriptVersion === capture.generator
      && capture.harness?.captureScriptSha256 === await sha256File(fileURLToPath(new URL("../capture-controlled-reference.mjs", import.meta.url)))
      && capture.localSourceIdentity?.sourceCommit === calibration.referenceClasses.controlledLocal.sourceCommit
      && capture.localSourceIdentity?.sourceTree === calibration.referenceClasses.controlledLocal.sourceTree
      && capture.localSourceIdentity?.trackedTreeClean === true;
    const profileIds = calibration.referenceClasses.controlledCapture.requiredProfiles;
    const localExpected = calibration.referenceClasses.controlledLocal;
    const matrix = await readJson(matrixPath);
    const matrixProfileIds = matrix.profiles.map((profile) => profile.id);
    const captureProfileIds = Object.keys(capture.profiles || {});
    const liveFailures = [];
    const localFailures = [];
    const cells = {};
    for (const profile of matrix.profiles.filter((item) => profileIds.includes(item.id))) {
      cells[profile.id] = {};
      for (const site of matrix.sites) {
        const cell = capture.profiles?.[profile.id]?.[site.id];
        const summary = inspectCaptureCellSummary(cell, profile, site, localExpected);
        const raw = await inspectRawCaptureEvidence(cell, capture.captureId, profile, site);
        const inspected = {
          ...summary,
          passed: summary.passed && raw.passed,
          failures: [...summary.failures, ...raw.failures],
          rawEvidenceVerified: raw.passed,
        };
        cells[profile.id][site.id] = inspected;
        if (!inspected.passed) (site.id === "target" ? liveFailures : localFailures)
          .push({ profile: profile.id, failures: inspected.failures });
      }
    }
    if (!sameStringSet(profileIds, matrixProfileIds) || !sameStringSet(profileIds, captureProfileIds)) {
      liveFailures.push({ profile: "all", failures: ["required-profile-set"] });
      localFailures.push({ profile: "all", failures: ["required-profile-set"] });
    }
    if (!matrixHashMatches) {
      liveFailures.push({ profile: "all", failures: ["capture-matrix-hash"] });
      localFailures.push({ profile: "all", failures: ["capture-matrix-hash"] });
    }
    if (!inputHashMatches) {
      liveFailures.push({ profile: "all", failures: ["input-script-hash"] });
      localFailures.push({ profile: "all", failures: ["input-script-hash"] });
    }
    if (!captureEnvelopeValid) {
      liveFailures.push({ profile: "all", failures: ["capture-envelope-status-or-id"] });
      localFailures.push({ profile: "all", failures: ["capture-envelope-status-or-id"] });
    }
    controlledLiveReference = pass(liveFailures.length ? "BLOCKED" : "PASS", {
      captureId: capture.captureId,
      cells: Object.fromEntries(Object.entries(cells).map(([id, value]) => [id, value.target])),
      reasons: liveFailures,
    });
    controlledLocalBaseline = pass(localFailures.length ? "BLOCKED" : "PASS", {
      captureId: capture.captureId,
      sourceCommit: capture.localSourceIdentity?.sourceCommit || null,
      sourceTree: capture.localSourceIdentity?.sourceTree || null,
      cells: Object.fromEntries(Object.entries(cells).map(([id, value]) => [id, value.local])),
      reasons: localFailures,
    });
  }

  const phase1Conditions = {
    sourceContractPassed: sourceConsistency.status === "PASS",
    controlledLocalBaselinePassed: controlledLocalBaseline.status === "PASS",
    frozenVisualReadableAndHashLocked: ["PASS", "CONDITIONAL"].includes(frozenVisualReference.status),
    cleanOpticalRoiPresent: (frozenVisualReference.cleanOpticalRoiCount || 0) >= 1,
    v3RuntimeSmokePassed: controlledLocalBaseline.status === "PASS",
    v4IsolationContractPresent: calibration.routing.v4Lab === "/glass-lab-v4"
      && calibration.routing.default === "v3",
  };
  const phase1Allowed = Object.values(phase1Conditions).every(Boolean);

  blockers.push(
    "strict-motion-fit-not-run",
    "final-optics-quantitative-comparison-not-run",
    "target-highlight-centroid-not-directly-exposed",
    "wheel-line-delta-is-synthetic-and-non-strict",
  );
  if (frozenVisualReference.status === "CONDITIONAL") blockers.push("frozen-roi-set-needs-human-review");
  if (controlledLiveReference.status !== "PASS") blockers.push("controlled-live-reference-incomplete");
  if (controlledLocalBaseline.status !== "PASS") blockers.push("controlled-local-baseline-incomplete");

  return {
    schemaVersion: 1,
    phase: 0,
    generatedAt: new Date().toISOString(),
    sourceConsistency,
    frozenVisualReference,
    controlledLocalBaseline,
    controlledLiveReference,
    frozenVsControlledLive: calibration.referenceClasses.frozenVsControlledLive,
    finalQuantitativeAcceptance: pass("BLOCKED", { blockers }),
    phase1Conditions,
    phase1Allowed,
    overallStatus: phase1Allowed ? "DEVELOPMENT_READY_FINAL_BLOCKED" : "BLOCKED",
  };
}
