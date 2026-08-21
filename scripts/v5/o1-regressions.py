#!/usr/bin/env python3
"""Summarise the frozen-regression re-runs at the O1 build.

Reads artifacts/optics/o1-regressions (written by run-o1.sh rendergate /
labelgate / frozen) and writes ONE public JSON. All suites must PASS --
O1 touched only the glass material, and this file is the proof.

Usage: o1-regressions.py --art=<dir> --out=<json>
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
    art = Path(args["art"])

    truth = json.loads((art / "render/render-culling-truth.json").read_text())
    render = {
        "framesChecked": truth["framesChecked"],
        "slotMismatches": truth["slotMismatches"],
        "labelMeshDisagreements": truth["labelMeshDisagreements"],
        "strictViewportMissing": truth["strictViewportMissing"],
        "mediaPassLeaks": truth["mediaPassLeaks"],
        "shellGlassMismatches": truth["shellGlassMismatches"],
        "settledSnapshots": f"{truth['settledSnapshots']['snapshots']} "
                            f"({'all PASS' if truth['settledSnapshots']['pass'] else 'FAIL'})",
        "errors": truth["consoleAndPageErrors"],
        "pass": truth["pass"],
    }

    lg = art / "labelgate"
    cov = json.loads((lg / "coverage-truth.json").read_text())
    sv = json.loads((lg / "slot-verdicts.json").read_text())
    pop = json.loads((lg / "edge-pop-in.json").read_text())
    w = json.loads((lg / "transform-writes.json").read_text())
    crc = cov["candidateRuleConsistency"]
    label = {
        "framesChecked": crc["framesChecked"],
        "slotMismatches": crc["slotMismatches"],
        "beyondBoundary": crc["beyondBoundary"],
        "identity": f"{sv['identical']}/{sv['comparisons']}",
        "snapshotBitExact": cov["candidateSnapshotBitExactness"]["pass"],
        "staleRects": cov["staleRectCheck"]["pass"],
        "edgePopIn": pop["pass"],
        "writes": w["pass"],
        "errors": cov["consoleAndPageErrors"],
        "pass": (crc["beyondBoundary"] == 0 and crc["slotMismatches"] == 0
                 and sv["pass"] and cov["candidateSnapshotBitExactness"]["pass"]
                 and cov["staleRectCheck"]["pass"] and pop["pass"] and w["pass"]),
    }

    contract = json.loads((art / "source-contract.json").read_text())
    typo = json.loads((art / "typography-regression.json").read_text())
    mot = json.loads((art / "motion-regression.json").read_text())
    clm = mot.get("cardLabelMotion", {})

    tsc_log = (art / "logs/tsc.log").read_text() if (art / "logs/tsc.log").exists() else "MISSING"
    build_log = (art / "logs/build.log").read_text() if (art / "logs/build.log").exists() else "MISSING"
    tsc_ok = tsc_log != "MISSING" and "error TS" not in tsc_log
    build_ok = "built in" in build_log

    doc = {
        "what": "every frozen suite re-run at the O1 candidate build. O1 "
                "touched only the glass material's dispersion law; this file "
                "proves nothing else moved.",
        "renderCullingGate": render,
        "labelCullingGate": label,
        "sourceContract": {"verdict": contract.get("verdict"),
                           "passed": contract.get("passed"),
                           "viewports": contract.get("viewports"),
                           "pass": contract.get("verdict") == "PASS"},
        "typography": {"verdict": typo.get("verdict"),
                       "passed": typo.get("passed"),
                       "pass": typo.get("verdict") == "PASS"},
        "motionFreeze": {"pass": mot["pass"],
                         "engineVsContract": mot["engineVsContract"],
                         "releaseHistory": mot["releaseHistory"]},
        "cardLabelMotion": {"assertions": clm.get("assertions"),
                            "failed": clm.get("failed"),
                            "pass": clm.get("assertions", 0) > 0
                                    and clm.get("failed", 1) == 0},
        "typescript": {"pass": tsc_ok},
        "build": {"pass": build_ok},
    }
    doc["pass"] = all(v["pass"] for k, v in doc.items()
                      if isinstance(v, dict) and "pass" in v)
    Path(args["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["out"]).write_text(json.dumps(doc, indent=1) + "\n")
    for k, v in doc.items():
        if isinstance(v, dict) and "pass" in v:
            print(f"{k}: {'PASS' if v['pass'] else 'FAIL'}")
    print("O1 REGRESSIONS:", "PASS" if doc["pass"] else "FAIL")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
