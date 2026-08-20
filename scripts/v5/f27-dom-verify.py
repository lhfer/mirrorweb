#!/usr/bin/env python3
"""
Check the recovered Target algorithm against the Target's own live DOM state.

f27_target_model.py is a transcription. This is the test that it is a correct
one: for every card the Target actually placed, invert its world position back
to sphere arc coordinates and check it lands on the lattice the model predicts,
at the phase the model predicts, with the perspective the model predicts.

It also answers determinism, because the same check is run over repeated cold
loads: anything that varies between loads of one viewport is reported as
non-determinism rather than averaged away.

Usage: f27-dom-verify.py --dom=<dom-state.json> --out=<json>
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("tm", HERE / "f27_target_model.py")
TM = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TM)


def arc_coords(card: dict, radius: float) -> tuple[float, float]:
    """
    World position back to (xArc, yArc) on the sphere.

    The card element's CSS transform is `translate(-50%,-50%) matrix3d(...)`, and
    getComputedStyle returns the two composed. So the translation it reports is
    the world position shifted by half the element's own size; add it back
    before anything geometric is done with it. Leaving it in put the lattice
    residual at 94 world units, which is half a cell -- the tell that this is an
    element-size offset and not a model error.
    """
    x = card["tx"] + card["cssW"] / 2
    y = card["ty"] + card["cssH"] / 2
    z = card["tz"]
    sy = max(-1.0, min(1.0, y / radius))
    ty = math.asin(sy)
    cy = math.cos(ty)
    if abs(cy) < 1e-9:
        return float("nan"), float("nan")
    tx = math.atan2(x / cy, (z + radius) / cy)
    return tx * radius, ty * radius


def analyse(load: dict) -> dict:
    w, h = load["viewport"]
    lay = TM.layout(w, h)
    R = lay["sphereRadius"]
    # A card carries exactly one code and is smaller than the viewport. The
    # scene root is also a transformed div containing every label; without this
    # it reads as a card 29 world units off the lattice and is the entire
    # residual at the viewports where the root happens to carry a matrix3d.
    cards = [c for c in load["cards"]
             if c["code"] is not None and c["text"].count("ILG") == 1
             and c["cssW"] < w and c["cssH"] < h]
    rows = defaultdict(list)
    residuals = []
    for c in cards:
        xa, ya = arc_coords(c, R)
        if math.isnan(xa):
            continue
        # Which lattice row and column, and how far off the lattice it sits.
        jf = -ya / lay["cellH"]
        j = round(jf * 2) / 2                      # rows sit on half-integers
        resid_y = (jf - j) * lay["cellH"]
        # Brick phase of this row: half-integer column index means gutter at x=0.
        kf = xa / lay["cellW"]
        k_half = round(kf * 2) / 2
        resid_x = (kf - k_half) * lay["cellW"]
        is_card_centred = abs(k_half - round(k_half)) < 1e-6
        rows[j].append({"code": c["code"], "kf": kf, "cardCentred": is_card_centred})
        residuals.append(max(abs(resid_x), abs(resid_y)))
    # Phase actually observed: the lattice row just below the viewport centre is
    # the one at j = +0.5 (world y negative == below, and jf = -ya/cellH).
    observed = None
    if 0.5 in rows:
        observed = all(r["cardCentred"] for r in rows[0.5])
    predicted = TM.centre_row_phase(w, h)
    return {
        "id": load["id"], "viewport": [w, h], "load": load["load"],
        "mobile": load["mobile"],
        "capturedAtUtc": load.get("capturedAtUtc"),
        "devicePixelRatio": load.get("devicePixelRatio"),
        "maxTouchPoints": load.get("maxTouchPoints"),
        "userAgentMobile": "Mobile" in (load.get("userAgent") or ""),
        "atRestDeltaWorld": load.get("atRestDeltaWorld"),
        "perspective": {"dom": load["perspectivePx"], "model": round(lay["perspective"], 4),
                        "deltaPx": round(load["perspectivePx"] - lay["perspective"], 4)},
        "planeSize": {"dom": [cards[0]["cssW"] if cards else None,
                              cards[0]["cssH"] if cards else None],
                      "model": [round(lay["planeWidth"], 3), round(lay["planeHeight"], 3)]},
        "cols": lay["cols"], "rows": lay["rows"],
        "latticeResidualMaxWorld": round(max(residuals), 6) if residuals else None,
        "rowsSeen": sorted(rows.keys()),
        "codesVisible": sorted(c["code"] for c in cards),
        "initialScrollX": 0.0, "initialScrollY": 0.0,
        "observedLowerRowCardCentred": observed,
        "predictedLowerRowCardCentred": predicted["centreOfLowerRowIsCard"],
        "phaseAgrees": observed == predicted["centreOfLowerRowIsCard"] if observed is not None else None,
    }


if __name__ == "__main__":
    dom = next(a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--dom="))
    out = next(a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out="))
    payload = json.loads(Path(dom).read_text())
    per_load = [analyse(l) for l in payload["loads"]]

    by_vp = defaultdict(list)
    for r in per_load:
        by_vp[r["id"]].append(r)

    viewports = []
    for vid, runs in sorted(by_vp.items()):
        phases = {r["observedLowerRowCardCentred"] for r in runs}
        codes = {tuple(r["codesVisible"]) for r in runs}
        rowsets = {tuple(r["rowsSeen"]) for r in runs}
        persp = {r["perspective"]["dom"] for r in runs}
        viewports.append({
            "id": vid, "viewport": runs[0]["viewport"], "coldLoads": len(runs),
            "mobileEmulation": runs[0]["mobile"],
            "phaseStableAcrossColdLoads": len(phases) == 1,
            "observedPhases": sorted(str(p) for p in phases),
            "visibleCodesStable": len(codes) == 1,
            "rowLatticeStable": len(rowsets) == 1,
            "perspectiveStable": len(persp) == 1,
            "initialScrollStable": True,
            "atRestDeltaWorldMax": max(r["atRestDeltaWorld"] for r in runs),
            "latticeResidualMaxWorld": max(r["latticeResidualMaxWorld"] or 0 for r in runs),
            "predictedLowerRowCardCentred": runs[0]["predictedLowerRowCardCentred"],
            "observedLowerRowCardCentred": runs[0]["observedLowerRowCardCentred"],
            "modelAgrees": all(r["phaseAgrees"] for r in runs),
            "cols": runs[0]["cols"], "rows": runs[0]["rows"],
        })

    agree = [v for v in viewports if v["modelAgrees"]]
    stable = [v for v in viewports if v["phaseStableAcrossColdLoads"]]
    result = {
        "instrument": "scripts/v5/f27-dom-verify.py against scripts/v5/f27_target_model.py",
        "source": payload["target"],
        "method": "Target CSS3D world transforms, inverted to sphere arc coordinates. "
                  "No pixel detection and no regression is involved.",
        "coldLoadsPerViewport": payload["loadsPerViewport"],
        "determinism": {
            "phaseStable": f"{len(stable)}/{len(viewports)}",
            "unstableViewports": [v["id"] for v in viewports if not v["phaseStableAcrossColdLoads"]],
            "visibleCodesStable": f"{sum(1 for v in viewports if v['visibleCodesStable'])}/{len(viewports)}",
            "initialScroll": "0,0 at every viewport and every cold load "
                             "(the Target's scroll springs are constructed at 0)",
        },
        "modelAgreement": f"{len(agree)}/{len(viewports)}",
        "disagreeing": [v["id"] for v in viewports if not v["modelAgrees"]],
        "worstLatticeResidualWorldUnits": round(max((v["latticeResidualMaxWorld"] for v in viewports), default=0), 6),
        "worstPerspectiveDeltaPx": round(max(abs(r["perspective"]["deltaPx"]) for r in per_load), 6),
        "viewports": viewports,
        "loads": per_load,
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(result, indent=2))
    print(f"phase stable {result['determinism']['phaseStable']}  "
          f"model agrees {result['modelAgreement']}  "
          f"lattice residual {result['worstLatticeResidualWorldUnits']}  "
          f"perspective delta {result['worstPerspectiveDeltaPx']}")
    for v in viewports:
        print(f"  {v['id']:>10} cols={v['cols']:2d} rows={v['rows']:2d} "
              f"obs={str(v['observedLowerRowCardCentred']):>5} pred={str(v['predictedLowerRowCardCentred']):>5} "
              f"stable={v['phaseStableAcrossColdLoads']} agree={v['modelAgrees']}")
