#!/usr/bin/env python3
"""O5F §十/§十一 -- the portrait closure decision, mechanically applied.

The decision tree below is PRE-REGISTERED: this file is committed in the
forensics commit alongside the instruments, before any Phase B capture is
scored, so the tree cannot be re-shaped around the data it will read.

Priority order:

 1. Phase A gates (identity, stress) must both be PASS. A failed Phase A
    was already a stop; the closure records it and refuses to reason
    further.
 2. §十A short-circuit. If the P0 residual is isolated to clip 2 -- every
    clip-0/1 row inside the sealed window and every clip-2 row outside it,
    on BOTH metrics -- the classification is FROZEN MEDIA-CROP PRODUCT
    DEVIATION. No optics change, no Media Fit change; the round stops for
    a product crop decision. Every other finding (a sample-tier mismatch
    included) is REPORTED for the next round, not acted on.
 3. Proven source mismatch. Readable instruments naming a first
    source-level cause: either a chain term that diverges from the source
    formula (§九), or a chain that is faithful while a chain INPUT is
    proven wrong -- the sample-tier mapping being the §十一-listed case.
    At most ONE correction; after it, the §十四 re-runs must pass and the
    sealed windows are re-read from post-fix captures.
 4. No mismatch, all instruments readable: PORTRAIT RESIDUAL REQUIRES
    PRODUCT TOLERANCE DECISION. Product code untouched.
 5. Unreadable at the deciding step: O5F PORTRAIT SOURCE RECONCILIATION
    FAILED. An unreadable instrument never converts to a verdict, and a
    round whose objective cannot be read has failed that objective.

Output: qa-v5/optics-o5f/portrait-closure.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
QA = REPO / "qa-v5/optics-o5f"
OUT = QA / "portrait-closure.json"

FINAL_STATES = [
    "READY FOR TARGET-SOURCE OPTICAL BODY PRODUCT ACCEPTANCE REVIEW",
    "READY FOR PRODUCT REVIEW WITH DECLARED PORTRAIT RESIDUAL",
    "O5F MATERIAL CACHE FAILED",
    "O5F PORTRAIT SOURCE RECONCILIATION FAILED",
]

# The sealed O5R corrected-gate residuals this round set out to explain.
SEALED_RESIDUAL = {
    "darkSideLuma390x844": {"candidate": 51.28, "target": 58.57},
    "whiteReflectionRatio390x844": {"candidate": 4.9035, "target": 3.8676},
}


def load(name):
    p = QA / name
    return json.loads(p.read_text()) if p.exists() else None


def main() -> int:
    ident = load("material-cache-identity.json")
    stress = load("material-cache-stress.json")
    attr = load("clip-index-attribution.json")
    tier = load("target-mobile-tier.json")
    dec = load("portrait-term-decomposition.json")
    refl = load("reflection-direction.json")
    outx = load("output-transform.json")
    roi = load("roi-isolation.json")
    fix = load("portrait-source-code.json")   # exists iff §十一 was exercised

    trace = []

    # ---- 1. Phase A ------------------------------------------------------
    phase_a = (ident is not None and ident.get("verdict") == "PASS"
               and stress is not None and stress.get("verdict") == "PASS")
    trace.append({"step": "phaseA",
                  "identity": (ident or {}).get("verdict"),
                  "stress": (stress or {}).get("verdict"),
                  "pass": phase_a})
    if not phase_a:
        return emit({"finalState": "O5F MATERIAL CACHE FAILED",
                     "classification": "PHASE A DID NOT PASS",
                     "trace": trace})

    # ---- 2. §十A clip-2 isolation ---------------------------------------
    # The attribution rows are per-card pixel metrics; they are only
    # attributable to the body if the ROI proof shows the measurement bands
    # clean of typography, footer and neighbours. A contaminated band makes
    # the isolation UNREADABLE, not false.
    roi_clean = bool(roi and roi.get("pass"))
    p0attr = (attr or {}).get("p0Conclusion")
    iso = (p0attr or {}).get("isolatedToClip2") or {}
    iso_vals = [iso.get("dark_side_luma"), iso.get("white_reflection_ratio")]
    attribution_readable = roi_clean and all(v is not None for v in iso_vals)
    isolated = attribution_readable and all(v is True for v in iso_vals)
    trace.append({"step": "clip2Isolation", "roiClean": roi_clean,
                  "isolatedToClip2": iso,
                  "readable": attribution_readable, "isolated": isolated})
    if isolated:
        return emit({
            "finalState": "READY FOR PRODUCT REVIEW WITH DECLARED PORTRAIT "
                          "RESIDUAL",
            "classification": "FROZEN MEDIA-CROP PRODUCT DEVIATION",
            "action": "no optics change, no Media Fit change; the frozen "
                      "clip-2 crop (focusY 0.46, zoom 1.06) is the isolated "
                      "carrier of the P0 residual and changing it is a "
                      "product decision, not a transcription fix.",
            "reportedNotActedOn": {
                "sampleTierMismatch": ((tier or {}).get("conclusion") or {})
                .get("p0"),
                "note": "§十A short-circuits: findings besides the crop are "
                        "reported for the next round, not acted on in this "
                        "one.",
            },
            "trace": trace})

    # ---- 3. the first source-level cause --------------------------------
    dec_status = None if dec is None else dec.get("terms")
    dec_readable = (dec is not None
                    and not dec.get("instrumentUnreadableTerms"))
    first_term = None if dec is None else dec.get("firstDivergingTerm")
    tier_readable = bool(tier and tier.get("status") == "READABLE")
    tier_mismatch = bool(tier_readable
                         and ((tier.get("conclusion") or {}).get("p0") or {})
                         .get("sampleTierMismatch"))
    trace.append({"step": "sourceCause",
                  "decompositionReadable": dec_readable,
                  "firstDivergingTerm": first_term,
                  "tierReadable": tier_readable,
                  "tierMismatch": tier_mismatch,
                  "reflectionDirection": (refl or {})
                  .get("allDirectionTermsMatchAtP0"),
                  "outputTransformAgrees": (outx or {}).get("agrees")})

    cause = None
    if dec_readable and first_term is not None:
        cause = {"kind": "CHAIN TERM DIVERGES", "term": first_term,
                 "basis": "portrait-term-decomposition.json"}
    elif dec_readable and tier_mismatch:
        cause = {"kind": "WRONG RUNTIME SAMPLE-TIER MAPPING",
                 "basis": "target-mobile-tier.json: the Target's tier is a "
                          "device predicate, and its P0 program runs a "
                          "different sample count than ours",
                 "target": ((tier.get("conclusion") or {}).get("p0") or {}),
                 "explicitlyListedIn": "§十一 allowed example: wrong runtime "
                                       "sample-tier mapping"}

    # ---- 3b. was the one correction applied? ----------------------------
    if fix is not None:
        gates = fix.get("gates") or {}
        gates_pass = (gates.get("controlIdentityAfterFix") == "PASS"
                      and gates.get("stressRerun") == "PASS")
        post = fix.get("postFixP0") or {}
        both_inside = (post.get("darkSideLumaInsideWindow") is True
                       and post.get("whiteReflectionRatioInsideWindow")
                       is True)
        trace.append({"step": "correction", "applied": True,
                      "cause": fix.get("cause"), "gatesPass": gates_pass,
                      "postFixBothInsideWindow": both_inside})
        if not gates_pass:
            return emit({
                "finalState": "O5F PORTRAIT SOURCE RECONCILIATION FAILED",
                "classification": "THE ONE CORRECTION BROKE A FROZEN GATE",
                "cause": cause, "correction": fix, "trace": trace})
        if both_inside:
            return emit({
                "finalState": "READY FOR TARGET-SOURCE OPTICAL BODY PRODUCT "
                              "ACCEPTANCE REVIEW",
                "classification": "SOURCE TRANSCRIPTION MISMATCH CORRECTED; "
                                  "P0 RESIDUAL CLOSED",
                "cause": cause, "correction": fix, "trace": trace})
        return emit({
            "finalState": "READY FOR PRODUCT REVIEW WITH DECLARED PORTRAIT "
                          "RESIDUAL",
            "classification": "CORRECTION APPLIED AND DISCLOSED; RESIDUAL "
                              "NOT FULLY CLOSED",
            "note": "one change only -- §十一 forbids chasing the remainder "
                    "with tuning.",
            "cause": cause, "correction": fix, "trace": trace})

    # ---- 4 / 5. no correction applied -----------------------------------
    if cause is not None:
        # A cause was proven but not corrected in this round. That is only
        # a legitimate stop if the cause is not a directly-provable source
        # transcription mismatch (e.g. a diverging term whose source line
        # could not be pinned). Record it; the state is a declared residual
        # with the cause named.
        return emit({
            "finalState": "READY FOR PRODUCT REVIEW WITH DECLARED PORTRAIT "
                          "RESIDUAL",
            "classification": "FIRST SOURCE-LEVEL CAUSE IDENTIFIED, NOT "
                              "CORRECTED",
            "cause": cause, "trace": trace})

    if dec_readable and tier_readable and attribution_readable:
        return emit({
            "finalState": "READY FOR PRODUCT REVIEW WITH DECLARED PORTRAIT "
                          "RESIDUAL",
            "classification": "PORTRAIT RESIDUAL REQUIRES PRODUCT TOLERANCE "
                              "DECISION",
            "basis": "every instrument readable; no chain term diverges, "
                     "the sample tiers agree, and the residual is not "
                     "isolated to the frozen crop. No source mismatch "
                     "exists, so §十一 forbids touching product code.",
            "trace": trace})

    return emit({
        "finalState": "O5F PORTRAIT SOURCE RECONCILIATION FAILED",
        "classification": "DECIDING INSTRUMENT UNREADABLE",
        "unreadable": {
            "decomposition": None if dec is None
            else dec.get("instrumentUnreadableTerms"),
            "tier": None if tier_readable else (tier or {}).get("status"),
            "attribution": attribution_readable,
        },
        "trace": trace})


def emit(body):
    doc = {
        "what": "§十/§十一 -- the portrait closure decision, applied by the "
                "pre-registered tree in scripts/v5/o5f-portrait-closure.py.",
        "sealedResidualUnderExamination": SEALED_RESIDUAL,
        **body,
        "reviewSummaryWordingRules": {
            "silhouette": "N/A-UNREADABLE in this round's summary: the "
                          "background ring is contaminated by neighbouring "
                          "cards and three of four PASS rows are "
                          "near-degenerate (O5R correction C). The sealed "
                          "rows themselves stand unmodified.",
            "pointerPath": "one readable PASS row (1440x900) and three "
                           "INSTRUMENT_UNREADABLE rows -- never 'a "
                           "4-viewport PASS' (O5R correction A).",
            "fullFrameReadiness": "proves the review package exists; it is "
                                  "not a product visual PASS (O5R "
                                  "correction B).",
            "o5rGate": "PASS 7 / FAIL 7 stays sealed and regression-only; "
                       "full-frame judgment is owned by the product review.",
            "noNewThresholds": "no threshold in this round was created "
                               "after Candidate capture.",
        },
        "targetVisualPass": "NOT ASSERTED",
    }
    assert doc["finalState"] in FINAL_STATES, doc["finalState"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"finalState: {doc['finalState']}")
    print(f"classification: {doc.get('classification')}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
