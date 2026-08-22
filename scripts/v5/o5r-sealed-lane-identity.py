#!/usr/bin/env python3
"""Is the SEALED O5 lane still the sealed O5 lane?

O5R adds a third `opticalBody` value and three QA programs to the material
factory. §十三A requires the ORIGINAL O5 gate to be re-runnable as a
regression, and that only means anything if `opticalBody=target-source` still
renders what O5 scored. This compares its Beauty captures at the O5R head
against the frames O5 was scored on, on the same deterministic media at the
same viewports.

The guarantee it checks is structural rather than statistical: the un-refracted
UV and the base-ior displacement are computed only when a build-time flag asks
for them, so the clamped lane's program contains nothing that the O5 program
did not. This is the check that the guarantee holds.

Output: qa-v5/optics-o5r/sealed-lane-identity.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
O5 = REPO / "artifacts/optics-o5/measure"
O5R = REPO / "artifacts/optics-o5r/measure"
OUT = REPO / "qa-v5/optics-o5r/sealed-lane-identity.json"


def diff(a_path: Path, b_path: Path):
    a = np.asarray(Image.open(a_path).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(b_path).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        return {"shapeMismatch": [list(a.shape), list(b.shape)],
                "differingPixels": None, "maxDelta": None}
    d = np.abs(a - b).max(axis=2)
    return {"differingPixels": int((d > 0).sum()), "maxDelta": int(d.max()),
            "totalPixels": int(d.size)}


def main() -> int:
    o5 = json.loads((O5 / "measure-manifest.json").read_text())
    o5r = json.loads((O5R / "measure-manifest.json").read_text())

    def index(man, **kw):
        return {(r["asset"], r["vp"]): r for r in man["records"]
                if all(r.get(k) == v for k, v in kw.items())}

    old = index(o5, kind="lane", lane="candidate", state="rest")
    new = index(o5r, kind="lane", lane="o5-clamped", state="rest")
    rows = []
    for key in sorted(set(old) & set(new)):
        a, b = O5 / old[key]["file"], O5R / new[key]["file"]
        if not (a.exists() and b.exists()):
            continue
        rows.append({"asset": key[0], "vp": key[1],
                     "o5File": old[key]["file"], "o5rFile": new[key]["file"],
                     **diff(a, b)})
    exact = bool(rows) and all(r.get("differingPixels") == 0 for r in rows)
    doc = {
        "what": "The SEALED O5 candidate lane (opticalBody=target-source) at "
                "the O5R head, against the frames the O5 gate was scored on.",
        "why": "§十三A re-runs the original O5 gate as a regression. That is "
               "only a regression if the lane still renders what it rendered.",
        "structuralGuarantee":
            "TargetOpticalBodyV5's bodyChain takes a BUILD-TIME wantUv flag. "
            "The un-refracted UV and the base-ior displacement are constructed "
            "only for the three O5R measurement views, so the Beauty program "
            "of the clamped lane contains no expression the O5 program did not "
            "-- the identity does not depend on dead-code elimination.",
        "comparisons": len(rows),
        "exactZero": exact,
        "totalDifferingPixels": sum(r.get("differingPixels") or 0 for r in rows),
        "maxDeltaAnywhere": max((r.get("maxDelta") or 0) for r in rows)
        if rows else None,
        "pass": exact,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    bad = [r for r in rows if r.get("differingPixels") != 0]
    for r in bad[:8]:
        print(f"  DIFFERS {r['asset']} {r['vp']}: {r['differingPixels']} px, "
              f"max delta {r['maxDelta']}")
    print(f"{len(rows) - len(bad)}/{len(rows)} byte-identical -> {OUT}")
    return 0 if exact else 1


if __name__ == "__main__":
    sys.exit(main())
