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
import math
import statistics
import sys
from pathlib import Path


def sign_test_p(n: int, k: int) -> float:
    """Exact two-sided sign test. Same function the gate uses, restated once."""
    lo = min(k, n - k)
    tail = sum(math.comb(n, i) for i in range(lo + 1)) / (2 ** n)
    return min(1.0, 2 * tail)

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

    # A systematic-sign summary is not a cell and cannot be attributed like one.
    #
    # It says: across every cell of this landmark, the candidate's difference
    # from the Target lands on the SAME SIDE far more often than chance. Most
    # of those cells PASS individually -- the sign is lopsided, each cell is
    # inside its threshold -- so resolving the summary from the failing cells
    # alone would leave it unexplained, which is what a first pass did.
    #
    # It is resolved instead by running the SAME sign test on the three terms
    # of the decomposition, over every cell of that landmark. If the frozen
    # contract's own difference from the Target is lopsided in the SAME
    # direction and at least as large, the lopsidedness is the contract's and
    # no implementation of it can be otherwise. That is a measurement on the
    # same cells, not an appeal to the landmark's name.
    for row in rows:
        if not row.get("isSystematicSignSummary"):
            continue
        kin = [c for c in cvt["rows"]
               if c["landmark"] == row["landmark"] and c["grid"] == row["grid"]
               and c["candidateObserved"] is not None
               and c["contractOnCandidateInput"] is not None]
        row["systematicSignCells"] = len(kin)
        if not kin:
            row["why"] = ("no exact cell of this landmark is covered by the "
                          "four-column decomposition, so the summary cannot be "
                          "resolved by measurement.")
            continue

        def lopsided(vals):
            n = sum(1 for v in vals if abs(v) > 1e-12)
            if n < 8:
                return None
            k = sum(1 for v in vals if v > 0)
            return {"cells": n, "higher": k, "p": round(sign_test_p(n, k), 8),
                    "medianAbs": round(statistics.median([abs(v) for v in vals]), 6),
                    "signedMedian": round(statistics.median(vals), 6)}

        total = lopsided([c["candidateObserved"] - c["targetObserved"] for c in kin])
        terms = {
            "SOURCE_CONTRACT_RESIDUAL_EXACT_CELL":
                lopsided([c["inheritedResidual"] for c in kin]),
            "CANDIDATE_IMPLEMENTATION_RESIDUAL":
                lopsided([c["candidateResidual"] for c in kin]),
            "TARGET_INPUT_VARIATION":
                lopsided([c["inputStreamResidual"] for c in kin]),
        }
        row["signTestOnTerms"] = {"total": total, **terms}
        # The SAME rule the individual cells use -- the largest of the three
        # terms -- with "exceeds this cell's threshold" replaced by the only
        # analogue a summary has: the term must itself be lopsided. A summary
        # is a claim about SIGN, so the test that qualifies a term is a sign
        # test.
        #
        # p < 0.05 here, against p < 0.001 in the gate, and the difference is
        # deliberate rather than convenient. The gate's job is to be
        # conservative about declaring a FAIL; this file's job, once a FAIL has
        # been declared, is to say which of three measured terms carries it.
        # Those are different questions and they do not take the same line.
        live = {k: v for k, v in terms.items() if v is not None}
        if not live:
            row["why"] = ("fewer than eight cells carry a difference in any term, so "
                          "no sign test on this landmark is meaningful.")
        else:
            biggest = max(live, key=lambda k: live[k]["medianAbs"])
            v = live[biggest]
            others = ", ".join(
                f"{k.split('_')[0].lower()} {live[k]['medianAbs']:.5g} (p={live[k]['p']:.2g})"
                for k in live if k != biggest)
            if v["p"] < 0.05:
                row["category"] = biggest
                row["why"] = (
                    f"of the three terms measured over the same {v['cells']} cells, the "
                    f"{biggest} one is the largest at {v['medianAbs']:.5g} and is itself "
                    f"lopsided (higher in {v['higher']}, p={v['p']:.2g}). The others: "
                    f"{others}. Total difference {total['medianAbs']:.5g}.")
            else:
                row["why"] = (
                    f"the largest term, {biggest} at {v['medianAbs']:.5g}, is not itself "
                    f"lopsided (p={v['p']:.2g}), so no term carries the summary. "
                    f"Others: {others}.")

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
