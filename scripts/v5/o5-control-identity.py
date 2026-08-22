#!/usr/bin/env python3
"""O5 §六 -- score the control-identity captures.

Exact zero differing pixels, or the round stops. Also compares the state probes
the brief names explicitly: render layers, draw calls, media state, shell
state, bodyFloorMode, reflectionSupport, dispersionLaw.

Output: qa-v5/optics-o5/control-identity.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent

# Fields that did not exist at the baseline commit. Absent there by
# construction, so they are checked against an expected value instead of
# against the baseline's null.
NEW_IN_O5 = {"opticalBody"}

PROBE_KEYS = [
    "opticalBody", "bodyFloorMode", "reflectionSupport", "dispersionLaw",
    "shellMode", "envMixScale", "rimScale", "glassMeshesVisible",
    "reflectionShellsVisible", "mediaMeshesVisible", "activeSlots",
    "drawCallsFinal", "drawCallsSceneColor",
]


def diff(a_path: Path, b_path: Path):
    a = np.asarray(Image.open(a_path).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(b_path).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        return {"shapeMismatch": [list(a.shape), list(b.shape)],
                "differingPixels": None, "maxDelta": None}
    d = np.abs(a - b).max(axis=2)
    return {"differingPixels": int((d > 0).sum()),
            "maxDelta": int(d.max()),
            "totalPixels": int(d.size)}


def main() -> int:
    src = REPO / "artifacts/optics-o5/control-identity"
    out = REPO / "qa-v5/optics-o5/control-identity.json"
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k == "src":
            src = Path(v)
        elif k == "out":
            out = Path(v)

    man = json.loads((src / "identity-manifest.json").read_text())
    rows, all_zero, probe_ok = [], True, True
    total_errors = 0

    for rec in man["records"]:
        vp = rec["vp"]
        total_errors += rec["local"]["errorCount"] + rec["base"]["errorCount"]
        by_state = {c["state"]: c for c in rec["base"]["captures"]}
        for cap in rec["local"]["captures"]:
            st = cap["state"]
            base = by_state.get(st)
            if base is None:
                rows.append({"vp": vp, "state": st, "FAILED": "no baseline"})
                all_zero = False
                continue
            d = diff(src / cap["file"], src / base["file"])
            # The probes the brief names, compared field by field. A pixel
            # match with a different draw-call count would mean the two builds
            # agree by accident, not by construction.
            # `opticalBody` did not exist at 5a87751, so the baseline
            # reports null for it. That is the field being NEW, not the two
            # builds disagreeing, and scoring it as a mismatch would make the
            # gate unpassable by construction. It is checked separately below
            # against the value the local build must have.
            mismatched = {k: [cap["probe"].get(k), base["probe"].get(k)]
                          for k in PROBE_KEYS
                          if k not in NEW_IN_O5
                          and cap["probe"].get(k) != base["probe"].get(k)}
            if cap["probe"].get("opticalBody") != "current":
                mismatched["opticalBody"] = [cap["probe"].get("opticalBody"),
                                             "expected 'current'"]
            if mismatched:
                probe_ok = False
            if d["differingPixels"] != 0:
                all_zero = False
            rows.append({"vp": vp, "state": st,
                         "localFile": cap["file"], "baseFile": base["file"],
                         **d, "probeMismatches": mismatched,
                         "identical": d["differingPixels"] == 0 and not mismatched})

    verdict = "PASS" if (all_zero and probe_ok and total_errors == 0) else "FAIL"
    doc = {
        "what": "O5 §六 control identity: opticalBody=current at the O5 code "
                "commit against a 5a87751 build.",
        "baselineCommit": "5a87751d348ebc626e8193d76af33957a1bdf664",
        "local": man["local"], "base": man["base"],
        "asset": man["asset"], "freeze": man["freeze"],
        "statesAreFixedNotReplayed": man["statesAreFixedNotReplayed"],
        "viewports": man["viewports"],
        "states": [s["state"] for s in man["states"]],
        "comparisons": len(rows),
        "allExactZero": all_zero,
        "allProbesMatch": probe_ok,
        "consoleAndPageErrors": total_errors,
        "verdict": verdict,
        "finalStateIfFailed": "O5 CONTROL IDENTITY FAILED",
        "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    worst = max((r.get("differingPixels") or 0) for r in rows)
    print(f"{len(rows)} comparisons, worst differing pixels = {worst}, "
          f"probes match = {probe_ok}, errors = {total_errors}")
    print(f"verdict: {verdict}")
    for r in rows:
        if r.get("differingPixels") or r.get("probeMismatches"):
            print(f"  {r['vp']:10} {r['state']:16} diff={r.get('differingPixels')} "
                  f"probes={r.get('probeMismatches')}")
    print(f"-> {out}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
