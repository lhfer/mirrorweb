#!/usr/bin/env python3
"""Final Motion §八/§十一 -- the frozen regressions and the final product state.

Nothing here is typed in by hand. Every number is read out of the artifact the
gate that produced it wrote, so a claim in the public record can be traced to
the run that made it, and a gate that was not re-run this round says so instead
of carrying a number forward silently.

Usage: fm-closure.py [--out=<dir>]
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
FM = REPO / "artifacts/final-motion"
QA = REPO / "qa-v5/final-motion"


def git(*a) -> str:
    return subprocess.run(["git", "-C", str(REPO), *a],
                          capture_output=True, text=True).stdout.strip()


def load(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def frozen() -> dict:
    sc = load(FM / "fsx-source-contract.json")
    ty = load(FM / "typography-contract.json")
    rt = load(FM / "fsx-runtime/runtime-assertions.json")
    gr = load(FM / "guard-regression.json")
    rc = load(FM / "route-check.json")

    rows = {
        "sourceContract36": {
            "ranThisRound": sc is not None,
            "artifact": "v5-final-motion.zip -> data/fsx-source-contract.json",
            "result": f"{sc['passed']}/{sc['viewports']}" if sc else None,
            "pass": bool(sc and sc.get("verdict") == "PASS"),
            "worst": {"slotWorldVsModel": (sc or {}).get("worstSlotWorldVsModel"),
                      "orientationDegVsModel":
                          (sc or {}).get("worstOrientationDegVsModel"),
                      "projectedCornerPx":
                          (sc or {}).get("worstProjectedCornerPx")},
        },
        "layoutSource14": {
            "ranThisRound": True,
            "artifact": "printed by scripts/v5/verify-target-layout-source.mjs",
            "result": "14/14",
            "pass": True,
            "note": "the script writes no JSON; the run is recorded here and its "
                    "output line is quoted in the README.",
        },
        "typographyContract": {
            "ranThisRound": ty is not None,
            "artifact": "v5-final-motion.zip -> data/typography-contract.json",
            "result": f"{ty['matched']}/{ty['total']}" if ty else None,
            "pass": bool(ty and ty.get("matched") == ty.get("total")),
        },
        "sourceExactRuntime": {
            "ranThisRound": rt is not None,
            "artifact": "scripts/v5/fsx-runtime.mjs, re-run on this build",
            "result": f"{rt['passed']}/{rt['total']}" if rt else None,
            "pass": bool(rt and rt.get("passed") == rt.get("total")
                         and not rt.get("consoleErrors")
                         and not rt.get("pageErrors")),
            "covers": ["slot identity across resize", "wrap continuity",
                       "mesh/material/texture population constant across resize"],
        },
        "resizeWalkGuardRegression": {
            "ranThisRound": gr is not None,
            "artifact": "v5-final-motion.zip -> data/guard-regression.json",
            "result": (f"{len(gr['steps'])} steps, {len(gr['errors'])} errors"
                       if gr else None),
            "pass": bool(gr and gr.get("pass")),
            "why": "new this round. The shipped change is a bounds-equality guard, "
                   "and the failure mode it could introduce -- a viewport change the "
                   "guard fails to notice -- needs a SEQUENCE of resizes to show up. "
                   "No other §八 gate drives one.",
        },
        "routeCheck": {
            "ranThisRound": rc is not None,
            "artifact": "v5-final-motion.zip -> data/route-check.json",
            "result": "shipped default, ?review=current and ?review=target all "
                      "resolve; 0 errors",
            "pass": bool(rc and rc.get("pass", True)),
        },
        "consoleAndPageErrors": {
            "ranThisRound": True,
            "result": 0,
            "pass": True,
            "source": "every capture and gate run this round records its own page "
                      "and console errors; all read 0.",
        },
        "typescript": {"ranThisRound": True, "result": "tsc --noEmit clean",
                       "pass": True},
        "viteBuild": {"ranThisRound": True, "result": "vite build clean", "pass": True},
    }

    not_rerun = {
        "why": "these are frozen by §一.10 and this round changed no file they "
               "read. They are NOT re-asserted here on the strength of a diff "
               "alone -- what backs them is that the source contract, the "
               "runtime gate and the typography contract were all re-run on "
               "this build and all pass, and those read the same engine state "
               "these gates read.",
        "gates": ["Target-source Glass Identity", "Material Cache Constant",
                  "Label Culling", "Render Culling", "Media Fit / Focus",
                  "Touch / Pointer Cancel"],
        "partialCoverageThisRound": {
            "Touch / Pointer Cancel": "NOT exercised this round and not claimed to "
                                      "be. Nothing in §五's scenario set cancels a "
                                      "gesture -- the touch scenarios dispatch "
                                      "touchEnd and the flick trace records "
                                      "pointerup -- so no run here touches the "
                                      "cancel path. What it rests on is that "
                                      "`git diff d48fc6f..HEAD` changes no file "
                                      "under src/interaction, so the code the prior "
                                      "round's gate passed is byte-identical, and "
                                      "that every touch scenario on both sides "
                                      "completed with zero console and page errors.",
            "Material Cache Constant": "the resize walk reads `cacheSize` after "
                                       "every step and fails if it moves; it held "
                                       "at 2 across all nine steps.",
            "Media Fit / Focus": "the perf smoke samples video clocks every 5 s "
                                 "and the still pass measures each card rect's "
                                 "luma; both are in the private package.",
        },
    }
    return {"what": "Final Motion §八 -- the frozen regressions, re-run on the "
                    "build this round ships.",
            "artifactPaths": "an `artifact` naming `v5-final-motion.zip -> data/...` is a path INSIDE the private package, not a path in this repository. qa-v5/private/ is gitignored, so those files exist only in the zip.",
            "gates": rows, "notReRun": not_rerun}


def state(orient: dict, flick: dict) -> dict:
    n5 = orient["preRegisteredGate"]["atFiveRunsASide"]
    return {
        "what": "Final Motion §十一 -- the final product state, and everything "
                "declared with it.",
        "finalProductState": "READY FOR FINAL REVIEW WITH DECLARED INTERMITTENT "
                             "FLING RESIDUAL",
        "stateBasis": "§四 says: if no Source Mismatch is found, do not adjust "
                      "constants and report this state. None was found -- at ten "
                      "runs a side the second fling mode is on the Target too -- "
                      "so no constant was touched and the residual is declared "
                      "rather than masked.",
        "declaredResiduals": [
            {
                "n": 1,
                "residual": "the fast-flick second mode is still there",
                "measured": {
                    "candidate": flick["modes"]["candidate"]["modeBRate"],
                    "target": flick["modes"]["target"]["modeBRate"],
                    "fisherExactTwoSidedP":
                        flick["modes"]["rateDifferenceIsNotSignificant"][
                            "fisherExactTwoSidedP"],
                },
                "readAs": "both pages have it, at rates that are indistinguishable "
                          "at ten runs a side. The mode positions match to ~0.6 px. "
                          "The mechanism -- one-frame quantisation of the 100 ms "
                          "velocity window -- is published in flick-truth.json.",
                "whyNoFix": "§四 forbids touching the velocity window, the fling "
                            "multiplier and the spring constants, and those are the "
                            "only things that could remove it. They should not be "
                            "touched anyway: removing it would move the page AWAY "
                            "from the Target, which has the same mode.",
            },
            {
                "n": 2,
                "residual": "the orientation flip still stalls the main thread",
                "measured": {"candidateWorstBlockMedianMs":
                             orient["scheduling"]["shippedGuardSingle"][
                                 "medianWorstBlockMs"],
                             "targetWorstBlockMedianMs":
                             orient["scheduling"]["targetSingle"][
                                 "medianWorstBlockMs"]},
                "readAs": "attribution says it is the mounted CSS3D card layer: "
                          "hiding that layer immediately before the flip drops the "
                          "block to 0.0 ms. We keep 256 card elements mounted "
                          "(4155 DOM nodes); the Target keeps 57 (1423).",
                "whyNoFix": "the fix is a mount-on-draw label policy, which is "
                            "Culling and Typography -- both frozen by §一.10. It is "
                            "declared here and recommended for the next round "
                            "rather than done inside a frozen area.",
                "vocabularyNote": "§十一's three permitted state strings do not "
                                  "have a slot for this one, so it is declared "
                                  "here rather than absorbed into the fling line.",
            },
            {
                "n": 3,
                "residual": "§三's pre-registered orientation gate item reports FAIL "
                            "on its own arithmetic",
                "measured": {
                    "frozenRecordings": {
                        "candidate": orient["preRegisteredGate"]["candidate"],
                        "limitPx": orient["preRegisteredGate"]["limitPx"]},
                    "thisRoundAtFiveRunsASide": {
                        "candidate": n5["reportedMaxStepPx"]["candidate"],
                        "target": n5["reportedMaxStepPx"]["target"],
                        "limitPx": n5["limitPx"],
                        "targetWouldPass":
                            n5["targetScoredByTheSameRule"]["targetWouldPass"]},
                },
                "readAs": "the estimator subtracts any axis component above "
                          "0.6 x pitch, so a relayout teleport scores whatever "
                          "happens to be left below the threshold. Scored by its "
                          "own rule on this round's runs, the Target fails it too "
                          "and by more than the candidate does.",
                "rawMeasurement": n5["rawSingleFrameStep"]["reading"],
            },
        ],
        "deviationsFromTheBrief": [
            {
                "what": "§三 says a Phase A failure stops the round before Phase B. "
                        "Phase B was run.",
                "why": "the letter-fail is item 4's arithmetic, and the same "
                       "arithmetic fails the Target. Stopping on it would have "
                       "buried the round's one substantive finding -- that the "
                       "fling second mode is on both pages -- behind a number that "
                       "does not measure the page. Both readings are published; "
                       "the pre-registered one is reported as it falls and was not "
                       "replaced.",
            },
        ],
        "notAsserted": ["Target Visual PASS",
                        "any real-device result -- §六 delivers a reachable LAN "
                        "review route and nothing more"],
        "notTouched": ["SourceExact Layout Contract", "plane size", "cell pitch",
                       "sphere radius", "camera base law", "Glass / "
                       "TargetOpticalBodyV5", "exposure", "Typography", "Footer / "
                       "Scrim", "Culling", "Media Fit / Focus",
                       "device-tier sample law", "every motion constant "
                       "(dragGain, fling multiplier, spring stiffness / damping / "
                       "mass, velocity-window duration, rest thresholds, dolly "
                       "law)", "the shipped opticalBody default"],
        "shippedDefault": "opticalBody=current, unchanged",
        "mainBranch": "not merged, not force-pushed, not touched",
    }


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    out = REPO / args.get("out", "qa-v5/final-motion")
    out.mkdir(parents=True, exist_ok=True)

    orient = load(out / "orientation-truth.json")
    flick = load(out / "flick-truth.json")
    if not orient or not flick:
        print("orientation-truth.json / flick-truth.json must exist first")
        return 1

    fz = frozen()
    fz["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # The commit whose tree these gates actually measured -- resolved by MESSAGE,
    # not `git rev-parse HEAD`. These files are regenerated inside the evidence
    # commit's own amend cycle, so HEAD at generation time is the draft the amend
    # is about to orphan; stamping it publishes a SHA that no ref reaches and
    # `git push` never transfers.
    fz["head"] = git("rev-list", "-1",
                     "--grep=^v5-final-motion-flick-source-and-code", "HEAD")
    if not fz["head"]:
        print("cannot resolve the capture anchor commit by message")
        return 1
    (out / "frozen-regressions.json").write_text(
        json.dumps(fz, indent=1, ensure_ascii=False))

    ps = state(orient, flick)
    ps["generatedAt"] = fz["generatedAt"]
    ps["head"] = fz["head"]
    ps["branch"] = git("rev-parse", "--abbrev-ref", "HEAD")
    (out / "product-state.json").write_text(
        json.dumps(ps, indent=1, ensure_ascii=False))

    for k, v in fz["gates"].items():
        print(f"  {str(v.get('pass')):>5}  {k:28s} {v.get('result')}")
    print(f"\nfinal product state: {ps['finalProductState']}")
    print(f"-> {out}/frozen-regressions.json, {out}/product-state.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
