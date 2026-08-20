#!/usr/bin/env python3
"""
Does the Target really switch regime at width == height?

The shipped law switches on orientation, which would be a ~1.9x instantaneous
scale jump at the square. That was inferred from samples far from the corner.
This measures the corner directly: three viewports either side of 900x900 and
700x700, plus a continuous landscape -> square -> portrait sweep.

Scale is recovered from the row-band pitch, which is a full-width statistic and
does not need a card to be unclipped -- necessary here, because several of these
viewports show only one or two rows.
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ml", HERE / "measure-layout.py")
ML = importlib.util.module_from_spec(spec); spec.loader.exec_module(ML)

CELL_H = 420.43
CELL_W = 561.14


def scale_from_structure(m: dict) -> dict:
    """Composition scale from the row-band pitch, plus the gutter pitch as a
    second, independent estimate."""
    H, W = m["size"]["h"], m["size"]["w"]
    bands = [b["center"] for b in m["horizontalGutterBands"]
             if b["y0"] > 0 and b["y1"] < H - 1 and b["height"] >= 4]
    band_pitch = None
    if len(bands) >= 2:
        d = np.diff(sorted(bands))
        d = d[d > H * 0.08]
        if d.size:
            band_pitch = float(np.median(d))
    gut_pitch = None
    for r in m["rows"]:
        gs = sorted(g["center"] for g in r["verticalGutters"])
        if len(gs) >= 2:
            d = np.diff(gs)
            d = d[d > W * 0.15]
            if d.size:
                gut_pitch = float(np.median(d))
                break
    return {
        "rowBandPitchPx": round(band_pitch, 2) if band_pitch else None,
        "scaleFromRowPitch": round(band_pitch / CELL_H, 5) if band_pitch else None,
        "gutterPitchPx": round(gut_pitch, 2) if gut_pitch else None,
        "scaleFromGutterPitch": round(gut_pitch / CELL_W, 5) if gut_pitch else None,
        "rowBands": [round(b, 1) for b in bands],
        "parityOfLowestRow": ("centre-gutter"
                              if any(abs(g["center"] - W / 2) < W * 0.06
                                     for r in m["rows"][-1:] for g in r["verticalGutters"])
                              else "centre-card"),
    }


if __name__ == "__main__":
    args = sys.argv[1:]
    dirs = [Path(a.split("=", 1)[1]) for a in args if a.startswith("--glob=")]
    out = next((a.split("=", 1)[1] for a in args if a.startswith("--out=")), "qa-v5/f2/orientation-boundary.json")
    rows = []
    for d in dirs:
        for png in sorted(d.glob("*.png")):
            stem = png.stem.split("-dpr")[0]
            if "x" not in stem:
                continue
            try:
                w, h = (int(v) for v in stem.split("x"))
            except ValueError:
                continue
            m = ML.measure(png)
            s = scale_from_structure(m)
            law_gain = 1.8975 if w < h else 1.0
            pred = law_gain * w / 1440
            meas = s["scaleFromRowPitch"] or s["scaleFromGutterPitch"]
            rows.append({
                "viewport": [w, h], "id": f"{w}x{h}",
                "orientation": "portrait" if w < h else ("square" if w == h else "landscape"),
                "aspect": round(w / h, 5),
                **s,
                "shippedLawScale": round(pred, 5),
                "measuredScale": meas,
                "measuredOverPredicted": round(meas / pred, 4) if meas else None,
                "impliedGain": round(meas * 1440 / w, 4) if meas else None,
            })
    rows.sort(key=lambda r: r["aspect"])
    payload = {
        "question": "Does the Target switch composition scale at width == height?",
        "shippedLaw": "landscape S = w/1440 ; portrait S = 1.8975 * w/1440",
        "method": "scale from row-band pitch (full-width statistic), gutter pitch as a "
                  "second independent estimate",
        "samples": rows,
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(payload, indent=2))
    print(f"{'viewport':>10} {'aspect':>7} {'orient':>9} {'measS':>8} {'lawS':>8} {'meas/law':>9} {'gain':>7}")
    for r in rows:
        print(f"{r['id']:>10} {r['aspect']:7.3f} {r['orientation']:>9} "
              f"{(r['measuredScale'] or float('nan')):8.4f} {r['shippedLawScale']:8.4f} "
              f"{(r['measuredOverPredicted'] or float('nan')):9.3f} {(r['impliedGain'] or float('nan')):7.3f}")
