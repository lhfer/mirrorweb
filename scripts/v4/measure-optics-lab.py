#!/usr/bin/env python3
"""Measure deterministic Phase-1 optics-lab captures.

The input is the local manifest emitted by capture-optics-lab.mjs. PNG evidence
remains ignored/private; the output contains only hashes, aggregate metrics and
explicit caveats. These measurements are structural diagnostics, not a claim of
pixel equivalence to the private Frozen Visual Golden.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage, signal as scipy_signal


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "qa-v4/results/optics-lab-foundation.capture.local.json"
DEFAULT_OUTPUT = REPO_ROOT / "qa-v4/results/optics-lab-foundation.json"
DEFAULT_ARTIFACT_DIR = REPO_ROOT / "qa-v4/results/optics-lab-foundation-artifacts"
GENERATOR = "optics-lab-measure-v1"
REQUIRED_CAPTURE_IDS = {
    "split-checker",
    "difference-checker",
    "edge-mask-black",
    "v4-checker",
    "v4-horizontal-lines",
    "v4-vertical-lines",
    "v4-white",
    "v4-black",
    "dispersion-checker",
}
THRESHOLDS = {
    "centerToRimSharpnessRatioMin": 1.0,
    "rimWidthNormalizedMin": 0.015,
    "rimWidthNormalizedMax": 0.25,
    "lineCoverageMin": 0.80,
    "lineContinuityScoreMin": 0.70,
    "lineOuterDisplacementPxMin": 1.5,
    "cornerContinuityScoreMin": 0.40,
    "highlightTravelNormalizedMin": 0.03,
    "highlightJumpRatioMax": 3.5,
    "dispersionOuterZoneRatioMin": 0.90,
    "flatBackgroundDiscernibilityMin": 0.015,
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def finite(value: float | np.floating[Any]) -> float | None:
    result = float(value)
    return result if math.isfinite(result) else None


def safe_repository_file(value: str) -> Path:
    candidate = (REPO_ROOT / value).resolve()
    if REPO_ROOT not in candidate.parents:
        raise ValueError(f"Evidence path escapes repository: {value}")
    return candidate


def load_rgb(entry: dict[str, Any]) -> np.ndarray:
    file = safe_repository_file(entry["file"])
    if not file.is_file():
        raise FileNotFoundError(f"Missing capture: {entry['file']}")
    actual_hash = sha256_file(file)
    if actual_hash != entry.get("sha256"):
        raise ValueError(f"Capture hash mismatch: {entry['file']}")
    return np.asarray(Image.open(file).convert("RGB"), dtype=np.float32) / 255.0


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def largest_component(mask: np.ndarray) -> np.ndarray:
    labels, count = ndimage.label(mask)
    if count == 0:
        return np.zeros_like(mask, dtype=bool)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return labels == int(np.argmax(sizes))


def bbox_of(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError("No card silhouette found in edge-mask capture")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def build_zones(edge_rgb: np.ndarray) -> dict[str, Any]:
    gray = luminance(edge_rgb)
    chroma = edge_rgb.max(axis=2) - edge_rgb.min(axis=2)
    border = np.concatenate((gray[0], gray[-1], gray[:, 0], gray[:, -1]))
    baseline = float(np.median(border))
    # The debug contract renders optical zones in chromatic false color over a
    # grayscale pattern. Chroma is therefore a much safer silhouette cue than
    # luminance: a checker tile must never be mistaken for the glass body.
    if float(np.percentile(chroma, 90)) >= 0.08:
        signal = chroma
        signal_kind = "false-color-chroma"
    else:
        signal = np.abs(gray - baseline)
        signal_kind = "luminance-fallback"
    positive = signal[signal > max(0.01, float(np.percentile(signal, 65)))]
    if positive.size == 0:
        raise ValueError("Edge-mask capture contains no separable optical-zone signal")
    threshold = max(0.025, float(np.percentile(positive, 35)) * 0.55)
    seed = signal >= threshold
    seed = ndimage.binary_closing(seed, iterations=2)
    seed = largest_component(seed)
    silhouette = ndimage.binary_fill_holes(seed)
    silhouette = ndimage.binary_closing(silhouette, iterations=3)
    x0, y0, x1, y1 = bbox_of(silhouette)
    box_width, box_height = x1 - x0, y1 - y0
    image_height, image_width = gray.shape
    area_ratio = float(silhouette.mean())
    touches_frame = x0 <= image_width * 0.01 or y0 <= image_height * 0.01 \
        or x1 >= image_width * 0.99 or y1 >= image_height * 0.99
    if (
        box_width < image_width * 0.22
        or box_height < image_height * 0.22
        or box_width > image_width * 0.92
        or box_height > image_height * 0.92
        or area_ratio < 0.10
        or area_ratio > 0.78
        or touches_frame
    ):
        raise ValueError("Edge-mask silhouette is implausible; capture/debug contract requires review")

    distance = ndimage.distance_transform_edt(silhouette)
    center_region = silhouette & (distance >= max(2.0, float(distance.max()) * 0.36))
    center_signal = float(np.median(signal[center_region])) if center_region.any() else baseline
    high = float(np.percentile(signal[silhouette], 92))
    rim_threshold = center_signal + max(0.015, (high - center_signal) * 0.32)
    rim_seed = silhouette & (signal >= rim_threshold)
    rim_seed &= distance <= max(3.0, float(distance.max()) * 0.48)
    rim_seed = ndimage.binary_closing(rim_seed, iterations=1)
    if rim_seed.sum() < max(32, silhouette.sum() * 0.003):
        raise ValueError("Edge-mask did not expose a measurable rim zone")

    rim_depth = distance[rim_seed]
    rim_width_px = float(np.percentile(rim_depth, 92))
    outer_zone = silhouette & (distance <= max(2.0, rim_width_px * 1.35))
    center_face = silhouette & (distance >= max(rim_width_px * 2.0, float(distance.max()) * 0.42))
    if center_face.sum() < silhouette.sum() * 0.08:
        center_face = center_region
    perimeter = silhouette & ~ndimage.binary_erosion(silhouette, iterations=1)
    gutter = ndimage.binary_dilation(silhouette, iterations=max(2, round(rim_width_px * 0.5))) & ~silhouette

    return {
        "silhouette": silhouette,
        "rim": rim_seed,
        "outer": outer_zone,
        "center": center_face,
        "perimeter": perimeter,
        "gutter": gutter,
        "distance": distance,
        "bbox": (x0, y0, x1, y1),
        "rimWidthPx": rim_width_px,
        "rimWidthNormalized": rim_width_px / min(box_width, box_height),
        "silhouetteAreaRatio": area_ratio,
        "edgeMaskThreshold": threshold,
        "edgeMaskSignal": signal_kind,
    }


def gradient_energy(gray: np.ndarray) -> np.ndarray:
    gx = ndimage.sobel(gray, axis=1, mode="reflect") / 8.0
    gy = ndimage.sobel(gray, axis=0, mode="reflect") / 8.0
    laplacian = ndimage.laplace(gray, mode="reflect")
    return np.sqrt(gx * gx + gy * gy) + np.abs(laplacian) * 0.35


def sharpness_metrics(rgb: np.ndarray, zones: dict[str, Any]) -> dict[str, Any]:
    energy = gradient_energy(luminance(rgb))
    center_values = energy[zones["center"]]
    rim_values = energy[zones["outer"]]
    center = float(np.sqrt(np.mean(center_values * center_values))) if center_values.size else 0.0
    rim = float(np.sqrt(np.mean(rim_values * rim_values))) if rim_values.size else 0.0
    return {
        "method": "RMS Sobel plus Laplacian energy on display-encoded deterministic checker capture",
        "center": center,
        "rim": rim,
        "centerToRimRatio": center / max(rim, 1e-9),
        "centerSampleCount": int(center_values.size),
        "rimSampleCount": int(rim_values.size),
    }


def reference_line_peaks(
    rgb: np.ndarray,
    zones: dict[str, Any],
    orientation: str,
) -> tuple[np.ndarray, float]:
    """Find un-refracted black-line centers in the gutters around the card."""
    x0, y0, x1, y1 = zones["bbox"]
    image_height, image_width = rgb.shape[:2]
    if orientation == "horizontal":
        margin = max(8, round((x1 - x0) * 0.025))
        strips = []
        if x0 > margin * 2:
            strips.append(rgb[:, max(0, x0 - margin * 3):x0 - margin])
        if image_width - x1 > margin * 2:
            strips.append(rgb[:, x1 + margin:min(image_width, x1 + margin * 3)])
        profile_start, profile_end = y0, y1
        if not strips:
            raise ValueError("Horizontal-line capture has no clean side gutter")
        reference_rgb = np.median(np.concatenate(strips, axis=1), axis=1)
    else:
        margin = max(8, round((y1 - y0) * 0.025))
        strips = []
        if y0 > margin * 2:
            strips.append(rgb[max(0, y0 - margin * 3):y0 - margin, :])
        if image_height - y1 > margin * 2:
            strips.append(rgb[y1 + margin:min(image_height, y1 + margin * 3), :])
        profile_start, profile_end = x0, x1
        if not strips:
            raise ValueError("Vertical-line capture has no clean top/bottom gutter")
        reference_rgb = np.median(np.concatenate(strips, axis=0), axis=0)

    reference_gray = luminance(reference_rgb)
    reference_chroma = reference_rgb.max(axis=1) - reference_rgb.min(axis=1)
    darkness = ndimage.gaussian_filter1d(1.0 - reference_gray, sigma=0.7)
    peaks, properties = scipy_signal.find_peaks(
        darkness,
        distance=6,
        prominence=0.12,
        height=0.28,
    )
    # The deterministic pattern contains one red optical axis. It is not a
    # black grid line and must not enter displacement matching.
    peaks = np.asarray([
        int(peak) for peak in peaks
        if profile_start + 2 <= peak < profile_end - 2 and reference_chroma[peak] < 0.08
    ], dtype=int)
    if peaks.size < 6:
        raise ValueError(f"Only {peaks.size} reference {orientation} lines were detected")

    spacing = float(np.median(np.diff(peaks)))
    # Remove an occasional label/text peak that violates the regular test-grid
    # cadence. This does not move any retained reference line.
    keep = np.ones(peaks.size, dtype=bool)
    for index in range(1, peaks.size):
        if peaks[index] - peaks[index - 1] < spacing * 0.58:
            left_height = float(darkness[peaks[index - 1]])
            right_height = float(darkness[peaks[index]])
            keep[index if left_height >= right_height else index - 1] = False
    peaks = peaks[keep]
    if peaks.size < 6 or spacing < 5:
        raise ValueError(f"Reference {orientation} line cadence is not measurable")
    refined = []
    for peak in peaks:
        y0_value, y1_value, y2_value = (float(darkness[peak - 1]), float(darkness[peak]), float(darkness[peak + 1]))
        denominator = y0_value - 2.0 * y1_value + y2_value
        offset = 0.5 * (y0_value - y2_value) / denominator if abs(denominator) > 1e-9 else 0.0
        refined.append(float(peak) + max(-0.5, min(0.5, offset)))
    return np.asarray(refined, dtype=float), spacing


def local_line_peak(profile: np.ndarray, expected: float, radius: int) -> tuple[float, float] | None:
    darkness = ndimage.gaussian_filter1d(1.0 - profile, sigma=0.7)
    expected_index = int(round(expected))
    left = max(1, expected_index - radius)
    right = min(profile.size - 1, expected_index + radius + 1)
    if right - left < 3:
        return None
    segment = darkness[left:right]
    local_index = int(np.argmax(segment))
    index = left + local_index
    peak_value = float(darkness[index])
    contrast = peak_value - float(np.percentile(segment, 20))
    if peak_value < 0.22 or contrast < 0.055:
        return None
    # Quadratic interpolation keeps sub-pixel antialiasing changes from
    # quantizing a real, slowly bending line to an all-zero displacement.
    y0, y1, y2 = (float(darkness[index - 1]), peak_value, float(darkness[index + 1]))
    denominator = y0 - 2.0 * y1 + y2
    offset = 0.5 * (y0 - y2) / denominator if abs(denominator) > 1e-9 else 0.0
    offset = max(-0.5, min(0.5, offset))
    return index + offset, contrast


def line_displacement_metrics(rgb: np.ndarray, zones: dict[str, Any], orientation: str) -> dict[str, Any]:
    gray = luminance(rgb)
    x0, y0, x1, y1 = zones["bbox"]
    reference_peaks, line_spacing = reference_line_peaks(rgb, zones, orientation)
    if orientation == "horizontal":
        longitudinal_start, longitudinal_end = x0, x1
        profile_start, profile_end = y0, y1
        get_profile = lambda coordinate: np.median(  # noqa: E731
            gray[:, max(0, coordinate - 2):min(gray.shape[1], coordinate + 3)], axis=1
        )
        get_mask = lambda coordinate: zones["silhouette"][:, coordinate]  # noqa: E731
    else:
        longitudinal_start, longitudinal_end = y0, y1
        profile_start, profile_end = x0, x1
        get_profile = lambda coordinate: np.median(  # noqa: E731
            gray[max(0, coordinate - 2):min(gray.shape[0], coordinate + 3), :], axis=0
        )
        get_mask = lambda coordinate: zones["silhouette"][coordinate, :]  # noqa: E731

    span = longitudinal_end - longitudinal_start
    coordinates = np.linspace(longitudinal_start + span * 0.035, longitudinal_end - span * 0.035, 39).astype(int)
    radius = max(3, int(math.floor(line_spacing * 0.44)))
    profile_center = (profile_start + profile_end) * 0.5
    profile_half_span = max(1.0, (profile_end - profile_start) * 0.5)
    samples: list[dict[str, Any]] = []
    line_curves: dict[int, list[tuple[float, float]]] = {index: [] for index in range(reference_peaks.size)}
    outer_line_displacements: list[float] = []
    total_possible_matches = 0
    total_line_matches = 0
    for coordinate in coordinates:
        profile = get_profile(int(coordinate))
        profile_mask = get_mask(int(coordinate))
        displacements: list[float] = []
        positions: list[float] = []
        contrasts: list[float] = []
        possible = 0
        for peak_index, peak in enumerate(reference_peaks):
            expected_index = int(round(float(peak)))
            search_left = max(0, expected_index - radius)
            search_right = min(profile_mask.size, expected_index + radius + 1)
            if not profile_mask[search_left:search_right].any():
                continue
            possible += 1
            match = local_line_peak(profile, float(peak), radius)
            if match is None:
                continue
            measured_position, contrast = match
            displacement = measured_position - float(peak)
            if abs(displacement) > radius + 0.51:
                continue
            displacements.append(displacement)
            positions.append((float(peak) - profile_center) / profile_half_span)
            contrasts.append(contrast)
            normalized_longitudinal = (float(coordinate) - longitudinal_start) / max(span, 1)
            line_curves[peak_index].append((normalized_longitudinal, displacement))
            if abs(positions[-1]) >= 0.55:
                outer_line_displacements.append(abs(displacement))
        total_possible_matches += possible
        total_line_matches += len(displacements)
        if len(displacements) < 4:
            continue
        line_positions = np.asarray(positions)
        line_displacements = np.asarray(displacements)
        upper = line_displacements[line_positions <= -0.18]
        lower = line_displacements[line_positions >= 0.18]
        outer_lines = np.abs(line_positions) >= 0.55
        upper_median = float(np.median(upper)) if upper.size else None
        lower_median = float(np.median(lower)) if lower.size else None
        symmetric_compression = (
            abs(upper_median - lower_median) * 0.5
            if upper_median is not None and lower_median is not None
            else 0.0
        )
        regression_slope = float(np.polyfit(line_positions, line_displacements, 1)[0])
        samples.append({
            "position": (float(coordinate) - longitudinal_start) / max(span, 1),
            "matchedLineCount": len(displacements),
            "possibleLineCount": possible,
            "matchCoverage": len(displacements) / max(possible, 1),
            "medianPeakContrast": float(np.median(contrasts)),
            "medianAbsoluteDisplacementPx": float(np.median(np.abs(line_displacements))),
            "p90AbsoluteDisplacementPx": float(np.percentile(np.abs(line_displacements), 90)),
            "outerLineP90AbsoluteDisplacementPx": (
                float(np.percentile(np.abs(line_displacements[outer_lines]), 90)) if outer_lines.any() else None
            ),
            "upperMedianShiftPx": upper_median,
            "lowerMedianShiftPx": lower_median,
            "symmetricCompressionPx": symmetric_compression,
            "displacementSlopePx": regression_slope,
        })

    profile_coverage = len(samples) / len(coordinates)
    match_coverage = total_line_matches / max(total_possible_matches, 1)
    coverage = min(profile_coverage, match_coverage)
    samples.sort(key=lambda sample: sample["position"])
    side_deltas: list[float] = []
    side_metrics: dict[str, Any] = {}
    for side, predicate in {
        "leading": lambda value: value <= 0.5,
        "trailing": lambda value: value >= 0.5,
    }.items():
        side_samples = [sample for sample in samples if predicate(sample["position"])]
        side_samples.sort(key=lambda sample: abs(sample["position"] - 0.5), reverse=True)
        values = [sample["symmetricCompressionPx"] for sample in side_samples]
        side_deltas.extend(abs(right - left) for left, right in zip(values, values[1:]))
        outer = [sample for sample in side_samples if sample["position"] <= 0.20 or sample["position"] >= 0.80]
        side_metrics[side] = {
            "sampleCount": len(side_samples),
            "outerMedianAbsoluteDisplacementPx": (
                float(np.median([sample["medianAbsoluteDisplacementPx"] for sample in outer])) if outer else None
            ),
            "outerMedianSymmetricCompressionPx": (
                float(np.median([sample["symmetricCompressionPx"] for sample in outer])) if outer else None
            ),
        }
    p95_jump = float(np.percentile(side_deltas, 95)) if side_deltas else float("inf")
    continuity = max(0.0, 1.0 - p95_jump / max(2.0, line_spacing * 0.35)) if math.isfinite(p95_jump) else 0.0
    outer_samples = [sample for sample in samples if sample["position"] <= 0.20 or sample["position"] >= 0.80]
    outer_displacement = float(np.percentile(outer_line_displacements, 90)) if outer_line_displacements else None
    outer_compression = (
        float(np.median([sample["symmetricCompressionPx"] for sample in outer_samples]))
        if outer_samples else None
    )
    outer_curve_bending = []
    for peak_index, curve in line_curves.items():
        normalized_profile_position = (float(reference_peaks[peak_index]) - profile_center) / profile_half_span
        if abs(normalized_profile_position) < 0.55 or len(curve) < 5:
            continue
        values = np.asarray([displacement for _, displacement in curve])
        outer_curve_bending.append(float(np.percentile(values, 90) - np.percentile(values, 10)))
    bending_p90 = float(np.percentile(outer_curve_bending, 90)) if outer_curve_bending else None
    effective_outer_displacement = max(
        outer_displacement if outer_displacement is not None else 0.0,
        outer_compression if outer_compression is not None else 0.0,
        bending_p90 if bending_p90 is not None else 0.0,
    )
    return {
        "orientation": orientation,
        "method": "per-line gutter peak matching with leading/trailing half-zone continuity and signed symmetric compression",
        "sampleCount": len(samples),
        "expectedSampleCount": len(coordinates),
        "referenceLineCount": int(reference_peaks.size),
        "lineSpacingPx": line_spacing,
        "lineMatchCount": total_line_matches,
        "possibleLineMatchCount": total_possible_matches,
        "coverage": coverage,
        "profileCoverage": profile_coverage,
        "lineMatchCoverage": match_coverage,
        "p95AdjacentShiftJumpPx": finite(p95_jump),
        "continuityScore": continuity,
        "outerEdgeDisplacementPx": outer_displacement,
        "outerSymmetricCompressionPx": outer_compression,
        "outerLineBendingP90Px": bending_p90,
        "effectiveOuterDisplacementPx": effective_outer_displacement,
        "maxAbsoluteDisplacementPx": max((sample["p90AbsoluteDisplacementPx"] for sample in samples), default=None),
        "sideMetrics": side_metrics,
        "samples": samples,
    }


def corner_continuity_metrics(edge_rgb: np.ndarray, zones: dict[str, Any]) -> dict[str, Any]:
    signal = luminance(edge_rgb)
    x0, y0, x1, y1 = zones["bbox"]
    width, height = x1 - x0, y1 - y0
    patch_width, patch_height = max(3, round(width * 0.22)), max(3, round(height * 0.22))
    patches = {
        "topLeft": (x0, y0, x0 + patch_width, y0 + patch_height),
        "topRight": (x1 - patch_width, y0, x1, y0 + patch_height),
        "bottomLeft": (x0, y1 - patch_height, x0 + patch_width, y1),
        "bottomRight": (x1 - patch_width, y1 - patch_height, x1, y1),
    }
    corner_values: dict[str, dict[str, float]] = {}
    energies = []
    coverages = []
    for name, (left, top, right, bottom) in patches.items():
        ring = zones["outer"][top:bottom, left:right]
        patch = signal[top:bottom, left:right]
        energy = float(np.mean(patch[ring])) if ring.any() else 0.0
        coverage = float(ring.mean())
        energies.append(energy)
        coverages.append(coverage)
        corner_values[name] = {"meanEdgeSignal": energy, "outerZoneCoverage": coverage}
    energy_ratio = min(energies) / max(max(energies), 1e-9)
    coverage_ratio = min(coverages) / max(max(coverages), 1e-9)
    labels, count = ndimage.label(zones["outer"])
    component_fraction = 0.0
    if count:
        sizes = np.bincount(labels.ravel())
        sizes[0] = 0
        component_fraction = float(sizes.max() / max(zones["outer"].sum(), 1))
    return {
        "method": "four-corner outer-zone signal and connected-ring coverage",
        "score": min(energy_ratio, coverage_ratio, component_fraction),
        "edgeSignalBalance": energy_ratio,
        "coverageBalance": coverage_ratio,
        "largestConnectedOuterZoneFraction": component_fraction,
        "corners": corner_values,
    }


def highlight_centroid(rgb: np.ndarray, zones: dict[str, Any]) -> tuple[float, float] | None:
    gray = luminance(rgb)
    values = gray[zones["silhouette"]]
    if not values.size:
        return None
    threshold = max(float(np.percentile(values, 92)), float(np.median(values)) + 0.025)
    weights = np.clip(gray - threshold, 0.0, None) * zones["silhouette"]
    total = float(weights.sum())
    if total <= 1e-7:
        return None
    yy, xx = np.indices(gray.shape)
    return float((xx * weights).sum() / total), float((yy * weights).sum() / total)


def highlight_path_metrics(pointer_entries: list[dict[str, Any]], zones: dict[str, Any]) -> dict[str, Any]:
    x0, y0, x1, y1 = zones["bbox"]
    width, height = max(1, x1 - x0), max(1, y1 - y0)
    samples = []
    for entry in pointer_entries:
        centroid = highlight_centroid(load_rgb(entry), zones)
        normalized = None if centroid is None else [
            (centroid[0] - x0) / width,
            (centroid[1] - y0) / height,
        ]
        samples.append({
            "pointer": entry.get("pointer"),
            "centroidPx": list(centroid) if centroid else None,
            "centroidNormalized": normalized,
            "screenshotSha256": entry["sha256"],
        })
    valid = [sample for sample in samples if sample["centroidNormalized"] is not None]
    segments = []
    for left, right in zip(valid, valid[1:]):
        a = np.asarray(left["centroidNormalized"], dtype=float)
        b = np.asarray(right["centroidNormalized"], dtype=float)
        segments.append(float(np.linalg.norm(b - a)))
    travel = float(sum(segments))
    median_segment = float(np.median(segments)) if segments else 0.0
    jump_ratio = max(segments, default=0.0) / max(median_segment, 1e-9) if segments else None
    pointer_x = np.asarray([sample["pointer"][0] for sample in valid], dtype=float) if valid else np.asarray([])
    centroid_x = np.asarray([sample["centroidNormalized"][0] for sample in valid], dtype=float) if valid else np.asarray([])
    response_correlation = None
    if len(valid) >= 3 and np.std(pointer_x) > 1e-6 and np.std(centroid_x) > 1e-6:
        response_correlation = float(np.corrcoef(pointer_x, centroid_x)[0, 1])
    return {
        "method": "bright reflection-energy centroid inside the measured card silhouette",
        "requestedSampleCount": len(pointer_entries),
        "validSampleCount": len(valid),
        "travelNormalized": travel,
        "medianSegmentNormalized": median_segment,
        "maxJumpNormalized": max(segments, default=None),
        "maxToMedianJumpRatio": finite(jump_ratio) if jump_ratio is not None else None,
        "pointerXToCentroidXCorrelation": finite(response_correlation) if response_correlation is not None else None,
        "samples": samples,
    }


def dispersion_metrics(rgb: np.ndarray, zones: dict[str, Any]) -> dict[str, Any]:
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    chroma = np.clip(chroma - float(np.percentile(chroma[~zones["silhouette"]], 75)) if (~zones["silhouette"]).any() else chroma, 0.0, None)
    total = float(chroma[zones["silhouette"]].sum())
    outer = float(chroma[zones["outer"]].sum())
    return {
        "method": "display-encoded RGB range energy inside measured silhouette",
        "totalEnergy": total,
        "outerZoneEnergy": outer,
        "outerZoneRatio": outer / total if total > 1e-9 else None,
        "energyPresent": total > 1e-6,
    }


def flat_background_metrics(rgb: np.ndarray, zones: dict[str, Any], background: str) -> dict[str, Any]:
    gray = luminance(rgb)
    ring = gray[zones["outer"]]
    center = gray[zones["center"]]
    gutter = gray[zones["gutter"]]
    if not ring.size or not gutter.size:
        return {"background": background, "discernibilityScore": 0.0, "measurable": False}
    rim_gutter = abs(float(np.mean(ring)) - float(np.mean(gutter)))
    center_gutter = abs(float(np.mean(center)) - float(np.mean(gutter))) if center.size else 0.0
    boundary_gradient = gradient_energy(gray)[ndimage.binary_dilation(zones["perimeter"], iterations=2)]
    boundary_score = float(np.percentile(boundary_gradient, 75)) if boundary_gradient.size else 0.0
    return {
        "background": background,
        "method": "maximum of rim/gutter contrast, center/gutter contrast and boundary-gradient energy",
        "discernibilityScore": max(rim_gutter, center_gutter, boundary_score),
        "rimToGutterLumaDifference": rim_gutter,
        "centerToGutterLumaDifference": center_gutter,
        "boundaryGradientP75": boundary_score,
        "measurable": True,
    }


def difference_metrics(rgb: np.ndarray) -> dict[str, Any]:
    gray = luminance(rgb)
    border = np.concatenate((gray[0], gray[-1], gray[:, 0], gray[:, -1]))
    baseline = float(np.median(border))
    magnitude = np.abs(gray - baseline)
    return {
        "method": "display-encoded difference-view energy relative to border baseline",
        "meanAbsoluteLuma": float(magnitude.mean()),
        "p95AbsoluteLuma": float(np.percentile(magnitude, 95)),
        "nontrivialPixelRatio": float((magnitude > 2 / 255).mean()),
    }


def svg_polyline(points: list[tuple[float, float]], color: str, width: float = 2.5) -> str:
    if not points:
        return ""
    coordinates = " ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    return (
        f'<polyline points="{coordinates}" fill="none" stroke="{color}" '
        f'stroke-width="{width:.1f}" stroke-linejoin="round" stroke-linecap="round"/>'
    )


def displacement_plot_svg(line_metrics: dict[str, Any]) -> str:
    width, height = 960, 560
    panels = []
    all_values = []
    for orientation in ("horizontal", "vertical"):
        for sample in line_metrics[orientation]["samples"]:
            all_values.extend([
                sample["outerLineP90AbsoluteDisplacementPx"] or 0.0,
                sample["symmetricCompressionPx"],
            ])
        all_values.append(line_metrics[orientation]["effectiveOuterDisplacementPx"])
    y_max = max(THRESHOLDS["lineOuterDisplacementPxMin"] * 1.35, max(all_values, default=1.0) * 1.12)
    plot_left, plot_right = 76.0, width - 34.0
    panel_height = 188.0
    for panel_index, orientation in enumerate(("horizontal", "vertical")):
        top = 84.0 + panel_index * 238.0
        bottom = top + panel_height
        samples = line_metrics[orientation]["samples"]

        def point(sample: dict[str, Any], key: str) -> tuple[float, float]:
            x = plot_left + float(sample["position"]) * (plot_right - plot_left)
            raw_value = sample.get(key)
            value = min(y_max, max(0.0, float(raw_value) if raw_value is not None else 0.0))
            y = bottom - value / y_max * panel_height
            return x, y

        displacement = [point(sample, "outerLineP90AbsoluteDisplacementPx") for sample in samples]
        compression = [point(sample, "symmetricCompressionPx") for sample in samples]
        threshold_y = bottom - THRESHOLDS["lineOuterDisplacementPxMin"] / y_max * panel_height
        effective = float(line_metrics[orientation]["effectiveOuterDisplacementPx"])
        gate_status = "PASS" if effective >= THRESHOLDS["lineOuterDisplacementPxMin"] else "FAIL"
        panels.append(
            f'<text x="{plot_left:.0f}" y="{top - 18:.0f}" class="panel">{orientation.upper()} LINES</text>'
            f'<text x="{plot_right:.0f}" y="{top - 18:.0f}" class="summary" text-anchor="end">EFFECTIVE OUTER {effective:.3f} PX · {gate_status}</text>'
            f'<rect x="{plot_left:.0f}" y="{top:.0f}" width="{plot_right - plot_left:.0f}" height="{panel_height:.0f}" class="plot"/>'
            f'<line x1="{plot_left:.0f}" y1="{threshold_y:.2f}" x2="{plot_right:.0f}" y2="{threshold_y:.2f}" class="threshold"/>'
            f'<text x="{plot_right - 6:.0f}" y="{threshold_y - 6:.2f}" class="threshold-label" text-anchor="end">SUMMARY GATE MIN {THRESHOLDS["lineOuterDisplacementPxMin"]:.1f} PX</text>'
            f'{svg_polyline(displacement, "#9cff38")}'
            f'{svg_polyline(compression, "#ff5b43")}'
            f'<text x="{plot_left - 12:.0f}" y="{top + 5:.0f}" class="axis" text-anchor="end">{y_max:.1f}</text>'
            f'<text x="{plot_left - 12:.0f}" y="{bottom + 5:.0f}" class="axis" text-anchor="end">0</text>'
        )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    .bg {{ fill: #080a0b; }} .plot {{ fill: #111516; stroke: #394043; stroke-width: 1; }}
    text {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; fill: #d9dfdc; }}
    .title {{ font-size: 18px; font-weight: 700; }} .panel {{ font-size: 13px; letter-spacing: 1.5px; }} .summary {{ font-size: 10px; fill: #9cff38; }}
    .axis {{ font-size: 10px; fill: #89928e; }} .threshold {{ stroke: #ffc94a; stroke-width: 1; stroke-dasharray: 5 5; }}
    .threshold-label {{ font-size: 9px; fill: #ffc94a; }} .legend {{ font-size: 11px; }}
  </style>
  <rect class="bg" width="100%" height="100%"/>
  <text x="34" y="36" class="title">V4 OPTICS · LINE DISPLACEMENT</text>
  <line x1="600" y1="31" x2="636" y2="31" stroke="#9cff38" stroke-width="3"/><text x="646" y="35" class="legend">OUTER-LINE P90</text>
  <line x1="806" y1="31" x2="842" y2="31" stroke="#ff5b43" stroke-width="3"/><text x="852" y="35" class="legend">SYMMETRIC</text>
  {''.join(panels)}
</svg>'''


def highlight_path_svg(highlight: dict[str, Any]) -> str:
    width, height = 720, 520
    left, top, right, bottom = 70.0, 74.0, width - 46.0, height - 54.0
    centroid_points = []
    pointer_points = []
    labels = []
    for index, sample in enumerate(highlight["samples"]):
        centroid = sample.get("centroidNormalized")
        pointer = sample.get("pointer")
        if centroid is not None:
            x = left + min(1.15, max(-0.15, float(centroid[0]))) * (right - left)
            y = top + min(1.15, max(-0.15, float(centroid[1]))) * (bottom - top)
            centroid_points.append((x, y))
            labels.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4" fill="#9cff38"/><text x="{x + 7:.2f}" y="{y - 7:.2f}" class="index">{index:02d}</text>')
        if pointer is not None:
            # Pointer coordinates are NDC [-1, 1]; remap to the same unit frame.
            x = left + (min(1.0, max(-1.0, float(pointer[0]))) + 1.0) * 0.5 * (right - left)
            y = top + (min(1.0, max(-1.0, float(pointer[1]))) + 1.0) * 0.5 * (bottom - top)
            pointer_points.append((x, y))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    .bg {{ fill: #080a0b; }} .frame {{ fill: #111516; stroke: #394043; stroke-width: 1; }}
    text {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; fill: #d9dfdc; }}
    .title {{ font-size: 18px; font-weight: 700; }} .legend {{ font-size: 11px; }} .index {{ font-size: 9px; fill: #9cff38; }}
  </style>
  <rect class="bg" width="100%" height="100%"/>
  <text x="34" y="36" class="title">V4 OPTICS · HIGHLIGHT CENTROID PATH</text>
  <rect x="{left:.0f}" y="{top:.0f}" width="{right - left:.0f}" height="{bottom - top:.0f}" class="frame"/>
  {svg_polyline(pointer_points, "#5a6570", 1.5)}
  {svg_polyline(centroid_points, "#9cff38", 3.0)}
  {''.join(labels)}
  <line x1="70" y1="487" x2="106" y2="487" stroke="#5a6570" stroke-width="2"/><text x="116" y="491" class="legend">POINTER INPUT</text>
  <line x1="245" y1="487" x2="281" y2="487" stroke="#9cff38" stroke-width="3"/><text x="291" y="491" class="legend">MEASURED HIGHLIGHT</text>
</svg>'''


def write_metric_artifacts(result: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    specifications = {
        "displacementPlot": (
            artifact_dir / "displacement-plot.svg",
            displacement_plot_svg(result["metrics"]["lineDisplacement"]),
        ),
        "highlightPath": (
            artifact_dir / "highlight-path.svg",
            highlight_path_svg(result["metrics"]["highlightPath"]),
        ),
    }
    records = {}
    for identifier, (file, content) in specifications.items():
        file.write_text(content + "\n", encoding="utf-8")
        records[identifier] = {
            "path": file.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(file),
            "source": "sanitized metrics only; no screenshot or private pixel embedding",
        }
    return records


def check(identifier: str, passed: bool, value: Any, threshold: Any) -> dict[str, Any]:
    return {"id": identifier, "status": "PASS" if passed else "FAIL", "value": value, "threshold": threshold}


def blocked_result(reason: str, input_path: Path | None = None) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "phase": "v4-02-optics-lab-foundation",
        "generator": GENERATOR,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED",
        "measurementRun": {"executed": False, "reason": reason},
        "inputManifestSha256": sha256_file(input_path) if input_path and input_path.is_file() else None,
        "runtimeContract": {"passed": False},
        "metrics": {},
        "checks": [],
        "finalQuantitativeAcceptance": "BLOCKED",
        "caveats": {
            "naturalMediaTextureCoverage": False,
            "gpuExecutionTimeMeasured": False,
            "scope": "No measurements or visual acceptance may be inferred from this blocked result.",
        },
    }


def measure(input_path: Path) -> dict[str, Any]:
    manifest = json.loads(input_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "CAPTURED":
        raise ValueError(f"Capture manifest status is {manifest.get('status')!r}, expected 'CAPTURED'")
    contract = manifest.get("runtimeContract", {})
    if not (
        contract.get("passed") is True
        and contract.get("normalPathDirectMedia") is False
        and contract.get("sceneTarget", {}).get("type") == "half-float"
        and contract.get("sceneTarget", {}).get("colorSpace") == "linear"
        and contract.get("v3Preserved") is True
    ):
        raise ValueError("Runtime optics contract did not pass")
    source_identity = manifest.get("sourceIdentity")
    served_resource_identity = manifest.get("servedResourceIdentity")
    if not (
        isinstance(source_identity, dict)
        and len(source_identity.get("runtimeSourceSetSha256", "")) == 64
        and isinstance(source_identity.get("files"), list)
        and source_identity.get("files")
    ):
        raise ValueError("Capture is not bound to a runtime source-set identity")
    if not (
        isinstance(served_resource_identity, dict)
        and len(served_resource_identity.get("manifestSha256", "")) == 64
        and isinstance(served_resource_identity.get("resources"), list)
        and served_resource_identity.get("resourceCount") == len(served_resource_identity["resources"])
    ):
        raise ValueError("Capture is not bound to a served-resource identity")

    entries = {entry["id"]: entry for entry in manifest.get("captures", [])}
    missing = sorted(REQUIRED_CAPTURE_IDS - entries.keys())
    if missing:
        raise ValueError(f"Capture manifest is missing required cases: {', '.join(missing)}")
    pointer_entries = manifest.get("pointerPath", [])
    if len(pointer_entries) < 5:
        raise ValueError("At least five pointer/reflection samples are required")

    edge_rgb = load_rgb(entries["edge-mask-black"])
    shapes = {load_rgb(entry).shape for entry in list(entries.values()) + pointer_entries}
    if len(shapes) != 1:
        raise ValueError("All optics-lab captures must have identical dimensions")
    zones = build_zones(edge_rgb)
    checker = load_rgb(entries["v4-checker"])
    sharpness = sharpness_metrics(checker, zones)
    horizontal = line_displacement_metrics(load_rgb(entries["v4-horizontal-lines"]), zones, "horizontal")
    vertical = line_displacement_metrics(load_rgb(entries["v4-vertical-lines"]), zones, "vertical")
    corners = corner_continuity_metrics(edge_rgb, zones)
    highlight = highlight_path_metrics(pointer_entries, zones)
    dispersion = dispersion_metrics(load_rgb(entries["dispersion-checker"]), zones)
    dark = flat_background_metrics(load_rgb(entries["v4-black"]), zones, "black")
    light = flat_background_metrics(load_rgb(entries["v4-white"]), zones, "white")
    difference = difference_metrics(load_rgb(entries["difference-checker"]))

    checks = [
        check(
            "center-sharpness",
            sharpness["centerToRimRatio"] >= THRESHOLDS["centerToRimSharpnessRatioMin"],
            sharpness["centerToRimRatio"],
            {"min": THRESHOLDS["centerToRimSharpnessRatioMin"]},
        ),
        check(
            "rim-width",
            THRESHOLDS["rimWidthNormalizedMin"] <= zones["rimWidthNormalized"] <= THRESHOLDS["rimWidthNormalizedMax"],
            zones["rimWidthNormalized"],
            {"min": THRESHOLDS["rimWidthNormalizedMin"], "max": THRESHOLDS["rimWidthNormalizedMax"]},
        ),
        check(
            "horizontal-line-displacement-continuity",
            horizontal["coverage"] >= THRESHOLDS["lineCoverageMin"]
            and horizontal["continuityScore"] >= THRESHOLDS["lineContinuityScoreMin"]
            and horizontal["effectiveOuterDisplacementPx"] >= THRESHOLDS["lineOuterDisplacementPxMin"],
            {
                "coverage": horizontal["coverage"],
                "score": horizontal["continuityScore"],
                "outerDisplacementPx": horizontal["effectiveOuterDisplacementPx"],
            },
            {
                "coverageMin": THRESHOLDS["lineCoverageMin"],
                "scoreMin": THRESHOLDS["lineContinuityScoreMin"],
                "outerDisplacementPxMin": THRESHOLDS["lineOuterDisplacementPxMin"],
            },
        ),
        check(
            "vertical-line-displacement-continuity",
            vertical["coverage"] >= THRESHOLDS["lineCoverageMin"]
            and vertical["continuityScore"] >= THRESHOLDS["lineContinuityScoreMin"]
            and vertical["effectiveOuterDisplacementPx"] >= THRESHOLDS["lineOuterDisplacementPxMin"],
            {
                "coverage": vertical["coverage"],
                "score": vertical["continuityScore"],
                "outerDisplacementPx": vertical["effectiveOuterDisplacementPx"],
            },
            {
                "coverageMin": THRESHOLDS["lineCoverageMin"],
                "scoreMin": THRESHOLDS["lineContinuityScoreMin"],
                "outerDisplacementPxMin": THRESHOLDS["lineOuterDisplacementPxMin"],
            },
        ),
        check(
            "corner-continuity",
            corners["score"] >= THRESHOLDS["cornerContinuityScoreMin"],
            corners["score"],
            {"min": THRESHOLDS["cornerContinuityScoreMin"]},
        ),
        check(
            "pointer-highlight-path",
            highlight["validSampleCount"] == highlight["requestedSampleCount"]
            and highlight["travelNormalized"] >= THRESHOLDS["highlightTravelNormalizedMin"]
            and highlight["maxToMedianJumpRatio"] is not None
            and highlight["maxToMedianJumpRatio"] <= THRESHOLDS["highlightJumpRatioMax"],
            {
                "valid": highlight["validSampleCount"],
                "requested": highlight["requestedSampleCount"],
                "travel": highlight["travelNormalized"],
                "jumpRatio": highlight["maxToMedianJumpRatio"],
            },
            {
                "travelMin": THRESHOLDS["highlightTravelNormalizedMin"],
                "jumpRatioMax": THRESHOLDS["highlightJumpRatioMax"],
            },
        ),
        check(
            "dispersion-localization",
            dispersion["outerZoneRatio"] is not None
            and dispersion["outerZoneRatio"] >= THRESHOLDS["dispersionOuterZoneRatioMin"],
            dispersion["outerZoneRatio"],
            {"min": THRESHOLDS["dispersionOuterZoneRatioMin"]},
        ),
        check(
            "dark-background-discernibility",
            dark["discernibilityScore"] >= THRESHOLDS["flatBackgroundDiscernibilityMin"],
            dark["discernibilityScore"],
            {"min": THRESHOLDS["flatBackgroundDiscernibilityMin"]},
        ),
        check(
            "light-background-discernibility",
            light["discernibilityScore"] >= THRESHOLDS["flatBackgroundDiscernibilityMin"],
            light["discernibilityScore"],
            {"min": THRESHOLDS["flatBackgroundDiscernibilityMin"]},
        ),
    ]
    structural_pass = all(item["status"] == "PASS" for item in checks)
    screenshot_evidence = [
        {"id": entry["id"], "role": entry["role"], "sha256": entry["sha256"]}
        for entry in list(entries.values()) + pointer_entries
    ]
    return {
        "schemaVersion": 1,
        "phase": "v4-02-optics-lab-foundation",
        "generator": GENERATOR,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if structural_pass else "FAIL",
        "measurementRun": {
            "executed": True,
            "inputManifestSha256": sha256_file(input_path),
            "screenshotSetSha256": manifest.get("screenshotSetSha256"),
            "evidenceSetSha256": canonical_sha256(screenshot_evidence),
            "privateSessionVideoSha256": manifest.get("sessionVideo", {}).get("sha256"),
            "privateUiPreviewSha256": manifest.get("uiPreview", {}).get("sha256"),
            "privatePixelsCommitted": False,
        },
        "runtimeContract": contract,
        "sourceIdentity": source_identity,
        "servedResourceIdentity": served_resource_identity,
        "environment": manifest.get("environment"),
        "metrics": {
            "centerSharpness": sharpness,
            "rimWidth": {
                "method": "92nd-percentile inward distance of the measured edge-mask lens zone",
                "pixels": zones["rimWidthPx"],
                "normalizedToShortCardSide": zones["rimWidthNormalized"],
                "silhouetteAreaRatio": zones["silhouetteAreaRatio"],
            },
            "lineDisplacement": {"horizontal": horizontal, "vertical": vertical},
            "cornerContinuity": corners,
            "highlightPath": highlight,
            "dispersionLocalization": dispersion,
            "flatBackgroundDiscernibility": {"dark": dark, "light": light},
            "differenceView": difference,
            "rafIntervalMs": manifest.get("performance"),
        },
        "checks": checks,
        "thresholds": THRESHOLDS,
        "evidence": screenshot_evidence,
        "finalQuantitativeAcceptance": "BLOCKED",
        "caveats": {
            "naturalMediaTextureCoverage": False,
            "naturalMediaTextureReason": "No natural/high-frequency photo or licensed video is measured in this first structural round.",
            "displayEncodedReadback": True,
            "displayEncodedReadbackReason": "PNG diagnostics are measured after presentation; the runtime contract separately verifies linear HDR scene sampling.",
            "gpuExecutionTimeMeasured": False,
            "gpuTimingReason": "Reported P50/P95/P99 are browser rAF intervals, not WebGPU timestamp-query measurements.",
            "scope": "PASS, if present, applies only to the Phase-1 deterministic optics-lab structural gate and never to final Frozen Visual Golden acceptance.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--artifact-dir", type=Path, default=DEFAULT_ARTIFACT_DIR)
    arguments = parser.parse_args()
    input_path = arguments.input.resolve()
    output_path = arguments.output.resolve()
    artifact_dir = arguments.artifact_dir.resolve()
    if REPO_ROOT not in output_path.parents:
        parser.error("--output must remain inside the repository")
    if REPO_ROOT not in artifact_dir.parents:
        parser.error("--artifact-dir must remain inside the repository")

    try:
        result = measure(input_path)
        result["artifacts"] = write_metric_artifacts(result, artifact_dir)
        exit_code = 0 if result["status"] == "PASS" else 2
    except Exception as error:  # Fail closed and leave an auditable reason.
        result = blocked_result(str(error), input_path)
        exit_code = 2
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "output": output_path.relative_to(REPO_ROOT).as_posix(),
        "checkCount": len(result.get("checks", [])),
    }, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
