#!/usr/bin/env python3
"""O5F -- the control-identity rows in the schema the sealed aggregator reads.

`o5-regressions.py` (imported unedited by o5f-regressions.py) reads
`control-identity.json` with the O5 schema: a verdict, a comparison count and
per-row pixel diffs for the CURRENT lane. O5F's §六 gate holds those same
rows inside material-cache-identity.json, alongside the candidate lane and
the program probe. This writes the current-lane rows back out in the O5
schema -- a reshape of already-scored data, no new threshold and no new
verdict: the verdict is PASS exactly when the source file's A-section rows
are all identical, which is what its own verdict already required.

Output: qa-v5/optics-o5f/control-identity.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "qa-v5/optics-o5f/material-cache-identity.json"
OUT = REPO / "qa-v5/optics-o5f/control-identity.json"


def main() -> int:
    src = json.loads(SRC.read_text())
    rows = src["rows"]["current"]
    all_zero = all(r.get("differingPixels") == 0 for r in rows)
    probes_ok = all(not r.get("probeMismatches") for r in rows)
    verdict = "PASS" if (all_zero and probes_ok
                         and src["consoleAndPageErrors"] == 0) else "FAIL"
    doc = {
        "what": "O5F control identity: opticalBody=current at the O5F "
                "material-cache commit against a 445037e worktree build. A "
                "schema view of material-cache-identity.json's A-section for "
                "the sealed regression aggregator; the scoring lives there.",
        "derivedFrom": "qa-v5/optics-o5f/material-cache-identity.json",
        "baselineCommit": src["baselineCommit"],
        "local": src["local"], "base": src["base"],
        "asset": src["asset"], "freeze": src["freeze"],
        "viewports": src["viewports"],
        "states": src["states"],
        "comparisons": len(rows),
        "allExactZero": all_zero,
        "allProbesMatch": probes_ok,
        "totalDifferingPixels": sum(r.get("differingPixels") or 0
                                    for r in rows),
        "consoleAndPageErrors": src["consoleAndPageErrors"],
        "verdict": verdict,
        "finalStateIfFailed": "O5F MATERIAL CACHE IDENTITY FAILED",
        "rows": rows,
    }
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"{len(rows)} rows, allExactZero={all_zero}, verdict {verdict}")
    print(f"-> {OUT}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
