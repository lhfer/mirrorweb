import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  ASSET_KINDS,
  CATEGORY_IDS,
  FEATURE_IDS,
  ROLE_IDS,
  ROLE_SPECS,
  PrivateReviewError,
  validateAndRebindAnnotation,
} from "../../scripts/v4/lib/private-review-server.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const EXAMPLE_PATH = path.join(ROOT, "qa-v4/reference/frozen-visual/annotations.example.json");

async function source(relativePath) {
  return readFile(path.join(ROOT, relativePath), "utf8");
}

async function example() {
  return JSON.parse(await readFile(EXAMPLE_PATH, "utf8"));
}

function clone(value) {
  return structuredClone(value);
}

function approveRoleDraft(annotation, roleId, quad) {
  const spec = ROLE_SPECS.find((entry) => entry.id === roleId);
  const category = annotation.categories[spec.targetCategory];
  category.quadNormalized = quad;
  category.quadReviewStatus = "APPROVED";
  category.zoneBoundaries = {
    coordinateSpace: "inward-ratio-of-card-minor-axis",
    sidewallOuter: 0,
    sidewallToStrongLensRim: 0.012,
    strongLensRimToOpticalShoulder: 0.065,
    opticalShoulderToCenterFace: 0.145,
  };
  category.zoneReviewStatus = "APPROVED";
  annotation.roles[roleId].reviewStatus = "APPROVED";
  for (const feature of FEATURE_IDS) annotation.roles[roleId].featureDecisions[feature] = "APPROVED";
}

test("private annotation v2 starts fully pending and keeps seven roles separate from eight categories", async () => {
  const value = await example();
  assert.equal(value.schemaVersion, 2);
  assert.equal(value.private, true);
  assert.equal(value.reviewStatus, "PENDING");
  assert.deepEqual(Object.keys(value.roles), ROLE_IDS);
  assert.deepEqual(Object.keys(value.categories), CATEGORY_IDS);
  assert.ok(Object.values(value.roles).every((role) => role.reviewStatus === "PENDING"));
  assert.ok(Object.values(value.roles).every((role) => FEATURE_IDS.every(
    (feature) => role.featureDecisions[feature] === "PENDING",
  )));
  assert.ok(Object.values(value.categories).every((category) =>
    category.quadNormalized === null
      && category.quadReviewStatus === "PENDING"
      && category.zoneReviewStatus === "PENDING"
      && category.approvals.existingHighlightMask === false
      && category.approvals.naturalFeatureSignature === false
      && Object.values(category.metrics).every((metric) => metric === null),
  ));
  assert.equal(value.roles.highTexture.targetCategory, "high-texture");
  assert.equal(value.roles.front.targetCategory, "high-texture");
  assert.notEqual(value.roles.highTexture.localCaptureId, value.roles.front.localCaptureId);
});

test("server derives a conditional category approval and never promotes provisional or client metrics", async () => {
  const seed = await example();
  const frozen = JSON.parse(await source("qa-v4/reference/frozen-visual/frozen-visual.sanitized.json"));
  const quad = frozen.categories.find((entry) => entry.id === "bright-front").geometry.quadNormalized;
  approveRoleDraft(seed, "bright", quad);
  seed.roles.bright.localCaptureId = "tampered-client-id";
  seed.categories["bright-front"].metrics.strongLensRimWidthRatio = 0.49;
  const result = validateAndRebindAnnotation(seed);
  assert.equal(result.roles.bright.localCaptureId, "v4-white", "immutable capture binding was not restored");
  assert.equal(result.roles.bright.reviewStatus, "APPROVED");
  assert.equal(result.categories["bright-front"].reviewStatus, "APPROVED");
  assert.equal(result.reviewStatus, "PARTIAL");
  assert.equal(result.categories["bright-front"].metrics.strongLensRimWidthRatio, null);
  assert.equal(result.roles.front.reviewStatus, "PENDING");
  assert.equal(result.categories["pointer-before"].reviewStatus, "PENDING");
});

test("server fails closed on unreviewed geometry, malformed zones, and unexplained rejection", async () => {
  const seed = await example();
  seed.roles.bright.reviewStatus = "APPROVED";
  for (const feature of FEATURE_IDS) seed.roles.bright.featureDecisions[feature] = "APPROVED";
  assert.throws(() => validateAndRebindAnnotation(seed), PrivateReviewError);

  const malformed = await example();
  malformed.categories["bright-front"].zoneBoundaries = {
    coordinateSpace: "inward-ratio-of-card-minor-axis",
    sidewallOuter: 0,
    sidewallToStrongLensRim: 0.12,
    strongLensRimToOpticalShoulder: 0.08,
    opticalShoulderToCenterFace: 0.14,
  };
  assert.throws(() => validateAndRebindAnnotation(malformed), /strictly increasing/);

  const rejected = await example();
  rejected.roles.dark.reviewStatus = "REJECTED";
  rejected.roles.dark.featureDecisions.edge = "REJECTED";
  assert.throws(() => validateAndRebindAnnotation(rejected), /concrete note/);
});

test("changing the bound review asset set invalidates prior human approvals", async () => {
  const seed = await example();
  const frozen = JSON.parse(await source("qa-v4/reference/frozen-visual/frozen-visual.sanitized.json"));
  approveRoleDraft(
    seed,
    "bright",
    frozen.categories.find((entry) => entry.id === "bright-front").geometry.quadNormalized,
  );
  const firstBinding = {
    frozenManifestSha256: "1".repeat(64),
    reviewBundleSha256: "2".repeat(64),
    reviewAssetSetSha256: "3".repeat(64),
    localRuntimeSourceSetSha256: "4".repeat(64),
  };
  const approved = validateAndRebindAnnotation(seed, { evidenceBinding: firstBinding });
  assert.equal(approved.roles.bright.reviewStatus, "APPROVED");
  const drifted = validateAndRebindAnnotation(approved, {
    evidenceBinding: { ...firstBinding, reviewAssetSetSha256: "5".repeat(64) },
  });
  assert.equal(drifted.roles.bright.reviewStatus, "PENDING");
  assert.equal(drifted.categories["bright-front"].quadReviewStatus, "PENDING");
  assert.equal(drifted.categories["bright-front"].zoneReviewStatus, "PENDING");
  assert.equal(drifted.reviewStatus, "PENDING");
});

test("review route is isolated, private assets are deny-listed, and the local server is narrow", async () => {
  const [vite, html, main, server, entry, packageSource] = await Promise.all([
    source("vite.config.ts"),
    source("phase-1b-review.html"),
    source("src/review-phase1b/main.ts"),
    source("scripts/v4/lib/private-review-server.mjs"),
    source("scripts/v4/serve-phase1b-review.mjs"),
    source("package.json"),
  ]);
  assert.match(vite, /phase-1b-review\.html/);
  assert.match(vite, /privateReferencePath/);
  for (const privatePath of [".private", "qa-v4/review", "frames", "masks"]) {
    assert.ok(vite.includes(privatePath), `Vite private deny-list is missing ${privatePath}`);
  }
  assert.match(vite, /annotations\\\.private\\\.json|\*\*\/\*\*\/.+private\.json/);
  for (const label of ["Frozen target", "Local candidate", "Card plane", "Edge", "Highlight", "Dispersion", "Sharpness", "Approve role", "Reject role"]) {
    assert.ok(html.includes(label), `review UI is missing ${label}`);
  }
  assert.match(main, /X-Phase1B-CSRF/);
  assert.match(main, /If-Match/);
  assert.match(main, /validateQuad/);
  assert.match(main, /validateZoneDraft/);
  for (const contract of ["LOOPBACK_REQUIRED", "HOST_REJECTED", "ORIGIN_REJECTED", "CSRF_REJECTED", "ETAG_MISMATCH", "atomicWrite"]) {
    assert.ok(server.includes(contract), `private server is missing ${contract}`);
  }
  assert.match(server, /REVIEW_HOST\s*=\s*"127\.0\.0\.1"/);
  assert.match(entry, /REVIEW_HOST/);
  const packageJson = JSON.parse(packageSource);
  assert.equal(packageJson.scripts["v4:review:serve"], "node scripts/v4/serve-phase1b-review.mjs");
  assert.equal(ROLE_SPECS.length, 7);
  assert.equal(ASSET_KINDS.length, 10);
});
