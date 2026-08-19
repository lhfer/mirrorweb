#!/usr/bin/env python3
"""Extract a private Frozen Visual reference set from the target recording.

The generated PNG frames, crops, masks, overlays, and private manifest stay under
the caller supplied output root.  ``frozen-visual.sanitized.json`` deliberately
contains no source/output paths and no image payloads; it is safe to validate
against ``qa-v4/reference/roi-mask.schema.json`` and review for publication.

This is an initial, fail-visible segmentation pass.  It uses only deterministic
image measurements and never treats the annotated screenshot as pixel evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import subprocess
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

import numpy as np
import PIL
import scipy
import skimage
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from skimage import filters, measure, morphology, transform

warnings.filterwarnings("ignore", category=FutureWarning, message=r".*deprecated.*")


ALGORITHM_ID = "mirrorweb-frozen-visual-roi"
ALGORITHM_VERSION = "1.0.0"
ANALYSIS_MAX_SIDE = 960
ANALYSIS_STRIDE_FRAMES = 3
CANONICAL_SIZE = (768, 448)

CATEGORY_IDS = (
    "bright-front",
    "dark-front",
    "high-texture",
    "low-texture",
    "left-tilt",
    "right-tilt",
    "pointer-before",
    "pointer-after",
)

MASK_NAMES = (
    "card-silhouette",
    "center-face",
    "optical-shoulder",
    "lens-rim",
    "sidewall",
    "highlight",
    "typography",
    "gutter",
)

MASK_COLORS = {
    "center-face": (36, 220, 130),
    "optical-shoulder": (255, 205, 46),
    "lens-rim": (238, 74, 214),
    "sidewall": (255, 72, 72),
    "highlight": (255, 255, 255),
    "typography": (60, 155, 255),
    "gutter": (90, 100, 120),
}


class ExtractionError(RuntimeError):
    """An actionable failure that prevents a trustworthy reference set."""


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    frame_rate_num: int
    frame_rate_den: int
    frame_count: int
    duration_seconds: float

    @property
    def fps(self) -> float:
        return self.frame_rate_num / self.frame_rate_den


@dataclass
class Candidate:
    frame_index: int
    bbox_n: tuple[float, float, float, float]
    center_n: tuple[float, float]
    clipped: bool
    luminance: float
    contrast: float
    texture: float
    entropy: float
    sharpness: float
    frame_motion: float
    tilt_deg: float
    highlight_n: tuple[float, float] | None
    highlight_strength: float
    quality: float = 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build private Frozen Visual frames, masks, overlays, and a sanitized metric summary.",
    )
    parser.add_argument("target_mp4", type=Path, help="Clean, unannotated frozen target MP4")
    parser.add_argument("output_root", type=Path, help="Private output root (must not be published)")
    parser.add_argument(
        "--sanitized-output",
        type=Path,
        default=None,
        help="Optional sanitized JSON destination; defaults inside output_root",
    )
    parser.add_argument(
        "--analysis-stride",
        type=int,
        default=ANALYSIS_STRIDE_FRAMES,
        help="Analyze every Nth source frame (default: 3)",
    )
    return parser.parse_args()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_json(args: Sequence[str]) -> dict[str, Any]:
    result = subprocess.run(args, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        raise ExtractionError(result.stderr.strip() or f"Command failed: {args[0]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ExtractionError(f"Invalid JSON from {args[0]}: {error}") from error


def parse_rate(value: str | None) -> tuple[int, int]:
    fields = str(value or "0/1").split("/", maxsplit=1)
    numerator = int(fields[0])
    denominator = int(fields[1]) if len(fields) == 2 else 1
    if numerator <= 0 or denominator <= 0:
        raise ExtractionError(f"Invalid video frame rate: {value}")
    return numerator, denominator


def probe_video(path: Path) -> VideoInfo:
    data = run_json(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,avg_frame_rate,r_frame_rate,nb_frames",
            "-of",
            "json",
            str(path),
        ],
    )
    stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), None)
    if stream is None:
        raise ExtractionError("Target contains no video stream")
    numerator, denominator = parse_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
    duration = float(data.get("format", {}).get("duration") or 0.0)
    encoded_count = int(stream.get("nb_frames") or 0)
    frame_count = encoded_count if encoded_count > 0 else int(round(duration * numerator / denominator))
    if int(stream.get("width") or 0) <= 0 or int(stream.get("height") or 0) <= 0 or frame_count <= 0:
        raise ExtractionError("Target video metadata is incomplete")
    return VideoInfo(
        width=int(stream["width"]),
        height=int(stream["height"]),
        frame_rate_num=numerator,
        frame_rate_den=denominator,
        frame_count=frame_count,
        duration_seconds=duration,
    )


def analysis_dimensions(info: VideoInfo) -> tuple[int, int]:
    scale = min(1.0, ANALYSIS_MAX_SIDE / max(info.width, info.height))
    width = max(2, int(round(info.width * scale)))
    height = max(2, int(round(info.height * scale)))
    return width, height


def read_exact(stream: Any, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def decode_analysis_frames(path: Path, info: VideoInfo, stride: int) -> Iterator[tuple[int, np.ndarray]]:
    width, height = analysis_dimensions(info)
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"scale={width}:{height}:flags=lanczos,format=rgb24",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None:
        raise ExtractionError("ffmpeg did not expose decoded video output")
    frame_bytes = width * height * 3
    frame_index = 0
    try:
        while True:
            payload = read_exact(process.stdout, frame_bytes)
            if not payload:
                break
            if len(payload) != frame_bytes:
                raise ExtractionError("ffmpeg returned a truncated decoded frame")
            if frame_index % stride == 0:
                rgb = np.frombuffer(payload, dtype=np.uint8).reshape((height, width, 3)).copy()
                yield frame_index, rgb
            frame_index += 1
    finally:
        if process.stdout:
            process.stdout.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
        return_code = process.wait()
        if return_code != 0:
            raise ExtractionError(stderr.strip() or "ffmpeg analysis decode failed")


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    value = rgb.astype(np.float32) / 255.0
    return np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)


def luma_linear(rgb: np.ndarray) -> np.ndarray:
    linear = srgb_to_linear(rgb)
    return 0.2126 * linear[..., 0] + 0.7152 * linear[..., 1] + 0.0722 * linear[..., 2]


def luma_display(rgb: np.ndarray) -> np.ndarray:
    value = rgb.astype(np.float32) / 255.0
    return 0.2126 * value[..., 0] + 0.7152 * value[..., 1] + 0.0722 * value[..., 2]


def runs_below(values: np.ndarray, cutoff: float, min_length: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value <= cutoff and start is None:
            start = index
        elif value > cutoff and start is not None:
            if index - start >= min_length:
                result.append((start, index - 1))
            start = None
    if start is not None and len(values) - start >= min_length:
        result.append((start, len(values) - 1))
    return result


def robust_line(points: np.ndarray) -> tuple[float, float] | None:
    if len(points) < 8:
        return None
    x = points[:, 0].astype(np.float64)
    y = points[:, 1].astype(np.float64)
    keep = np.ones(len(points), dtype=bool)
    for _ in range(4):
        if keep.sum() < 8:
            return None
        slope, intercept = np.polyfit(x[keep], y[keep], 1)
        residual = np.abs(y - (slope * x + intercept))
        median = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - median))) + 1e-6
        keep = residual <= median + 3.5 * mad
    return float(slope), float(intercept)


def estimate_top_tilt(gray: np.ndarray) -> float:
    height, width = gray.shape
    if width < 40 or height < 30:
        return 0.0
    edge = filters.scharr(gray)
    points: list[tuple[float, float]] = []
    x_values = np.linspace(int(width * 0.18), int(width * 0.82), 48).astype(int)
    top_limit = max(4, int(height * 0.30))
    threshold = float(np.percentile(edge[:top_limit], 65))
    for x in x_values:
        column = edge[:top_limit, x]
        y = int(np.argmax(column))
        if column[y] >= threshold:
            points.append((float(x), float(y)))
    fitted = robust_line(np.asarray(points)) if points else None
    return math.degrees(math.atan(fitted[0])) if fitted else 0.0


def rough_highlight(gray: np.ndarray, rgb: np.ndarray) -> tuple[tuple[float, float] | None, float]:
    height, width = gray.shape
    yy, xx = np.mgrid[:height, :width]
    edge_distance = np.minimum.reduce((xx, width - 1 - xx, yy, height - 1 - yy)).astype(np.float32)
    rim_prior = edge_distance <= 0.18 * min(width, height)
    value = rgb.astype(np.float32) / 255.0
    chroma = value.max(axis=2) - value.min(axis=2)
    local = ndi.median_filter(gray, size=max(5, int(min(width, height) * 0.045) | 1))
    residual = gray - local
    valid = rim_prior & (chroma < 0.24)
    if not valid.any():
        return None, 0.0
    threshold = max(0.06, float(np.percentile(residual[valid], 98.8)))
    mask = valid & (residual >= threshold)
    if mask.sum() < 4:
        return None, 0.0
    weights = np.maximum(residual[mask], 1e-5)
    ys, xs = np.where(mask)
    cx = float(np.average(xs, weights=weights) / max(width - 1, 1))
    cy = float(np.average(ys, weights=weights) / max(height - 1, 1))
    strength = float(np.mean(residual[mask]))
    return (cx, cy), strength


def candidate_features(
    rgb: np.ndarray,
    bbox: tuple[int, int, int, int],
    frame_index: int,
    frame_motion: float,
) -> Candidate | None:
    frame_height, frame_width = rgb.shape[:2]
    x0, y0, x1, y1 = bbox
    width, height = x1 - x0, y1 - y0
    if width < frame_width * 0.09 or height < frame_height * 0.10:
        return None
    crop = rgb[y0:y1, x0:x1]
    inset_x = max(2, int(width * 0.12))
    inset_top = max(2, int(height * 0.14))
    inset_bottom = max(inset_top + 1, int(height * 0.76))
    inner = crop[inset_top:inset_bottom, inset_x : width - inset_x]
    if inner.size == 0:
        return None
    gray = luma_linear(inner)
    display_gray = luma_display(inner)
    gradient = filters.sobel(display_gray)
    histogram, _ = np.histogram(display_gray, bins=32, range=(0.0, 1.0), density=False)
    probabilities = histogram[histogram > 0] / max(histogram.sum(), 1)
    entropy = float(-(probabilities * np.log2(probabilities)).sum())
    highlight, highlight_strength = rough_highlight(luma_display(crop), crop)
    clipped = x0 <= 2 or y0 <= 2 or x1 >= frame_width - 2 or y1 >= frame_height - 2
    return Candidate(
        frame_index=frame_index,
        bbox_n=(x0 / frame_width, y0 / frame_height, width / frame_width, height / frame_height),
        center_n=((x0 + x1) / (2 * frame_width), (y0 + y1) / (2 * frame_height)),
        clipped=clipped,
        luminance=float(np.median(gray)),
        contrast=float(np.percentile(gray, 90) - np.percentile(gray, 10)),
        texture=float(np.mean(gradient)),
        entropy=entropy,
        sharpness=float(np.var(filters.laplace(display_gray))),
        frame_motion=frame_motion,
        tilt_deg=estimate_top_tilt(luma_display(crop)),
        highlight_n=highlight,
        highlight_strength=highlight_strength,
    )


def detect_candidates(rgb: np.ndarray, frame_index: int, frame_motion: float) -> list[Candidate]:
    height, width = rgb.shape[:2]
    display_y = luma_display(rgb)
    value = rgb.astype(np.float32) / 255.0
    chroma = value.max(axis=2) - value.min(axis=2)
    dark_cutoff = min(0.14, max(0.035, float(np.percentile(display_y, 14)) * 1.65))
    gutter = (display_y <= dark_cutoff) & (chroma <= 0.24)
    gutter = morphology.binary_opening(gutter, morphology.disk(1))
    gutter[-max(8, height // 24) :, :] = True

    row_signal = ndi.uniform_filter1d(gutter.mean(axis=1), size=max(5, height // 90))
    row_bands = runs_below(row_signal, 0.50, max(20, height // 12))
    candidates: list[Candidate] = []
    for y0, y1 in row_bands:
        row_gap = gutter[y0 : y1 + 1]
        column_signal = ndi.uniform_filter1d(row_gap.mean(axis=0), size=max(5, width // 110))
        column_bands = runs_below(column_signal, 0.62, max(36, width // 12))
        for x0, x1 in column_bands:
            cell = ~gutter[y0 : y1 + 1, x0 : x1 + 1]
            if cell.size == 0 or float(cell.mean()) < 0.14:
                continue
            row_coverage = cell.mean(axis=1)
            col_coverage = cell.mean(axis=0)
            ys = np.where(row_coverage > 0.15)[0]
            xs = np.where(col_coverage > 0.15)[0]
            if len(xs) < 8 or len(ys) < 8:
                continue
            rx0, rx1 = x0 + int(xs[0]), x0 + int(xs[-1]) + 1
            ry0, ry1 = y0 + int(ys[0]), y0 + int(ys[-1]) + 1
            pad_x = max(1, int((rx1 - rx0) * 0.008))
            pad_y = max(1, int((ry1 - ry0) * 0.008))
            bbox = (
                max(0, rx0 - pad_x),
                max(0, ry0 - pad_y),
                min(width, rx1 + pad_x),
                min(height, ry1 + pad_y),
            )
            candidate = candidate_features(rgb, bbox, frame_index, frame_motion)
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def percentile_ranks(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    order = np.argsort(array, kind="stable")
    ranks = np.empty(len(array), dtype=np.float64)
    ranks[order] = np.linspace(0.0, 1.0, len(array), endpoint=True) if len(array) > 1 else 0.5
    return ranks


def score_candidates(candidates: list[Candidate]) -> dict[str, np.ndarray]:
    if not candidates:
        raise ExtractionError("No glass card candidates were detected in the frozen target")
    feature_ranks = {
        "luminance": percentile_ranks([item.luminance for item in candidates]),
        "texture": percentile_ranks([item.texture for item in candidates]),
        "entropy": percentile_ranks([item.entropy for item in candidates]),
        "sharpness": percentile_ranks([item.sharpness for item in candidates]),
        "motion": percentile_ranks([item.frame_motion for item in candidates]),
    }
    quality = 0.62 * feature_ranks["sharpness"] + 0.28 * (1.0 - feature_ranks["motion"])
    for index, candidate in enumerate(candidates):
        quality[index] += 0.10 if not candidate.clipped else 0.0
        candidate.quality = float(np.clip(quality[index], 0.0, 1.0))
    return feature_ranks


def candidate_key(candidate: Candidate) -> tuple[int, int, int]:
    return (
        candidate.frame_index,
        int(round(candidate.center_n[0] * 100)),
        int(round(candidate.center_n[1] * 100)),
    )


def choose_visual_categories(candidates: list[Candidate], ranks: dict[str, np.ndarray]) -> dict[str, Candidate]:
    used: set[tuple[int, int, int]] = set()
    selected: dict[str, Candidate] = {}
    roles = ("bright-front", "dark-front", "high-texture", "low-texture", "left-tilt", "right-tilt")
    for role in roles:
        scores: list[tuple[float, int]] = []
        for index, candidate in enumerate(candidates):
            frontness = 1.0 - min(abs(candidate.tilt_deg) / 6.0, 1.0)
            leftness = float(np.clip((0.52 - candidate.center_n[0]) / 0.52, 0.0, 1.0))
            rightness = float(np.clip((candidate.center_n[0] - 0.48) / 0.52, 0.0, 1.0))
            tilt_magnitude = min(abs(candidate.tilt_deg) / 5.0, 1.0)
            visible = 1.0 if not candidate.clipped else 0.25
            if role == "bright-front":
                score = 0.50 * ranks["luminance"][index] + 0.22 * frontness + 0.18 * candidate.quality + 0.10 * visible
            elif role == "dark-front":
                score = 0.50 * (1.0 - ranks["luminance"][index]) + 0.22 * frontness + 0.18 * candidate.quality + 0.10 * visible
            elif role == "high-texture":
                score = 0.40 * ranks["texture"][index] + 0.22 * ranks["entropy"][index] + 0.20 * candidate.quality + 0.18 * visible
            elif role == "low-texture":
                score = 0.40 * (1.0 - ranks["texture"][index]) + 0.22 * (1.0 - ranks["entropy"][index]) + 0.20 * candidate.quality + 0.18 * visible
            elif role == "left-tilt":
                score = 0.40 * leftness + 0.23 * tilt_magnitude + 0.22 * candidate.quality + 0.15 * visible
            else:
                score = 0.40 * rightness + 0.23 * tilt_magnitude + 0.22 * candidate.quality + 0.15 * visible
            key = candidate_key(candidate)
            if key in used:
                score -= 0.55
            if any(abs(candidate.frame_index - item.frame_index) < 5 for item in selected.values()):
                score -= 0.08
            scores.append((float(score), index))
        _, chosen_index = max(scores)
        chosen = candidates[chosen_index]
        selected[role] = chosen
        used.add(candidate_key(chosen))
    return selected


def bbox_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax0, ay0, aw, ah = a
    bx0, by0, bw, bh = b
    ax1, ay1, bx1, by1 = ax0 + aw, ay0 + ah, bx0 + bw, by0 + bh
    intersection = max(0.0, min(ax1, bx1) - max(ax0, bx0)) * max(0.0, min(ay1, by1) - max(ay0, by0))
    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


def choose_pointer_pair(candidates: list[Candidate], stride: int) -> tuple[Candidate, Candidate, float, list[str]]:
    best: tuple[float, Candidate, Candidate, float] | None = None
    by_frame: dict[int, list[Candidate]] = {}
    for candidate in candidates:
        by_frame.setdefault(candidate.frame_index, []).append(candidate)
    frames = sorted(by_frame)
    for frame_a in frames:
        for frame_b in frames:
            delta = frame_b - frame_a
            if delta < stride or delta > 36:
                continue
            for before in by_frame[frame_a]:
                if before.highlight_n is None:
                    continue
                for after in by_frame[frame_b]:
                    if after.highlight_n is None:
                        continue
                    overlap = bbox_iou(before.bbox_n, after.bbox_n)
                    if overlap < 0.70:
                        continue
                    if abs(before.luminance - after.luminance) > 0.28:
                        continue
                    shift = math.dist(before.highlight_n, after.highlight_n)
                    box_drift = math.dist(before.center_n, after.center_n)
                    score = 0.42 * overlap + 0.34 * min(shift / 0.18, 1.0) + 0.18 * min(before.quality, after.quality) - 1.5 * box_drift
                    if best is None or score > best[0]:
                        pair_confidence = float(np.clip(0.45 * overlap + 0.35 * min(shift / 0.12, 1.0) + 0.20 * min(before.quality, after.quality), 0.0, 1.0))
                        best = (score, before, after, pair_confidence)
    if best is not None:
        reasons = [] if best[3] >= 0.62 else ["pointer-pair-highlight-shift-is-ambiguous"]
        return best[1], best[2], best[3], reasons

    fallback = sorted((item for item in candidates if not item.clipped), key=lambda item: item.quality, reverse=True)
    if len(fallback) < 2:
        fallback = sorted(candidates, key=lambda item: item.quality, reverse=True)
    if len(fallback) < 2:
        raise ExtractionError("Could not form a pointer before/after candidate pair")
    return fallback[0], fallback[1], 0.25, ["pointer-pair-fallback-needs-human-confirmation"]


def analyze_video(path: Path, info: VideoInfo, stride: int) -> tuple[dict[str, Candidate], float, list[str]]:
    candidates: list[Candidate] = []
    previous_gray: np.ndarray | None = None
    for frame_index, rgb in decode_analysis_frames(path, info, stride):
        gray = luma_display(rgb)
        frame_motion = 0.0 if previous_gray is None else float(np.median(np.abs(gray - previous_gray)))
        previous_gray = gray
        candidates.extend(detect_candidates(rgb, frame_index, frame_motion))
    ranks = score_candidates(candidates)
    selected = choose_visual_categories(candidates, ranks)
    before, after, pointer_confidence, pointer_reasons = choose_pointer_pair(candidates, stride)
    selected["pointer-before"] = before
    selected["pointer-after"] = after
    if set(selected) != set(CATEGORY_IDS):
        raise ExtractionError("Automatic category assignment did not produce all required Frozen Visual roles")
    return selected, pointer_confidence, pointer_reasons


def extract_frame(video: Path, frame_index: int, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    expression = f"select=eq(n\\,{frame_index})"
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(video),
            "-vf",
            expression,
            "-fps_mode",
            "vfr",
            "-frames:v",
            "1",
            "-y",
            str(destination),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not destination.is_file():
        raise ExtractionError(result.stderr.strip() or f"Could not extract source frame {frame_index}")


def line_points_for_side(
    edge: np.ndarray,
    bbox: tuple[int, int, int, int],
    side: str,
) -> np.ndarray:
    x0, y0, x1, y1 = bbox
    width, height = x1 - x0, y1 - y0
    points: list[tuple[float, float]] = []
    if side in {"top", "bottom"}:
        xs = np.linspace(x0 + 0.20 * width, x1 - 0.20 * width, 72).astype(int)
        if side == "top":
            ya, yb = max(0, y0 - int(0.08 * height)), min(edge.shape[0], y0 + int(0.22 * height))
        else:
            ya, yb = max(0, y1 - int(0.22 * height)), min(edge.shape[0], y1 + int(0.08 * height))
        for x in xs:
            if yb <= ya:
                continue
            values = edge[ya:yb, x]
            y = ya + int(np.argmax(values))
            points.append((float(x), float(y)))
    else:
        ys = np.linspace(y0 + 0.22 * height, y1 - 0.22 * height, 60).astype(int)
        if side == "left":
            xa, xb = max(0, x0 - int(0.08 * width)), min(edge.shape[1], x0 + int(0.18 * width))
        else:
            xa, xb = max(0, x1 - int(0.18 * width)), min(edge.shape[1], x1 + int(0.08 * width))
        for y in ys:
            if xb <= xa:
                continue
            values = edge[y, xa:xb]
            x = xa + int(np.argmax(values))
            points.append((float(y), float(x)))
    return np.asarray(points, dtype=np.float64)


def line_intersection(horizontal: tuple[float, float], vertical: tuple[float, float]) -> tuple[float, float] | None:
    # horizontal: y = ah*x + bh; vertical: x = av*y + bv
    ah, bh = horizontal
    av, bv = vertical
    denominator = 1.0 - av * ah
    if abs(denominator) < 1e-6:
        return None
    x = (av * bh + bv) / denominator
    y = ah * x + bh
    return float(x), float(y)


def polygon_area(points: np.ndarray) -> float:
    x, y = points[:, 0], points[:, 1]
    return float(0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))))


def refine_quad(gray: np.ndarray, bbox: tuple[int, int, int, int]) -> tuple[np.ndarray, bool]:
    edge = filters.scharr(gray)
    fitted: dict[str, tuple[float, float] | None] = {}
    for side in ("top", "bottom", "left", "right"):
        fitted[side] = robust_line(line_points_for_side(edge, bbox, side))
    x0, y0, x1, y1 = bbox
    fallback = np.asarray([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float64)
    if any(fitted[side] is None for side in fitted):
        return fallback, True
    top = fitted["top"]
    bottom = fitted["bottom"]
    left = fitted["left"]
    right = fitted["right"]
    assert top and bottom and left and right
    corners = [
        line_intersection(top, left),
        line_intersection(top, right),
        line_intersection(bottom, right),
        line_intersection(bottom, left),
    ]
    if any(point is None for point in corners):
        return fallback, True
    quad = np.asarray(corners, dtype=np.float64)
    height, width = gray.shape
    bbox_area = max((x1 - x0) * (y1 - y0), 1)
    if (
        not np.isfinite(quad).all()
        or polygon_area(quad) < 0.58 * bbox_area
        or polygon_area(quad) > 1.38 * bbox_area
        or (quad[:, 0] < -0.04 * width).any()
        or (quad[:, 0] > 1.04 * width).any()
        or (quad[:, 1] < -0.04 * height).any()
        or (quad[:, 1] > 1.04 * height).any()
    ):
        return fallback, True
    return quad, False


def canonical_zones(exponent: float) -> dict[str, np.ndarray]:
    width, height = CANONICAL_SIZE
    yy, xx = np.mgrid[:height, :width]
    nx = np.abs((xx - (width - 1) / 2) / ((width - 3) / 2))
    ny = np.abs((yy - (height - 1) / 2) / ((height - 3) / 2))
    silhouette = nx**exponent + ny**exponent <= 1.0
    distance = ndi.distance_transform_edt(silhouette)
    minor = float(min(width, height))
    side_end = 0.012 * minor
    rim_end = 0.065 * minor
    shoulder_end = 0.145 * minor
    return {
        "card-silhouette": silhouette,
        "sidewall": silhouette & (distance <= side_end),
        "lens-rim": silhouette & (distance > side_end) & (distance <= rim_end),
        "optical-shoulder": silhouette & (distance > rim_end) & (distance <= shoulder_end),
        "center-face": silhouette & (distance > shoulder_end),
    }


def warp_boolean(image: np.ndarray, mapping: transform.ProjectiveTransform, shape: tuple[int, int]) -> np.ndarray:
    warped = transform.warp(
        image.astype(np.float32),
        inverse_map=mapping.inverse,
        output_shape=shape,
        order=0,
        preserve_range=True,
        mode="constant",
        cval=0,
    )
    return warped >= 0.5


def boundary_support(mask: np.ndarray, gradient: np.ndarray) -> float:
    boundary = mask & ~morphology.binary_erosion(mask, morphology.disk(2))
    if boundary.sum() < 8:
        return 0.0
    local_values = gradient[boundary]
    reference = float(np.percentile(gradient, 78)) + 1e-7
    return float(np.clip(np.median(local_values) / reference, 0.0, 1.0))


def build_geometric_masks(
    rgb: np.ndarray,
    bbox: tuple[int, int, int, int],
) -> tuple[dict[str, np.ndarray], np.ndarray, float, float, bool]:
    height, width = rgb.shape[:2]
    margin_x = max(4, int((bbox[2] - bbox[0]) * 0.05))
    margin_y = max(4, int((bbox[3] - bbox[1]) * 0.06))
    cx0, cy0 = max(0, bbox[0] - margin_x), max(0, bbox[1] - margin_y)
    cx1, cy1 = min(width, bbox[2] + margin_x), min(height, bbox[3] + margin_y)
    crop = rgb[cy0:cy1, cx0:cx1]
    gray = luma_display(crop)
    local_bbox = (bbox[0] - cx0, bbox[1] - cy0, bbox[2] - cx0, bbox[3] - cy0)
    quad, used_fallback = refine_quad(gray, local_bbox)
    canonical_corners = np.asarray(
        [[0, 0], [CANONICAL_SIZE[0] - 1, 0], [CANONICAL_SIZE[0] - 1, CANONICAL_SIZE[1] - 1], [0, CANONICAL_SIZE[1] - 1]],
        dtype=np.float64,
    )
    mapping = transform.ProjectiveTransform()
    if not mapping.estimate(canonical_corners, quad):
        raise ExtractionError("Could not establish the card perspective transform")

    gradient = filters.scharr(gray)
    best: tuple[float, float, dict[str, np.ndarray]] | None = None
    for exponent in (3.2, 4.0, 4.8, 5.8):
        zones = canonical_zones(exponent)
        silhouette = warp_boolean(zones["card-silhouette"], mapping, gray.shape)
        support = boundary_support(silhouette, gradient)
        if best is None or support > best[0]:
            best = (support, exponent, zones)
    assert best is not None
    support, exponent, canonical = best
    local_masks = {name: warp_boolean(mask, mapping, gray.shape) for name, mask in canonical.items()}
    full_masks: dict[str, np.ndarray] = {}
    for name, local in local_masks.items():
        full = np.zeros((height, width), dtype=bool)
        full[cy0:cy1, cx0:cx1] = local
        full_masks[name] = full

    full_quad = quad + np.asarray([cx0, cy0], dtype=np.float64)
    return full_masks, full_quad, float(exponent), float(support), used_fallback


def typography_mask(rgb: np.ndarray, silhouette: np.ndarray, center: np.ndarray, shoulder: np.ndarray) -> tuple[np.ndarray, float]:
    gray = luma_display(rgb)
    ys, xs = np.where(silhouette)
    result = np.zeros_like(silhouette)
    if len(xs) == 0:
        return result, 0.0
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    crop_gray = gray[y0:y1, x0:x1]
    crop_allowed = (center | shoulder)[y0:y1, x0:x1]
    height, width = crop_gray.shape
    window = max(5, int(min(width, height) * 0.032) | 1)
    local = ndi.median_filter(crop_gray, size=window)
    contrast = np.abs(crop_gray - local)
    yy = np.arange(height)[:, None] / max(height - 1, 1)
    text_prior = (yy <= 0.30) | (yy >= 0.56)
    valid_values = contrast[crop_allowed & text_prior]
    if valid_values.size < 20:
        return result, 0.0
    threshold = max(0.055, float(np.percentile(valid_values, 96.8)))
    strokes = crop_allowed & text_prior & (contrast >= threshold)
    strokes = morphology.remove_small_objects(strokes, min_size=max(3, int(silhouette.sum() * 0.000008)))
    join_width = max(3, int(width * 0.010))
    clusters = morphology.binary_dilation(strokes, morphology.rectangle(3, join_width))
    labels = measure.label(clusters)
    retained = np.zeros_like(strokes)
    cluster_count = 0
    for region in measure.regionprops(labels):
        ry0, rx0, ry1, rx1 = region.bbox
        rw, rh = rx1 - rx0, ry1 - ry0
        if rw < width * 0.025 or rh < max(2, height * 0.005):
            continue
        if rh > height * 0.22 or region.area > silhouette.sum() * 0.16:
            continue
        retained[ry0:ry1, rx0:rx1] |= strokes[ry0:ry1, rx0:rx1]
        cluster_count += 1
    retained = morphology.binary_dilation(retained, morphology.disk(1))
    result[y0:y1, x0:x1] = retained
    area_ratio = retained.sum() / max(silhouette.sum(), 1)
    confidence = float(np.clip(0.20 + 0.13 * cluster_count + (0.35 if 0.0005 <= area_ratio <= 0.14 else 0.0), 0.0, 1.0))
    return result, confidence


def highlight_mask(
    rgb: np.ndarray,
    silhouette: np.ndarray,
    sidewall: np.ndarray,
    rim: np.ndarray,
    shoulder: np.ndarray,
    typography: np.ndarray,
) -> tuple[np.ndarray, float]:
    gray = luma_linear(rgb)
    value = rgb.astype(np.float32) / 255.0
    chroma = value.max(axis=2) - value.min(axis=2)
    ys, xs = np.where(silhouette)
    result = np.zeros_like(silhouette)
    if len(xs) == 0:
        return result, 0.0
    height = int(ys.max() - ys.min() + 1)
    window = max(7, int(height * 0.055) | 1)
    local = ndi.median_filter(gray, size=window)
    residual = gray - local
    optical_prior = sidewall | rim | shoulder
    allowed = silhouette & ~morphology.binary_dilation(typography, morphology.disk(3))
    values = residual[allowed & optical_prior]
    if values.size < 20:
        return result, 0.0
    threshold = max(0.055, float(np.percentile(values, 98.6)))
    candidate = allowed & (residual >= threshold) & (chroma <= 0.28)
    candidate |= allowed & optical_prior & (gray >= np.percentile(gray[silhouette], 99.4)) & (chroma <= 0.20)
    candidate = morphology.binary_opening(candidate, morphology.disk(1))
    candidate = morphology.remove_small_objects(candidate, min_size=max(3, int(silhouette.sum() * 0.000006)))
    labels = measure.label(candidate)
    components = sorted(measure.regionprops(labels), key=lambda region: region.area, reverse=True)
    max_area = silhouette.sum() * 0.08
    kept = 0
    for region in components[:16]:
        if region.area > max_area:
            continue
        result[labels == region.label] = True
        kept += 1
    ratio = result.sum() / max(silhouette.sum(), 1)
    confidence = float(np.clip(0.22 + 0.08 * kept + (0.38 if 0.00002 <= ratio <= 0.055 else 0.0), 0.0, 1.0))
    return result, confidence


def gutter_mask(rgb: np.ndarray, silhouette: np.ndarray) -> tuple[np.ndarray, float]:
    height, width = silhouette.shape
    ys, xs = np.where(silhouette)
    result = np.zeros_like(silhouette)
    if len(xs) == 0:
        return result, 0.0
    card_height = int(ys.max() - ys.min() + 1)
    card_width = int(xs.max() - xs.min() + 1)
    pad_x, pad_y = int(card_width * 0.08), int(card_height * 0.10)
    x0, x1 = max(0, int(xs.min()) - pad_x), min(width, int(xs.max()) + pad_x + 1)
    y0, y1 = max(0, int(ys.min()) - pad_y), min(height, int(ys.max()) + pad_y + 1)
    region = np.zeros_like(silhouette)
    region[y0:y1, x0:x1] = True
    outside = region & ~morphology.binary_dilation(silhouette, morphology.disk(max(2, int(card_height * 0.008))))
    display_y = luma_display(rgb)
    value = rgb.astype(np.float32) / 255.0
    chroma = value.max(axis=2) - value.min(axis=2)
    outside_values = display_y[outside]
    if outside_values.size == 0:
        return result, 0.0
    cutoff = min(0.16, max(0.035, float(np.percentile(outside_values, 42))))
    dark = outside & (display_y <= cutoff) & (chroma <= 0.25)
    labels = measure.label(dark)
    for region_props in measure.regionprops(labels):
        ry0, rx0, ry1, rx1 = region_props.bbox
        touches_roi = rx0 <= x0 + 2 or ry0 <= y0 + 2 or rx1 >= x1 - 2 or ry1 >= y1 - 2
        if touches_roi:
            result[labels == region_props.label] = True
    coverage = result.sum() / max(outside.sum(), 1)
    return result, float(np.clip(coverage / 0.55, 0.0, 1.0))


def normalized_quad(quad: np.ndarray, width: int, height: int) -> list[list[float]]:
    return [[round(float(x / width), 6), round(float(y / height), 6)] for x, y in quad]


def normalized_bbox(mask: np.ndarray) -> dict[str, float] | None:
    height, width = mask.shape
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return {
        "x": round(float(xs.min() / width), 6),
        "y": round(float(ys.min() / height), 6),
        "width": round(float((xs.max() - xs.min() + 1) / width), 6),
        "height": round(float((ys.max() - ys.min() + 1) / height), 6),
    }


def normalized_centroid(mask: np.ndarray) -> list[float] | None:
    height, width = mask.shape
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return [round(float(xs.mean() / width), 6), round(float(ys.mean() / height), 6)]


def save_mask(path: Path, mask: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((mask.astype(np.uint8) * 255), mode="L").save(path, optimize=True)
    return sha256_file(path)


def make_overlay(rgb: np.ndarray, masks: dict[str, np.ndarray], role: str, destination: Path) -> str:
    base = Image.fromarray(rgb, mode="RGB").convert("RGBA")
    for name in ("gutter", "center-face", "optical-shoulder", "lens-rim", "sidewall", "typography", "highlight"):
        color = MASK_COLORS[name]
        alpha = 52 if name == "gutter" else 78
        layer = np.zeros((*masks[name].shape, 4), dtype=np.uint8)
        layer[masks[name]] = (*color, alpha)
        base = Image.alpha_composite(base, Image.fromarray(layer, mode="RGBA"))
    silhouette = masks["card-silhouette"]
    outline = silhouette & ~morphology.binary_erosion(silhouette, morphology.disk(3))
    outline_layer = np.zeros((*silhouette.shape, 4), dtype=np.uint8)
    outline_layer[outline] = (0, 245, 255, 235)
    base = Image.alpha_composite(base, Image.fromarray(outline_layer, mode="RGBA"))
    draw = ImageDraw.Draw(base)
    legend = f"{role} | cyan silhouette | green center | yellow shoulder | magenta rim | red sidewall | blue type | white highlight"
    draw.rectangle((8, 8, min(base.width - 8, 8 + len(legend) * 7), 34), fill=(0, 0, 0, 190))
    draw.text((14, 14), legend, fill=(255, 255, 255, 255))
    destination.parent.mkdir(parents=True, exist_ok=True)
    base.convert("RGB").save(destination, optimize=True)
    return sha256_file(destination)


def sharpness_metric(gray: np.ndarray, mask: np.ndarray) -> float | None:
    values = np.abs(filters.laplace(gray))[mask]
    luminance = gray[mask]
    if values.size < 20:
        return None
    dynamic_range = float(np.percentile(luminance, 90) - np.percentile(luminance, 10)) + 0.02
    return float(np.percentile(values, 90) / dynamic_range)


def dispersion_energy_ratio(rgb: np.ndarray, outer: np.ndarray, silhouette: np.ndarray) -> float | None:
    linear = srgb_to_linear(rgb)
    gradients = [filters.sobel(linear[..., channel]) for channel in range(3)]
    energy = np.abs(gradients[0] - gradients[1]) + np.abs(gradients[2] - gradients[1])
    total = float(energy[silhouette].sum())
    return float(energy[outer].sum() / total) if total > 1e-8 else None


def partition_is_valid(masks: dict[str, np.ndarray]) -> bool:
    silhouette = masks["card-silhouette"]
    zones = [masks[name] for name in ("center-face", "optical-shoulder", "lens-rim", "sidewall")]
    summed = np.sum(np.stack(zones, axis=0), axis=0)
    return bool(np.array_equal(summed == 1, silhouette) and not (summed > 1).any())


def process_selection(
    role: str,
    candidate: Candidate,
    video: Path,
    info: VideoInfo,
    output_root: Path,
    pointer_confidence: float,
    pointer_reasons: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    frame_path = output_root / "frames" / f"{role}.png"
    extract_frame(video, candidate.frame_index, frame_path)
    rgb = np.asarray(Image.open(frame_path).convert("RGB"))
    height, width = rgb.shape[:2]
    bx, by, bw, bh = candidate.bbox_n
    bbox = (
        max(0, int(round(bx * width))),
        max(0, int(round(by * height))),
        min(width, int(round((bx + bw) * width))),
        min(height, int(round((by + bh) * height))),
    )
    geometric, quad, exponent, edge_support, used_fallback = build_geometric_masks(rgb, bbox)
    typography, typography_confidence = typography_mask(
        rgb,
        geometric["card-silhouette"],
        geometric["center-face"],
        geometric["optical-shoulder"],
    )
    highlight, highlight_confidence = highlight_mask(
        rgb,
        geometric["card-silhouette"],
        geometric["sidewall"],
        geometric["lens-rim"],
        geometric["optical-shoulder"],
        typography,
    )
    gutter, gutter_confidence = gutter_mask(rgb, geometric["card-silhouette"])
    masks = {
        **geometric,
        "highlight": highlight,
        "typography": typography,
        "gutter": gutter,
    }
    if set(masks) != set(MASK_NAMES):
        raise ExtractionError(f"Mask set for {role} is incomplete")

    crop_bounds = normalized_bbox(geometric["card-silhouette"])
    assert crop_bounds is not None
    x0 = int(crop_bounds["x"] * width)
    y0 = int(crop_bounds["y"] * height)
    x1 = min(width, int(math.ceil((crop_bounds["x"] + crop_bounds["width"]) * width)))
    y1 = min(height, int(math.ceil((crop_bounds["y"] + crop_bounds["height"]) * height)))
    crop_path = output_root / "crops" / f"{role}.png"
    crop_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb[y0:y1, x0:x1], mode="RGB").save(crop_path, optimize=True)

    mask_hashes: dict[str, str] = {}
    for name in MASK_NAMES:
        mask_hashes[name] = save_mask(output_root / "masks" / role / f"{name}.png", masks[name])
    overlay_path = output_root / "overlays" / f"{role}.png"
    overlay_hash = make_overlay(rgb, masks, role, overlay_path)

    silhouette = masks["card-silhouette"]
    card_area = max(int(silhouette.sum()), 1)
    frame_area = height * width
    mask_confidences = {
        "card-silhouette": float(np.clip(0.35 + 0.55 * edge_support - (0.18 if used_fallback else 0.0), 0.0, 1.0)),
        "center-face": float(np.clip(0.62 + 0.25 * edge_support, 0.0, 1.0)),
        "optical-shoulder": float(np.clip(0.58 + 0.28 * edge_support, 0.0, 1.0)),
        "lens-rim": float(np.clip(0.58 + 0.28 * edge_support, 0.0, 1.0)),
        "sidewall": float(np.clip(0.55 + 0.30 * edge_support, 0.0, 1.0)),
        "highlight": highlight_confidence,
        "typography": typography_confidence,
        "gutter": gutter_confidence,
    }
    band_widths = {
        "sidewall": 0.012,
        "lens-rim": 0.053,
        "optical-shoulder": 0.080,
    }
    mask_metrics: dict[str, Any] = {}
    for name in MASK_NAMES:
        mask_metrics[name] = {
            "sha256": mask_hashes[name],
            "areaRatioOfFrame": round(float(masks[name].sum() / frame_area), 8),
            "areaRatioOfCard": round(float(masks[name].sum() / card_area), 8),
            "centroidNormalized": normalized_centroid(masks[name]),
            "confidence": round(mask_confidences[name], 4),
        }
        if name in band_widths:
            mask_metrics[name]["widthOverCardMinor"] = band_widths[name]

    gray = luma_linear(rgb)
    center_sharpness = sharpness_metric(gray, masks["center-face"])
    rim_sharpness = sharpness_metric(gray, masks["lens-rim"])
    sharpness_ratio = (
        center_sharpness / rim_sharpness
        if center_sharpness is not None and rim_sharpness is not None and rim_sharpness > 1e-8
        else None
    )
    outer = masks["sidewall"] | masks["lens-rim"]
    dispersion_ratio = dispersion_energy_ratio(rgb, outer, silhouette)
    title_bounds = normalized_bbox(typography)

    review_reasons: list[str] = []
    silhouette_ratio = float(silhouette.sum() / max((bbox[2] - bbox[0]) * (bbox[3] - bbox[1]), 1))
    if candidate.clipped:
        review_reasons.append("selected-card-is-clipped")
    if used_fallback:
        review_reasons.append("perspective-edge-fit-used-bounding-box-fallback")
    if edge_support < 0.48:
        review_reasons.append("silhouette-boundary-support-is-low")
    if not 0.60 <= silhouette_ratio <= 1.08:
        review_reasons.append("silhouette-area-is-inconsistent-with-detected-card")
    if not partition_is_valid(masks):
        review_reasons.append("optical-zone-partition-is-invalid")
    typography_ratio = typography.sum() / card_area
    highlight_ratio = highlight.sum() / card_area
    if typography_ratio > 0.18:
        review_reasons.append("typography-mask-is-obviously-too-broad")
    if highlight_ratio == 0 or highlight_ratio > 0.08:
        review_reasons.append("highlight-mask-is-empty-or-obviously-too-broad")
    if role.startswith("pointer-") and pointer_confidence < 0.62:
        review_reasons.extend(pointer_reasons)
    review_reasons = sorted(set(review_reasons))

    geometry_confidence = mask_confidences["card-silhouette"]
    confidence = float(
        np.clip(
            0.42 * geometry_confidence
            + 0.18 * candidate.quality
            + 0.16 * typography_confidence
            + 0.16 * highlight_confidence
            + 0.08 * gutter_confidence,
            0.0,
            1.0,
        ),
    )
    if role.startswith("pointer-"):
        confidence = min(confidence, pointer_confidence)

    frame_hash = sha256_file(frame_path)
    crop_hash = sha256_file(crop_path)
    center = np.mean(quad, axis=0)
    top_width = float(np.linalg.norm(quad[1] - quad[0]))
    bottom_width = float(np.linalg.norm(quad[2] - quad[3]))
    left_height = float(np.linalg.norm(quad[3] - quad[0]))
    right_height = float(np.linalg.norm(quad[2] - quad[1]))
    geometry = {
        "coordinateSpace": "source-frame-normalized",
        "quadNormalized": normalized_quad(quad, width, height),
        "centerNormalized": [round(float(center[0] / width), 6), round(float(center[1] / height), 6)],
        "widthNormalized": round(float((top_width + bottom_width) / (2 * width)), 6),
        "heightNormalized": round(float((left_height + right_height) / (2 * height)), 6),
        "topEdgeTiltDeg": round(math.degrees(math.atan2(quad[1, 1] - quad[0, 1], quad[1, 0] - quad[0, 0])), 4),
        "perspectiveHeightAsymmetry": round(float((right_height - left_height) / max((right_height + left_height) / 2, 1e-6)), 6),
        "superellipseExponent": exponent,
        "clipped": candidate.clipped,
    }
    sanitized = {
        "id": role,
        "frameIndex": candidate.frame_index,
        "ptsSeconds": round(candidate.frame_index / info.fps, 6),
        "frameSha256": frame_hash,
        "cropSha256": crop_hash,
        "overlaySha256": overlay_hash,
        "geometry": geometry,
        "features": {
            "medianLuminanceLinear": round(candidate.luminance, 6),
            "localContrast": round(candidate.contrast, 6),
            "edgeDensity": round(candidate.texture, 6),
            "entropyBits": round(candidate.entropy, 6),
            "clarityScore": round(candidate.quality, 6),
        },
        "metrics": {
            "rimZoneFallbackWidthOverCardMinor": 0.065,
            "opticalZoneFallbackWidthOverCardMinor": 0.145,
            "zoneWidthSource": "configured-initial-mask-not-measured-target-optics",
            "centerSharpness": None if center_sharpness is None else round(center_sharpness, 6),
            "rimSharpness": None if rim_sharpness is None else round(rim_sharpness, 6),
            "centerRimSharpnessRatio": None if sharpness_ratio is None else round(sharpness_ratio, 6),
            "dispersionOuterEnergyRatio": None if dispersion_ratio is None else round(dispersion_ratio, 6),
            "highlightCentroidNormalized": normalized_centroid(highlight),
            "typographyBoundsNormalized": title_bounds,
            "naturalContentCaveat": True,
        },
        "masks": mask_metrics,
        "confidence": round(confidence, 4),
        "needsHumanReview": bool(review_reasons),
        "reviewReasons": review_reasons,
    }
    private = {
        "id": role,
        "sourceFrameIndex": candidate.frame_index,
        "sourceFramePath": str(frame_path.resolve()),
        "cropPath": str(crop_path.resolve()),
        "overlayPath": str(overlay_path.resolve()),
        "maskPaths": {name: str((output_root / "masks" / role / f"{name}.png").resolve()) for name in MASK_NAMES},
        "pixelGeometry": {
            "sourceWidth": width,
            "sourceHeight": height,
            "detectedBbox": list(bbox),
            "quad": [[round(float(x), 3), round(float(y), 3)] for x, y in quad],
        },
        "hashes": {
            "frame": frame_hash,
            "crop": crop_hash,
            "overlay": overlay_hash,
            "masks": mask_hashes,
        },
    }
    return sanitized, private


def build_reference(video: Path, output_root: Path, sanitized_output: Path, stride: int) -> dict[str, Any]:
    if not video.is_file():
        raise ExtractionError("Frozen target MP4 does not exist or is not a regular file")
    if stride <= 0:
        raise ExtractionError("--analysis-stride must be positive")
    output_root.mkdir(parents=True, exist_ok=True)
    info = probe_video(video)
    source_hash = sha256_file(video)
    selected, pointer_confidence, pointer_reasons = analyze_video(video, info, stride)

    categories: list[dict[str, Any]] = []
    private_categories: list[dict[str, Any]] = []
    for role in CATEGORY_IDS:
        sanitized, private = process_selection(
            role,
            selected[role],
            video,
            info,
            output_root,
            pointer_confidence,
            pointer_reasons,
        )
        categories.append(sanitized)
        private_categories.append(private)

    artifact_hash_inputs: list[dict[str, Any]] = []
    for category in categories:
        artifact_hash_inputs.append(
            {
                "id": category["id"],
                "frameSha256": category["frameSha256"],
                "cropSha256": category["cropSha256"],
                "overlaySha256": category["overlaySha256"],
                "maskSha256": {name: category["masks"][name]["sha256"] for name in MASK_NAMES},
            },
        )
    artifact_set_hash = sha256_bytes(canonical_json_bytes(artifact_hash_inputs))
    review_count = sum(1 for item in categories if item["needsHumanReview"])
    clean_optical_count = sum(
        1
        for item in categories
        if not item["needsHumanReview"]
        and not item["geometry"]["clipped"]
        and item["masks"]["card-silhouette"]["confidence"] >= 0.65
    )
    if len(categories) < 8 or clean_optical_count == 0:
        status = "BLOCKED"
    elif review_count:
        status = "CONDITIONAL"
    else:
        status = "PASS"

    ffmpeg_version = subprocess.run(
        ["ffmpeg", "-version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()[0]
    sanitized_manifest = {
        "$schema": "../roi-mask.schema.json",
        "schemaVersion": 1,
        "referenceClass": "frozen-visual",
        "source": {
            "videoSha256": source_hash,
            "frameRate": {"numerator": info.frame_rate_num, "denominator": info.frame_rate_den},
            "frameCount": info.frame_count,
            "durationSeconds": round(info.duration_seconds, 6),
        },
        "algorithm": {
            "id": ALGORITHM_ID,
            "version": ALGORITHM_VERSION,
            "scriptSha256": sha256_file(Path(__file__).resolve()),
            "runtime": {
                "python": platform.python_version(),
                "ffmpeg": ffmpeg_version,
                "numpy": np.__version__,
                "scipy": scipy.__version__,
                "scikitImage": skimage.__version__,
                "pillow": PIL.__version__,
            },
            "analysisStrideFrames": stride,
            "zoneFallbacksOverCardMinor": {
                "sidewallEnd": 0.012,
                "lensRimEnd": 0.065,
                "opticalShoulderEnd": 0.145,
            },
        },
        "categories": categories,
        "summary": {
            "status": status,
            "selectedCategoryCount": len(categories),
            "uniqueFrameCount": len({item["frameIndex"] for item in categories}),
            "validCleanOpticalRoiCount": clean_optical_count,
            "opticalZoneWidthsMeasured": False,
            "needsHumanReviewCount": review_count,
            "artifactSetSha256": artifact_set_hash,
        },
    }
    private_manifest = {
        "schemaVersion": 1,
        "private": True,
        "sourcePath": str(video.resolve()),
        "outputRoot": str(output_root.resolve()),
        "sourceSha256": source_hash,
        "sourcePixels": {"width": info.width, "height": info.height},
        "categories": private_categories,
        "sanitizedManifestSha256": sha256_bytes(canonical_json_bytes(sanitized_manifest)),
    }
    write_json(output_root / "manifest.private.json", private_manifest)
    write_json(sanitized_output, sanitized_manifest)
    return sanitized_manifest


def main() -> int:
    args = parse_args()
    output_root = args.output_root.resolve()
    sanitized_output = (args.sanitized_output or (output_root / "frozen-visual.sanitized.json")).resolve()
    try:
        result = build_reference(args.target_mp4.resolve(), output_root, sanitized_output, args.analysis_stride)
    except (ExtractionError, OSError, ValueError) as error:
        print(json.dumps({"status": "BLOCKED", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": result["summary"]["status"],
                "selectedCategoryCount": result["summary"]["selectedCategoryCount"],
                "validCleanOpticalRoiCount": result["summary"]["validCleanOpticalRoiCount"],
                "needsHumanReviewCount": result["summary"]["needsHumanReviewCount"],
                "artifactSetSha256": result["summary"]["artifactSetSha256"],
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return 0 if result["summary"]["status"] != "BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
