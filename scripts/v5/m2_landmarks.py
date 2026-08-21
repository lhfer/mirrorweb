#!/usr/bin/env python3
"""Scheduler-invariant landmarks. One definition, used by baseline and gate.

WHY A SEPARATE FILE
-------------------
The baseline computes these on the Target and the gate computes them on the
candidate. If the two ever computed them slightly differently, the comparison
would be between two readers. They are written here once and imported by both,
so "the same measurement on both sides" is enforced by the module system rather
than by care.

WHAT "SCHEDULER-INVARIANT" MEANS HERE
-------------------------------------
The Target computes its motion in framer-motion's frame loop and paints it in
r3f's -- two independent rAF callbacks. A frame on which framer did not tick
between two paints repaints the same value, and the next frame carries double.
Measured, the Target's scroll deviates from its own local trend by 12.7% per
frame against our 1.8%.

That is real, and it is visible in every RAW per-frame number: a single-frame
derivative, a single-frame peak, a coefficient of variation. It is NOT visible
in where the page ends up, how far it travelled, how long it took to stop, or
how big the dolly got -- unless you measure those with a single-frame ruler.

So every landmark below is read off a UNIFORM timeline: position interpolated
onto a fixed 120 Hz or 60 Hz grid, derivatives taken over a short window rather
than one frame, peaks taken as a running median or a windowed RMS rather than
a maximum. The endpoints are never interpolated -- the final rest position is
the number the page actually finished at.

The raw single-frame numbers are still computed, in `raw_metrics`, and still
written out. They are simply not what the product verdict is taken from; see
MOTION-EXC-01.
"""
from __future__ import annotations

import importlib.util
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
R = _load("m2_replay", "m2_replay.py")

# Below this many live cards the scroll recovery is a median over almost
# nothing. Not a threshold on a result -- the point at which the INSTRUMENT
# stops reading.
MIN_LIVE_CARDS = 4


def reseeded(run: dict) -> bool:
    """Did the grid re-tile inside this run?

    A resize re-tiles the field and re-seeds the recovery: the recovered scroll
    is an INTEGRAL of per-frame card motion, so it has no absolute origin, and
    across a re-tile it picks up a constant offset. Measured on our own page,
    where the engine's own scroll is readable beside the recovery: the recovery
    error is 0.02 to 0.03 world units on every other sequence and 15 to 36 world
    units on the resize runs, with the median error equal to the worst -- a
    constant offset, exactly as the mechanism predicts, not a divergence.

    So a trajectory landmark taken across that boundary measures the re-seed.
    It is reported as INSTRUMENT_UNREADABLE rather than gated, on BOTH sides,
    and resize is judged on continuity instead -- which is a per-frame question
    the re-seed does not touch. This is the same exclusion M0 and M1 applied for
    the same reason; what is new is that it is now measured rather than argued.
    """
    fr = run.get("frames") or []
    if len(fr) < 2:
        return False
    return any(fr[i]["w"] != fr[0]["w"] or fr[i]["h"] != fr[0]["h"]
               for i in range(1, len(fr)))

# "Visually stopped": world units per second below which nothing on screen is
# moving in a way a viewer could see. Declared here, once, and used identically
# on both sides.
VISUAL_STOP_UNITS_PER_S = 2.0

# Below this speed a sign flip is dither, not a direction reversal.
REVERSAL_FLOOR_UNITS_PER_S = 8.0

GRIDS = (120.0, 60.0)

TRAJECTORY_EXCLUDED = {"resize-during-motion"}
WHEEL_SEQUENCES = {"wheel-mouse-steps", "wheel-trackpad-small", "wheel-deltamode"}


def _dolly_envelope(run):
    """Camera distance from the origin, as a fraction of the orbit radius.

    The camera rides an orbit whose radius IS the perspective, so a pointer
    orbit moves it around that sphere without changing its distance. The dolly
    is the only thing that takes it off the sphere, which makes
    `distance / perspective - 1` the dolly and nothing else.
    """
    persp = MT.frame_for(*run["viewport"])["perspective"]
    ts, vs = [], []
    for sample in run["frames"]:
        pos = MT.camera_position(sample)
        if pos is None:
            continue
        ts.append(sample["t"])
        vs.append(math.dist(pos, (0.0, 0.0, 0.0)) / persp - 1.0)
    return ts, vs


def scheduler_invariant(run: dict, obs: dict, hz: float) -> dict:
    """Landmarks a difference in frame scheduling cannot move.

    Returns {} when the recovery is too thin to read; the caller reports that
    as INSTRUMENT_UNREADABLE rather than gating a curve with no content.
    """
    live = [n for n in obs.get("liveCards", []) if n is not None]
    if live and min(live) < MIN_LIVE_CARDS:
        return {}
    if reseeded(run):
        return {}
    if len(obs["t"]) < 8:
        return {}

    tx, x = R.uniform(obs["t"], obs["scrollX"], hz)
    _, y = R.uniform(obs["t"], obs["scrollY"], hz)
    vx = R.velocity_series(tx, x)
    vy = R.velocity_series(tx, y)
    speed = [math.hypot(a, b) for a, b in zip(vx, vy)]

    out: dict = {}
    # ---- where it ended up, and how far it went ---------------------------
    # Read off the un-smoothed endpoints: the resampling preserves them, and
    # smoothing a position is rewriting the trajectory.
    out["totalX"] = round(x[-1] - x[0], 4)
    out["totalY"] = round(y[-1] - y[0], 4)
    # Where it came to REST, which is not the same number as where it ended up:
    # the mean of the last 100 ms. A page still creeping at the end of the run
    # has a rest value that differs from its last sample, and this is the pair
    # of numbers that says so. (Total travel is measured from the last sample;
    # the recovery has no absolute origin, so a "final position" that was just
    # the last sample would be totalX under a second name.)
    tail = [v for t_, v in zip(tx, x) if t_ >= tx[-1] - 100.0]
    tail_y = [v for t_, v in zip(tx, y) if t_ >= tx[-1] - 100.0]
    out["restX"] = round(statistics.mean(tail) if tail else x[-1], 4)
    out["restY"] = round(statistics.mean(tail_y) if tail_y else y[-1], 4)
    out["residualDriftX"] = round(abs(x[-1] - (tail[0] if tail else x[-1])), 4)
    # Distance actually travelled, which a there-and-back gesture separates
    # from net displacement.
    out["velocityIntegralX"] = round(R.integral_abs_velocity(tx, vx), 4)
    out["velocityIntegralY"] = round(R.integral_abs_velocity(tx, vy), 4)
    out["overshootX"] = round(R.overshoot(x), 4)
    out["overshootY"] = round(R.overshoot(y), 4)
    out["directionReversals"] = R.direction_reversals(vx, REVERSAL_FLOOR_UNITS_PER_S)

    # ---- how closely it followed the finger ------------------------------
    span = MT.drag_span(run)
    if span and abs(span[0]) > 1:
        out["followRatioX"] = round((x[-1] - x[0]) / span[0], 5)
    if span and abs(span[1]) > 1:
        out["followRatioY"] = round((y[-1] - y[0]) / span[1], 5)

    # ---- the release, measured with a line rather than one frame ---------
    rel = MC.release_time(run)
    if rel is not None and tx and tx[-1] > rel + 120:
        for w in (50.0, 75.0, 100.0):
            key = f"robustReleaseVelocity{int(w)}Ms"
            sx = R.robust_release_velocity(tx, x, rel, w)
            if sx is not None:
                out[key] = round(sx, 3)
        i_rel = next((i for i, t in enumerate(tx) if t >= rel), None)
        if i_rel is not None and i_rel < len(x) - 2:
            out["travelAfterReleaseX"] = round(abs(x[-1] - x[i_rel]), 4)
            out["travelAfterReleaseY"] = round(abs(y[-1] - y[i_rel]), 4)
            # Decay times, from the windowed speed rather than a frame step.
            peak_i = max(range(i_rel, min(i_rel + int(hz * 0.06) + 2, len(speed))),
                         key=lambda i: speed[i])
            peak = speed[peak_i]
            if peak > 0:
                def time_to(frac):
                    for i in range(peak_i, len(speed)):
                        if speed[i] <= frac * peak:
                            return round(tx[i] - rel, 2)
                    return None
                for frac, key in ((0.5, "timeTo50PctMs"), (0.1, "timeTo10PctMs")):
                    v = time_to(frac)
                    if v is not None:
                        out[key] = v
                # Visually stopped, and STAYS stopped: a curve that dips
                # through the threshold on one sample has not stopped.
                hold = max(3, int(hz * 0.05))
                for i in range(peak_i, len(speed)):
                    if all(speed[j] <= VISUAL_STOP_UNITS_PER_S
                           for j in range(i, min(i + hold, len(speed)))):
                        out["timeToVisualStopMs"] = round(tx[i] - rel, 2)
                        break

    # ---- the pointer orbit -----------------------------------------------
    pt = MT.pointer_track(run)
    if pt:
        out["orbitYawAmplitudeRad"] = round(max(p[1] for p in pt) - min(p[1] for p in pt), 6)
        out["orbitPitchAmplitudeRad"] = round(max(p[2] for p in pt) - min(p[2] for p in pt), 6)
    if run["sequence"] == "pointer-sweep":
        settle = MT.pointer_settle_63(run)
        if settle is not None:
            out["pointerSettle63Ms"] = settle

    # ---- the dolly, on a filtered envelope -------------------------------
    dt_, dv = _dolly_envelope(run)
    if len(dt_) > 8:
        gt, gv = R.uniform(dt_, dv, hz)
        # Three-frame running median: one frame's spike cannot produce it.
        out["dollyMedianPeak3"] = round(R.median_peak(gv, 3), 6)
        # 30 ms RMS: a peak that has to be sustained for a quarter of the
        # decay's own rise time before it counts.
        out["dollyRms30Peak"] = round(R.rolling_peak(gt, gv, 30.0), 6)
        if out["dollyMedianPeak3"] > 1e-9:
            i = max(range(len(gv)), key=lambda k: gv[k])
            out["dollyPeakTimeMs"] = round(gt[i] - gt[0], 2)
        out["dollyEnvelopeIntegral"] = round(R.integral_abs_velocity(gt, gv), 6)
    return out


def raw_metrics(run: dict, obs: dict) -> dict:
    """The single-frame numbers. Reported, and NOT gated -- see MOTION-EXC-01.

    Every one of these is read with a one-frame ruler, which is precisely the
    ruler the Target's two-rAF architecture moves. They stay in the record
    because "we did not reproduce the Target's scheduling" should be a number a
    reviewer can see, not a sentence in a document.
    """
    out: dict = {}
    steps = [abs(obs["scrollX"][i] - obs["scrollX"][i - 1])
             for i in range(1, len(obs["scrollX"]))]
    live = [i for i, v in enumerate(steps) if v > 0.5]
    if len(live) >= 30:
        devs = []
        zeros = doubles = 0
        for i in range(live[0] + 1, live[-1]):
            trend = (steps[i - 1] + steps[i + 1]) / 2.0
            if trend > 0.5:
                devs.append(abs(steps[i] - trend) / trend)
                if steps[i] < 0.5 * trend:
                    zeros += 1
                elif steps[i] > 1.5 * trend:
                    doubles += 1
        if devs:
            out["frameStepJitterFraction"] = round(statistics.median(devs), 5)
            out["nearZeroStepFraction"] = round(zeros / len(devs), 5)
            out["doubleStepFraction"] = round(doubles / len(devs), 5)
    # The FRAME INTERVAL, beside the step jitter.
    #
    # This pair is what identifies the mechanism, and it corrected the M1
    # reading. M1 described the Target's jitter as "a frame on which framer did
    # not tick repaints the same value, and the next frame carries double".
    # Measured here, the Target has NO near-zero steps at all and essentially
    # no double steps, while its frame interval is as steady as ours -- 8.3 ms
    # median, 7.4 to 9.3 at the 1st and 99th percentiles. The step/trend ratio
    # instead spreads smoothly from about 0.89 to 1.13. So it is not dropped
    # frames: it is a continuous PHASE difference between the loop that solves
    # the spring and the loop that paints it, sampling the same closed-form
    # curve a fraction of a frame early or late each time.
    ivs = sorted(run["frames"][i]["t"] - run["frames"][i - 1]["t"]
                 for i in range(1, len(run["frames"])))
    if len(ivs) > 20:
        n = len(ivs)
        out["frameIntervalMedianMs"] = round(ivs[n // 2], 3)
        out["frameIntervalP1Ms"] = round(ivs[int(0.01 * n)], 3)
        out["frameIntervalP99Ms"] = round(ivs[int(0.99 * n)], 3)
        out["frameIntervalMaxMs"] = round(ivs[-1], 3)
    rel = MC.release_time(run)
    d = MC.decay_stats(obs["t"], obs["scrollX"], rel) if rel else None
    if d:
        out["maxFrameVelocityStep"] = d["maxFrameVelocityStep"]
        out["maxSingleFrameSpeedDropFraction"] = d["maxSingleFrameSpeedDropFraction"]
        out["singleFrameReleaseVelocity"] = d["releaseVelocity"]
    persp = MT.frame_for(*run["viewport"])["perspective"]
    dists = [math.dist(p, (0.0, 0.0, 0.0)) / persp
             for p in (MT.camera_position(s) for s in run["frames"]) if p is not None]
    if dists:
        out["cameraDistanceOverPerspectivePeak"] = round(max(dists), 6)
    return out


# Which floor each landmark is measured against. The floors themselves are
# declared in the baseline file, once, before any candidate is read.
UNIT = {
    "totalX": "travelWorldUnits", "totalY": "travelWorldUnits",
    "restX": "travelWorldUnits", "restY": "travelWorldUnits",
    "velocityIntegralX": "travelWorldUnits", "velocityIntegralY": "travelWorldUnits",
    "residualDriftX": "travelWorldUnits",
    "overshootX": "travelWorldUnits", "overshootY": "travelWorldUnits",
    "travelAfterReleaseX": "travelWorldUnits", "travelAfterReleaseY": "travelWorldUnits",
    "directionReversals": "reversalCount",
    "followRatioX": "followRatio", "followRatioY": "followRatio",
    "robustReleaseVelocity50Ms": "releaseVelocity",
    "robustReleaseVelocity75Ms": "releaseVelocity",
    "robustReleaseVelocity100Ms": "releaseVelocity",
    "timeTo50PctMs": "decayMs", "timeTo10PctMs": "decayMs",
    "timeToVisualStopMs": "decayMs",
    "orbitYawAmplitudeRad": "orbitRad", "orbitPitchAmplitudeRad": "orbitRad",
    "pointerSettle63Ms": "settleMs",
    "dollyMedianPeak3": "dollyRatio", "dollyRms30Peak": "dollyRatio",
    "dollyPeakTimeMs": "decayMs", "dollyEnvelopeIntegral": "dollyIntegral",
    "touchMouseFollowParity": "followRatio",
}

# Landmarks where only an EXCESS over the Target is a defect. A page that
# overshoots LESS, jerks LESS or loses less speed in one frame than the Target
# is not worse for it, and failing it there is failing it for being smoother.
ONE_SIDED_UPPER = {
    "overshootX", "overshootY", "directionReversals",
    # raw, reported not gated, but the classification is still recorded
    "maxSingleFrameSpeedDropFraction", "maxFrameVelocityStep",
    "frameStepJitterFraction", "nearZeroStepFraction", "doubleStepFraction",
}

# Landmarks where only a SHORTFALL is a defect. Nothing is in this set today.
# It exists because the brief requires the mechanism to be general: a one-sided
# lower landmark added later must not need the comparison rewritten.
ONE_SIDED_LOWER: set[str] = set()

# Raw metrics: computed and written, never a product FAIL. MOTION-EXC-01.
EXCEPTION_RAW = {
    "frameStepJitterFraction", "nearZeroStepFraction", "doubleStepFraction",
    "frameIntervalMedianMs", "frameIntervalP1Ms", "frameIntervalP99Ms",
    "frameIntervalMaxMs",
    "maxFrameVelocityStep", "maxSingleFrameSpeedDropFraction",
    "singleFrameReleaseVelocity", "cameraDistanceOverPerspectivePeak",
}


def gate_type(name: str) -> str:
    if name in ONE_SIDED_UPPER:
        return "one-sided-upper"
    if name in ONE_SIDED_LOWER:
        return "one-sided-lower"
    return "two-sided"


def judge(name: str, ours: float, target: float, threshold: float) -> tuple[bool, str]:
    """PASS / FAIL / ACCEPTED_DEVIATION, by the landmark's own gate type.

    The bug this replaces: the M1 gate applied the one-sided rule to the
    per-cell comparison but a plain two-sided sign test to the systematic-sign
    summary, so "smoother than the Target in every single cell" -- which is the
    one thing a one-sided-upper landmark is defined to allow -- was reported as
    a systematic FAIL. Three landmarks failed that way and none of them was a
    defect.
    """
    kind = gate_type(name)
    delta = ours - target
    if kind == "one-sided-upper":
        if delta <= threshold:
            return True, ("PASS" if abs(delta) <= threshold else "SMOOTHER_THAN_TARGET")
        return False, "FAIL"
    if kind == "one-sided-lower":
        if -delta <= threshold:
            return True, ("PASS" if abs(delta) <= threshold else "STRONGER_THAN_TARGET")
        return False, "FAIL"
    return (abs(delta) <= threshold), ("PASS" if abs(delta) <= threshold else "FAIL")
