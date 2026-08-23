#!/usr/bin/env python3
"""VC2 -- page-chrome truth from matched full-page stills.

The footer band is the one region of the page where Target and Candidate can be
compared without any optical argument at all: with matched media, matched copy
and a proven-identical layout, whatever differs in the bottom strip is page
chrome, not glass and not content.

What it measures, per viewport, on full 1x frames:

  rowLuma      mean luma per screen row across the bottom `band` rows, both
               sides -- the shape of the difference, not just its size
  bandMeans    mean luma of the bottom 144 rows (the Target's own scrim height)
               and of the 144 rows above it, both sides
  scrimRamp    (candidate - target) mean luma at the very bottom rows minus the
               same difference one band higher. A missing gradient scrim shows
               up here as a large positive ramp and nowhere else.
  fullFrame    whole-page mean luma, so a chrome-only claim can be checked
               against the page as a whole

Usage:
  vc2-chrome-truth.py --a=<dir with {vp}-labels-on.png> --b=<dir> [--out=<json>]
                      [--label-a=target] [--label-b=candidate] [--band=288]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
VPS = ["1440x900", "390x844", "844x390", "700x700"]


def luma(p: Path) -> np.ndarray:
    a = np.asarray(Image.open(p).convert("RGB"), dtype=np.float64)
    return 0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]


def row_profile(img: np.ndarray, band: int) -> list[float]:
    return [round(float(v), 3) for v in img[-band:].mean(axis=1)]


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    a_dir, b_dir = (REPO / args["a"]).resolve(), (REPO / args["b"]).resolve()
    band = int(args.get("band", 288))
    la, lb = args.get("label-a", "target"), args.get("label-b", "candidate")
    out_p = REPO / args.get("out", "artifacts/visual-convergence/chrome-truth.json")
    doc = {"what": "page-chrome truth from matched full-page stills",
           "a": {"label": la, "dir": str(a_dir.relative_to(REPO))},
           "b": {"label": lb, "dir": str(b_dir.relative_to(REPO))},
           "bandRows": band, "viewports": {}}
    for vp in VPS:
        pa, pb = a_dir / f"{vp}-labels-on.png", b_dir / f"{vp}-labels-on.png"
        if not (pa.exists() and pb.exists()):
            continue
        ia, ib = luma(pa), luma(pb)
        if ia.shape != ib.shape:
            doc["viewports"][vp] = {"error": f"shape {ia.shape} vs {ib.shape}"}
            continue
        h = ia.shape[0]
        low = slice(h - 144, h)          # the Target's own scrim height
        above = slice(h - 288, h - 144)  # the band immediately above it
        row = {
            "size": [int(ia.shape[1]), int(h)],
            "fullFrameMeanLuma": {la: round(float(ia.mean()), 3), lb: round(float(ib.mean()), 3),
                                  "delta": round(float(ib.mean() - ia.mean()), 3)},
            "bandMeans": {
                "bottom144": {la: round(float(ia[low].mean()), 3),
                              lb: round(float(ib[low].mean()), 3),
                              "delta": round(float(ib[low].mean() - ia[low].mean()), 3)},
                "above144": {la: round(float(ia[above].mean()), 3),
                             lb: round(float(ib[above].mean()), 3),
                             "delta": round(float(ib[above].mean() - ia[above].mean()), 3)},
            },
            "lastRow": {la: round(float(ia[-1].mean()), 3), lb: round(float(ib[-1].mean()), 3),
                        "delta": round(float(ib[-1].mean() - ia[-1].mean()), 3)},
            "rowLuma": {la: row_profile(ia, band), lb: row_profile(ib, band)},
        }
        row["scrimRamp"] = round(row["bandMeans"]["bottom144"]["delta"]
                                 - row["bandMeans"]["above144"]["delta"], 3)
        row["rowLumaDelta"] = [round(x - y, 3) for x, y in
                               zip(row["rowLuma"][lb], row["rowLuma"][la])]
        doc["viewports"][vp] = row
        print(f"{vp}: bottom144 {la}={row['bandMeans']['bottom144'][la]} "
              f"{lb}={row['bandMeans']['bottom144'][lb]} "
              f"delta={row['bandMeans']['bottom144']['delta']} ramp={row['scrimRamp']}")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, indent=1))
    print(f"-> {out_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
