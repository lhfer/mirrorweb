#!/usr/bin/env python3
"""Integrated Visual Sprint 1 §九 -- displacement traces from the §四
recordings, and the trajectory overlays.

Per recording: the global inter-frame displacement by FFT phase
correlation on the downscaled grey frame (the whole grid moves together, so
the correlation peak IS the scroll step). Cumulative sum = the page's
displacement-vs-time curve, timestamped by the screencast's own browser
timestamps. The overlay draws Target and candidate curves for the same
scenario on one canvas -- same real input sequence on both sides, so the
time axes align at recording start.

Output: artifacts/integrated-review/motion/{scenario}.json + overlay PNGs.
No product code is read or touched; no gate, no threshold -- §九 is
diagnosis only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent.parent
BASE = REPO / "artifacts/integrated-review"
OUT = BASE / "motion"
SCENARIOS = ["desktop-slow-drag", "desktop-fast-flick", "desktop-pointer-sweep",
             "mobile-touch-drag", "mobile-long-drag-wrap", "orientation-change"]
SIDES = {"target": "target", "candidate": "review-target"}


def load_grey(p: Path, scale: int = 4) -> np.ndarray:
    im = Image.open(p).convert("L")
    im = im.resize((im.width // scale, im.height // scale), Image.BILINEAR)
    return np.asarray(im, dtype=np.float64)


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """(dx, dy, peak) of b relative to a, in DOWNSCALED pixels."""
    fa, fb = np.fft.rfft2(a), np.fft.rfft2(b)
    cross = fa * np.conj(fb)
    denom = np.abs(cross)
    denom[denom < 1e-9] = 1e-9
    corr = np.fft.irfft2(cross / denom, s=a.shape)
    peak = np.unravel_index(np.argmax(corr), corr.shape)
    dy, dx = peak
    if dy > a.shape[0] // 2:
        dy -= a.shape[0]
    if dx > a.shape[1] // 2:
        dx -= a.shape[1]
    return -float(dx), -float(dy), float(corr.max())


def trace(rec_dir: Path, scale: int = 4, step: int = 2):
    idx = json.loads((rec_dir / "index.json").read_text())
    frames = sorted(rec_dir.glob("*.jpg"))[::step]
    t0 = None
    rows = []
    prev = None
    cx = cy = 0.0
    for f in frames:
        g = load_grey(f, scale)
        n = int(f.stem)
        if prev is not None and prev.shape == g.shape:
            dx, dy, pk = phase_shift(prev, g)
            cx += dx * scale
            cy += dy * scale
            rows.append({"frame": n, "dx": dx * scale, "dy": dy * scale,
                         "x": cx, "y": cy, "peak": pk})
        elif prev is not None:
            rows.append({"frame": n, "resized": True, "x": cx, "y": cy})
        prev = g
    span = idx.get("spanSec") or 1
    total = idx.get("frames") or (len(frames) * step)
    for r in rows:
        r["tSec"] = round(r["frame"] / max(1, total - 1) * span, 3)
    return {"scenario": rec_dir.name, "vp": idx.get("vp"), "fps": idx.get("fps"),
            "spanSec": span, "rows": rows}


def overlay(scenario: str, traces: dict[str, dict], path: Path):
    W, H = 1200, 500
    im = Image.new("RGB", (W, H), (12, 14, 24))
    dr = ImageDraw.Draw(im)
    tmax = max((r["tSec"] for t in traces.values() for r in t["rows"]), default=1)
    xs = [abs(r["x"]) for t in traces.values() for r in t["rows"]]
    xmax = max(max(xs, default=1), 1)
    colors = {"target": (120, 200, 255), "candidate": (255, 170, 90)}
    for side, t in traces.items():
        pts = [(60 + r["tSec"] / tmax * (W - 120),
                H - 60 - abs(r["x"]) / xmax * (H - 120)) for r in t["rows"]]
        if len(pts) > 1:
            dr.line(pts, fill=colors[side], width=3)
    dr.text((60, 12), f"{scenario} -- |x displacement| vs time  "
            f"(blue target, orange candidate; identical real input)", fill=(230, 230, 230))
    dr.text((60, H - 40), f"0..{tmax:.1f}s   0..{xmax:.0f}px", fill=(160, 160, 170))
    im.save(path)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for sc in SCENARIOS:
        traces = {}
        for label, side in SIDES.items():
            d = BASE / side / "recordings" / sc
            if d.exists():
                traces[label] = trace(d)
        if not traces:
            continue
        (OUT / f"{sc}.json").write_text(json.dumps(traces, indent=1))
        overlay(sc, traces, OUT / f"{sc}-overlay.png")
        stats = {}
        for label, t in traces.items():
            xs = [r["x"] for r in t["rows"]]
            dxs = [abs(r.get("dx", 0)) for r in t["rows"]]
            big = [(r["tSec"], r.get("dx", 0)) for r in t["rows"]
                   if abs(r.get("dx", 0)) > 120]
            stats[label] = {
                "finalX": round(xs[-1], 1) if xs else None,
                "peakStep": round(max(dxs), 1) if dxs else None,
                "jumps>120px": big[:6],
                "settleT": next((r["tSec"] for r in reversed(t["rows"])
                                 if abs(r.get("dx", 0)) > 1.0), None),
            }
        summary[sc] = stats
        print(sc, json.dumps(stats))
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
