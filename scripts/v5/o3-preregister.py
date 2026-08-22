#!/usr/bin/env python3
"""Seal the O3 pre-registration.

Everything a later commit is allowed to measure against: the candidate
system in full, the lane switch, the 20 absolute-gate items with their
thresholds already INSTANTIATED from the §八 Target repeatability
baseline, the comparison basis for every "not worse than O2" item, the
instrument codings, and the rule that decides the shipped default.

This runs in the SOURCE / PRE-REGISTRATION commit, before the candidate
code exists. Nothing in the emitted document may be edited afterwards.

Usage: o3-preregister.py --repeatability=<json> --source=<json>
                         --instrument-tests=<json> --out=<json>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def head() -> str:
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


CANDIDATE_SYSTEM = {
    "name": "Target Analytic Bevel Reflection Support",
    "module": "src/materials/TargetBevelFieldV4.ts",
    "problemItAnswers":
        "O2's reflection LAW is the Target's and is frozen. The FIELD it is "
        "evaluated on is ours: a baked geometry shoulder normal and a "
        "38px-at-reference strongLensRim attribute. That field spreads the "
        "white reflection over 15.3 px where the Target spreads it over 3.3 "
        "px. O3 replaces the field, not the law.",
    "inputs": ["card uv", "planeWidth / planeHeight (per-frame uniform)",
               "sphereRadius (per-frame uniform)", "cardScale (per-frame)",
               "the Target source constants from "
               "qa-v5/optics-o3/target-bevel-reflection-source.json"],
    "uniformLaws": {
        "cornerRadius": "0.163 * planeWidth",
        "bevelWidth": "0.192 * planeWidth",
        "bevelPower": "3.9 (constant)",
        "bevelMaxSlope": "1.74 (constant)",
        "thickness": "155 * cardScale",
        "rimWidth": "10 * cardScale",
        "sphereRadius": "layout frame sphereRadius",
        "note": "identical to the Target's per-frame writes at bundle byte "
                "1978215; nothing here is fitted.",
    },
    "field": [
        "p = (uv - 0.5) * planeSize                                  [plane px]",
        "halfExtent = planeSize * 0.5",
        "radius = min(cornerRadius, min(halfExtent.x, halfExtent.y))",
        "q = abs(p) - halfExtent + radius",
        "sdf = length(max(q, 0)) + min(max(q.x, q.y), 0) - radius",
        "P = max(bevelPower, 1)",
        "t(s) = clamp(1 + s / max(bevelWidth, 0.001), 0, 1)",
        "T(s) = pow(max(1 - pow(t(s), P), 0), 1/P) * thickness",
        "eps = max(bevelWidth * 0.06, 0.35)",
        "grad = vec2(T(sdf(p+(eps,0))) - T(sdf(p-(eps,0))),"
        " T(sdf(p+(0,eps))) - T(sdf(p-(0,eps)))) / (2*eps)",
        "slope = length(grad)",
        "g = grad * min(slope, bevelMaxSlope) / max(slope, 1e-4)",
        "m = p / sqrt(max(sphereRadius^2 - dot(p,p), 1))",
        "Nplane = normalize(vec3(m - g, 1)) * faceDirection",
        "analyticBevelNormalView = "
        "normalize(modelWorldMatrix * vec4(Nplane, 0)) -> view space",
        "targetRimMask = smoothstep(-rimWidth, 0, sdf)",
        "bevelSupportMask = clamp(slope / bevelMaxSlope, 0, 1)",
    ],
    "normalMappingProof":
        "The Target's plane-space -> world bridge is "
        "normalize(modelWorldMatrix * vec4(v.xy / planeSize, v.z, 0)); its "
        "mesh scale is (planeWidth, planeHeight, 1), so the division cancels "
        "the scale and the bridge is the card's pure ROTATION. Our "
        "sourceExact card mesh carries a UNIFORM cardScale, so "
        "normalize(modelWorldMatrix * vec4(Nplane, 0)) cancels identically "
        "and is the same rotation. dot products are therefore equal in "
        "plane, world and view space, and the fresnel may be evaluated "
        "against positionViewDirection exactly as O2 does.",
    "sourceFormulaProfile": {
        "what": "The source formula evaluated numerically at 1440x900 "
                "BEFORE any shader was written -- verification that the "
                "implementation target is understood, not a fit. Every "
                "constant is the byte-anchored one; nothing was chosen "
                "from a measured result.",
        "constants": {"cornerRadius": 89.19, "bevelWidth": 105.06,
                      "thickness": 129.17, "rimWidth": 8.333,
                      "gradientEpsilon": 6.304, "sphereRadius": 4166.67},
        "profileInwardFromTheEdge": [
            "x=0px    slope 6.90 -> clamped 1.74, tilt 61.0deg, envMix 0.154, rim 1.000",
            "x=4px    slope 7.72 -> clamped 1.74, tilt 61.0deg, envMix 0.154, rim 0.530",
            "x=8px    slope 3.26 -> clamped 1.74, tilt 61.0deg, envMix 0.154, rim 0.005",
            "x=16px   slope 1.39 (unclamped),     tilt 55.5deg, envMix 0.115, rim 0",
            "x=24px   slope 0.83,                 tilt 41.8deg, envMix 0.089, rim 0",
            "x=60px   slope 0.11,                 tilt  9.2deg, envMix 0.087, rim 0",
            "x=105px+ slope 0 (flat interior),    tilt  2.3deg, envMix 0.087, rim 0",
        ],
        "whatItSettles":
            "Two things decide the Target's narrow band. (1) The slope clamp "
            "binds out to ~14 px, so the bevel normal -- and therefore the "
            "reflected direction and the fresnel -- is CONSTANT across the "
            "outer band rather than sweeping; envMix only ranges 0.087 "
            "(flat interior) to 0.154 (clamped bevel). (2) The rim is an "
            "8.3 px smoothstep that has fallen to 0.005 by 8 px inward. The "
            "measured 3.3 px reflection band is dominated by the RIM MASK, "
            "not by the fresnel. Our O2 rim rides strongLensRim at "
            "lensRimWidthPx 38 (31.7 px at this cardScale), which is why the "
            "O2 band measures 15.3 px. This is the single largest lever in "
            "O3, and it is exactly the swap §五 mandates.",
    },
    "bevelSupportMaskUse":
        "QA AND DEBUG ONLY. bevelSupportMask is emitted for the §十 "
        "Rim Mask / Analytic Normal debug stills and is never multiplied "
        "into any product term. A gate may read it; the beauty path may not.",
    "consumedBy": [
        "System B Schlick fresnel -- dot(analyticBevelNormalView, positionViewDirection)",
        "System B environment reflection direction -- "
        "reflect(-positionViewDirection, analyticBevelNormalView)",
        "the Target white rim -- targetRimMask * rimIntensity * rimScale",
    ],
    "mustNotBeConsumedBy": ["refraction", "dispersion", "blur",
                            "geometry position", "alpha / card silhouette",
                            "the scene-colour pipeline", "tone mapping",
                            "adaptive quality", "camera"],
    "frozenAndUnchanged": {
        "fresnelF0": 0.045, "fresnelExponent": 5, "envIntensity": 1.93,
        "envMaxMix": 0.27, "envRotationY": -2, "envRotationX": 0,
        "rimIntensity": 0.11, "envSampleCeiling": 16,
        "envAsset": "public/hdri/studio_small_03_1k.hdr",
        "shellMode(sourceExact beauty)": "off",
        "dispersionLaw(default)": "o1-spectral",
        "note": "no O3 result may be obtained by moving any of these. A "
                "candidate that needs one moved has FAILED.",
    },
}

LANE_SWITCH = {
    "parameter": "reflectionSupport",
    "values": {
        "geometry": "the O2 control -- v_o2NormalView + strongLensRim rim, "
                    "the accepted O2 output",
        "target-sdf": "the O3 candidate -- analytic Target bevel normal + "
                      "Target SDF rim",
    },
    "kind": "BUILD-TIME JavaScript branch, chosen when the material is "
            "created, exactly like dispersionLaw. NOT a shader uniform "
            "branch.",
    "whyBuildTime":
        "A uniform branch would put both paths in one generated shader, "
        "which changes the control lane's compiled program and forfeits the "
        "exact-zero structural proof of gate 1 -- and re-exposes the TSL "
        "first-referencing-branch varying hazard root-caused in O2. With a "
        "JS branch the geometry lane emits the O2 program byte for byte.",
    "override": "?reflectionSupport=geometry|target-sdf",
    "defaultInTheCodeCommit": "geometry",
    "debugViewsRule":
        "the rim-mask and analytic-normal debug views are added ONLY inside "
        "the candidate branch's debug chain; adding them to the shared chain "
        "would change the control program and break gate 1.",
    "byteIdenticalRequirement":
        "every line of System B outside the two swapped inputs is identical "
        "between lanes: same schlick expression, same reflect idiom, same "
        "rotations, same env sample ceiling, same LERP, same rimIntensity.",
}

DEFAULT_FLIP_RULE = {
    "rule": "The shipped default V4_OPTICS_CONFIG.material.reflectionSupport "
            "stays 'geometry' in the code commit. It flips to 'target-sdf' "
            "in the EVIDENCE commit if and only if ALL twenty absolute-gate "
            "items PASS. If any item fails, the default stays 'geometry' and "
            "the final state is 'O3 ANALYTIC BEVEL REFLECTION FAILED "
            "ABSOLUTE GATE'.",
    "noPartialFlip": "there is no per-viewport, per-asset or per-metric "
                     "flip, and no 'flip with a caveat'.",
    "precedent": "the same shape as the O2 dispersionLaw selection: the rule "
                 "is written before the pixels and its execution is a "
                 "recorded fact, not a judgement call.",
}

COMPARISON_BASIS = {
    "notWorseThanO2":
        "Every 'not worse than O2' item is evaluated against the SAME-RUN "
        "reflectionSupport=geometry lane -- same build, same harness, same "
        "frozen media, same capture pass -- and NOT against the sealed O2 "
        "numbers. Gate 1 proves that lane is pixel-identical to e913aa6, so "
        "it IS the O2 measurement, re-measured on the same instrument. This "
        "removes cross-round instrument drift from every comparison.",
    "allowance":
        "where an item permits a candidate to be no worse, the allowance is "
        "the TARGET's own repeatability spread of that same metric on that "
        "same asset, measured in §八 before any candidate existed. It is a "
        "number from Target data, never from candidate data.",
}


def build_gates(rep: dict) -> list:
    thr = rep["thresholds"]
    band = thr["bandWidthThreshold"]["threshold"]
    luma = thr["darkLumaThreshold"]["threshold"]
    white = thr["whiteRatioThreshold"]["threshold"]
    series = rep["series"]

    # "Not worse than O2" needs ONE allowance, fixed now. The Target's own
    # repeatability spread is the natural candidate, but under the
    # deterministic harness it measured exactly 0, and a literal zero would
    # fail the round on a difference smaller than one 8-bit level. So the
    # allowance is the larger of that spread and EDGE_CHROMA_ENVELOPE: the
    # O2 round established a deterministic <= 1/255-per-channel difference
    # between two differently-generated shader programs, and half a level on
    # a 0-255 chroma mean is a conservative statement of it. It is two orders
    # of magnitude below the signal these gates exist to catch (O2's own
    # grayscale chroma moved 11.22 -> 3.56 and its saturated drop was 18.03),
    # so it cannot hide a real regression -- and it is chosen from O2's
    # record, never from an O3 measurement.
    EDGE_CHROMA_ENVELOPE = 0.5

    def edge_chroma_allowance(asset):
        s = series.get(f"{asset}@1440x900", {}).get("spread", {})
        v = s.get("edgeChromaMean") or 0.0
        return round(max(v, EDGE_CHROMA_ENVELOPE), 5)

    gs_allow = edge_chroma_allowance("grayscale-step")
    sat_allow = max(edge_chroma_allowance("rgb-bars"),
                    edge_chroma_allowance("cool-blue"))

    return [
        {"n": 1, "item": "O2 control pixel-identical to e913aa6",
         "measure": "reflectionSupport=geometry, dispersionLaw=o1, shell off, "
                    "deterministic frozen media, vs a worktree build of "
                    "e913aa6a33e384ba4fc80eb28b9a8718fb20e5b9 at the same "
                    "viewport and state",
         "pass": "differingPixels == 0 on every scored viewport",
         "threshold": 0, "kind": "structural, blocking",
         "note": "the geometry lane must emit the O2 shader byte for byte; "
                 "a non-zero here voids every 'not worse than O2' comparison "
                 "below because the control is no longer O2."},
        {"n": 2, "item": "Analytic source contract PASS",
         "measure": "scripts/v5/o3-bevel-source-forensics.py",
         "pass": "pass == true, sitesFailed == 0, live bundle matches"},
        {"n": 3, "item": "bw-split reflection band width vs Target",
         "measure": "S.reflection_band meanPx, bw-split, 1440x900",
         "pass": f"|candidate - target| <= {band}",
         "threshold": band,
         "thresholdOrigin": "§八 max(2 x Target spread, 1.5 px)"},
        {"n": 4, "item": "candidate band materially narrower than O2's 15.3 px",
         "measure": "same metric, candidate vs the same-run geometry lane",
         "pass": "candidate <= 0.5 x control AND (control - candidate) >= 4.0 px",
         "threshold": {"ratio": 0.5, "absolutePx": 4.0},
         "note": "'significantly smaller' pinned to a number BEFORE capture; "
                 "both conditions must hold."},
        {"n": 5, "item": "bw-split dark-side edge luma vs Target",
         "measure": "S.side_bands darkSideEdgeLuma, bw-split, 1440x900",
         "pass": f"|candidate - target| <= {luma}",
         "threshold": luma,
         "thresholdOrigin": "§八 max(2 x Target spread, 10 luma levels)"},
        {"n": 6, "item": "white reflection ratio vs Target",
         "measure": "whiteReflectionRatio, bw-split, 1440x900",
         "pass": f"|candidate - target| <= {white}",
         "threshold": white,
         "thresholdOrigin": "§八 max(2 x worst Target spread, 0.02)"},
        {"n": 7, "item": "dark / bright ratio closer to Target",
         "measure": "S.side_bands darkOverBrightLumaRatio, bw-split, 1440x900",
         "pass": "|candidate - target| < |control - target|",
         "note": "strictly closer; equal is a fail."},
        {"n": 8, "item": "grayscale edge chroma not worse than O2",
         "measure": "edgeChromaMean, grayscale-step, 1440x900",
         "pass": f"candidate <= control + {gs_allow}",
         "threshold": gs_allow,
         "thresholdOrigin": "max(Target repeatability spread of the same "
                            "metric on the same asset, 0.5 = O2's recorded "
                            "deterministic <=1/255-per-channel shader-program "
                            "difference expressed on a 0-255 chroma mean)"},
        {"n": 9, "item": "saturated edge chroma not worse than O2 A+B",
         "measure": "edgeChromaMean on rgb-bars, cool-blue, warm-skin",
         "pass": f"candidate <= control + {sat_allow} on EVERY saturated asset",
         "threshold": sat_allow,
         "thresholdOrigin": "worst of (Target repeatability spread of the "
                            "same metric across the saturated media, 0.5 = "
                            "O2's recorded deterministic shader-program "
                            "difference envelope)"},
        {"n": 10, "item": "no new coloured rim on RGB / cool / warm",
         "measure": "fringeRB and fringeWidthPxMean, candidate vs control",
         "pass": "fringeRB <= control fringeRB + 0.5 AND fringeWidthPxMean "
                 "<= control + 0.5 on each of rgb-bars, cool-blue, warm-skin"},
        {"n": 11, "item": "interior media not globally brightened or desaturated",
         "measure": "o3_instruments.f5_interior_change, control as baseline, "
                    "every scored desktop asset",
         "pass": "fired == false on every asset",
         "coding": "PRE-REGISTERED: baseline interior saturation > 0.01 -> "
                   "relative change vs a 0.12 ceiling; <= 0.01 -> absolute "
                   "change vs 0.02 saturation / 2.0 chroma. Luminance is "
                   "always relative vs 0.12."},
        {"n": 12, "item": "media-only bit-identical",
         "measure": "glass layer hidden, candidate vs control, every captured "
                    "media-only pair",
         "pass": "differingPixels == 0 exactly -- no FMA envelope applies, "
                 "the glass shader is not in the rendered path"},
        {"n": 13, "item": "gutter invasion not increased",
         "measure": "o3_instruments.f10_gutter_ink -- EVERY projected card "
                    "polygon masked (not a bounding box, not only the "
                    "fully-visible twins), dilated by one third of the "
                    "inter-card gap (8 px at 1440x900, 4 px at 390x844); "
                    "the middle third of the gap is what is measured",
         "pass": "candidate <= control + 0.006 on bw-split and rgb-bars",
         "threshold": 0.006,
         "thresholdOrigin":
             "the largest change this instrument attributes to card-edge "
             "brightening in the ALREADY-ACCEPTED O2 System B (+0.0057 on "
             "bw-split, +0.0051 on rgb-bars vs the pre-O2 build, dry run on "
             "the O2 captures), rounded up. Product review established O2 "
             "invades no gutter -- the glass cannot paint outside its own "
             "alpha cutout -- so that magnitude is instrument attribution, "
             "not invasion, and an O3 change larger than it is real.",
         "note": "at this layout the cards nearly tile the frame (gap = 4.5% "
                 "of the card width), so the residual strip is narrow and its "
                 "ABSOLUTE value is not meaningful. The gate is a delta "
                 "against the same-run control, never an absolute."},
        {"n": 14, "item": "pointer reflection path, glass-only metric",
         "measure": "o3_instruments.glass_reflection_masks + f11_judge; "
                    "label / typography ink excluded by construction",
         "pass": "fired == false, and the published record carries exactly "
                 "the path the verdict was computed from",
         "coding":
             "PRE-REGISTERED, branch taken on the TARGET path alone (as F5 "
             "branches on the baseline): if the Target's own path range is "
             ">= 0.05 card widths the candidate must be monotonic in the "
             "Target's direction; if it is < 0.05 the Target's reflection "
             "centroid does not track the pointer materially, and the "
             "candidate must instead not INTRODUCE a swing the Target lacks "
             "-- range <= max(targetRange + 0.05, 0.10). An adjacent jump > "
             "0.4 card widths fires in either branch, and an unmeasurable "
             "state fires.",
         "whyTheBranchExists":
             "the dry run on the O2 captures measured the Target's own "
             "glass-only path at range 0.027 and NON-MONOTONIC. A bare "
             "direction test would have failed this round on the reference, "
             "not on the optics. Found and fixed BEFORE sealing, on Target "
             "and O2 data only.",
         "cardSpace":
             "the label-ink exclusion is computed in CARD space, each "
             "pointer state cropped at its OWN card rect -- the card moves "
             "on screen between pointer states, and a shared screen rect "
             "would misalign the ink and leak it into the glass population.",
         "inkIntersectionStates": ["pl", "rest", "pr", "pbr"],
         "pathStates": ["pl", "rest", "pr"],
         "unitTest": "scripts/v5/o3-instrument-tests.py -- a non-monotonic "
                     "path MUST fire, the branch must be selectable only "
                     "from the target, and the accepted O2 candidate must "
                     "pass"},
        {"n": 15, "item": "desktop / portrait / landscape same direction",
         "measure": "band width and dark-side luma change (candidate - "
                    "control) at 1440x900, 390x844, 844x390",
         "pass": "SAME SIGN on every viewport (the §九.15 requirement, "
                 "literally)",
         "recordedDiagnostic":
             "the per-viewport |candidate - target| is reported against that "
             "viewport's own §八 threshold, as a DIAGNOSTIC and not as a "
             "pass condition. 844x390 has no fully-visible card and rides "
             "the recorded one-card side-bands basis, so an absolute "
             "threshold there would gate a basis limitation the brief never "
             "gated."},
        {"n": 16, "item": "no rim / reflection pop during drag, flick, touch",
         "measure": "per recorded frame, the FULL-FRAME count of bright "
                    "low-chroma pixels (luma > 200, chroma < 40), over each "
                    "recorded sequence",
         "pass": "no adjacent-frame relative change > 40%, and no frame at "
                 "zero while both neighbours are non-zero (a rim break)",
         "whyFullFrame":
             "a per-card measure would need per-frame scroll and pointer "
             "state, which the CDP screencast recordings do not carry; "
             "reading it back post hoc would be exactly the re-interpretation "
             "§七 forbids this round. The full-frame count includes the "
             "static label ink, which is CONSTANT and so cannot create a "
             "discontinuity -- and a pop is a discontinuity."},
        {"n": 17, "item": "v_o2NormalView control regression",
         "measure": "the geometry lane still reads its private varying and "
                    "still produces the O2 pixels",
         "pass": "gate 1 exact zero AND the control program still declares "
                 "v_o2NormalView"},
        {"n": 18, "item": "compiled shader proof",
         "measure": "dump both lanes' generated fragment programs",
         "pass": "control consumes v_o2NormalView in the beauty branch; "
                 "candidate consumes the analytic bevel normal in the beauty "
                 "branch; neither leaks into the other"},
        {"n": 19, "item": "all frozen suites PASS",
         "measure": "Source Contract 36/36, Layout Source 14/14, Typography "
                    "4/4, Motion Freeze, Release History, Card/Label Motion "
                    "34/34, V0 Label Culling Gate, V1 Render Culling Gate, "
                    "O2 Shared-media Harness, O2 Media-only Controls, A+B "
                    "Dispersion Selection, Wrap = 0, Touch/Pointer Cancel, "
                    "Console/Page Errors = 0, TypeScript, Vite Build",
         "pass": "every suite PASS"},
        {"n": 20, "item": "full frame no longer reads as a wide white plastic frame",
         "measure": "JUDGED on named recorded full frames, Target vs O2 "
                    "control vs O3 candidate, at 100% -- no 2x ROI",
         "pass": "stated plainly in the evidence, with the frames named; "
                 "'the numbers moved' is not a pass",
         "registeredFailureText":
             "the candidate full frame still reads as a wide white plastic "
             "frame around the card, or its corners still read as thick "
             "plastic, when compared with the Target's same-media frame "
             "without zooming"},
    ]


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:])
    rep = json.loads(Path(args["repeatability"]).read_text())
    src = json.loads(Path(args["source"]).read_text())
    tests = json.loads(Path(args["instrument-tests"]).read_text())

    if not src["pass"]:
        print("source contract does not pass -- refusing to seal", file=sys.stderr)
        return 1
    if not tests["pass"]:
        print("instrument unit tests do not pass -- refusing to seal",
              file=sys.stderr)
        return 1

    doc = {
        "what": "O3 pre-registration -- sealed in the source / "
                "pre-registration commit, BEFORE any candidate code or "
                "candidate pixel exists.",
        "sealedAtHead": head(),
        "sealedAtHeadNote":
            "the HEAD this document was generated ON TOP OF. The commit that "
            "carries it is its child -- a document cannot name its own SHA.",
        "round": "O3 -- Target Analytic Bevel Reflection Support",
        "authorisedScope":
            "the System B reflection SUPPORT FIELD only: the fresnel / "
            "reflection normal and the white rim mask. Everything in "
            "docs/v5/O2_OPTICS_FREEZE_CONTRACT.md's frozen list stays frozen, "
            "and O3 may not reach a result by moving any of it.",
        "sourceContract": {
            "file": "qa-v5/optics-o3/target-bevel-reflection-source.json",
            "sites": src["sitesTotal"], "failed": src["sitesFailed"],
            "bundleSha256": src["bundle"]["sha256"],
            "notFitted": src["notFitted"],
        },
        "candidateSystem": CANDIDATE_SYSTEM,
        "laneSwitch": LANE_SWITCH,
        "repeatability": {
            "file": "qa-v5/optics-o3/target-repeatability.json",
            "repeats": rep["repeats"],
            "spreadDefinition": rep["spreadDefinition"],
            "thresholds": {k: v["threshold"] for k, v in
                           rep["thresholds"].items()},
        },
        "comparisonBasis": COMPARISON_BASIS,
        "instrumentCorrections": {
            "module": "scripts/v5/o3_instruments.py",
            "unitTests": "scripts/v5/o3-instrument-tests.py",
            "unitTestsPassing": f"{tests['total'] - tests['failed']}/"
                                f"{tests['total']}",
            "F5": "branch on the BASELINE: > 0.01 relative, <= 0.01 absolute. "
                  "Fixed before capture, never re-chosen after.",
            "F10": "mask every projected card POLYGON (not a bounding box, "
                   "not only the fully-visible twins); measure only the "
                   "strict between-card region.",
            "F11": "glass reflection only -- the pointer-invariant bright "
                   "low-chroma population (label / typography ink) is "
                   "excluded by construction. ONE coding, and the published "
                   "record carries the same path the verdict used: a "
                   "non-monotonic path with fired=false is impossible by "
                   "construction and is asserted so by unit test.",
            "validatedOn":
                "qa-v5/optics-o3/instrument-dryrun.json -- the corrected F5, "
                "F10 and F11 run against the EXISTING O2 captures (Target "
                "and both O2 lanes, no O3 candidate exists). All three score "
                "the already-accepted O2 candidate as PASS, which is the "
                "property a corrected instrument must have: it may not "
                "retroactively condemn accepted product. Two codings were "
                "FIXED as a result of that dry run, before sealing -- F11's "
                "flat-reference branch and F10's dilation law -- and both "
                "fixes are recorded on their gate items.",
            "noPostCaptureAlternateCoding":
                "this round may NOT repeat O2's adjudication pattern. If a "
                "registered coding fires, it fires.",
        },
        "absoluteGate": build_gates(rep),
        "defaultFlipRule": DEFAULT_FLIP_RULE,
        "finalStates": ["READY FOR O3 OPTICS PRODUCT REVIEW",
                        "O3 ANALYTIC BEVEL REFLECTION FAILED ABSOLUTE GATE"],
        "prohibited": [
            "auto-entering own-media refraction",
            "modifying tone mapping", "modifying dispersion",
            "lowering envIntensity or envMaxMix",
            "modifying geometry",
            "modifying layout / typography / motion / culling",
            "asserting Target Visual PASS", "merging main",
            "editing any threshold or parameter after the candidate is captured",
        ],
    }
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    print(f"{out}: sealed at {doc['sealedAtHead'][:12]}, "
          f"{len(doc['absoluteGate'])} gate items")
    for g in doc["absoluteGate"]:
        if "threshold" in g:
            print(f"  {g['n']:2d}. {g['item'][:52]:52s} thr={g['threshold']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
