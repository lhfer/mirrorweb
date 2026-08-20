#!/usr/bin/env python3
"""
Structure measurement from a multi-frame Target consensus.

A single frame cannot tell a real gutter from a dark patch of video. Several
frames can: a gutter is void in all of them, a dark patch is not. The consensus
mask keeps a pixel only if it reads as void in at least `--consensus` of the
frames (default 80%), and the intersection is reported alongside so the two
agree or the difference is visible.

Usage: f26-consensus-measure.py --dir=<frames dir> --out=<json> [--consensus=0.8]
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("ml", HERE / "measure-layout.py")
ML = importlib.util.module_from_spec(spec); spec.loader.exec_module(ML)


def consensus_mask(files, frac):
    votes = None
    strict = None
    for f in files:
        rgb = np.asarray(Image.open(f).convert("RGB"))
        edge_preset, band_preset = ML.pick_void(rgb)
        m = ML.void_mask(rgb, band_preset)
        votes = m.astype(np.int16) if votes is None else votes + m
        strict = m.copy() if strict is None else (strict & m)
    need = int(np.ceil(frac * len(files)))
    return (votes >= need), strict, votes


if __name__ == "__main__":
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    root = Path(args["--dir"])
    frac = float(args.get("--consensus", 0.8))
    out = Path(args.get("--out", "qa-v5/f26/target-consensus-measurements.json"))
    cap = json.loads((root / "capture.json").read_text())
    results = []
    for s in cap["samples"]:
        files = [root / f for f in s["files"]]
        cons, inter, votes = consensus_mask(files, frac)
        single = ML.measure(files[0])
        multi = ML.measure(files[0], mask_override=cons)
        inter_m = ML.measure(files[0], mask_override=inter)

        def summarise(m):
            H = m["size"]["h"]
            return {
                "rowBands": [round(b["center"], 1) for b in m["horizontalGutterBands"]
                             if b["y0"] > 0 and b["y1"] < H - 1 and b["height"] >= 4],
                "rows": [{"centre": round((r["y0"] + r["y1"]) / 2, 1),
                          "height": r["y1"] - r["y0"] + 1,
                          "clipped": bool(r["clippedTop"] or r["clippedBottom"]),
                          "gutterCentres": [round(g["center"], 1) for g in r["verticalGutters"]],
                          "gutterWidths": [g["width"] for g in r["verticalGutters"]]}
                         for r in m["rows"]],
            }
        a, b, c = summarise(single), summarise(multi), summarise(inter_m)
        removed = int((ML.void_mask(np.asarray(Image.open(files[0]).convert("RGB")),
                                    ML.pick_void(np.asarray(Image.open(files[0]).convert("RGB")))[1]).sum()
                       - cons.sum()))
        results.append({
            "id": s["id"], "viewport": s["viewport"], "frames": len(files),
            "consensusFraction": frac,
            "pixelsRemovedFromSingleFrame": removed,
            "singleFrame": a, "consensus": b, "intersection": c,
            "consensusEqualsIntersection": b == c,
            "gutterCountDelta": [len(r["gutterCentres"]) for r in b["rows"]] !=
                                [len(r["gutterCentres"]) for r in a["rows"]],
        })
        print(f"{s['id']:>10} frames={len(files)} removed={removed:>7} "
              f"bands {len(a['rowBands'])}->{len(b['rowBands'])}  "
              f"gutters/row {[len(r['gutterCentres']) for r in a['rows']]} -> "
              f"{[len(r['gutterCentres']) for r in b['rows']]}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "note": "Consensus keeps a pixel only if it reads as void in at least "
                f"{frac:.0%} of the frames, so a dark video patch cannot become a gutter.",
        "viewports": results}, indent=2))
    print(f"wrote {out}")
