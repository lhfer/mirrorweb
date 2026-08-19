/**
 * Private Reviewer Mode state: the guided five-step target annotation.
 *
 * This module owns a state file that is deliberately SEPARATE from
 * qa-v4/reference/frozen-visual/annotations.private.json. Reviewer Mode never
 * writes the annotation contract; it produces a locked, hash-identified target
 * annotation that a human can later promote in an explicit, separate step.
 *
 * Every rule here is fail-closed and mirrors the client-side model, so an
 * illegal optical-boundary ordering is rejected even if a hand-written payload
 * reaches the endpoint.
 */

import { createHash } from "node:crypto";

export const REVIEWER_SCHEMA_VERSION = 1;
export const REVIEWER_REFERENCE_CLASS = "frozen-visual-human-reviewer";
export const REVIEWER_STATE_RELATIVE_ROOT = "qa-v4/review";
export const DEFAULT_REVIEWER_STATE_PATH = "qa-v4/review/phase-1b/reviewer-state.private.json";
export const MAX_REVIEWER_STATE_BYTES = 512 * 1024;

/** Step 0 is the tutorial and is never part of a role's own progress. */
export const REVIEWER_STEPS = Object.freeze([1, 2, 3, 4, 5]);
export const FRAME_STATUSES = Object.freeze(["PENDING", "ACCEPTED", "REJECTED"]);
export const QUAD_STATUSES = Object.freeze(["PENDING", "ACCEPTED"]);
export const ZONE_STATUSES = Object.freeze(["PENDING", "ACCEPTED", "UNCLEAR"]);
export const LOCK_STATUSES = Object.freeze(["UNLOCKED", "LOCKED"]);
export const LANGUAGES = Object.freeze(["zh", "en"]);

export const FRAME_REJECT_REASONS = Object.freeze([
  "motion-blur",
  "cursor-occlusion",
  "highlight-occlusion",
  "card-clipped",
  "wrong-role",
  "boundary-unclear",
]);

export const COMPARE_VERDICTS = Object.freeze([
  "local-looks-close",
  "local-too-wide",
  "local-too-narrow",
  "wrong-refraction-direction",
  "highlight-mismatch",
  "dispersion-mismatch",
  "needs-later-review",
]);

/** Mirrors src/review-phase1b/zone-model.ts. Both sides must agree exactly. */
export const MIN_BAND_WIDTH = 0.002;
export const MAX_TOTAL_INWARD = 0.46;
export const ZONE_WIDTH_KEYS = Object.freeze(["sidewall", "strongRim", "shoulder"]);

const SHA256_PATTERN = /^[0-9a-f]{64}$/;
const COORDINATE_PRECISION = 1e6;

export class ReviewerStateError extends Error {
  constructor(message) {
    super(message);
    this.name = "ReviewerStateError";
    this.statusCode = 400;
    this.code = "INVALID_REVIEWER_STATE";
  }
}

function fail(pathLabel, message) {
  throw new ReviewerStateError(`${pathLabel}: ${message}`);
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

function round(value) {
  return Math.round(value * COORDINATE_PRECISION) / COORDINATE_PRECISION;
}

function enumeration(value, allowed, pathLabel) {
  if (!allowed.includes(value)) fail(pathLabel, `must be one of ${allowed.join(", ")}`);
  return value;
}

function optionalText(value, pathLabel, maximum = 2000) {
  if (value === null || value === undefined) return "";
  if (typeof value !== "string") fail(pathLabel, "must be a string");
  if (value.length > maximum) fail(pathLabel, `must be at most ${maximum} characters`);
  return value;
}

function isoOrNull(value, pathLabel) {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string" || !Number.isFinite(Date.parse(value))) fail(pathLabel, "must be an ISO date-time");
  return value;
}

function validatePoint(value, pathLabel) {
  if (!Array.isArray(value) || value.length !== 2) fail(pathLabel, "must be [x, y]");
  for (const [index, entry] of value.entries()) {
    if (typeof entry !== "number" || !Number.isFinite(entry) || entry < 0 || entry > 1) {
      fail(`${pathLabel}[${index}]`, "must be a normalized finite number in [0, 1]");
    }
  }
  return [round(value[0]), round(value[1])];
}

/** TL / TR / BR / BL clockwise image-space quad, identical to the annotation contract. */
export function normalizeQuad(value, pathLabel) {
  if (value === null || value === undefined) return null;
  if (!Array.isArray(value) || value.length !== 4) fail(pathLabel, "must contain TL, TR, BR, BL");
  const quad = value.map((point, index) => validatePoint(point, `${pathLabel}[${index}]`));
  const crosses = quad.map((point, index) => {
    const next = quad[(index + 1) % 4];
    const after = quad[(index + 2) % 4];
    return (next[0] - point[0]) * (after[1] - next[1]) - (next[1] - point[1]) * (after[0] - next[0]);
  });
  if (crosses.some((cross) => cross <= 1e-6)) fail(pathLabel, "must stay a convex clockwise TL/TR/BR/BL quad");
  const topY = (quad[0][1] + quad[1][1]) / 2;
  const bottomY = (quad[2][1] + quad[3][1]) / 2;
  const leftX = (quad[0][0] + quad[3][0]) / 2;
  const rightX = (quad[1][0] + quad[2][0]) / 2;
  if (!(topY < bottomY && leftX < rightX)) fail(pathLabel, "must retain TL/TR/BR/BL ordering");
  return quad;
}

/**
 * Band widths, not cumulative boundaries. Ordering cannot be violated because
 * an ordered cumulative triple is derived from three positive widths.
 */
export function normalizeZoneWidths(value, pathLabel) {
  if (value === null || value === undefined) return null;
  exactObject(value, ZONE_WIDTH_KEYS, [], pathLabel);
  const widths = {};
  let total = 0;
  for (const key of ZONE_WIDTH_KEYS) {
    const entry = value[key];
    if (typeof entry !== "number" || !Number.isFinite(entry)) fail(`${pathLabel}.${key}`, "must be a finite number");
    if (entry < MIN_BAND_WIDTH) fail(`${pathLabel}.${key}`, `must be at least ${MIN_BAND_WIDTH} of the card minor axis`);
    widths[key] = round(entry);
    total += widths[key];
  }
  if (total > MAX_TOTAL_INWARD + 1e-9) {
    fail(pathLabel, `accumulated inward distance must stay below ${MAX_TOTAL_INWARD} of the card minor axis`);
  }
  return widths;
}

export function boundariesFromWidths(widths) {
  const first = widths.sidewall;
  const second = round(first + widths.strongRim);
  return {
    coordinateSpace: "inward-ratio-of-card-minor-axis",
    sidewallOuter: 0,
    sidewallToStrongLensRim: round(first),
    strongLensRimToOpticalShoulder: second,
    opticalShoulderToCenterFace: round(second + widths.shoulder),
  };
}

export function boundariesAreOrdered(boundaries) {
  const values = [
    boundaries.sidewallToStrongLensRim,
    boundaries.strongLensRimToOpticalShoulder,
    boundaries.opticalShoulderToCenterFace,
  ];
  return values.every((value) => typeof value === "number" && Number.isFinite(value))
    && 0 < values[0] && values[0] < values[1] && values[1] < values[2] && values[2] < 0.5;
}

function emptyRoleState() {
  return {
    step: 1,
    frame: { status: "PENDING", candidateId: null, rejectionReasons: [], note: "" },
    quad: { status: "PENDING", quadNormalized: null },
    zones: { status: "PENDING", widths: null },
    lock: { status: "UNLOCKED", targetAnnotationSha256: null, lockedAt: null, unlockCount: 0, unlockReason: "" },
    compare: { verdicts: [], note: "" },
    updatedAt: null,
  };
}

export function emptyReviewerState(context = {}) {
  const roleIds = context.roleIds ?? [];
  return {
    schemaVersion: REVIEWER_SCHEMA_VERSION,
    referenceClass: REVIEWER_REFERENCE_CLASS,
    private: true,
    sourceVideoSha256: context.sourceVideoSha256 ?? null,
    evidenceBinding: context.evidenceBinding ? { ...context.evidenceBinding } : null,
    language: "zh",
    tutorialAcknowledged: false,
    activeRoleId: roleIds[0] ?? null,
    roles: Object.fromEntries(roleIds.map((id) => [id, emptyRoleState()])),
    updatedAt: null,
  };
}

/**
 * The furthest step a role may display. The reviewer can always walk back, but
 * cannot skip ahead of the evidence they have actually produced. Step 5 is the
 * only step that is allowed to show the local candidate at all.
 */
export function maxReachableStep(role) {
  if (role.frame.status !== "ACCEPTED") return 1;
  if (role.quad.status !== "ACCEPTED") return 2;
  if (role.zones.status !== "ACCEPTED") return 3;
  if (role.lock.status !== "LOCKED") return 4;
  return 5;
}

/** Steps 1-4 are the Target Annotation stage; the local capture stays hidden. */
export function localComparisonAllowed(role) {
  return role.lock.status === "LOCKED";
}

export function roleProgressState(role) {
  if (role.frame.status === "REJECTED") return "REJECTED";
  if (role.lock.status === "LOCKED") return "TARGET_LOCKED";
  if (role.zones.status === "ACCEPTED") return "PENDING_LOCK";
  if (role.quad.status === "ACCEPTED") return "PENDING_ZONES";
  if (role.frame.status === "ACCEPTED") return "PENDING_QUAD";
  return "PENDING_FRAME";
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (isPlainObject(value)) {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value ?? null);
}

/**
 * Identity of one locked target annotation. Recomputing this from the stored
 * state must reproduce the stored hash, otherwise the lock is not trusted.
 */
export function targetAnnotationPayload(roleId, spec, role, state) {
  return {
    referenceClass: REVIEWER_REFERENCE_CLASS,
    schemaVersion: REVIEWER_SCHEMA_VERSION,
    roleId,
    targetCategory: spec.targetCategory,
    targetFrameSha256: spec.targetFrameSha256,
    frameCandidateId: role.frame.candidateId,
    quadNormalized: role.quad.quadNormalized,
    zoneWidths: role.zones.widths,
    zoneBoundaries: role.zones.widths ? boundariesFromWidths(role.zones.widths) : null,
    sourceVideoSha256: state.sourceVideoSha256,
    evidenceBinding: state.evidenceBinding,
  };
}

export function computeTargetAnnotationHash(roleId, spec, role, state) {
  return createHash("sha256")
    .update(canonicalJson(targetAnnotationPayload(roleId, spec, role, state)))
    .digest("hex");
}

function validateRoleState(value, roleId, spec, state, context) {
  const pathLabel = `roles.${roleId}`;
  exactObject(value, ["step", "frame", "quad", "zones", "lock", "compare", "updatedAt"], [], pathLabel);

  exactObject(value.frame, ["status", "candidateId", "rejectionReasons", "note"], [], `${pathLabel}.frame`);
  const frameStatus = enumeration(value.frame.status, FRAME_STATUSES, `${pathLabel}.frame.status`);
  let candidateId = value.frame.candidateId;
  if (candidateId !== null) {
    if (typeof candidateId !== "string" || !/^[A-Za-z0-9_-]{1,64}$/.test(candidateId)) {
      fail(`${pathLabel}.frame.candidateId`, "must be null or a candidate identifier");
    }
    const allowed = context.candidateIds?.get(spec.targetCategory);
    if (allowed && !allowed.has(candidateId)) fail(`${pathLabel}.frame.candidateId`, "is not an offered candidate frame");
  }
  if (!Array.isArray(value.frame.rejectionReasons)) fail(`${pathLabel}.frame.rejectionReasons`, "must be an array");
  const rejectionReasons = [...new Set(value.frame.rejectionReasons)];
  for (const reason of rejectionReasons) enumeration(reason, FRAME_REJECT_REASONS, `${pathLabel}.frame.rejectionReasons`);
  const frameNote = optionalText(value.frame.note, `${pathLabel}.frame.note`);
  if (frameStatus === "ACCEPTED" && candidateId === null) fail(`${pathLabel}.frame`, "acceptance requires a selected candidate frame");
  if (frameStatus === "REJECTED" && rejectionReasons.length === 0) fail(`${pathLabel}.frame`, "rejection requires at least one reason");
  if (frameStatus !== "REJECTED" && rejectionReasons.length > 0) fail(`${pathLabel}.frame`, "reasons are only recorded for a rejected frame");

  exactObject(value.quad, ["status", "quadNormalized"], [], `${pathLabel}.quad`);
  const quadStatus = enumeration(value.quad.status, QUAD_STATUSES, `${pathLabel}.quad.status`);
  const quadNormalized = normalizeQuad(value.quad.quadNormalized, `${pathLabel}.quad.quadNormalized`);
  if (quadStatus === "ACCEPTED" && quadNormalized === null) fail(`${pathLabel}.quad`, "acceptance requires a card quad");
  if (quadStatus === "ACCEPTED" && frameStatus !== "ACCEPTED") fail(`${pathLabel}.quad`, "acceptance requires an accepted target frame");

  exactObject(value.zones, ["status", "widths"], [], `${pathLabel}.zones`);
  const zoneStatus = enumeration(value.zones.status, ZONE_STATUSES, `${pathLabel}.zones.status`);
  const widths = normalizeZoneWidths(value.zones.widths, `${pathLabel}.zones.widths`);
  if (zoneStatus === "ACCEPTED") {
    if (widths === null) fail(`${pathLabel}.zones`, "acceptance requires marked optical boundaries");
    if (!boundariesAreOrdered(boundariesFromWidths(widths))) {
      fail(`${pathLabel}.zones`, "boundaries must stay ordered: 0 < sidewall < strong rim < shoulder");
    }
    if (quadStatus !== "ACCEPTED") fail(`${pathLabel}.zones`, "acceptance requires an accepted card quad");
  }

  exactObject(value.lock, ["status", "targetAnnotationSha256", "lockedAt", "unlockCount", "unlockReason"], [], `${pathLabel}.lock`);
  const lockStatus = enumeration(value.lock.status, LOCK_STATUSES, `${pathLabel}.lock.status`);
  const lockedAt = isoOrNull(value.lock.lockedAt, `${pathLabel}.lock.lockedAt`);
  const unlockCount = value.lock.unlockCount;
  if (!Number.isInteger(unlockCount) || unlockCount < 0 || unlockCount > 10000) {
    fail(`${pathLabel}.lock.unlockCount`, "must be a non-negative integer");
  }
  const unlockReason = optionalText(value.lock.unlockReason, `${pathLabel}.lock.unlockReason`);
  if (unlockCount > 0 && unlockReason.trim().length < 8) {
    fail(`${pathLabel}.lock.unlockReason`, "unlocking a target annotation requires a concrete reason");
  }

  const normalizedRole = {
    step: 1,
    frame: { status: frameStatus, candidateId, rejectionReasons, note: frameNote },
    quad: { status: quadStatus, quadNormalized },
    zones: { status: zoneStatus, widths },
    lock: {
      status: lockStatus,
      targetAnnotationSha256: null,
      lockedAt,
      unlockCount,
      unlockReason,
    },
    compare: { verdicts: [], note: "" },
    updatedAt: isoOrNull(value.updatedAt, `${pathLabel}.updatedAt`),
  };

  if (lockStatus === "LOCKED" && context.bindingDrifted) {
    // The evidence this lock was taken against no longer exists. The lock is
    // dropped rather than rejected, so the reviewer keeps their drafted
    // geometry and re-confirms it against the new evidence.
    normalizedRole.lock.status = "UNLOCKED";
    normalizedRole.lock.lockedAt = null;
  } else if (lockStatus === "LOCKED") {
    if (zoneStatus !== "ACCEPTED") fail(`${pathLabel}.lock`, "locking requires accepted frame, quad and optical zones");
    const expected = computeTargetAnnotationHash(roleId, spec, normalizedRole, state);
    const provided = value.lock.targetAnnotationSha256;
    if (typeof provided !== "string" || !SHA256_PATTERN.test(provided)) {
      fail(`${pathLabel}.lock.targetAnnotationSha256`, "must be a SHA-256 hash");
    }
    if (provided !== expected) fail(`${pathLabel}.lock`, "target annotation hash does not match the locked geometry");
    normalizedRole.lock.targetAnnotationSha256 = expected;
    if (!lockedAt) normalizedRole.lock.lockedAt = context.now ?? null;
  } else if (lockStatus === "UNLOCKED" && value.lock.targetAnnotationSha256 !== null) {
    fail(`${pathLabel}.lock.targetAnnotationSha256`, "must be null while the target annotation is unlocked");
  }

  exactObject(value.compare, ["verdicts", "note"], [], `${pathLabel}.compare`);
  if (!Array.isArray(value.compare.verdicts)) fail(`${pathLabel}.compare.verdicts`, "must be an array");
  const verdicts = [...new Set(value.compare.verdicts)];
  for (const verdict of verdicts) enumeration(verdict, COMPARE_VERDICTS, `${pathLabel}.compare.verdicts`);
  if (verdicts.length > 0 && lockStatus !== "LOCKED") {
    fail(`${pathLabel}.compare`, "a local comparison requires a locked target annotation");
  }
  normalizedRole.compare = { verdicts, note: optionalText(value.compare.note, `${pathLabel}.compare.note`) };

  const step = value.step;
  if (!REVIEWER_STEPS.includes(step)) fail(`${pathLabel}.step`, `must be one of ${REVIEWER_STEPS.join(", ")}`);
  const reachable = maxReachableStep(normalizedRole);
  if (context.bindingDrifted) {
    normalizedRole.step = Math.min(step, reachable);
    return normalizedRole;
  }
  if (step > reachable) fail(`${pathLabel}.step`, `step ${step} is not reachable yet (max ${reachable})`);
  if (step === 5 && !localComparisonAllowed(normalizedRole)) {
    fail(`${pathLabel}.step`, "the local comparison step requires a locked target annotation");
  }
  normalizedRole.step = step;
  return normalizedRole;
}

function bindingChanged(stored, expected) {
  if (!stored || !expected) return false;
  return Object.keys(expected).some((key) => stored[key] !== expected[key]);
}

function resetDecisions(role) {
  return {
    ...role,
    step: 1,
    frame: { ...role.frame, status: "PENDING", rejectionReasons: [] },
    quad: { ...role.quad, status: "PENDING" },
    zones: { ...role.zones, status: "PENDING" },
    lock: { status: "UNLOCKED", targetAnnotationSha256: null, lockedAt: null, unlockCount: role.lock.unlockCount, unlockReason: role.lock.unlockReason },
    compare: { verdicts: [], note: role.compare.note },
  };
}

/**
 * Validates and normalizes a reviewer-state payload.
 *
 * `context` carries the immutable evidence identity, the role specs and the
 * candidate frames the server actually offers. Drafts survive an evidence
 * rebind; human decisions do not.
 */
export function validateReviewerState(payload, context = {}) {
  if (!isPlainObject(payload)) fail("<root>", "must be an object");
  const roleSpecs = context.roleSpecs ?? [];
  const roleIds = roleSpecs.map((spec) => spec.id);
  exactObject(
    payload,
    ["schemaVersion", "referenceClass", "private", "sourceVideoSha256", "evidenceBinding", "language", "tutorialAcknowledged", "activeRoleId", "roles", "updatedAt"],
    ["$schema"],
    "<root>",
  );
  if (payload.schemaVersion !== REVIEWER_SCHEMA_VERSION) fail("schemaVersion", `must be ${REVIEWER_SCHEMA_VERSION}`);
  if (payload.referenceClass !== REVIEWER_REFERENCE_CLASS) fail("referenceClass", "has an unexpected reference class");
  if (payload.private !== true) fail("private", "must be true");
  if (typeof payload.tutorialAcknowledged !== "boolean") fail("tutorialAcknowledged", "must be boolean");
  enumeration(payload.language, LANGUAGES, "language");

  const state = {
    schemaVersion: REVIEWER_SCHEMA_VERSION,
    referenceClass: REVIEWER_REFERENCE_CLASS,
    private: true,
    sourceVideoSha256: context.sourceVideoSha256 ?? payload.sourceVideoSha256 ?? null,
    evidenceBinding: context.evidenceBinding ? { ...context.evidenceBinding } : payload.evidenceBinding ?? null,
    language: payload.language,
    tutorialAcknowledged: payload.tutorialAcknowledged,
    activeRoleId: roleIds.includes(payload.activeRoleId) ? payload.activeRoleId : roleIds[0] ?? null,
    roles: {},
    updatedAt: context.now ?? isoOrNull(payload.updatedAt, "updatedAt"),
  };
  if (state.sourceVideoSha256 !== null && !SHA256_PATTERN.test(String(state.sourceVideoSha256))) {
    fail("sourceVideoSha256", "must be a SHA-256 hash");
  }

  exactObject(payload.roles, roleIds, [], "roles");
  const drifted = bindingChanged(payload.evidenceBinding, context.evidenceBinding);
  const roleContext = { ...context, bindingDrifted: drifted };
  for (const spec of roleSpecs) {
    const normalized = validateRoleState(payload.roles[spec.id], spec.id, spec, state, roleContext);
    state.roles[spec.id] = drifted ? resetDecisions(normalized) : normalized;
  }
  return state;
}

export function reviewerStateSummary(state, roleSpecs) {
  const roles = roleSpecs.map((spec) => ({
    id: spec.id,
    progress: roleProgressState(state.roles[spec.id]),
    step: state.roles[spec.id].step,
    locked: state.roles[spec.id].lock.status === "LOCKED",
  }));
  return {
    lockedCount: roles.filter((role) => role.locked).length,
    rejectedCount: roles.filter((role) => role.progress === "REJECTED").length,
    roleCount: roles.length,
    roles,
  };
}

export function serializeReviewerState(state) {
  return `${JSON.stringify(state, null, 2)}\n`;
}

export function reviewerStateEtag(state) {
  return `"${createHash("sha256").update(serializeReviewerState(state)).digest("hex")}"`;
}
