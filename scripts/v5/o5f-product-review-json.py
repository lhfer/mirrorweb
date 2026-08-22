#!/usr/bin/env python3
"""O5F §十五 -- the O5R product review in machine-readable form.

`docs/v5/O5R_PRODUCT_REVIEW.md` is the record a person reads. This is the
same record shaped so the evidence tree can be checked mechanically: every
ACCEPTED claim carries the sealed numbers it rests on, every NOT-ACCEPTED
item carries the gap that keeps it there, and each of the five evidence
wording corrections carries the sealed rows it corrects the reading of.

Output: qa-v5/optics-o5f/o5r-product-review.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
O5R = REPO / "qa-v5/optics-o5r"
OUT = REPO / "qa-v5/optics-o5f/o5r-product-review.json"
REVIEWED_AT = "445037e11eb44ae07bca6360707e043d969b1d4b"


def load(name):
    p = O5R / name
    return json.loads(p.read_text()) if p.exists() else None


def item(gate, n):
    for i in gate["items"]:
        if i["item"] == n:
            return i
    return None


def main() -> int:
    gate = load("corrected-product-gate.json")
    pointer = load("pointer-path.json")
    closure = load("portrait-closure.json")
    perf = load("pipeline-performance-v2.json")
    ident = load("control-identity.json")
    seal = load("sealed-lane-identity.json")
    reg = load("regressions.json")
    hdr = load("hdr-radiance-audit.json")

    sil = item(gate, 9)
    band = item(gate, 1)
    refr = item(gate, 6)

    doc = {
        "what": "the O5R product review, machine-readable. The human record "
                "is docs/v5/O5R_PRODUCT_REVIEW.md.",
        "reviewedAt": REVIEWED_AT,
        "sealedCorrectedGate": {
            "counts": gate["counts"], "gate": gate["gate"],
            "finalState": "O5R TARGET-SOURCE BODY FAILED CORRECTED PRODUCT "
                          "GATE",
            "notRewritten": True,
        },
        "accepted": {
            "hdrAuditAndUnclamp": {
                "asA": "source correction",
                "audit": {k: (hdr or {}).get(k) for k in
                          ("nanChannels", "infChannels", "maxRadiance",
                           "oldCeiling", "verdict") if hdr and k in hdr},
                "consequence": "target-source-unclamped is the only active "
                               "optics candidate; the sealed clamped lane "
                               "is retained for regression only",
            },
            "structuralEnvironmentOff": "environmentMode=off omits the "
                                        "sample from the PROGRAM",
            "refractionCompression": {
                "status": refr["status"],
                "note": "replay validated on the Target's own render to "
                        "1.4-1.6 px; candidate displacement inside the "
                        "Target window at every readable viewport",
            },
            "reflectionBand": {"status": band["status"],
                               "rows": band["numbers"]["rows"]},
            "ownMediaIsolation": item(gate, 8)["status"],
            "temporalContinuity": item(gate, 11)["status"],
            "mobileDirection": item(gate, 12)["status"],
            "controlIdentity": {"comparisons": (ident or {}).get("comparisons"),
                                "verdict": (ident or {}).get("verdict")},
            "sealedLaneIdentity": {"comparisons": (seal or {}).get("comparisons"),
                                   "exactZero": (seal or {}).get("exactZero")},
            "frozenRegressions": {"passed": (reg or {}).get("suitesPassed"),
                                  "total": (reg or {}).get("suiteCount")},
        },
        "notAccepted": {
            "defaultFlip": "opticalBody=current remains shipped",
            "darkSideLuma390x844": (closure or {})["outcome"]["darkSideLuma"],
            "whiteReflectionRatio390x844":
                (closure or {})["outcome"]["whiteReflectionRatio"],
            "memoryResourceStability": {
                "sessionTroughRisesMB": [18.59, 20.03, 22.15],
                "controlTroughRiseMB": -1.04,
                "attribution": "quality-step material rebuild -- 39.36 MB "
                               "in the six-minute quality-cycle arm against "
                               "<= 2.06 MB in every other arm, ~68 KB per "
                               "step",
                "performanceVerdict": (perf or {}).get("pass"),
            },
            "targetVisualPass": "NOT ASSERTED",
        },
        "evidenceWordingCorrections": {
            "A_pointerPath": {
                "correction": "NOT 'every instrument now reads': one "
                              "readable PASS row and three "
                              "INSTRUMENT_UNREADABLE rows",
                "sealedRows": [{"vp": r["vp"], "status": r["status"]}
                               for r in (pointer or {}).get("rows", [])],
            },
            "B_fullFrameReadiness": "proves the review package exists; it "
                                    "is not a product visual PASS",
            "C_silhouette": {
                "correction": "background ring contaminated by neighbouring "
                              "cards; three PASS rows near-degenerate; at "
                              "390x844 the candidate is the closest "
                              "silhouette match despite the sealed FAIL",
                "numbers390x844": {
                    lane: {"litBeyondSilhouette": v["litBeyondSilhouette"],
                           "iou": v["iou"]}
                    for lane, v in (sil["numbers"]["rows"][1]["lanes"]
                                    .items())},
            },
            "D_windowFloors": "the grayscale and saturated-edge instruments "
                              "discriminate, but their fixed floors are "
                              "scale-blind; the sealed FAIL rows stand and "
                              "may not be cited as calibrated absolute "
                              "product thresholds",
            "E_packageMetadata": {
                "defect": "O5R package reviewHead recorded 726ee02; the "
                          "semantic reviewHead is 445037e",
                "fix": "applied in the O5F package only: capturedAtHead = "
                       "the capture SHA, reviewHead = the final evidence "
                       "SHA. No standalone hygiene delivery.",
            },
        },
        "o5fAuthorisation": {
            "phaseA": "eliminate the quality-step material retention behind "
                      "a finite material-set cache; identity then stress, "
                      "both pre-registered",
            "phaseB": "identify the FIRST source-level cause of the 390x844 "
                      "residual; at most one proven source-transcription "
                      "correction; no constant tuning",
            "not": ["default flip", "main merge", "source constant tuning",
                    "another optics architecture", "rewriting O5/O5R sealed "
                    "evidence", "Final Integration", "Target Visual PASS"],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
