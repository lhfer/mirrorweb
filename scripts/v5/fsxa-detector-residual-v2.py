#!/usr/bin/env python3
"""
Detector residual, reported with its pairing honesty attached.

CORRECTION. The first version of this measurement reported a headline of
"max centre 2.67 px, max width 71.89 px". Those were the numbers from a run over
six viewports; once 700x700 and 667x375 were added the true top-level maxima
became 35.02 px and 118.75 px, and the F2-SX delivery reply quoted the old pair.
The large values are mispairings -- a detected region matched to the wrong Target
card -- but "they are outliers" is not something a reader should have to take on
trust, so every bucket is reported here with the rule that produced it.

What this measures: how far a pixel detector reads a TARGET card from where the
TARGET's own DOM says that card is. Both sides come from the Target alone, so it
bounds the instrument, not our layout. It cannot stand in for the source
contract and it cannot declare anything about beauty.

Usage: fsxa-detector-residual-v2.py --dom=<f>... --frames=<dir> --out=<json> [--vps=..]
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(n, f):
    spec = importlib.util.spec_from_file_location(n, HERE / f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


G = _load("f2_gate", "f2-gate.py")
ML = _load("measure_layout", "measure-layout.py")
SC = _load("fsx_source_contract", "fsx-source-contract.py")
SL = _load("source_layout", "source_layout.py")

# Objective, stated before the numbers are looked at.
RULES = {
    "mutualNearest": "the detected region's nearest truth card must also have that "
                     "region as ITS nearest detection",
    "runnerUpMargin": 0.5,
    "runnerUpMarginMeaning": "the nearest truth card must be at least twice as close as "
                             "the next one, so an ambiguous match is never counted as a clean one",
    "widthRatioBand": [0.75, 1.25],
    "widthRatioMeaning": "a detection whose width is more than 25% from the truth width has "
                         "merged two cards or lost most of one; it is not a measurement of "
                         "that card's position",
    "unclippedBothSides": "clipped cards have no true centre to compare",
    "gutterMatchTolerancePx": 30.0,
    "gutterMatchMeaning": "a detected gutter with no true gutter within 30 px is a phantom -- "
                          "void found where a card was clipped or a video frame went dark",
}


def truth_cards(load: dict) -> list[dict]:
    w, h = load["viewport"]
    f = SL.layout(w, h)
    persp, R = f["perspective"], f["sphereRadius"]
    out = []
    for c in SC.dom_cards(load):
        wx, wy, wz = SC.dom_world(c)
        n = (wx / R, wy / R, (wz + R) / R)
        ln = math.sqrt(sum(v * v for v in n)) or 1.0
        n = tuple(v / ln for v in n)
        q = SC.quat_from_unit_vectors((0.0, 0.0, 1.0), n)
        rx, ry = SC.rotate(q, (1.0, 0.0, 0.0)), SC.rotate(q, (0.0, 1.0, 0.0))
        hw, hh = c["cssW"] / 2, c["cssH"] / 2
        pts = []
        for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
            p = [(wx, wy, wz)[k] + rx[k] * sx * hw + ry[k] * sy * hh for k in range(3)]
            pr = SC.project(p, persp, w, h)
            if pr is None:
                pts = []
                break
            pts.append(pr)
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        out.append({"code": c["code"], "cx": sum(xs) / 4, "cy": sum(ys) / 4,
                    "x0": min(xs), "x1": max(xs), "w": max(xs) - min(xs),
                    "onScreen": max(xs) > 0 and min(xs) < w and max(ys) > 0 and min(ys) < h})
    return [c for c in out if c["onScreen"]]


def pair(detected_rows, truth, vw):
    """Every detection paired with a truth card, and how confident that pairing is."""
    dets = []
    for row in detected_rows:
        for card in row["cards"]:
            dets.append({"cx": card["cx"], "cy": row["cy"], "w": card["w"],
                         "unclipped": card["unclipped"]})
    pairs = []
    for d in dets:
        ranked = sorted(truth, key=lambda t: math.hypot(t["cx"] - d["cx"], t["cy"] - d["cy"]))
        if not ranked:
            continue
        best = ranked[0]
        d0 = math.hypot(best["cx"] - d["cx"], best["cy"] - d["cy"])
        d1 = (math.hypot(ranked[1]["cx"] - d["cx"], ranked[1]["cy"] - d["cy"])
              if len(ranked) > 1 else math.inf)
        back = min(dets, key=lambda x: math.hypot(best["cx"] - x["cx"], best["cy"] - x["cy"]))
        mutual = abs(back["cx"] - d["cx"]) < 1e-9 and abs(back["cy"] - d["cy"]) < 1e-9
        ratio = d["w"] / best["w"] if best["w"] else math.inf
        margin = (d0 / d1) if d1 else 0.0
        reasons = []
        if not mutual:
            reasons.append("not mutual nearest")
        if margin > RULES["runnerUpMargin"]:
            reasons.append(f"runner-up margin {margin:.2f} > {RULES['runnerUpMargin']}")
        if not (RULES["widthRatioBand"][0] <= ratio <= RULES["widthRatioBand"][1]):
            reasons.append(f"width ratio {ratio:.2f} outside {RULES['widthRatioBand']}")
        if not d["unclipped"]:
            reasons.append("clipped detection")
        pairs.append({"code": best["code"],
                      "truthCx": round(best["cx"], 2), "detectedCx": round(d["cx"], 2),
                      "dCxPx": round(d["cx"] - best["cx"], 2),
                      "truthW": round(best["w"], 2), "detectedW": round(d["w"], 2),
                      "dWPx": round(d["w"] - best["w"], 2),
                      "widthRatio": round(ratio, 3), "runnerUpMargin": round(margin, 3),
                      "mutualNearest": mutual, "unclipped": d["unclipped"],
                      "highConfidence": not reasons, "excludedBecause": reasons})
    return pairs


if __name__ == "__main__":
    args = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if "=" in a}
    doms = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--dom=")]
    frames_dir = Path(args["--frames"])
    vps = args.get("--vps", "1440x900,960x720,1366x768,1440x1080,780x470,960x500,390x844,700x700,667x375").split(",")
    by_id = {}
    for f in doms:
        for load in json.loads(Path(f).read_text())["loads"]:
            by_id.setdefault(load["id"], load)

    results = []
    for vp in vps:
        load = by_id.get(vp)
        pngs = sorted(str(p) for p in frames_dir.glob(f"{vp}-f*.png"))
        if load is None or not pngs:
            results.append({"id": vp, "status": "NOT_AVAILABLE"})
            continue
        w, h = load["viewport"]
        truth = truth_cards(load)
        detected = G.normalise(G.consensus_measure(pngs), 1)
        pairs = pair(detected["rows"], truth, w)
        hi = [p for p in pairs if p["highConfidence"]]
        lo = [p for p in pairs if not p["highConfidence"]]

        t_bands = sorted(b["c"] for b in detected["bands"] if not b["edge"])
        rows_by_cy: dict[int, list] = {}
        for t in truth:
            rows_by_cy.setdefault(round(t["cy"] / max(1.0, h) * 40), []).append(t)
        truth_gutters = []
        for band in rows_by_cy.values():
            band.sort(key=lambda t: t["cx"])
            for a, b in zip(band, band[1:]):
                if b["x0"] > a["x1"] and b["x0"] - a["x1"] < w * 0.25:
                    truth_gutters.append((a["x1"] + b["x0"]) / 2)

        def gutters(meas):
            g = []
            for row in meas["rows"]:
                g.extend(x["c"] for x in row["gutters"])
            return sorted(g)

        def delta(vals):
            m, ph = [], 0
            for v in vals:
                if not truth_gutters:
                    continue
                d = min(abs(v - t) for t in truth_gutters)
                (m.append(d) if d <= RULES["gutterMatchTolerancePx"] else None) or (ph := ph)
                if d > RULES["gutterMatchTolerancePx"]:
                    ph += 1
            return m, ph

        local = Path(f"artifacts/fsx/local/{vp}/01-rest.png")
        lmeas = G.normalise(ML.measure(local), 1) if local.exists() else None
        t_dev, t_ph = delta(gutters(detected))
        l_dev, l_ph = delta(gutters(lmeas)) if lmeas else ([], 0)

        results.append({
            "id": vp, "status": "MEASURED",
            "truthCardsOnScreen": len(truth), "detections": len(pairs),
            "highConfidencePairs": len(hi), "excludedPairs": len(lo),
            "pairingConfidence": round(len(hi) / len(pairs), 3) if pairs else None,
            "allPairs": {
                "worstCentreErrorPx": round(max((abs(p["dCxPx"]) for p in pairs), default=0.0), 2),
                "worstWidthErrorPx": round(max((abs(p["dWPx"]) for p in pairs), default=0.0), 2),
            },
            "highConfidenceOnly": {
                "worstCentreErrorPx": round(max((abs(p["dCxPx"]) for p in hi), default=0.0), 2),
                "worstWidthErrorPx": round(max((abs(p["dWPx"]) for p in hi), default=0.0), 2),
                "meanWidthErrorPx": round(sum(p["dWPx"] for p in hi) / len(hi), 2) if hi else None,
            },
            "excluded": [{"code": p["code"], "dCxPx": p["dCxPx"], "dWPx": p["dWPx"],
                          "because": p["excludedBecause"]} for p in lo],
            "gutterCentres": {
                "truthCount": len(truth_gutters),
                "targetFrameMatched": len(t_dev), "targetFramePhantoms": t_ph,
                "targetFrameWorstDeltaPx": round(max(t_dev), 2) if t_dev else None,
                "sourceExactFrameMatched": len(l_dev), "sourceExactFramePhantoms": l_ph,
                "sourceExactFrameWorstDeltaPx": round(max(l_dev), 2) if l_dev else None,
                "ourReadingIsAtLeastAsCloseToTruth":
                    (max(l_dev) <= max(t_dev) + 1e-9) if (t_dev and l_dev) else None,
            },
            "pairs": pairs,
        })

    m = [r for r in results if r["status"] == "MEASURED"]
    payload = {
        "correction": "Supersedes qa-v5/fsx/detector-residual.json AS QUOTED. That file's own "
                      "top-level fields were 35.02 px and 118.75 px; the F2-SX delivery reply "
                      "quoted 2.67 px and 71.89 px, which were the maxima of an earlier "
                      "six-viewport run. Both the all-pair and the high-confidence figures are "
                      "reported here so the distinction cannot be lost again.",
        "scope": "Bounds the PIXEL INSTRUMENT only. Both sides of the comparison come from the "
                 "Target: its own DOM geometry against a detector reading its own frame. It "
                 "cannot substitute for the source contract and it asserts nothing about beauty.",
        "exclusionRules": RULES,
        "allPairs": {
            "worstCentreErrorPx": round(max((r["allPairs"]["worstCentreErrorPx"] for r in m), default=0.0), 2),
            "worstWidthErrorPx": round(max((r["allPairs"]["worstWidthErrorPx"] for r in m), default=0.0), 2),
        },
        "highConfidenceOnly": {
            "worstCentreErrorPx": round(max((r["highConfidenceOnly"]["worstCentreErrorPx"] for r in m), default=0.0), 2),
            "worstWidthErrorPx": round(max((r["highConfidenceOnly"]["worstWidthErrorPx"] for r in m), default=0.0), 2),
        },
        "pairingConfidenceOverall": round(
            sum(r["highConfidencePairs"] for r in m) / max(1, sum(r["detections"] for r in m)), 3),
        "totalDetections": sum(r["detections"] for r in m),
        "totalHighConfidence": sum(r["highConfidencePairs"] for r in m),
        "totalExcluded": sum(r["excludedPairs"] for r in m),
        "phantomGutters": {"targetFrames": sum(r["gutterCentres"]["targetFramePhantoms"] for r in m),
                           "sourceExactFrames": sum(r["gutterCentres"]["sourceExactFramePhantoms"] for r in m)},
        "ourGutterReadingNeverWorseThanTargetsOwn":
            all(r["gutterCentres"]["ourReadingIsAtLeastAsCloseToTruth"] is not False for r in m),
        "viewports": results,
    }
    Path(args["--out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["--out"]).write_text(json.dumps(payload, indent=2))
    print(f"ALL pairs        centre <= {payload['allPairs']['worstCentreErrorPx']} px, "
          f"width <= {payload['allPairs']['worstWidthErrorPx']} px")
    print(f"HIGH-confidence  centre <= {payload['highConfidenceOnly']['worstCentreErrorPx']} px, "
          f"width <= {payload['highConfidenceOnly']['worstWidthErrorPx']} px "
          f"({payload['totalHighConfidence']}/{payload['totalDetections']} pairs, "
          f"confidence {payload['pairingConfidenceOverall']})")
    print(f"phantom gutters  target {payload['phantomGutters']['targetFrames']}, "
          f"ours {payload['phantomGutters']['sourceExactFrames']}")
    for r in m:
        print(f"  {r['id']:>10} conf={r['pairingConfidence']} hi={r['highConfidencePairs']:2d} "
              f"excl={r['excludedPairs']:2d} allC={r['allPairs']['worstCentreErrorPx']:6.2f} "
              f"hiC={r['highConfidenceOnly']['worstCentreErrorPx']:5.2f} "
              f"hiW={r['highConfidenceOnly']['worstWidthErrorPx']:6.2f}")
