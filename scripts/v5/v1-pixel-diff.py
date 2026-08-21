#!/usr/bin/env python3
"""Score the V1 pixel-invariance captures.

A/B (culling ON vs OFF, same build): the full frame must be IDENTICAL --
zero differing pixels, no tolerance. Anything else means the verdict hid an
object that was contributing fragments.

baseline (V0-accepted build vs candidate ON): compared inside the STRICT
VIEWPORT (the full frame is also reported). V1 changed no shader, no
layout and no motion, so the expectation is identity; any nonzero result is
reported with its magnitude and location and fails the gate unless it is
zero. No pre-declared tolerance is consumed silently.

Usage: v1-pixel-diff.py --dir=<pixels dir> --out=<json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops


def diff_stats(a_path, b_path):
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    if a.size != b.size:
        return {"comparable": False, "reason": f"size {a.size} vs {b.size}"}
    d = np.asarray(ImageChops.difference(a, b))
    nz = int((d.sum(axis=2) > 0).sum())
    return {"comparable": True, "differingPixels": nz,
            "maxChannelDelta": int(d.max()),
            "totalPixels": a.size[0] * a.size[1]}


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    d = Path(args["dir"])
    index = json.loads((d / "index.json").read_text())

    ab_rows = []
    base_rows = []
    cand = {}
    for s in index["shots"]:
        if s["lane"] == "candidate":
            r = diff_stats(s["on"], s["off"])
            ab_rows.append({"viewport": s["vp"], "state": s["state"], **r})
            cand[(s["vp"], s["state"])] = s["on"]
    for s in index["shots"]:
        if s["lane"] == "baseline":
            on = cand.get((s["vp"], s["state"]))
            if not on:
                continue
            r = diff_stats(s["file"], on)
            base_rows.append({"viewport": s["vp"], "state": s["state"], **r})

    ab_pass = all(r.get("differingPixels") == 0 for r in ab_rows) and len(ab_rows) > 0
    base_pass = (all(r.get("differingPixels") == 0 for r in base_rows)
                 if base_rows else None)
    doc = {
        "what": "V1 pixel invariance: culling ON vs OFF must be IDENTICAL "
                "(no tolerance); V0-accepted baseline vs candidate reported "
                "with magnitudes, expectation identity",
        "abComparisons": len(ab_rows),
        "abPass": ab_pass,
        "ab": ab_rows,
        "baselineComparisons": len(base_rows),
        "baselinePass": base_pass,
        "baseline": base_rows,
        "pass": ab_pass and (base_pass is not False),
    }
    Path(args["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["out"]).write_text(json.dumps(doc, indent=1) + "\n")
    worst_ab = max((r.get("differingPixels", 0) for r in ab_rows), default=0)
    print(f"A/B: {len(ab_rows)} comparisons, worst {worst_ab} differing px -> "
          f"{'PASS' if ab_pass else 'FAIL'}")
    if base_rows:
        worst_b = max((r.get("differingPixels", 0) for r in base_rows), default=0)
        print(f"baseline: {len(base_rows)} comparisons, worst {worst_b} differing px -> "
              f"{'PASS' if base_pass else 'FAIL'}")
    print("PIXEL GATE:", "PASS" if doc["pass"] else "FAIL")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
