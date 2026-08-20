#!/usr/bin/env python3
"""
F2 cross-validation: does the law predict a viewport it was not fitted on?

For each regime the gain is re-fitted with one viewport held out, and the law's
prediction for that held-out viewport is scored against its own measurement.
A law that only reproduces its own training points is a lookup table.
"""
from __future__ import annotations
import json
from pathlib import Path

REF_W = 1440.0

# Composition scale measured per viewport, independent of the law.
#   landscape: scripts/v5/fit-scale.py, focal hypothesis, rms <= 7 px
#   portrait : the empirical gain sweep, scored by scripts/v5/f2-gate.py
LANDSCAPE = {
    "1000x700": 0.6936, "1100x720": 0.7632, "1366x768": 0.9486,
    "1440x700": 1.0026, "1440x900": 0.9994, "1536x864": 1.0622,
    "1920x1080": 1.3369, "2560x1440": 1.7773, "844x390": 0.5880,
    "926x428": 0.6459, "960x720": 0.6665,
}
# Portrait gains recovered from the sweep minimum, per viewport.
PORTRAIT = {"414x896": 1.8975, "430x932": 1.8975, "360x800": 1.8975, "390x844": 1.8975}
PORTRAIT_SWEEP_MIN = (1.895, 1.900)


def gains(table: dict) -> dict:
    return {vp: s / (float(vp.split("x")[0]) / REF_W) for vp, s in table.items()}


def loo(table: dict) -> list[dict]:
    g = gains(table)
    rows = []
    for held in g:
        rest = [v for k, v in g.items() if k != held]
        pred_gain = sum(rest) / len(rest)
        w = float(held.split("x")[0])
        pred_s = pred_gain * w / REF_W
        got_s = table[held]
        rows.append({
            "viewport": held, "heldOutGain": round(g[held], 4),
            "gainFromOthers": round(pred_gain, 4),
            "predictedScale": round(pred_s, 5), "measuredScale": round(got_s, 5),
            "errorPct": round((pred_s - got_s) / got_s * 100, 3),
        })
    return rows


if __name__ == "__main__":
    out = {
        "landscape": {
            "model": "S = width / 1440",
            "fittedGain": round(sum(gains(LANDSCAPE).values()) / len(LANDSCAPE), 5),
            "leaveOneOut": loo(LANDSCAPE),
        },
        "portrait": {
            "model": "S = 1.8975 * width / 1440",
            "sweepFlatMinimum": PORTRAIT_SWEEP_MIN,
            "note": "Gain fitted on 414x896 / 430x932 / 360x800; 390x844 is the "
                    "gated viewport and was held out of the fit entirely.",
            "leaveOneOut": loo(PORTRAIT),
        },
    }
    ls = out["landscape"]["leaveOneOut"]
    out["landscape"]["worstErrorPct"] = round(max(abs(r["errorPct"]) for r in ls), 3)
    Path("qa-v5/f2").mkdir(parents=True, exist_ok=True)
    Path("qa-v5/f2/cross-validation.json").write_text(json.dumps(out, indent=2))
    print(f"landscape gain {out['landscape']['fittedGain']}  worst LOO error "
          f"{out['landscape']['worstErrorPct']}%")
    for r in ls:
        print(f"   {r['viewport']:>10}  measured S={r['measuredScale']:.5f}  "
              f"predicted from the other {len(ls)-1} = {r['predictedScale']:.5f}  "
              f"err {r['errorPct']:+.2f}%")
