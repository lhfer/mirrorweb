/**
 * Optical-zone geometry expressed as three band WIDTHS instead of three
 * cumulative boundaries.
 *
 * The private annotation contract stores cumulative inward distances
 * (`0 < sidewall < strongRim < shoulder < 0.5`). Editing those three numbers
 * independently makes an illegal ordering representable, which is exactly how
 * the review page could display `Shoulder = 0%` while the sliders still held
 * cumulative values and the validator reported an ordering failure.
 *
 * Widths make the illegal state unrepresentable: every band is clamped to a
 * positive minimum and the accumulated total is clamped below the card half
 * size, so any conversion back to cumulative boundaries is ordered by
 * construction. Nothing in the UI can produce a state the validator rejects.
 */

export interface ZoneWidths {
  /** Outermost band: sidewall / reflective side of the card. */
  sidewall: number;
  /** Strong lens rim: fast compression, folding and local dispersion. */
  strongRim: number;
  /** Optical shoulder: content starts bending slowly. */
  shoulder: number;
}

export interface ZoneBoundaryValues {
  sidewallToStrongLensRim: number;
  strongLensRimToOpticalShoulder: number;
  opticalShoulderToCenterFace: number;
}

/** Smallest band a human can mark; keeps every band visible and ordered. */
export const MIN_BAND_WIDTH = 0.002;
/** Largest total inward distance; guarantees a real center face remains. */
export const MAX_TOTAL_INWARD = 0.46;
/** Provisional prior from the automatic extraction, never target truth. */
export const SUGGESTED_ZONE_WIDTHS: Readonly<ZoneWidths> = Object.freeze({
  sidewall: 0.012,
  strongRim: 0.053,
  shoulder: 0.08,
});

export const ZONE_KEYS = ["sidewall", "strongRim", "shoulder"] as const;
export type ZoneKey = (typeof ZONE_KEYS)[number];

function finite(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

/**
 * Returns a legal `ZoneWidths` for any input, including NaN, negative and
 * oversized values. This is the only constructor the UI is allowed to use.
 */
export function clampZoneWidths(input: Partial<ZoneWidths> | null | undefined): ZoneWidths {
  const raw: ZoneWidths = {
    sidewall: Math.max(MIN_BAND_WIDTH, finite(input?.sidewall, SUGGESTED_ZONE_WIDTHS.sidewall)),
    strongRim: Math.max(MIN_BAND_WIDTH, finite(input?.strongRim, SUGGESTED_ZONE_WIDTHS.strongRim)),
    shoulder: Math.max(MIN_BAND_WIDTH, finite(input?.shoulder, SUGGESTED_ZONE_WIDTHS.shoulder)),
  };
  const total = raw.sidewall + raw.strongRim + raw.shoulder;
  if (total <= MAX_TOTAL_INWARD) return raw;
  // Shrink proportionally, then re-apply the per-band floor so the ordering
  // survives even when the requested total is far too large.
  const scale = (MAX_TOTAL_INWARD - MIN_BAND_WIDTH * 3) / (total - MIN_BAND_WIDTH * 3);
  return {
    sidewall: MIN_BAND_WIDTH + (raw.sidewall - MIN_BAND_WIDTH) * scale,
    strongRim: MIN_BAND_WIDTH + (raw.strongRim - MIN_BAND_WIDTH) * scale,
    shoulder: MIN_BAND_WIDTH + (raw.shoulder - MIN_BAND_WIDTH) * scale,
  };
}

/** Cumulative inward boundaries, ordered by construction. */
export function boundariesFromWidths(widths: ZoneWidths): ZoneBoundaryValues {
  const safe = clampZoneWidths(widths);
  const first = safe.sidewall;
  const second = first + safe.strongRim;
  return {
    sidewallToStrongLensRim: first,
    strongLensRimToOpticalShoulder: second,
    opticalShoulderToCenterFace: second + safe.shoulder,
  };
}

export function widthsFromBoundaries(values: Partial<ZoneBoundaryValues> | null | undefined): ZoneWidths {
  const first = finite(values?.sidewallToStrongLensRim, SUGGESTED_ZONE_WIDTHS.sidewall);
  const second = finite(
    values?.strongLensRimToOpticalShoulder,
    first + SUGGESTED_ZONE_WIDTHS.strongRim,
  );
  const third = finite(values?.opticalShoulderToCenterFace, second + SUGGESTED_ZONE_WIDTHS.shoulder);
  return clampZoneWidths({
    sidewall: first,
    strongRim: second - first,
    shoulder: third - second,
  });
}

/**
 * Moves one cumulative boundary to `nextValue` and returns legal widths.
 * Used by the direct on-card drag interaction: the dragged boundary is bounded
 * by its neighbours instead of being allowed to cross them.
 */
export function withBoundaryAt(
  widths: ZoneWidths,
  boundary: 0 | 1 | 2,
  nextValue: number,
): ZoneWidths {
  const safe = clampZoneWidths(widths);
  const current = boundariesFromWidths(safe);
  const value = finite(nextValue, 0);
  if (boundary === 0) {
    const upper = current.strongLensRimToOpticalShoulder - MIN_BAND_WIDTH;
    const sidewall = Math.min(Math.max(value, MIN_BAND_WIDTH), Math.max(MIN_BAND_WIDTH, upper));
    return clampZoneWidths({
      sidewall,
      strongRim: current.strongLensRimToOpticalShoulder - sidewall,
      shoulder: safe.shoulder,
    });
  }
  if (boundary === 1) {
    const lower = current.sidewallToStrongLensRim + MIN_BAND_WIDTH;
    const upper = current.opticalShoulderToCenterFace - MIN_BAND_WIDTH;
    const second = Math.min(Math.max(value, lower), Math.max(lower, upper));
    return clampZoneWidths({
      sidewall: safe.sidewall,
      strongRim: second - current.sidewallToStrongLensRim,
      shoulder: current.opticalShoulderToCenterFace - second,
    });
  }
  const lower = current.strongLensRimToOpticalShoulder + MIN_BAND_WIDTH;
  const third = Math.min(Math.max(value, lower), Math.max(lower, MAX_TOTAL_INWARD));
  return clampZoneWidths({
    sidewall: safe.sidewall,
    strongRim: safe.strongRim,
    shoulder: third - current.strongLensRimToOpticalShoulder,
  });
}

/** Half-extent of the remaining center face, as a ratio of the minor axis. */
export function centerFaceHalfExtent(widths: ZoneWidths): number {
  return Math.max(0, 0.5 - boundariesFromWidths(widths).opticalShoulderToCenterFace);
}

export function zoneWidthsEqual(left: ZoneWidths, right: ZoneWidths, epsilon = 1e-9): boolean {
  return ZONE_KEYS.every((key) => Math.abs(left[key] - right[key]) <= epsilon);
}

/** True only for a strictly ordered, in-range cumulative boundary triple. */
export function boundariesAreOrdered(values: Partial<ZoneBoundaryValues> | null | undefined): boolean {
  const first = values?.sidewallToStrongLensRim;
  const second = values?.strongLensRimToOpticalShoulder;
  const third = values?.opticalShoulderToCenterFace;
  return [first, second, third].every((value) => typeof value === "number" && Number.isFinite(value))
    && 0 < (first as number)
    && (first as number) < (second as number)
    && (second as number) < (third as number)
    && (third as number) < 0.5;
}
