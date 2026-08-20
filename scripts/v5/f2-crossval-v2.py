#!/usr/bin/env python3
"""
F2 cross-validation, rebuilt.

The previous version was wrong and is replaced. It stored the *gain* 1.8975 in
a table labelled "scale", then divided it by width/1440 as if it were a scale --
so every portrait viewport reported a measuredScale of 1.8975, the four portrait
entries were pre-loaded with the same answer, and the viewport documented as
held out was in fact in the table. None of that constituted validation.

This version reads independently measured scales from
qa-v5/f2/target-measurements.json, which is produced by the detector and the
scale fitter and never by evaluating the responsive law.

  landscape: leave-one-out over every landscape viewport
  portrait : trained on 360x800 / 414x896 / 430x932 ONLY
             primary hold-out 390x844 (the gated viewport, absent from the fit)
             further validation on 390x700, 390x1000, 500x900, 320x900, 700x900
"""
from __future__ import annotations
import json, sys
from pathlib import Path

REF_W = 1440.0
TRAIN_PORTRAIT = ["360x800", "414x896", "430x932"]
HOLDOUT_PRIMARY = "390x844"
EXTRA_PORTRAIT = ["390x700", "390x1000", "500x900", "320x900", "700x900"]


def load(path: Path, hyp: str) -> dict:
    data = json.loads(path.read_text())
    out = {}
    for v in data["viewports"]:
        fit = v["fits"].get(hyp, {})
        if "scale" not in fit:
            continue
        w, h = v["viewportCss"]
        bands = [b for b in v["structure"]["bands"] if not b["touchesFrameEdge"]]
        out[v["id"]] = {
            "id": v["id"], "w": w, "h": h, "orientation": v["orientation"],
            "aspect": v["aspect"], "measuredScale": fit["scale"],
            "measuredScrollX": fit["scrollX"], "measuredScrollY": fit["scrollY"],
            "fitRmsPx": fit["rmsPx"], "fitMaxPx": fit["maxPx"],
            "impliedGain": round(fit["scale"] * REF_W / w, 5),
            "rowBands": [round(b["centre"], 1) for b in bands],
            "rowHeights": [round(r["height"], 1) for r in v["structure"]["rows"] if not r["clipped"]],
            "gutterCentres": [[round(g, 1) for g in r["gutterCentres"]]
                              for r in v["structure"]["rows"]],
            "capture": v["capture"],
        }
    return out


def weighted_gain(rows: list[dict]) -> float:
    """Inverse-variance weighting: a fit that landed at 1 px says more than one
    that landed at 6 px."""
    num = den = 0.0
    for r in rows:
        wgt = 1.0 / max(r["fitRmsPx"], 0.25) ** 2
        num += r["impliedGain"] * wgt
        den += wgt
    return num / den if den else float("nan")


def score(rows: list[dict], gain: float) -> list[dict]:
    out = []
    for r in rows:
        pred = gain * r["w"] / REF_W
        out.append({
            "viewport": r["id"], "orientation": r["orientation"], "aspect": r["aspect"],
            "measuredScale": r["measuredScale"], "predictedScale": round(pred, 5),
            "errorPct": round((pred - r["measuredScale"]) / r["measuredScale"] * 100, 3),
            "fitRmsPx": r["fitRmsPx"], "fitMaxPx": r["fitMaxPx"],
            "measuredScrollX": r["measuredScrollX"], "measuredScrollY": r["measuredScrollY"],
        })
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    src = Path(next((a.split("=", 1)[1] for a in args if a.startswith("--in=")),
                    "qa-v5/f2/target-measurements.json"))
    out_dir = Path(next((a.split("=", 1)[1] for a in args if a.startswith("--out=")), "qa-v5/f2"))
    hyp = next((a.split("=", 1)[1] for a in args if a.startswith("--hyp=")), "focal")
    m = load(src, hyp)

    land = [v for v in m.values() if v["orientation"] == "landscape"]
    loo = []
    for held in land:
        rest = [v for v in land if v["id"] != held["id"]]
        g = weighted_gain(rest)
        s = score([held], g)[0]
        s["gainFromOthers"] = round(g, 5)
        s["trainedOn"] = [v["id"] for v in rest]
        loo.append(s)

    port_train = [m[k] for k in TRAIN_PORTRAIT if k in m]
    missing = [k for k in TRAIN_PORTRAIT if k not in m]
    g_p = weighted_gain(port_train) if port_train else float("nan")
    holdout = score([m[HOLDOUT_PRIMARY]], g_p) if HOLDOUT_PRIMARY in m else []
    extra = score([m[k] for k in EXTRA_PORTRAIT if k in m], g_p)

    payload = {
        "hypothesis": hyp,
        "source": str(src),
        "note": "Scales are measured per viewport by scripts/v5/fit-scale.py. No value "
                "in this file is produced by evaluating the shipped responsive law.",
        "landscape": {
            "model": "S = gain * width / 1440",
            "fittedGainAllViewports": round(weighted_gain(land), 5) if land else None,
            "viewports": [v["id"] for v in land],
            "leaveOneOut": loo,
            "worstErrorPct": round(max((abs(r["errorPct"]) for r in loo), default=0.0), 3),
        },
        "portrait": {
            "model": "S = gain * width / 1440",
            "trainedOn": [v["id"] for v in port_train],
            "trainingMissing": missing,
            "fittedGain": round(g_p, 5) if port_train else None,
            "shippedGain": 1.8975,
            "primaryHoldOut": holdout,
            "furtherValidation": extra,
            "worstErrorPct": round(max((abs(r["errorPct"]) for r in holdout + extra), default=0.0), 3),
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cross-validation-v2.json").write_text(json.dumps(payload, indent=2))

    summary = {
        "hypothesisCompared": {},
        "measuredScales": {k: {"scale": v["measuredScale"], "gain": v["impliedGain"],
                               "rms": v["fitRmsPx"], "orientation": v["orientation"],
                               "aspect": v["aspect"]} for k, v in sorted(m.items())},
    }
    for h in ("camera", "focal"):
        mh = load(src, h)
        if not mh:
            continue
        summary["hypothesisCompared"][h] = {
            "viewports": len(mh),
            "meanRmsPx": round(sum(v["fitRmsPx"] for v in mh.values()) / len(mh), 3),
            "maxRmsPx": round(max(v["fitRmsPx"] for v in mh.values()), 3),
        }
    (out_dir / "model-fit-summary.json").write_text(json.dumps(summary, indent=2))

    print(f"landscape gain {payload['landscape']['fittedGainAllViewports']}  "
          f"LOO worst {payload['landscape']['worstErrorPct']}%")
    print(f"portrait  gain {payload['portrait']['fittedGain']} from {payload['portrait']['trainedOn']}  "
          f"shipped {payload['portrait']['shippedGain']}")
    for r in holdout:
        print(f"   HOLD-OUT {r['viewport']}: measured {r['measuredScale']} predicted "
              f"{r['predictedScale']}  err {r['errorPct']:+.2f}%")
    for r in extra:
        print(f"   extra    {r['viewport']}: measured {r['measuredScale']} predicted "
              f"{r['predictedScale']}  err {r['errorPct']:+.2f}%")
