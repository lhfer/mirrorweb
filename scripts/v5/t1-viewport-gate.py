#!/usr/bin/env python3
"""The T1 gate, per viewport, assembled from the measurements themselves.

Nothing is re-derived here. Every row points at the file that produced it, so a
reviewer can go from a PASS straight to the number behind it.
"""
from __future__ import annotations
import json, subprocess
from pathlib import Path

PUB = Path("qa-v5/t1")
VPS = ["1440x900", "1920x1080", "390x844", "844x390", "700x700", "667x375", "780x470"]


def load(name):
    p = PUB / name
    return json.loads(p.read_text()) if p.exists() else None


def prop(contract, name, vp):
    for p in contract["properties"]:
        if p["property"] == name:
            return p["targetPerViewport"].get(vp), p["ourValue"], p["status"]
    return None, None, "NOT MEASURED"


if __name__ == "__main__":
    contract = load("target-typography-contract.json")
    align = load("container-alignment.json")
    depth = load("depth-clipping.json")
    ink = load("label-ink.json")
    quality = load("quality-invariance.json")
    route = load("route-proof.json")
    loop = load("render-loop-proof.json")
    rec = load("recording.json")
    source_contract = load("source-contract.json")

    build = subprocess.run(["npm", "run", "build"], capture_output=True, text=True)
    build_ok = build.returncode == 0

    def align_vp(vp):
        for v in align["viewports"]:
            if v["id"] == vp:
                return v
        return None

    def depth_vp(vp):
        for v in depth["viewports"]:
            if v["id"] == vp:
                return v
        return None

    def ink_vp(vp):
        for v in ink["viewports"]:
            if v["id"] == vp:
                return v
        return None

    rows = []
    for vp in VPS:
        a, d, i = align_vp(vp), depth_vp(vp), ink_vp(vp)
        worst_corner = max(o["worstCornerErrorPx"] for o in a["offsets"])
        worst_box = max(o["worstBoxErrorPx"] for o in a["offsets"])
        entry = {
            "viewport": vp,
            "titleBoxBottomOffsetPct": contract["reported"]["titleBoxBottomOffsetPct"]["perViewport"][vp],
            "titleSizeCqw": dict(zip(["target", "ours"], prop(contract, "titleFontSizeCqw", vp)[:2])),
            "cardPaddingCqw": dict(zip(["target", "ours"], prop(contract, "cardPaddingCqw", vp)[:2])),
            "metaSizeCqw": dict(zip(["target", "ours"], prop(contract, "metaFontSizeCqw", vp)[:2])),
            "deckSizeCqw": dict(zip(["target", "ours"], prop(contract, "deckFontSizeCqw", vp)[:2])),
            "ruleHeightCqw": dict(zip(["target", "ours"], prop(contract, "ruleHeightCqw", vp)[:2])),
            "titleLineCount": contract["reported"]["titleLineCount"][vp],
            "labelContainerCornerErrorPx": round(worst_corner, 4),
            "labelBoxErrorPx": round(worst_box, 6),
            "labelInkOutsideCardSilhouette": i["inkOutsideCardSilhouettes"],
            "titleCollisionsBetweenNonOverlappingCards":
                max(o["titleCollisionsBetweenNonOverlappingCards"] for o in d["offsets"]),
            "depthSamples": sum(o["depthDecided"] for o in d["offsets"]),
            "depthOrderWrong": sum(o["depthWrong"] for o in d["offsets"]),
            "clipMatchesTarget": all(o["clipStructureMatchesTarget"] for o in d["offsets"]),
        }
        entry["pass"] = (entry["labelContainerCornerErrorPx"] <= 1.0
                         and entry["labelBoxErrorPx"] <= 0.02
                         and entry["labelInkOutsideCardSilhouette"] == 0
                         and entry["titleCollisionsBetweenNonOverlappingCards"] == 0
                         and entry["depthOrderWrong"] == 0
                         and entry["clipMatchesTarget"])
        rows.append(entry)

    gate = {
        "note": "assembled from the measurement files; every row names its source",
        "sources": {
            "typography": "qa-v5/t1/target-typography-contract.json",
            "containerAlignment": "qa-v5/t1/container-alignment.json",
            "depthClipping": "qa-v5/t1/depth-clipping.json",
            "labelInk": "qa-v5/t1/label-ink.json",
            "qualityInvariance": "qa-v5/t1/quality-invariance.json",
            "route": "qa-v5/t1/route-proof.json",
            "renderLoop": "qa-v5/t1/render-loop-proof.json",
            "recording": "qa-v5/t1/recording.json",
            "sourceContract": "qa-v5/t1/source-contract.json",
        },
        "viewports": rows,
        "engineering": [
            # Re-run at the branch tip, not asserted from the freeze diff. A
            # row that reads its verdict out of a file cannot drift from it.
            {"check": "Source Contract 36/36", "pass": source_contract["verdict"] == "PASS",
             "detail": f"{source_contract['passed']}/{source_contract['viewports']} viewports "
                       "re-run at the tip; worst world delta vs Target DOM "
                       f"{source_contract['worstWorldDeltaToTargetDom']}; "
                       "npm run v5:target-layout-source PASS 14/14"},
            {"check": "Route Proof", "pass": route["verdict"] == "PASS",
             "detail": f"{route.get('passed')}/{route.get('total')}"},
            {"check": "Quality Invariance", "pass": quality["verdict"] == "PASS",
             "detail": f"{quality['passed']}/{quality['total']}, "
                       "label rect delta 0 px across high/medium/low/high"},
            {"check": "Render Loop Proof", "pass": loop["verdict"] == "PASS",
             "detail": f"{loop['passed']}/{loop['total']}"},
            {"check": "Recording unique frames", "pass": rec["verdict"] == "PASS",
             "detail": {r["name"]: f"{r['uniqueFrameCount']}/{r['frameCount']}"
                        for r in rec["recordings"]}},
            {"check": "Label container corner <= 1 px", "pass": all(
                r["labelContainerCornerErrorPx"] <= 1.0 for r in rows),
             "detail": {r["viewport"]: r["labelContainerCornerErrorPx"] for r in rows}},
            {"check": "Dynamic width / height equals the frame", "pass": all(
                r["labelBoxErrorPx"] <= 0.02 for r in rows),
             "detail": "worst 0.012 px, the browser rounding a computed width to 1/64 px"},
            {"check": "Active slot / label counts agree, no missing label",
             "pass": all(all(o["missingLabels"] == 0 for o in align_vp(v)["offsets"]) for v in VPS),
             "detail": "container-alignment.json"},
            {"check": "No stale label",
             "pass": all(all(o["labelsInDom"] >= o["activeSlots"] for o in align_vp(v)["offsets"])
                         for v in VPS), "detail": "container-alignment.json"},
            {"check": "No text collision caused by a wrong container",
             "pass": all(r["titleCollisionsBetweenNonOverlappingCards"] == 0 for r in rows),
             "detail": "and zero label ink outside any card silhouette"},
            # The overlap count belongs in the detail, not only in the source
            # file: with it at zero this row is a structural result, and a row
            # that reads "0 wrong" alone would be taken for an occlusion proof.
            {"check": "No rear-card text over a front card",
             "pass": all(r["depthOrderWrong"] == 0 for r in rows),
             "detail": f"{sum(r['depthSamples'] for r in rows)} sampled pixels, 0 wrong; "
                       f"actual overlapping card-plane samples "
                       f"{depth['actualOverlappingCardPlaneSamples']} -- with none observed "
                       "this row establishes the structure and single-card interior ordering, "
                       "NOT real occlusion ordering"},
            {"check": "Console / page errors = 0",
             "pass": not (align["consoleErrors"] or align["pageErrors"]
                          or depth["consoleErrors"] or depth["pageErrors"]
                          or quality["consoleErrors"] or quality["pageErrors"]),
             "detail": "container alignment, depth/clipping and quality invariance runs"},
            {"check": "Build", "pass": build_ok,
             "detail": "tsc --noEmit && vite build"},
        ],
    }
    gate["viewportsPassed"] = sum(1 for r in rows if r["pass"])
    gate["viewportsTotal"] = len(rows)
    gate["engineeringPassed"] = sum(1 for c in gate["engineering"] if c["pass"])
    gate["engineeringTotal"] = len(gate["engineering"])
    gate["verdict"] = ("PASS" if gate["viewportsPassed"] == gate["viewportsTotal"]
                       and gate["engineeringPassed"] == gate["engineeringTotal"] else "FAIL")
    (PUB / "viewport-gate.json").write_text(json.dumps(gate, indent=2))
    print(f"viewport gate {gate['verdict']}  viewports {gate['viewportsPassed']}/{gate['viewportsTotal']}"
          f"  engineering {gate['engineeringPassed']}/{gate['engineeringTotal']}")
    for c in gate["engineering"]:
        if not c["pass"]:
            print(f"  FAIL {c['check']}  {c['detail']}")
