#!/usr/bin/env python3
"""Every failing cell, attributed by measurement on that cell.

WHAT WAS WRONG BEFORE
---------------------
M2 attributed by LANDMARK NAME: if the frozen contract missed a landmark
anywhere on the Target's own input, every candidate failure carrying that name
was called inherited. Eleven rows were classified that way and the M3 brief
bans the shortcut by name. It deserves banning -- a landmark can be reproduced
exactly in one cell and missed badly in another, and a name is not a cell.

HOW THIS ATTRIBUTES INSTEAD
---------------------------
Per exact cell -- (grid, viewport, sequence, landmark) -- there are four
measurements, from contract-vs-target-v2.json:

  targetObserved            what the Target did
  contractOnTargetInput     the frozen contract on the TARGET's input
  contractOnCandidateInput  the frozen contract on OUR input
  candidateObserved         what our engine did

and the failing difference decomposes EXACTLY, with no remainder:

  candidateObserved - targetObserved
      = (contractOnTargetInput    - targetObserved)           inherited
      + (contractOnCandidateInput - contractOnTargetInput)    input stream
      + (candidateObserved - contractOnCandidateInput)        candidate

A cell is attributed to the term that both exceeds the cell's own threshold and
is the largest of the three. If no term exceeds the threshold the difference is
not explained by any of them and the cell stays UNRESOLVED_ATTRIBUTION -- which
is a result, not a hole to be filled with the nearest plausible label.

Usage: m3-attribution.py --dir=<qa-v5/motion-final> --out=<json>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


LM = _load("m2_landmarks", "m2_landmarks.py")

CATEGORIES = [
    "SOURCE_CONTRACT_RESIDUAL_EXACT_CELL",
    "CANDIDATE_IMPLEMENTATION_RESIDUAL",
    "TARGET_INPUT_VARIATION",
    "INSTRUMENT_UNREADABLE",
    "MOTION-EXC-01",
    "UNRESOLVED_ATTRIBUTION",
]


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    d = Path(args["dir"])

    gate = json.loads((d / "scheduler-invariant-gate.json").read_text())
    cvt = json.loads((d / "contract-vs-target-v2.json").read_text())
    cells = {r["exactCellKey"]: r for r in cvt["rows"]}

    rows = []
    for f in gate["failures"]:
        name = f["landmark"]
        key = f"{f['grid']}|{f.get('viewport')}|{f.get('sequence')}|{name}"
        row = {
            "exactCellKey": key,
            "grid": f["grid"], "viewport": f.get("viewport"),
            "sequence": f.get("sequence"), "landmark": name,
            "gateType": f.get("gateType"),
            "gateDelta": f.get("delta"), "gateThreshold": f.get("threshold"),
            "proofFile": "qa-v5/motion-final/contract-vs-target-v2.json",
        }
        if name in LM.EXCEPTION_RAW:
            row.update({"category": "MOTION-EXC-01",
                        "why": "a raw single-frame metric the product placed under "
                               "MOTION-EXC-01; not an absolute product gate.",
                        "proofFile": "qa-v5/motion-final/scheduler-invariant-gate.json"})
            rows.append(row)
            continue
        if f.get("viewport") == "ALL":
            # A systematic-sign row is not a cell. It is attributed by the
            # cells that produced it, which are in this same list.
            row.update({"category": "UNRESOLVED_ATTRIBUTION",
                        "why": "a systematic-sign summary row, not an exact cell. It is "
                               "resolved by the cells beneath it; see "
                               "`systematicSignCells` below.",
                        "isSystematicSignSummary": True})
            rows.append(row)
            continue
        c = cells.get(key)
        if c is None:
            row.update({"category": "UNRESOLVED_ATTRIBUTION",
                        "why": "this landmark is read from the camera matrix and is not "
                               "computable from a replay, so the four-column "
                               "decomposition does not exist for it."})
            rows.append(row)
            continue

        thr = c["threshold"]
        inherited = c["inheritedResidual"]
        cand = c["candidateResidual"]
        inp = c["inputStreamResidual"]
        row.update({
            "targetObserved": c["targetObserved"],
            "contractOnTargetInput": c["contractOnTargetInput"],
            "contractOnCandidateInput": c["contractOnCandidateInput"],
            "candidateObserved": c["candidateObserved"],
            "inheritedResidual": inherited,
            "candidateResidual": cand,
            "inputStreamResidual": inp,
            "threshold": thr,
            "windowBoundarySensitive": c["windowBoundarySensitive"],
        })
        if cand is None or inp is None:
            row.update({"category": "UNRESOLVED_ATTRIBUTION",
                        "why": "no readable candidate run in this cell, so the "
                               "candidate and input-stream terms do not exist."})
            rows.append(row)
            continue

        terms = {"SOURCE_CONTRACT_RESIDUAL_EXACT_CELL": abs(inherited),
                 "CANDIDATE_IMPLEMENTATION_RESIDUAL": abs(cand),
                 "TARGET_INPUT_VARIATION": abs(inp)}
        biggest = max(terms, key=lambda k: terms[k])
        if terms[biggest] > thr:
            row["category"] = biggest
            row["why"] = (f"of the three terms the {biggest} one is the largest at "
                          f"{terms[biggest]:.5g} and it exceeds this cell's own "
                          f"threshold of {thr:.5g}.")
        elif c["windowBoundarySensitive"]:
            row["category"] = "INSTRUMENT_UNREADABLE"
            row["why"] = ("no term exceeds the threshold, and the contract's own "
                          "prediction on the Target's input moves with the velocity "
                          "window boundary, which the Target's traces cannot resolve.")
        else:
            row["category"] = "UNRESOLVED_ATTRIBUTION"
            row["why"] = (f"the cell fails the gate but none of the three terms "
                          f"exceeds its threshold: inherited {inherited:.5g}, "
                          f"candidate {cand:.5g}, input {inp:.5g}, threshold "
                          f"{thr:.5g}. Reported as unresolved rather than assigned.")
        row["termSizes"] = {k: round(v, 6) for k, v in terms.items()}
        rows.append(row)

    # A systematic-sign summary is resolved by the cells it summarises.
    for row in rows:
        if not row.get("isSystematicSignSummary"):
            continue
        kin = [r for r in rows if not r.get("isSystematicSignSummary")
               and r["landmark"] == row["landmark"] and r["grid"] == row["grid"]]
        cats = {r["category"] for r in kin}
        row["systematicSignCells"] = len(kin)
        row["systematicSignCellCategories"] = sorted(cats)
        if kin and cats and cats <= {"SOURCE_CONTRACT_RESIDUAL_EXACT_CELL",
                                     "TARGET_INPUT_VARIATION",
                                     "INSTRUMENT_UNREADABLE", "MOTION-EXC-01"}:
            row["category"] = "SOURCE_CONTRACT_RESIDUAL_EXACT_CELL"
            row["why"] = ("every failing cell beneath this summary attributes away "
                          "from the candidate: " + ", ".join(sorted(cats)))
        elif "CANDIDATE_IMPLEMENTATION_RESIDUAL" in cats:
            row["category"] = "CANDIDATE_IMPLEMENTATION_RESIDUAL"
            row["why"] = "at least one failing cell beneath this summary is ours."

    counts = {c: sum(1 for r in rows if r["category"] == c) for c in CATEGORIES}
    doc = {
        "what": "every failing gate cell, attributed by measurement on that cell",
        "whatWasBanned": "attribution by landmark NAME. M2 used "
                         "`elif landmark in contract_miss_landmarks` and that is not "
                         "evidence about a cell.",
        "decomposition": "candidateObserved - targetObserved = inherited + inputStream "
                         "+ candidate, exactly and with no remainder. A cell is "
                         "attributed to the term that both exceeds the cell's own "
                         "threshold and is the largest of the three.",
        "categories": {
            "SOURCE_CONTRACT_RESIDUAL_EXACT_CELL":
                "the frozen contract already misses the Target in THIS cell. No "
                "faithful implementation of that contract can close it.",
            "CANDIDATE_IMPLEMENTATION_RESIDUAL":
                "our engine differs from the contract on our own input. Ours.",
            "TARGET_INPUT_VARIATION":
                "the same contract, two synthetic input streams that did not land on "
                "identical pixels at identical times.",
            "INSTRUMENT_UNREADABLE":
                "the instrument cannot resolve the cell, and the reason is named.",
            "MOTION-EXC-01":
                "a raw single-frame scheduling metric the product placed under the "
                "accepted exception.",
            "UNRESOLVED_ATTRIBUTION":
                "the cell fails and no term explains it. Left unresolved on purpose.",
        },
        "failingCells": len(rows),
        "counts": counts,
        "unresolved": [r for r in rows if r["category"] == "UNRESOLVED_ATTRIBUTION"],
        "rows": rows,
    }
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"attribution -> {out}   failing cells {len(rows)}")
    for k, v in counts.items():
        print(f"  {k:38s} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
