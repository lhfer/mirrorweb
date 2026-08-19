/**
 * Client mirror of scripts/v4/lib/reviewer-state.mjs hashing.
 *
 * The server recomputes this hash and refuses a lock whose hash does not match
 * the geometry it received, so the two implementations must stay byte-for-byte
 * identical: same rounding, same key order, same canonical JSON.
 */

import type { NormalizedQuad } from "../types";
import type { ZoneWidths } from "../zone-model";
import { sha256Hex } from "./api";
import type { EvidenceBinding, ReviewerRoleState } from "./types";

const COORDINATE_PRECISION = 1e6;

export function roundCoordinate(value: number): number {
  return Math.round(value * COORDINATE_PRECISION) / COORDINATE_PRECISION;
}

export function roundQuad(quad: NormalizedQuad): NormalizedQuad {
  return quad.map(([x, y]) => [roundCoordinate(x), roundCoordinate(y)]) as NormalizedQuad;
}

export function roundWidths(widths: ZoneWidths): ZoneWidths {
  return {
    sidewall: roundCoordinate(widths.sidewall),
    strongRim: roundCoordinate(widths.strongRim),
    shoulder: roundCoordinate(widths.shoulder),
  };
}

export function serverBoundaries(widths: ZoneWidths): {
  coordinateSpace: string;
  sidewallOuter: number;
  sidewallToStrongLensRim: number;
  strongLensRimToOpticalShoulder: number;
  opticalShoulderToCenterFace: number;
} {
  const first = widths.sidewall;
  const second = roundCoordinate(first + widths.strongRim);
  return {
    coordinateSpace: "inward-ratio-of-card-minor-axis",
    sidewallOuter: 0,
    sidewallToStrongLensRim: roundCoordinate(first),
    strongLensRimToOpticalShoulder: second,
    opticalShoulderToCenterFace: roundCoordinate(second + widths.shoulder),
  };
}

function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value ?? null);
}

export interface HashContext {
  roleId: string;
  targetCategory: string;
  targetFrameSha256: string;
  sourceVideoSha256: string | null;
  evidenceBinding: EvidenceBinding | null;
}

export function targetAnnotationPayload(context: HashContext, role: ReviewerRoleState): Record<string, unknown> {
  const widths = role.zones.widths ? roundWidths(role.zones.widths) : null;
  return {
    referenceClass: "frozen-visual-human-reviewer",
    schemaVersion: 1,
    roleId: context.roleId,
    targetCategory: context.targetCategory,
    targetFrameSha256: context.targetFrameSha256,
    frameCandidateId: role.frame.candidateId,
    quadNormalized: role.quad.quadNormalized ? roundQuad(role.quad.quadNormalized) : null,
    zoneWidths: widths,
    zoneBoundaries: widths ? serverBoundaries(widths) : null,
    sourceVideoSha256: context.sourceVideoSha256,
    evidenceBinding: context.evidenceBinding,
  };
}

export async function computeTargetAnnotationHash(
  context: HashContext,
  role: ReviewerRoleState,
): Promise<string> {
  const canonical = canonicalJson(targetAnnotationPayload(context, role));
  return sha256Hex(new TextEncoder().encode(canonical));
}
