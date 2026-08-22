#!/usr/bin/env python3
"""Do the O5R-scored lanes still render at the O5F head?

The O5F material cache must not move a pixel of ANY lane. §六 proved that for
35 fixed states against a 445037e worktree; this proves it across the whole
measure suite -- every capture the corrected gate scored -- by re-capturing
the three local lanes at the O5F head (o5r-measure.mjs, unedited, pointed at
artifacts/optics-o5f/measure) and comparing every record that exists in both
trees: beauty rest, pointer states, media-only, and the measurement views,
for control, o5-clamped and o5r-unclamped alike.

Together with the gate re-runs this is the O5R §十三A pattern transposed:
the sealed gates re-run unchanged on the frames they scored, and THIS file
establishes that the lanes at the O5F head still render those frames.

Output: qa-v5/optics-o5f/sealed-lane-identity.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
O5R = REPO / "artifacts/optics-o5r/measure"
O5F = REPO / "artifacts/optics-o5f/measure"
OUT = REPO / "qa-v5/optics-o5f/sealed-lane-identity.json"

LANES = ["control", "o5-clamped", "o5r-unclamped"]


def diff(a_path: Path, b_path: Path):
    a = np.asarray(Image.open(a_path).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(b_path).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        return {"shapeMismatch": [list(a.shape), list(b.shape)],
                "differingPixels": None, "maxDelta": None}
    d = np.abs(a - b).max(axis=2)
    return {"differingPixels": int((d > 0).sum()), "maxDelta": int(d.max()),
            "totalPixels": int(d.size)}


def key(r):
    return (r.get("kind"), r.get("lane"), r.get("asset"), r.get("vp"),
            r.get("state"), r.get("view"))


def main() -> int:
    o5r = json.loads((O5R / "measure-manifest.json").read_text())
    o5f = json.loads((O5F / "measure-manifest.json").read_text())
    sealed = {key(r): r for r in o5r["records"]
              if r.get("lane") in LANES and r.get("file")}
    fresh = {key(r): r for r in o5f["records"]
             if r.get("lane") in LANES and r.get("file")}

    rows = []
    missing = []
    total_diff = 0
    max_delta = 0
    for k, s in sorted(sealed.items(), key=str):
        f = fresh.get(k)
        if f is None:
            missing.append({"key": list(k)})
            continue
        if not str(s["file"]).endswith(".png"):
            # body-truth records are JSON matrices, not pixels; byte
            # equality is the right identity for them.
            same = ((O5R / s["file"]).read_bytes()
                    == (O5F / f["file"]).read_bytes())
            rows.append({"kind": k[0], "lane": k[1], "asset": k[2],
                         "vp": k[3], "state": k[4], "view": k[5],
                         "differingPixels": 0 if same else None,
                         "maxDelta": 0 if same else None,
                         "byteIdentical": same, "totalPixels": None})
            if not same:
                missing.append({"key": list(k),
                                "why": "body-truth bytes differ"})
            continue
        d = diff(O5R / s["file"], O5F / f["file"])
        total_diff += d["differingPixels"] or 0
        max_delta = max(max_delta, d["maxDelta"] or 0)
        rows.append({"kind": k[0], "lane": k[1], "asset": k[2], "vp": k[3],
                     "state": k[4], "view": k[5], **d})

    exact = bool(rows) and not missing and all(
        r.get("differingPixels") == 0 for r in rows)
    by_lane = {}
    for r in rows:
        b = by_lane.setdefault(r["lane"], {"comparisons": 0, "differing": 0})
        b["comparisons"] += 1
        b["differing"] += r.get("differingPixels") or 0

    doc = {
        "what": "Every O5R measure capture of the three local lanes, "
                "re-captured at the O5F head with o5r-measure.mjs unedited "
                "and compared against the sealed O5R tree.",
        "why": "the material cache must not move a pixel of any lane; §六 "
               "proved 35 states, this proves the whole scored suite -- and "
               "it is what lets the sealed gates re-run on their own frames "
               "as a true regression.",
        "lanes": LANES,
        "comparisons": len(rows),
        "missingInFresh": missing,
        "exactZero": exact,
        "totalDifferingPixels": total_diff,
        "maxDeltaAnywhere": max_delta,
        "byLane": by_lane,
        "pass": exact,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"{len(rows)} comparisons, missing {len(missing)}, total differing "
          f"pixels {total_diff}, max delta {max_delta}")
    print(f"byLane: {json.dumps(by_lane)}")
    print(f"-> {OUT}  {'PASS' if exact else 'FAIL'}")
    return 0 if exact else 1


if __name__ == "__main__":
    sys.exit(main())
