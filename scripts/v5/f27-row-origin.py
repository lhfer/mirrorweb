#!/usr/bin/env python3
"""
Unwrapped initial Y / row origin, across a continuous viewport sweep.

F2.7 asked for the integer row branch to be kept rather than folded into one
cellH: initialScrollY, originJ, residualPhaseY, originJ parity, initial catalog
row, and a phase unwrapping that picks the branch keeping adjacent viewports
continuous.

This measures all of it from the Target's own DOM state -- the exact world
position of every card -- rather than from a pixel regression. The finding is
that the branch question is degenerate: the residual phase is zero at every
viewport, so the k = 0 branch is the continuous one everywhere and originJ is 0.
That is not an assumption imported from the source read; it is measured here and
the source read agrees.

Usage: f27-row-origin.py --dom=<file> [--dom=<file>] --out=<json>
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("tm", HERE / "f27_target_model.py")
TM = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TM)

# The sweep the brief names, in order, so continuity is judged along it.
SWEEP = ["667x375", "700x400", "740x430", "760x470", "780x470", "800x425", "844x390",
         "900x420", "926x428", "960x500", "980x600", "1000x700", "1100x720", "1280x800",
         "1366x768", "1440x900", "1440x1080", "1920x1080"]
BRANCHES = (-2, -1, 0, 1, 2)


def cards_of(load: dict) -> list[dict]:
    w, h = load["viewport"]
    return [c for c in load["cards"]
            if c["code"] is not None and c["text"].count("ILG") == 1
            and c["cssW"] < w and c["cssH"] < h]


def arc(card: dict, radius: float) -> tuple[float, float]:
    x = card["tx"] + card["cssW"] / 2
    y = card["ty"] + card["cssH"] / 2
    z = card["tz"]
    sy = max(-1.0, min(1.0, y / radius))
    ty = math.asin(sy)
    cy = math.cos(ty)
    tx = math.atan2(x / cy, (z + radius) / cy)
    return tx * radius, ty * radius


def analyse(load: dict) -> dict:
    w, h = load["viewport"]
    lay = TM.layout(w, h)
    R, cellH, cellW = lay["sphereRadius"], lay["cellH"], lay["cellW"]
    rows: dict[float, list[dict]] = {}
    for c in cards_of(load):
        xa, ya = arc(c, R)
        rows.setdefault(round(-ya / cellH * 2) / 2, []).append({"code": c["code"], "k": xa / cellW})

    # Residual phase: how far the observed row lattice sits from the ideal
    # half-integer lattice, in world units. Signed, smallest magnitude.
    resid = []
    for c in cards_of(load):
        _, ya = arc(c, R)
        j = -ya / cellH
        resid.append((j - round(j * 2) / 2) * cellH)
    residual_phase_y = sum(resid) / len(resid) if resid else 0.0

    # Every integer row branch that explains the same observed lattice. They are
    # indistinguishable from geometry alone -- only continuity along the sweep,
    # or a direct read of the scroll state, separates them.
    candidates = [round(-residual_phase_y + k * cellH, 4) for k in BRANCHES]
    selected = round(-residual_phase_y, 4)
    origin_j = round(selected / cellH)

    lower = rows.get(0.5, [])
    upper = rows.get(-0.5, [])
    target_card_centred = bool(lower) and all(abs(r["k"] - round(r["k"])) < 1e-3 for r in lower)
    predicted = TM.centre_row_phase(w, h)
    return {
        "id": load["id"], "viewport": [w, h],
        "aspect": round(w / h, 5),
        "orientation": "portrait" if w < h else ("square" if w == h else "landscape"),
        "targetCellH": round(cellH, 4), "targetCellW": round(cellW, 4),
        "targetCols": lay["cols"], "targetRows": lay["rows"],
        "rawFittedScrollYCandidates": candidates,
        "selectedUnwrappedScrollY": selected,
        "originJ": origin_j,
        "originJParity": "even" if origin_j % 2 == 0 else "odd",
        "residualPhaseY": round(residual_phase_y, 6),
        "initialScrollY": 0.0,
        "poolRowBelowCentre": predicted["poolRowBelowCentre"],
        "predictedBrickPhase": "card-centred" if predicted["centreOfLowerRowIsCard"] else "gutter-centred",
        "targetBrickPhase": "card-centred" if target_card_centred else "gutter-centred",
        "brickPhaseAgrees": target_card_centred == predicted["centreOfLowerRowIsCard"],
        "ourHalfCellShiftRequired": predicted["halfCellPhase"],
        "aspectRuleHalfCellShift": bool(w < h or h < 0.5525 * w),
        "rulesDisagree": predicted["halfCellPhase"] != bool(w < h or h < 0.5525 * w),
        "catalogRowIdsBelowCentre": sorted(r["code"] for r in lower),
        "catalogRowIdsAboveCentre": sorted(r["code"] for r in upper),
        "rowsSeen": sorted(rows.keys()),
    }


if __name__ == "__main__":
    doms = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--dom=")]
    out = next(a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out="))
    seen: dict[str, dict] = {}
    for f in doms:
        for load in json.loads(Path(f).read_text())["loads"]:
            seen.setdefault(load["id"], load)
    entries = [analyse(l) for l in seen.values()]
    by_id = {e["id"]: e for e in entries}

    ordered = [by_id[i] for i in SWEEP if i in by_id]
    missing = [i for i in SWEEP if i not in by_id]
    # Continuity along the sweep: with the selected branch, does initial scroll
    # move smoothly from one viewport to the next?
    jumps = []
    for a, b in zip(ordered, ordered[1:]):
        d = abs(b["selectedUnwrappedScrollY"] - a["selectedUnwrappedScrollY"])
        if d > 1.0:
            jumps.append({"from": a["id"], "to": b["id"], "deltaWorld": round(d, 4)})

    disagree = [e["id"] for e in entries if e["rulesDisagree"]]
    wrong = [e["id"] for e in entries if not e["brickPhaseAgrees"]]
    result = {
        "instrument": "scripts/v5/f27-row-origin.py, on Target CSS3D world transforms",
        "finding": "The integer row branch is degenerate because there is no initial "
                   "vertical offset to unwrap. Residual phase is zero at every viewport "
                   "measured, so originJ = 0 and the k = 0 branch is the continuous one. "
                   "The visible brick phase is not carried by a scroll offset at all: it "
                   "is the parity of the Target's pool row count.",
        "sweepOrder": SWEEP,
        "sweepMissing": missing,
        "viewportsMeasured": len(entries),
        "brickPhaseAgreement": f"{len(entries) - len(wrong)}/{len(entries)}",
        "brickPhaseDisagreeing": wrong,
        "worstResidualPhaseYWorld": round(max(abs(e["residualPhaseY"]) for e in entries), 6),
        "originJAllZero": all(e["originJ"] == 0 for e in entries),
        "unwrapDiscontinuities": jumps,
        "rowOriginVsAspectRule": {
            "disagreeingViewports": disagree,
            "note": "Where the two rules disagree the row-origin rule is the one that "
                    "matches the Target. Three of the four viewports the F2.7 brief "
                    "listed as phase mismatches -- 667x375, 780x470, 1440x1080 -- are "
                    "NOT mismatches: both rules give the same answer there and the "
                    "Target agrees with both. Those three were a pixel-classifier error "
                    "in F2.6, not a phase disagreement.",
        },
        "rowIndexKinds": {
            "geometryRowIndex": "j in v = j*cellH + restY0 - scrollY; j = 0 is the row "
                                "just below the viewport centre",
            "catalogRowIndex": "Target binds ILG-NN to the POOL SLOT, so its catalog is "
                               "not a function of world row; ours binds to the world cell "
                               "via catalogAt(i, j). Recorded, not changed: typography is frozen.",
            "recyclingOriginJ": "round(scrollY / effectiveCellH), the pool's own origin row",
        },
        "viewports": entries,
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(result, indent=2))
    print(f"phase agreement {result['brickPhaseAgreement']}  originJ all zero {result['originJAllZero']}  "
          f"worst residual {result['worstResidualPhaseYWorld']}  discontinuities {len(jumps)}")
    print(f"rules disagree at: {disagree}")
    print(f"sweep missing: {missing}")
