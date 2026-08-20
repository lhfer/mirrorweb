#!/usr/bin/env python3
"""
Portrait law: what the code runs, versus what cross-validation actually endorsed.

F2.5 shipped gain = 1.9468 - 0.31*(aspect-0.5) from the joint fit, but quoted a
+0.472% hold-out from a DIFFERENT model, 1.87715 + 0.12202*(aspect-0.5). Those
are not the same law and their slopes have opposite signs, so that hold-out
number never applied to the shipped code. This resolves it by building three
runnable candidates and gating all three:

  P0  the law the code runs today, unchanged
  P1  the law cross-validation endorses, with the vertical parameters left
      alone so only the scale changes
  P2  P1's scale locked, and radiusY / cellH / restY0 refitted underneath it

390x844 is held out of P1 and P2 entirely.

Whatever ships must be the parameter set that appears in this file's validated
output -- not a neighbouring one.

Usage: f26-portrait-crossval.py --out=qa-v5/f26/portrait-crossval.json
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("f25", HERE / "f25-joint-fit.py")
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)

REF_W = 1440.0
TRAIN_PORTRAIT = ["360x800", "414x896", "430x932", "390x700", "500x900", "700x900"]
HOLD = "390x844"
TRAIN_ALL = ["1440x900", "1100x720", "1920x1080", "1366x768", "844x390", "1000x700"] + TRAIN_PORTRAIT
P0 = {"radiusY": -4707.6, "cellH": 419.95, "restY0": -200.99,
      "gainBase": 1.9468, "gainSlope": -0.31}


def measured(path="qa-v5/f2/target-measurements.json", rms_max=8.0):
    data = json.loads(Path(path).read_text())
    out = {}
    for v in data["viewports"]:
        f = v["fits"].get("focal", {})
        if "scale" in f and f["rmsPx"] <= rms_max:
            w, h = v["viewportCss"]
            out[v["id"]] = {"w": w, "h": h, "aspect": v["aspect"],
                            "orientation": v["orientation"], "scale": f["scale"],
                            "rms": f["rmsPx"], "gain": f["scale"] * REF_W / w}
    return out


def fit_gain(rows):
    A = np.array([[1.0, r["aspect"] - 0.5] for r in rows])
    y = np.array([r["gain"] for r in rows])
    w = np.array([1 / max(r["rms"], 0.25) ** 2 for r in rows])
    W = np.diag(w)
    c = np.linalg.lstsq(A.T @ W @ A, A.T @ W @ y, rcond=None)[0]
    return float(c[0]), float(c[1])


if __name__ == "__main__":
    out = Path(next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out=")),
                    "qa-v5/f26/portrait-crossval.json"))
    m = measured()
    train_rows = [m[k] for k in TRAIN_PORTRAIT if k in m]
    used = [k for k in TRAIN_PORTRAIT if k in m]
    base, slope = fit_gain(train_rows)

    def err(vp, b, s):
        r = m[vp]
        pred = (b + s * (r["aspect"] - 0.5)) * r["w"] / REF_W
        return round((pred - r["scale"]) / r["scale"] * 100, 3), round(pred, 5)

    P1 = dict(P0, gainBase=round(base, 5), gainSlope=round(slope, 5))

    obs_train = F.load_obs(Path("qa-v5/f2/target-measurements.json"),
                           [v for v in TRAIN_ALL if v != HOLD])
    obs_hold = F.load_obs(Path("qa-v5/f2/target-measurements.json"), [HOLD])
    fixed = {"gainBase": P1["gainBase"], "gainSlope": P1["gainSlope"]}
    free = ["radiusY", "cellH", "restY0"]
    sol = least_squares(F.residuals, [P1["radiusY"], P1["cellH"], P1["restY0"]],
                        args=(free, obs_train, "tangent", fixed),
                        bounds=([-40000, 380, -260], [-600, 470, -160]),
                        loss="soft_l1", f_scale=8.0, xtol=1e-12, ftol=1e-12, max_nfev=3000)
    P2 = dict(fixed); P2.update(dict(zip(free, [round(float(x), 4) for x in sol.x])))

    def stats(p, obs):
        r = np.abs(F.residuals([], [], obs, "tangent", p))
        return {"medianPx": round(float(np.median(r)), 3),
                "p90Px": round(float(np.percentile(r, 90)), 3),
                "maxPx": round(float(np.max(r)), 3), "n": len(r)}

    payload = {
        "problem": "F2.5 shipped one portrait law and quoted another law's hold-out number. "
                   "Slopes even had opposite signs. These are the three runnable candidates.",
        "heldOut": HOLD, "trainedOn": used,
        "candidates": {
            "P0": {"label": "law the code runs today", "params": P0,
                   "scaleHoldOutErrorPct": err(HOLD, P0["gainBase"], P0["gainSlope"])[0],
                   "scalePredicted": err(HOLD, P0["gainBase"], P0["gainSlope"])[1],
                   "trainStats": stats(P0, obs_train), "holdOutStats": stats(P0, obs_hold)},
            "P1": {"label": "cross-validated scale law, vertical unchanged", "params": P1,
                   "scaleHoldOutErrorPct": err(HOLD, P1["gainBase"], P1["gainSlope"])[0],
                   "scalePredicted": err(HOLD, P1["gainBase"], P1["gainSlope"])[1],
                   "trainStats": stats(P1, obs_train), "holdOutStats": stats(P1, obs_hold)},
            "P2": {"label": "cross-validated scale law with vertical refitted under it",
                   "params": P2,
                   "scaleHoldOutErrorPct": err(HOLD, P2["gainBase"], P2["gainSlope"])[0],
                   "scalePredicted": err(HOLD, P2["gainBase"], P2["gainSlope"])[1],
                   "trainStats": stats(P2, obs_train), "holdOutStats": stats(P2, obs_hold)},
        },
        "measuredScales": {k: {"scale": v["scale"], "gain": round(v["gain"], 5),
                               "rms": v["rms"], "orientation": v["orientation"]}
                           for k, v in sorted(m.items())},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    for k, c in payload["candidates"].items():
        p = c["params"]
        print(f"{k}: gain {p['gainBase']:.5f} {p['gainSlope']:+.5f}  radiusY {p['radiusY']:>9.1f} "
              f"cellH {p['cellH']:.2f} restY0 {p['restY0']:.2f}  scaleHoldOut "
              f"{c['scaleHoldOutErrorPct']:+.3f}%  trainMed {c['trainStats']['medianPx']} "
              f"holdMed {c['holdOutStats']['medianPx']}")
    print(f"wrote {out}")
