#!/usr/bin/env python3
"""O5F -- re-run the SEALED O5R corrected gate, unchanged, as a regression.

`o5r-gate.py` is imported and executed exactly as it sits on disk. Its reads
happen at import time from the sealed O5R measure tree -- the frames the
corrected verdict was taken from -- and only its OUTPUT directory is
redirected to a stage, so the sealed evidence cannot be overwritten. §一.10
says the O5R corrected gate result is not to be rewritten; a regression that
mutated it would be worthless anyway.

Two-part regression, the §十三A pattern transposed:

  1. the sealed corrected gate, unchanged, still produces its 7/14 verdict
     from the frames it scored -- run here
  2. the lanes at the O5F head still render those frames -- established
     separately in qa-v5/optics-o5f/sealed-lane-identity.json

Item 14 reads the sealed §十二 performance record out of the gate's own
output directory, so that record is staged in before the run: the re-run must
read the same input the sealed run read. O5F's own memory result lives in
material-cache-stress.json and is NOT spliced into this regression.

Output: qa-v5/optics-o5f/o5r-gate-regression.json
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
SEALED = REPO / "qa-v5/optics-o5r/corrected-product-gate.json"
IDENTITY = REPO / "qa-v5/optics-o5f/sealed-lane-identity.json"
OUT = REPO / "qa-v5/optics-o5f/o5r-gate-regression.json"


def main() -> int:
    sealed = json.loads(SEALED.read_text())
    stage = Path(tempfile.mkdtemp(prefix="o5f-o5r-gate-"))
    stage_out = stage / "qa-v5/optics-o5r"
    stage_out.mkdir(parents=True)
    # Item 14 reads the sealed performance verdict from the gate's own OUT.
    shutil.copy2(REPO / "qa-v5/optics-o5r/pipeline-performance-v2.json",
                 stage_out / "pipeline-performance-v2.json")

    spec = importlib.util.spec_from_file_location("o5r_gate_rerun",
                                                  HERE / "o5r-gate.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["o5r_gate_rerun"] = mod
    # Import executes the module-level reads -- MAN, MEDIA, RECTS -- from the
    # REAL sealed paths. That is the point: the re-run consumes the frames
    # the sealed verdict was taken from.
    spec.loader.exec_module(mod)
    mod.OUT = stage_out
    rc = mod.main()

    fresh = json.loads((stage_out / "corrected-product-gate.json").read_text())
    identity = (json.loads(IDENTITY.read_text())
                if IDENTITY.exists() else None)

    def key(doc):
        return {
            "counts": doc.get("counts"),
            "gate": doc.get("gate"),
            "items": {i["item"]: i["status"] for i in doc["items"]},
        }

    a, b = key(sealed), key(fresh)
    same = a == b
    rows = [{"item": n, "sealed": a["items"][n], "rerun": b["items"].get(n),
             "same": a["items"][n] == b["items"].get(n)}
            for n in sorted(a["items"])]

    doc = {
        "what": "the SEALED O5R corrected gate, re-run unchanged for "
                "regression only. Its verdict is not restated as an O5F "
                "result and O5F's own memory result is not spliced into it.",
        "script": "scripts/v5/o5r-gate.py, imported and executed as it sits "
                  "on disk; only its output directory was redirected.",
        "rerunExitCode": rc,
        "sealedVerdict": {k: v for k, v in a.items() if k != "items"},
        "rerunVerdict": {k: v for k, v in b.items() if k != "items"},
        "identical": same,
        "perItem": rows,
        "lanesStillRenderThoseFrames": {
            "source": "qa-v5/optics-o5f/sealed-lane-identity.json",
            "comparisons": (identity or {}).get("comparisons"),
            "exactZero": (identity or {}).get("exactZero"),
        },
        "stagedInput": "qa-v5/optics-o5r/pipeline-performance-v2.json, "
                       "copied into the staged output directory because item "
                       "14 reads it from there; the re-run reads the same "
                       "record the sealed run read.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    shutil.rmtree(stage, ignore_errors=True)
    print(f"sealed {a['counts']} {a['gate']}  |  rerun {b['counts']} "
          f"{b['gate']}  identical={same}")
    print(f"-> {OUT}")
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
