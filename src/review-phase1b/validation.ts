import {
  ASSET_KINDS,
  FEATURE_IDS,
  ROLE_IDS,
  type CategoryAnnotation,
  type NormalizedPoint,
  type NormalizedQuad,
  type ReviewAnnotations,
  type ReviewApiState,
  type ReviewRoleEvidence,
  type ReviewStatus,
  type RoleId,
  type ZoneBoundaries,
  type ZoneDraft,
} from "./types";

const SHA256 = /^[0-9a-f]{64}$/;
const GIT_HEAD = /^[0-9a-f]{40}$/;
const STATUSES = new Set<ReviewStatus>(["PENDING", "APPROVED", "REJECTED"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) throw new Error(`Missing ${key}`);
  return value;
}

function reviewStatus(value: unknown, label: string): ReviewStatus {
  if (typeof value !== "string" || !STATUSES.has(value as ReviewStatus)) {
    throw new Error(`${label} has an invalid review status`);
  }
  return value as ReviewStatus;
}

function sha256(value: unknown, label: string): string {
  if (typeof value !== "string" || !SHA256.test(value)) throw new Error(`${label} is not SHA-256 bound`);
  return value;
}

function nullableFinite(value: unknown, label: string): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${label} is not finite`);
  return value;
}

function point(value: unknown, label: string): NormalizedPoint {
  if (!Array.isArray(value) || value.length !== 2) throw new Error(`${label} is not a 2D point`);
  const x = value[0];
  const y = value[1];
  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    !Number.isFinite(x) ||
    !Number.isFinite(y) ||
    x < 0 ||
    x > 1 ||
    y < 0 ||
    y > 1
  ) {
    throw new Error(`${label} leaves the normalized image plane`);
  }
  return [x, y];
}

function cross(a: NormalizedPoint, b: NormalizedPoint, c: NormalizedPoint): number {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

export function validateQuad(value: unknown, label = "quad"): NormalizedQuad {
  if (!Array.isArray(value) || value.length !== 4) throw new Error(`${label} must contain four corners`);
  const quad = value.map((item, index) => point(item, `${label}[${index}]`)) as NormalizedQuad;
  const turns = quad.map((item, index) => cross(item, quad[(index + 1) % 4], quad[(index + 2) % 4]));
  if (turns.some((value) => value <= 1e-6)) {
    throw new Error(`${label} must preserve clockwise image-space TL / TR / BR / BL ordering`);
  }
  const area = Math.abs(
    quad.reduce((sum, item, index) => {
      const next = quad[(index + 1) % 4];
      return sum + item[0] * next[1] - next[0] * item[1];
    }, 0) / 2,
  );
  if (area < 0.002) throw new Error(`${label} is too small for precise review`);
  const topY = (quad[0][1] + quad[1][1]) / 2;
  const bottomY = (quad[2][1] + quad[3][1]) / 2;
  const leftX = (quad[0][0] + quad[3][0]) / 2;
  const rightX = (quad[1][0] + quad[2][0]) / 2;
  if (!(topY < bottomY && leftX < rightX)) {
    throw new Error(`${label} no longer preserves TL / TR / BR / BL ordering`);
  }
  return quad;
}

export function validateZoneDraft(value: ZoneDraft, label = "zone boundaries"): ZoneDraft {
  const values = [
    value.sidewallToStrongLensRim,
    value.strongLensRimToOpticalShoulder,
    value.opticalShoulderToCenterFace,
  ];
  if (values.some((entry) => !Number.isFinite(entry) || entry < 0 || entry > 0.5)) {
    throw new Error(`${label} must stay between 0% and 50% of the card minor axis`);
  }
  if (!(values[0] > 0 && values[0] < values[1] && values[1] < values[2])) {
    throw new Error(`${label} must remain strictly ordered: 0 < Sidewall < Strong Rim < Shoulder`);
  }
  return value;
}

function parseZoneBoundaries(value: unknown, label: string): ZoneBoundaries {
  if (!isRecord(value)) throw new Error(`${label} is missing`);
  if (value.coordinateSpace !== "inward-ratio-of-card-minor-axis" || value.sidewallOuter !== 0) {
    throw new Error(`${label} uses an unsupported coordinate space`);
  }
  return {
    coordinateSpace: "inward-ratio-of-card-minor-axis",
    sidewallOuter: 0,
    sidewallToStrongLensRim: nullableFinite(value.sidewallToStrongLensRim, `${label}.sidewallToStrongLensRim`),
    strongLensRimToOpticalShoulder: nullableFinite(
      value.strongLensRimToOpticalShoulder,
      `${label}.strongLensRimToOpticalShoulder`,
    ),
    opticalShoulderToCenterFace: nullableFinite(
      value.opticalShoulderToCenterFace,
      `${label}.opticalShoulderToCenterFace`,
    ),
  };
}

function parseRoleEvidence(value: unknown, expectedId: RoleId): ReviewRoleEvidence {
  if (!isRecord(value)) throw new Error(`Role ${expectedId} evidence is missing`);
  const id = requiredString(value, "id");
  if (id !== expectedId) throw new Error(`Expected role ${expectedId}, received ${id}`);
  const label = requiredString(value, "label");
  const targetCategory = requiredString(value, "targetCategory");
  const parsed: ReviewRoleEvidence = {
    id: expectedId,
    label,
    targetCategory,
    frameReused: value.frameReused === true,
  };
  if (value.targetFrameSha256 !== undefined) parsed.targetFrameSha256 = sha256(value.targetFrameSha256, `${id}.targetFrameSha256`);
  if (value.localCaptureId !== undefined) parsed.localCaptureId = requiredString(value, "localCaptureId");
  if (value.localCaptureSha256 !== undefined) parsed.localCaptureSha256 = sha256(value.localCaptureSha256, `${id}.localCaptureSha256`);
  const suggestedQuad = value.suggestedQuadNormalized ?? value.quadNormalized;
  if (suggestedQuad !== undefined) parsed.suggestedQuadNormalized = validateQuad(suggestedQuad, `${id}.suggestedQuadNormalized`);
  const suggestedZones = value.suggestedZoneBoundaries ?? value.zoneBoundaries;
  if (suggestedZones !== undefined) parsed.suggestedZoneBoundaries = parseZoneBoundaries(suggestedZones, `${id}.suggestedZoneBoundaries`);
  if (!isRecord(value.assets)) throw new Error(`${id}.assets is missing`);
  for (const kind of ASSET_KINDS) {
    const asset = value.assets[kind];
    if (typeof asset === "string") sha256(asset, `${id}.assets.${kind}`);
    else if (isRecord(asset)) sha256(asset.sha256, `${id}.assets.${kind}.sha256`);
    else throw new Error(`${id} is missing ${kind} evidence`);
  }
  parsed.assets = value.assets as ReviewRoleEvidence["assets"];
  return parsed;
}

function parseCategory(value: unknown, label: string): CategoryAnnotation {
  if (!isRecord(value)) throw new Error(`${label} is missing`);
  const sourceFrameSha256 = sha256(value.sourceFrameSha256, `${label}.sourceFrameSha256`);
  const quadReviewStatus = reviewStatus(value.quadReviewStatus, `${label}.quadReviewStatus`);
  const zoneReviewStatus = reviewStatus(value.zoneReviewStatus, `${label}.zoneReviewStatus`);
  const quadNormalized = value.quadNormalized === null ? null : validateQuad(value.quadNormalized, `${label}.quadNormalized`);
  const zoneBoundaries = parseZoneBoundaries(value.zoneBoundaries, `${label}.zoneBoundaries`);
  if (!isRecord(value.approvals)) throw new Error(`${label}.approvals is missing`);
  if (typeof value.approvals.existingHighlightMask !== "boolean" || typeof value.approvals.naturalFeatureSignature !== "boolean") {
    throw new Error(`${label}.approvals is invalid`);
  }
  if (!isRecord(value.metrics)) throw new Error(`${label}.metrics is missing`);
  const categoryReviewStatus = value.reviewStatus;
  if (typeof categoryReviewStatus !== "string" || !["PENDING", "PARTIAL", "APPROVED", "REJECTED"].includes(categoryReviewStatus)) {
    throw new Error(`${label}.reviewStatus is invalid`);
  }
  return {
    ...(value as unknown as CategoryAnnotation),
    sourceFrameSha256,
    reviewStatus: categoryReviewStatus as CategoryAnnotation["reviewStatus"],
    quadReviewStatus,
    zoneReviewStatus,
    quadNormalized,
    zoneBoundaries,
    approvals: {
      existingHighlightMask: value.approvals.existingHighlightMask,
      naturalFeatureSignature: value.approvals.naturalFeatureSignature,
    },
  };
}

function normalizeRoleEvidence(value: unknown): ReviewRoleEvidence[] {
  if (Array.isArray(value)) {
    if (value.length !== ROLE_IDS.length) throw new Error(`Expected ${ROLE_IDS.length} roles`);
    return ROLE_IDS.map((id, index) => parseRoleEvidence(value[index], id));
  }
  if (!isRecord(value)) throw new Error("Role evidence is missing");
  return ROLE_IDS.map((id) => parseRoleEvidence(value[id], id));
}

function parseAnnotations(value: unknown, roles: ReviewRoleEvidence[]): ReviewAnnotations {
  if (!isRecord(value)) throw new Error("Annotations document is missing");
  if (typeof value.schemaVersion !== "number" || value.schemaVersion < 2) {
    throw new Error("Phase 1B review requires annotation schema v2 or newer");
  }
  if (value.private !== true) throw new Error("Annotations are not marked private");
  const sourceVideoSha256 = sha256(value.sourceVideoSha256, "annotations.sourceVideoSha256");
  if (!isRecord(value.evidenceBinding)) throw new Error("Annotation evidence binding is missing");
  const evidenceBinding = {
    frozenManifestSha256: sha256(value.evidenceBinding.frozenManifestSha256, "annotations.evidenceBinding.frozenManifestSha256"),
    reviewBundleSha256: sha256(value.evidenceBinding.reviewBundleSha256, "annotations.evidenceBinding.reviewBundleSha256"),
    reviewAssetSetSha256: sha256(value.evidenceBinding.reviewAssetSetSha256, "annotations.evidenceBinding.reviewAssetSetSha256"),
    localRuntimeSourceSetSha256: sha256(
      value.evidenceBinding.localRuntimeSourceSetSha256,
      "annotations.evidenceBinding.localRuntimeSourceSetSha256",
    ),
  };
  if (!isRecord(value.categories)) throw new Error("Annotation categories are missing");
  if (!isRecord(value.roles)) throw new Error("Annotation roles are missing");

  const categories: Record<string, CategoryAnnotation> = {};
  for (const role of roles) {
    if (!(role.targetCategory in categories)) {
      categories[role.targetCategory] = parseCategory(
        value.categories[role.targetCategory],
        `categories.${role.targetCategory}`,
      );
    }
  }

  const annotationRoles = {} as ReviewAnnotations["roles"];
  for (const role of roles) {
    const entry = value.roles[role.id];
    if (!isRecord(entry)) throw new Error(`annotations.roles.${role.id} is missing`);
    if (entry.targetCategory !== role.targetCategory) throw new Error(`${role.id} target category drifted`);
    const targetFrameSha256 = sha256(entry.targetFrameSha256, `${role.id}.targetFrameSha256`);
    const localCaptureId = requiredString(entry, "localCaptureId");
    const localCaptureSha256 = sha256(entry.localCaptureSha256, `${role.id}.localCaptureSha256`);
    if (!isRecord(entry.featureDecisions)) throw new Error(`${role.id}.featureDecisions is missing`);
    annotationRoles[role.id] = {
      targetCategory: role.targetCategory,
      targetFrameSha256,
      localCaptureId,
      localCaptureSha256,
      reviewStatus: reviewStatus(entry.reviewStatus, `${role.id}.reviewStatus`),
      featureDecisions: {
        edge: reviewStatus(entry.featureDecisions.edge, `${role.id}.featureDecisions.edge`),
        highlight: reviewStatus(entry.featureDecisions.highlight, `${role.id}.featureDecisions.highlight`),
        dispersion: reviewStatus(entry.featureDecisions.dispersion, `${role.id}.featureDecisions.dispersion`),
        sharpness: reviewStatus(entry.featureDecisions.sharpness, `${role.id}.featureDecisions.sharpness`),
      },
      notes: typeof entry.notes === "string" ? entry.notes : "",
    };
  }

  if (!isRecord(value.approvals) || typeof value.approvals.brightDarkPairedUse !== "boolean") {
    throw new Error("Global annotation approvals are invalid");
  }

  const topReviewStatus = value.reviewStatus;
  if (typeof topReviewStatus !== "string" || !["PENDING", "PARTIAL", "APPROVED", "REJECTED"].includes(topReviewStatus)) {
    throw new Error("annotations.reviewStatus is invalid");
  }
  return {
    ...(value as unknown as ReviewAnnotations),
    sourceVideoSha256,
    evidenceBinding,
    reviewStatus: topReviewStatus as ReviewAnnotations["reviewStatus"],
    approvals: { brightDarkPairedUse: value.approvals.brightDarkPairedUse },
    categories: { ...(value.categories as Record<string, CategoryAnnotation>), ...categories },
    roles: annotationRoles,
  };
}

export function parseReviewState(value: unknown): { state: ReviewApiState; roles: ReviewRoleEvidence[] } {
  if (!isRecord(value)) throw new Error("Review API returned a non-object response");
  const csrfToken = requiredString(value, "csrfToken");
  const etag = requiredString(value, "etag");
  if (!isRecord(value.evidence)) throw new Error("Evidence identity is missing");
  const evidence = value.evidence;
  const sourceVideoSha256 = sha256(evidence.sourceVideoSha256, "evidence.sourceVideoSha256");
  const localHead = requiredString(evidence, "localHead");
  if (!GIT_HEAD.test(localHead)) throw new Error("Evidence localHead is not a commit hash");
  const localRuntimeSourceSetSha256 = sha256(
    evidence.localRuntimeSourceSetSha256,
    "evidence.localRuntimeSourceSetSha256",
  );
  const reviewBundleSha256 = sha256(evidence.reviewBundleSha256, "evidence.reviewBundleSha256");
  const frozenManifestSha256 = sha256(evidence.frozenManifestSha256, "evidence.frozenManifestSha256");
  const reviewAssetSetSha256 = sha256(evidence.reviewAssetSetSha256, "evidence.reviewAssetSetSha256");
  const failures = evidence.failures;
  if (Array.isArray(failures) && failures.length > 0) throw new Error(`Evidence gate: ${failures.join("; ")}`);
  if (evidence.ready === false || (typeof evidence.status === "string" && !["PASS", "READY"].includes(evidence.status))) {
    throw new Error(`Evidence status is ${String(evidence.status ?? "not ready")}`);
  }
  if (evidence.privateOutput !== true && evidence.privateOutput !== "PRIVATE" && evidence.privateOutput !== "IGNORED") {
    throw new Error("Private output is not proven ignored and local-only");
  }

  const roles = normalizeRoleEvidence(value.roles);
  const annotations = parseAnnotations(value.annotations, roles);
  if (annotations.sourceVideoSha256 !== sourceVideoSha256) throw new Error("Frozen source identity does not match annotations");
  if (
    annotations.evidenceBinding.frozenManifestSha256 !== frozenManifestSha256
    || annotations.evidenceBinding.reviewBundleSha256 !== reviewBundleSha256
    || annotations.evidenceBinding.reviewAssetSetSha256 !== reviewAssetSetSha256
    || annotations.evidenceBinding.localRuntimeSourceSetSha256 !== localRuntimeSourceSetSha256
  ) throw new Error("Private annotations are bound to a different review evidence set");

  for (const role of roles) {
    const category = annotations.categories[role.targetCategory];
    const roleAnnotation = annotations.roles[role.id];
    if (category.sourceFrameSha256 !== roleAnnotation.targetFrameSha256) {
      throw new Error(`${role.id} target frame identity does not match its category`);
    }
    if (role.targetFrameSha256 && role.targetFrameSha256 !== roleAnnotation.targetFrameSha256) {
      throw new Error(`${role.id} target frame identity does not match evidence`);
    }
    if (role.localCaptureId && role.localCaptureId !== roleAnnotation.localCaptureId) {
      throw new Error(`${role.id} local capture id does not match evidence`);
    }
    if (role.localCaptureSha256 && role.localCaptureSha256 !== roleAnnotation.localCaptureSha256) {
      throw new Error(`${role.id} local capture identity does not match evidence`);
    }

    if (category.quadNormalized === null && !role.suggestedQuadNormalized) {
      throw new Error(`${role.id} has no editable card quad`);
    }
    const zone = category.zoneBoundaries;
    const hasStoredZones =
      zone.sidewallToStrongLensRim !== null &&
      zone.strongLensRimToOpticalShoulder !== null &&
      zone.opticalShoulderToCenterFace !== null;
    if (!hasStoredZones && !role.suggestedZoneBoundaries) {
      throw new Error(`${role.id} has no editable optical-zone suggestion`);
    }
  }

  return {
    roles,
    state: {
      csrfToken,
      etag,
      evidence: {
        status: typeof evidence.status === "string" ? evidence.status : undefined,
        ready: typeof evidence.ready === "boolean" ? evidence.ready : undefined,
        sourceVideoSha256,
        localHead,
        localRuntimeSourceSetSha256,
        reviewBundleSha256,
        frozenManifestSha256,
        reviewAssetSetSha256,
        privateOutput: evidence.privateOutput as boolean | string,
        failures: Array.isArray(failures) ? failures.filter((item): item is string => typeof item === "string") : [],
      },
      roles,
      annotations,
    },
  };
}

export function zoneDraftFrom(category: CategoryAnnotation, role: ReviewRoleEvidence): ZoneDraft {
  const stored = category.zoneBoundaries;
  const suggested = role.suggestedZoneBoundaries;
  const sidewallToStrongLensRim = stored.sidewallToStrongLensRim ?? suggested?.sidewallToStrongLensRim;
  const strongLensRimToOpticalShoulder =
    stored.strongLensRimToOpticalShoulder ?? suggested?.strongLensRimToOpticalShoulder;
  const opticalShoulderToCenterFace =
    stored.opticalShoulderToCenterFace ?? suggested?.opticalShoulderToCenterFace;
  if (
    sidewallToStrongLensRim === null ||
    sidewallToStrongLensRim === undefined ||
    strongLensRimToOpticalShoulder === null ||
    strongLensRimToOpticalShoulder === undefined ||
    opticalShoulderToCenterFace === null ||
    opticalShoulderToCenterFace === undefined
  ) {
    throw new Error(`${role.id} optical zones are incomplete`);
  }
  return validateZoneDraft({
    sidewallToStrongLensRim,
    strongLensRimToOpticalShoulder,
    opticalShoulderToCenterFace,
  });
}

export function quadFrom(category: CategoryAnnotation, role: ReviewRoleEvidence): NormalizedQuad {
  return validateQuad(category.quadNormalized ?? role.suggestedQuadNormalized, `${role.id}.quad`);
}
