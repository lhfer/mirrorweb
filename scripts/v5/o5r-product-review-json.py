#!/usr/bin/env python3
"""§十五 -- the O5 product review in machine-readable form.

`docs/v5/O5_PRODUCT_REVIEW.md` is the record a person reads. This is the same
record shaped so the evidence tree can be checked mechanically: every ACCEPTED
claim carries the numbers it rests on, every NOT-YET-ACCEPTED item carries the
gap that keeps it there, and every one of the six O5 failures carries both its
classification and what the corrected instrument said afterwards.

The last part is the point of the round. Classifying an instrument as invalid
is a claim, and a claim of that kind is worth nothing unless the repaired
instrument is then shown reading the same candidate.

Output: qa-v5/optics-o5r/o5-product-review.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
QA = REPO / "qa-v5/optics-o5r"
O5 = REPO / "qa-v5/optics-o5"
O5_HEAD = "c940a3102b466476249d45f632bc9ccdcd1bcb9f"


def load(p):
    return json.loads(p.read_text()) if p.exists() else None


def item(gate, n):
    for i in gate["items"]:
        if i["item"] == n:
            return i
    return None


def rows_for(gate, n, **filt):
    it = item(gate, n) or {}
    out = []
    for r in (it.get("numbers") or {}).get("rows", []) or []:
        if all(r.get(k) == v for k, v in filt.items()):
            out.append(r)
    return out


def main() -> int:
    gate = load(QA / "corrected-product-gate.json")
    sealed = load(O5 / "body-absolute-gate.json")
    regression = load(QA / "original-o5-gate-regression.json")
    grayscale = load(QA / "grayscale-v2.json")
    saturated = load(QA / "saturated-edge-v2.json")
    compression = load(QA / "refraction-compression-v2.json")
    interior = load(QA / "interior-fidelity-v2.json")
    silhouette = load(QA / "silhouette-v2.json")
    portrait = load(QA / "portrait-closure.json")
    if gate is None:
        print("corrected-product-gate.json missing; run o5r-gate.py first")
        return 2

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                          capture_output=True, text=True).stdout.strip()

    def hf_row(doc, asset, vp):
        for r in doc["rows"]:
            if r.get("asset") == asset and r.get("vp") == vp:
                return r
        return None

    accepted = [
        {"claim": "the Target optical body source contract",
         "evidence": "57 sites, 0 failed, every offset seek-verified against "
                     "the live bundle in raw bytes. Absences proved over two "
                     "spans, because an absence claimed in the material "
                     "factory would be vacuous for a geometry claim.",
         "numbers": {"sites": 57, "failed": 0, "seekVerified": True},
         "source": "qa-v5/optics-o5/source-contract.json"},
        {"claim": "the O5 target-source architecture, in full",
         "evidence": "PlaneGeometry(1,1,16,12); vertex-stage sphere dome; "
                     "rounded-rect SDF alpha; analytic bevel normal; own-media "
                     "texture; per-IOR refract; 5/5/3 samples; per-channel "
                     "normalised spectral weights; level-0 sampling; no "
                     "adaptive body shaping; integrated studio reflection; "
                     "white SDF rim; no separate reflection shell; no "
                     "scene-colour pass; quality-step material rebuild.",
         "numbers": {}, "source": "docs/v5/O5_PRODUCT_REVIEW.md"},
        {"claim": "the own-media pipeline",
         "evidence": "proved at runtime, not by a string search: the "
                     "scene-colour pass draws 0 calls and the media plane is "
                     "hidden, yet the cards still show media. Neighbour bleed "
                     "is structurally impossible -- the refracted UV is "
                     "clamped before the cover transform.",
         "numbers": {"sceneColourDrawCalls": 0},
         "source": "qa-v5/optics-o5/compiled-body-audit.json"},
        {"claim": "per-IOR spectral refraction and the analytic normal",
         "evidence": "five refract() calls at high and three at low, tracking "
                     "the sample count; the analytic normal decodes to unit "
                     "length on 95.0% of card pixels. The O4A zero-normal "
                     "defect has no surface: the program declares no shared "
                     "normal varying at all.",
         "numbers": {"unitLengthFraction": 0.950, "pixels": 634495,
                     "perChannelStd": [46.94, 46.12, 46.62]},
         "source": "qa-v5/optics-o5/compiled-body-audit.json"},
        {"claim": "the SDF silhouette MECHANISM, as transcription",
         "evidence": "the mechanism is accepted; the O5 measurement of it was "
                     "not, and is repaired in O5R §八.",
         "numbers": {}, "source": "qa-v5/optics-o5r/silhouette-v2.json"},
        {"claim": "the no-scene-colour architecture",
         "evidence": "52 draw calls in the control, 0 in the candidate; ready "
                     "in 305 ms against 361; CPU frame p99 1.0 ms against 1.4.",
         "numbers": {"controlDrawCalls": 52, "candidateDrawCalls": 0,
                     "readyMsCandidate": 305, "readyMsControl": 361,
                     "cpuP99Candidate": 1.0, "cpuP99Control": 1.4},
         "source": "qa-v5/optics-o5/pipeline.json"},
        {"claim": "control identity, 35 / 35",
         "evidence": "opticalBody=current against a worktree build of 5a87751: "
                     "exactly zero differing pixels across 5 viewports x 7 "
                     "states, every state probe matching, 0 console errors. "
                     "Re-verified in O5R after the one authorised code change.",
         "numbers": (load(QA / "control-identity.json") or {}),
         "source": "qa-v5/optics-o5r/control-identity.json"},
        {"claim": "compiled body audit, 15 / 15",
         "evidence": "with a genuine positive control for the no-mip claim: 20 "
                     "explicit-LOD samples in the control program, 0 in the "
                     "candidate.",
         "numbers": {"controlExplicitLodSamples": 20,
                     "candidateExplicitLodSamples": 0},
         "source": "qa-v5/optics-o5/compiled-body-audit.json"},
        {"claim": "the reflection-band result",
         "evidence": "the band enters the Target's window at every viewport -- "
                     "the measurement O3 and O4 both failed. Re-confirmed by "
                     "the corrected gate's item 1.",
         "numbers": {"rows": rows_for(gate, 1)},
         "source": "qa-v5/optics-o5r/reflection-band.json"},
        {"claim": "the HF spectral-structure result",
         "evidence": "per-tile HF structure correlates 0.9274 with the Target "
                     "against the control's 0.6886. Interior chroma on "
                     "hf-checker: candidate 79.07, Target 79.77, control 0.12.",
         "numbers": {"perTileCorrelationCandidate": 0.9274,
                     "perTileCorrelationControl": 0.6886,
                     "interiorChromaCandidate": 79.07,
                     "interiorChromaTarget": 79.77,
                     "interiorChromaControl": 0.12},
         "source": "qa-v5/optics-o5/body-absolute-gate.json"},
        {"claim": "the pipeline DIRECTION",
         "evidence": "accepted as a direction only. Not accepted as a resource "
                     "verdict; §十二 replaces the five-minute start/end heap "
                     "delta with three fifteen-minute sessions.",
         "numbers": {}, "source": "qa-v5/optics-o5r/pipeline-performance-v2.json"},
    ]

    dl = ((portrait or {}).get("outcome") or {}).get("darkSideLuma", {})
    wr = ((portrait or {}).get("outcome") or {}).get("whiteReflectionRatio", {})
    not_yet = [
        {"item": "the shipped default flip",
         "status": "NOT ACCEPTED", "detail": "opticalBody=current remains "
                                             "shipped. O5R does not flip it."},
        {"item": "390x844 dark-side luma", "status": "OPEN",
         "detail": "still open after the §十 correction.", "numbers": dl},
        {"item": "390x844 white reflection ratio", "status": "OPEN",
         "detail": "still open after the §十 correction.", "numbers": wr},
        {"item": "the O5 absolute-gate verdict as a statement about the "
                 "candidate", "status": "SEALED, NOT RESTATED",
         "detail": "it stands sealed at FAIL 8/14 and is re-run unchanged as a "
                   "regression. Four of its six failures are not readings of "
                   "the candidate.",
         "numbers": {"sealed": (sealed or {}).get("passed"),
                     "total": (sealed or {}).get("total"),
                     "rerunIdentical": (regression or {}).get("identical")}},
        {"item": "Target Visual PASS", "status": "NOT ASSERTED",
         "detail": "not asserted in O5 and not asserted in O5R."},
    ]

    def repaired(n, doc, note, numbers):
        it = item(gate, n) or {}
        return {"o5rItem": n, "o5rStatus": it.get("status"),
                "o5rRowCounts": it.get("rowCounts"),
                "instrument": doc, "whatItSaysNow": note, "numbers": numbers}

    hf_1440 = hf_row(grayscale, "hf-checker", "1440x900") or {}
    hf_lanes = hf_1440.get("lanes") or {}
    bw_1440 = hf_row(grayscale, "bw-split", "1440x900") or {}
    bw_lanes = bw_1440.get("lanes") or {}

    failures = [
        {"o5Item": 2, "name": "dark-side edge luma",
         "kind": "REAL CANDIDATE RESIDUAL",
         "scope": "390x844 only",
         "detail": "inside the window at the other three viewports, and moved "
                   "toward the Target from a control roughly twice as bright "
                   "at every viewport. Portrait mobile is the narrowest card, "
                   "so its bevel occupies the largest fraction of the card.",
         "afterO5R": repaired(2, "carried unchanged, so the two gates stay "
                                 "comparable",
                              "still open; the §十 unclamp moved it by "
                              f"{dl.get('movedByUnclamp')} of a "
                              f"{dl.get('remainingDifference')} gap",
                              dl)},
        {"o5Item": 3, "name": "white reflection ratio",
         "kind": "REAL CANDIDATE RESIDUAL",
         "scope": "390x844 only",
         "detail": "inside the window at the other three viewports.",
         "afterO5R": repaired(3, "carried unchanged",
                              "still open; the §十 unclamp moved it by "
                              f"{wr.get('movedByUnclamp')} of a "
                              f"{wr.get('remainingDifference')} gap",
                              wr)},
        {"o5Item": 4, "name": "grayscale absolute chroma ceiling",
         "kind": "INSTRUMENT UNREADABLE / INVALID",
         "detail": "the coding scored p99.5 chroma against an absolute ceiling "
                   "of 6.0. Candidate 18.0, control 18.0, and the TARGET 30.0 "
                   "-- five times the ceiling. A test the Target fails worse "
                   "than the candidate is not measuring the candidate.",
         "afterO5R": repaired(
             4, "§四 -- seven Target-RELATIVE measurements, feature-local, "
                "with the window set by the Target's own repeatability",
             "the repaired instrument still fails, and now says something: on "
             "coarse achromatic edges the candidate carries about twice the "
             "Target's edge chroma and the shipped body is closer; on "
             "hf-checker the candidate reproduces the Target's edge chroma "
             "that the shipped body misses by a factor of seventy. Same item, "
             "opposite readings, and both are real.",
             {"bwSplit1440": {ln: (v or {}).get("chromaAtGradients")
                              for ln, v in bw_lanes.items()},
              "hfChecker1440": {ln: (v or {}).get("chromaAtGradients")
                                for ln, v in hf_lanes.items()}})},
        {"o5Item": 7, "name": "flat-card edge-compression baseline",
         "kind": "INSTRUMENT UNREADABLE / INVALID",
         "detail": "the analytic baseline assumed the media maps linearly "
                   "across a flat card. The card is a domed plane under "
                   "perspective. The sealed guard refused to answer on most "
                   "cards rather than emit a confident wrong number.",
         "afterO5R": repaired(
             6, "§六 -- a CPU replay of the source refraction formula through "
                "the live card matrix, camera and cover transform, validated "
                "against the Target's own render, with three QA-only "
                "measurement programs supplying the candidate's UV fields",
             "this is the round's substantive instrument result. The replay "
             "reproduces the Target's own displacement field to 1.4-1.6 px, "
             "and the candidate's field enters the Target's window at every "
             "readable viewport.",
             {"rows": rows_for(gate, 6)})},
        {"o5Item": 9, "name": "control-relative interior sharpness",
         "kind": "INSTRUMENT UNREADABLE / INVALID",
         "detail": "the coding asked that the candidate be no blurrier than "
                   "the control. On hf-checker the control is SHARPER than the "
                   "Target, so the candidate failed for being closer.",
         "afterO5R": repaired(
             7, "§七 -- distance(candidate, Target) against distance(control, "
                "Target), with flat-interior assets marked NOT_APPLICABLE when "
                "the Target's own HF energy is below the pre-registered floor",
             "the noise-floor assets are now excluded by name rather than "
             "argued away, and the candidate is closer to the Target than the "
             "control on 45 of 48 readable comparisons. The two rows that "
             "still fail are rgb-micro interior luminance and chroma at the "
             "two mobile viewports.",
             {"rows": [r for r in rows_for(gate, 7)
                       if r.get("status") == "FAIL"]})},
        {"o5Item": 10, "name": "axis-aligned silhouette model",
         "kind": "INSTRUMENT UNREADABLE / INVALID",
         "detail": "the instrument evaluated an axis-aligned rounded-rect SDF "
                   "over the card's screen bounding box. The cards are "
                   "perspective-projected onto a sphere; their quad corners "
                   "sit up to 109 px from the bounding-box corners. Both lanes "
                   "failed it, which is the tell.",
         "afterO5R": repaired(
             9, "§八 -- the sdf-mask program's own coverage: the Target's SDF "
                "rendered through the real PlaneGeometry projection, the real "
                "card matrix and the real fwidth alpha",
             "the projected reference is now right, and the REMAINING limit is "
             "the other half of the measurement: the rendered-alpha side still "
             "needs a background to compare against, and at these packed "
             "layouts the ring outside the card rect lands on neighbouring "
             "cards. See the disclosure in the README; the sealed row stands "
             "as FAIL rather than being relabelled after capture.",
             {"rows": rows_for(gate, 9)})},
    ]

    non_discriminating = [
        {"o5Item": 5, "name": "saturated-edge metric",
         "detail": "Target 0.0, control 0.0, candidate 0.0 on fringeRB, "
                   "fringeWidthPxMean and edgeChroma, for rgb-bars, cool-blue "
                   "and warm-skin alike. Every lane returned the same "
                   "constant. Unreadable, not a pass -- it scored PASS because "
                   "'closer to the Target than the control' is vacuously true "
                   "when all three inputs are zero.",
         "mayBeCitedAsProof": False,
         "afterO5R": repaired(
             5, "§五 -- feature-local: chroma at media gradients, chroma away "
                "from them, fringe localisation, and broad coloured rim area, "
                "with a per-channel gradient mask so a red-to-blue boundary is "
                "still a feature",
             "the metric now discriminates strongly -- on cool-blue the "
             "candidate sits 2.2 from the Target where the shipped body sits "
             "30.3 -- and the item FAILS, mostly on broad coloured rim area. "
             "The shipped body is closer on 46 of 72 readable comparisons "
             "here, which is the one item where that is true.",
             {"rows": [r for r in rows_for(gate, 5)
                       if r.get("status") == "FAIL"][:6]})},
        {"o5Item": 14, "name": "the third fringe sub-check",
         "detail": "colouredGlassFrame_fringeWidthPx read 0.0 for all three "
                   "lanes, so its candidateCloser:true is vacuous. Item 14's "
                   "verdict rests on the two sub-checks that do discriminate.",
         "mayBeCitedAsProof": False,
         "afterO5R": {"o5rItem": None,
                      "instrument": "§三 -- degenerate_reading() is now the "
                                    "single place the rule lives, and every "
                                    "scored row is routed through it",
                      "whatItSaysNow": "a row where every lane returns the "
                                       "same constant is INSTRUMENT_UNREADABLE "
                                       "by construction and cannot reach PASS."}},
    ]

    doc = {
        "what": "§二 -- the O5 product review, machine-readable. The prose "
                "record is docs/v5/O5_PRODUCT_REVIEW.md; this carries the same "
                "decisions with the numbers attached and, for each of the six "
                "failures, what the repaired instrument said afterwards.",
        "reviewedAt": O5_HEAD,
        "o5rHead": head,
        "sealedO5Gate": {
            "verdict": (sealed or {}).get("absoluteGate"),
            "passed": (sealed or {}).get("passed"),
            "total": (sealed or {}).get("total"),
            "rewritten": False,
            "rerunIdentical": (regression or {}).get("identical"),
            "note": "not rewritten and not overwritten. Re-run unchanged in "
                    "§十三A as a regression.",
        },
        "accepted": accepted,
        "notYetAccepted": not_yet,
        "sixFailuresClassified": failures,
        "passesThatCarryNoSignal": non_discriminating,
        "o5rAuthorisation": {
            "mayModify": ["the O5 optical measurement instruments",
                          "envSampleCeiling = 16, the one known non-source "
                          "Target-body deviation",
                          "QA-only structural controls",
                          "evidence and product status"],
            "mayNotModify": ["Target source constants", "ior", "dispersion",
                             "sample count", "refractStrength", "bevelWidth",
                             "bevelPower", "bevelMaxSlope", "thickness",
                             "corner radius", "fresnelF0", "envIntensity",
                             "envMaxMix", "env rotation", "rimWidth",
                             "rimIntensity", "the HDR asset", "layout",
                             "typography", "motion", "label culling",
                             "render coverage verdict", "media focus/crop",
                             "camera", "adaptive quality policy"],
            "didNotDo": ["flip the shipped default", "tune a source constant",
                         "create a second candidate variant",
                         "rewrite the sealed O5 evidence",
                         "enter Performance Final", "merge main",
                         "assert Target Visual PASS"],
        },
    }
    QA.mkdir(parents=True, exist_ok=True)
    (QA / "o5-product-review.json").write_text(json.dumps(doc, indent=1))
    print(f"accepted {len(accepted)}, not-yet-accepted {len(not_yet)}, "
          f"failures classified {len(failures)}, non-discriminating passes "
          f"{len(non_discriminating)}")
    print(f"-> {QA}/o5-product-review.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
