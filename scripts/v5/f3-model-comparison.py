#!/usr/bin/env python3
"""
F3 pre-diagnosis: which model explains the Target's row-height falloff?

Diagnosis only. Nothing here changes product code, and no radiusY is written.

The accepted V5 Foundation geometry (M0) gives every row the same projected
height, because in a vertical-axis cylinder depth is a function of horizontal
position only. Tall Target viewports disagree: their outer rows are measurably
shorter than their inner ones. Three models are fitted to the SAME observations
with ONE shared parameter set across all viewports -- per-viewport parameters
would fit anything and prove nothing:

  M0  horizontal cylinder only                         (the accepted baseline)
  M1  M0 plus a vertical curvature radius              (dual-axis)
  M2  M0 plus a camera pitch (lookY offset)            (simplest alternative)

Cross-validated: one portrait viewport is held out of every fit.
"""
from __future__ import annotations
import importlib.util, json, math, sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ml", HERE / "measure-layout.py")
ML = importlib.util.module_from_spec(spec); spec.loader.exec_module(ML)

WORLD = {"cellW": 561.14, "cellH": 420.43, "radius": -4058.94,
         "tileW": 540.7678, "tileH": 401.5479}
PERSPECTIVE_PX = 1000.0
CAM_Y = 8.0

VIEWPORTS = ["1440x900", "1100x720", "1920x1080", "360x800", "390x844", "414x896", "430x932"]
HOLD_OUT = "414x896"


def scale_of(w: float, h: float) -> float:
    return (1.8975 if w < h else 1.0) * w / 1440.0


def project(pts, vw, vh, f_px, look_y):
    eye = np.array([0.0, CAM_Y, PERSPECTIVE_PX])
    fwd = np.array([0.0, look_y - CAM_Y, -PERSPECTIVE_PX])
    fwd = fwd / np.linalg.norm(fwd)
    right = np.array([1.0, 0.0, 0.0])
    up = np.cross(right, fwd)
    rel = pts - eye
    zc = np.maximum(rel @ fwd, 1e-3)
    return np.stack([vw / 2 + f_px * (rel @ right) / zc,
                     vh / 2 - f_px * (rel @ up) / zc], axis=1)


def row_heights(vw, vh, model, params, scroll_x, scroll_y):
    """Projected height of each visible row, at the row's own centre column."""
    S = scale_of(vw, vh)
    f_px = PERSPECTIVE_PX * S
    radius_y = params.get("radiusY")
    look_y = params.get("lookY", 0.0)
    vscale = params.get("vScale", 1.0)
    out = []
    for j in range(-6, 7):
        v = j * WORLD["cellH"] - scroll_y
        # vertical curvature: rows away from the axis recede
        z_v = 0.0
        if model == "M1" and radius_y:
            z_v = -(v * v) / (2.0 * radius_y)
        vv = v * vscale
        pts = np.array([[0.0, vv + WORLD["tileH"] / 2, z_v],
                        [0.0, vv - WORLD["tileH"] / 2, z_v]])
        q = project(pts, vw, vh, f_px, look_y)
        top, bot = q[0, 1], q[1, 1]
        if bot < -20 or top > vh + 20:
            continue
        out.append({"j": j, "top": float(top), "bottom": float(bot),
                    "height": float(bot - top), "centre": float((top + bot) / 2)})
    return out


def observed(png: Path, dpr: float = 1.0):
    m = ML.measure(png)
    H = m["size"]["h"]
    rows = [r for r in m["rows"] if not r["clippedTop"] and not r["clippedBottom"]]
    return [{"centre": (r["y0"] + r["y1"]) / 2 / dpr, "height": (r["y1"] - r["y0"] + 1) / dpr}
            for r in rows], m["size"]["w"] / dpr, H / dpr


def residuals(vec, model, obs, free):
    params = dict(zip(free, vec))
    out = []
    for o in obs:
        vw, vh, rows = o["vw"], o["vh"], o["rows"]
        sy = params.get(f"scrollY_{o['id']}", 0.0)
        pred = row_heights(vw, vh, model, params, 0.0, sy)
        for r in rows:
            cands = [p for p in pred if abs(p["centre"] - r["centre"]) < vh * 0.12]
            if not cands:
                out.append(40.0)
                continue
            best = min(cands, key=lambda p: abs(p["centre"] - r["centre"]))
            out.append(best["height"] - r["height"])
            out.append(0.5 * (best["centre"] - r["centre"]))
    return np.asarray(out, float)


def fit(model, obs):
    free, seed, lo, hi = [], [], [], []
    if model == "M1":
        free.append("radiusY"); seed.append(1600.0); lo.append(300.0); hi.append(200000.0)
    if model == "M2":
        free.append("lookY"); seed.append(0.0); lo.append(-400.0); hi.append(400.0)
        free.append("vScale"); seed.append(1.0); lo.append(0.8); hi.append(1.2)
    for o in obs:
        free.append(f"scrollY_{o['id']}"); seed.append(-209.97)
        lo.append(-3 * WORLD["cellH"]); hi.append(3 * WORLD["cellH"])
    sol = least_squares(residuals, seed, args=(model, obs, free), bounds=(lo, hi),
                        xtol=1e-12, ftol=1e-12, max_nfev=4000)
    params = dict(zip(free, sol.x))
    r = residuals(sol.x, model, obs, free)
    return params, float(np.sqrt(np.mean(r ** 2))), float(np.max(np.abs(r)))


def evaluate(model, params, o):
    sy = params.get(f"scrollY_{o['id']}")
    if sy is None:
        # held-out viewport: only its own vertical offset is re-fitted, shared
        # shape parameters stay frozen at the trained values.
        def res(v):
            p = dict(params); p[f"scrollY_{o['id']}"] = v[0]
            return residuals([v[0]], model, [o], [f"scrollY_{o['id']}"]) if False else \
                _res_one(model, p, o)
        sol = least_squares(lambda v: _res_one(model, {**params, f"scrollY_{o['id']}": v[0]}, o),
                            [-209.97], bounds=([-3 * WORLD["cellH"]], [3 * WORLD["cellH"]]),
                            xtol=1e-12, ftol=1e-12, max_nfev=800)
        sy = float(sol.x[0])
    r = _res_one(model, {**params, f"scrollY_{o['id']}": sy}, o)
    pred = row_heights(o["vw"], o["vh"], model, params, 0.0, sy)
    return {"viewport": o["id"], "scrollY": round(sy, 2),
            "rmsPx": round(float(np.sqrt(np.mean(r ** 2))), 3),
            "maxPx": round(float(np.max(np.abs(r))), 3),
            "observedRowHeights": [round(x["height"], 1) for x in o["rows"]],
            "modelRowHeights": [round(x["height"], 1) for x in pred],
            "observedRowCentres": [round(x["centre"], 1) for x in o["rows"]],
            "modelRowCentres": [round(x["centre"], 1) for x in pred],
            "observedBandCount": len(o["rows"]), "modelRowCount": len(pred)}


def _res_one(model, params, o):
    out = []
    sy = params.get(f"scrollY_{o['id']}", 0.0)
    pred = row_heights(o["vw"], o["vh"], model, params, 0.0, sy)
    for r in o["rows"]:
        cands = [p for p in pred if abs(p["centre"] - r["centre"]) < o["vh"] * 0.12]
        if not cands:
            out.append(40.0); continue
        best = min(cands, key=lambda p: abs(p["centre"] - r["centre"]))
        out.append(best["height"] - r["height"])
        out.append(0.5 * (best["centre"] - r["centre"]))
    return np.asarray(out, float)


if __name__ == "__main__":
    root = Path("artifacts/v5-target")
    obs = []
    for vp in VIEWPORTS:
        png = root / f"{vp}-dpr1.png"
        if not png.exists():
            print(f"missing {png}"); continue
        rows, vw, vh = observed(png)
        obs.append({"id": vp, "vw": vw, "vh": vh, "rows": rows})

    train = [o for o in obs if o["id"] != HOLD_OUT]
    held = [o for o in obs if o["id"] == HOLD_OUT]

    results = {}
    for model in ("M0", "M1", "M2"):
        params, rms, mx = fit(model, train)
        shared = {k: round(v, 4) for k, v in params.items() if not k.startswith("scrollY_")}
        per_vp = [evaluate(model, params, o) for o in obs]
        results[model] = {
            "sharedParameters": shared or {"(none)": "M0 has no extra shape parameter"},
            "trainRmsPx": round(rms, 3), "trainMaxPx": round(mx, 3),
            "perViewport": per_vp,
            "heldOut": [p for p in per_vp if p["viewport"] == HOLD_OUT],
            "desktopRegression": [p for p in per_vp if p["viewport"] in
                                  ("1440x900", "1100x720", "1920x1080")],
        }
        print(f"{model}: train rms {rms:.2f} px  max {mx:.2f} px  shared {shared}  "
              f"held-out({HOLD_OUT}) rms "
              f"{results[model]['heldOut'][0]['rmsPx'] if results[model]['heldOut'] else 'n/a'}")

    out = Path("qa-v5/f3-diagnosis"); out.mkdir(parents=True, exist_ok=True)
    (out / "model-comparison.json").write_text(json.dumps({
        "note": "Diagnosis only. No product code is changed and no radiusY is implemented.",
        "models": {"M0": "horizontal cylinder only (accepted V5 Foundation baseline)",
                   "M1": "M0 + vertical curvature radius (dual axis)",
                   "M2": "M0 + camera pitch (lookY) + vertical composition scale"},
        "viewports": VIEWPORTS, "heldOut": HOLD_OUT,
        "sharedParameterPolicy": "one shared shape parameter set across all viewports; "
                                 "only each viewport's own vertical rest offset is free",
        "results": results}, indent=2))
    (out / "held-out-results.json").write_text(json.dumps(
        {m: results[m]["heldOut"] for m in results}, indent=2))
    (out / "row-height-curves.json").write_text(json.dumps(
        {"observed": {o["id"]: {"centres": [round(r["centre"], 1) for r in o["rows"]],
                                "heights": [round(r["height"], 1) for r in o["rows"]]} for o in obs},
         "models": {m: {p["viewport"]: {"centres": p["modelRowCentres"],
                                        "heights": p["modelRowHeights"]}
                        for p in results[m]["perViewport"]} for m in results}}, indent=2))
    print(f"wrote {out}/model-comparison.json")
