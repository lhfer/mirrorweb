#!/usr/bin/env python3
"""
Is the remaining pixel residual OUR layout, or the detector reading a glass card?

The source-contract gate already shows the engine matches the Target's own DOM
world transforms to 0.005 world units. If that is true and the pixel gate still
shows a few pixels of gutter-centre error, then the error is in what a pixel
detector makes of a video-filled glass card versus a flat opaque slab.

That is testable without us in the picture at all: project the TARGET's own DOM
card corners through the TARGET's own camera, and compare them with what the
detector reads off the TARGET's own frame. Any disagreement there is the
detector, measured against ground truth from the same site.

Usage: fsx-detector-residual.py --dom=<dom-state.json> --frames=<dir> --out=<json> [--vps=a,b]
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load("f2_gate", "f2-gate.py")
ML = _load("measure_layout", "measure-layout.py")
SL = _load("source_layout", "source_layout.py")
SC = _load("fsx_source_contract", "fsx-source-contract.py")


def target_truth_cards(load: dict) -> list[dict]:
    """Projected corners of every code-bearing Target card, from its own DOM."""
    w, h = load["viewport"]
    frame = SL.layout(w, h)
    persp = frame["perspective"]
    R = frame["sphereRadius"]
    out = []
    for c in SC.dom_cards(load):
        wx, wy, wz = SC.dom_world(c)
        # Recover the surface normal from the position: it is the unit vector
        # from the sphere centre, which is at (0, 0, -R).
        n = (wx / R, wy / R, (wz + R) / R)
        ln = math.sqrt(sum(v * v for v in n)) or 1.0
        n = tuple(v / ln for v in n)
        q = SC.quat_from_unit_vectors((0.0, 0.0, 1.0), n)
        rx = SC.rotate(q, (1.0, 0.0, 0.0))
        ry = SC.rotate(q, (0.0, 1.0, 0.0))
        hw, hh = c["cssW"] / 2, c["cssH"] / 2
        corners = []
        for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
            p = [(wx, wy, wz)[k] + rx[k] * sx * hw + ry[k] * sy * hh for k in range(3)]
            pr = SC.project(p, persp, w, h)
            if pr is None:
                corners = []
                break
            corners.append(pr)
        if not corners:
            continue
        xs = [p[0] for p in corners]
        ys = [p[1] for p in corners]
        out.append({"code": c["code"], "cx": sum(xs) / 4, "cy": sum(ys) / 4,
                    "x0": min(xs), "x1": max(xs), "w": max(xs) - min(xs),
                    "onScreen": max(xs) > 0 and min(xs) < w and max(ys) > 0 and min(ys) < h})
    return out


if __name__ == "__main__":
    args = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if "=" in a}
    doms = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--dom=")]
    frames_dir = Path(args["--frames"])
    vps = args.get("--vps", "1440x900,960x720,1366x768,1440x1080,780x470,960x500").split(",")
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
        truth = [c for c in target_truth_cards(load) if c["onScreen"]]
        detected = G.normalise(G.consensus_measure(pngs), 1)
        pairs = []
        for row in detected["rows"]:
            for card in row["cards"]:
                best = None
                for t in truth:
                    d = abs(t["cx"] - card["cx"])
                    if best is None or d < best[0]:
                        best = (d, t)
                if best is None or best[0] > w * 0.06:
                    continue
                t = best[1]
                pairs.append({
                    "code": t["code"],
                    "truthCx": round(t["cx"], 2), "detectedCx": round(card["cx"], 2),
                    "dCxPx": round(card["cx"] - t["cx"], 2),
                    "truthW": round(t["w"], 2), "detectedW": round(card["w"], 2),
                    "dWPx": round(card["w"] - t["w"], 2),
                    "unclipped": card["unclipped"],
                })
        clean = [p for p in pairs if p["unclipped"]]

        # The statistic the pixel gate actually fails on is the GUTTER CENTRE.
        # Compute it three ways at the same viewport: from the Target's own DOM
        # geometry (ground truth), from the detector reading the Target's frame,
        # and from the detector reading ours. If ours is no further from truth
        # than the Target's own reading is, the residual is the instrument.
        # Group by ROW before pairing neighbours: cards in different rows overlap
        # in x, so a flat sort pairs cards that have no gutter between them.
        rows_by_cy: dict[int, list] = {}
        for t in truth:
            rows_by_cy.setdefault(round(t["cy"] / max(1.0, h) * 40), []).append(t)
        truth_gutters = []
        for band in rows_by_cy.values():
            band.sort(key=lambda t: t["cx"])
            for a, b in zip(band, band[1:]):
                if b["x0"] > a["x1"] and b["x0"] - a["x1"] < w * 0.25:
                    truth_gutters.append(round((a["x1"] + b["x0"]) / 2, 2))
        truth_gutters.sort()
        def detected_gutters(meas):
            g = []
            for row in meas["rows"]:
                g.extend(x["c"] for x in row["gutters"])
            return sorted(g)
        def nearest_delta(values, truths, tol=30.0):
            """
            How far each DETECTED gutter sits from the nearest TRUE one.

            A detected gutter with no true gutter anywhere near it is not a
            measurement of a gutter -- it is the detector finding void where a
            card was clipped or a video frame went dark. Those are counted
            separately rather than allowed to set the maximum, because a single
            300 px phantom would otherwise swamp the real 1-6 px question.
            """
            matched, unmatched = [], 0
            for v in values:
                if not truths:
                    continue
                d = min(abs(v - t) for t in truths)
                if d <= tol:
                    matched.append(d)
                else:
                    unmatched += 1
            return matched, unmatched
        local_png = Path(f"artifacts/fsx/local/{vp}/01-rest.png")
        local_meas = G.normalise(ML.measure(local_png), 1) if local_png.exists() else None
        t_dev, t_phantom = nearest_delta(detected_gutters(detected), truth_gutters)
        l_dev, l_phantom = (nearest_delta(detected_gutters(local_meas), truth_gutters)
                            if local_meas else ([], 0))
        results.append({
            "id": vp, "status": "MEASURED",
            "cardsCompared": len(clean),
            "worstCentreErrorPx": round(max((abs(p["dCxPx"]) for p in clean), default=0.0), 2),
            "worstWidthErrorPx": round(max((abs(p["dWPx"]) for p in clean), default=0.0), 2),
            "meanWidthErrorPx": round(sum(p["dWPx"] for p in clean) / len(clean), 2) if clean else None,
            "gutterCentres": {
                "truthFromTargetDom": truth_gutters,
                "targetFrameMatched": len(t_dev),
                "targetFramePhantomGutters": t_phantom,
                "targetFrameWorstDeltaPx": round(max(t_dev), 2) if t_dev else None,
                "sourceExactFrameMatched": len(l_dev),
                "sourceExactFramePhantomGutters": l_phantom,
                "sourceExactFrameWorstDeltaPx": round(max(l_dev), 2) if l_dev else None,
                "ourReadingIsAtLeastAsCloseToTruth":
                    (max(l_dev) <= max(t_dev) + 1e-9) if (t_dev and l_dev) else None,
            },
            "pairs": clean,
        })

    payload = {
        "question": "How far does the pixel detector read a TARGET card from where the "
                    "TARGET's own DOM says that card is?",
        "why": "Both sides of this comparison come from the Target alone. Nothing we render "
               "is involved, so whatever error appears here is the instrument meeting a "
               "video-filled glass card, and it bounds how much of the pixel gate's residual "
               "can possibly be attributed to our layout.",
        "instrument": "scripts/v5/f2-gate.py detector, 5-frame consensus, against corners "
                      "projected from the Target's own CSS3D world transforms",
        "worstCentreErrorPx": round(max((r["worstCentreErrorPx"] for r in results
                                         if r["status"] == "MEASURED"), default=0.0), 2),
        "worstWidthErrorPx": round(max((r["worstWidthErrorPx"] for r in results
                                        if r["status"] == "MEASURED"), default=0.0), 2),
        "viewports": results,
    }
    Path(args["--out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["--out"]).write_text(json.dumps(payload, indent=2))
    print(f"detector vs Target's own geometry: worst centre {payload['worstCentreErrorPx']} px, "
          f"worst width {payload['worstWidthErrorPx']} px")
    print("  gutter centre against DOM truth   target-frame / source-exact-frame")
    for r in results:
        if r["status"] == "MEASURED":
            g = r["gutterCentres"]
            print(f"  {r['id']:>10} n={r['cardsCompared']:2d} centre<={r['worstCentreErrorPx']:5.2f}px "
                  f"width<={r['worstWidthErrorPx']:6.2f}px | gutter truth-delta "
                  f"target={g['targetFrameWorstDeltaPx']}({g['targetFrameMatched']}m/{g['targetFramePhantomGutters']}p) "
                  f"ours={g['sourceExactFrameWorstDeltaPx']}({g['sourceExactFrameMatched']}m/{g['sourceExactFramePhantomGutters']}p) "
                  f"oursNoWorse={g['ourReadingIsAtLeastAsCloseToTruth']}")
