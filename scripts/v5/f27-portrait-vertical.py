#!/usr/bin/env python3
"""
Portrait-only vertical composition: fit and cross-validate V0 / V1 / V2.

The horizontal scale law is frozen this round, so the only lever is vertical.
Everything is measured with the GATE's own instrument -- the same detector, the
same edge-trace validity test, the same row pairing, multi-frame consensus on
the Target -- so a number here means the same thing a number in gate.json means.

Card WIDTH is not used to fit anything: a card offset from the centre line is
yawed, and yaw foreshortens width but not height. Height and row-band pitch
carry the vertical signal cleanly.

Usage:
  f27-portrait-vertical.py --target=<consensus dir> --local=<dir> --out=<json>
                           [--train=a,b] [--holdout=WxH] [--validate=a,b]
"""
from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load("f2_gate", "f2-gate.py")
ML = _load("measure_layout", "measure-layout.py")
TM = _load("f27_target_model", "f27_target_model.py")


def target_structure(root: Path, vp: str) -> dict:
    frames = sorted(str(p) for p in root.glob(f"{vp}-f*.png"))
    if not frames:
        raise SystemExit(f"no Target frames for {vp} in {root}")
    return G.normalise(G.consensus_measure(frames), 1), frames


def local_structure(png: Path) -> dict:
    return G.normalise(ML.measure(png), 1)


def compare(t: dict, l: dict, vw: float, vh: float) -> dict:
    """Row and card correspondence, with the gate's own conditioning."""
    def median_height(rows):
        hs = sorted(r["y1"] - r["y0"] for r in rows)
        return hs[len(hs) // 2] if hs else 0.0
    med = max(median_height(t["rows"]), median_height(l["rows"]))

    def symmetric(row, tol=6.0):
        edges = sorted([c["x0"] for c in row["cards"]] + [c["x1"] for c in row["cards"]])
        mirrored = sorted(vw - 1 - e for e in edges)
        return len(edges) == len(mirrored) and all(abs(a - b) <= tol for a, b in zip(edges, mirrored))

    pairs = G.nearest_pairs(t["rows"], l["rows"], lambda r: r["cy"], vh * 0.12)
    usable = [(a, b) for a, b in pairs
              if (a["y1"] - a["y0"]) >= 0.6 * med and (b["y1"] - b["y0"]) >= 0.6 * med
              and symmetric(a) and symmetric(b)]
    vertical_ok = [(a, b) for a, b in usable if not a["clipped"] and not b["clipped"]]

    heights, widths, yaws, band_err = [], [], [], []
    for rt, rl in usable:
        for ct, cl in G.nearest_pairs(rt["cards"], rl["cards"], lambda c: c["cx"], vw * 0.12):
            if not (ct["unclipped"] and cl["unclipped"]):
                continue
            widths.append((ct["w"], cl["w"]))
            if ct["h"] and cl["h"] and (rt, rl) in vertical_ok:
                heights.append((ct["h"], cl["h"]))
            lever_ok = abs(rt["y1"] - vh / 2) >= vh * 0.15
            if ct["botSlope"] is not None and cl["botSlope"] is not None and lever_ok:
                yaws.append(abs(cl["botSlope"] - ct["botSlope"]))
    t_bands = [b["c"] for b in t["bands"] if not b["edge"]]
    l_bands = [b["c"] for b in l["bands"] if not b["edge"]]
    matched = sorted(((a["c"], b["c"]) for a, b in G.nearest_pairs(
        [{"c": c} for c in t_bands], [{"c": c} for c in l_bands], lambda x: x["c"], vh * 0.08)))
    band_err = [b - a for a, b in matched]

    def pitch(bands):
        """
        Row pitch, or nothing.

        A median of consecutive band gaps is worthless when the detector emits a
        spurious band: two centres a few pixels apart drag the median to junk,
        which is how this statistic produced 0.21 at 700x900. Only report a
        pitch when the detected bands are actually evenly spaced -- every gap
        within 20% of the median -- and say so when they are not.
        """
        if len(bands) < 3:
            return None
        gaps = [b - a for a, b in zip(bands, bands[1:])]
        med = statistics.median(gaps)
        if med <= 0 or any(abs(g - med) > 0.2 * med for g in gaps):
            return None
        return med

    # Pitch from PAIRED bands only. Comparing an unpaired list to an unpaired
    # list compares different rows: at 390x844 the Target keeps a top band the
    # local frame does not, and the two "pitches" then differ by 6% purely from
    # which rows each median happened to average. Sphere curvature also
    # compresses the outermost gaps, so an all-band median is not a pitch at all.
    t_pitch, l_pitch = pitch([a for a, _ in matched]), pitch([b for _, b in matched])
    return {
        "rowsPaired": len(usable), "rowsUsableForHeight": len(vertical_ok),
        "cardHeightPairs": len(heights), "cardWidthPairs": len(widths),
        "targetCardHeights": [round(a, 2) for a, _ in heights],
        "localCardHeights": [round(b, 2) for _, b in heights],
        "targetCardWidths": [round(a, 2) for a, _ in widths],
        "localCardWidths": [round(b, 2) for _, b in widths],
        "worstCardHeightPct": round(max((abs(b - a) / a * 100 for a, b in heights), default=0.0), 3),
        "worstCardWidthPct": round(max((abs(b - a) / a * 100 for a, b in widths), default=0.0), 3),
        "requiredScaleYFromCardHeight":
            round(statistics.median([a / b for a, b in heights]), 5) if heights else None,
        "targetRowBands": [round(x, 1) for x in sorted(t_bands)],
        "localRowBands": [round(x, 1) for x in sorted(l_bands)],
        "worstRowBandCentrePx": round(max((abs(e) for e in band_err), default=0.0), 2),
        "targetRowHeights": [round(r["y1"] - r["y0"] + 1, 2) for r in t["rows"] if not r["clipped"]],
        "localRowHeights": [round(r["y1"] - r["y0"] + 1, 2) for r in l["rows"] if not r["clipped"]],
        "rowPitchResolvable": bool(t_pitch and l_pitch),
        "targetRowPitchPx": round(t_pitch, 2) if t_pitch else None,
        "localRowPitchPx": round(l_pitch, 2) if l_pitch else None,
        "requiredScaleYFromRowPitch": round(t_pitch / l_pitch, 5) if t_pitch and l_pitch else None,
        "worstEdgeYawDeg": round(max(yaws), 3) if yaws else None,
        "centreDarkBand": {
            "target": any(b["y0"] <= vh / 2 <= b["y1"] for b in t["bands"]),
            "local": any(b["y0"] <= vh / 2 <= b["y1"] for b in l["bands"]),
        },
    }


if __name__ == "__main__":
    args = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if "=" in a}
    troot = Path(args["--target"])
    lroot = Path(args["--local"])
    out = Path(args["--out"])
    train = args.get("--train", "360x800,390x700,414x896,430x932,500x900").split(",")
    holdout = args.get("--holdout", "390x844")
    validate = args.get("--validate", "375x812,393x852,428x926,700x900").split(",")
    models = args.get("--models", "v0").split(",")

    per_model = {}
    for model in models:
        rows = {}
        for vp in train + [holdout] + validate + ["1440x900"]:
            png = lroot / model / vp / "01-rest.png"
            if not png.exists():
                png = lroot / vp / "01-rest.png"
            if not png.exists():
                continue
            w, h = map(int, vp.split("x"))
            t, frames = target_structure(troot, vp)
            l = local_structure(png)
            c = compare(t, l, w, h)
            lay = TM.layout(w, h)
            c["viewport"] = [w, h]
            c["aspect"] = round(w / h, 5)
            c["targetFrames"] = len(frames)
            c["sourceExactPlaneSize"] = [round(lay["planeWidth"], 2), round(lay["planeHeight"], 2)]
            c["role"] = ("train" if vp in train else "holdout" if vp == holdout
                         else "validate" if vp in validate else "reference")
            rows[vp] = c
        per_model[model] = rows

    base = per_model.get("v0", {})
    fit_from = [(vp, base[vp]) for vp in train if vp in base
                and base[vp]["requiredScaleYFromCardHeight"]]
    ks = [r["requiredScaleYFromCardHeight"] for _, r in fit_from]
    k_height = round(statistics.median(ks), 5) if ks else None
    kp = [base[vp]["requiredScaleYFromRowPitch"] for vp, _ in fit_from
          if base[vp]["requiredScaleYFromRowPitch"]]
    k_pitch = round(statistics.median(kp), 5) if kp else None

    result = {
        "instrument": "scripts/v5/f27-portrait-vertical.py; gate detector, gate row pairing, "
                      "gate edge-trace validity, 5-frame Target consensus",
        "fitPolicy": "Card WIDTH is never used to fit. A card off the centre line is yawed, and "
                     "yaw foreshortens width but not height, so width would put a phase effect "
                     "into a vertical parameter. Height and row-band pitch are used.",
        "trainViewports": train, "holdoutViewport": holdout, "validationViewports": validate,
        "fitted": {
            "scaleYFromCardHeight": k_height,
            "scaleYFromRowBandPitch": k_pitch,
            "perTrainViewport": {vp: r["requiredScaleYFromCardHeight"] for vp, r in fit_from},
            "spreadPct": round((max(ks) - min(ks)) / statistics.median(ks) * 100, 3) if ks else None,
        },
        "models": per_model,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(f"scaleY from card height {k_height}  from row pitch {k_pitch}")
    for model, rows in per_model.items():
        for vp, r in rows.items():
            print(f"  {model} {vp:>9} [{r['role']:>9}] h%={r['worstCardHeightPct']:6.3f} "
                  f"w%={r['worstCardWidthPct']:6.3f} needK={r['requiredScaleYFromCardHeight']} "
                  f"pitchK={r['requiredScaleYFromRowPitch']} band={r['centreDarkBand']}")
