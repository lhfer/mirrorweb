#!/usr/bin/env python3
"""Order-aware replay, and the resampling the scheduler-invariant gate needs.

WHY THIS FILE EXISTS
--------------------
The M1 replay attributed an input event to a frame with `event.t <= frame.t`.
Those two numbers come from different points in the browser's frame pipeline:
`event.t` is `performance.now()` at listener entry, `frame.t` is the rAF
timestamp, which is the time the frame STARTED -- before any callback in it
ran. Chrome dispatches input before the rAF block, so an event dispatched in
frame N satisfies `event.t > frame_N.t` and the rule handed it to frame N+1.

Measured on the M1 local traces, 90% of all events fell in the window
`(frame.t, frame.wall]` -- nine events in ten, one frame late, always the same
direction. That is the whole of the "persistent final error": 0.1457 of travel
on every reverse-flick row and 0.0527 on every fast-flick row, across four
viewports and three repeats, with a best-fit time shift clustered at -11 to
-13.5 ms. A defect that lands on exactly the same number in twelve independent
runs is not the engine mis-integrating; it is the reader mis-reading.

So ordering is no longer inferred from a clock. The M2 recorder bumps ONE
monotone counter from every event listener and every frame callback, and this
module replays in that order. `frame.t` keeps its job -- it is the clock the
springs integrate on, and it is still the right clock for that -- but it is no
longer asked a question it cannot answer.

WHAT IS STILL AMBIGUOUS, STATED RATHER THAN HIDDEN
--------------------------------------------------
The counter tells us the order of events against OUR callback. The page's own
frame callback is somewhere in the same rAF block and we cannot see it from
outside. An event dispatched between the page's callback and ours has a lower
`ord` than our sample but was not seen by the page until the next frame.
Input dispatch normally precedes the whole rAF block, so this window is small,
but it is not empty and it is not assumed away: `engine_vs_contract` measures
how often it bites, by replaying a second time with the release pinned to the
frame the engine itself recorded committing it on, and reporting the
difference. On the Target there is no such readback, which is why the Target
comparison is made on scheduler-invariant landmarks and not frame by frame.
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


SM = _load("source_motion", "source_motion.py")
MT = _load("motion_trace", "motion_trace.py")

# Field order written by the M2 recorder's truthOf(). Named here once.
TRUTH = ["scrollX", "scrollY", "scrollTargetX", "scrollTargetY",
         "velocityX", "velocityY", "magnitude",
         "pointerX", "pointerY", "pointerTargetX", "pointerTargetY",
         "dollyZ", "dragging", "motionSteps",
         "releaseVelocityX", "releaseVelocityY",
         "lastReleaseStep", "pendingReleaseCount"]
TRUTH_IX = {k: i for i, k in enumerate(TRUTH)}


def has_order(run: dict) -> bool:
    """Is this an M2 trace? An M1 trace replayed here would be replayed wrong."""
    f, e = run.get("frames") or [], run.get("events") or []
    return bool(f) and f[0].get("ord") is not None and (not e or e[0].get("ord") is not None)


def truth_series(run: dict, field: str):
    """One engine-truth field per frame, or None on a page that exposes none."""
    i = TRUTH_IX[field]
    out = []
    for f in run["frames"]:
        t = f.get("truth")
        out.append(None if not t else t[i])
    return out if any(v is not None for v in out) else None


def replay(run: dict, *, pin_release_step: bool = False,
           release_after_frame: bool = False) -> dict:
    """Run the frozen motion contract on this run's input, in callback order.

    One model step per recorded frame sample. The events consumed by step N are
    exactly those whose `ord` falls between sample N-1's and sample N's -- the
    events the browser dispatched between our two callbacks.

    The sample reported for each frame is the model's PREVIOUS frame, because
    the renderer consumes the motion values from a frame callback that runs
    before the model's own. That is the one-frame publication delay the product
    decided to keep; see SourceExactMotion.begin_frame for the measurement that
    fixed it at one frame rather than nought or two.

    `release_after_frame` is the DIAGNOSTIC that measures the sub-frame window
    this module's docstring describes, and it earns its place by being decisive
    rather than by sounding plausible.

    The question it settles: when a pointerup is dispatched between two of our
    sample callbacks, had the PAGE's own frame callback already run and pushed
    another point into the gesture history? If it had, `up()` measures its
    velocity over a history one entry longer, and the fling is different. We
    cannot see the page's callback from outside, so the honest thing is to
    replay it both ways and report where they disagree.

    Measured across 180 runs on our own page, against the engine's own recorded
    spring target: the default ordering -- release BEFORE this frame's pan
    dispatch -- is exact in 176 of them, and the alternative is wrong in 44. So
    the default is the right reading and is what the product path uses. The
    remaining 4 to 5 runs are ones where the race fell the other way, and they
    are reported as INSTRUMENT_SUBFRAME_RACE rather than as engine error,
    because replaying them the other way puts them at zero and puts forty
    others wrong.

    `pin_release_step` is a weaker diagnostic kept for completeness: it commits
    the release on the frame the engine recorded committing it on. It comes back
    at zero on every run, which says the release lands on the right FRAME; the
    disagreement is about ordering WITHIN the frame, which is what
    `release_after_frame` measures.
    """
    if not has_order(run):
        raise ValueError("trace carries no callback order; this is an M1 trace")

    model = SM.SourceExactMotion()
    events = sorted(run["events"], key=lambda e: e["ord"])
    frames = run["frames"]
    steps = truth_series(run, "motionSteps") if pin_release_step else None
    pinned = truth_series(run, "lastReleaseStep") if pin_release_step else None

    out = {"t": [], "scrollX": [], "scrollY": [], "targetX": [], "targetY": [],
           "magnitude": [], "pointerX": [], "pointerY": [],
           "velocityX": [], "velocityY": [], "dragging": [],
           "releaseStep": -1, "releaseVelocity": [0.0, 0.0],
           "consumedPerFrame": [], "eventsAfterLastFrame": 0}
    pending: list = []
    held_release = None
    deferred_up = None
    pointer_ndc = None
    ei = 0

    for n, sample in enumerate(frames):
        t = sample["t"]
        ord_hi = sample["ord"]
        published = model.begin_frame()
        consumed = 0
        while ei < len(events) and events[ei]["ord"] < ord_hi:
            e = events[ei]
            ei += 1
            consumed += 1
            kind = e["type"]
            if kind in ("pointerdown", "touchstart"):
                if e["clientX"] is not None:
                    model.session.down(e["clientX"], e["clientY"], e["t"])
            elif kind in ("pointermove", "touchmove"):
                if e["clientX"] is None:
                    continue
                model.session.move(e["clientX"], e["clientY"])
                if kind == "pointermove":
                    # Recorded, not committed: the pointer retarget is stamped
                    # with the FRAME's clock below, exactly as the scroll one
                    # is. The Target's passive effect records the target on the
                    # event and rebuilds the solve on the frame loop.
                    pointer_ndc = (e["clientX"] / sample["w"] * 2 - 1,
                                   e["clientY"] / sample["h"] * 2 - 1)
            elif kind in ("pointerup", "touchend", "pointercancel", "touchcancel"):
                cancelled = kind in ("pointercancel", "touchcancel")
                x = e["clientX"] if e["clientX"] is not None else model.session.history[-1][0]
                y = e["clientY"] if e["clientY"] is not None else model.session.history[-1][1]
                if release_after_frame:
                    # Deferred so that this frame's pan dispatch pushes its
                    # history entry FIRST, and up() then measures its velocity
                    # over the longer history. The other side of the race.
                    deferred_up = (x, y, e["t"], cancelled)
                    continue
                info = model.session.up(x, y, e["t"], cancelled=cancelled)
                if info is not None:
                    if pin_release_step:
                        held_release = info
                    else:
                        pending.append(("end", info))
            # wheel: the Target registers no handler, so the model has none.

        if held_release is not None and steps and pinned:
            # This frame is the one the engine recorded the release on.
            want = pinned[n]
            have = steps[n]
            if want is not None and have is not None and want == have:
                pending.append(("end", held_release))
                held_release = None

        if pointer_ndc is not None:
            model.set_pointer(pointer_ndc[0], pointer_ndc[1], t)
        info = model.session.frame(t)
        if info is not None:
            pending.append(("pan", info))
        if deferred_up is not None:
            ux, uy, ut, ucancel = deferred_up
            deferred_up = None
            uinfo = model.session.up(ux, uy, ut, cancelled=ucancel)
            if uinfo is not None:
                pending.append(("end", uinfo))
        for kind, i in pending:
            # Stamped with the FRAME's clock, not the event's. The Target has
            # no out-of-band path: a release is dispatched by the same frame
            # loop as a pan, so it retargets on the frame like everything else.
            if kind == "pan":
                model.on_pan(i, t)
            else:
                model.on_pan_end(i, t)
                out["releaseStep"] = n
                out["releaseVelocity"] = [i["velocity"][0], i["velocity"][1]]
        pending = []

        model.advance(t)

        out["t"].append(t)
        out["scrollX"].append(published["scrollX"])
        out["scrollY"].append(published["scrollY"])
        out["targetX"].append(model.target_x)
        out["targetY"].append(model.target_y)
        out["magnitude"].append(published["magnitude"])
        out["pointerX"].append(published["pointerX"])
        out["pointerY"].append(published["pointerY"])
        out["velocityX"].append(published["velocityX"])
        out["velocityY"].append(published["velocityY"])
        out["dragging"].append(1 if model.session.active else 0)
        out["consumedPerFrame"].append(consumed)

    out["eventsAfterLastFrame"] = len(events) - ei
    return out


def attribution_stats(run: dict) -> dict:
    """How different the two attribution rules are, on this run.

    Reported so that "the instrument was the defect" is a number in the record
    rather than a claim in a commit message.
    """
    frames, events = run["frames"], sorted(run["events"], key=lambda e: e["ord"])
    if not frames or not events:
        return {"events": len(events), "movedByOneFrameOrMore": 0, "fraction": 0.0}
    by_ord, by_t = {}, {}
    fi = 0
    for e in events:
        while fi < len(frames) and frames[fi]["ord"] < e["ord"]:
            fi += 1
        by_ord[e["ord"]] = fi           # first frame whose callback follows it
    fj = 0
    for e in events:
        while fj < len(frames) and frames[fj]["t"] < e["t"]:
            fj += 1
        by_t[e["ord"]] = fj             # what the M1 rule would have said
    moved = sum(1 for k in by_ord if by_ord[k] != by_t[k])
    shifts = [by_t[k] - by_ord[k] for k in by_ord]
    return {"events": len(events),
            "movedByOneFrameOrMore": moved,
            "fraction": round(moved / len(events), 4),
            "medianFrameShift": statistics.median(shifts) if shifts else 0,
            "maxFrameShift": max(shifts) if shifts else 0}


# ---------------------------------------------------------------------------
# Uniform resampling, for landmarks that must not depend on the scheduler
# ---------------------------------------------------------------------------

def uniform(t: list, v: list, hz: float) -> tuple[list, list]:
    """Linear resample onto a uniform timeline at `hz`.

    A frame the browser skipped and a frame it ran twice are both scheduling,
    not motion. Interpolating POSITION onto a fixed grid removes both without
    inventing anything: the value at any grid time is the value the trajectory
    already had, read at a regular instant instead of an irregular one.

    Endpoints are preserved exactly, so the final rest position -- the number
    a viewer actually sees -- is never rewritten by the resampling.
    """
    if not t or len(t) < 2:
        return list(t), list(v)
    step = 1000.0 / hz
    t0, t1 = t[0], t[-1]
    n = max(2, int(round((t1 - t0) / step)) + 1)
    grid = [t0 + i * step for i in range(n)]
    grid[-1] = t1
    out, j = [], 0
    for g in grid:
        while j + 1 < len(t) and t[j + 1] < g:
            j += 1
        if j + 1 >= len(t):
            out.append(v[-1])
            continue
        a, b = t[j], t[j + 1]
        out.append(v[j] if b == a else v[j] + (v[j + 1] - v[j]) * (g - a) / (b - a))
    out[0], out[-1] = v[0], v[-1]
    return grid, out


def smoothed(v: list, window: int = 3) -> list:
    """Centred moving average, endpoints held.

    Applied only to series a DERIVATIVE is taken from. The position series that
    the travel and rest landmarks are read off is never smoothed -- smoothing a
    position is rewriting the trajectory, which is exactly what the brief
    forbids.
    """
    if window < 3 or len(v) < window:
        return list(v)
    h = window // 2
    out = list(v)
    for i in range(h, len(v) - h):
        out[i] = sum(v[i - h:i + h + 1]) / window
    return out


def velocity_series(t: list, v: list, window: int = 3) -> list:
    """Central-difference velocity of a smoothed series, in units per second."""
    if len(t) < 3:
        return [0.0] * len(t)
    s = smoothed(v, window)
    out = [0.0] * len(t)
    for i in range(1, len(t) - 1):
        dt = t[i + 1] - t[i - 1]
        out[i] = 0.0 if dt <= 0 else (s[i + 1] - s[i - 1]) / dt * 1000.0
    out[0], out[-1] = out[1], out[-2]
    return out


def robust_release_velocity(t: list, v: list, t_rel: float, window_ms: float = 75.0) -> float | None:
    """Least-squares slope over a window that starts at release, in units/s.

    A single-frame derivative at the release instant is the noisiest number in
    the whole trace: it is one difference divided by one frame interval, and on
    the Target that interval is the thing that jitters by 12.7%. A line fitted
    through the first `window_ms` of the fling is the same quantity read in a
    way that a scheduler cannot move.

    Returns None when the window holds fewer than four samples -- an answer
    that would be a line through three points is not reported as a measurement.
    """
    xs = [(a, b) for a, b in zip(t, v) if t_rel <= a <= t_rel + window_ms]
    if len(xs) < 4:
        return None
    n = len(xs)
    mx = sum(a for a, _ in xs) / n
    my = sum(b for _, b in xs) / n
    den = sum((a - mx) ** 2 for a, _ in xs)
    if den <= 0:
        return None
    num = sum((a - mx) * (b - my) for a, b in xs)
    return num / den * 1000.0


def integral_abs_velocity(t: list, vel: list) -> float:
    """Trapezoid integral of |velocity| dt -- distance actually travelled."""
    if len(t) < 2:
        return 0.0
    s = 0.0
    for i in range(1, len(t)):
        s += 0.5 * (abs(vel[i]) + abs(vel[i - 1])) * (t[i] - t[i - 1]) / 1000.0
    return s


def direction_reversals(vel: list, floor: float) -> int:
    """Sign changes of a velocity that is actually moving.

    `floor` keeps a curve that is sitting at rest, dithering across zero by a
    thousandth of a unit, from being reported as fifty reversals.
    """
    sign, n = 0, 0
    for v in vel:
        if abs(v) < floor:
            continue
        s = 1 if v > 0 else -1
        if sign and s != sign:
            n += 1
        sign = s
    return n


def overshoot(v: list) -> float:
    """How far past the final value the curve went, in the units of `v`."""
    if len(v) < 3:
        return 0.0
    final, start = v[-1], v[0]
    if abs(final - start) < 1e-9:
        return 0.0
    if final > start:
        return max(0.0, max(v) - final)
    return max(0.0, final - min(v))


def rolling_peak(t: list, v: list, window_ms: float) -> float:
    """Largest value of a `window_ms` RMS -- a peak a single frame cannot make."""
    if not t:
        return 0.0
    best, j = 0.0, 0
    for i in range(len(t)):
        while t[i] - t[j] > window_ms:
            j += 1
        seg = v[j:i + 1]
        if len(seg) < 2:
            continue
        rms = math.sqrt(sum(x * x for x in seg) / len(seg))
        best = max(best, rms)
    return best


def median_peak(v: list, window: int = 3) -> float:
    """Peak of a running median -- one frame's spike cannot produce it."""
    if len(v) < window:
        return max(v) if v else 0.0
    h = window // 2
    return max(statistics.median(v[i - h:i + h + 1]) for i in range(h, len(v) - h))
