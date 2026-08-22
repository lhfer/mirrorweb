#!/usr/bin/env python3
"""O5F -- re-run the ORIGINAL O5 gate, unchanged, as a regression.

Identical in structure to the O5R §十三A re-run: `o5-gate.py` is imported and
executed exactly as it sits on disk, reading the frames the sealed verdict
was taken from; only where it WRITES is redirected, so the sealed evidence
tree cannot be overwritten. The lane half of the regression -- that
`opticalBody=target-source` at the O5F head still renders those frames -- is
established in qa-v5/optics-o5f/sealed-lane-identity.json, which compares
the clamped lane's fresh captures against the O5R measure tree (itself
proven byte-identical to the O5 frames in the sealed O5R round, 22/22).

Output: qa-v5/optics-o5f/original-o5-gate-regression.json
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
IDENTITY = REPO / "qa-v5/optics-o5f/sealed-lane-identity.json"
OUT = REPO / "qa-v5/optics-o5f/original-o5-gate-regression.json"


def main() -> int:
    sealed = json.loads(SEALED.read_text())
    stage = Path(tempfile.mkdtemp(prefix="o5f-orig-gate-"))
    (stage / "qa-v5/optics-o5").mkdir(parents=True)
    # The gate reads captures and the recorded pop analysis through REPO and
    # writes one file. Symlinking artifacts/ means the redirect changes only
    # where it WRITES -- the same arrangement the O5R re-run used, for the
    # same reason: without it, item 12's pop.json read silently follows the
    # redirect and the item reports "recordings not present".
    (stage / "artifacts").symlink_to(REPO / "artifacts")

    spec = importlib.util.spec_from_file_location("o5_gate_rerun_f",
                                                  HERE / "o5-gate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["o5_gate_rerun_f"] = mod
    spec.loader.exec_module(mod)
    original_repo = mod.REPO
    mod.REPO = stage
    try:
        rc = mod.main()
    finally:
        mod.REPO = original_repo

    fresh = json.loads((stage / "qa-v5/optics-o5/body-absolute-gate.json")
                       .read_text())
    identity = json.loads(IDENTITY.read_text()) if IDENTITY.exists() else None
    clamped = ((identity or {}).get("byLane") or {}).get("o5-clamped")

    def key(doc):
        return {
            "passed": doc["passed"], "failed": doc["failed"],
            "pending": doc["pending"], "total": doc["total"],
            "absoluteGate": doc["absoluteGate"],
            "finalState": doc["finalState"],
            "items": {i["item"]: i["pass"] for i in doc["items"]},
        }

    a, b = key(sealed), key(fresh)
    same = a == b
    rows = [{"item": n, "sealed": a["items"][n], "rerun": b["items"].get(n),
             "same": a["items"][n] == b["items"].get(n)}
            for n in sorted(a["items"])]

    lane_ok = bool(clamped) and clamped.get("differing") == 0
    doc = {
        "what": "the ORIGINAL O5 gate, re-run unchanged at the O5F head for "
                "history and regression only. Its verdict is not restated as "
                "an O5F result.",
        "script": "scripts/v5/o5-gate.py, imported and executed as it sits "
                  "on disk. Not edited, not copied, not parameterised; only "
                  "its output path was redirected.",
        "rerunExitCode": rc,
        "sealedVerdict": {k: v for k, v in a.items() if k != "items"},
        "rerunVerdict": {k: v for k, v in b.items() if k != "items"},
        "identical": same,
        "perItem": rows,
        "laneStillRendersThoseFrames": {
            "source": "qa-v5/optics-o5f/sealed-lane-identity.json "
                      "(o5-clamped rows)",
            "clampedLane": clamped,
            "chain": "O5F captures == O5R captures (this round, exact zero) "
                     "and O5R captures == O5 frames (sealed O5R round, "
                     "22/22 byte-identical).",
        },
        "pass": bool(same and lane_ok),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    shutil.rmtree(stage, ignore_errors=True)
    print(f"sealed {a['passed']}/{a['total']} {a['absoluteGate']} | re-run "
          f"{b['passed']}/{b['total']} {b['absoluteGate']} | identical={same}")
    print(f"clamped-lane identity: {clamped}")
    print(f"-> {OUT}")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
