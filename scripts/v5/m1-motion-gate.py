#!/usr/bin/env python3
"""
The motion gate: our page against the Target, on the same input.

Four questions, in order, because each one only means something if the one
before it held:

  1. Is the Target repeatable, and by how much? Run 3x, take the pointwise
     spread of the runs against each other. This is computed and written FIRST
     and is what every threshold below is derived from -- a threshold picked
     after seeing a candidate number is not a threshold.
  2. Does the CONTRACT reproduce the Target? Replay the model on the Target's
     own recorded input (m0-motion-contract.py).
  3. Does OUR ENGINE reproduce the contract? Replay the model on OUR page's own
     recorded input and compare with what our page actually did. This separates
     "the model is right" from "we implemented the model".
  4. Do our LANDMARKS match the Target's? Follow ratio, release velocity,
     decay times, travel. Landmarks rather than pointwise curves, because the
     two pages were driven by two separate event streams with their own
     dispatch jitter: a pointwise comparison would be measuring the automation
     harness as much as the pages.

Thresholds are `max(2 * target repeatability, floor)`, per sequence and per
viewport. The floors are declared here, once, and are not per-sequence.

Usage: m1-motion-gate.py --target=<trace> --local=<trace> --out=<dir>
"""
from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


MT = _load("motion_trace", "motion_trace.py")
MC = _load("m0_motion_contract", "m0-motion-contract.py")

# Explicit floors, declared once. A repeatability of zero -- which a sequence
# that moves nothing legitimately has -- must not produce a threshold of zero.
FLOORS = {
    "travelWorldUnits": 12.0,
    "followRatio": 0.05,
    "releaseVelocity": 60.0,
    "decayMs": 60.0,
    # CORRECTED. These two were written as "two frames at 60 Hz". Both pages
    # actually run at ~120 Hz -- the median inter-frame interval is 8.30 ms on
    # both sides, over 72,902 Target intervals and 19,654 of ours -- so 34.0 was
    # FOUR frames, and a perfectly systematic one-frame difference passed all
    # forty latency rows. 16.6 ms is two frames at the rate the pages run.
    #
    # This is a correction of a factual error about the frame rate, made in the
    # direction that makes the gate HARDER: it converts passing rows into
    # failing ones and relieves nothing.
    "latencyMs": 16.6,
    "orbitRad": 0.002,
    "settleMs": 16.6,           # two frames at the 120 Hz these pages run at
    "zeroMotionWorldUnits": 1.0,
    # A scale-free fraction: one frame losing a tenth of the speed it had.
    # Comfortably above the recovery's own noise, well below anything a viewer
    # would read as a stop.
    "speedDropFraction": 0.10,
    # The camera's distance from the origin as a multiple of the orbit radius.
    # The Target's dolly reaches 22% of it, so a page that dropped the dolly
    # misses by twenty floors.
    "dollyRatio": 0.01,
}

# A resize re-tiles the grid mid-run, so a pointwise trajectory comparison
# across that boundary measures the re-seed. Judged on continuity instead.
TRAJECTORY_EXCLUDED = {"resize-during-motion"}
WHEEL_SEQUENCES = {"wheel-mouse-steps", "wheel-trackpad-small", "wheel-deltamode"}


def group(trace):
    out = {}
    for run in trace["runs"]:
        out.setdefault((run["id"], run["sequence"]), []).append(run)
    return out


# Below this many live cards the scroll recovery is a median over almost
# nothing and the curve it produces is noise. It is not a threshold on a
# result -- it is the point at which the INSTRUMENT stops reading. The Target's
# own resize runs at 700x700 drop to 0 and 1 live cards, and every landmark
# taken from them is manufactured.
MIN_LIVE_CARDS = 4


def landmarks(run, obs):
    """Input-normalised numbers, so two event streams can be compared."""
    live = [n for n in obs.get("liveCards", []) if n is not None]
    if live and min(live) < MIN_LIVE_CARDS:
        # Reported as unreadable rather than gated. Silently gating a curve
        # recovered from one card is how a number with no content acquires a
        # verdict.
        return {"instrumentUnreadable": True,
                "liveCardsMin": min(live),
                "why": f"the scroll recovery fell to {min(live)} live cards, below "
                       f"{MIN_LIVE_CARDS}; every landmark from this run would be a median "
                       f"over almost nothing"}
    span = MT.drag_span(run)
    rel = MC.release_time(run)
    total_x = obs["scrollX"][-1] - obs["scrollX"][0]
    total_y = obs["scrollY"][-1] - obs["scrollY"][0]
    out = {"totalX": round(total_x, 4), "totalY": round(total_y, 4)}

    if span and abs(span[0]) > 1:
        out["followRatioX"] = round(total_x / span[0], 5)
    if span and abs(span[1]) > 1:
        out["followRatioY"] = round(total_y / span[1], 5)

    # Input-to-motion latency: from the first pointermove past the 3 px
    # threshold to the first frame whose scroll has actually changed.
    if span:
        downs = [e for e in run["events"] if e["type"] in ("pointerdown", "touchstart")]
        if downs:
            ox, oy = downs[0]["clientX"], downs[0]["clientY"]
            crossed = None
            for e in run["events"]:
                if e["type"] not in ("pointermove", "touchmove") or e["clientX"] is None:
                    continue
                if math.hypot(e["clientX"] - ox, e["clientY"] - oy) >= 3:
                    crossed = e["t"]; break
            if crossed is not None:
                base = obs["scrollX"][0]
                for t, x in zip(obs["t"], obs["scrollX"]):
                    if t >= crossed and abs(x - base) > 0.5:
                        out["latencyMs"] = round(t - crossed, 3)
                        break

    decay = MC.decay_stats(obs["t"], obs["scrollX"], rel) if rel else None
    if decay:
        out.update({"releaseVelocity": decay["releaseVelocity"],
                    "timeTo50PctMs": decay["timeTo50PctMs"],
                    "timeTo10PctMs": decay["timeTo10PctMs"],
                    "timeToVisualStopMs": decay["timeToVisualStopMs"],
                    "travelAfterRelease": decay["travelAfterRelease"],
                    "maxFrameVelocityStep": decay["maxFrameVelocityStep"],
                    "maxSingleFrameSpeedDropFraction":
                        decay["maxSingleFrameSpeedDropFraction"]})

    pt = MT.pointer_track(run)
    if pt:
        out["orbitYawMin"] = round(min(p[1] for p in pt), 6)
        out["orbitYawMax"] = round(max(p[1] for p in pt), 6)
        out["orbitPitchMin"] = round(min(p[2] for p in pt), 6)
        out["orbitPitchMax"] = round(max(p[2] for p in pt), 6)
    # Amplitude is not dynamics. Two pages can orbit to the same extremes and
    # get there at completely different speeds, so the smoothing constant is
    # its own landmark -- but a SETTLE TIME is only defined for a STEP, and the
    # only sequence that steps the pointer is the sweep, whose mouse moves all
    # land inside one frame followed by half a second of stillness. On a drag
    # the pointer travels as a continuous ramp: the burst detector finds a
    # "step" that is really the whole drag, and the number it returns is not a
    # time constant. It came back as 0.70 ms on one sequence and 297 ms on
    # another, for one and the same spring.
    #
    # Restricting it would drop coverage, so it does not go alone: the row
    # below replaces it with a measurement that IS defined on every stimulus.
    if run["sequence"] == "pointer-sweep":
        settle = MT.pointer_settle_63(run)
        if settle is not None:
            out["pointerSettle63Ms"] = settle

    # The dolly, on its own row.
    #
    # Making the orbit recovery dolly-immune -- which it had to be -- removed
    # the gate's only remaining view of the dolly: nothing else looked at the
    # camera's distance from the origin, so a page that dropped the dolly from
    # its CSS3D camera again, which is exactly the defect this round found,
    # would pass every row. The camera rides an orbit of radius `perspective`,
    # and the dolly is the only thing that takes it off that sphere.
    persp = MT.frame_for(*run["viewport"])["perspective"]
    dists = []
    for sample in run["frames"]:
        pos = MT.camera_position(sample)
        if pos is not None:
            dists.append(math.dist(pos, (0.0, 0.0, 0.0)) / persp)
    if dists:
        out["cameraDistanceOverPerspectivePeak"] = round(max(dists), 6)

    # The pointer spring's dynamics, on ANY stimulus.
    #
    # Drive the contract's pointer spring with this side's own recorded
    # pointermove stream and compare the predicted camera yaw against the yaw
    # recovered from this side's own CSS3D camera. It asks the same question a
    # settle time asks -- is the smoothing this fast? -- without needing the
    # input to be a step, so a drag, a flick and a sweep all answer it. A page
    # whose pointer spring is faster or slower than the contract's shows up
    # here as a larger residual, whatever the input did.
    if pt and len(pt) > 8:
        pred = MC.replay(run)
        gain = MC.SM.CAMERA["orbit"]["pointerGain"]
        model_yaw = MC.resample(pred["t"], [-gain * v for v in pred["pointerX"]],
                                [p[0] for p in pt])
        errs = [abs(a - b) for a, b in zip(model_yaw, [p[1] for p in pt])]
        if errs:
            out["pointerModelResidualRad"] = round(max(errs), 6)
    return out


# Landmarks where only an EXCESS is a defect. Everything else is compared
# two-sided, because a difference in either direction is a difference.
ONE_SIDED_UPPER = {"maxSingleFrameSpeedDropFraction"}

LANDMARK_UNIT = {
    "totalX": "travelWorldUnits", "totalY": "travelWorldUnits",
    "followRatioX": "followRatio", "followRatioY": "followRatio",
    "latencyMs": "latencyMs",
    "releaseVelocity": "releaseVelocity",
    "timeTo50PctMs": "decayMs", "timeTo10PctMs": "decayMs",
    "timeToVisualStopMs": "decayMs",
    "travelAfterRelease": "travelWorldUnits",
    "maxFrameVelocityStep": "releaseVelocity",
    "maxSingleFrameSpeedDropFraction": "speedDropFraction",
    "orbitYawMin": "orbitRad", "orbitYawMax": "orbitRad",
    "orbitPitchMin": "orbitRad", "orbitPitchMax": "orbitRad",
    "pointerSettle63Ms": "settleMs",
    "pointerModelResidualRad": "orbitRad",
    "cameraDistanceOverPerspectivePeak": "dollyRatio",
}


def wrap_continuity(run, obs):
    """Does a card ever jump ON SCREEN, in pixels, when the grid wraps?

    The product brief's claim is "no >2px wrap discontinuity" -- a SCREEN
    claim. The first version of this check answered a different question: it
    took every card that was not `visibility:hidden` in both frames and
    measured its movement in WORLD units. A card can be un-hidden and still be
    nowhere near the viewport, and a recycle moves such a card by a full wrap
    period, so the check flagged correct recycles. It flagged them on the
    TARGET too -- fourteen times -- and an instrument that fires on the page
    that is correct by definition is not measuring what it says it is.

    This version asks the brief's question with the browser's own answer. Every
    card's `getBoundingClientRect()` is recorded per frame on both sides, so
    "was it on screen" is a rect-viewport intersection and "how far did it
    move" is in pixels. A card is judged only if it was on screen in BOTH
    frames; the allowance is the field's own median screen step plus 2 px.

    The world-unit count is still reported beside it, so the change is visible
    rather than a quiet substitution.
    """
    frames = run["frames"]
    if len(frames) < 3:
        return None
    f0 = MT.frame_for(*run["viewport"])
    radius = f0["sphereRadius"]
    worst, worst_at, checked, jumps = 0.0, None, 0, 0
    for k in range(1, len(frames)):
        if frames[k]["w"] != frames[k - 1]["w"] or frames[k]["h"] != frames[k - 1]["h"]:
            continue
        a = {c[0]: (c[1], c[2], c[3]) for c in frames[k - 1]["cards"] if c[1] is not None}
        b = {c[0]: (c[1], c[2], c[3]) for c in frames[k]["cards"] if c[1] is not None}
        shared = a.keys() & b.keys()
        if len(shared) < 4:
            continue
        moves = sorted(math.dist(a[c], b[c]) for c in shared)
        field = moves[len(moves) // 2]
        # A wrap moves a card by a full period; the field moves by one frame's
        # worth. Anything past the field's own step plus a generous margin is a
        # teleport, and it happened while the card was visible on both frames.
        limit = max(field * 4.0, field + 40.0)
        for c in shared:
            d = math.dist(a[c], b[c])
            checked += 1
            if d > limit:
                jumps += 1
                if d - field > worst:
                    worst, worst_at = d - field, {"frame": k, "code": c,
                                                  "moved": round(d, 3),
                                                  "fieldMoved": round(field, 3)}
    # --- the screen-pixel measure the brief actually asks for ---------------
    #
    # Second attempt. The first one compared each card's screen movement with
    # the MEDIAN card's, and flagged anything more than 2 px above it -- which
    # under perspective is just parallax: a near card legitimately moves faster
    # on screen than the median. It fired ~7,900 times on the TARGET and ~8,600
    # on ours out of ~165,000 checks each, worst excess ~8 px on both. Equal
    # firing on the page that is correct by definition, again.
    #
    # A wrap is a DISCRETE event, so find it as one: the card's world position
    # jumps by a full period while the field steps by a frame's worth. That is
    # what the world-unit pass above already identifies, reliably. The only
    # question the brief asks is whether such a jump was ever VISIBLE -- so for
    # each card that wrapped, ask whether its rect was inside the viewport in
    # both frames, and if it was, measure how far it moved on screen.
    px_checked = px_jumps = 0
    px_worst, px_worst_at = 0.0, None
    have_rects = False
    for k in range(1, len(frames)):
        fa, fb = frames[k - 1], frames[k]
        if fb["w"] != fa["w"] or fb["h"] != fa["h"]:
            continue
        w, h = fb["w"], fb["h"]

        def rect_centre(c):
            if len(c) < 8 or c[4] is None:
                return None
            left, top, cw, ch = c[4], c[5], c[6], c[7]
            if left + cw <= 0 or top + ch <= 0 or left >= w or top >= h:
                return None
            return (left + cw / 2.0, top + ch / 2.0)

        wa = {c[0]: (c[1], c[2], c[3]) for c in fa["cards"] if c[1] is not None}
        wb = {c[0]: (c[1], c[2], c[3]) for c in fb["cards"] if c[1] is not None}
        shared_w = wa.keys() & wb.keys()
        if len(shared_w) < 4:
            continue
        moves = sorted(math.dist(wa[c], wb[c]) for c in shared_w)
        field_w = moves[len(moves) // 2]
        limit_w = max(field_w * 4.0, field_w + 40.0)

        ra = {c[0]: p for c in fa["cards"] if (p := rect_centre(c)) is not None}
        rb = {c[0]: p for c in fb["cards"] if (p := rect_centre(c)) is not None}
        if ra and rb:
            have_rects = True
        screen_moves = sorted(math.dist(ra[c], rb[c]) for c in ra.keys() & rb.keys())
        field_px = screen_moves[len(screen_moves) // 2] if screen_moves else 0.0

        for c in shared_w:
            if math.dist(wa[c], wb[c]) <= limit_w:
                continue                      # not a wrap
            if c not in ra or c not in rb:
                continue                      # wrapped off screen: invisible, correct
            px_checked += 1
            d = math.dist(ra[c], rb[c])
            if d - field_px > 2.0:
                px_jumps += 1
                if d - field_px > px_worst:
                    px_worst, px_worst_at = d - field_px, {
                        "frame": k, "code": c, "movedPx": round(d, 3),
                        "fieldMovedPx": round(field_px, 3)}

    return {"framePairs": len(frames) - 1, "cardFrameChecks": checked,
            "worldUnitFlags": jumps, "worstExcessWorldUnits": round(worst, 3),
            "worstAtWorldUnits": worst_at,
            "worldUnitNote": "reported, NOT gated: an un-hidden card can be far off screen, so a "
                             "correct recycle registers here -- it does on the Target too",
            "screenRectsAvailable": have_rects,
            "wrapsThatHappenedWhileOnScreen": px_checked,
            "visibleTeleports": px_jumps,
            "worstExcessPx": round(px_worst, 3), "worstAt": px_worst_at}


def spread_of(values):
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return 0.0
    return max(vals) - min(vals)


def mean_of(values):
    vals = [v for v in values if v is not None]
    return statistics.fmean(vals) if vals else None


def analyse(trace):
    """Per (viewport, sequence): the observed trajectories and landmarks."""
    out = {}
    for key, runs in group(trace).items():
        rows = []
        for run in runs:
            obs = MT.trajectory(run)
            rows.append({"run": run, "obs": obs, "marks": landmarks(run, obs)})
        out[key] = rows
    return out


if __name__ == "__main__":
    args = {a.split("=", 1)[0][2:]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--")}
    out_dir = Path(args["out"])
    target = json.loads(Path(args["target"]).read_text())
    local = json.loads(Path(args["local"]).read_text())
    extra_t = [json.loads(Path(p).read_text()) for p in args.get("targetExtra", "").split(",") if p]
    extra_l = [json.loads(Path(p).read_text()) for p in args.get("localExtra", "").split(",") if p]
    for e in extra_t:
        target["runs"].extend(e["runs"])
        target.setdefault("errors", []).extend(e.get("errors", []))
    for e in extra_l:
        local["runs"].extend(e["runs"])
        local.setdefault("errors", []).extend(e.get("errors", []))

    T, L = analyse(target), analyse(local)

    # ---- 1. Target repeatability, and the thresholds it produces -----------
    thresholds, repeat_rows = {}, []
    unreadable = []
    for side, data in (("target", T), ("ours", L)):
        for key, rows in sorted(data.items()):
            for r in rows:
                if r["marks"].get("instrumentUnreadable"):
                    unreadable.append({"side": side, "viewport": key[0], "sequence": key[1],
                                       "repeat": r["run"].get("repeat"),
                                       "liveCardsMin": r["marks"]["liveCardsMin"],
                                       "why": r["marks"]["why"]})
    for key, rows in sorted(T.items()):
        marks = {}
        for name in LANDMARK_UNIT:
            vals = [r["marks"].get(name) for r in rows]
            if all(v is None for v in vals):
                continue
            s = spread_of(vals)
            floor = FLOORS[LANDMARK_UNIT[name]]
            marks[name] = {"targetValues": vals, "targetMean": mean_of(vals),
                           "repeatabilitySpread": round(s, 5),
                           "threshold": round(max(2 * s, floor), 5)}
        thresholds[key] = marks
        base_t = rows[0]["obs"]["t"]
        curves = [MC.resample(r["obs"]["t"], r["obs"]["scrollX"], base_t) for r in rows]
        repeat_rows.append({
            "viewport": key[0], "sequence": key[1], "runs": len(rows),
            "worstPointwiseSpreadX": round(
                max((max(c) - min(c) for c in zip(*curves)), default=0.0), 4),
            "landmarks": {n: marks[n]["repeatabilitySpread"] for n in marks},
        })

    # ---- 3. our engine against the contract, on OUR OWN input --------------
    engine_rows = []
    for key, rows in sorted(L.items()):
        if key[1] in TRAJECTORY_EXCLUDED:
            continue
        for r in rows:
            pred = MC.replay(r["run"])
            res = MC.residual(pred, r["obs"])
            travel = max(1.0, abs(r["obs"]["scrollX"][-1] - r["obs"]["scrollX"][0]),
                         abs(r["obs"]["scrollY"][-1] - r["obs"]["scrollY"][0]))
            engine_rows.append({
                "viewport": key[0], "sequence": key[1], "repeat": r["run"]["repeat"],
                "travel": round(travel, 3),
                "maxAbsErr": max(res["maxAbsErrX"], res["maxAbsErrY"]),
                "rmsErr": max(res["rmsErrX"], res["rmsErrY"]),
                "finalErr": max(res["finalErrX"], res["finalErrY"]),
                "finalErrFraction": round(max(res["finalErrX"], res["finalErrY"]) / travel, 6),
                "maxAbsErrTimeAligned": res["maxAbsErrXTimeAligned"],
                "bestTimeShiftMs": res["bestTimeShiftMs"],
            })

    # ---- 4. landmark comparison, against those thresholds ------------------
    compare_rows, failures = [], []
    for key, rows in sorted(L.items()):
        tmarks = thresholds.get(key)
        if tmarks is None:
            compare_rows.append({"viewport": key[0], "sequence": key[1],
                                 "status": "NO TARGET RUN"})
            continue
        for name, spec in sorted(tmarks.items()):
            ours = mean_of([r["marks"].get(name) for r in rows])
            if ours is None or spec["targetMean"] is None:
                compare_rows.append({"viewport": key[0], "sequence": key[1],
                                     "landmark": name, "target": spec["targetMean"],
                                     "ours": ours, "status": "NOT MEASURABLE ON BOTH SIDES"})
                continue
            delta = abs(ours - spec["targetMean"])
            ok = delta <= spec["threshold"]
            if name in ONE_SIDED_UPPER:
                # Smaller is never worse. "No abrupt stop" is a claim about our
                # own curve: a page that loses LESS speed in a single frame
                # than the Target does is not stopping abruptly, and failing it
                # for that would be failing it for being smoother. Only an
                # excess counts.
                ok = (ours - spec["targetMean"]) <= spec["threshold"]
            row = {"viewport": key[0], "sequence": key[1], "landmark": name,
                   "target": round(spec["targetMean"], 5), "ours": round(ours, 5),
                   "delta": round(delta, 5),
                   "targetRepeatability": spec["repeatabilitySpread"],
                   "threshold": spec["threshold"],
                   "thresholdRule": "max(2 * target repeatability, floor)",
                   "floor": FLOORS[LANDMARK_UNIT[name]],
                   "pass": ok}
            compare_rows.append(row)
            if not ok:
                failures.append(row)

    # ---- systematic sign, across cells -----------------------------------
    #
    # The check shape this round was missing, and the reason a real defect
    # survived forty rows.
    #
    # Every other row asks "is this cell within threshold". A difference that
    # is SMALL in every cell but lands on the SAME SIDE in every cell is not
    # noise -- it is a defect whose size happens to sit under the floor. The
    # one-frame render lead was exactly that: latencyMs was negative in 40 of
    # 40 pairs and failed none of them.
    #
    # Two conditions, both required, so this cannot fire on a rounding bias:
    # the sign must be lopsided beyond what a fair coin would give (a two-sided
    # sign test at p < 0.001), AND the typical difference must exceed the
    # TARGET'S OWN repeatability on that landmark, so a systematic difference
    # smaller than the Target's own spread is reported rather than gated.
    systematic_rows = []
    by_landmark = {}
    for r in compare_rows:
        if "pass" not in r or r.get("target") is None or r.get("ours") is None:
            continue
        by_landmark.setdefault(r["landmark"], []).append(r)
    for name, rows in sorted(by_landmark.items()):
        diffs = [r["ours"] - r["target"] for r in rows]
        n = sum(1 for d in diffs if abs(d) > 1e-12)
        if n < 8:
            continue
        k = sum(1 for d in diffs if d > 0)
        tail = min(k, n - k)
        p_val = min(1.0, 2.0 * sum(math.comb(n, i) for i in range(tail + 1)) / (2 ** n))
        med_abs = statistics.median([abs(d) for d in diffs])
        med_rep = statistics.median([r["targetRepeatability"] for r in rows])
        lopsided = p_val < 0.001
        bigger = med_abs > med_rep
        row = {"landmark": name, "cells": n, "oursHigherIn": k,
               "signTestP": round(p_val, 8),
               "medianAbsDelta": round(med_abs, 6),
               "medianTargetRepeatability": round(med_rep, 6),
               "lopsided": lopsided, "largerThanTargetOwnSpread": bigger,
               "pass": not (lopsided and bigger)}
        systematic_rows.append(row)
        if not row["pass"]:
            failures.append({**row, "viewport": "ALL", "sequence": "ALL",
                             "target": None, "ours": None,
                             "delta": row["medianAbsDelta"],
                             "threshold": row["medianTargetRepeatability"]})

    # ---- direction and axis signs ----------------------------------------
    #
    # A magnitude threshold can be met by a page that moves the right distance
    # the wrong way at a small enough scale, and a follow ratio hides the sign
    # entirely when both sides are negative. Stated on its own row.
    sign_rows = []
    for key, rows in sorted(L.items()):
        if key[1] in TRAJECTORY_EXCLUDED or key[1] in WHEEL_SEQUENCES:
            continue
        trows = T.get(key)
        if not trows:
            continue
        row = {"viewport": key[0], "sequence": key[1]}
        ok = True
        for axis, mark in (("X", "totalX"), ("Y", "totalY")):
            ours = mean_of([r["marks"].get(mark) for r in rows])
            theirs = mean_of([r["marks"].get(mark) for r in trows])
            if ours is None or theirs is None:
                continue
            floor = FLOORS["travelWorldUnits"]
            row[f"target{axis}"] = round(theirs, 4)
            row[f"ours{axis}"] = round(ours, 4)
            if abs(theirs) < floor and abs(ours) < floor:
                row[f"sign{axis}"] = "BOTH BELOW FLOOR -- no direction to compare"
                continue
            same = (ours > 0) == (theirs > 0)
            row[f"sign{axis}"] = "same" if same else "OPPOSITE"
            ok = ok and same
        # Which INPUT axis drove which OUTPUT axis: a page that swapped them
        # would still pass every per-axis magnitude row.
        span = MT.drag_span(rows[0]["run"])
        if span and (abs(span[0]) > 4 or abs(span[1]) > 4):
            row["dragSpanPx"] = [round(span[0], 2), round(span[1], 2)]
        row["pass"] = ok
        sign_rows.append(row)
        if not ok:
            failures.append({**row, "landmark": "axisSign"})

    # ---- wheel: proof of absence, on both sides ---------------------------
    wheel_rows = []
    for side, data in (("target", T), ("ours", L)):
        for key, rows in sorted(data.items()):
            if key[1] not in WHEEL_SEQUENCES:
                continue
            for r in rows:
                modes = sorted({e["deltaMode"] for e in r["run"]["events"]
                                if e["type"] == "wheel" and e["deltaMode"] is not None})
                prevented = [e["defaultPrevented"] for e in r["run"]["events"]
                             if e["type"] == "wheel"]
                travel = max(abs(r["obs"]["scrollX"][-1] - r["obs"]["scrollX"][0]),
                             abs(r["obs"]["scrollY"][-1] - r["obs"]["scrollY"][0]))
                wheel_rows.append({
                    "side": side, "viewport": key[0], "sequence": key[1],
                    "repeat": r["run"]["repeat"],
                    "wheelEvents": len(prevented), "deltaModes": modes,
                    "anyDefaultPrevented": any(prevented),
                    "scrollTravel": round(travel, 5),
                    "pass": travel <= FLOORS["zeroMotionWorldUnits"],
                })

    # ---- wrap continuity, both sides --------------------------------------
    wrap_rows = []
    for side, data in (("target", T), ("ours", L)):
        for key, rows in sorted(data.items()):
            if key[1] not in ("long-drag-multi-wrap", "fast-flick"):
                continue
            for r in rows:
                wc = wrap_continuity(r["run"], r["obs"])
                if wc:
                    wrap_rows.append({"side": side, "viewport": key[0],
                                      "sequence": key[1], "repeat": r["run"]["repeat"], **wc})

    # ---- touch and mouse parity, and no stuck gesture ----------------------
    touch_rows = []
    for side, data in (("target", T), ("ours", L)):
        for key, rows in sorted(data.items()):
            if key[1] not in ("touch-drag-release", "pointercancel", "lostpointercapture",
                              "medium-drag"):
                continue
            for r in rows:
                ev = r["run"]["events"]
                kinds = sorted({e["type"] for e in ev})
                tail = r["obs"]["t"][-1]
                # Did the page come to rest by the end of the run? A gesture the
                # page never closed keeps following the pointer, so the tail
                # would still be drifting.
                last = r["obs"]["scrollX"]
                still = abs(last[-1] - last[-6]) < 0.5 if len(last) > 6 else None
                touch_rows.append({
                    "side": side, "viewport": key[0], "sequence": key[1],
                    "repeat": r["run"]["repeat"], "eventTypes": kinds,
                    "pointerTypes": sorted({e["pointerType"] for e in ev if e["pointerType"]}),
                    "totalX": round(last[-1] - last[0], 4),
                    "cameToRestByEndOfRun": still, "runMs": round(tail, 1),
                })

    # ---- resize continuity, both sides ------------------------------------
    resize_rows = []
    for side, data in (("target", T), ("ours", L)):
        for key, rows in sorted(data.items()):
            if key[1] != "resize-during-motion":
                continue
            for r in rows:
                cont = MC.resize_continuity(r["run"], r["obs"])
                if cont:
                    resize_rows.append({"side": side, "viewport": key[0],
                                        "repeat": r["run"]["repeat"], **cont})

    out_dir.mkdir(parents=True, exist_ok=True)

    def w(name, payload):
        (out_dir / name).write_text(json.dumps(payload, indent=2))

    w("input-trajectories.json", {
        "what": "what was actually dispatched, on both sides, and by what means",
        "everySequenceIsRealInput": "mouse, wheel and touch are dispatched as trusted browser "
                                    "input through the automation protocol. No QA hook moves "
                                    "either page. The one exception is labelled: wheel "
                                    "deltaMode 1 and 2 cannot be produced by a real device "
                                    "through the protocol and are dispatched as synthetic "
                                    "WheelEvents, which still reach a listener if one exists.",
        "sides": {
            side: [{"viewport": k[0], "sequence": k[1], "runs": len(rows),
                    "framesPerRun": [len(r["run"]["frames"]) for r in rows],
                    "eventsPerRun": [len(r["run"]["events"]) for r in rows],
                    "eventTypes": sorted({e["type"] for r in rows for e in r["run"]["events"]}),
                    "fingerDx": [round(MT.drag_span(r["run"])[0], 2) if MT.drag_span(r["run"])
                                 else None for r in rows],
                    "fingerDy": [round(MT.drag_span(r["run"])[1], 2) if MT.drag_span(r["run"])
                                 else None for r in rows]}
                   for k, rows in sorted(data.items())]
            for side, data in (("target", T), ("ours", L))},
    })

    w("drag-response.json", {
        "what": "drag displacement, follow ratio and input-to-motion latency",
        "thresholdRule": "max(2 * target repeatability, floor)",
        "floors": FLOORS,
        "targetRepeatability": repeat_rows,
        "rows": [r for r in compare_rows
                 if r.get("landmark") in ("totalX", "totalY", "followRatioX", "followRatioY",
                                          "latencyMs")],
        "systematicSign": {
            "what": "landmarks whose difference lands on the SAME SIDE in cell after cell",
            "why": "a difference that is small in every cell but never changes sign is a defect "
                   "sitting under the floor, not noise. The one-frame render lead this round was "
                   "exactly that: latencyMs was negative in 40 of 40 pairs and failed none of "
                   "them. No per-cell threshold can see it.",
            "rule": "FAIL when the sign is lopsided beyond a two-sided sign test at p < 0.001 AND "
                    "the median absolute difference exceeds the Target's own median repeatability "
                    "on that landmark. Both are required, so a systematic difference smaller than "
                    "the Target's own spread is reported and not gated.",
            "rows": systematic_rows,
        },
        "axisSigns": {
            "what": "which way each axis moved, and whether the input axes drove the output "
                    "axes the same way on both sides",
            "why": "a magnitude threshold can be met by a page that moves the right distance "
                   "the wrong way, and a follow ratio hides the sign when both sides are "
                   "negative",
            "rows": sign_rows,
        },
    })

    w("flick-decay.json", {
        "what": "release velocity and the decay curve after it",
        "note": "the Target has no decay law of its own: the release is a single jump of "
                "velocity * 0.1 on the spring's target, and the spring carries the rest.",
        "abruptStop": "maxFrameVelocityStep is a SHAPE comparison -- how our post-release ramp "
                      "differs from the Target's -- judged against the Target's own repeatability "
                      "like every other landmark. It is NOT the abrupt-stop test, and it used to "
                      "be labelled as one: a page whose jerk is SMALLER than the Target's is not "
                      "stopping abruptly, yet a matching test fails it, and ours is smaller in "
                      "most pairs. maxSingleFrameSpeedDropFraction is the abrupt-stop test proper "
                      "-- the largest single-frame fractional loss of speed after release, "
                      "scale-free and one-sided, with the Target's own value beside it. Both are "
                      "gated; neither replaces the other.",
        "rows": [r for r in compare_rows
                 if r.get("landmark") in ("releaseVelocity", "timeTo50PctMs", "timeTo10PctMs",
                                          "timeToVisualStopMs", "travelAfterRelease",
                                          "maxFrameVelocityStep",
                                          "maxSingleFrameSpeedDropFraction")],
    })

    w("wheel-normalization.json", {
        "what": "proof of ABSENCE: the Target registers no wheel listener, so no deltaMode "
                "produces motion, and neither does ours",
        "targetEvidence": "the only addEventListener(\"wheel\") in the Target's bundle is "
                          "inside three.js OrbitControls, which the app never mounts",
        "toleranceWorldUnits": FLOORS["zeroMotionWorldUnits"],
        "rows": wheel_rows,
        "passed": sum(1 for r in wheel_rows if r["pass"]),
        "total": len(wheel_rows),
    })

    w("pointer-orbit.json", {
        "what": "the camera orbit driven by the smoothed pointer, recovered from the CSS3D "
                "camera matrix on both sides",
        "law": "yaw = -0.05 * pointerX, pitch = 0.05 * pointerY, radius = perspective",
        "rows": [r for r in compare_rows
                 if str(r.get("landmark", "")).startswith("orbit")
                 or r.get("landmark") in ("pointerSettle63Ms", "pointerModelResidualRad")],
        "orbitRecovery": "the orbit angles are recovered from the camera's POSITION with the "
                         "velocity dolly solved out, not from its forward axis. The dolly is added "
                         "to the camera's world z and the camera then looks at the origin, so with "
                         "an off-centre pointer AND a moving page the forward axis is tilted by the "
                         "dolly. On a sweep, where nothing moves, both readings agree exactly.",
        "smoothing": "pointerSettle63Ms is the step response of the pointer spring, read "
                     "from the camera yaw on both sides: the sweep's mouse moves all land "
                     "inside one frame, so each corner is a step, and the number is the "
                     "time to cover 63.2% of it.",
    })

    w("engine-vs-contract.json", {
        "what": "our page against the model, driven by our page's OWN recorded input",
        "why": "separates 'the contract is right' from 'we implemented the contract'. The "
               "contract-against-the-Target check is target-motion-contract.json.",
        "rows": engine_rows,
        "worstFinalErrFraction": round(max((r["finalErrFraction"] for r in engine_rows),
                                           default=0.0), 6),
        "worstMaxAbsErrTimeAligned": round(max((r["maxAbsErrTimeAligned"] for r in engine_rows),
                                               default=0.0), 4),
    })

    w("wrap-continuity.json", {
        "what": "does any card that is ON SCREEN in two consecutive frames jump by more than "
                "2 px beyond what the whole field moved?",
        "rule": "a wrap is found as the DISCRETE event it is -- a card whose world position "
                "jumps by a full period while the field steps by a frame's worth -- and then "
                "asked whether it was VISIBLE: was the card's rect inside the viewport in both "
                "frames, and if so did it move more than 2 px beyond what the field moved on "
                "screen. 2.0 px is the product brief's number.",
        "twoEarlierVersionsWereWrong": "the first compared world-unit movement for any un-hidden "
                "card, and an un-hidden card can be far off screen, so it flagged correct "
                "recycles -- 14 of them on the TARGET. The second compared each card's SCREEN "
                "movement against the median card's, which under perspective is just parallax: a "
                "near card legitimately moves faster than the median. It fired ~7,900 times on "
                "the Target and ~8,600 on ours out of ~165,000 checks each. Both are recorded "
                "here because both fired on the page that is correct by definition, which is the "
                "only reliable way to catch an instrument measuring the wrong thing.",
        "supersedes": "the world-unit version, which flagged correct recycles -- fourteen of them "
                      "on the TARGET, which is correct by definition. Its count is still reported "
                      "per row as worldUnitFlags so the substitution is visible.",
        "rows": wrap_rows,
        "visibleTeleports": sum(r["visibleTeleports"] for r in wrap_rows),
        "visibleTeleportsTarget": sum(r["visibleTeleports"] for r in wrap_rows
                                      if r["side"] == "target"),
        "visibleTeleportsOurs": sum(r["visibleTeleports"] for r in wrap_rows
                                    if r["side"] == "ours"),
    })

    w("touch-runtime.json", {
        "what": "touch and mouse parity, and whether a cancelled or capture-lost gesture "
                "leaves the page stuck",
        "note": "the Target never takes pointer capture, so lostpointercapture cannot strand "
                "its gesture; ours does not either on the source-exact path. Both are checked "
                "by behaviour rather than by reading the implementation.",
        "rows": touch_rows,
    })

    w("resize-continuity.json", {
        "what": "a resize taken while the page is still moving, on both sides",
        "rows": resize_rows,
    })

    # Everything that can fail, folded into ONE verdict. A row that is recorded
    # but cannot change the verdict is not a gate -- the wheel rows, the wrap
    # teleports and the stuck-gesture rows all used to sit outside it.
    wheel_fail = [r for r in wheel_rows if r["side"] == "ours" and not r["pass"]]
    teleports = sum(r["visibleTeleports"] for r in wrap_rows if r["side"] == "ours")
    teleports_target = sum(r["visibleTeleports"] for r in wrap_rows if r["side"] == "target")
    stuck = [r for r in touch_rows
             if r["side"] == "ours" and r["cameToRestByEndOfRun"] is False]
    sign_fail = [r for r in sign_rows if not r["pass"]]
    page_errors = {"target": target.get("errors", []), "ours": local.get("errors", [])}
    # A reload the recorder survived is a harness event, not a page defect; it
    # is reported either way rather than filtered out silently.
    our_real_errors = [e for e in page_errors["ours"] if "recorder was gone" not in e]

    verdict = "PASS" if not (failures or wheel_fail or teleports or stuck
                             or sign_fail or our_real_errors) else "FAIL"
    summary = {
        "verdict": verdict,
        "verdictInputs": ["landmark comparisons", "systematic sign across cells", "axis signs",
                          "wheel absence (our side)",
                          "visible wrap teleports (our side)",
                          "gestures that never came to rest (our side)",
                          "console and page errors (our side)"],
        "landmarkComparisons": len([r for r in compare_rows if "pass" in r]),
        "landmarkFailures": failures,
        "notMeasurableOnBothSides": [r for r in compare_rows if r.get("status")],
        "instrumentUnreadableRuns": unreadable,
        "axisSigns": {"total": len(sign_rows), "failures": sign_fail},
        "systematicSign": {"total": len(systematic_rows),
                           "failures": [r for r in systematic_rows if not r["pass"]]},
        "wheel": {"passed": sum(1 for r in wheel_rows if r["pass"]), "total": len(wheel_rows),
                  "ourFailures": wheel_fail},
        "visibleTeleports": sum(r["visibleTeleports"] for r in wrap_rows),
        "visibleTeleportsOurSide": teleports,
        "visibleTeleportsTargetSide": teleports_target,
        "wrapNote": "screen-space, >2 px beyond the field's own step, judged only while a card is "
                    "on screen in both frames. The Target's own count is reported beside ours: a "
                    "check that fires on the Target is measuring the wrong thing, and this one "
                    "replaced a check that did.",
        "runsThatDidNotComeToRest": [
            {k: r[k] for k in ("side", "viewport", "sequence", "repeat")}
            for r in touch_rows if r["cameToRestByEndOfRun"] is False],
        "consoleAndPageErrors": {
            "target": page_errors["target"],
            "ours": page_errors["ours"],
            "oursExcludingHarnessReloads": our_real_errors,
            "note": "captured live for every run on both sides; a 'recorder was gone' line is "
                    "the harness re-installing itself after a dev-server reload, which is a "
                    "harness event and is reported rather than dropped.",
        },
        "engineVsContractWorstFinalErrFraction": round(
            max((r["finalErrFraction"] for r in engine_rows), default=0.0), 6),
    }
    w("gate-summary.json", summary)
    passed = summary["landmarkComparisons"] - len(failures)
    print(f"motion gate {verdict}  landmarks {passed}/{summary['landmarkComparisons']}  "
          f"wheel {summary['wheel']['passed']}/{summary['wheel']['total']}  "
          f"engine-vs-contract worst final {summary['engineVsContractWorstFinalErrFraction']:.5f}")
    if wheel_fail or teleports or stuck or sign_fail or our_real_errors:
        print(f"  wheel failures {len(wheel_fail)}  teleports {teleports}  "
              f"stuck {len(stuck)}  sign {len(sign_fail)}  errors {len(our_real_errors)}")
    for f in failures[:25]:
        print(f"  FAIL {f['viewport']:9} {f['sequence']:22} {f['landmark']:20} "
              f"target={f['target']} ours={f['ours']} delta={f['delta']} thr={f['threshold']}")
