#!/usr/bin/env python3
"""Proof that V0 did not touch the frozen motion -- a smoke, not a re-study.

Reads the outputs of m3-motion-gate.py and m3-release-history.py run on a
FRESH candidate trace captured at the V0 build, and extracts exactly the
freeze-regression fields:

  - engine vs contract: the V0 engine must still integrate the frozen
    contract exactly (rowsFailed == 0, every row exact to floating point);
  - release history: every recorded release EXACT against the engine's own
    record, zero mismatches;
  - wrap teleports our side = 0, wheel responses our side = 0 (no default
    prevented, no scroll travel), touch runs came to rest, console and page
    errors our side = 0.

What it deliberately does NOT read: the landmark verdict against the Target.
That comparison is the ACCEPTED M3 state -- frozen, evidenced in
qa-v5/motion-final/, and not reopened by a culling round.

The card/label-under-motion result (the brief's corner-delta <= 1 px gate)
is folded in here as `cardLabelMotion` rather than shipped as its own public
file: the brief enumerates the public tree exactly, and this is the motion
file. The raw m1 report stays under artifacts/.

Usage: v0-motion-regression.py --gate=<dir> --release=<json> --clm=<json>
                               --out=<json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    gate_dir = Path(args["gate"])
    evc = json.loads((gate_dir / "engine-vs-contract-v3.json").read_text())
    cont = json.loads((gate_dir / "continuity-and-input.json").read_text())
    rel = json.loads(Path(args["release"]).read_text())
    clm = json.loads(Path(args["clm"]).read_text())
    clm_rows = clm.get("assertions", [])
    clm_failed = [r for r in clm_rows if not r.get("pass")]

    wheel_ours = [r for r in cont["wheel"] if r["side"] == "ours"]
    wheel_bad = [r for r in wheel_ours
                 if r["status"] != "PASS" or r["anyDefaultPrevented"]
                 or abs(r.get("scrollTravel") or 0) > 1e-9]
    touch_ours = [r for r in cont["touch"] if r["side"] == "ours"]
    touch_bad = [r for r in touch_ours if not r["cameToRestByEndOfRun"]]
    errors_ours = cont["consoleAndPageErrors"]["ours"]

    doc = {
        "what": "V0 motion freeze regression: the SAME engine gates the motion "
                "round sealed, re-run on a fresh capture at the V0 build. The "
                "landmark verdict against the Target is the accepted M3 state "
                "and is deliberately not re-read here.",
        "engineVsContract": {
            "rowsTotal": evc["rowsTotal"],
            "rowsFailed": evc["rowsFailed"],
            "rowsExactToFloatingPoint": evc["rowsExactToFloatingPoint"],
            "worstRecoveryError": evc["worstRecoveryError"],
            "threshold": evc["threshold"],
        },
        "releaseHistory": {
            "releases": rel["releases"],
            "exact": rel["exact"],
            "mismatched": rel["mismatched"],
            "worstVelocityError": rel["worstVelocityError"],
            "gesturesWithNoRecordedRelease": rel["gesturesWithNoRecordedRelease"],
        },
        "cardLabelMotion": {
            "assertions": len(clm_rows),
            "failed": len(clm_failed),
            "thresholdPx": clm.get("thresholdPx"),
            "gate": clm.get("gate"),
            "rawReport": "artifacts/culling/card-label-motion.json (not a "
                         "public file; the brief enumerates the public tree)",
        },
        "continuity": {
            "wrapTeleportsOurSide": cont["visibleWrapTeleportsOurSide"],
            "wheelRunsOurSide": len(wheel_ours),
            "wheelResponsesOurSide": len(wheel_bad),
            "touchRunsOurSide": len(touch_ours),
            "touchRunsNotAtRest": len(touch_bad),
            "consoleAndPageErrorsOurSide": errors_ours,
        },
        "pass": (evc["rowsFailed"] == 0
                 and len(clm_rows) > 0 and len(clm_failed) == 0
                 and evc["rowsExactToFloatingPoint"] == evc["rowsTotal"]
                 and rel["mismatched"] == 0
                 and cont["visibleWrapTeleportsOurSide"] == 0
                 and len(wheel_bad) == 0 and len(touch_bad) == 0
                 and errors_ours == 0),
    }
    Path(args["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["out"]).write_text(json.dumps(doc, indent=1) + "\n")
    print(f"engine vs contract: {evc['rowsTotal']} rows, {evc['rowsFailed']} failed, "
          f"{evc['rowsExactToFloatingPoint']} exact to floating point")
    print(f"release history: {rel['exact']}/{rel['releases']} exact, "
          f"{rel['mismatched']} mismatched")
    print(f"card/label motion: {len(clm_rows)} assertions, {len(clm_failed)} failed")
    print(f"wrap teleports {cont['visibleWrapTeleportsOurSide']}, wheel responses "
          f"{len(wheel_bad)}, touch not-at-rest {len(touch_bad)}, errors {errors_ours}")
    print("MOTION FREEZE REGRESSION:", "PASS" if doc["pass"] else "FAIL")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
