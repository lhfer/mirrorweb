import type { NormalizedQuad, RoleId } from "../types";
import type { ZoneWidths } from "../zone-model";
import type { Language } from "./i18n";

export const FRAME_REJECT_REASONS = [
  "motion-blur",
  "cursor-occlusion",
  "highlight-occlusion",
  "card-clipped",
  "wrong-role",
  "boundary-unclear",
] as const;

export const COMPARE_VERDICTS = [
  "local-looks-close",
  "local-too-wide",
  "local-too-narrow",
  "wrong-refraction-direction",
  "highlight-mismatch",
  "dispersion-mismatch",
  "needs-later-review",
] as const;

export type FrameRejectReason = (typeof FRAME_REJECT_REASONS)[number];
export type CompareVerdict = (typeof COMPARE_VERDICTS)[number];
export type ReviewerStep = 1 | 2 | 3 | 4 | 5;

export type RoleProgress =
  | "PENDING_FRAME"
  | "PENDING_QUAD"
  | "PENDING_ZONES"
  | "PENDING_LOCK"
  | "TARGET_LOCKED"
  | "REJECTED";

export interface EvidenceBinding {
  frozenManifestSha256: string;
  reviewBundleSha256: string;
  reviewAssetSetSha256: string;
  localRuntimeSourceSetSha256: string;
}

export interface ReviewerRoleState {
  step: ReviewerStep;
  frame: {
    status: "PENDING" | "ACCEPTED" | "REJECTED";
    candidateId: string | null;
    rejectionReasons: FrameRejectReason[];
    note: string;
  };
  quad: { status: "PENDING" | "ACCEPTED"; quadNormalized: NormalizedQuad | null };
  zones: { status: "PENDING" | "ACCEPTED" | "UNCLEAR"; widths: ZoneWidths | null };
  lock: {
    status: "UNLOCKED" | "LOCKED";
    targetAnnotationSha256: string | null;
    lockedAt: string | null;
    unlockCount: number;
    unlockReason: string;
  };
  compare: { verdicts: CompareVerdict[]; note: string };
  updatedAt: string | null;
}

export interface ReviewerState {
  schemaVersion: 1;
  referenceClass: "frozen-visual-human-reviewer";
  private: true;
  sourceVideoSha256: string | null;
  evidenceBinding: EvidenceBinding | null;
  language: Language;
  tutorialAcknowledged: boolean;
  activeRoleId: RoleId | null;
  roles: Record<RoleId, ReviewerRoleState>;
  updatedAt: string | null;
}

export interface CandidateFrame {
  id: string;
  frameIndex: number;
  primary: boolean;
  offsetFromSelected: number;
  width: number;
  height: number;
  sha256: string;
  thumbnailSha256: string;
  url: string;
  thumbnailUrl: string;
}

export interface ReviewerRoleEvidence {
  id: RoleId;
  label: string;
  targetCategory: string;
  frameReused?: boolean;
  targetFrameSha256: string;
  localCaptureId: string;
  localCaptureSha256: string;
  suggestedQuadNormalized: NormalizedQuad | null;
  candidates: CandidateFrame[];
  assets: Record<string, { url: string; sha256: string }>;
}

export interface ReviewerApiPayload {
  csrfToken: string;
  etag: string;
  evidence: Record<string, unknown> & {
    sourceVideoSha256: string;
    localHead: string;
    privateOutputPath: string;
    reviewerStatePath: string;
    candidateFrameCount: number;
  };
  roles: ReviewerRoleEvidence[];
  state: ReviewerState;
}
