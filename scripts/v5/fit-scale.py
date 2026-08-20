#!/usr/bin/env python3
"""
Stage F2: recover the Target's composition scale at each captured viewport.

The world geometry is NOT re-fitted here. `GRID`/`TILE` are the accepted V5
Foundation baseline and are held fixed in world units; the only free parameters
per viewport are

    S           composition scale, screen px per world unit at z = 0
    scrollX     horizontal rest offset, world units
    scrollY     vertical rest offset, world units

so whatever S comes out is a property of the Target's responsive behaviour, not
a re-parameterisation of the card geometry.

Two hypotheses for how a scale S is realised are fitted independently, because
they agree to first order and disagree on the curvature falloff:

    camera   the camera moves:      camZ = perspectivePx / S,  f = perspectivePx
    focal    the focal length moves: camZ = perspectivePx,      f = perspectivePx * S

Observables are structural: vertical gutter centres, horizontal gutter band
centres, and the left/right edges of any card that is not clipped by the frame.
None of them requires a card to be fully visible, which is what makes the same
instrument work on a 390-wide portrait frame and a 2560-wide desktop one.

Usage: fit-scale.py --png=<frame> [--png=...] [--json=<out>]
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ML = _load("measure_layout", "measure-layout.py")

# Accepted V5 Foundation baseline, world units. Silhouette tile size, because a
# pixel detector reads the silhouette.
WORLD = {
    "cellW": 561.14,
    "cellH": 420.43,
    "radius": -4058.94,
    "tileW": 540.7678,
    "tileH": 401.5479,
}
PERSPECTIVE_PX = 1000.0
CAM_Y = 8.0


def brick_column(i: int, j: int) -> float:
    return i + (0.5 if ((j % 2) + 2) % 2 == 1 else 0.0)


def projector(view_w: float, view_h: float, scale: float, hypothesis: str):
    if hypothesis == "camera":
        cam_z = PERSPECTIVE_PX / max(scale, 1e-6)
        f_px = PERSPECTIVE_PX
    elif hypothesis == "focal":
        cam_z = PERSPECTIVE_PX
        f_px = PERSPECTIVE_PX * scale
    else:
        raise ValueError(hypothesis)
    eye = np.array([0.0, CAM_Y, cam_z])
    fwd = np.array([0.0, -CAM_Y, -cam_z])
    fwd = fwd / np.linalg.norm(fwd)
    right = np.array([1.0, 0.0, 0.0])
    up = np.cross(right, fwd)

    def project(pts: np.ndarray) -> np.ndarray:
        rel = pts - eye
        zc = np.maximum(rel @ fwd, 1e-3)
        return np.stack([view_w / 2 + f_px * (rel @ right) / zc,
                         view_h / 2 - f_px * (rel @ up) / zc], axis=1)

    return project


def card_quads(view_w, view_h, scale, scroll_x, scroll_y, hypothesis, cols=7, rows=7):
    project = projector(view_w, view_h, scale, hypothesis)
    hw, hh = WORLD["tileW"] / 2, WORLD["tileH"] / 2
    r = WORLD["radius"]
    out = []
    for j in range(-rows, rows + 1):
        for i in range(-cols, cols + 1):
            u = brick_column(i, j) * WORLD["cellW"] - scroll_x
            v = j * WORLD["cellH"] - scroll_y
            theta = u / r
            gx, gy, gz = r * math.sin(theta), v, r * (1 - math.cos(theta))
            ca, sa = math.cos(-theta), math.sin(-theta)
            pts = np.array([[gx + lx * ca, gy + ly, gz - lx * sa]
                            for lx, ly in ((-hw, hh), (hw, hh), (hw, -hh), (-hw, -hh))])
            q = project(pts)
            if q[:, 0].max() < -8 or q[:, 0].min() > view_w + 8:
                continue
            if q[:, 1].max() < -8 or q[:, 1].min() > view_h + 8:
                continue
            out.append({"i": i, "j": j, "quad": q,
                        "x0": float(q[:, 0].min()), "x1": float(q[:, 0].max()),
                        "y0": float(q[:, 1].min()), "y1": float(q[:, 1].max())})
    return out


def model_structure(view_w, view_h, scale, scroll_x, scroll_y, hypothesis):
    """Predicted gutter centres and row-band centres, mirroring the detector."""
    quads = card_quads(view_w, view_h, scale, scroll_x, scroll_y, hypothesis)
    rows: dict[int, list] = {}
    for q in quads:
        rows.setdefault(q["j"], []).append(q)
    def band(row):
        """Vertical extent of a row as the DETECTOR sees it: only cards that
        actually cross the frame horizontally. Far off-screen cards are yawed
        hard and their AABBs are enormous, which would smear every row band
        into its neighbour."""
        on = [q for q in row if q["x1"] > 0 and q["x0"] < view_w]
        if not on:
            on = row
        return min(q["y0"] for q in on), max(q["y1"] for q in on)

    v_gutters = []
    for j, row in rows.items():
        row.sort(key=lambda q: q["x0"])
        y_lo, y_hi = band(row)
        for a, b in zip(row, row[1:]):
            if b["x0"] <= a["x1"]:
                continue
            v_gutters.append({"x": (a["x1"] + b["x0"]) / 2, "yLo": y_lo, "yHi": y_hi, "j": j})

    h_bands = horizontal_bands(quads, view_w, view_h)
    return quads, v_gutters, h_bands


def horizontal_bands(quads, view_w, view_h, ystep=2.0, xbins=180):
    """
    Predicted horizontal gutter bands, computed the way the detector finds
    them: scanlines where cards cover at most half the frame width. Using
    "no card AABB overlaps the next row" instead would miss every band, because
    a yawed outer card's AABB reaches into its neighbouring row.
    """
    ys = np.arange(0.0, view_h, ystep)
    occ = np.zeros((ys.size, xbins), bool)
    for q in quads:
        poly = q["quad"]
        lo, hi = poly[:, 1].min(), poly[:, 1].max()
        sel = (ys >= lo) & (ys <= hi)
        if not sel.any():
            continue
        yy = ys[sel]
        xmin = np.full(yy.shape, np.inf)
        xmax = np.full(yy.shape, -np.inf)
        for k in range(4):
            ax, ay = poly[k]
            bx, by = poly[(k + 1) % 4]
            if ay == by:
                continue
            t = (yy - ay) / (by - ay)
            on = (t >= 0) & (t <= 1)
            if not on.any():
                continue
            x = ax + t * (bx - ax)
            xmin = np.where(on, np.minimum(xmin, x), xmin)
            xmax = np.where(on, np.maximum(xmax, x), xmax)
        good = np.isfinite(xmin) & np.isfinite(xmax)
        if not good.any():
            continue
        b0 = np.clip((xmin / view_w * xbins).astype(int), 0, xbins - 1)
        b1 = np.clip((xmax / view_w * xbins).astype(int), 0, xbins - 1)
        rowidx = np.nonzero(sel)[0]
        for n, r in enumerate(rowidx):
            if good[n]:
                occ[r, b0[n]:b1[n] + 1] = True
    cover = occ.mean(axis=1)
    bands = []
    start = None
    for n, c in enumerate(cover):
        if c <= 0.5 and start is None:
            start = n
        elif c > 0.5 and start is not None:
            if n - start >= 2:
                bands.append(float((ys[start] + ys[n - 1]) / 2))
            start = None
    if start is not None and ys.size - start >= 2:
        bands.append(float((ys[start] + ys[-1]) / 2))
    return bands


def observations(measure: dict) -> dict:
    """Structural observables pulled out of a measured frame."""
    w = measure["size"]["w"]
    v = []
    for row in measure["rows"]:
        # A row clipped by the top or bottom of the frame is a sliver whose
        # rounded corners open false, over-wide gutters; keep it, but at low
        # weight, so it informs parity without steering the scale.
        weight = 0.3 if (row["clippedTop"] or row["clippedBottom"]) else 1.0
        for g in row["verticalGutters"]:
            v.append({"x": g["center"], "yLo": row["y0"], "yHi": row["y1"], "w": weight})
    h = [b["center"] for b in measure["horizontalGutterBands"]]
    edges = []
    for row in measure["rows"]:
        if row["clippedTop"] or row["clippedBottom"]:
            continue  # same reason: a sliver's x extent is not a card edge
        for c in row["cards"]:
            if not c["clipped"]["left"] and not c["clipped"]["right"]:
                edges.append({"x0": c["x0"], "x1": c["x1"], "yLo": row["y0"], "yHi": row["y1"]})
    return {"vGutters": v, "hBands": h, "edges": edges, "viewW": w, "viewH": measure["size"]["h"]}


def residuals(vec, obs, hypothesis):
    scale, sx, sy = vec
    vw, vh = obs["viewW"], obs["viewH"]
    quads, v_pred, h_pred = model_structure(vw, vh, scale, sx, sy, hypothesis)
    out = []
    big = 60.0  # cap so one unmatched feature cannot dominate the fit

    for g in obs["vGutters"]:
        cands = [p["x"] for p in v_pred if p["yHi"] > g["yLo"] and p["yLo"] < g["yHi"]]
        err = min((abs(c - g["x"]) for c in cands), default=big) if cands else big
        out.append(g.get("w", 1.0) * min(err, big))
    for y in obs["hBands"]:
        out.append(min((min(abs(p - y) for p in h_pred), big) if h_pred else big))
    for e in obs["edges"]:
        cands = [q for q in quads if q["y1"] > e["yLo"] and q["y0"] < e["yHi"]]
        if not cands:
            out += [big, big]
            continue
        best = min(cands, key=lambda q: abs(q["x0"] - e["x0"]) + abs(q["x1"] - e["x1"]))
        # Card edges anchor the scale, so they carry more weight than gutters.
        out.append(2.0 * (best["x0"] - e["x0"]))
        out.append(2.0 * (best["x1"] - e["x1"]))
    return np.asarray(out, float)


def fit_one(measure: dict, hypothesis: str) -> dict:
    obs = observations(measure)
    vw, vh = obs["viewW"], obs["viewH"]
    best = None
    # Multi-start. The seeds bracket both regimes the sweep revealed: landscape
    # sits near width/1440, portrait near 1.85x that. A pure "world size fixed"
    # seed is kept so a wrong prior cannot trap the fit.
    # Seeded from what the sweep established: landscape sits at width/1440,
    # portrait about 1.87x that. The 1.0 seed is retained so a wrong prior
    # cannot trap a viewport that behaves like neither.
    seeds = [vw / 1440.0, vw / 1440.0 * 1.87, 1.0]
    for s0 in seeds:
        for sx0 in (0.0, WORLD["cellW"] / 2):
            for sy0 in (0.0, WORLD["cellH"], WORLD["cellH"] / 2, -WORLD["cellH"] / 2):
                try:
                    sol = least_squares(
                        residuals, [s0, sx0, sy0], args=(obs, hypothesis),
                        bounds=([0.05, -WORLD["cellW"], -3 * WORLD["cellH"]],
                                [6.0, WORLD["cellW"], 3 * WORLD["cellH"]]),
                        xtol=1e-12, ftol=1e-12, max_nfev=600,
                    )
                except Exception:
                    continue
                if best is None or sol.cost < best.cost:
                    best = sol
    if best is None:
        return {"hypothesis": hypothesis, "failed": True}
    r = residuals(best.x, obs, hypothesis)
    return {
        "hypothesis": hypothesis,
        "scale": round(float(best.x[0]), 5),
        "scrollX": round(float(best.x[1]), 3),
        "scrollY": round(float(best.x[2]), 3),
        "rmsPx": round(float(np.sqrt(np.mean(r ** 2))), 3),
        "maxPx": round(float(np.max(np.abs(r))), 3),
        "observations": len(r),
    }


if __name__ == "__main__":
    pngs = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--png=")]
    only = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--hyp=")), None)
    out_json = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--json=")), None)
    results = []
    for png in pngs:
        path = Path(png)
        m = ML.measure(path)
        row = {"file": str(path), "viewW": m["size"]["w"], "viewH": m["size"]["h"]}
        for hyp in (("camera", "focal") if not only else (only,)):
            row[hyp] = fit_one(m, hyp)
        results.append(row)
        cells = []
        for hyp in (("camera", "focal") if not only else (only,)):
            r = row.get(hyp, {})
            cells.append(f"{hyp} S={r['scale']:.4f} rms={r['rmsPx']:6.2f}"
                         if "scale" in r else f"{hyp} FAILED")
        print(f"{path.name:34s} {row['viewW']}x{row['viewH']}  " + "   ".join(cells))
    if out_json:
        Path(out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(out_json).write_text(json.dumps(results, indent=2))
