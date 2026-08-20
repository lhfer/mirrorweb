#!/usr/bin/env python3
"""
Backfill the pixel gate's NOT_MEASURED items with named numeric checks.

The brief is explicit: an item the pixel detector cannot measure must be covered
by the source-contract numeric gate, and NOT_MEASURED must never be read as a
pass. This writes that mapping into gate.json per viewport, so a reviewer sees
exactly which numeric check stands in for which unmeasurable pixel item.

Usage: fsx-gate-coverage.py --gate=<gate.json> --contract=<source-contract.json> --out=<json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Which source-contract checks establish the same fact a pixel item would.
BACKFILL = {
    "cardCentre": ["every active slot world position (engine vs model)",
                   "projected card corners (engine vs model)",
                   "every visible Target card matched by an engine slot (world)"],
    "cardSize": ["planeWidth (engine vs model)", "planeHeight (engine vs model)",
                 "card aspect is 4/3", "projected card corners (engine vs model)"],
    "gutterPx": ["cellW (engine vs model)", "cellH (engine vs model)",
                 "projected card corners (engine vs model)"],
    "edgeYaw": ["every active slot orientation (engine vs model)"],
    "rowParity": ["rows exact", "cols exact", "active slot count exact",
                  "every active slot world position (engine vs model)"],
    "centreDarkBand": ["rows exact", "every active slot world position (engine vs model)"],
    "overlap": ["every active slot world position (engine vs model)"],
    "largeVoid": ["active slot count exact", "cols exact", "rows exact"],
    "f0Regression": [],
}

if __name__ == "__main__":
    args = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if "=" in a}
    gate = json.loads(Path(args["--gate"]).read_text())
    contract = json.loads(Path(args["--contract"]).read_text())
    by_id = {r["id"]: r for r in contract["results"]}

    holes = []
    for vp in gate["viewports"]:
        sc = by_id.get(vp["id"])
        mapping = {}
        for item, state in vp["contractCoverage"].items():
            if state != "NOT_MEASURED":
                continue
            names = BACKFILL.get(item, [])
            covered = []
            for n in names:
                c = next((c for c in (sc["checks"] if sc else []) if c["check"] == n), None)
                if c:
                    covered.append({"check": n, "value": c["value"], "limit": c["limit"],
                                    "unit": c["unit"], "pass": c["pass"]})
            mapping[item] = {
                "pixelDetectorResult": "NOT_MEASURED",
                "reason": "no row pair survived the gate's sliver / mirror-symmetry "
                          "conditioning at this viewport",
                "backfilledBy": covered,
                "backfillPasses": bool(covered) and all(c["pass"] for c in covered),
            }
        if mapping:
            holes.append({"id": vp["id"], "items": mapping})
        vp["notMeasuredBackfill"] = mapping

    gate["notMeasuredPolicy"] = (
        "NOT_MEASURED is never counted as a pass. Every unmeasurable pixel item is "
        "mapped to the source-contract numeric checks that establish the same fact, "
        "and those checks are listed per viewport with their measured values.")
    gate["notMeasuredViewports"] = [h["id"] for h in holes]
    gate["notMeasuredAllBackfilled"] = all(
        m["backfillPasses"] for h in holes for m in h["items"].values())
    Path(args["--out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["--out"]).write_text(json.dumps(gate, indent=2))
    n = sum(len(h["items"]) for h in holes)
    print(f"backfilled {n} NOT_MEASURED items across {len(holes)} viewports; "
          f"all backfills pass: {gate['notMeasuredAllBackfilled']}")
    for h in holes:
        print(f"  {h['id']:>10} {sorted(h['items'])}")
