#!/usr/bin/env python3
"""
Landscape rest phase, judged against the RUNTIME law.

The F2.5 record judged the phase rule using the scale the offline fitter
recovered. That is not what ships: the runtime uses S = width / 1440 for
landscape, unconditionally. So the 4/9 agreement figure was never the running
code's agreement. This recomputes it properly.

Parity is classified DIRECTLY from the Target's row structure -- which row
carries a centre gutter -- and never from a scale fit. A scale fit that fails
says nothing about parity; they are different observations and are reported
separately.

Usage: f26-landscape-phase.py --glob=<dir> [--glob=<dir>] --out=<json> --sheet=<png>
"""
from __future__ import annotations
import importlib.util, json, math, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ML = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location("ml", HERE / "measure-layout.py"))
importlib.util.spec_from_file_location("ml", HERE / "measure-layout.py").loader.exec_module(ML)

CELL_W = 561.14
REF_W = 1440.0


def runtime_scale(w, h, params):
    if w < h:
        return (params["gainBase"] + params["gainSlope"] * (w / h - 0.5)) * w / REF_W
    return w / REF_W


def direct_parity(m):
    """Parity of the row nearest the viewport's vertical centre, read straight
    off the structure. No scale fit is involved."""
    W, H = m["size"]["w"], m["size"]["h"]
    rows = [r for r in m["rows"] if r["verticalGutters"]]
    if not rows:
        return None, None
    r = min(rows, key=lambda x: abs((x["y0"] + x["y1"]) / 2 - H / 2))
    kind = ("centre-gutter"
            if any(abs(g["center"] - W / 2) < W * 0.06 for g in r["verticalGutters"])
            else "centre-card")
    return kind, round((r["y0"] + r["y1"]) / 2, 1)


def model_parity(w, h, params, mode, phase_x):
    """What the runtime renders: parity of the row nearest the viewport centre."""
    import importlib.util as iu
    spec = iu.spec_from_file_location("f25", HERE / "f25-joint-fit.py")
    F = iu.module_from_spec(spec); spec.loader.exec_module(F)
    orig = F.rest_phase_x
    F.rest_phase_x = lambda a, b, c, d: phase_x
    try:
        rows = F.row_geometry(w, h, params, mode)
    finally:
        F.rest_phase_x = orig
    cand = [r for r in rows if r["gutters"]]
    if not cand:
        return None
    r = min(cand, key=lambda x: abs(x["centre"] - h / 2))
    return "centre-gutter" if any(abs(g - w / 2) < w * 0.06 for g in r["gutters"]) else "centre-card"


if __name__ == "__main__":
    args = sys.argv[1:]
    dirs = [Path(a.split("=", 1)[1]) for a in args if a.startswith("--glob=")]
    out = Path(next((a.split("=", 1)[1] for a in args if a.startswith("--out=")),
                    "qa-v5/f26/landscape-phase.json"))
    sheet = next((a.split("=", 1)[1] for a in args if a.startswith("--sheet=")), None)
    params = json.loads(Path("qa-v5/f26/params.json").read_text())["tangent"]
    # The shipped rule: portrait, or a wide-and-short landscape window, takes
    # the half-cell phase. Threshold is the midpoint of the 0.545-0.56 plateau.
    aspect_threshold = float(next((a.split("=", 1)[1] for a in args
                                   if a.startswith("--aspect-threshold=")), "0.5525"))

    seen, rows = set(), []
    for d in dirs:
        for png in sorted(d.glob("*.png")):
            stem = png.stem.split("-dpr")[0]
            if "x" not in stem or "-" in stem.split("x")[1]:
                continue
            try:
                w, h = (int(v) for v in stem.split("x"))
            except ValueError:
                continue
            if w < h or (w, h) in seen:
                continue
            seen.add((w, h))
            m = ML.measure(png)
            parity, row_y = direct_parity(m)
            S = runtime_scale(w, h, params)
            phase = CELL_W / 2 if (w < h or h < aspect_threshold * w) else 0.0
            pred = model_parity(w, h, params, "tangent", phase)
            rows.append({
                "viewport": f"{w}x{h}", "viewportCss": [w, h],
                "targetDirectParity": parity, "targetParityRowCentre": row_y,
                "targetRestPhase": None,
                "runtimeCompositionScale": round(S, 5),
                "runtimeRestOffsetX": round(phase, 2),
                "runtimePredictedParity": pred,
                "runtimeLawAgrees": (parity is not None and pred is not None and parity == pred),
                "fitRmsPx": None,
            })
    # A phase that would make the runtime agree, so the data can be read directly.
    for r in rows:
        w, h = r["viewportCss"]
        for phase, name in ((0.0, "0"), (CELL_W / 2, "cellW/2")):
            if model_parity(w, h, params, "tangent", phase) == r["targetDirectParity"]:
                r["targetRestPhase"] = name
                break
    rows.sort(key=lambda r: r["viewportCss"][0])
    agree = [r for r in rows if r["runtimeLawAgrees"]]
    half = [r["viewportCss"][0] for r in rows if r["targetRestPhase"] == "cellW/2"]
    zero = [r["viewportCss"][0] for r in rows if r["targetRestPhase"] == "0"]
    interval = None
    if half and zero:
        lo, hi = min(half), max(half)
        if not any(lo <= z <= hi for z in zero):
            interval = {"lowerBreakpointPx": lo, "upperBreakpointPx": hi,
                        "statement": f"half-cell for {lo} <= width <= {hi}, zero outside",
                        "separable": True}
        else:
            interval = {"separable": False,
                        "halfCellWidths": sorted(half), "zeroWidths": sorted(zero),
                        "note": "half-cell and zero widths interleave, so no single CSS-width "
                                "interval separates them"}
    payload = {
        "question": "Judged against the RUNTIME law, where does the Target take a half-cell "
                    "rest phase?",
        "runtimeLandscapeScale": "S = width / 1440",
        "shippedRule": "restOffsetX = (portrait || height < 0.5525 * width) ? cellW/2 : 0",
        "aspectThreshold": aspect_threshold,
        "thresholdPlateau": [0.545, 0.56],
        "supersededRule": "scale switch at 0.674, which scored 23/39 against the runtime law",
        "parityMethod": "direct row-structure classification; no scale fit involved",
        "agreement": {"agrees": len(agree), "of": len(rows),
                      "disagreeing": [r["viewport"] for r in rows if not r["runtimeLawAgrees"]]},
        "cssWidthIntervalHypothesis": interval,
        "viewports": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"{'viewport':>10} {'S(runtime)':>11} {'restX':>8} {'target':>14} {'runtime':>14} {'ok':>6}")
    for r in rows:
        print(f"{r['viewport']:>10} {r['runtimeCompositionScale']:11.4f} {r['runtimeRestOffsetX']:8.1f} "
              f"{str(r['targetDirectParity']):>14} {str(r['runtimePredictedParity']):>14} "
              f"{str(r['runtimeLawAgrees']):>6}")
    print(f"agreement {len(agree)}/{len(rows)}")
    print("interval hypothesis:", json.dumps(interval))
