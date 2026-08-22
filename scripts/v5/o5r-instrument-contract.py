#!/usr/bin/env python3
"""§三 -- the O5R instrument contract.

Generated from the instrument module itself so a constant cannot be changed in
one place and described in the other. Every threshold the corrected gate binds
to is listed here with the reasoning that fixed it, and every instrument
declares its six required tests and its UNREADABLE conditions.

Output: qa-v5/optics-o5r/instrument-contract.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I = _load("o5r_c_ins", "o5r_instruments.py")
F = _load("o5r_c_ref", "o5r_refraction.py")

OUT = REPO / "qa-v5/optics-o5r/instrument-contract.json"

LAWS = [
    {
        "law": "DEGENERACY IS NEVER A PASS",
        "statement": "No row may report PASS when every compared lane produces "
                     "the same zero or constant value.",
        "why": "O5 item 5 returned 0.0 for Target, control and candidate on "
               "rgb-bars, cool-blue and warm-skin alike, and its sealed "
               "comparison -- closer to the Target than the control, no "
               "broader than either -- was vacuously true on three zeros. Item "
               "14's fringe sub-check did the same. A pass that measures "
               "nothing is a worse liability than a failure that measures "
               "something.",
        "implementedBy": "o5r_instruments.degenerate_reading, called on every "
                         "scored row in the corrected gate",
    },
    {
        "law": "UNREADABLE IS NEVER A FAIL",
        "statement": "An instrument that cannot answer returns "
                     "INSTRUMENT_UNREADABLE. It is not converted to FAIL, and "
                     "not converted to PASS.",
        "why": "Four of O5's six failures were the instrument, not the "
               "candidate, and they were reported as candidate failures "
               "because the codings had no way to say otherwise.",
        "implementedBy": "o5r_instruments.Unreadable, raised rather than "
                         "caught into a verdict",
    },
    {
        "law": "NOT APPLICABLE IS NEITHER",
        "statement": "An asset that cannot carry a measurand is marked "
                     "NOT_APPLICABLE before it is scored.",
        "why": "O5 item 9 let bw-split and rgb-bars -- whose interiors are "
               "flat, and whose sharpness therefore reads 1.2 to 5.7 on a "
               "scale where the textured asset reads 150 -- contribute "
               "0.2-unit differences to a product verdict.",
        "implementedBy": "o5r_instruments.sharpness_applicable, against "
                         "HF_SIGNAL_FLOOR",
    },
    {
        "law": "WINDOWS COME FROM TARGET REPEATABILITY",
        "statement": "Every two-sided window is max(2 x Target repeatability, "
                     "a floor pre-registered here). Repeatability is measured "
                     "from Target captures taken BEFORE any O5R candidate "
                     "frame exists.",
        "why": "Carried from O5 unchanged. A window derived after seeing the "
               "candidate is not a window, it is a fit.",
        "implementedBy": "o5r_instruments.window",
    },
    {
        "law": "NO CONSTANT IS FITTED AGAINST CANDIDATE PIXELS",
        "statement": "Every threshold in this contract is fixed before the "
                     "O5R candidate lane is captured, and none is derived "
                     "from a candidate render.",
        "why": "The O5R candidate is opticalBody=target-source-unclamped. "
               "This contract is committed before it is captured.",
        "implementedBy": "commit order: v5-o5r-instrument-contract precedes "
                         "v5-o5r-source-environment-code and the post-phase "
                         "capture",
    },
]

SEALING = {
    "sealedAt": "the v5-o5r-instrument-contract commit",
    "sealedAgainst": "any capture of opticalBody=target-source-unclamped",
    "amendmentRule": "The QA measurement programs (uv-unrefracted, "
                     "uv-refracted, refraction-displacement, sdf-mask) land in "
                     "the NEXT commit, so a self-test that depends on them can "
                     "only complete after it. A self-test failure discovered "
                     "then may be repaired and re-recorded ONLY until the "
                     "first O5R candidate capture. After that first capture, a "
                     "broken instrument reports INSTRUMENT_UNREADABLE and is "
                     "not edited -- that is exactly the discipline O5's item 4, "
                     "7, 9 and 10 were scored under, and it is why those four "
                     "were reported as written rather than quietly fixed.",
    "preSealRenders": {
        "what": "artifacts/optics-o5r/smoke/*.png",
        "disclosure": "The structural smoke run booted every lane, including "
                      "target-source-unclamped, on the PRODUCT clips before "
                      "this contract was committed. Those frames prove the "
                      "lanes start, report the right program state and raise "
                      "no console errors. No scored row reads them, they are "
                      "not on the deterministic shared media, and no threshold "
                      "here was chosen after looking at them.",
    },
}


def instruments():
    return [
        {
            "id": "grayscale_v2",
            "section": "§四",
            "replaces": "O5 item 4 -- p99.5 chroma against an ABSOLUTE ceiling "
                        "of 6.0, which the Target fails at 30.0, the control "
                        "at 18.0 and the candidate at 18.0. A test the Target "
                        "fails worse than the candidate is not measuring the "
                        "candidate.",
            "measures": [
                "mean chroma distance to Target",
                "p95 chroma distance to Target",
                "p99.5 chroma distance to Target",
                "chroma at high-luminance gradients",
                "chroma away from luminance gradients",
                "false-colour connected-component area",
                "false-colour distance from actual media features",
            ],
            "law": "The candidate is scored against the TARGET, not against an "
                   "ideal zero-chroma image. Colour localised to encoded sharp "
                   "edges is allowed where the Target carries it -- 4:2:0 "
                   "chroma subsampling puts colour on every sharp luminance "
                   "step, which is why the Target reads 30. Colour away from "
                   "Target and media features is a failure.",
            "assets": ["grayscale-step", "bw-split", "hf-checker"],
            "featureMask": "luminance gradient only. Using a colour gradient "
                           "here would let false colour define its own excuse.",
            "constants": {
                "FEATURE_GRADIENT_THRESHOLD": I.FEATURE_GRADIENT_THRESHOLD,
                "FALSE_COLOUR_CHROMA": I.FALSE_COLOUR_CHROMA,
                "FALSE_COLOUR_MIN_BLOB_FRACTION": I.FALSE_COLOUR_MIN_BLOB_FRACTION,
                "CHROMA_DISTANCE_WINDOW_FLOOR": I.CHROMA_DISTANCE_WINDOW_FLOOR,
                "FALSE_COLOUR_AREA_WINDOW_FLOOR": I.FALSE_COLOUR_AREA_WINDOW_FLOOR,
            },
            "unreadableWhen": [
                "no card rects were derived for the viewport",
                "every card rect is degenerate in size",
                "all three lanes return the same value on the scored statistic",
            ],
            "targetMustPassItsOwnWindow": True,
        },
        {
            "id": "saturated_edge_v2",
            "section": "§五",
            "replaces": "O5 item 5 -- fringeRB, fringeWidthPxMean and "
                        "edgeChroma all returned 0.0 for Target, control and "
                        "candidate on every saturated asset, and the sealed "
                        "comparison passed vacuously.",
            "measures": [
                "chroma at texture features",
                "chroma away from texture features",
                "fringe localisation (the ratio of the two)",
                "false broad coloured rim area, inside the rim band",
            ],
            "masks": [
                "media gradient mask -- PER CHANNEL and maximised over R/G/B, "
                "not a chroma scalar: max-minus-min is a saturation measure, "
                "so a red-to-blue boundary (the canonical saturated edge) has "
                "a chroma gradient of exactly zero",
                "card SDF edge mask, from the Target's own rounded-rect SDF",
                "inside-rim distance, banded at the Target's own bevelWidth "
                "ratio so 'broad coloured rim' is asked of the region a rim "
                "actually occupies",
            ],
            "assets": ["rgb-bars", "cool-blue", "warm-skin"],
            "constants": {
                "FEATURE_GRADIENT_THRESHOLD": I.FEATURE_GRADIENT_THRESHOLD,
                "RIM_BAND_FRACTION": I.RIM_BAND_FRACTION,
                "BROAD_RIM_CHROMA": I.BROAD_RIM_CHROMA,
            },
            "unreadableWhen": [
                "the asset has no feature population, or no non-feature "
                "population -- the exact situation O5 answered with 0.0",
                "all three lanes return the same value",
            ],
            "requiredFixtures": [
                "a synthetic broad cyan/magenta frame must FAIL",
                "colour that follows the media texture must PASS",
            ],
        },
        {
            "id": "refraction_compression_v2",
            "section": "§六",
            "replaces": "O5 item 7 -- an analytic FLAT-card baseline for a "
                        "domed plane under perspective. Its guard correctly "
                        "refused to answer on most cards; what it protected "
                        "against was the model.",
            "candidateMethod": [
                "read the unrefracted UV from the uv-unrefracted program",
                "read the refracted UV from the uv-refracted program",
                "read the base-ior displacement directly from the "
                "refraction-displacement program",
                "compute the displacement in card-media coordinates, with no "
                "flat-plane assumption anywhere",
            ],
            "targetMethod": [
                "replay the source refraction formula from the LIVE layout "
                "frame, card matrix, plane size, analytic normal, "
                "coverScale/coverOffset and per-IOR contract",
                "FORWARD-MAP every card fragment into source-image space, so "
                "the prediction is the disc's IMAGE -- including the smearing "
                "refraction produces near the bevel -- and not the refracted "
                "position of its centre",
                "validate the replay against deterministic calibration media: "
                "the Target's own render must sit on the replayed formula",
            ],
            "programs": ["uv-unrefracted", "uv-refracted",
                         "refraction-displacement"],
            "programsAreSeparate": "each is a separate PROGRAM built at "
                                   "material construction, never a debug "
                                   "branch inside Beauty -- the O4A codegen "
                                   "finding is why",
            "calibrationAsset": "calib-landmarks: ten bright discs on a "
                                "mid-grey ground, four radii, irregular "
                                "positions, no mirror symmetry in either axis",
            "scoredLandmarkSet": {
                "rule": f"discs with source ny <= {F.SCORED_DISC_MAX_NY}",
                "why": "the card's upper half. The Target draws its headline "
                       "across the lower half and has no QA surface to switch "
                       "it off; a white glyph is not distinguishable from a "
                       "white disc by luminance, and pretending otherwise "
                       "would put the label layer into an optical measurement.",
            },
            "cardValidation": {
                "rule": f"a card is scored only when the replayed source "
                        f"formula lands on the TARGET'S own render to within "
                        f"{F.REPLAY_VALIDATION_MAX_PX} px",
                "decidedFrom": "Target pixels alone, and applied identically "
                               "to every lane",
                "excludedSlots": f"clipIndex == {F.EXCLUDED_CLIP_INDEX} -- our "
                                 f"frozen product crop (focusY 0.46, zoom "
                                 f"1.06), which the Target does not apply. The "
                                 f"sealed O2 harness excludes these slots from "
                                 f"cross-page comparison for the same reason; "
                                 f"scoring them would report a frozen product "
                                 f"decision as an optical difference. On clips "
                                 f"0 and 1 the two cover laws agree exactly "
                                 f"for a 4:3 source on a 4:3 plane.",
            },
            "constants": {
                "REPLAY_VALIDATION_MAX_PX": F.REPLAY_VALIDATION_MAX_PX,
                "EXCLUDED_CLIP_INDEX": F.EXCLUDED_CLIP_INDEX,
                "SCORED_DISC_MAX_NY": F.SCORED_DISC_MAX_NY,
                "DISPLACEMENT_GAIN": I.DISPLACEMENT_GAIN,
                "LANDMARK_MIN_AREA_FRACTION": I.LANDMARK_MIN_AREA_FRACTION,
                "LANDMARK_MAX_AREA_FRACTION": I.LANDMARK_MAX_AREA_FRACTION,
                "LANDMARK_MIN_MATCHES": I.LANDMARK_MIN_MATCHES,
                "LANDMARK_REGION": list(I.LANDMARK_REGION),
                "DISC_WINDOW_MARGIN_PX": I.DISC_WINDOW_MARGIN_PX,
                "DISC_AREA_RATIO_RANGE": list(I.DISC_AREA_RATIO_RANGE),
                "COMPRESSION_WINDOW_FLOOR_PX": I.COMPRESSION_WINDOW_FLOOR_PX,
            },
            "unreadableWhen": [
                "fewer than LANDMARK_MIN_MATCHES discs can be measured on a "
                "card",
                "two predicted windows overlap, so the two centroids would "
                "share pixels",
                "the measured bright area is outside DISC_AREA_RATIO_RANGE x "
                "the predicted fragment count -- the window caught a glyph, "
                "the rim or a neighbour rather than the disc",
                "the card has no usable luminance contrast",
                "either the Target or the Candidate baseline cannot be "
                "verified -- §六 says status = INSTRUMENT_UNREADABLE, not FAIL",
            ],
        },
        {
            "id": "interior_fidelity_v2",
            "section": "§七",
            "replaces": "O5 item 9 -- 'candidate no blurrier than control', "
                        "where the control is SHARPER than the Target. On "
                        "hf-checker the Target reads 149.55, the control "
                        "183.34 and the candidate 153.68: the candidate failed "
                        "the item for being closer to the Target.",
            "question": "distance(candidate, Target) vs distance(control, "
                        "Target)",
            "measures": ["luma HF energy", "chroma HF energy", "local contrast",
                         "per-tile correlation", "media landmark position",
                         "cover scale / offset", "interior luminance",
                         "interior chroma"],
            "primaryAssets": ["hf-checker", "rgb-micro", "detail-chart"],
            "notApplicableAssets": {
                "rule": f"Target interior HF energy < {I.HF_SIGNAL_FLOOR}",
                "expected": ["bw-split", "grayscale-step",
                             "rgb-bars flat interiors"],
                "why": "O5's own numbers bracket the floor cleanly: bw-split "
                       "4.80, rgb-bars 5.68, hf-checker 149.55. A 0.2 "
                       "difference between numbers near a 1-5 noise floor may "
                       "not decide a product.",
            },
            "constants": {
                "HF_SIGNAL_FLOOR": I.HF_SIGNAL_FLOOR,
                "TILE_PX": I.TILE_PX,
                "HF_DISTANCE_WINDOW_FLOOR": I.HF_DISTANCE_WINDOW_FLOOR,
                "insetFraction": 0.225,
            },
            "insetNote": "O4's sealed inset to the card's middle 55%, carried "
                         "unchanged so the HF number means the same thing "
                         "across three rounds.",
            "unreadableWhen": [
                "no usable card interior after the inset",
                "all three lanes return the same value",
            ],
        },
        {
            "id": "silhouette_v2",
            "section": "§八",
            "replaces": "O5 item 10 -- an axis-aligned rounded rect evaluated "
                        "over a screen-space bounding box whose corners sit up "
                        "to 109 px from the real projected quad. Both lanes "
                        "failed it, which is the tell.",
            "candidateMethod": [
                "use the separate sdf-mask program",
                "which renders through the actual PlaneGeometry projection and "
                "the actual card matrix, including the dome",
                "and the actual fwidth alpha edge",
                "so its coverage IS the expected projected alpha coverage",
            ],
            "targetMethod": "the same projected silhouette: the Target's SDF "
                            "and positionNode are the ones transcribed in the "
                            "source contract, replayed through the live card "
                            "matrix and camera, which our frozen frame "
                            "reproduces exactly (o5-architecture.json, "
                            "layoutReproducesL6)",
            "compares": ["rendered alpha edge", "replayed projected alpha edge",
                         "corner radius", "antialias width",
                         "lit pixels beyond the source SDF",
                         "gutter beyond the actual projected silhouette"],
            "constants": {
                "SILHOUETTE_AA_PX": I.SILHOUETTE_AA_PX,
                "SILHOUETTE_LIT_DELTA": I.SILHOUETTE_LIT_DELTA,
                "SILHOUETTE_EDGE_WINDOW_FLOOR_PX":
                    I.SILHOUETTE_EDGE_WINDOW_FLOOR_PX,
            },
            "requiredFixtures": [
                "a synthetically perfect target-source card must PASS",
                "the accepted current body and a square-card negative control "
                "must be distinguishable",
            ],
            "unreadableWhen": [
                "no background can be sampled outside the card rect",
                "the rendered and projected masks have different shapes",
                "no sdf-mask program capture exists for the lane",
            ],
        },
        {
            "id": "target_replay",
            "section": "§六 / §八",
            "purpose": "the CPU port of the Target's geometry and refraction, "
                       "used wherever a Target-side prediction is needed and "
                       "the Target has no QA surface to read one out of",
            "legitimacy": [
                "validated against the GPU: the candidate's "
                "refraction-displacement program computes the same quantity, "
                "and a disagreement is a defect in the port",
                "driven by the ENGINE'S matrices, not a second model of the "
                "layout, whose disagreements with the engine would be "
                "indistinguishable from optical differences",
                "validated against the TARGET'S own render on deterministic "
                "calibration media",
            ],
            "constants": {"SOURCE_WH": list(F.SOURCE_WH)},
            "unreadableWhen": [
                "a landmark falls outside the cover crop -- reported outside, "
                "never clamped to an edge and measured anyway",
                "too few unsaturated samples to compare against the GPU",
            ],
        },
    ]


def main() -> int:
    tests_path = REPO / "qa-v5/optics-o5r/instrument-tests.json"
    tests = json.loads(tests_path.read_text()) if tests_path.exists() else None
    doc = {
        "what": "O5R §三 instrument contract. Every corrected instrument, its "
                "pre-registered constants, the fault it repairs, and the six "
                "tests §三 requires of it.",
        "round": "O5R -- corrected instruments and source environment",
        "sealing": SEALING,
        "laws": LAWS,
        "requiredTestKinds": [
            "positive unit test", "negative unit test", "Target self-test",
            "Control self-test", "Candidate-readable test",
            "explicit UNREADABLE state",
        ],
        "instruments": instruments(),
        "globalConstants": {
            "BAND_WINDOW_FLOOR_PX": I.BAND_WINDOW_FLOOR_PX,
            "DARK_LUMA_WINDOW_FLOOR": I.DARK_LUMA_WINDOW_FLOOR,
            "WHITE_RATIO_WINDOW_FLOOR": I.WHITE_RATIO_WINDOW_FLOOR,
            "HEAP_SLOPE_FLOOR_MB_PER_MIN": I.HEAP_SLOPE_FLOOR_MB_PER_MIN,
        },
        "carriedFromO5Unchanged": {
            "why": "the corrected gate shares rows with the sealed one -- "
                   "reflection band, dark-side luma, white reflection ratio -- "
                   "and those rows have to stay comparable across the two "
                   "gates. Their instruments and window floors are taken from "
                   "o5_instruments.py, which O5R does not edit at all.",
            "instruments": ["band_width_px", "dark_side_luma",
                            "white_reflection_ratio", "glass_reflection_masks",
                            "pointer_judge", "hf_energy", "spectral_structure"],
        },
        "testsFile": str(tests_path.relative_to(REPO)),
        "testsPassed": (tests or {}).get("passed"),
        "testsTotal": (tests or {}).get("total"),
        "testCoverage": (tests or {}).get("coverage"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"{len(doc['instruments'])} instruments, {len(LAWS)} laws -> {OUT}")
    if tests:
        gaps = {k: [n for n, v in c.items()
                    if n.startswith("has") and not v]
                for k, c in (tests.get("coverage") or {}).items()}
        for k, v in gaps.items():
            if v:
                print(f"  GAP {k}: {', '.join(v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
