export const ROLE_IDS = [
  "bright",
  "dark",
  "highTexture",
  "lowTexture",
  "front",
  "leftTilt",
  "rightTilt",
] as const;

export const FEATURE_IDS = ["edge", "highlight", "dispersion", "sharpness"] as const;

export const CORNER_IDS = ["topLeft", "topRight", "bottomRight", "bottomLeft"] as const;

export const ASSET_KINDS = [
  "target-source",
  "target-plane",
  "target-edge",
  "target-highlight",
  "local-source",
  "local-plane",
  "local-edge",
  "local-highlight",
  "local-dispersion",
  "local-zones",
] as const;

export type RoleId = (typeof ROLE_IDS)[number];
export type FeatureId = (typeof FEATURE_IDS)[number];
export type CornerId = (typeof CORNER_IDS)[number];
export type AssetKind = (typeof ASSET_KINDS)[number];
export type ReviewStatus = "PENDING" | "APPROVED" | "REJECTED";
export type CoordinateView = "source" | "plane";
export type OverlayId = FeatureId;
export type RoiId =
  | "all"
  | "topLeft"
  | "top"
  | "topRight"
  | "left"
  | "right"
  | "bottomLeft"
  | "bottom"
  | "bottomRight";

export type NormalizedPoint = [number, number];
export type NormalizedQuad = [NormalizedPoint, NormalizedPoint, NormalizedPoint, NormalizedPoint];

export interface ZoneBoundaries {
  coordinateSpace: "inward-ratio-of-card-minor-axis";
  sidewallOuter: 0;
  sidewallToStrongLensRim: number | null;
  strongLensRimToOpticalShoulder: number | null;
  opticalShoulderToCenterFace: number | null;
}

export interface FeatureDecisions {
  edge: ReviewStatus;
  highlight: ReviewStatus;
  dispersion: ReviewStatus;
  sharpness: ReviewStatus;
}

export interface RoleAnnotation {
  targetCategory: string;
  targetFrameSha256: string;
  localCaptureId: string;
  localCaptureSha256: string;
  reviewStatus: ReviewStatus;
  featureDecisions: FeatureDecisions;
  notes: string;
}

export interface CategoryApprovals {
  existingHighlightMask: boolean;
  naturalFeatureSignature: boolean;
}

export interface CategoryMetrics {
  centerFaceRatio: number | null;
  opticalShoulderWidthRatio: number | null;
  strongLensRimWidthRatio: number | null;
  sidewallScreenWidthRatio: number | null;
  highlightWidthRatio: number | null;
  highlightCentroidNormalized: NormalizedPoint | null;
  contentBendingWidthRatio: number | null;
  centerRimSharpnessRatio: number | null;
  dispersionWidthRatio: number | null;
  cornerRefractionSignature: [number, number, number, number] | null;
  sidewallContentCompression: number | null;
}

export interface CategoryAnnotation {
  sourceFrameSha256: string;
  reviewStatus: ReviewStatus | "PARTIAL";
  quadReviewStatus: ReviewStatus;
  zoneReviewStatus: ReviewStatus;
  quadNormalized: NormalizedQuad | null;
  zoneBoundaries: ZoneBoundaries;
  approvals: CategoryApprovals;
  metrics: CategoryMetrics;
}

export interface ReviewAnnotations {
  $schema?: string;
  schemaVersion: number;
  referenceClass: string;
  private: true;
  sourceVideoSha256: string;
  evidenceBinding: {
    frozenManifestSha256: string;
    reviewBundleSha256: string;
    reviewAssetSetSha256: string;
    localRuntimeSourceSetSha256: string;
  };
  reviewStatus: ReviewStatus | "PARTIAL";
  reviewer?: string | null;
  reviewedAt?: string | null;
  roleMap?: Record<string, { localCaptureId?: string }>;
  approvals: { brightDarkPairedUse: boolean };
  crossCategoryMetrics?: { brightDarkBackgroundResponseDifference?: number | null };
  categories: Record<string, CategoryAnnotation>;
  roles: Record<RoleId, RoleAnnotation>;
}

export interface AssetEvidence {
  sha256?: string;
  width?: number;
  height?: number;
  bytes?: number;
}

export interface ReviewRoleEvidence {
  id: RoleId;
  label: string;
  targetCategory: string;
  frameReused?: boolean;
  targetFrameSha256?: string;
  localCaptureId?: string;
  localCaptureSha256?: string;
  suggestedQuadNormalized?: NormalizedQuad;
  quadNormalized?: NormalizedQuad;
  suggestedZoneBoundaries?: ZoneBoundaries;
  zoneBoundaries?: ZoneBoundaries;
  assets?: Partial<Record<AssetKind, AssetEvidence | string>>;
}

export interface ReviewEvidence {
  status?: string;
  ready?: boolean;
  sourceVideoSha256: string;
  localHead: string;
  localRuntimeSourceSetSha256: string;
  reviewBundleSha256: string;
  frozenManifestSha256: string;
  reviewAssetSetSha256: string;
  privateOutput: boolean | string;
  failures?: string[];
}

export interface ReviewApiState {
  csrfToken: string;
  etag: string;
  evidence: ReviewEvidence;
  roles: ReviewRoleEvidence[] | Record<RoleId, ReviewRoleEvidence>;
  annotations: ReviewAnnotations;
}

export interface SaveApiResponse {
  etag?: string;
  savedAt?: string;
  annotations?: ReviewAnnotations;
}

export interface ZoneDraft {
  sidewallToStrongLensRim: number;
  strongLensRimToOpticalShoulder: number;
  opticalShoulderToCenterFace: number;
}
