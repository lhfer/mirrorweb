#!/usr/bin/env python3
"""§十三A -- re-run the ORIGINAL O5 gate, unchanged, as a regression.

`o5-gate.py` is not edited, not copied and not parameterised. It is imported
and executed exactly as it sits on disk; only the two module-level paths it
reads and writes are redirected, so the sealed evidence tree cannot be
overwritten. §一.12 forbids rewriting the sealed O5 result, and a "regression"
that mutated the thing it was checking would be worthless anyway.

What it is run ON, and why that is the right question.

The sealed gate scored `opticalBody=target-source` at the O5 head. O5R does not
re-derive that verdict from new pixels; it establishes the regression in two
parts, which together are stronger than a re-capture:

  1. the sealed gate, unchanged, still produces its verdict from the frames it
     scored -- run here, byte for byte the same script
  2. the lane at the O5R head still renders those frames -- established
     separately in sealed-lane-identity.json, 22 of 22 Beauty captures
     BYTE-IDENTICAL on the deterministic shared media

A re-capture-and-re-score would prove (1) and (2) together but less sharply:
"the verdict came out the same" tolerates two errors cancelling, where "zero
differing pixels" does not.

Output: qa-v5/optics-o5r/original-o5-gate-regression.json
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HERE = REPO / "scripts/v5"
SEALED = REPO / "qa-v5/optics-o5/body-absolute-gate.json"
IDENTITY = REPO / "qa-v5/optics-o5r/sealed-lane-identity.json"
OUT = REPO / "qa-v5/optics-o5r/original-o5-gate-regression.json"


def original_repo_artifacts() -> Path:
    return REPO / "artifacts"


def main() -> int:
    sealed = json.loads(SEALED.read_text())
    stage = Path(tempfile.mkdtemp(prefix="o5r-orig-gate-"))
    (stage / "qa-v5/optics-o5").mkdir(parents=True)
    # The gate reads two things through REPO -- the captures and the recorded
    # pop analysis -- and writes one. Symlinking artifacts/ means the redirect
    # changes only where it WRITES; without this, item 12's pop.json read
    # silently follows the redirect too and the item reports "recordings not
    # present" rather than its verdict. That is exactly the kind of quiet
    # difference a regression exists to catch, and it caught it here.
    (stage / "artifacts").symlink_to(original_repo_artifacts())

    spec = importlib.util.spec_from_file_location("o5_gate_rerun",
                                                  HERE / "o5-gate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["o5_gate_rerun"] = mod
    spec.loader.exec_module(mod)
    # Redirect the OUTPUT only. MD -- the captures the gate reads -- is left
    # exactly as the script defines it, so this run consumes the same frames
    # the sealed verdict was taken from.
    original_repo = mod.REPO
    mod.REPO = stage
    try:
        rc = mod.main()
    finally:
        mod.REPO = original_repo

    fresh = json.loads((stage / "qa-v5/optics-o5/body-absolute-gate.json")
                       .read_text())
    identity = json.loads(IDENTITY.read_text()) if IDENTITY.exists() else None

    def key(doc):
        return {
            "passed": doc["passed"], "failed": doc["failed"],
            "pending": doc["pending"], "total": doc["total"],
            "absoluteGate": doc["absoluteGate"], "finalState": doc["finalState"],
            "items": {i["item"]: i["pass"] for i in doc["items"]},
        }

    a, b = key(sealed), key(fresh)
    same = a == b
    rows = [{"item": n, "sealed": a["items"][n], "rerun": b["items"].get(n),
             "same": a["items"][n] == b["items"].get(n)}
            for n in sorted(a["items"])]

    doc = {
        "what": "§十三A -- the ORIGINAL O5 gate, re-run unchanged for history "
                "and regression only. Its verdict is not restated as an O5R "
                "result and it is not used to judge the O5R candidate.",
        "script": "scripts/v5/o5-gate.py, imported and executed as it sits on "
                  "disk. Not edited, not copied, not parameterised; only its "
                  "output path was redirected so the sealed evidence tree "
                  "cannot be overwritten.",
        "rerunExitCode": rc,
        "sealedVerdict": {k: v for k, v in a.items() if k != "items"},
        "rerunVerdict": {k: v for k, v in b.items() if k != "items"},
        "identical": same,
        "perItem": rows,
        "laneStillRendersThoseFrames": {
            "source": "qa-v5/optics-o5r/sealed-lane-identity.json",
            "comparisons": (identity or {}).get("comparisons"),
            "exactZero": (identity or {}).get("exactZero"),
            "totalDifferingPixels": (identity or {}).get("totalDifferingPixels"),
            "why": "the two halves together are the regression: the same gate "
                   "yields the same verdict, and the lane at the O5R head "
                   "renders the same pixels the gate scored.",
        },
        "pass": bool(same and (identity or {}).get("exactZero")),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    shutil.rmtree(stage, ignore_errors=True)
    print(f"\nsealed {a['passed']}/{a['total']} {a['absoluteGate']} | "
          f"re-run {b['passed']}/{b['total']} {b['absoluteGate']} | "
          f"identical={same}")
    print(f"lane byte-identity: {(identity or {}).get('comparisons')} "
          f"comparisons, exactZero={(identity or {}).get('exactZero')}")
    print(f"-> {OUT}")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
