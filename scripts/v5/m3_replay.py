#!/usr/bin/env python3
"""Replay driven by the engine's OWN recorded release, not by a reading of it.

WHAT THIS ADDS TO THE M2 REPLAY
-------------------------------
M2 closed the frame-attribution defect with a monotone callback counter and
came out exact on 175 of 180 runs. The five that did not were all at the
release instant, and all of them turned on one question the counter cannot
answer: when the pointerup was dispatched between two of OUR sample callbacks,
had the PAGE's own frame callback already run and pushed another point into
the gesture history? If it had, the 100 ms window measured the release over a
history one entry longer and the fling came out different. Nothing outside the
page can see that callback, so M2 replayed both ways and reported three runs as
INSTRUMENT_SUBFRAME_RACE and two as failures.

The M3 recorder does not ask that question from outside. The engine records
each release as it commits it -- the complete history, the two points the 100 ms
window used, the velocity that came out, and the scroll target either side of
the fling -- and the recorder reads the engine's frame counter inside every
event listener. So the replay is told how many pan dispatches had happened when
the release arrived, instead of inferring it.

`release_history_target` is that number. It orders the release against this
frame's pan dispatch by counting, not by guessing: if the engine's history was
one longer than the replay's is, this frame's dispatch happened first. The
unpinned reading is still produced and still reported, so the SIZE of the
effect stays in the record rather than disappearing into a corrected number.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


M2 = _load("m2_replay", "m2_replay.py")
SM = M2.SM
MT = M2.MT

# Re-exported so a reader of this module has the whole toolkit in one place.
TRUTH = M2.TRUTH
TRUTH_IX = M2.TRUTH_IX
has_order = M2.has_order
truth_series = M2.truth_series
attribution_stats = M2.attribution_stats
uniform = M2.uniform
smoothed = M2.smoothed
velocity_series = M2.velocity_series
robust_release_velocity = M2.robust_release_velocity
integral_abs_velocity = M2.integral_abs_velocity
direction_reversals = M2.direction_reversals
overshoot = M2.overshoot
rolling_peak = M2.rolling_peak
median_peak = M2.median_peak


def release_targets(run: dict) -> list:
    """The history lengths the engine itself recorded, one per release."""
    return [r.get("historyCount") for r in (run.get("releaseRecords") or [])]


def replay(run: dict, *, writer_order: str | None = None,
           release_history_target: bool = True,
           window_epsilon: float = 0.0,
           force_release_after_frame: bool = False) -> dict:
    """One model step per recorded frame sample, in callback order.

    Identical to the M2 replay except for how a release is ordered against the
    pan dispatch of the frame it lands in. See the module docstring.
    """
    if not has_order(run):
        raise ValueError("trace carries no callback order; this is an M1 trace")

    model = SM.SourceExactMotion()
    if writer_order is not None:
        model.magnitude_writer_order = writer_order
    model.session.window_epsilon = window_epsilon
    events = sorted(run["events"], key=lambda e: e["ord"])
    frames = run["frames"]
    wanted = release_targets(run) if release_history_target else []

    out = {"t": [], "scrollX": [], "scrollY": [], "targetX": [], "targetY": [],
           "magnitude": [], "pointerX": [], "pointerY": [],
           "velocityX": [], "velocityY": [], "dragging": [],
           "releaseStep": -1, "releaseVelocity": [0.0, 0.0],
           "releaseHistoryCount": None, "releaseOrderedAfterDispatch": None,
           "releaseWindow": None,
           "consumedPerFrame": [], "eventsAfterLastFrame": 0}
    pending: list = []
    deferred_up = None
    pointer_ndc = None
    ei = 0
    releases_seen = 0

    for n, sample in enumerate(frames):
        t = sample["t"]
        # The model runs on the RAW rAF timestamp, which is the number the
        # engine stamped its gesture history with. `t` is that minus t0 and
        # rounded, and the 100 ms velocity window is a strict `>` -- so on the
        # shifted clock a point exactly one window old lands on the other side
        # of the comparison and the fling changes. Older traces have no `raf`
        # and fall back to `t`, which is what they were replayed on before.
        clock = sample.get("raf", t)
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
                    model.session.down(e["clientX"], e["clientY"],
                                       e.get("timeStamp", e["t"]))
            elif kind in ("pointermove", "touchmove"):
                if e["clientX"] is None:
                    continue
                model.session.move(e["clientX"], e["clientY"])
                if kind == "pointermove":
                    pointer_ndc = (e["clientX"] / sample["w"] * 2 - 1,
                                   e["clientY"] / sample["h"] * 2 - 1)
            elif kind in ("pointerup", "touchend", "pointercancel", "touchcancel"):
                cancelled = kind in ("pointercancel", "touchcancel")
                x = e["clientX"] if e["clientX"] is not None else model.session.history[-1][0]
                y = e["clientY"] if e["clientY"] is not None else model.session.history[-1][1]
                # HOW THIS RELEASE IS ORDERED AGAINST THIS FRAME'S DISPATCH.
                #
                # Counted, not guessed. The engine recorded how long its
                # gesture history was when it took the release. If ours is
                # already that long, the release came first. If ours is one
                # short, the page's own frame callback ran between the release
                # and our sample, so this frame's dispatch came first.
                after = force_release_after_frame
                if not after and wanted and releases_seen < len(wanted):
                    want = wanted[releases_seen]
                    if want is not None and len(model.session.history) < want \
                            and model.session.active and model.session.started:
                        after = True
                if after:
                    deferred_up = (x, y, e.get("timeStamp", e["t"]), cancelled)
                    continue
                info = model.session.up(x, y, e.get("timeStamp", e["t"]),
                                        cancelled=cancelled)
                releases_seen += 1
                if info is not None:
                    pending.append(("end", info))

        if pointer_ndc is not None:
            model.set_pointer(pointer_ndc[0], pointer_ndc[1], clock)
        info = model.session.frame(clock)
        if info is not None:
            pending.append(("pan", info))
        if deferred_up is not None:
            ux, uy, ut, ucancel = deferred_up
            deferred_up = None
            uinfo = model.session.up(ux, uy, ut, cancelled=ucancel)
            releases_seen += 1
            if uinfo is not None:
                pending.append(("end", uinfo))
                out["releaseOrderedAfterDispatch"] = True
        for kind, i in pending:
            if kind == "pan":
                model.on_pan(i, clock)
            else:
                model.on_pan_end(i, clock)
                out["releaseStep"] = n
                out["releaseVelocity"] = [i["velocity"][0], i["velocity"][1]]
                out["releaseHistoryCount"] = len(model.session.history)
                out["releaseWindow"] = model.session.last_velocity_window
                if out["releaseOrderedAfterDispatch"] is None:
                    out["releaseOrderedAfterDispatch"] = False
        pending = []

        model.advance(clock)

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
