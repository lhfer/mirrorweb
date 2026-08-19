#!/usr/bin/env python3
"""Pixel measurements for the Round 1 V4 grid-preview engineering gate.

The browser driver captures frames and the projected card rectangles; this
script turns them into the numbers the gate asserts on:

  * body rim        - is there a FIXED dark ring, independent of card content?
  * dispersion      - is chroma localised at card rims, or smeared full screen?
  * pointer         - does moving the pointer actually change the reflection?
  * border streak   - does a partially off-screen card smear the frame border?

It reads only local capture frames and writes only aggregate numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as opened:
        opened.load()
        return np.asarray(opened.convert("RGB"), dtype=np.float32) / 255.0


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def chroma(rgb: np.ndarray) -> np.ndarray:
    return rgb.max(axis=-1) - rgb.min(axis=-1)


def quad_bbox(quad: list[list[float]], width: int, height: int) -> tuple[int, int, int, int]:
    xs = [point[0] * width for point in quad]
    ys = [point[1] * height for point in quad]
    return (
        max(0, int(min(xs))),
        max(0, int(min(ys))),
        min(width, int(max(xs))),
        min(height, int(max(ys))),
    )


def visible_cards(
    quads: list[dict[str, Any]],
    width: int,
    height: int,
    minimum: int = 48,
) -> list[tuple[dict[str, Any], tuple[int, int, int, int]]]:
    """On-screen cards only, largest first.

    A perspective projection of a card that sits behind the camera produces an
    inverted, enormous bounding box. Those have to be dropped before ranking,
    otherwise the measurement lands on geometry the viewer never sees.
    """
    entries: list[tuple[dict[str, Any], tuple[int, int, int, int], int]] = []
    for entry in quads:
        points = entry["quad"]
        if any(not (-1.0 <= value <= 2.0) for point in points for value in point):
            continue
        box = quad_bbox(points, width, height)
        span_x = box[2] - box[0]
        span_y = box[3] - box[1]
        if span_x < minimum or span_y < minimum:
            continue
        entries.append((entry, box, span_x * span_y))
    entries.sort(key=lambda item: -item[2])
    return [(entry, box) for entry, box, _ in entries]


def band_masks(box: tuple[int, int, int, int], shape: tuple[int, int]) -> dict[str, np.ndarray]:
    """Centre / shoulder / rim bands of one card, as a normalised box distance.

    Cards are close to axis aligned on screen, so a box-distance approximation
    is enough to separate the interior from the rim. It is deliberately coarse:
    the gate asks whether a fixed dark ring exists, not where it ends.
    """
    x0, y0, x1, y1 = box
    height, width = shape
    ys = np.arange(height)[:, None]
    xs = np.arange(width)[None, :]
    half_w = max(1.0, (x1 - x0) / 2)
    half_h = max(1.0, (y1 - y0) / 2)
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    normalized = np.maximum(np.abs(xs - cx) / half_w, np.abs(ys - cy) / half_h)
    return {
        "center": normalized <= 0.45,
        "shoulder": (normalized > 0.55) & (normalized <= 0.82),
        "rim": (normalized > 0.86) & (normalized <= 0.985),
        "inside": normalized <= 0.985,
    }


def card_metrics(frame: np.ndarray, quads: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    height, width = frame.shape[:2]
    luma = luminance(frame)
    chr_ = chroma(frame)
    results: list[dict[str, Any]] = []
    for entry, box in visible_cards(quads, width, height)[:limit]:
        masks = band_masks(box, (height, width))
        if masks["center"].sum() < 32 or masks["rim"].sum() < 32:
            continue
        results.append({
            "i": entry.get("i"),
            "j": entry.get("j"),
            "slotIndex": entry.get("slotIndex"),
            "box": list(box),
            "centerLuma": float(luma[masks["center"]].mean()),
            "shoulderLuma": float(luma[masks["shoulder"]].mean()),
            "rimLuma": float(luma[masks["rim"]].mean()),
            "rimToCenterLuma": float(luma[masks["rim"]].mean() / max(1e-4, luma[masks["center"]].mean())),
            "centerChroma": float(chr_[masks["center"]].mean()),
            "rimChroma": float(chr_[masks["rim"]].mean()),
            "interiorHighChromaRatio": float((chr_[masks["center"]] > 0.25).mean()),
        })
    return results


def dispersion_metrics(frame: np.ndarray, quads: list[dict[str, Any]]) -> dict[str, Any]:
    height, width = frame.shape[:2]
    chr_ = chroma(frame)
    interior = np.zeros((height, width), dtype=bool)
    rim = np.zeros((height, width), dtype=bool)
    for _, box in visible_cards(quads, width, height):
        masks = band_masks(box, (height, width))
        interior |= masks["center"]
        rim |= masks["rim"]
    interior &= ~rim
    return {
        "frameHighChromaRatio": float((chr_ > 0.25).mean()),
        "interiorHighChromaRatio": float((chr_[interior] > 0.25).mean()) if interior.any() else 0.0,
        "rimHighChromaRatio": float((chr_[rim] > 0.25).mean()) if rim.any() else 0.0,
        "interiorPixels": int(interior.sum()),
        "rimPixels": int(rim.sum()),
    }


def dispersion_debug_metrics(frame: np.ndarray, quads: list[dict[str, Any]]) -> dict[str, Any]:
    """Dispersion measured from the material's own dispersion debug view.

    Content saturation says nothing about the optics: a green field is chromatic
    on its own. The debug view outputs |R-G| and |B-G| of the three dispersion
    taps, so a non-zero signal there is dispersion the glass introduced.
    """
    height, width = frame.shape[:2]
    signal = np.maximum(frame[..., 0], frame[..., 2])
    interior = np.zeros((height, width), dtype=bool)
    rim = np.zeros((height, width), dtype=bool)
    for _, box in visible_cards(quads, width, height):
        masks = band_masks(box, (height, width))
        interior |= masks["center"]
        rim |= masks["rim"]
    interior &= ~rim
    return {
        "interiorMean": float(signal[interior].mean()) if interior.any() else 0.0,
        "rimMean": float(signal[rim].mean()) if rim.any() else 0.0,
        "interiorActiveRatio": float((signal[interior] > 0.05).mean()) if interior.any() else 0.0,
        "rimActiveRatio": float((signal[rim] > 0.05).mean()) if rim.any() else 0.0,
        "frameActiveRatio": float((signal > 0.05).mean()),
    }


def pointer_delta(left: np.ndarray, right: np.ndarray, quads: list[dict[str, Any]]) -> dict[str, Any]:
    height, width = left.shape[:2]
    delta = np.abs(left - right).mean(axis=-1)
    rim = np.zeros((height, width), dtype=bool)
    for _, box in visible_cards(quads, width, height):
        masks = band_masks(box, (height, width))
        rim |= masks["rim"] | masks["shoulder"]
    return {
        "meanAbsDelta": float(delta.mean()),
        "rimMeanAbsDelta": float(delta[rim].mean()) if rim.any() else 0.0,
        "rimChangedPixelRatio": float((delta[rim] > 2 / 255).mean()) if rim.any() else 0.0,
    }


def border_streak(frame: np.ndarray, depth: int = 6, run: int = 24) -> dict[str, Any]:
    """Detects clamped screen-UV smearing along the frame border.

    A clamped sample repeats the border texel outward, which shows up as a long
    run of rows (or columns) where the outermost pixels are identical to their
    inward neighbour. Real video content almost never does that.
    """
    height, width = frame.shape[:2]
    report: dict[str, Any] = {}
    worst = 0.0
    for side in ("left", "right", "top", "bottom"):
        if side == "left":
            outer, inner = frame[:, 0:depth, :], frame[:, depth:depth * 2, :]
            axis_len = height
        elif side == "right":
            outer, inner = frame[:, -depth:, :], frame[:, -depth * 2:-depth, :]
            axis_len = height
        elif side == "top":
            outer, inner = frame[0:depth, :, :], frame[depth:depth * 2, :, :]
            axis_len = width
        else:
            outer, inner = frame[-depth:, :, :], frame[-depth * 2:-depth, :, :]
            axis_len = width
        # Only lit pixels can smear visibly: the gutter is flat black, so
        # identical black columns are the background, not clamped sampling.
        lit = luminance(outer) > 0.03
        same = (np.abs(outer - inner).max(axis=-1) <= 1.5 / 255) & lit
        collapsed = same.all(axis=1) if side in ("left", "right") else same.all(axis=0)
        longest = 0
        current = 0
        for value in collapsed:
            current = current + 1 if value else 0
            longest = max(longest, current)
        ratio = float(collapsed.mean())
        report[side] = {
            "identicalRatio": ratio,
            "longestRun": int(longest),
            "runRatio": float(longest / max(1, axis_len)),
            "streaking": bool(longest >= run and ratio > 0.12),
        }
        worst = max(worst, float(longest / max(1, axis_len)))
    report["worstRunRatio"] = worst
    report["streaking"] = any(
        isinstance(value, dict) and value.get("streaking") for value in report.values()
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    manifest_path = Path(arguments.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    frames = {name: load_rgb(root / value) for name, value in manifest["frames"].items()}
    quads = manifest["cardQuads"]

    bright = frames["rest"]
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "generator": "round1-gate-analyzer-v1",
        "frameSize": [int(bright.shape[1]), int(bright.shape[0])],
        "cards": card_metrics(bright, quads),
        "dispersion": dispersion_metrics(bright, quads),
        "dispersionDebug": dispersion_debug_metrics(frames["dispersion-debug"], quads)
        if "dispersion-debug" in frames else None,
        "borderStreak": border_streak(frames["partial-viewport"]),
        "borderStreakRest": border_streak(bright),
    }
    if "pointer-left" in frames and "pointer-right" in frames:
        result["pointer"] = pointer_delta(frames["pointer-left"], frames["pointer-right"], quads)
    if result["cards"]:
        rims = [card["rimToCenterLuma"] for card in result["cards"]]
        result["bodyRim"] = {
            "minRimToCenterLuma": float(min(rims)),
            "maxRimToCenterLuma": float(max(rims)),
            "spread": float(max(rims) - min(rims)),
            "minRimLuma": float(min(card["rimLuma"] for card in result["cards"])),
        }
    Path(arguments.output).write_text(f"{json.dumps(result, indent=2)}\n", encoding="utf-8")
    print(json.dumps(
        {key: result[key] for key in ("dispersionDebug", "borderStreak", "bodyRim") if key in result},
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
