#!/usr/bin/env python3
"""O1 absolute gate: score the candidate on the brief's named metrics and
evaluate every failure condition PRE-REGISTERED in o1-selected-system.json.

Lanes (one capture session, o1-optics-measure.mjs):
  target      the live Target page
  before      the V0-accepted build (optics-identical to pre-O1 -- the V1
              pixel gate proved the V1 build bit-exact against it, and V1
              touched no material)
  candidate   the O1 build

Media is live and differs across lanes, so every number is a distribution
statistic over the SAME card geometry (the python layout twin), never a
pixel match. The metric lanes are captured over 3 REPEAT loads. What the
repeats established (recorded under targetLaneVariance): OUR lanes are
deterministic across loads (spread <= 1.3 chroma points), while the
TARGET's band statistics swing with its per-load media shuffle by 20-50x
the candidate-vs-before deltas. Cross-page ABSOLUTE comparisons against
one Target draw are therefore draw-dominated; within-page comparisons
(before / candidate / floor) are tight and carry the verdict. The floor
experiment (dispersionSpread=0 build) is the decisive attribution
instrument: it separates what the O1 system's lever can move from what it
cannot, entirely within our own page.

The pre-registered failure conditions are interpreted by the selection
file's own declared signs (`expectedVisualChange`: edge chroma DOWN,
fringe R-B DOWN, white ratio UP): "regresses" means AGAINST those signs.
A distance-to-target-sample coding was tried first and REJECTED -- both
codings and the per-rep evidence that decided it are in the artifact.

Also appends `attributionCorrectedByFloorExperiment` to the O0 diagnosis:
the O0 ranking attributed the desktop edge-chroma gap to System A; the
floor proves the dispersion lever owns only a small minority of it under
EVERY observed Target draw, so the residual is System B's (the Target's
fresnel-capped white env LERP).

Usage: o1-optics-gate.py --dir=<o1-final> --floor=<floor.png>
       --mediaonly=<result.json> --selected=<o1-selected-system.json>
       --regressions=<o1-regressions.json> --diagnosis=<o0 json>
       --out=<json>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


O0 = _load("o0_optics_report", "o0-optics-report.py")

KEY_STATES = ["1440x900/rest", "1440x900/pointer-corner-br",
              "390x844/rest", "390x844/pointer-corner-br"]
DESKTOP = KEY_STATES[:2]
MOBILE = KEY_STATES[2:]
METRIC_LANES = ("target", "before-beauty", "candidate-beauty")
# The selection file's declared signs: what "improves" means, pre-registered.
EXPECTED_SIGN = {"edgeChroma": -1, "fringeRB": -1, "whiteReflectionRatio": +1}
STAT_KEY = {"edgeChroma": "edgeChromaMean", "fringeRB": "fringeRB",
            "whiteReflectionRatio": "whiteReflectionRatio"}


def card_tuples(img, rects):
    """Per-card (interior luminance, edge chroma) samples."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    cards = []
    for (x0, y0, x1, y1) in rects:
        cw, ch = x1 - x0, y1 - y0
        ix0, iy0 = x0 + int(cw * 0.225), y0 + int(ch * 0.225)
        ix1, iy1 = x1 - int(cw * 0.225), y1 - int(ch * 0.225)
        inter = a[iy0:iy1, ix0:ix1].reshape(-1, 3)
        band = np.ones((ch, cw), dtype=bool)
        bx, by = int(cw * 0.15), int(ch * 0.15)
        band[by:ch - by, bx:cw - bx] = False
        edge = a[y0:y1, x0:x1][band]
        lum = float((0.2126 * inter[:, 0] + 0.7152 * inter[:, 1]
                     + 0.0722 * inter[:, 2]).mean())
        chroma = float((edge.max(axis=1) - edge.min(axis=1)).mean())
        cards.append((lum, chroma))
    return cards


def split_cohorts(cards):
    """Bright/dark halves at the pooled median interior luminance."""
    if len(cards) < 4:
        return None
    med = float(np.median([c[0] for c in cards]))
    dark = [c[1] for c in cards if c[0] <= med]
    bright = [c[1] for c in cards if c[0] > med]
    if not dark or not bright:
        return None
    return {"cards": len(cards), "interiorLumaMedian": round(med, 1),
            "darkEdgeChroma": round(float(np.mean(dark)), 2),
            "brightEdgeChroma": round(float(np.mean(bright)), 2)}


def average_stats(rows):
    """Mean of each numeric field across repeat captures."""
    out = {"repeats": len(rows)}
    for k in rows[0]:
        vals = [r[k] for r in rows if isinstance(r.get(k), (int, float))]
        if vals:
            out[k] = round(float(np.mean(vals)), 4 if k == "whiteReflectionRatio"
                           else 2)
    out["edgeChromaPerRepeat"] = [r.get("edgeChromaMean") for r in rows]
    out["whitePerRepeat"] = [r.get("whiteReflectionRatio") for r in rows]
    return out


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    d = Path(args["dir"])
    index = json.loads((d / "index.json").read_text())
    selected = json.loads(Path(args["selected"]).read_text())
    mediaonly = json.loads(Path(args["mediaonly"]).read_text())
    regressions = json.loads(Path(args["regressions"]).read_text())
    diag_path = Path(args["diagnosis"])
    diag = json.loads(diag_path.read_text())

    per_rep = {}      # key -> lane -> [stats]
    cohort_cards = {} # key -> lane -> [card tuples pooled over reps]
    single = {}       # key -> lane -> stats (layer controls)
    for s in index["shots"]:
        w, h = map(int, s["vp"].split("x"))
        img = Image.open(s["file"])
        rects = O0.card_rects(w, h, s["state"])
        key = f"{s['vp']}/{s['state']}"
        st = O0.stats(img, rects, w, h)
        if s["lane"] in METRIC_LANES:
            per_rep.setdefault(key, {}).setdefault(s["lane"], []).append(st)
            cohort_cards.setdefault(key, {}).setdefault(s["lane"], []).extend(
                card_tuples(img, rects))
        else:
            single.setdefault(key, {})[s["lane"]] = st

    metrics = {}
    for key, lanes in per_rep.items():
        metrics[key] = {lane: average_stats(rows) for lane, rows in lanes.items()}
        metrics[key].update(single.get(key, {}))

    cohort_rows = {}
    for key, lanes in cohort_cards.items():
        row = {lane: split_cohorts(cards) for lane, cards in lanes.items()}
        cohort_rows[key] = {k: v for k, v in row.items() if v}

    # ---- target-lane variance: the methodological finding ----
    o0_runtime = diag.get("runtime", {})
    variance = {"what": "how much each lane's band statistics move across "
                        "fresh loads (every load reshuffles the media). OUR "
                        "lanes are deterministic; the TARGET's numbers are "
                        "draw-dominated.",
                "perState": {}}
    for key in KEY_STATES:
        t = metrics[key]["target"]
        b = metrics[key]["before-beauty"]
        c = metrics[key]["candidate-beauty"]
        o0t = o0_runtime.get(key.replace("/", "/"), {}).get("target", {})
        variance["perState"][key] = {
            "targetEdgeChromaPerRepeat": t["edgeChromaPerRepeat"],
            "targetWhitePerRepeat": t["whitePerRepeat"],
            "targetO0SessionDraw": {"edgeChromaMean": o0t.get("edgeChromaMean"),
                                    "whiteReflectionRatio": o0t.get("whiteReflectionRatio")},
            "beforeEdgeChromaPerRepeat": b["edgeChromaPerRepeat"],
            "candidateEdgeChromaPerRepeat": c["edgeChromaPerRepeat"],
        }
    variance["reading"] = (
        "the Target's desktop edge chroma sampled 35.91 in the O0 session "
        "and 15.13-26.78 across this session's three draws; its mobile "
        "white ratio spans 0.042-0.243 within ONE session. Our own lanes "
        "spread at most 1.3 chroma points across loads. The candidate-vs-"
        "before deltas being judged (3-7 chroma points, 0.004-0.007 white) "
        "are 20-50x smaller than the Target lane's draw swing.")
    variance["methodRequirementForO2"] = (
        "cross-page ABSOLUTE band statistics against a single Target draw "
        "must not decide a gate. O2's gate must lean on within-page "
        "controls (before/candidate/floor on our page), source reads, and "
        "draw-stable structural measures; Target-lane numbers are context, "
        "reported with their per-draw range.")

    # ---- the floor experiment: dispersionSpread=0 build, desktop rest ----
    floor_img = Image.open(args["floor"])
    floor = O0.stats(floor_img, O0.card_rects(1440, 900, "rest"), 1440, 900)
    tb = metrics["1440x900/rest"]
    before_ec = tb["before-beauty"]["edgeChromaMean"]
    lever_pts = round(before_ec - floor["edgeChromaMean"], 2)
    target_draws = {
        "o0SessionDraw": o0_runtime.get("1440x900/rest", {}).get("target", {})
            .get("edgeChromaMean"),
        "thisSessionMean": tb["target"]["edgeChromaMean"],
    }
    shares = {name: round(100 * lever_pts / (before_ec - t), 1)
              for name, t in target_draws.items() if t}
    share_lo, share_hi = (min(shares.values()), max(shares.values())) if shares else (None, None)
    floor_doc = {
        "what": "the DECISIVE attribution instrument: the O1 build rebuilt "
                "with dispersionSpread=0 (dispersion OFF, everything else "
                "identical), desktop rest, single capture. Entirely within "
                "our own page, so media-draw variance does not touch it.",
        "captureFile": "private package: floor/floor-1440x900-rest.png",
        "edgeChromaMean": floor["edgeChromaMean"],
        "fringeRB": floor["fringeRB"],
        "whiteReflectionRatio": floor["whiteReflectionRatio"],
        "samePageLeverEffect": {
            "edgeChromaPoints": lever_pts,
            "reading": f"before {before_ec} -> floor {floor['edgeChromaMean']}: "
                       f"the ENTIRE dispersion mechanism is worth {lever_pts} "
                       f"edge-chroma points on our page (media-stable, "
                       f"within-page)."},
        "shareOfTargetGap": {
            "targetDraws": target_draws,
            "sharePctPerDraw": shares,
            "reading": f"the gap to the Target depends on the Target's media "
                       f"draw; dispersion's share of it is "
                       f"{share_lo}-{share_hi}% across the observed draws -- "
                       f"a small minority under every draw."},
    }
    floor_doc["conclusion"] = (
        f"dispersion owns {share_lo}-{share_hi}% of the desktop edge-chroma "
        f"gap to the Target (depending on the Target's media draw; the "
        f"same-page lever effect is exact: {lever_pts} points). The residual "
        f"is System B: the Target desaturates its edges by LERPing toward "
        f"the white env reflection under a fresnel cap (source-anchored in "
        f"the O0 forensics), while our shell ADDS white over a "
        f"still-saturated refracted edge.")

    # ---- direction checks ----
    def sign_ok(metric, b, c):
        return (c - b) * EXPECTED_SIGN[metric] > 0

    direction = {}
    for key in KEY_STATES:
        t = metrics[key]["target"]
        b = metrics[key]["before-beauty"]
        c = metrics[key]["candidate-beauty"]
        row = {}
        for m, sk in STAT_KEY.items():
            row[m] = {
                "target": t[sk], "before": b[sk], "candidate": c[sk],
                "movedInExpectedDirection": sign_ok(m, b[sk], c[sk]),
                "movedTowardTargetSample": abs(c[sk] - t[sk]) < abs(b[sk] - t[sk]),
            }
        row["edgeChroma"]["overcorrectedBelowTargetSample"] = (
            c["edgeChromaMean"] < t["edgeChromaMean"])
        row["fringeWidthPx"] = {"target": t["fringeWidthPxMean"],
                                "before": b["fringeWidthPxMean"],
                                "candidate": c["fringeWidthPxMean"]}
        direction[key] = row

    # ---- interior shift vs own media-only (no fake fix via media desat) ----
    interior = {}
    for key in KEY_STATES:
        row = {}
        for lane in ("before", "candidate"):
            bb = metrics[key].get(f"{lane}-beauty")
            mm = metrics[key].get(f"{lane}-media-only")
            if bb and mm and mm.get("interiorSaturationMean"):
                row[lane] = round(bb["interiorSaturationMean"]
                                  / mm["interiorSaturationMean"], 3)
        interior[key] = row

    # ---- the five pre-registered failure conditions, verbatim ----
    white_cand = tb["candidate-beauty"]["whiteReflectionRatio"]
    white_floor = floor["whiteReflectionRatio"]
    lever_white = round(white_cand - white_floor, 4)

    desktop_improved = all(direction[k][m]["movedInExpectedDirection"]
                           for k in DESKTOP for m in STAT_KEY)
    mobile_against_sign = [
        {"metric": f"{k}:{m}",
         "before": direction[k][m]["before"], "candidate": direction[k][m]["candidate"]}
        for k in MOBILE for m in STAT_KEY
        if not direction[k][m]["movedInExpectedDirection"]]
    mobile_away_from_sample = [
        {"metric": f"{k}:{m}", **{f: direction[k][m][f]
         for f in ("target", "before", "candidate")}}
        for k in MOBILE for m in STAT_KEY
        if not direction[k][m]["movedTowardTargetSample"]]

    conditions = [
        {"condition": selected["failureConditions"][0],
         "fired": any(direction[k]["edgeChroma"]["overcorrectedBelowTargetSample"]
                      for k in KEY_STATES),
         "measured": {
             "candidateEdgeChroma": {k: direction[k]["edgeChroma"]["candidate"]
                                     for k in KEY_STATES},
             "targetSampleMean": {k: direction[k]["edgeChroma"]["target"]
                                  for k in KEY_STATES},
             "note": "evaluated against this session's 3-draw Target mean; "
                     "the candidate sits ABOVE it in every state, so the "
                     "condition does not fire under any observed draw "
                     "(Target per-draw ranges in targetLaneVariance)."}},
        {"condition": selected["failureConditions"][1],
         "fired": True,
         "measured": {
             "whiteBefore": tb["before-beauty"]["whiteReflectionRatio"],
             "whiteCandidate": white_cand,
             "whiteAtFloorSpread0": white_floor,
             "leverEffectOnWhite": lever_white,
             "targetWhiteSampleRange": "0.071-0.147 across this session's "
                                       "desktop draws; 0.204 in the O0 "
                                       "session's draw",
         },
         "rationale": (
             f"fired on the LEVER-NULL result, which is same-page and "
             f"media-stable: white at dispersionSpread=0.3 ({white_cand}) "
             f"differs from the floor's at spread=0 ({white_floor}) by "
             f"{lever_white:+.4f} -- the system's ONE tunable lever "
             f"contributes essentially nothing to the white band. The "
             f"visual gap O1 targeted (the Target's white desaturating rim) "
             f"is produced by System B's mechanism, byte-anchored in the O0 "
             f"forensics as a fresnel-capped LERP toward the white env "
             f"reflection. Cross-page white-ratio comparisons are NOT part "
             f"of this firing: min(RGB)>180 counts bright media as 'white', "
             f"and the Target lane's draw range (targetLaneVariance) spans "
             f"our own values in both directions. The pre-registered "
             f"consequence applies: wrong root cause, System B next.")},
        {"condition": selected["failureConditions"][2],
         "fired": desktop_improved and len(mobile_against_sign) > 0,
         "measured": {
             "interpretation": "'regresses' is read by the selection file's "
                               "own declared signs (expectedVisualChange: "
                               "edge chroma DOWN, fringe R-B DOWN, white "
                               "UP): a mobile metric fires this condition "
                               "by moving AGAINST those signs while desktop "
                               "improves.",
             "desktopImprovedOnDeclaredSigns": desktop_improved,
             "mobileAgainstDeclaredSigns": mobile_against_sign or "none",
             "rejectedCoding": {
                 "what": "distance-to-this-session's-Target-sample; it "
                         "fires on 4 mobile rows",
                 "rows": mobile_away_from_sample or "none",
                 "whyRejected": "the comparator swings with the Target's "
                                "per-load media draw by 20-50x the deltas "
                                "being judged (mobile white draw range "
                                "0.042-0.243 vs candidate deltas "
                                "0.004-0.007) -- that coding measures the "
                                "Target's draw, not the candidate. Recorded "
                                "here so the rejection is auditable.",
             }}},
        {"condition": selected["failureConditions"][3],
         "fired": not mediaonly["pass"],
         "measured": mediaonly["rows"]},
        {"condition": selected["failureConditions"][4],
         "fired": not regressions["pass"],
         "measured": {k: v["pass"] for k, v in regressions.items()
                      if isinstance(v, dict) and "pass" in v}},
    ]
    fired = [c["condition"] for c in conditions if c["fired"]]

    doc = {
        "what": "O1 absolute gate. Scores the candidate on the brief's "
                "named metrics and evaluates every failure condition "
                "pre-registered in o1-selected-system.json before the "
                "candidate code existed. Conditions are interpreted by the "
                "selection file's own declared signs; a rejected "
                "alternative coding is recorded inside condition 3.",
        "verdict": "FAILED" if fired else "PASS",
        "firedFailureConditions": fired,
        "lanes": {
            "target": "https://infinite-liquid-glass.shader.se (live)",
            "before": "the V0-accepted build -- optics-identical to pre-O1 "
                      "(V1 pixel gate: bit-exact; V1 touched no material)",
            "candidate": "the O1 build, dispersionSpread=0.3",
        },
        "metrics": metrics,
        "directionChecks": direction,
        "brightDarkCohorts": cohort_rows,
        "targetLaneVariance": variance,
        "floorExperiment": floor_doc,
        "mediaOnlyInvariance": mediaonly,
        "interiorBeautyOverMediaOnlySaturation": interior,
        "failureConditions": conditions,
        "visuallyObviousGlassAdvance": {
            "required": "the brief: O1 must produce a visually OBVIOUS glass "
                        "advance",
            "met": False,
            "observed": "the synthetic cyan/magenta fringe LINES are visibly "
                        "reduced in the edge strips (private package, "
                        "roi/edge-compare-*.png), but the frame still reads "
                        "as a dark chromatic rim next to the Target's white "
                        "glassy one -- the dominant visual gap is the white "
                        "desaturating LERP (System B), which O1's one-system "
                        "scope could not touch.",
        },
        "runtimeMethod": "identical to O0 (o0-optics-report.py): same layout-"
                         "twin card rects, same bands, distribution "
                         "statistics only, media live on every lane; metric "
                         "lanes averaged over 3 repeat loads, cohorts pooled "
                         "across repeats.",
    }
    Path(args["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["out"]).write_text(json.dumps(doc, indent=1) + "\n")

    # ---- forward-correct the O0 attribution (never rewrite the commit) ----
    diag["attributionCorrectedByFloorExperiment"] = {
        "when": "O1 gate (this round), after the candidate was measured",
        "original": "systemGapRanking placed System A first because the "
                    "edge-band gaps were the largest DIRECTLY measured on "
                    "the brief's named metrics",
        "correction": floor_doc["conclusion"],
        "samePageLeverEffect": floor_doc["samePageLeverEffect"],
        "shareOfTargetGap": floor_doc["shareOfTargetGap"],
        "targetLaneVarianceWarning": variance["methodRequirementForO2"],
        "consequence": "the O2 system selection must read THIS field: the "
                       "dominant remaining edge gap belongs to System B "
                       "(environment / white studio reflection), not A.",
    }
    diag_path.write_text(json.dumps(diag, indent=1) + "\n")

    for key in KEY_STATES:
        dd = direction[key]
        print(f"{key}: edgeChroma T={dd['edgeChroma']['target']} "
              f"B={dd['edgeChroma']['before']} C={dd['edgeChroma']['candidate']} "
              f"| white T={dd['whiteReflectionRatio']['target']} "
              f"B={dd['whiteReflectionRatio']['before']} "
              f"C={dd['whiteReflectionRatio']['candidate']}")
    print(f"floor: edgeChroma {floor['edgeChromaMean']} "
          f"(same-page lever {lever_pts} pts; {share_lo}-{share_hi}% of the "
          f"Target gap across draws)")
    print("desktop improved on declared signs:", desktop_improved)
    print("mobile against declared signs:", len(mobile_against_sign))
    print("fired conditions:", len(fired))
    print("O1 GATE:", doc["verdict"])
    return 0 if not fired else 1


if __name__ == "__main__":
    sys.exit(main())
