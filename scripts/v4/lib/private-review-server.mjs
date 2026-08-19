import { createHash, randomBytes, timingSafeEqual } from "node:crypto";
import {
  DEFAULT_REVIEWER_STATE_PATH,
  MAX_REVIEWER_STATE_BYTES,
  ReviewerStateError,
  emptyReviewerState,
  reviewerStateEtag,
  reviewerStateSummary,
  serializeReviewerState,
  validateReviewerState,
} from "./reviewer-state.mjs";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { access, lstat, mkdir, open, readFile, rename, stat, unlink } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const MODULE_DIR = path.dirname(fileURLToPath(import.meta.url));
export const DEFAULT_REPO_ROOT = path.resolve(MODULE_DIR, "../../..");
export const REVIEW_HOST = "127.0.0.1";
export const REVIEW_PORT = 5282;
export const MAX_ANNOTATION_BYTES = 256 * 1024;

export const ROLE_IDS = Object.freeze([
  "bright", "dark", "highTexture", "lowTexture", "front", "leftTilt", "rightTilt",
]);
export const CATEGORY_IDS = Object.freeze([
  "bright-front", "dark-front", "high-texture", "low-texture", "left-tilt", "right-tilt",
  "pointer-before", "pointer-after",
]);
export const FEATURE_IDS = Object.freeze(["edge", "highlight", "dispersion", "sharpness"]);
export const ASSET_KINDS = Object.freeze([
  "target-source", "target-plane", "target-edge", "target-highlight",
  "local-source", "local-plane", "local-edge", "local-highlight", "local-dispersion", "local-zones",
]);

const CATEGORY_HASHES = Object.freeze({
  "bright-front": "11bc11bc659ed827ec2569210425b0c67dc7751ba1674779a79178ad25b8a897",
  "dark-front": "e3abcfafcced25e69a3ad587fc6c48bb15da9a45bcef7fe00615145a4d2acebe",
  "high-texture": "436e8fc42525f9e2f9baf3e8bf934861f0a1438e7c3d7dc9bbe62a3e7f10c202",
  "low-texture": "25341575958cb6ac190b1da5522dfbb6947b31b8b9ddd87ee820d217a2fb1ce9",
  "left-tilt": "dd187a9b38a0962209ab786dd068a900cb77888e25b346b88cef2725250d2822",
  "right-tilt": "bd3f7f87019e231a8d2d565e0bcf6be48c7a23274e2a8690f3bddba5a4120caa",
  "pointer-before": "02e5157c26ad46b9c54f616e3dd26594fa64867b7c31eb643e1ed0e61ad7dab3",
  "pointer-after": "7b8db4d33286a7e3ec387d4e8cded7b83c66a7952e34e1c6e8bf96f46a519d45",
});

const TARGET_ROOT = "qa-v4/reference/frozen-visual";
const CANDIDATE_MANIFEST = "qa-v4/review/phase-1b/candidates/candidates.local.json";
const LOCAL_ROOT = "qa-v4/results/frozen-visual-calibration.private";
const REVIEW_ROOT = "qa-v4/review/phase-1b";

function roleSpec(id, label, targetCategory, localCaptureId, localCaptureSha256, localFile, pose = "front") {
  const highlightFile = pose === "left" ? "phase1b-reflection-left.png"
    : pose === "right" ? "phase1b-reflection-right.png" : "phase1b-reflection-center.png";
  const zonesFile = `phase1b-optical-zones-${pose}.png`;
  return Object.freeze({
    id,
    label,
    targetCategory,
    targetFrameSha256: CATEGORY_HASHES[targetCategory],
    localCaptureId,
    localCaptureSha256,
    frameReused: targetCategory === "high-texture",
    assets: Object.freeze({
      "target-source": `${TARGET_ROOT}/frames/${targetCategory}.png`,
      "target-plane": `${REVIEW_ROOT}/edge-roi-target-${id}.png`,
      "target-edge": `${REVIEW_ROOT}/edge-roi-target-${id}.png`,
      "target-highlight": `${TARGET_ROOT}/masks/${targetCategory}/highlight.png`,
      "local-source": `${LOCAL_ROOT}/${localFile}`,
      "local-plane": `${REVIEW_ROOT}/edge-roi-local-${id}.png`,
      "local-edge": `${REVIEW_ROOT}/edge-roi-local-${id}.png`,
      "local-highlight": `${LOCAL_ROOT}/${highlightFile}`,
      "local-dispersion": `${LOCAL_ROOT}/dispersion-checker.png`,
      "local-zones": `${LOCAL_ROOT}/${zonesFile}`,
    }),
  });
}

export const ROLE_SPECS = Object.freeze([
  roleSpec("bright", "Bright", "bright-front", "v4-white", "849e49ac6fd840bd178bee44d5cc538ba4ed85821be9327142c62fced1706780", "v4-white.png"),
  roleSpec("dark", "Dark", "dark-front", "v4-black", "26b4356433fc1a2906fffce30c5c330d3f95f9f0aca6f87875aa158dbebbae45", "v4-black.png"),
  roleSpec("highTexture", "High Texture", "high-texture", "v4-high-frequency-photo", "31251ccd62d32b3e9e19f61e076da20f1203bf64a144957d017ca2ec00c9c92b", "v4-high-frequency-photo.png"),
  roleSpec("lowTexture", "Low Texture", "low-texture", "v4-low-frequency-flat", "7a02bc4563b438c44e40347582144f663e8329dd79eecf487b5316a3c514e524", "v4-low-frequency-flat.png"),
  roleSpec("front", "Front", "high-texture", "v4-checker", "13a95ddf84ee3ace1c70b1cfa9b33ac36a0d22003b68fe367de3bd29a5d93350", "v4-checker.png"),
  roleSpec("leftTilt", "Left Tilt", "left-tilt", "phase1b-pose-left", "fb74c2c21dc101573d69ff1b519e8f0b7e654dc472594d9fbb9c8c74fca646b4", "phase1b-pose-left.png", "left"),
  roleSpec("rightTilt", "Right Tilt", "right-tilt", "phase1b-pose-right", "22a4f0442f08ca8c11e4778af18b7ea442644244d41953a4bbda879a9af8617d", "phase1b-pose-right.png", "right"),
]);

const ROLE_BY_ID = new Map(ROLE_SPECS.map((spec) => [spec.id, spec]));
const SOURCE_VIDEO_SHA256 = "b6e79250c75e0357e489de87b63ffd4a5097a573eb7baced35e5de8b050c2435";
const DECISIONS = new Set(["PENDING", "APPROVED", "REJECTED"]);
const AGGREGATE_STATUSES = new Set([...DECISIONS, "PARTIAL"]);
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

export class PrivateReviewError extends Error {
  constructor(statusCode, code, message) {
    super(message);
    this.name = "PrivateReviewError";
    this.statusCode = statusCode;
    this.code = code;
  }
}

function fail(pathLabel, message) {
  throw new PrivateReviewError(400, "INVALID_ANNOTATION", `${pathLabel}: ${message}`);
}

function isPlainObject(value) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function exactObject(value, required, optional, pathLabel) {
  if (!isPlainObject(value)) fail(pathLabel, "must be an object");
  const allowed = new Set([...required, ...optional]);
  for (const key of Object.keys(value)) if (!allowed.has(key)) fail(pathLabel, `unexpected property ${key}`);
  for (const key of required) if (!Object.hasOwn(value, key)) fail(pathLabel, `missing property ${key}`);
}

function numberInRange(value, minimum, maximum, pathLabel, nullable = true) {
  if (value === null && nullable) return;
  if (typeof value !== "number" || !Number.isFinite(value) || value < minimum || value > maximum) {
    fail(pathLabel, `must be ${nullable ? "null or " : ""}a finite number in [${minimum}, ${maximum}]`);
  }
}

function decision(value, pathLabel, aggregate = false) {
  if (!(aggregate ? AGGREGATE_STATUSES : DECISIONS).has(value)) fail(pathLabel, "has an invalid decision status");
}

function validatePoint(value, pathLabel) {
  if (!Array.isArray(value) || value.length !== 2) fail(pathLabel, "must be [x, y]");
  numberInRange(value[0], 0, 1, `${pathLabel}[0]`, false);
  numberInRange(value[1], 0, 1, `${pathLabel}[1]`, false);
}

function validateQuad(value, pathLabel) {
  if (value === null) return;
  if (!Array.isArray(value) || value.length !== 4) fail(pathLabel, "must contain TL, TR, BR, BL");
  value.forEach((point, index) => validatePoint(point, `${pathLabel}[${index}]`));
  const crosses = value.map((point, index) => {
    const next = value[(index + 1) % 4];
    const after = value[(index + 2) % 4];
    return (next[0] - point[0]) * (after[1] - next[1]) - (next[1] - point[1]) * (after[0] - next[0]);
  });
  if (crosses.some((cross) => cross <= 0.000001)) fail(pathLabel, "must be a non-self-intersecting clockwise image-space TL/TR/BR/BL quad");
  const topY = (value[0][1] + value[1][1]) / 2;
  const bottomY = (value[2][1] + value[3][1]) / 2;
  const leftX = (value[0][0] + value[3][0]) / 2;
  const rightX = (value[1][0] + value[2][0]) / 2;
  if (!(topY < bottomY && leftX < rightX)) fail(pathLabel, "must retain TL/TR/BR/BL ordering");
}

function validateZones(value, pathLabel) {
  const keys = ["coordinateSpace", "sidewallOuter", "sidewallToStrongLensRim", "strongLensRimToOpticalShoulder", "opticalShoulderToCenterFace"];
  exactObject(value, keys, [], pathLabel);
  if (value.coordinateSpace !== "inward-ratio-of-card-minor-axis" || value.sidewallOuter !== 0) {
    fail(pathLabel, "has an invalid coordinate space or outer boundary");
  }
  const points = keys.slice(2).map((key) => value[key]);
  points.forEach((point, index) => numberInRange(point, 0, 0.5, `${pathLabel}.${keys[index + 2]}`));
  const present = points.filter((point) => point !== null);
  if (present.length !== 0 && present.length !== 3) fail(pathLabel, "must set all three inner boundaries together");
  if (present.length === 3 && !(0 < present[0] && present[0] < present[1] && present[1] < present[2] && present[2] < 0.5)) {
    fail(pathLabel, "inner boundaries must be strictly increasing from the silhouette");
  }
}

function validateMetrics(value, pathLabel) {
  const ratioKeys = ["centerFaceRatio", "opticalShoulderWidthRatio", "strongLensRimWidthRatio", "sidewallScreenWidthRatio", "highlightWidthRatio", "contentBendingWidthRatio", "dispersionWidthRatio"];
  const nonnegativeKeys = ["centerRimSharpnessRatio", "sidewallContentCompression"];
  const keys = [...ratioKeys.slice(0, 5), "highlightCentroidNormalized", ...ratioKeys.slice(5), ...nonnegativeKeys.slice(0, 1), "cornerRefractionSignature", ...nonnegativeKeys.slice(1)];
  exactObject(value, keys, [], pathLabel);
  ratioKeys.forEach((key) => numberInRange(value[key], 0, 1, `${pathLabel}.${key}`));
  nonnegativeKeys.forEach((key) => numberInRange(value[key], 0, Number.MAX_VALUE, `${pathLabel}.${key}`));
  if (value.highlightCentroidNormalized !== null) validatePoint(value.highlightCentroidNormalized, `${pathLabel}.highlightCentroidNormalized`);
  const corners = value.cornerRefractionSignature;
  if (corners !== null) {
    if (!Array.isArray(corners) || corners.length !== 4) fail(`${pathLabel}.cornerRefractionSignature`, "must contain four values");
    corners.forEach((entry, index) => numberInRange(entry, 0, Number.MAX_VALUE, `${pathLabel}.cornerRefractionSignature[${index}]`, false));
  }
}

function validateCategory(value, categoryId) {
  const pathLabel = `categories.${categoryId}`;
  exactObject(value, ["sourceFrameSha256", "reviewStatus", "quadReviewStatus", "zoneReviewStatus", "quadNormalized", "zoneBoundaries", "approvals", "metrics"], [], pathLabel);
  if (value.sourceFrameSha256 !== CATEGORY_HASHES[categoryId]) fail(`${pathLabel}.sourceFrameSha256`, "does not match the frozen frame binding");
  decision(value.reviewStatus, `${pathLabel}.reviewStatus`, true);
  decision(value.quadReviewStatus, `${pathLabel}.quadReviewStatus`);
  decision(value.zoneReviewStatus, `${pathLabel}.zoneReviewStatus`);
  validateQuad(value.quadNormalized, `${pathLabel}.quadNormalized`);
  validateZones(value.zoneBoundaries, `${pathLabel}.zoneBoundaries`);
  exactObject(value.approvals, ["existingHighlightMask", "naturalFeatureSignature"], [], `${pathLabel}.approvals`);
  for (const [key, approval] of Object.entries(value.approvals)) {
    if (typeof approval !== "boolean") fail(`${pathLabel}.approvals.${key}`, "must be boolean");
  }
  validateMetrics(value.metrics, `${pathLabel}.metrics`);
  if (value.quadReviewStatus === "APPROVED" && value.quadNormalized === null) fail(pathLabel, "cannot approve a missing quad");
  if (value.zoneReviewStatus === "APPROVED" && value.zoneBoundaries.sidewallToStrongLensRim === null) fail(pathLabel, "cannot approve missing zone boundaries");
  if (value.reviewStatus === "APPROVED" && (
    value.quadReviewStatus !== "APPROVED"
    || value.zoneReviewStatus !== "APPROVED"
    || value.approvals.naturalFeatureSignature !== true
  )) fail(pathLabel, "approval requires an approved quad, zones, and natural feature signature");
}

function validateRole(value, spec) {
  const pathLabel = `roles.${spec.id}`;
  exactObject(value, ["targetCategory", "targetFrameSha256", "localCaptureId", "localCaptureSha256", "reviewStatus", "featureDecisions", "notes"], [], pathLabel);
  for (const key of ["targetCategory", "targetFrameSha256", "localCaptureId", "localCaptureSha256"]) {
    if (value[key] !== spec[key]) fail(`${pathLabel}.${key}`, "does not match its immutable evidence binding");
  }
  decision(value.reviewStatus, `${pathLabel}.reviewStatus`);
  exactObject(value.featureDecisions, FEATURE_IDS, [], `${pathLabel}.featureDecisions`);
  FEATURE_IDS.forEach((feature) => decision(value.featureDecisions[feature], `${pathLabel}.featureDecisions.${feature}`));
  if (value.notes !== null && (typeof value.notes !== "string" || value.notes.length > 2000)) fail(`${pathLabel}.notes`, "must be null or at most 2000 characters");
  const featureValues = FEATURE_IDS.map((feature) => value.featureDecisions[feature]);
  if (value.reviewStatus === "APPROVED" && featureValues.some((status) => status !== "APPROVED")) {
    fail(pathLabel, "approval requires all four feature decisions to be approved");
  }
  if (value.reviewStatus === "REJECTED" && (typeof value.notes !== "string" || value.notes.trim().length < 8)) {
    fail(pathLabel, "rejection requires a concrete note of at least 8 characters");
  }
}

function resetDerivedMetrics(category) {
  for (const key of [
    "centerFaceRatio", "opticalShoulderWidthRatio", "strongLensRimWidthRatio",
    "sidewallScreenWidthRatio", "highlightWidthRatio", "highlightCentroidNormalized",
    "contentBendingWidthRatio", "centerRimSharpnessRatio", "dispersionWidthRatio",
    "cornerRefractionSignature", "sidewallContentCompression",
  ]) category.metrics[key] = null;
}

function deriveCategoryReviews(annotation) {
  for (const categoryId of CATEGORY_IDS) {
    const category = annotation.categories[categoryId];
    if (!isPlainObject(category)) fail(`categories.${categoryId}`, "must be an object");
    if (!isPlainObject(category.metrics)) fail(`categories.${categoryId}.metrics`, "must be an object");
    if (!isPlainObject(category.approvals)) fail(`categories.${categoryId}.approvals`, "must be an object");
    resetDerivedMetrics(category);
    const linked = ROLE_SPECS.filter((spec) => spec.targetCategory === categoryId)
      .map((spec) => annotation.roles[spec.id]);
    if (!linked.length) continue;
    category.approvals.existingHighlightMask = linked.every(
      (role) => role.featureDecisions.highlight === "APPROVED",
    );
    category.approvals.naturalFeatureSignature = linked.every((role) =>
      FEATURE_IDS.every((feature) => role.featureDecisions[feature] === "APPROVED"),
    );
    if (category.quadReviewStatus === "REJECTED" || category.zoneReviewStatus === "REJECTED") {
      category.reviewStatus = "REJECTED";
      continue;
    }
    if (
      linked.every((role) => role.reviewStatus === "APPROVED")
      && category.quadReviewStatus === "APPROVED"
      && category.zoneReviewStatus === "APPROVED"
      && category.approvals.naturalFeatureSignature
    ) {
      category.reviewStatus = "APPROVED";
      continue;
    }
    const hasProgress = category.quadReviewStatus !== "PENDING"
      || category.zoneReviewStatus !== "PENDING"
      || linked.some((role) => role.reviewStatus !== "PENDING"
        || FEATURE_IDS.some((feature) => role.featureDecisions[feature] !== "PENDING"));
    category.reviewStatus = hasProgress ? "PARTIAL" : "PENDING";
  }
}

export function deriveReviewStatus(annotation) {
  const categoryValues = CATEGORY_IDS.map((id) => annotation.categories[id]);
  const roleValues = ROLE_IDS.map((id) => annotation.roles[id]);
  if (categoryValues.some((value) => value.reviewStatus === "REJECTED") || roleValues.some((value) => value.reviewStatus === "REJECTED")) return "REJECTED";
  if (categoryValues.every((value) => value.reviewStatus === "APPROVED") && roleValues.every((value) => value.reviewStatus === "APPROVED")) return "APPROVED";
  const hasProgress = categoryValues.some((value) =>
    value.reviewStatus !== "PENDING" || value.quadReviewStatus !== "PENDING" || value.zoneReviewStatus !== "PENDING"
    || value.approvals.existingHighlightMask || value.approvals.naturalFeatureSignature,
  ) || roleValues.some((value) =>
    value.reviewStatus !== "PENDING" || FEATURE_IDS.some((feature) => value.featureDecisions[feature] !== "PENDING"),
  ) || annotation.approvals.brightDarkPairedUse;
  return hasProgress ? "PARTIAL" : "PENDING";
}

function rebindImmutableFields(payload, context) {
  if (!isPlainObject(payload)) fail("<root>", "must be an object");
  const result = JSON.parse(JSON.stringify(payload));
  result.schemaVersion = 2;
  result.referenceClass = "frozen-visual-human-calibration";
  result.private = true;
  result.sourceVideoSha256 = context.sourceVideoSha256 || SOURCE_VIDEO_SHA256;
  const incomingBinding = isPlainObject(result.evidenceBinding) ? result.evidenceBinding : null;
  const nextBinding = context.evidenceBinding || incomingBinding;
  if (!isPlainObject(nextBinding)) fail("evidenceBinding", "is missing");
  const incomingWasBound = incomingBinding
    && Object.values(incomingBinding).every((value) => typeof value === "string" && SHA256_PATTERN.test(value))
    && Object.values(incomingBinding).some((value) => !/^0{64}$/.test(value));
  const bindingDrifted = incomingWasBound && context.evidenceBinding
    && Object.keys(context.evidenceBinding).some((key) => incomingBinding[key] !== context.evidenceBinding[key]);
  result.evidenceBinding = JSON.parse(JSON.stringify(nextBinding));
  if (isPlainObject(result.categories)) {
    for (const categoryId of CATEGORY_IDS) {
      if (isPlainObject(result.categories[categoryId])) result.categories[categoryId].sourceFrameSha256 = CATEGORY_HASHES[categoryId];
    }
  }
  if (isPlainObject(result.roles)) {
    for (const spec of ROLE_SPECS) {
      if (!isPlainObject(result.roles[spec.id])) continue;
      result.roles[spec.id].targetCategory = spec.targetCategory;
      result.roles[spec.id].targetFrameSha256 = spec.targetFrameSha256;
      result.roles[spec.id].localCaptureId = spec.localCaptureId;
      result.roles[spec.id].localCaptureSha256 = spec.localCaptureSha256;
    }
  }
  if (bindingDrifted && isPlainObject(result.roles) && isPlainObject(result.categories)) {
    for (const role of Object.values(result.roles)) {
      if (!isPlainObject(role) || !isPlainObject(role.featureDecisions)) continue;
      role.reviewStatus = "PENDING";
      for (const feature of FEATURE_IDS) role.featureDecisions[feature] = "PENDING";
    }
    for (const category of Object.values(result.categories)) {
      if (!isPlainObject(category)) continue;
      category.reviewStatus = "PENDING";
      category.quadReviewStatus = "PENDING";
      category.zoneReviewStatus = "PENDING";
      if (isPlainObject(category.approvals)) {
        category.approvals.existingHighlightMask = false;
        category.approvals.naturalFeatureSignature = false;
      }
    }
  }
  return result;
}

export function validateAndRebindAnnotation(payload, context = {}) {
  const value = rebindImmutableFields(payload, context);
  exactObject(value, ["schemaVersion", "referenceClass", "private", "sourceVideoSha256", "evidenceBinding", "reviewStatus", "categories", "roles", "approvals"], ["$schema", "reviewer", "reviewedAt", "crossCategoryMetrics"], "<root>");
  if (value.schemaVersion !== 2 || value.referenceClass !== "frozen-visual-human-calibration" || value.private !== true) fail("<root>", "has invalid schema identity");
  if (value.sourceVideoSha256 !== (context.sourceVideoSha256 || SOURCE_VIDEO_SHA256)) fail("sourceVideoSha256", "does not match the frozen video");
  exactObject(value.evidenceBinding, ["frozenManifestSha256", "reviewBundleSha256", "reviewAssetSetSha256", "localRuntimeSourceSetSha256"], [], "evidenceBinding");
  for (const [key, hash] of Object.entries(value.evidenceBinding)) {
    if (typeof hash !== "string" || !SHA256_PATTERN.test(hash)) fail(`evidenceBinding.${key}`, "must be a SHA-256 hash");
  }
  if (value.$schema !== undefined && typeof value.$schema !== "string") fail("$schema", "must be a string");
  if (value.reviewer !== undefined && value.reviewer !== null && (typeof value.reviewer !== "string" || value.reviewer.length > 200)) fail("reviewer", "must be null or at most 200 characters");
  if (value.reviewedAt !== undefined && value.reviewedAt !== null && (typeof value.reviewedAt !== "string" || !Number.isFinite(Date.parse(value.reviewedAt)))) fail("reviewedAt", "must be null or an ISO date-time string");
  exactObject(value.approvals, ["brightDarkPairedUse"], [], "approvals");
  if (typeof value.approvals.brightDarkPairedUse !== "boolean") fail("approvals.brightDarkPairedUse", "must be boolean");
  // This review surface does not measure cross-category values. Keeping this
  // null prevents a hand-edited client payload from becoming target truth.
  value.approvals.brightDarkPairedUse = false;
  if (value.crossCategoryMetrics !== undefined) {
    exactObject(value.crossCategoryMetrics, [], ["brightDarkBackgroundResponseDifference"], "crossCategoryMetrics");
    if (Object.hasOwn(value.crossCategoryMetrics, "brightDarkBackgroundResponseDifference")) numberInRange(value.crossCategoryMetrics.brightDarkBackgroundResponseDifference, 0, Number.MAX_VALUE, "crossCategoryMetrics.brightDarkBackgroundResponseDifference");
    value.crossCategoryMetrics.brightDarkBackgroundResponseDifference = null;
  }
  exactObject(value.roles, ROLE_IDS, [], "roles");
  ROLE_SPECS.forEach((spec) => validateRole(value.roles[spec.id], spec));
  exactObject(value.categories, CATEGORY_IDS, [], "categories");
  deriveCategoryReviews(value);
  CATEGORY_IDS.forEach((categoryId) => validateCategory(value.categories[categoryId], categoryId));
  for (const spec of ROLE_SPECS) {
    const role = value.roles[spec.id];
    const category = value.categories[spec.targetCategory];
    if (role.reviewStatus === "APPROVED" && (
      category.quadReviewStatus !== "APPROVED" || category.zoneReviewStatus !== "APPROVED"
    )) fail(`roles.${spec.id}`, "approval requires the shared target quad and optical zones to be approved");
  }
  value.reviewStatus = deriveReviewStatus(value);
  if (value.reviewStatus === "PENDING") value.reviewedAt = null;
  else if (value.reviewedAt == null && context.now) value.reviewedAt = context.now;
  return value;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function serializedAnnotation(annotation) {
  return `${JSON.stringify(annotation, null, 2)}\n`;
}

export function annotationEtag(annotation) {
  return `"${sha256(serializedAnnotation(annotation))}"`;
}

function safeJoin(root, relativePath) {
  if (typeof relativePath !== "string" || path.isAbsolute(relativePath)) throw new Error("Expected a repository-relative path");
  const result = path.resolve(root, relativePath);
  const relative = path.relative(root, result);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("Path escapes its root");
  return result;
}

async function sha256File(file) {
  return sha256(await readFile(file));
}

async function assertRegularFile(file, label) {
  const info = await lstat(file);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error(`${label} is missing or unsafe`);
}

function git(repoRoot, args) {
  return execFileSync("git", args, { cwd: repoRoot, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

function assertPrivateOutput(repoRoot, outputPath) {
  const relative = path.relative(repoRoot, outputPath).split(path.sep).join("/");
  if (relative !== "qa-v4/reference/frozen-visual/annotations.private.json") throw new Error("Private annotations must use the exact approved output path");
  if (git(repoRoot, ["ls-files", "--", relative])) throw new Error("Private annotation output is tracked by Git");
  execFileSync("git", ["check-ignore", "-q", "--no-index", "--", relative], { cwd: repoRoot, stdio: "ignore" });
  return relative;
}

/**
 * Reviewer Mode drafts are a separate private artefact. They must stay inside
 * the ignored review bundle and can never be pointed at the annotation
 * contract, which this service still treats as the only approved output path.
 */
function assertReviewerStatePath(repoRoot, statePath) {
  const relative = path.relative(repoRoot, statePath).split(path.sep).join("/");
  if (!relative.startsWith("qa-v4/review/") || !relative.endsWith(".private.json")) {
    throw new Error("Reviewer state must be a private JSON file inside qa-v4/review/");
  }
  if (relative.includes("..")) throw new Error("Reviewer state path escapes the review bundle");
  if (git(repoRoot, ["ls-files", "--", relative])) throw new Error("Reviewer state file is tracked by Git");
  execFileSync("git", ["check-ignore", "-q", "--no-index", "--", relative], { cwd: repoRoot, stdio: "ignore" });
  return relative;
}

async function atomicWrite(file, contents) {
  await mkdir(path.dirname(file), { recursive: true });
  try {
    const existing = await lstat(file);
    if (existing.isSymbolicLink() || !existing.isFile()) throw new Error("Private write target is not a regular file");
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  const temporary = path.join(path.dirname(file), `.${path.basename(file)}-${process.pid}-${randomBytes(8).toString("hex")}.tmp`);
  let handle;
  try {
    handle = await open(temporary, "wx", 0o600);
    await handle.writeFile(contents, "utf8");
    await handle.sync();
    await handle.close();
    handle = null;
    await rename(temporary, file);
    const directory = await open(path.dirname(file), "r");
    try { await directory.sync(); } finally { await directory.close(); }
  } finally {
    if (handle) await handle.close().catch(() => {});
    await unlink(temporary).catch((error) => { if (error?.code !== "ENOENT") throw error; });
  }
}

async function readJson(file, label) {
  try {
    return JSON.parse(await readFile(file, "utf8"));
  } catch (error) {
    throw new Error(`${label} could not be read: ${error.message}`);
  }
}

async function loadAnnotation(outputPath, examplePath, context) {
  let source = examplePath;
  try {
    const info = await lstat(outputPath);
    if (!info.isFile() || info.isSymbolicLink()) throw new Error("Private annotation path is unsafe");
    if (info.size > MAX_ANNOTATION_BYTES) throw new Error("Private annotation exceeds 256 KiB");
    source = outputPath;
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  const annotation = await readJson(source, "Private annotation state");
  return validateAndRebindAnnotation(annotation, context);
}

function contentType(file) {
  const extension = path.extname(file).toLowerCase();
  return ({
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".woff2": "font/woff2",
  })[extension] || "application/octet-stream";
}

function baseHeaders(privateContent = false) {
  return {
    "Cache-Control": privateContent ? "no-store, max-age=0" : "no-cache, max-age=0",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
  };
}

function sendJson(response, statusCode, value, extraHeaders = {}) {
  const body = `${JSON.stringify(value)}\n`;
  response.writeHead(statusCode, {
    ...baseHeaders(true),
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    ...extraHeaders,
  });
  response.end(body);
}

function sendError(response, error) {
  const typed = Number.isInteger(error?.statusCode) && error.statusCode >= 400 && error.statusCode < 600;
  const statusCode = typed ? error.statusCode : 500;
  const code = typed && typeof error.code === "string" ? error.code : "INTERNAL_ERROR";
  sendJson(response, statusCode, { error: code, message: statusCode === 500 ? "Private review service failed closed" : error.message });
  if (statusCode === 500) console.error(error);
}

function isLoopbackAddress(address) {
  return address === "127.0.0.1" || address === "::ffff:127.0.0.1";
}

function assertLocalRequest(request, expectedHost, expectedOrigin, { requireOrigin = false } = {}) {
  if (!isLoopbackAddress(request.socket.remoteAddress)) throw new PrivateReviewError(403, "LOOPBACK_REQUIRED", "Only loopback clients may use this service");
  if (request.headers.host !== expectedHost) throw new PrivateReviewError(403, "HOST_REJECTED", "Host header does not match the private review origin");
  const origin = request.headers.origin;
  if ((requireOrigin || origin !== undefined) && origin !== expectedOrigin) throw new PrivateReviewError(403, "ORIGIN_REJECTED", "Origin does not match the private review origin");
  if (requireOrigin && request.headers["sec-fetch-site"] && request.headers["sec-fetch-site"] !== "same-origin") {
    throw new PrivateReviewError(403, "CROSS_SITE_REJECTED", "Cross-site writes are forbidden");
  }
}

function safeTokenEquals(received, expected) {
  if (typeof received !== "string") return false;
  const left = Buffer.from(received);
  const right = Buffer.from(expected);
  return left.length === right.length && timingSafeEqual(left, right);
}

async function readLimitedBody(request, limit = MAX_ANNOTATION_BYTES) {
  const length = Number(request.headers["content-length"] || 0);
  if (Number.isFinite(length) && length > limit) throw new PrivateReviewError(413, "BODY_TOO_LARGE", `Payload exceeds ${limit} bytes`);
  const chunks = [];
  let total = 0;
  for await (const chunk of request) {
    total += chunk.byteLength;
    if (total > limit) throw new PrivateReviewError(413, "BODY_TOO_LARGE", `Payload exceeds ${limit} bytes`);
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}

async function buildRuntime(options) {
  const repoRoot = path.resolve(options.repoRoot || DEFAULT_REPO_ROOT);
  const distRoot = path.resolve(options.distRoot || path.join(repoRoot, "dist"));
  const outputPath = path.resolve(options.outputPath || path.join(repoRoot, "qa-v4/reference/frozen-visual/annotations.private.json"));
  const host = options.host || REVIEW_HOST;
  const port = options.port ?? REVIEW_PORT;
  if (host !== REVIEW_HOST) throw new Error("Private review service must bind 127.0.0.1");
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error("Invalid private review port");
  const privateOutput = assertPrivateOutput(repoRoot, outputPath);
  const reviewerStatePath = path.resolve(
    options.reviewerStatePath || path.join(repoRoot, DEFAULT_REVIEWER_STATE_PATH),
  );
  const reviewerStateRelative = assertReviewerStatePath(repoRoot, reviewerStatePath);
  const htmlPath = safeJoin(distRoot, "phase-1b-review.html");
  await assertRegularFile(htmlPath, "Built review page");

  const frozenPath = safeJoin(repoRoot, `${TARGET_ROOT}/frozen-visual.sanitized.json`);
  const calibrationPath = safeJoin(repoRoot, "qa-v4/results/frozen-visual-calibration.json");
  const reviewManifestPath = safeJoin(repoRoot, `${REVIEW_ROOT}/review-manifest.local.json`);
  const examplePath = safeJoin(repoRoot, `${TARGET_ROOT}/annotations.example.json`);
  const [frozen, calibration] = await Promise.all([
    readJson(frozenPath, "Frozen visual manifest"), readJson(calibrationPath, "Frozen calibration result"),
  ]);
  if (frozen.source?.videoSha256 !== SOURCE_VIDEO_SHA256) throw new Error("Frozen video identity changed");
  const frozenCategories = new Map((frozen.categories || []).map((category) => [category.id, category]));
  for (const [id, expectedHash] of Object.entries(CATEGORY_HASHES)) {
    if (frozenCategories.get(id)?.frameSha256 !== expectedHash) throw new Error(`Frozen category binding changed for ${id}`);
  }

  const assetRecords = new Map();
  for (const spec of ROLE_SPECS) {
    for (const kind of ASSET_KINDS) {
      const relativePath = spec.assets[kind];
      const file = safeJoin(repoRoot, relativePath);
      await assertRegularFile(file, `${spec.id}/${kind}`);
      const hash = await sha256File(file);
      if (kind === "target-source" && hash !== spec.targetFrameSha256) throw new Error(`Target pixel hash changed for ${spec.id}`);
      if (kind === "local-source" && hash !== spec.localCaptureSha256) throw new Error(`Local pixel hash changed for ${spec.id}`);
      assetRecords.set(`${spec.id}/${kind}`, { file, sha256: hash });
    }
  }

  const candidateRecords = new Map();
  const candidatesByCategory = new Map();
  let candidateManifestSha256 = null;
  try {
    const candidateFile = safeJoin(repoRoot, CANDIDATE_MANIFEST);
    await assertRegularFile(candidateFile, "Reviewer candidate manifest");
    const manifest = await readJson(candidateFile, "Reviewer candidate manifest");
    if (manifest.sourceVideoSha256 !== SOURCE_VIDEO_SHA256) {
      throw new Error("Candidate manifest is bound to a different source video");
    }
    candidateManifestSha256 = await sha256File(candidateFile);
    for (const [categoryId, entries] of Object.entries(manifest.categories || {})) {
      if (!CATEGORY_IDS.includes(categoryId) || !Array.isArray(entries)) continue;
      const list = [];
      for (const entry of entries) {
        if (!/^f\d{1,8}$/.test(String(entry.id))) throw new Error(`Invalid candidate id in ${categoryId}`);
        const frameFile = safeJoin(repoRoot, entry.path);
        const thumbnailFile = safeJoin(repoRoot, entry.thumbnail.path);
        await assertRegularFile(frameFile, `candidate ${categoryId}/${entry.id}`);
        await assertRegularFile(thumbnailFile, `candidate thumbnail ${categoryId}/${entry.id}`);
        const frameSha = await sha256File(frameFile);
        const thumbnailSha = await sha256File(thumbnailFile);
        if (frameSha !== entry.sha256 || thumbnailSha !== entry.thumbnail.sha256) {
          throw new Error(`Candidate pixels changed for ${categoryId}/${entry.id}`);
        }
        if (entry.primary === true && frameSha !== CATEGORY_HASHES[categoryId]) {
          throw new Error(`Primary candidate is not the frozen frame for ${categoryId}`);
        }
        candidateRecords.set(`${categoryId}/${entry.id}`, { file: frameFile, sha256: frameSha });
        candidateRecords.set(`${categoryId}/${entry.id}/thumb`, { file: thumbnailFile, sha256: thumbnailSha });
        list.push({
          id: entry.id,
          frameIndex: entry.frameIndex,
          primary: entry.primary === true,
          offsetFromSelected: entry.offsetFromSelected ?? 0,
          width: entry.width,
          height: entry.height,
          sha256: frameSha,
          thumbnailSha256: thumbnailSha,
          url: `/__phase1b_review__/candidate/${categoryId}/${entry.id}`,
          thumbnailUrl: `/__phase1b_review__/candidate/${categoryId}/${entry.id}/thumb`,
        });
      }
      list.sort((left, right) => left.frameIndex - right.frameIndex);
      candidatesByCategory.set(categoryId, list);
    }
  } catch (error) {
    if (error?.code !== "ENOENT" && !/is missing or unsafe/.test(String(error?.message))) throw error;
    candidateRecords.clear();
    candidatesByCategory.clear();
    candidateManifestSha256 = null;
  }

  const localHead = calibration.sourceIdentity?.localHead || null;
  const localRuntimeSourceSetSha256 = calibration.sourceIdentity?.localRuntimeSourceSetSha256 || null;
  const reviewBundleSha256 = await sha256File(reviewManifestPath);
  const frozenManifestSha256 = await sha256File(frozenPath);
  const reviewAssetSetSha256 = sha256([...assetRecords.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, record]) => `${key}:${record.sha256}`)
    .join("\n"));
  const immutableBindingsSha256 = sha256(JSON.stringify(ROLE_SPECS.map((spec) => ({
    id: spec.id, targetCategory: spec.targetCategory, targetFrameSha256: spec.targetFrameSha256,
    localCaptureId: spec.localCaptureId, localCaptureSha256: spec.localCaptureSha256,
  }))));
  const origin = `http://${host}:${port}`;
  const csrfToken = options.csrfToken || randomBytes(32).toString("hex");
  const evidenceBinding = {
    frozenManifestSha256,
    reviewBundleSha256,
    reviewAssetSetSha256,
    localRuntimeSourceSetSha256,
  };
  if (Object.values(evidenceBinding).some((value) => typeof value !== "string" || !SHA256_PATTERN.test(value))) {
    throw new Error("Review evidence binding is incomplete");
  }
  const annotationContext = { sourceVideoSha256: SOURCE_VIDEO_SHA256, evidenceBinding };
  const categoryCandidates = Object.fromEntries(CATEGORY_IDS.map((id) => [id, {
    quadNormalized: frozenCategories.get(id)?.geometry?.quadNormalized || null,
    evidenceClass: "automatic-candidate-unapproved",
  }]));
  const suggestedZoneBoundaries = Object.freeze({
    coordinateSpace: "inward-ratio-of-card-minor-axis",
    sidewallOuter: 0,
    sidewallToStrongLensRim: 0.012,
    strongLensRimToOpticalShoulder: 0.065,
    opticalShoulderToCenterFace: 0.145,
  });
  const roles = ROLE_SPECS.map((spec) => ({
    id: spec.id,
    label: spec.label,
    targetCategory: spec.targetCategory,
    targetFrameSha256: spec.targetFrameSha256,
    localCaptureId: spec.localCaptureId,
    localCaptureSha256: spec.localCaptureSha256,
    frameReused: spec.frameReused,
    suggestedQuadNormalized: categoryCandidates[spec.targetCategory].quadNormalized,
    suggestedZoneBoundaries,
    suggestionEvidenceClass: "automatic-candidate-unapproved",
    suggestionApproved: false,
    candidates: candidatesByCategory.get(spec.targetCategory) ?? [],
    assets: Object.fromEntries(ASSET_KINDS.map((kind) => {
      const record = assetRecords.get(`${spec.id}/${kind}`);
      return [kind, { url: `/__phase1b_review__/asset/${spec.id}/${kind}`, sha256: record.sha256 }];
    })),
  }));
  const reviewerContext = {
    roleSpecs: ROLE_SPECS,
    roleIds: ROLE_IDS,
    sourceVideoSha256: SOURCE_VIDEO_SHA256,
    evidenceBinding,
    candidateIds: new Map(
      [...candidatesByCategory.entries()].map(([id, list]) => [id, new Set(list.map((entry) => entry.id))]),
    ),
  };
  return {
    repoRoot, distRoot, outputPath, htmlPath, examplePath, host, port, origin, csrfToken,
    assetRecords, roles, annotationContext,
    reviewerStatePath, reviewerStateRelative, reviewerContext, candidateRecords, candidatesByCategory,
    evidence: {
      sourceVideoSha256: SOURCE_VIDEO_SHA256,
      localHead,
      localRuntimeSourceSetSha256,
      reviewBundleSha256,
      reviewAssetSetSha256,
      frozenManifestSha256,
      immutableBindingsSha256,
      privateOutput: "IGNORED",
      privateOutputPath: privateOutput,
      reviewerStatePath: reviewerStateRelative,
      candidateManifestSha256,
      candidateFrameCount: [...candidatesByCategory.values()].reduce((total, list) => total + list.length, 0),
      categoryCandidates,
      provisionalMasksApproved: false,
      provisionalRangesArePixelTruth: false,
      finalTargetMatch: "BLOCKED",
    },
  };
}

async function loadReviewerState(runtime) {
  let payload = null;
  try {
    const info = await lstat(runtime.reviewerStatePath);
    if (!info.isFile() || info.isSymbolicLink()) throw new Error("Reviewer state path is unsafe");
    if (info.size > MAX_REVIEWER_STATE_BYTES) throw new Error("Reviewer state exceeds 512 KiB");
    payload = JSON.parse(await readFile(runtime.reviewerStatePath, "utf8"));
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
  }
  if (!payload) return emptyReviewerState(runtime.reviewerContext);
  return validateReviewerState(payload, runtime.reviewerContext);
}

async function serveFile(response, file, { privateContent = false, head = false } = {}) {
  await assertRegularFile(file, "Requested resource");
  const info = await stat(file);
  response.writeHead(200, {
    ...baseHeaders(privateContent),
    "Content-Type": contentType(file),
    "Content-Length": info.size,
  });
  if (head) return response.end();
  response.end(await readFile(file));
}

function staticAssetPath(runtime, pathname) {
  if (!pathname.startsWith("/assets/")) return null;
  let decoded;
  try { decoded = decodeURIComponent(pathname.slice(1)); } catch { return null; }
  if (!/^assets\/[A-Za-z0-9._/-]+$/.test(decoded) || decoded.includes("..")) return null;
  const file = safeJoin(runtime.distRoot, decoded);
  const relative = path.relative(path.join(runtime.distRoot, "assets"), file);
  if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) return null;
  return file;
}

export async function createPrivateReviewServer(options = {}) {
  const runtime = await buildRuntime(options);
  let writeQueue = Promise.resolve();
  let reviewerQueue = Promise.resolve();

  const handler = async (request, response) => {
    try {
      const expectedHost = `${runtime.host}:${runtime.port}`;
      assertLocalRequest(request, expectedHost, runtime.origin);
      const url = new URL(request.url || "/", runtime.origin);
      const method = request.method || "GET";

      if (url.pathname === "/__phase1b_review__/state") {
        if (method !== "GET") throw new PrivateReviewError(405, "METHOD_NOT_ALLOWED", "State is read-only");
        const annotations = await loadAnnotation(runtime.outputPath, runtime.examplePath, runtime.annotationContext);
        const etag = annotationEtag(annotations);
        sendJson(response, 200, {
          csrfToken: runtime.csrfToken,
          etag,
          evidence: runtime.evidence,
          roles: runtime.roles,
          annotations,
        }, { ETag: etag });
        return;
      }

      if (url.pathname === "/__phase1b_review__/reviewer/state") {
        if (method === "GET") {
          const state = await loadReviewerState(runtime);
          const etag = reviewerStateEtag(state);
          sendJson(response, 200, {
            csrfToken: runtime.csrfToken,
            etag,
            evidence: runtime.evidence,
            roles: runtime.roles,
            state,
            summary: reviewerStateSummary(state, ROLE_SPECS),
          }, { ETag: etag });
          return;
        }
        if (method !== "PUT") throw new PrivateReviewError(405, "METHOD_NOT_ALLOWED", "Reviewer state supports GET and PUT");
        assertLocalRequest(request, expectedHost, runtime.origin, { requireOrigin: true });
        if (!safeTokenEquals(request.headers["x-phase1b-csrf"], runtime.csrfToken)) throw new PrivateReviewError(403, "CSRF_REJECTED", "Missing or invalid Phase 1B CSRF token");
        if (!String(request.headers["content-type"] || "").toLowerCase().startsWith("application/json")) throw new PrivateReviewError(415, "JSON_REQUIRED", "Reviewer state must use application/json");
        const ifMatch = request.headers["if-match"];
        if (typeof ifMatch !== "string") throw new PrivateReviewError(428, "IF_MATCH_REQUIRED", "If-Match is required for reviewer writes");
        const body = await readLimitedBody(request, MAX_REVIEWER_STATE_BYTES);
        let payload;
        try { payload = JSON.parse(body.toString("utf8")); } catch { throw new PrivateReviewError(400, "INVALID_JSON", "Reviewer state body is not valid JSON"); }
        const operation = reviewerQueue.catch(() => {}).then(async () => {
          const current = await loadReviewerState(runtime);
          if (ifMatch !== reviewerStateEtag(current)) {
            throw new PrivateReviewError(412, "ETAG_MISMATCH", "Reviewer state changed on disk; reload before saving");
          }
          const next = validateReviewerState(payload, { ...runtime.reviewerContext, now: new Date().toISOString() });
          const serialized = serializeReviewerState(next);
          if (Buffer.byteLength(serialized) > MAX_REVIEWER_STATE_BYTES) {
            throw new PrivateReviewError(413, "BODY_TOO_LARGE", "Reviewer state exceeds 512 KiB");
          }
          await atomicWrite(runtime.reviewerStatePath, serialized);
          return { state: next, etag: reviewerStateEtag(next) };
        });
        reviewerQueue = operation;
        const result = await operation;
        sendJson(response, 200, {
          etag: result.etag,
          state: result.state,
          summary: reviewerStateSummary(result.state, ROLE_SPECS),
        }, { ETag: result.etag });
        return;
      }

      if (url.pathname.startsWith("/__phase1b_review__/candidate/")) {
        if (method !== "GET" && method !== "HEAD") throw new PrivateReviewError(405, "METHOD_NOT_ALLOWED", "Candidate frames are read-only");
        const match = /^\/__phase1b_review__\/candidate\/([a-z-]+)\/(f\d{1,8})(\/thumb)?$/.exec(url.pathname);
        const key = match ? `${match[1]}/${match[2]}${match[3] ? "/thumb" : ""}` : null;
        const record = key ? runtime.candidateRecords.get(key) : null;
        if (!record) throw new PrivateReviewError(404, "ASSET_NOT_FOUND", "Unknown candidate frame");
        if (await sha256File(record.file) !== record.sha256) throw new PrivateReviewError(409, "ASSET_IDENTITY_CHANGED", "Candidate frame changed after startup");
        await serveFile(response, record.file, { privateContent: true, head: method === "HEAD" });
        return;
      }

      if (url.pathname.startsWith("/__phase1b_review__/asset/")) {
        if (method !== "GET" && method !== "HEAD") throw new PrivateReviewError(405, "METHOD_NOT_ALLOWED", "Private assets are read-only");
        const match = /^\/__phase1b_review__\/asset\/([A-Za-z]+)\/([a-z-]+)$/.exec(url.pathname);
        if (!match || !ROLE_BY_ID.has(match[1]) || !ASSET_KINDS.includes(match[2])) throw new PrivateReviewError(404, "ASSET_NOT_FOUND", "Unknown private review asset");
        const record = runtime.assetRecords.get(`${match[1]}/${match[2]}`);
        if (!record) throw new PrivateReviewError(404, "ASSET_NOT_FOUND", "Unknown private review asset");
        if (await sha256File(record.file) !== record.sha256) throw new PrivateReviewError(409, "ASSET_IDENTITY_CHANGED", "Private review asset changed after startup");
        await serveFile(response, record.file, { privateContent: true, head: method === "HEAD" });
        return;
      }

      if (url.pathname === "/__phase1b_review__/annotations") {
        if (method !== "PUT") throw new PrivateReviewError(405, "METHOD_NOT_ALLOWED", "Annotations require PUT");
        assertLocalRequest(request, expectedHost, runtime.origin, { requireOrigin: true });
        if (!safeTokenEquals(request.headers["x-phase1b-csrf"], runtime.csrfToken)) throw new PrivateReviewError(403, "CSRF_REJECTED", "Missing or invalid Phase 1B CSRF token");
        if (!String(request.headers["content-type"] || "").toLowerCase().startsWith("application/json")) throw new PrivateReviewError(415, "JSON_REQUIRED", "Annotations must use application/json");
        const ifMatch = request.headers["if-match"];
        if (typeof ifMatch !== "string") throw new PrivateReviewError(428, "IF_MATCH_REQUIRED", "If-Match is required for annotation writes");
        const body = await readLimitedBody(request);
        let payload;
        try { payload = JSON.parse(body.toString("utf8")); } catch { throw new PrivateReviewError(400, "INVALID_JSON", "Annotation body is not valid JSON"); }

        const operation = writeQueue.catch(() => {}).then(async () => {
          const current = await loadAnnotation(runtime.outputPath, runtime.examplePath, runtime.annotationContext);
          const currentEtag = annotationEtag(current);
          if (ifMatch !== currentEtag) throw new PrivateReviewError(412, "ETAG_MISMATCH", "Annotation state changed; reload before saving");
          const annotation = validateAndRebindAnnotation(payload, {
            ...runtime.annotationContext,
            now: new Date().toISOString(),
          });
          const serialized = serializedAnnotation(annotation);
          if (Buffer.byteLength(serialized) > MAX_ANNOTATION_BYTES) throw new PrivateReviewError(413, "BODY_TOO_LARGE", "Normalized annotation exceeds 256 KiB");
          await atomicWrite(runtime.outputPath, serialized);
          return { annotation, etag: annotationEtag(annotation) };
        });
        writeQueue = operation;
        const result = await operation;
        sendJson(response, 200, { etag: result.etag, annotations: result.annotation }, { ETag: result.etag });
        return;
      }

      if (["/", "/reviewer", "/phase-1b-review", "/phase-1b-review/", "/phase-1b-review.html"].includes(url.pathname)) {
        if (method !== "GET" && method !== "HEAD") throw new PrivateReviewError(405, "METHOD_NOT_ALLOWED", "Review page is read-only");
        await serveFile(response, runtime.htmlPath, { head: method === "HEAD" });
        return;
      }
      if (url.pathname === "/favicon.svg") {
        if (method !== "GET" && method !== "HEAD") throw new PrivateReviewError(405, "METHOD_NOT_ALLOWED", "Static assets are read-only");
        await serveFile(response, safeJoin(runtime.distRoot, "favicon.svg"), { head: method === "HEAD" });
        return;
      }
      const asset = staticAssetPath(runtime, url.pathname);
      if (asset) {
        if (method !== "GET" && method !== "HEAD") throw new PrivateReviewError(405, "METHOD_NOT_ALLOWED", "Static assets are read-only");
        await serveFile(response, asset, { head: method === "HEAD" });
        return;
      }
      throw new PrivateReviewError(404, "NOT_FOUND", "Private review route not found");
    } catch (error) {
      if (!response.headersSent) sendError(response, error);
      else response.destroy();
    }
  };

  const server = createServer((request, response) => { void handler(request, response); });
  return {
    server,
    runtime,
    async listen() {
      await new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(runtime.port, runtime.host, () => { server.off("error", reject); resolve(); });
      });
      return runtime.origin;
    },
    async close() {
      if (!server.listening) return;
      await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
    },
  };
}

export async function startPrivateReviewServer(options = {}) {
  const instance = await createPrivateReviewServer(options);
  await instance.listen();
  return instance;
}
