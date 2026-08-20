#!/usr/bin/env python3
"""
F2.5 joint recovery: portrait scale, vertical depth and rest phase together.

These three are coupled. Locking the portrait gain under a flat-grid model and
then attributing the leftover error to a vertical radius produces a confident
wrong answer, so nothing is locked first: one shared parameter set is solved
against every viewport at once, with NO per-viewport freedom at all.

Shared free parameters
    radiusY                exact cosine vertical curvature (negative = recede)
    cellH                  vertical cell pitch
    restY0                 vertical rest phase
    portraitGainBase       portrait gain at aspect 0.5
    portraitGainSlope      d(gain)/d(aspect); zero it to test whether the term
                           is earning its place

Fixed by prior acceptance and not refitted here: TILE, GRID.cellW, the
horizontal radius, the landscape gain (1.0), and the rest-phase regime switch.

Observations come from qa-v5/f2/target-measurements.json, which the detector and
the scale fitter produce and no responsive law ever touches.

Usage: f25-joint-fit.py [--mode=depth|tangent] [--slope-free] [--holdout=390x844]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

CELL_W = 561.14
RADIUS_X = -4058.94
TILE_W, TILE_H = 540.7678, 401.5479
PERSPECTIVE_PX = 1000.0
CAM_Y = 8.0
REF_W = 1440.0
REST_PHASE_SWITCH = 0.674

TRAIN = ["1440x900", "1100x720", "1920x1080", "1366x768", "844x390", "1000x700",
         "360x800", "390x844", "414x896", "430x932", "390x700", "500x900", "700x900"]
ANOMALY = ["320x900", "390x1000"]


def brick(i: int, j: int) -> float:
    return i + (0.5 if ((j % 2) + 2) % 2 == 1 else 0.0)


def scale_of(w: float, h: float, base: float, slope: float) -> float:
    if w < h:
        return (base + slope * (w / h - 0.5)) * w / REF_W
    return w / REF_W


def rest_phase_x(w: float, h: float, base: float, slope: float) -> float:
    return CELL_W / 2 if scale_of(w, h, base, slope) < REST_PHASE_SWITCH else 0.0


def quads(vw, vh, p, mode):
    """Projected card quads, mirroring placeTile() + applyPose() exactly."""
    S = scale_of(vw, vh, p["gainBase"], p["gainSlope"])
    f_px = PERSPECTIVE_PX * S
    sx = rest_phase_x(vw, vh, p["gainBase"], p["gainSlope"])
    eye = np.array([0.0, CAM_Y, PERSPECTIVE_PX])
    fwd = np.array([0.0, -CAM_Y, -PERSPECTIVE_PX])
    fwd /= np.linalg.norm(fwd)
    right = np.array([1.0, 0.0, 0.0])
    up = np.cross(right, fwd)
    hw, hh = TILE_W / 2, TILE_H / 2
    ry = p["radiusY"]
    out = []
    for j in range(-5, 6):
        v = j * p["cellH"] + p["restY0"]
        phi = v / ry
        gy = v                                   # exact cosine DEPTH law: rows
        gz_v = ry * (1 - math.cos(phi))          # recede, they do not slide
        rot_x = math.atan(math.sin(phi)) if mode == "tangent" else 0.0
        cbx, sbx = math.cos(rot_x), math.sin(rot_x)
        for i in range(-4, 5):
            u = brick(i, j) * CELL_W - sx
            th = u / RADIUS_X
            gx = RADIUS_X * math.sin(th)
            gz = RADIUS_X * (1 - math.cos(th)) + gz_v
            ca, sa = math.cos(-th), math.sin(-th)
            pts = []
            for lx, ly in ((-hw, hh), (hw, hh), (hw, -hh), (-hw, -hh)):
                # three.js Euler 'XYZ' with rotZ = 0 gives R = Rx * Ry
                x1, y1, z1 = lx * ca, ly, -lx * sa
                x2, y2, z2 = x1, y1 * cbx - z1 * sbx, y1 * sbx + z1 * cbx
                pts.append((gx + x2, gy + y2, gz + z2))
            a = np.asarray(pts)
            rel = a - eye
            zc = np.maximum(rel @ fwd, 1e-3)
            q = np.stack([vw / 2 + f_px * (rel @ right) / zc,
                          vh / 2 - f_px * (rel @ up) / zc], axis=1)
            if q[:, 0].max() < -30 or q[:, 0].min() > vw + 30:
                continue
            if q[:, 1].max() < -30 or q[:, 1].min() > vh + 30:
                continue
            out.append({"i": i, "j": j, "q": q})
    return out


def row_geometry(vw, vh, p, mode):
    """
    Per-row geometry, analytically.

    An earlier revision scored the fit against a coverage raster, mirroring the
    detector. That is the right way to JUDGE a candidate but a poor way to fit
    one: band presence is a step function, so the residual surface is rugged and
    the optimiser sits in whichever basin it started in. Here the residuals are
    smooth -- projected row centre, row height and gutter position -- and the
    rendered gate remains the authority on whether the result is any good.
    """
    S = scale_of(vw, vh, p["gainBase"], p["gainSlope"])
    f_px = PERSPECTIVE_PX * S
    sx = rest_phase_x(vw, vh, p["gainBase"], p["gainSlope"])
    ry = p["radiusY"]
    rows = []
    for j in range(-4, 5):
        v = j * p["cellH"] + p["restY0"]
        phi = v / ry
        gy = v                                   # exact cosine DEPTH law: rows
        gz_v = ry * (1 - math.cos(phi))          # recede, they do not slide
        rot_x = math.atan(math.sin(phi)) if mode == "tangent" else 0.0
        cbx, sbx = math.cos(rot_x), math.sin(rot_x)

        def project(pt):
            x, y, z = pt
            zc = PERSPECTIVE_PX - z + (CAM_Y - y) * (CAM_Y / PERSPECTIVE_PX)
            zc = max(zc, 1e-3)
            return (vw / 2 + f_px * x / zc, vh / 2 - f_px * (y - CAM_Y) / zc)

        # the row's own central column, where the detector reads its height
        i_centre = -0.5 if ((j % 2) + 2) % 2 == 1 else 0.0
        u0 = i_centre * CELL_W - sx + (CELL_W / 2 if sx else 0.0) * 0
        th0 = u0 / RADIUS_X
        gx0 = RADIUS_X * math.sin(th0)
        gz0 = RADIUS_X * (1 - math.cos(th0)) + gz_v
        tops, bots = [], []
        for ly in (TILE_H / 2, -TILE_H / 2):
            y1, z1 = ly, 0.0
            y2, z2 = y1 * cbx - z1 * sbx, y1 * sbx + z1 * cbx
            sy = project((gx0, gy + y2, gz0 + z2))[1]
            (tops if ly > 0 else bots).append(sy)
        top, bot = tops[0], bots[0]

        gutters = []
        for i in range(-4, 4):
            edges = []
            for k, lx in ((i, TILE_W / 2), (i + 1, -TILE_W / 2)):
                u = brick(k, j) * CELL_W - sx
                th = u / RADIUS_X
                gxk = RADIUS_X * math.sin(th)
                gzk = RADIUS_X * (1 - math.cos(th)) + gz_v
                ca, sa = math.cos(-th), math.sin(-th)
                edges.append(project((gxk + lx * ca, gy, gzk - lx * sa))[0])
            if edges[1] > edges[0]:
                c = (edges[0] + edges[1]) / 2
                if -20 < c < vw + 20:
                    gutters.append(c)
        rows.append({"j": j, "top": top, "bottom": bot, "height": bot - top,
                     "centre": (top + bot) / 2, "gutters": gutters})
    return rows


def load_obs(path: Path, ids: list[str]) -> list[dict]:
    data = json.loads(path.read_text())
    out = []
    for v in data["viewports"]:
        if v["id"] not in ids:
            continue
        w, h = v["viewportCss"]
        bands = [b["centre"] for b in v["structure"]["bands"] if not b["touchesFrameEdge"]]
        rows = [{"centre": r["centre"], "height": r["height"],
                 "gutters": r["gutterCentres"]}
                for r in v["structure"]["rows"] if not r["clipped"]]
        out.append({"id": v["id"], "vw": w, "vh": h, "bands": bands, "rows": rows})
    return out


def residuals(vec, free, obs, mode, fixed):
    p = dict(fixed)
    p.update(dict(zip(free, vec)))
    res = []
    for o in obs:
        rows = row_geometry(o["vw"], o["vh"], p, mode)
        for r in o["rows"]:
            best = min(rows, key=lambda x: abs(x["centre"] - r["centre"]))
            res.append(best["centre"] - r["centre"])
            res.append(best["height"] - r["height"])
            for g in r["gutters"]:
                if best["gutters"]:
                    res.append(0.7 * min(abs(mg - g) for mg in best["gutters"]))
        for y in o["bands"]:
            # a band sits between two rows; score it against the nearest
            # predicted inter-row midpoint
            mids = []
            srt = sorted(rows, key=lambda x: x["centre"])
            for a, b in zip(srt, srt[1:]):
                mids.append((a["bottom"] + b["top"]) / 2)
            if mids:
                res.append(0.8 * min(abs(m - y) for m in mids))
    return np.asarray(res, float)


def fit(obs, mode, slope_free: bool):
    fixed = {"gainSlope": 0.0}
    free = ["radiusY", "cellH", "restY0", "gainBase"]
    seed = [-2053.4, 420.43, -209.97, 1.8636]
    lo = [-40000.0, 380.0, -260.0, 1.60]
    hi = [-600.0, 470.0, -160.0, 2.10]
    if slope_free:
        free.append("gainSlope"); seed.append(0.0); lo.append(-1.5); hi.append(1.5)
        fixed.pop("gainSlope")
    # Robust loss. The Target observations are contaminated: a dark video frame
    # can read as void and open a gutter that is not there (1100x720 reports six
    # gutters in a row that has two; 430x932 reports three where there is one).
    # soft_l1 down-weights those without anyone hand-picking which observations
    # are allowed to count.
    sol = least_squares(residuals, seed, args=(free, obs, mode, fixed),
                        bounds=(lo, hi), loss="soft_l1", f_scale=8.0,
                        xtol=1e-12, ftol=1e-12, max_nfev=3000)
    p = dict(fixed); p.update(dict(zip(free, sol.x)))
    r = residuals(sol.x, free, obs, mode, fixed)
    return p, float(np.sqrt(np.mean(r ** 2))), float(np.max(np.abs(r)))


def score(p, obs, mode):
    out = []
    for o in obs:
        r = np.abs(residuals([], [], [o], mode, p))
        out.append({"viewport": o["id"],
                    "rmsPx": round(float(np.sqrt(np.mean(r ** 2))), 3),
                    "medianPx": round(float(np.median(r)), 3),
                    "p90Px": round(float(np.percentile(r, 90)), 3),
                    "maxPx": round(float(np.max(r)), 3), "observations": len(r)})
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    holdout = next((a.split("=", 1)[1] for a in args if a.startswith("--holdout=")), "390x844")
    src = Path("qa-v5/f2/target-measurements.json")
    results = {}
    for mode in ("depth", "tangent"):
        for slope_free in (False, True):
            key = f"{mode}{'+aspect' if slope_free else ''}"
            train_ids = [v for v in TRAIN if v != holdout]
            obs_train = load_obs(src, train_ids)
            obs_hold = load_obs(src, [holdout])
            obs_anom = load_obs(src, ANOMALY)
            p, rms, mx = fit(obs_train, mode, slope_free)
            allr = np.abs(residuals([], [], obs_train, mode, p))
            results[key] = {
                "mode": mode, "aspectTermFree": slope_free,
                "sharedParameters": {k: round(v, 4) for k, v in p.items()},
                "trainRmsPx": round(rms, 3), "trainMaxPx": round(mx, 3),
                "trainMedianPx": round(float(np.median(allr)), 3),
                "trainP90Px": round(float(np.percentile(allr, 90)), 3),
                "trainedOn": train_ids, "heldOut": holdout,
                "heldOutScore": score(p, obs_hold, mode),
                "perViewport": score(p, obs_train + obs_hold, mode),
                "anomalySmoke": score(p, obs_anom, mode),
            }
            ho = results[key]["heldOutScore"][0]
            print(f"{key:16s} train med {np.median(allr):5.2f} p90 {np.percentile(allr,90):6.2f} "
                  f"rms {rms:6.2f}   held-out {holdout} "
                  f"med {ho['medianPx']:5.2f} p90 {ho['p90Px']:6.2f}   radiusY {p['radiusY']:9.1f} cellH {p['cellH']:7.2f} "
                  f"restY0 {p['restY0']:8.2f} gain {p['gainBase']:.4f}"
                  + (f" slope {p['gainSlope']:+.4f}" if slope_free else ""), flush=True)
    out = Path("qa-v5/f25"); out.mkdir(parents=True, exist_ok=True)
    (out / "model-comparison.json").write_text(json.dumps({
        "note": "Joint recovery. No parameter is locked before the others; no per-viewport "
                "freedom; the portrait gain is NOT seeded from a flat-grid fit result.",
        "fixedByPriorAcceptance": {"TILE": [TILE_W, TILE_H], "cellW": CELL_W,
                                   "horizontalRadius": RADIUS_X, "landscapeGain": 1.0,
                                   "restPhaseScaleSwitch": REST_PHASE_SWITCH},
        "anomalyExcluded": ANOMALY,
        "candidates": results,
    }, indent=2))
    print(f"wrote {out}/model-comparison.json")
