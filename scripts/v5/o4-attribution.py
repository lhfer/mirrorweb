#!/usr/bin/env python3
"""O4B — frozen body floor attribution (§六).

Reads the factorial captures and computes, for every factor, on every
scored measurand:

  main effect      mean(factor current) - mean(factor neutralised).
                   Positive means neutralising the factor REDUCES the
                   measurand -- i.e. the factor was contributing to the
                   body floor.
  interactions     every two-factor interaction, and each factor's total
                   interaction magnitude.
  Shapley          exact, over the full factorial: the factor's average
                   marginal contribution to the reduction from all-current
                   to all-neutralised, over every order in which the
                   factors could be switched.

Every number is computed on BOTH band width (the gate measurand, but
thresholded and lumpy) and band energy (continuous). Interaction dominance
is read from the continuous one, as the sealed instrument contract
registered before any of this ran.

No product default changes here. §六 forbids it.

Usage: o4-attribution.py [--factorial=<dir>] [--vp=1440x900] [--out=<json>]
"""
from __future__ import annotations

import importlib.util
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o4_att_stats", "o2_optics_stats.py")
I = _load("o4_att_ins", "o4_instruments.py")

FACTORS = ["A", "B", "C", "D", "E", "N"]
FACTOR_NAME = {
    "A": "refraction displacement", "B": "blur / mip sampling",
    "C": "adaptive body shaping", "D": "dispersion",
    "E": "output transform", "N": "refraction normal repair",
}
#: §六's design is the 2^5 over A..E. N is a sixth axis the O4A audit made
#: necessary; it is reported separately wherever "the five" matters.
FIVE = ["A", "B", "C", "D", "E"]

TARGET_BAND = {"1440x900": 3.3, "390x844": 1.5, "844x390": 2.0}


def rects_for(vp):
    w, h = (int(x) for x in vp.split("x"))
    r = [q for _, q in S.rects_at(w, h)]
    if r:
        return r, "fully-visible cards"
    VC, SL = sys.modules["v0_culling"], sys.modules["source_layout"]
    frame = SL.layout(w, h)
    cam = VC.coverage_camera(0.0, 0.0, frame)
    cand = []
    for v in VC.frame_verdicts(0.0, 0.0, cam, frame).values():
        if v.get("draw") and v.get("aabb"):
            x0, y0, x1, y1 = v["aabb"]
            cand.append((x1 - x0, (int(max(x0, 0)), int(max(y0, 0)),
                                   int(min(x1, w)), int(min(y1, h)))))
    return ([max(cand)[1]] if cand else []), "no fully-visible card -- widest drawn"


def measure(path, rects, vp, silhouette, control_path):
    img = Image.open(path)
    w, h = (int(x) for x in vp.split("x"))
    out = {}
    out.update({k: v for k, v in S.stats(img, rects, w, h).items()
                if k in ("edgeChromaMean", "fringeRB", "fringeWidthPxMean",
                         "whiteReflectionRatio", "edgeLuminanceMean")})
    out.update(S.side_bands(img, rects))
    out["bandWidthPx"] = I.band_width_px(img, rects)["meanPx"]
    out["bandEnergy"] = I.band_energy(img, rects)["meanEnergy"]
    interior = S.interior_stats(img, rects)
    out.update(interior)
    if silhouette is not None:
        g = I.gutter_outside_silhouette(path, silhouette)
        out["gutterInkOutsideSilhouette"] = g["gutterInkRatio"]
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    b = np.asarray(Image.open(control_path).convert("RGB")).astype(int)
    d = np.abs(a - b).max(axis=2)
    out["differingPixelsVsControl"] = int((d > 0).sum())
    out["maxChannelDeltaVsControl"] = int(d.max())
    return out


def bits(code):
    return {f: code[i] == "1" for i, f in enumerate(FACTORS)}


def shapley(values, factors):
    """Exact Shapley over `factors`, on v(S) = f(all-current) - f(S)."""
    n = len(factors)
    base = values["".join("0" for _ in FACTORS)]
    idx = {f: FACTORS.index(f) for f in factors}

    def code_of(subset):
        c = ["0"] * len(FACTORS)
        for f in subset:
            c[idx[f]] = "1"
        return "".join(c)

    def v(subset):
        c = code_of(subset)
        return base - values[c] if c in values else None

    phi = {}
    for f in factors:
        others = [g for g in factors if g != f]
        total = 0.0
        for k in range(len(others) + 1):
            weight = math.factorial(k) * math.factorial(n - k - 1) / math.factorial(n)
            for subset in itertools.combinations(others, k):
                a, b = v(list(subset) + [f]), v(list(subset))
                if a is None or b is None:
                    continue
                total += weight * (a - b)
        phi[f] = round(total, 4)
    return phi


def main() -> int:
    opts = {"factorial": REPO / "artifacts/optics-o4/factorial",
            "vp": "1440x900",
            "out": REPO / "qa-v5/optics-o4/body-floor-factorial.json"}
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k in opts:
            opts[k] = v if k == "vp" else Path(v)
    fd, vp = Path(opts["factorial"]), opts["vp"]
    man = json.loads((fd / f"manifest-{vp}.json").read_text())
    rects, basis = rects_for(vp)

    lanes = [r for r in man["records"] if r["kind"] == "lane"]
    media = sorted({r["asset"] for r in lanes})
    cells = {}
    for asset in media:
        mo = next((r for r in man["records"]
                   if r["kind"] == "media-only" and r["asset"] == asset), None)
        ctrl = next(r for r in lanes
                    if r["asset"] == asset and r["bodyDiag"] == "000000")
        sil = (I.true_silhouette(fd / ctrl["file"], fd / mo["file"])
               if mo else None)
        per_lane = {}
        for r in lanes:
            if r["asset"] != asset:
                continue
            per_lane[r["bodyDiag"]] = {
                **measure(fd / r["file"], rects, vp, sil, fd / ctrl["file"]),
                "programSha256": r["programSha256"],
            }
        cells[asset] = {"lanes": per_lane,
                        "silhouettePixels": int(sil.sum()) if sil is not None else None}

    # ------------------------------------------------------------ effects --
    MEASURANDS = ["bandWidthPx", "bandEnergy", "darkSideEdgeLuma",
                  "edgeChromaMean", "whiteReflectionRatio"]
    effects = {}
    for m in MEASURANDS:
        per_media = {}
        for asset, cell in cells.items():
            vals = {c: v[m] for c, v in cell["lanes"].items() if v[m] is not None}
            if len(vals) < 64:
                continue
            main = {}
            for f in FACTORS:
                i = FACTORS.index(f)
                lo = [v for c, v in vals.items() if c[i] == "0"]
                hi = [v for c, v in vals.items() if c[i] == "1"]
                main[f] = round(float(np.mean(lo) - np.mean(hi)), 4)
            inter = {}
            for f, g in itertools.combinations(FACTORS, 2):
                i, j = FACTORS.index(f), FACTORS.index(g)
                # standard two-factor interaction of a 2^k design
                def mean_at(bf, bg):
                    sel = [v for c, v in vals.items()
                           if c[i] == bf and c[j] == bg]
                    return float(np.mean(sel))
                inter[f + g] = round(
                    ((mean_at("1", "1") - mean_at("1", "0"))
                     - (mean_at("0", "1") - mean_at("0", "0"))) / 2.0, 4)
            per_media[asset] = {
                "allCurrent": vals["000000"], "allNeutralised": vals["111111"],
                "mainEffect": main,
                "interaction2": inter,
                "interactionMagnitude": {
                    f: round(float(sum(abs(v) for k, v in inter.items()
                                       if f in k)), 4) for f in FACTORS},
                "shapleySix": shapley(vals, FACTORS),
                "shapleyFive": shapley(
                    {c: v for c, v in vals.items() if c[5] == "0"}, FIVE),
            }
        effects[m] = per_media

    doc = {
        "what": "O4B frozen body floor attribution. System B OFF; the "
                "all-current lane in that state is the accepted O2 body with "
                "the reflection neutralised.",
        "viewport": vp, "metricBasis": basis,
        "design": man["design"], "factorMeaning": man["factorMeaning"],
        "targetBandPx": TARGET_BAND.get(vp),
        "measurands": {
            "primary": "bandWidthPx -- the gate measurand",
            "continuous": "bandEnergy -- registered before capture because a "
                          "thresholded measurand ties and hides interactions; "
                          "interaction dominance is read from it",
        },
        "signConvention": "positive main effect / Shapley = neutralising the "
                          "factor REDUCES the measurand, i.e. the factor was "
                          "contributing to the body floor",
        "cells": cells,
        "effects": effects,
        "noProductDefaultChanged": True,
    }
    Path(opts["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(opts["out"]).write_text(json.dumps(doc, indent=1))

    for m in ["bandWidthPx", "bandEnergy"]:
        print(f"\n=== {m} ===")
        for asset, e in effects[m].items():
            print(f"  {asset:15s} current={e['allCurrent']:8.2f} "
                  f"allNeutral={e['allNeutralised']:8.2f}")
            print("      main   " + "  ".join(
                f"{f}={e['mainEffect'][f]:+7.2f}" for f in FACTORS))
            print("      shap6  " + "  ".join(
                f"{f}={e['shapleySix'][f]:+7.2f}" for f in FACTORS))
    print(f"\n-> {opts['out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
