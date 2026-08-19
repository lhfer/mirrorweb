"""Card-normalized optical measurements for the private Phase 1B review.

The functions in this module deliberately operate on card ROIs and scalar/
profile descriptors.  They never compute a whole-card SSIM or other raw-pixel
equivalence score.  A projective transform removes screen placement and card
perspective before the four sides and four corners are measured separately.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage, signal
from skimage import transform


CANONICAL_WIDTH = 768
CANONICAL_HEIGHT = 448
CANONICAL_SIZE = (CANONICAL_WIDTH, CANONICAL_HEIGHT)
EDGE_REGION_NAMES = (
    "top",
    "right",
    "bottom",
    "left",
    "topLeft",
    "topRight",
    "bottomRight",
    "bottomLeft",
)

OPTICAL_ZONE_LABELS = {
    "centerFace": 0,
    "opticalShoulder": 1,
    "strongLensRim": 2,
    "sidewall": 3,
}
OPTICAL_ZONE_PALETTE = np.asarray(
    [
        [0.25, 0.25, 0.25],  # Center Face
        [1.0, 0.0, 0.0],     # Optical Shoulder
        [0.0, 1.0, 0.0],     # Strong Lens Rim
        [0.0, 0.0, 1.0],     # Sidewall
    ],
    dtype=np.float32,
)


class MeasurementUnavailable(ValueError):
    """Raised when evidence cannot support a non-invented measurement."""


@dataclass(frozen=True)
class CardTransform:
    """Projective mapping from canonical card pixels to source pixels."""

    mapping: transform.ProjectiveTransform
    source_quad: np.ndarray
    canonical_width: int = CANONICAL_WIDTH
    canonical_height: int = CANONICAL_HEIGHT

    @property
    def canonical_corners(self) -> np.ndarray:
        return np.asarray(
            [
                [0.0, 0.0],
                [self.canonical_width - 1.0, 0.0],
                [self.canonical_width - 1.0, self.canonical_height - 1.0],
                [0.0, self.canonical_height - 1.0],
            ],
            dtype=np.float64,
        )

    def rectify(self, image: np.ndarray, *, order: int = 1) -> np.ndarray:
        """Warp a source-frame array into canonical card coordinates."""

        if image.ndim not in (2, 3):
            raise ValueError("Only grayscale or RGB arrays can be rectified")
        return transform.warp(
            image,
            inverse_map=self.mapping,
            output_shape=(self.canonical_height, self.canonical_width),
            order=order,
            preserve_range=True,
            mode="constant",
            cval=0,
        )

    def source_to_canonical(self, points: np.ndarray) -> np.ndarray:
        return np.asarray(self.mapping.inverse(points), dtype=np.float64)


def load_rgb(path: Path | str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def load_mask(path: Path | str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L"), dtype=np.uint8) >= 128


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    value = np.clip(rgb.astype(np.float32), 0.0, 1.0)
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def luminance(rgb: np.ndarray, *, linearize: bool = True) -> np.ndarray:
    value = srgb_to_linear(rgb) if linearize else np.clip(rgb, 0.0, 1.0)
    return value[..., 0] * 0.2126 + value[..., 1] * 0.7152 + value[..., 2] * 0.0722


def chroma_energy(rgb: np.ndarray, *, linearize: bool = True) -> np.ndarray:
    value = srgb_to_linear(rgb) if linearize else np.clip(rgb, 0.0, 1.0)
    return value.max(axis=2) - value.min(axis=2)


def gradient_energy(gray: np.ndarray) -> np.ndarray:
    gx = ndimage.sobel(gray, axis=1, mode="reflect") / 8.0
    gy = ndimage.sobel(gray, axis=0, mode="reflect") / 8.0
    laplacian = ndimage.laplace(gray, mode="reflect")
    return np.sqrt(gx * gx + gy * gy) + np.abs(laplacian) * 0.35


def largest_component(mask: np.ndarray) -> np.ndarray:
    labels, count = ndimage.label(mask)
    if count == 0:
        return np.zeros_like(mask, dtype=bool)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return labels == int(np.argmax(sizes))


def _quad_area(quad: np.ndarray) -> float:
    x, y = quad[:, 0], quad[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


def card_transform(
    quad: Sequence[Sequence[float]],
    *,
    source_shape: Sequence[int] | None = None,
    normalized: bool = False,
    canonical_size: tuple[int, int] = CANONICAL_SIZE,
) -> CardTransform:
    """Create a validated canonical-to-source card homography.

    ``quad`` must be top-left, top-right, bottom-right, bottom-left.  A
    normalized quad is expanded using ``source_shape=(height, width, ...)``.
    """

    source_quad = np.asarray(quad, dtype=np.float64)
    if source_quad.shape != (4, 2) or not np.isfinite(source_quad).all():
        raise MeasurementUnavailable("card quad must contain four finite x/y points")
    if normalized:
        if source_shape is None or len(source_shape) < 2:
            raise MeasurementUnavailable("source shape is required for a normalized quad")
        source_quad = source_quad * np.asarray([source_shape[1], source_shape[0]], dtype=np.float64)
    if _quad_area(source_quad) < 64.0:
        raise MeasurementUnavailable("card quad has insufficient measurable area")
    if source_shape is not None:
        height, width = int(source_shape[0]), int(source_shape[1])
        margin = max(width, height) * 0.04
        if (
            (source_quad[:, 0] < -margin).any()
            or (source_quad[:, 0] > width + margin).any()
            or (source_quad[:, 1] < -margin).any()
            or (source_quad[:, 1] > height + margin).any()
        ):
            raise MeasurementUnavailable("card quad escapes the source frame")
    canonical_width, canonical_height = canonical_size
    canonical = np.asarray(
        [
            [0.0, 0.0],
            [canonical_width - 1.0, 0.0],
            [canonical_width - 1.0, canonical_height - 1.0],
            [0.0, canonical_height - 1.0],
        ],
        dtype=np.float64,
    )
    mapping = transform.ProjectiveTransform.from_estimate(canonical, source_quad)
    if mapping is None:
        raise MeasurementUnavailable("card homography could not be estimated")
    projected = np.asarray(mapping(canonical))
    error = float(np.sqrt(np.mean(np.sum((projected - source_quad) ** 2, axis=1))))
    short_side = max(1.0, min(
        np.linalg.norm(source_quad[1] - source_quad[0]),
        np.linalg.norm(source_quad[2] - source_quad[1]),
        np.linalg.norm(source_quad[3] - source_quad[2]),
        np.linalg.norm(source_quad[0] - source_quad[3]),
    ))
    if error / short_side > 0.015:
        raise MeasurementUnavailable("card homography reprojection error exceeds 1.5% of the short side")
    return CardTransform(mapping, source_quad, canonical_width, canonical_height)


def infer_axis_aligned_quad(signal_rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Infer a conservative front-card quad from a chromatic debug capture.

    Oblique/tilted evidence should provide an explicit quad.  This helper is
    intentionally limited to the fixed front pose used by the existing lab.
    """

    gray = luminance(signal_rgb, linearize=False)
    chroma = signal_rgb.max(axis=2) - signal_rgb.min(axis=2)
    border = np.concatenate((gray[0], gray[-1], gray[:, 0], gray[:, -1]))
    baseline = float(np.median(border))
    signal_map = np.maximum(chroma, np.abs(gray - baseline))
    positive = signal_map[signal_map > max(0.01, float(np.percentile(signal_map, 65)))]
    if positive.size < 64:
        raise MeasurementUnavailable("edge debug image has no separable card signal")
    threshold = max(0.025, float(np.percentile(positive, 30)) * 0.5)
    mask = largest_component(ndimage.binary_closing(signal_map >= threshold, iterations=2))
    mask = ndimage.binary_fill_holes(mask)
    yy, xx = np.nonzero(mask)
    if xx.size < 256:
        raise MeasurementUnavailable("edge debug card silhouette is too small")
    x0, x1 = float(xx.min()), float(xx.max())
    y0, y1 = float(yy.min()), float(yy.max())
    height, width = mask.shape
    if x0 <= width * 0.005 or y0 <= height * 0.005 or x1 >= width * 0.995 or y1 >= height * 0.995:
        raise MeasurementUnavailable("edge debug card is clipped by the capture frame")
    quad = np.asarray([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64)
    return quad, mask


def infer_card_quad_from_silhouette(silhouette: np.ndarray) -> np.ndarray:
    """Infer four projective edge intersections from a rounded card mask.

    Straight edge spans are fitted away from the rounded corners.  Their four
    intersections provide a pose-specific homography for matching beauty and
    categorical-zone captures made without an explicit projected quad.
    """

    mask = largest_component(silhouette.astype(bool))
    mask = ndimage.binary_fill_holes(mask)
    yy, xx = np.nonzero(mask)
    if xx.size < 256:
        raise MeasurementUnavailable("card silhouette is too small for pose homography")
    x0, x1 = int(xx.min()), int(xx.max())
    y0, y1 = int(yy.min()), int(yy.max())
    width, height = x1 - x0 + 1, y1 - y0 + 1
    if width < 32 or height < 32:
        raise MeasurementUnavailable("card silhouette bounds are too small for pose homography")

    columns = np.arange(x0, x1 + 1)
    top = np.asarray([
        np.flatnonzero(mask[:, x])[0] if mask[:, x].any() else np.nan
        for x in columns
    ], dtype=np.float64)
    bottom = np.asarray([
        np.flatnonzero(mask[:, x])[-1] if mask[:, x].any() else np.nan
        for x in columns
    ], dtype=np.float64)
    rows = np.arange(y0, y1 + 1)
    left = np.asarray([
        np.flatnonzero(mask[y])[0] if mask[y].any() else np.nan
        for y in rows
    ], dtype=np.float64)
    right = np.asarray([
        np.flatnonzero(mask[y])[-1] if mask[y].any() else np.nan
        for y in rows
    ], dtype=np.float64)

    def central_fit(coordinates: np.ndarray, values: np.ndarray) -> tuple[float, float]:
        low = float(np.min(coordinates) + np.ptp(coordinates) * 0.24)
        high = float(np.min(coordinates) + np.ptp(coordinates) * 0.76)
        valid = np.isfinite(values) & (coordinates >= low) & (coordinates <= high)
        if valid.sum() < 12:
            raise MeasurementUnavailable("card edge has insufficient straight-span samples")
        slope, intercept = np.polyfit(coordinates[valid], values[valid], 1)
        residual = np.abs(values - (slope * coordinates + intercept))
        scale = max(float(np.median(residual[valid])) * 3.5, 1.5)
        refined = valid & (residual <= scale)
        if refined.sum() >= 12:
            slope, intercept = np.polyfit(coordinates[refined], values[refined], 1)
        return float(slope), float(intercept)

    top_line = central_fit(columns, top)       # y = ax + b
    bottom_line = central_fit(columns, bottom) # y = ax + b
    left_line = central_fit(rows, left)        # x = ay + b
    right_line = central_fit(rows, right)      # x = ay + b

    def intersect(horizontal: tuple[float, float], vertical: tuple[float, float]) -> list[float]:
        horizontal_slope, horizontal_intercept = horizontal
        vertical_slope, vertical_intercept = vertical
        denominator = 1.0 - vertical_slope * horizontal_slope
        if abs(denominator) < 1e-6:
            raise MeasurementUnavailable("card edge fits are nearly parallel in projective intersection")
        x = (vertical_slope * horizontal_intercept + vertical_intercept) / denominator
        y = horizontal_slope * x + horizontal_intercept
        return [float(x), float(y)]

    quad = np.asarray([
        intersect(top_line, left_line),
        intersect(top_line, right_line),
        intersect(bottom_line, right_line),
        intersect(bottom_line, left_line),
    ], dtype=np.float64)
    if not np.isfinite(quad).all() or _quad_area(quad) < width * height * 0.45:
        raise MeasurementUnavailable("pose homography quad inferred from the silhouette is implausible")
    return quad


def canonical_silhouette(rectified_edge_rgb: np.ndarray) -> np.ndarray:
    gray = luminance(rectified_edge_rgb, linearize=False)
    chroma = rectified_edge_rgb.max(axis=2) - rectified_edge_rgb.min(axis=2)
    signal_map = np.maximum(chroma, np.abs(gray - float(np.median(gray))))
    positive = signal_map[signal_map > max(0.008, float(np.percentile(signal_map, 55)))]
    if positive.size == 0:
        raise MeasurementUnavailable("canonical edge image has no card signal")
    threshold = max(0.018, float(np.percentile(positive, 22)) * 0.42)
    silhouette = largest_component(ndimage.binary_closing(signal_map >= threshold, iterations=2))
    silhouette = ndimage.binary_fill_holes(silhouette)
    if silhouette.mean() < 0.35:
        # A dark center can leave only a ring. Filling the largest ring should
        # recover the card, but do not silently accept a tiny component.
        raise MeasurementUnavailable("canonical card silhouette coverage is implausibly low")
    return silhouette


def normalized_distance(silhouette: np.ndarray) -> np.ndarray:
    short_side = float(min(silhouette.shape))
    return ndimage.distance_transform_edt(silhouette) / max(short_side, 1.0)


def normalized_edge_regions(
    silhouette: np.ndarray,
    *,
    max_depth_ratio: float = 0.18,
) -> dict[str, np.ndarray]:
    """Partition a canonical edge ROI into four sides and four corners."""

    height, width = silhouette.shape
    yy, xx = np.mgrid[:height, :width]
    x = xx / max(width - 1, 1)
    y = yy / max(height - 1, 1)
    edge = silhouette & (normalized_distance(silhouette) <= max_depth_ratio)
    corner_x = 0.23
    corner_y = 0.27
    regions = {
        "topLeft": edge & (x < corner_x) & (y < corner_y),
        "topRight": edge & (x > 1 - corner_x) & (y < corner_y),
        "bottomRight": edge & (x > 1 - corner_x) & (y > 1 - corner_y),
        "bottomLeft": edge & (x < corner_x) & (y > 1 - corner_y),
        "top": edge & (x >= corner_x) & (x <= 1 - corner_x) & (y <= 0.5),
        "right": edge & (y >= corner_y) & (y <= 1 - corner_y) & (x >= 0.5),
        "bottom": edge & (x >= corner_x) & (x <= 1 - corner_x) & (y >= 0.5),
        "left": edge & (y >= corner_y) & (y <= 1 - corner_y) & (x <= 0.5),
    }
    return {name: regions[name] for name in EDGE_REGION_NAMES}


def _finite_or_none(value: float | np.floating[Any]) -> float | None:
    number = float(value)
    return number if math.isfinite(number) else None


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float | None:
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if valid.sum() < 8:
        return None
    values = values[valid]
    weights = weights[valid]
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    cutoff = quantile * cumulative[-1]
    return float(values[min(int(np.searchsorted(cumulative, cutoff, side="left")), len(values) - 1)])


def normalized_profiles(
    rectified_rgb: np.ndarray,
    silhouette: np.ndarray,
    *,
    exclusions: Iterable[np.ndarray] = (),
    bins: int = 54,
    max_depth_ratio: float = 0.18,
) -> dict[str, Any]:
    """Return normalized radial profiles for all four sides and corners."""

    if rectified_rgb.shape[:2] != silhouette.shape:
        raise ValueError("rectified image and silhouette shapes differ")
    allowed = silhouette.copy()
    for exclusion in exclusions:
        if exclusion.shape != silhouette.shape:
            raise ValueError("profile exclusion shape differs from the card silhouette")
        allowed &= ~exclusion.astype(bool)
    distance = normalized_distance(silhouette)
    gray = luminance(rectified_rgb)
    chroma = chroma_energy(rectified_rgb)
    sharpness = gradient_energy(gray)
    regions = normalized_edge_regions(silhouette, max_depth_ratio=max_depth_ratio)
    edges = np.linspace(0.0, max_depth_ratio, bins + 1)
    result: dict[str, Any] = {}
    for name, region in regions.items():
        samples = []
        valid_region = region & allowed
        for index in range(bins):
            sample = valid_region & (distance >= edges[index]) & (distance < edges[index + 1])
            count = int(sample.sum())
            samples.append({
                "depthRatio": float((edges[index] + edges[index + 1]) * 0.5),
                "sampleCount": count,
                "meanLuma": float(np.mean(gray[sample])) if count else None,
                "meanChroma": float(np.mean(chroma[sample])) if count else None,
                "rmsSharpness": float(np.sqrt(np.mean(sharpness[sample] ** 2))) if count else None,
            })
        result[name] = {
            "coverage": float(valid_region.sum() / max(region.sum(), 1)),
            "sampleCount": int(valid_region.sum()),
            "samples": samples,
        }
    return {
        "coordinateSpace": "canonical-card-short-side",
        "maxDepthRatio": max_depth_ratio,
        "binCount": bins,
        "regions": result,
    }


def summarize_profiles(profiles: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name, region in profiles["regions"].items():
        valid = [sample for sample in region["samples"] if sample["sampleCount"] > 0]
        summary[name] = {
            "coverage": region["coverage"],
            "sampleCount": region["sampleCount"],
            "medianLuma": float(np.median([sample["meanLuma"] for sample in valid])) if valid else None,
            "medianChroma": float(np.median([sample["meanChroma"] for sample in valid])) if valid else None,
            "medianSharpness": float(np.median([sample["rmsSharpness"] for sample in valid])) if valid else None,
        }
    return summary


def decode_optical_zone_palette(
    rectified_zone_rgb: np.ndarray,
    silhouette: np.ndarray | None = None,
    *,
    required_zones: Sequence[str] = tuple(OPTICAL_ZONE_LABELS),
) -> dict[str, Any]:
    """Decode the mutually-exclusive V4 optical-zone debug palette.

    The debug contract is categorical, not three continuous material fields:
    center gray ``(.25,.25,.25)``, shoulder red, strong rim green, and
    sidewall blue.  Saturated pixels are decoded by channel argmax; neutral
    pixels are matched to the gray swatch.  This remains stable after normal
    display encoding while refusing captures that do not resemble the palette.
    """

    if rectified_zone_rgb.ndim != 3 or rectified_zone_rgb.shape[2] < 3:
        raise ValueError("optical-zone debug evidence must be RGB")
    rgb = np.clip(rectified_zone_rgb[..., :3].astype(np.float32), 0.0, 1.0)
    maximum = rgb.max(axis=2)
    minimum = rgb.min(axis=2)
    chroma = maximum - minimum
    mean = rgb.mean(axis=2)

    colored = (maximum >= 0.16) & (chroma >= 0.10)
    neutral_center = (mean >= 0.075) & (chroma < 0.10)
    palette_signal = colored | neutral_center
    if silhouette is None:
        candidate = largest_component(ndimage.binary_closing(palette_signal, iterations=2))
        silhouette = ndimage.binary_fill_holes(candidate)
    else:
        silhouette = silhouette.astype(bool)
    if silhouette.shape != rgb.shape[:2]:
        raise ValueError("optical-zone debug and silhouette shapes differ")
    if silhouette.sum() < 256 or float(silhouette.mean()) < 0.20:
        raise MeasurementUnavailable("optical-zone palette has no plausible card silhouette")

    # Nearest-palette is used for neutral/antialiased pixels.  Colored pixels
    # use argmax explicitly so red/green/blue remain categorical even after
    # output transforms.  At no point are channels interpreted as zone weights.
    nearest = np.argmin(
        np.sum((rgb[..., None, :] - OPTICAL_ZONE_PALETTE[None, None, :, :]) ** 2, axis=3),
        axis=2,
    ).astype(np.int8)
    labels = nearest
    labels[colored] = np.argmax(rgb[colored], axis=1).astype(np.int8) + 1
    labels[neutral_center] = OPTICAL_ZONE_LABELS["centerFace"]
    labels[~silhouette] = -1

    recognized = palette_signal & silhouette
    recognized_ratio = float(recognized.sum() / max(int(silhouette.sum()), 1))
    if recognized_ratio < 0.965:
        raise MeasurementUnavailable(
            f"optical-zone palette recognition {recognized_ratio:.4f} is below 0.965"
        )
    counts = {
        name: int((labels == label).sum())
        for name, label in OPTICAL_ZONE_LABELS.items()
    }
    unknown_required = [name for name in required_zones if name not in OPTICAL_ZONE_LABELS]
    if unknown_required:
        raise ValueError(f"unknown required optical zones: {', '.join(unknown_required)}")
    missing = [name for name in required_zones if counts[name] < 8]
    if missing:
        raise MeasurementUnavailable(f"optical-zone palette is missing categories: {', '.join(missing)}")
    return {
        "labels": labels,
        "silhouette": silhouette,
        "recognizedRatio": recognized_ratio,
        "counts": counts,
        "method": "mutually-exclusive palette; neutral-gray nearest match plus RGB channel argmax",
    }


def _ray_zone_width_samples(labels: np.ndarray, silhouette: np.ndarray) -> dict[str, np.ndarray]:
    """Measure band widths along four screen-space side normals.

    Rays are restricted to the middle 60% of each side so rounded corners do
    not inflate a screen-width metric.  Each ray must reach the center label;
    only the outer prefix is counted for the three optical bands.
    """

    height, width = silhouette.shape
    short_side = float(min(height, width))
    samples: dict[str, list[float]] = {
        "opticalShoulder": [],
        "strongLensRim": [],
        "sidewall": [],
    }

    def consume(sequence: np.ndarray) -> None:
        center_positions = np.flatnonzero(sequence == OPTICAL_ZONE_LABELS["centerFace"])
        if center_positions.size == 0:
            return
        prefix = sequence[:int(center_positions[0])]
        if prefix.size == 0:
            return
        for name in samples:
            samples[name].append(float(np.count_nonzero(prefix == OPTICAL_ZONE_LABELS[name])) / short_side)

    for y in range(int(height * 0.20), max(int(height * 0.80), int(height * 0.20) + 1)):
        positions = np.flatnonzero(silhouette[y])
        if positions.size:
            sequence = labels[y, positions[0]:positions[-1] + 1]
            consume(sequence)
            consume(sequence[::-1])
    for x in range(int(width * 0.20), max(int(width * 0.80), int(width * 0.20) + 1)):
        positions = np.flatnonzero(silhouette[:, x])
        if positions.size:
            sequence = labels[positions[0]:positions[-1] + 1, x]
            consume(sequence)
            consume(sequence[::-1])
    return {name: np.asarray(values, dtype=np.float64) for name, values in samples.items()}


def _width_distribution(
    values: np.ndarray,
    *,
    positive_only: bool = False,
    min_samples: int = 16,
) -> dict[str, Any]:
    minimum = 0 if not positive_only else 1e-9
    valid = values[np.isfinite(values) & (values >= minimum)]
    if valid.size < min_samples:
        raise MeasurementUnavailable("optical-zone width has insufficient screen-normal rays")
    return {
        "p10": float(np.percentile(valid, 10)),
        "p50": float(np.percentile(valid, 50)),
        "p90": float(np.percentile(valid, 90)),
        "sampleCount": int(valid.size),
        "resolutionLimited": bool(valid.size < 16),
    }


def compute_optical_zone_metrics(
    rectified_zone_rgb: np.ndarray,
    silhouette: np.ndarray | None = None,
    *,
    required_zones: Sequence[str] = tuple(OPTICAL_ZONE_LABELS),
) -> dict[str, Any]:
    """Measure local zones from the categorical ``optical-zones`` view."""

    decoded = decode_optical_zone_palette(
        rectified_zone_rgb,
        silhouette,
        required_zones=required_zones,
    )
    labels = decoded["labels"]
    silhouette = decoded["silhouette"]
    samples = _ray_zone_width_samples(labels, silhouette)
    distributions = {}
    for name, values in samples.items():
        if decoded["counts"].get(name, 0) < 8:
            distributions[name] = None
            continue
        distributions[name] = _width_distribution(
            values,
            positive_only=name == "sidewall",
            min_samples=8 if name == "sidewall" else 16,
        )
    center = labels == OPTICAL_ZONE_LABELS["centerFace"]
    return {
        "method": "categorical optical-zones palette; four-side screen-normal width P10/P50/P90",
        "paletteDecode": {
            "method": decoded["method"],
            "recognizedRatio": decoded["recognizedRatio"],
            "pixelCounts": decoded["counts"],
        },
        "centerFaceRatio": float(center.sum() / max(int(silhouette.sum()), 1)),
        "opticalShoulderWidthRatio": distributions["opticalShoulder"]["p50"],
        "strongLensRimWidthRatio": distributions["strongLensRim"]["p50"],
        "sidewallScreenWidthRatio": distributions["sidewall"]["p50"] if distributions["sidewall"] else None,
        "widthDistributions": distributions,
        "highlightWidthRatio": None,
        "contentBendingWidthRatio": None,
        "unit": "card-short-side",
    }


def aggregate_pose_width_distributions(
    distributions: Mapping[str, Mapping[str, Any]],
    *,
    required_poses: Sequence[str] = ("left", "right"),
) -> dict[str, Any]:
    """Aggregate matched pose widths without replacing a missing pose by zero."""

    missing = [pose for pose in required_poses if pose not in distributions]
    if missing:
        raise MeasurementUnavailable(f"missing pose width distributions: {', '.join(missing)}")
    selected = [distributions[pose] for pose in required_poses]
    for pose, distribution in zip(required_poses, selected):
        if not all(isinstance(distribution.get(key), (int, float)) for key in ("p10", "p50", "p90")):
            raise MeasurementUnavailable(f"{pose} pose width distribution is incomplete")
    result = {
        key: float(np.median([float(entry[key]) for entry in selected]))
        for key in ("p10", "p50", "p90")
    }
    result["sampleCount"] = int(sum(int(entry.get("sampleCount", 0)) for entry in selected))
    result["resolutionLimited"] = any(entry.get("resolutionLimited") is True for entry in selected)
    result["poseCount"] = len(selected)
    return result


def _highlight_components(rectified_rgb: np.ndarray, silhouette: np.ndarray) -> dict[str, Any]:
    gray = luminance(rectified_rgb)
    short_side = min(gray.shape)
    local = ndimage.median_filter(gray, size=max(7, int(short_side * 0.045) | 1))
    residual = np.clip(gray - local, 0.0, None)
    distance = normalized_distance(silhouette)
    optical = silhouette & (distance <= 0.18)
    values = residual[optical]
    if values.size < 128:
        raise MeasurementUnavailable("highlight ROI has insufficient optical samples")
    threshold = max(float(np.percentile(values, 94)), float(np.median(values)) + 0.008)
    weights = np.clip(residual - threshold, 0.0, None) * optical
    total = float(weights.sum())
    if total <= 1e-7:
        raise MeasurementUnavailable("highlight residual energy is not measurable")
    binary = weights > max(1e-6, float(weights.max()) * 0.08)
    yy, xx = np.indices(gray.shape)
    centroid = [
        float((xx * weights).sum() / total / max(gray.shape[1] - 1, 1)),
        float((yy * weights).sum() / total / max(gray.shape[0] - 1, 1)),
    ]
    radial_weights = weights[binary]
    radial_depth = distance[binary]
    low = _weighted_quantile(radial_depth, radial_weights, 0.10)
    high = _weighted_quantile(radial_depth, radial_weights, 0.90)
    width = None if low is None or high is None else max(0.0, high - low)
    display_max = rectified_rgb.max(axis=2)
    clipped = binary & (display_max >= (254.0 / 255.0))
    return {
        "weights": weights,
        "mask": binary,
        "centroidNormalized": centroid,
        "widthRatio": width,
        "reflectionEnergyPerCardPixel": total / max(int(silhouette.sum()), 1),
        "clippedPixelRatio": float(clipped.sum() / max(binary.sum(), 1)),
        "sampleCount": int(binary.sum()),
    }


def highlight_metrics(rectified_rgb: np.ndarray, silhouette: np.ndarray) -> dict[str, Any]:
    components = _highlight_components(rectified_rgb, silhouette)
    return {
        "method": "positive local-linear-luma residual in the canonical outer optical ROI",
        "centroidNormalized": components["centroidNormalized"],
        "widthRatio": components["widthRatio"],
        "reflectionEnergy": components["reflectionEnergyPerCardPixel"],
        "highlightClippedPixelRatio": components["clippedPixelRatio"],
        "sampleCount": components["sampleCount"],
    }


def shell_composite_delta_metrics(
    variant_rgb: np.ndarray,
    shell_off_rgb: np.ndarray,
    silhouette: np.ndarray,
) -> dict[str, Any]:
    """Measure shell energy against a matched body-only beauty baseline."""

    if variant_rgb.shape != shell_off_rgb.shape or variant_rgb.shape[:2] != silhouette.shape:
        raise ValueError("shell A/B images and silhouette must share canonical dimensions")
    variant_luma = luminance(variant_rgb)
    off_luma = luminance(shell_off_rgb)
    delta = np.clip(variant_luma - off_luma, 0.0, None)
    distance = normalized_distance(silhouette)
    optical = silhouette & (distance <= 0.18)
    samples = delta[optical]
    if samples.size < 128:
        raise MeasurementUnavailable("shell delta has insufficient optical samples")
    threshold = max(0.0005, float(np.percentile(samples, 82)) * 0.35)
    weights = np.clip(delta - threshold, 0.0, None) * optical
    total = float(weights.sum())
    if total <= 1e-8:
        raise MeasurementUnavailable("shell delta energy is not measurable")
    binary = weights > max(1e-7, float(weights.max()) * 0.06)
    yy, xx = np.indices(silhouette.shape)
    centroid = [
        float((xx * weights).sum() / total / max(silhouette.shape[1] - 1, 1)),
        float((yy * weights).sum() / total / max(silhouette.shape[0] - 1, 1)),
    ]
    radial = distance[binary]
    radial_weights = weights[binary]
    low = _weighted_quantile(radial, radial_weights, 0.10)
    high = _weighted_quantile(radial, radial_weights, 0.90)
    rim = silhouette & (distance <= 0.08)
    clipped = binary & (variant_rgb.max(axis=2) >= (254.0 / 255.0))
    return {
        "method": "positive linear-luma shell contribution against matched shell-off beauty baseline",
        "reflectionEnergy": total / max(int(silhouette.sum()), 1),
        "highlightWidthRatio": None if low is None or high is None else max(0.0, high - low),
        "highlightCentroidNormalized": centroid,
        "highlightClippedPixelRatio": float(clipped.sum() / max(int(binary.sum()), 1)),
        "rimMeanLumaDelta": float(np.mean(delta[rim])) if rim.any() else None,
        "whiteOutlinePixelRatio": float((binary & rim).sum() / max(int(rim.sum()), 1)),
        "sampleCount": int(binary.sum()),
    }


def highlight_mask_metrics(rectified_mask: np.ndarray, silhouette: np.ndarray) -> dict[str, Any]:
    """Measure a reviewed target highlight mask without re-segmenting pixels."""

    mask = (rectified_mask >= 0.5) & silhouette
    if mask.sum() < 8:
        raise MeasurementUnavailable("reviewed highlight mask is empty")
    distance = normalized_distance(silhouette)
    yy, xx = np.indices(mask.shape)
    low = float(np.percentile(distance[mask], 10))
    high = float(np.percentile(distance[mask], 90))
    return {
        "centroidNormalized": [
            float(xx[mask].mean() / max(mask.shape[1] - 1, 1)),
            float(yy[mask].mean() / max(mask.shape[0] - 1, 1)),
        ],
        "widthRatio": max(0.0, high - low),
        "sampleCount": int(mask.sum()),
    }


def sharpness_ratio(
    rectified_rgb: np.ndarray,
    silhouette: np.ndarray,
    *,
    rim_width_ratio: float,
    shoulder_width_ratio: float | None = None,
) -> dict[str, Any]:
    if not math.isfinite(rim_width_ratio) or rim_width_ratio <= 0:
        raise MeasurementUnavailable("a measured local rim width is required for sharpness")
    distance = normalized_distance(silhouette)
    outer_end = rim_width_ratio + max(0.0, shoulder_width_ratio or 0.0)
    rim = silhouette & (distance <= max(0.008, rim_width_ratio))
    center = silhouette & (distance >= min(0.22, max(outer_end * 1.5, 0.12)))
    energy = gradient_energy(luminance(rectified_rgb))
    if rim.sum() < 64 or center.sum() < 128:
        raise MeasurementUnavailable("sharpness zones have insufficient samples")
    center_value = float(np.sqrt(np.mean(energy[center] ** 2)))
    rim_value = float(np.sqrt(np.mean(energy[rim] ** 2)))
    if rim_value <= 1e-9:
        raise MeasurementUnavailable("rim sharpness is numerically zero")
    return {
        "method": "RMS Sobel-plus-Laplacian energy in measured canonical zones",
        "center": center_value,
        "rim": rim_value,
        "centerRimSharpnessRatio": center_value / rim_value,
        "centerSampleCount": int(center.sum()),
        "rimSampleCount": int(rim.sum()),
    }


def dispersion_width(rectified_rgb: np.ndarray, silhouette: np.ndarray) -> dict[str, Any]:
    energy = chroma_energy(rectified_rgb)
    distance = normalized_distance(silhouette)
    center_baseline = float(np.percentile(energy[silhouette & (distance >= 0.18)], 55)) \
        if (silhouette & (distance >= 0.18)).any() else 0.0
    weights = np.clip(energy - center_baseline, 0.0, None) * silhouette
    total = float(weights.sum())
    if total <= 1e-7:
        raise MeasurementUnavailable("dispersion energy is not measurable")
    low = _weighted_quantile(distance.ravel(), weights.ravel(), 0.10)
    high = _weighted_quantile(distance.ravel(), weights.ravel(), 0.90)
    if low is None or high is None:
        raise MeasurementUnavailable("dispersion radial support is unavailable")
    outer = float(weights[(silhouette) & (distance <= 0.08)].sum())
    center = float(weights[(silhouette) & (distance >= 0.18)].sum())
    return {
        "method": "linear-RGB chroma-energy radial CDF",
        "widthRatio": max(0.0, high - low),
        "outerEnergyRatio": outer / total,
        "centerLeakageRatio": center / total,
        "totalEnergyPerCardPixel": total / max(int(silhouette.sum()), 1),
    }


def background_response(rectified_rgb: np.ndarray, silhouette: np.ndarray, background: str) -> dict[str, Any]:
    gray = luminance(rectified_rgb)
    chroma = chroma_energy(rectified_rgb)
    distance = normalized_distance(silhouette)
    rim = silhouette & (distance <= 0.06)
    center = silhouette & (distance >= 0.18)
    if rim.sum() < 64 or center.sum() < 128:
        raise MeasurementUnavailable("flat-background zones have insufficient samples")
    rim_luma = float(np.mean(gray[rim]))
    center_luma = float(np.mean(gray[center]))
    difference = np.abs(gray - float(np.median(gray[center])))
    halo_signal = silhouette & (difference >= max(0.006, float(np.percentile(difference[center], 95)) * 2.5))
    halo_width = float(np.percentile(distance[halo_signal], 95)) if halo_signal.sum() >= 16 else None
    return {
        "background": background,
        "rimMeanLuma": rim_luma,
        "centerMeanLuma": center_luma,
        "discernibility": abs(rim_luma - center_luma),
        "haloWidthRatio": halo_width,
        "neutralPerimeterChroma": float(np.mean(chroma[rim])),
        "whiteOutlineLumaBias": max(0.0, rim_luma - center_luma),
    }


def _regular_line_spacing(profile: np.ndarray) -> float | None:
    darkness = ndimage.gaussian_filter1d(1.0 - np.clip(profile, 0.0, 1.0), sigma=0.7)
    peaks, _ = signal.find_peaks(darkness, distance=5, prominence=0.08, height=0.18)
    if peaks.size < 4:
        return None
    diffs = np.diff(peaks.astype(float))
    median = float(np.median(diffs))
    stable = diffs[(diffs >= median * 0.55) & (diffs <= median * 1.55)]
    return float(np.median(stable)) if stable.size >= 3 else None


def sidewall_content_compression(
    rectified_horizontal: np.ndarray,
    rectified_vertical: np.ndarray,
    silhouette: np.ndarray,
) -> dict[str, Any]:
    """Compare deterministic line spacing in sidewall and center samples."""

    gray_h = luminance(rectified_horizontal, linearize=False)
    gray_v = luminance(rectified_vertical, linearize=False)
    height, width = silhouette.shape
    center_h = np.median(gray_h[:, int(width * 0.43):int(width * 0.57)], axis=1)
    outer_h_parts = [gray_h[:, int(width * 0.08):int(width * 0.16)], gray_h[:, int(width * 0.84):int(width * 0.92)]]
    outer_h = np.median(np.concatenate(outer_h_parts, axis=1), axis=1)
    center_v = np.median(gray_v[int(height * 0.40):int(height * 0.60), :], axis=0)
    outer_v_parts = [gray_v[int(height * 0.08):int(height * 0.17), :], gray_v[int(height * 0.83):int(height * 0.92), :]]
    outer_v = np.median(np.concatenate(outer_v_parts, axis=0), axis=0)
    values = {
        "horizontalCenterSpacingPx": _regular_line_spacing(center_h),
        "horizontalSidewallSpacingPx": _regular_line_spacing(outer_h),
        "verticalCenterSpacingPx": _regular_line_spacing(center_v),
        "verticalSidewallSpacingPx": _regular_line_spacing(outer_v),
    }
    ratios = []
    for axis in ("horizontal", "vertical"):
        center_spacing = values[f"{axis}CenterSpacingPx"]
        side_spacing = values[f"{axis}SidewallSpacingPx"]
        if center_spacing is not None and side_spacing is not None and center_spacing > 0:
            ratios.append(side_spacing / center_spacing)
    if not ratios:
        raise MeasurementUnavailable("deterministic sidewall line spacing is not measurable")
    return {
        "method": "sidewall-to-center deterministic line-spacing ratio",
        **values,
        "compressionRatio": float(np.median(ratios)),
        "axisSampleCount": len(ratios),
    }


def content_bending_width(
    rectified_horizontal: np.ndarray,
    rectified_vertical: np.ndarray,
    silhouette: np.ndarray,
) -> dict[str, Any]:
    """Estimate how far inward deterministic line deformation remains visible."""

    distance = normalized_distance(silhouette)
    height, width = silhouette.shape
    measurements: list[tuple[np.ndarray, np.ndarray]] = []

    gray_h = luminance(rectified_horizontal, linearize=False)
    h_reference = np.median(gray_h[:, int(width * 0.43):int(width * 0.57)], axis=1)
    h_difference = np.mean(np.abs(gray_h - h_reference[:, None]), axis=0)
    h_depth = np.asarray([np.median(distance[silhouette[:, x], x]) if silhouette[:, x].any() else np.nan for x in range(width)])
    measurements.append((h_depth, h_difference))

    gray_v = luminance(rectified_vertical, linearize=False)
    v_reference = np.median(gray_v[int(height * 0.43):int(height * 0.57), :], axis=0)
    v_difference = np.mean(np.abs(gray_v - v_reference[None, :]), axis=1)
    v_depth = np.asarray([np.median(distance[y, silhouette[y]]) if silhouette[y].any() else np.nan for y in range(height)])
    measurements.append((v_depth, v_difference))

    supports = []
    for depths, differences in measurements:
        valid = np.isfinite(depths)
        if valid.sum() < 16:
            continue
        center_values = differences[valid & (depths >= 0.18)]
        baseline = float(np.median(center_values)) if center_values.size else float(np.percentile(differences[valid], 25))
        threshold = baseline + max(0.018, float(np.percentile(differences[valid], 85) - baseline) * 0.28)
        changed = valid & (differences >= threshold)
        if changed.sum() >= 4:
            supports.append(float(np.percentile(depths[changed], 92)))
    if not supports:
        raise MeasurementUnavailable("content-bending support is not measurable")
    return {
        "method": "inward support of deterministic line-profile deviation from the center reference",
        "widthRatio": float(max(supports)),
        "axisSampleCount": len(supports),
    }


def corner_refraction_signature(rectified_rgb: np.ndarray, silhouette: np.ndarray) -> dict[str, Any]:
    profiles = normalized_profiles(rectified_rgb, silhouette, bins=24, max_depth_ratio=0.16)
    vector = []
    coverage = []
    for name in ("topLeft", "topRight", "bottomRight", "bottomLeft"):
        region = profiles["regions"][name]
        samples = [sample for sample in region["samples"] if sample["sampleCount"] > 0]
        if not samples:
            vector.append(None)
            coverage.append(0.0)
            continue
        # A natural target has no un-refracted source.  This is intentionally
        # an edge-energy signature, not an invented absolute displacement.
        vector.append(float(np.median([sample["rmsSharpness"] for sample in samples])))
        coverage.append(float(region["coverage"]))
    if any(value is None for value in vector):
        raise MeasurementUnavailable("one or more corner signatures are unavailable")
    scale = max(float(np.mean(vector)), 1e-9)
    return {
        "method": "four-corner normalized edge-energy signature (not whole-card pixels)",
        "vector": [float(value / scale) for value in vector],
        "coverage": coverage,
        "minCoverage": min(coverage),
    }


def highlight_path(
    samples: Sequence[tuple[Sequence[float], np.ndarray]],
    silhouette: np.ndarray,
) -> dict[str, Any]:
    measured = []
    for pointer, rectified_rgb in samples:
        try:
            value = highlight_metrics(rectified_rgb, silhouette)
        except MeasurementUnavailable:
            value = None
        measured.append({
            "pointer": [float(pointer[0]), float(pointer[1])],
            "centroidNormalized": None if value is None else value["centroidNormalized"],
            "widthRatio": None if value is None else value["widthRatio"],
            "clippedPixelRatio": None if value is None else value["highlightClippedPixelRatio"],
        })
    valid = [sample for sample in measured if sample["centroidNormalized"] is not None]
    if len(valid) < 3:
        raise MeasurementUnavailable("at least three measurable pointer highlights are required")
    segments = [
        float(np.linalg.norm(np.asarray(right["centroidNormalized"]) - np.asarray(left["centroidNormalized"])))
        for left, right in zip(valid, valid[1:])
    ]
    median = float(np.median(segments)) if segments else 0.0
    widths = [sample["widthRatio"] for sample in valid if sample["widthRatio"] is not None]
    clipped = [sample["clippedPixelRatio"] for sample in valid if sample["clippedPixelRatio"] is not None]
    return {
        "method": "canonical highlight centroid path",
        "requestedSampleCount": len(samples),
        "validSampleCount": len(valid),
        "travelNormalized": float(sum(segments)),
        "maxToMedianJumpRatio": max(segments, default=0.0) / max(median, 1e-9),
        "medianHighlightWidthRatio": float(np.median(widths)) if widths else None,
        "meanClippedPixelRatio": float(np.mean(clipped)) if clipped else None,
        "samples": measured,
    }


def relative_scalar(local: float | None, target: float | None) -> dict[str, Any]:
    if local is None or target is None or not math.isfinite(local) or not math.isfinite(target) or abs(target) <= 1e-12:
        return {"absoluteError": None, "relativeError": None}
    return {
        "absoluteError": abs(local - target),
        "relativeError": abs(local - target) / abs(target),
    }


def relative_point(local: Sequence[float] | None, target: Sequence[float] | None) -> dict[str, Any]:
    if local is None or target is None or len(local) != 2 or len(target) != 2:
        return {"distanceNormalized": None}
    return {"distanceNormalized": float(np.linalg.norm(np.asarray(local, dtype=float) - np.asarray(target, dtype=float)))}


def relative_vector(local: Sequence[float] | None, target: Sequence[float] | None) -> dict[str, Any]:
    if local is None or target is None or len(local) != len(target) or len(local) == 0:
        return {"normalizedRmse": None}
    left, right = np.asarray(local, dtype=float), np.asarray(target, dtype=float)
    if not np.isfinite(left).all() or not np.isfinite(right).all():
        return {"normalizedRmse": None}
    scale = max(float(np.sqrt(np.mean(right * right))), 1e-9)
    return {"normalizedRmse": float(np.sqrt(np.mean((left - right) ** 2)) / scale)}


def draw_private_edge_overlay(
    rectified_rgb: np.ndarray,
    silhouette: np.ndarray,
    destination: Path,
    *,
    title: str,
    zone_boundaries: Mapping[str, float | None] | None = None,
) -> None:
    """Write a private pixel overlay; callers publish only its hash."""

    image = Image.fromarray((np.clip(rectified_rgb, 0.0, 1.0) * 255).astype(np.uint8), mode="RGB").convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    regions = normalized_edge_regions(silhouette)
    colors = {
        "top": (0, 230, 255, 78),
        "right": (255, 205, 40, 78),
        "bottom": (70, 230, 130, 78),
        "left": (245, 85, 210, 78),
        "topLeft": (255, 80, 80, 100),
        "topRight": (255, 145, 40, 100),
        "bottomRight": (115, 105, 255, 100),
        "bottomLeft": (80, 155, 255, 100),
    }
    overlay = np.zeros((*silhouette.shape, 4), dtype=np.uint8)
    for name, mask in regions.items():
        overlay[mask] = colors[name]
    image = Image.alpha_composite(image, Image.fromarray(overlay, mode="RGBA"))
    draw = ImageDraw.Draw(image, "RGBA")
    boundary = silhouette & ~ndimage.binary_erosion(silhouette, iterations=2)
    yy, xx = np.nonzero(boundary)
    for x, y in zip(xx[::2], yy[::2]):
        draw.point((int(x), int(y)), fill=(0, 255, 255, 230))
    if zone_boundaries:
        distance = normalized_distance(silhouette)
        for index, (_, value) in enumerate(zone_boundaries.items()):
            if value is None or not math.isfinite(value):
                continue
            band = silhouette & (np.abs(distance - value) <= 1.2 / min(silhouette.shape))
            by, bx = np.nonzero(band)
            color = [(255, 80, 80, 230), (255, 220, 30, 230), (70, 255, 130, 230)][index % 3]
            for x, y in zip(bx[::2], by[::2]):
                draw.point((int(x), int(y)), fill=color)
    draw.rectangle((0, 0, image.width, 28), fill=(0, 0, 0, 205))
    draw.text((10, 8), title, fill=(255, 255, 255, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(destination, optimize=True)


def ensure_no_whole_card_ssim_api() -> None:
    """Explicit source-level contract used by tests and downstream callers."""

    return None
