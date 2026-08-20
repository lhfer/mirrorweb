#!/usr/bin/env python3
"""
Gutter-structure layout measurement for 1440x900 ILG frames.

Measures the NEGATIVE space (the dark navy void) rather than card blobs. Card
edges are gutter boundaries, which are immune to the video content inside a
card and to the sidewall/rim glow that biased the old AABB detector.

The background void is a near-black navy with R==0 and B ~= 4-6x G. Dark video
content inside a card is either neutral black (B ~= G) or lifted (R > 3), so the
chroma test separates them cleanly.

Usage: measure-layout.py <png> [<png> ...]  -> JSON on stdout
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# Background void discriminator.
#
# One algorithm, two void presets, because the two sides clear to different
# colours: the Target clears to a navy that ranges ~(0,3,20)..(0,6,32) with a
# darker (0,0,6) toward the frame edge, and this build clears to a black that
# the tone-mapped pipeline lands on exactly (0,0,0). Both presets are declared
# here and the resolved one is echoed into the JSON, so any frame can be
# re-checked with the same instrument.
# bMin/bOverG are deliberately strict. Relaxing them to (4, 1.5) also resolves
# the mid-row right gutter at x=1257..1270 -- symmetric with the left one at
# 169..182, which is the cross-check that the layout is left/right symmetric --
# but it leaks into Free State's very dark video and corrupts that card's
# bottom edge, which is one of the strongest depth observations. Strict wins;
# the right gutter is redundant with the left under proven symmetry.
NAVY_VOID = {"mode": "navy", "rMax": 3, "gMax": 10, "bMin": 13, "bMax": 42, "bOverG": 2.2}
# Relaxed twin, used ONLY to split rows. The Target void darkens to ~(0,0,6)
# near the frame edge, which the strict preset misses, and that costs the whole
# top-row band. Row splitting is a coarse, full-width statistic and tolerates
# the extra leakage; per-card edge tracing does not, so it keeps the strict one.
NAVY_VOID_BANDS = {"mode": "navy-bands", "rMax": 3, "gMax": 10, "bMin": 4, "bMax": 42, "bOverG": 1.5}
BLACK_VOID = {"mode": "black", "rMax": 8, "gMax": 8, "bMin": -1, "bMax": 8, "bOverG": 0.0}
MIN_RUN = 6  # a gutter pixel must belong to a run this long on both axes


def flat_void(max_value: int) -> dict:
    """Explicit override: void is anything at or below `max_value` on every
    channel."""
    return {"mode": "flat", "rMax": max_value, "gMax": max_value, "bMin": -1,
            "bMax": max_value, "bOverG": 0.0}


def void_mask(rgb: np.ndarray, void: dict) -> np.ndarray:
    a = rgb.astype(np.int16)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return (
        (R <= void["rMax"])
        & (G <= void["gMax"])
        & (B >= void["bMin"])
        & (B <= void["bMax"])
        & (B >= void["bOverG"] * G)
    )


def pick_void(rgb: np.ndarray) -> tuple[dict, dict]:
    """(edge preset, band/gutter preset) for this frame.

    The relaxed preset is used for BOTH full-width statistics: horizontal row
    bands and vertical gutters. Both require a feature to hold across most of a
    row or column, which a patch of dark video cannot do, so the extra leakage
    is harmless there. Per-card edge tracing walks single columns and is not
    robust to leakage, so it keeps the strict preset.
    """
    navy = void_mask(rgb, NAVY_VOID)
    if navy.sum() >= 20000:
        return NAVY_VOID, NAVY_VOID_BANDS
    return BLACK_VOID, BLACK_VOID


def runs(flags: np.ndarray) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    start = None
    for i, v in enumerate(flags):
        if v and start is None:
            start = i
        elif not v and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(flags) - 1))
    return out


def despeckle(mask: np.ndarray, axis: int, min_run: int = MIN_RUN) -> np.ndarray:
    """Drop mask runs shorter than min_run along `axis`."""
    out = mask.copy()
    if axis == 0:  # vertical runs, per column
        for x in range(mask.shape[1]):
            for a, b in runs(mask[:, x]):
                if b - a + 1 < min_run:
                    out[a : b + 1, x] = False
    else:  # horizontal runs, per row
        for y in range(mask.shape[0]):
            for a, b in runs(mask[y, :]):
                if b - a + 1 < min_run:
                    out[y, a : b + 1] = False
    return out


def fit(xs, ys):
    if len(xs) < 8:
        return None
    xs = np.asarray(xs, float)
    ys = np.asarray(ys, float)
    a, b = np.polyfit(xs, ys, 1)
    res = np.abs(ys - (a * xs + b))
    keep = res <= max(2.0, float(np.quantile(res, 0.85)))
    if keep.sum() >= 8:
        a, b = np.polyfit(xs[keep], ys[keep], 1)
    return {
        "slopeDeg": float(np.degrees(np.arctan(a))),
        "yAtX": lambda x: float(a * x + b),
        "a": float(a),
        "b": float(b),
        "median": float(np.median(ys)),
        "n": int(keep.sum()),
    }


def measure(path: Path, void_max: int | None = None,
            mask_override: "np.ndarray | None" = None,
            band_mask_override: "np.ndarray | None" = None) -> dict:
    rgb = np.asarray(Image.open(path).convert("RGB"))
    h, w = rgb.shape[:2]
    if void_max is not None:
        void = band_void = flat_void(void_max)
    else:
        void, band_void = pick_void(rgb)
    # A caller can supply consensus masks built from several frames of the same
    # viewport, which is how video content is kept out of the geometry.
    #
    # There are TWO presets here for a reason -- strict for per-card edge
    # tracing, relaxed for gutters and bands -- so a consensus caller must
    # supply two masks as well. Feeding one relaxed mask to both, which is what
    # a single `mask_override` did, hands edge tracing a mask that calls more
    # pixels void: card edges then truncate and their measured slope goes wrong.
    # That alone turned two passing viewports into edge-yaw failures.
    raw = mask_override if mask_override is not None else void_mask(rgb, void)
    if band_mask_override is not None:
        band_raw = band_mask_override
    elif mask_override is not None:
        band_raw = mask_override
    else:
        band_raw = void_mask(rgb, band_void)
    mv = despeckle(raw, axis=0)             # per-card edge tracing: strict
    mg = despeckle(band_raw, axis=0)        # vertical gutters: relaxed
    mh = despeckle(band_raw, axis=1)        # row bands: relaxed

    # ---- horizontal gutter bands (row separators) -------------------------
    hcov = mh.mean(axis=1)
    hbands = [(a, b) for a, b in runs(hcov >= 0.5) if b - a + 1 >= 4]

    # ---- row extents: the card bands between horizontal gutter bands ------
    # A clipped top or bottom row can be a thin sliver, so the minimum span is
    # small; 18 px is still far wider than any gutter this detector reports.
    row_spans = []
    prev = -1
    for a, b in hbands:
        if a - prev > 18:
            row_spans.append((prev + 1, a - 1))
        prev = b
    if h - prev > 18:
        row_spans.append((prev + 1, h - 1))

    rows = []
    for ry0, ry1 in row_spans:
        seed = (ry0 + ry1) // 2
        # vertical gutters, measured across the middle 60% of the row band so
        # rounded corners cannot open a false gutter.
        q0 = ry0 + int((ry1 - ry0) * 0.20)
        q1 = ry1 - int((ry1 - ry0) * 0.20)
        vcov = mg[q0 : q1 + 1, :].mean(axis=0)
        vg = [(a, b) for a, b in runs(vcov >= 0.85) if b - a + 1 >= 3]

        card_spans = []
        prev = -1
        for a, b in vg:
            if a - prev > 60:
                card_spans.append((prev + 1, a - 1))
            prev = b
        if w - prev > 60:
            card_spans.append((prev + 1, w - 1))

        cards = []
        for x0, x1 in card_spans:
            span = x1 - x0
            ix0 = max(x0 + int(span * 0.20), 0)
            ix1 = min(x1 - int(span * 0.20), w - 1)
            txs, tys, bxs, bys = [], [], [], []
            for x in range(ix0, ix1 + 1):
                if mv[seed, x]:
                    continue
                y = seed
                while y > 0 and not mv[y - 1, x]:
                    y -= 1
                top = y
                y = seed
                while y < h - 1 and not mv[y + 1, x]:
                    y += 1
                bot = y
                if top > 0:
                    txs.append(x)
                    tys.append(top)
                if bot < h - 1:
                    bxs.append(x)
                    bys.append(bot)
            top_fit = fit(txs, tys)
            bot_fit = fit(bxs, bys)
            cx = (x0 + x1) / 2
            entry = {
                "x0": int(x0),
                "x1": int(x1),
                "w": int(x1 - x0 + 1),
                "cx": float(cx),
                "clipped": {
                    "left": bool(x0 <= 0),
                    "right": bool(x1 >= w - 1),
                    "top": bool(ry0 <= 0),
                    "bottom": bool(ry1 >= h - 1),
                },
            }
            for key, f in (("topEdge", top_fit), ("bottomEdge", bot_fit)):
                if f is None:
                    entry[key] = None
                else:
                    entry[key] = {
                        "slopeDeg": round(f["slopeDeg"], 3),
                        "yAtCx": round(f["a"] * cx + f["b"], 2),
                        "median": round(f["median"], 2),
                        "samples": f["n"],
                    }
            if entry["topEdge"] and entry["bottomEdge"]:
                entry["h"] = round(entry["bottomEdge"]["yAtCx"] - entry["topEdge"]["yAtCx"] + 1, 2)
                entry["cy"] = round((entry["bottomEdge"]["yAtCx"] + entry["topEdge"]["yAtCx"]) / 2, 2)
                entry["aspect"] = round(entry["w"] / entry["h"], 4)
            cards.append(entry)

        rows.append(
            {
                "y0": int(ry0),
                "y1": int(ry1),
                "clippedTop": bool(ry0 <= 0),
                "clippedBottom": bool(ry1 >= h - 1),
                "verticalGutters": [
                    {"x0": int(a), "x1": int(b), "width": int(b - a + 1), "center": float((a + b) / 2)}
                    for a, b in vg
                ],
                "cards": cards,
            }
        )

    return {
        "file": str(path),
        "size": {"w": int(w), "h": int(h)},
        "voidMask": ({"mode": "consensus"} if mask_override is not None else void),
        "bandVoidMask": band_void,
        "horizontalGutterBands": [
            {"y0": int(a), "y1": int(b), "height": int(b - a + 1), "center": float((a + b) / 2)}
            for a, b in hbands
        ],
        "rows": rows,
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    vm = None
    files = []
    for a in args:
        if a.startswith("--void-max="):
            vm = int(a.split("=", 1)[1])
        else:
            files.append(a)
    out = [measure(Path(p), vm) for p in files]
    print(json.dumps(out if len(out) > 1 else out[0], indent=2))
