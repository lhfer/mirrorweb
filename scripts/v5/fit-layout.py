#!/usr/bin/env python3
"""
Joint least-squares fit of the grid layout to the 1440x900 Target evidence.

The forward model is an exact mirror of the shipped engine:
  placeTile()  (src/scene/GridCurvature.ts)  +  applyPose() camera
so a fitted parameter set can be pasted into src/config.ts and reproduce the
projection the optimiser scored.

Observations are the gutter-structure measurements of
artifacts/reference/A-1440x900-dpr1/06-rest-5s.png produced by
scripts/v5/measure-layout.py -- card silhouette edges, not blob AABBs.

TILE_W / TILE_H here are the *silhouette* width/height (what a pixel detector
sees, glass rim included). The rim inflation is removed afterwards by
scripts/v5/rim-delta.py, which measures the same detector against a local
render of a known slab size.
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np
from scipy.optimize import least_squares

VIEW_W, VIEW_H = 1440.0, 900.0
FOV_DEG = 48.46
CAM_Z = 1000.0
PERSPECTIVE_PX = 1000.0
CAM_Y = 8.0
LOOK_Y = 0.0

# ---------------------------------------------------------------- projection


def camera_basis():
    """View matrix rows for a camera at (0, CAM_Y, CAM_Z) looking at (0, LOOK_Y, 0)."""
    eye = np.array([0.0, CAM_Y, CAM_Z])
    target = np.array([0.0, LOOK_Y, 0.0])
    fwd = target - eye
    fwd = fwd / np.linalg.norm(fwd)
    up = np.array([0.0, 1.0, 0.0])
    right = np.cross(fwd, up)
    right = right / np.linalg.norm(right)
    trueup = np.cross(right, fwd)
    return eye, right, trueup, fwd


EYE, RIGHT, UP, FWD = camera_basis()
F_PX = (VIEW_H / 2.0) / math.tan(math.radians(FOV_DEG) / 2.0)


def project(pts: np.ndarray, view_w: float = VIEW_W, view_h: float = VIEW_H) -> np.ndarray:
    """
    World points (N,3) -> screen pixels (N,2), y down.

    The engine recomputes fov per resize as 2*atan(height/2 / perspectivePx),
    which pins the focal length at perspectivePx for every viewport size: one
    world unit is one CSS pixel on the z=0 plane, always. That is the same
    contract the Target's HTML overlay declares with `perspective: 1000px`, so
    the model uses the focal length directly instead of a fixed fov.
    """
    f_px = PERSPECTIVE_PX
    rel = pts - EYE
    xc = rel @ RIGHT
    yc = rel @ UP
    zc = rel @ FWD  # positive in front
    zc = np.maximum(zc, 1e-3)
    return np.stack([view_w / 2 + f_px * xc / zc, view_h / 2 - f_px * yc / zc], axis=1)


def brick_column(i: int, j: int) -> float:
    return i + (0.5 if ((j % 2) + 2) % 2 == 1 else 0.0)


def place(i: int, j: int, p: dict):
    """Mirror of placeTile(): vertical-axis cylinder, +Z toward the camera."""
    u = brick_column(i, j) * p["cellW"] - p.get("scrollX", 0.0)
    v = j * p["cellH"] + p["restY0"] - p.get("scrollY", 0.0)
    r = p["radius"]
    theta = u / r
    return (r * math.sin(theta), v, r * (1 - math.cos(theta)), -theta)


def card_quad(i: int, j: int, p: dict, view_w: float = VIEW_W, view_h: float = VIEW_H) -> np.ndarray:
    """Four silhouette corners of card (i, j), projected to screen pixels."""
    gx, gy, gz, roty = place(i, j, p)
    hw, hh = p["tileW"] / 2, p["tileH"] / 2
    ca, sa = math.cos(roty), math.sin(roty)
    pts = []
    for lx, ly in ((-hw, hh), (hw, hh), (hw, -hh), (-hw, -hh)):
        pts.append((gx + lx * ca, gy + ly, gz - lx * sa))
    return project(np.asarray(pts, float), view_w, view_h)


def edge_y_at(quad: np.ndarray, x: float, top: bool) -> float:
    """y of the card's top (or bottom) edge at screen x, matching the detector."""
    a, b = (quad[0], quad[1]) if top else (quad[3], quad[2])
    if abs(b[0] - a[0]) < 1e-6:
        return float((a[1] + b[1]) / 2)
    t = (x - a[0]) / (b[0] - a[0])
    return float(a[1] + t * (b[1] - a[1]))


def edge_slope_deg(quad: np.ndarray, top: bool) -> float:
    a, b = (quad[0], quad[1]) if top else (quad[3], quad[2])
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def aabb(quad: np.ndarray):
    return float(quad[:, 0].min()), float(quad[:, 0].max()), float(quad[:, 1].min()), float(quad[:, 1].max())


# --------------------------------------------------------------- observations
# key: (i, j). Every value is a screen pixel measurement from the Target frame,
# except slopeDeg which is degrees. `w` is the confidence weight.
OBS = [
    # Infinite City -- fully unclipped, on the midline. Highest confidence.
    dict(cell=(0, 0), kind="x0", value=449.0, w=4.0),
    dict(cell=(0, 0), kind="x1", value=990.0, w=4.0),
    dict(cell=(0, 0), kind="topAt", at=719.5, value=459.0, w=4.0),
    dict(cell=(0, 0), kind="botAt", at=719.5, value=859.09, w=4.0),
    # Free State -- left-clipped, bottom row. Vertical edges are clean.
    dict(cell=(-1, 0), kind="x1", value=429.0, w=2.5),
    dict(cell=(-1, 0), kind="topAt", at=214.5, value=458.68, w=2.5),
    dict(cell=(-1, 0), kind="botAt", at=214.5, value=845.87, w=2.5),
    dict(cell=(-1, 0), kind="botSlope", value=3.343, w=1.2),
    # Glass House -- right-clipped mirror of Free State.
    dict(cell=(1, 0), kind="x0", value=1010.0, w=2.5),
    dict(cell=(1, 0), kind="topAt", at=1224.5, value=459.0, w=2.5),
    dict(cell=(1, 0), kind="botAt", at=1224.5, value=846.34, w=2.5),
    dict(cell=(1, 0), kind="botSlope", value=-2.994, w=1.2),
    # Slow Signal -- mid row. Top edge is contaminated by the row above, so only
    # the bottom edge and the two vertical gutters are scored.
    dict(cell=(-1, 1), kind="x0", value=183.0, w=3.0),
    dict(cell=(-1, 1), kind="x1", value=708.0, w=3.0),
    dict(cell=(-1, 1), kind="botAt", at=445.5, value=440.27, w=3.0),
    # Field Notes -- mirror of Slow Signal (layout is symmetric about x=720).
    dict(cell=(0, 1), kind="x0", value=731.0, w=1.5),
    dict(cell=(0, 1), kind="x1", value=1257.0, w=1.5),
    dict(cell=(0, 1), kind="botAt", at=994.5, value=440.67, w=1.5),
    # Mid-row side clips -- only their inner vertical edges are trustworthy.
    dict(cell=(-2, 1), kind="x1", value=168.0, w=1.5),
    dict(cell=(1, 1), kind="x0", value=1271.0, w=1.5),
]

SLOPE_PX_PER_DEG = 4.0  # 1 deg of edge tilt costs the same as 4 px of position


def residuals(vec: np.ndarray) -> np.ndarray:
    p = dict(cellW=vec[0], cellH=vec[1], restY0=vec[2], radius=vec[3], tileW=vec[4], tileH=vec[5])
    quads = {}
    out = []
    for o in OBS:
        cell = o["cell"]
        if cell not in quads:
            quads[cell] = card_quad(cell[0], cell[1], p)
        q = quads[cell]
        k = o["kind"]
        if k == "x0":
            got = aabb(q)[0]
        elif k == "x1":
            got = aabb(q)[1]
        elif k == "topAt":
            got = edge_y_at(q, o["at"], True)
        elif k == "botAt":
            got = edge_y_at(q, o["at"], False)
        elif k == "topSlope":
            got = edge_slope_deg(q, True) * SLOPE_PX_PER_DEG
            out.append(o["w"] * (got - o["value"] * SLOPE_PX_PER_DEG))
            continue
        elif k == "botSlope":
            got = edge_slope_deg(q, False) * SLOPE_PX_PER_DEG
            out.append(o["w"] * (got - o["value"] * SLOPE_PX_PER_DEG))
            continue
        else:
            raise ValueError(k)
        out.append(o["w"] * (got - o["value"]))
    return np.asarray(out)


def report(vec: np.ndarray) -> dict:
    p = dict(cellW=vec[0], cellH=vec[1], restY0=vec[2], radius=vec[3], tileW=vec[4], tileH=vec[5])
    rows = []
    quads = {}
    for o in OBS:
        cell = o["cell"]
        if cell not in quads:
            quads[cell] = card_quad(cell[0], cell[1], p)
        q = quads[cell]
        k = o["kind"]
        if k == "x0":
            got = aabb(q)[0]
        elif k == "x1":
            got = aabb(q)[1]
        elif k == "topAt":
            got = edge_y_at(q, o["at"], True)
        elif k == "botAt":
            got = edge_y_at(q, o["at"], False)
        elif k == "botSlope":
            got = edge_slope_deg(q, False)
        elif k == "topSlope":
            got = edge_slope_deg(q, True)
        rows.append(dict(cell=list(cell), kind=k, target=o["value"], model=round(got, 2),
                         err=round(got - o["value"], 2), w=o["w"]))
    return {"params": {k: round(v, 4) for k, v in p.items()}, "residuals": rows}


def run(seed, label):
    lo = [400.0, 300.0, -400.0, -60000.0, 400.0, 250.0]
    hi = [750.0, 600.0, 0.0, 60000.0, 700.0, 550.0]
    sol = least_squares(residuals, seed, bounds=(lo, hi), xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=40000)
    r = report(sol.x)
    r["cost"] = float(sol.cost)
    r["rmsPx"] = float(np.sqrt(np.mean((residuals(sol.x) / np.array([o["w"] for o in OBS])) ** 2)))
    r["label"] = label
    return r


if __name__ == "__main__":
    results = []
    # Two starts, one per curvature sign, so the optimiser cannot hide the sign
    # question inside a local minimum.
    results.append(run([553.0, 419.0, -209.0, -4600.0, 542.0, 401.0], "convex(r<0) seed"))
    results.append(run([553.0, 419.0, -209.0, 7200.0, 542.0, 401.0], "concave(r>0) seed"))
    results.sort(key=lambda r: r["cost"])
    print(json.dumps(results, indent=2))
