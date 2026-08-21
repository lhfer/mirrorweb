#!/usr/bin/env python3
"""
Check the recovered motion contract against the Target, by replay.

The contract is read out of the Target's bundle, so the question is not "what
number fits this curve" -- no number here was fitted -- but "does the model the
source describes reproduce what the Target actually did". The check drives the
model with the TARGET'S OWN recorded input events and compares the predicted
scroll trajectory against the trajectory recovered from the Target's own card
matrices, frame by frame.

Repeatability comes first and is computed before any model residual is looked
at: the same trajectory is run three times on the Target, and the spread of the
Target against itself is what the model residual is then judged against. A
threshold chosen after seeing the residual is not a threshold.

Usage: m0-motion-contract.py --trace=<trace.json> --out=<json>
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
    # Register before exec: @dataclass resolves annotations through
    # sys.modules[cls.__module__], which is None for an unregistered module.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


MT = _load("motion_trace", "motion_trace.py")
SM = _load("source_motion", "source_motion.py")

# A resize re-tiles the grid and changes the arc period, so the recovered
# trajectory is re-seeded across that boundary and a pointwise residual against
# it measures the re-seed. The resize sequence is judged on continuity instead,
# and is named here rather than dropped quietly.
TRAJECTORY_EXCLUDED = {"resize-during-motion"}


def replay(run: dict) -> dict:
    """Run the model on this run's recorded input; sample it at its frames.

    The springs tick to the current frame time before any retarget, exactly as
    the library does -- its animation runs in the frame's update step and the
    retarget is scheduled at that same frame's postRender, so a new solve always
    starts from the value the animation just produced.

    The sample taken for each frame is the model's PREVIOUS frame, because the
    Target's renderer consumes framer-motion's values from a frame callback
    that runs before framer-motion's own. See SourceExactMotion.begin_frame.
    """
    model = SM.SourceExactMotion()
    events = sorted(run["events"], key=lambda e: e["t"])
    frames = run["frames"]
    out_t, out_x, out_y, out_mag, out_px = [], [], [], [], []
    pending: list[dict] = []
    pointer_ndc: tuple[float, float] | None = None
    ei = 0

    for sample in frames:
        t = sample["t"]
        # What the Target's renderer paints on this frame is what its model
        # produced on the PREVIOUS one -- snapshot first, then tick.
        published = model.begin_frame()
        # Every input event since the previous frame, in order.
        while ei < len(events) and events[ei]["t"] <= t:
            e = events[ei]; ei += 1
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
                    # with the FRAME's clock, below, exactly as the scroll one
                    # is. The Target's passive effect records the target on the
                    # event and rebuilds the solve on the frame loop.
                    pointer_ndc = (e["clientX"] / sample["w"] * 2 - 1,
                                   e["clientY"] / sample["h"] * 2 - 1)
            elif kind in ("pointerup", "touchend", "pointercancel", "touchcancel"):
                cancelled = kind in ("pointercancel", "touchcancel")
                x = e["clientX"] if e["clientX"] is not None else model.session.history[-1][0]
                y = e["clientY"] if e["clientY"] is not None else model.session.history[-1][1]
                info = model.session.up(x, y, e["t"], cancelled=cancelled)
                if info is not None:
                    pending.append(("end", info, e["t"]))
            # wheel: the Target has no handler, so the model has none either.

        if pointer_ndc is not None:
            model.set_pointer(pointer_ndc[0], pointer_ndc[1], t)
        info = model.session.frame(t)
        if info is not None:
            pending.append(("pan", info, t))
        for kind, i, _at in pending:
            # Stamped with the FRAME's clock, not the event's. The Target has
            # no out-of-band path: a release is dispatched by the same frame
            # loop as a pan, so it retargets on the frame like everything else.
            (model.on_pan if kind == "pan" else model.on_pan_end)(i, t)
        pending = []

        model.advance(t)

        out_t.append(t); out_x.append(published["scrollX"]); out_y.append(published["scrollY"])
        out_mag.append(published["magnitude"]); out_px.append(published["pointerX"])

    return {"t": out_t, "scrollX": out_x, "scrollY": out_y,
            "magnitude": out_mag, "pointerX": out_px}


def resample(src_t, src_v, at_t):
    """Linear resample; both series are dense frame samples."""
    out, j = [], 0
    for t in at_t:
        while j + 1 < len(src_t) and src_t[j + 1] < t:
            j += 1
        if j + 1 >= len(src_t):
            out.append(src_v[-1]); continue
        t0, t1 = src_t[j], src_t[j + 1]
        if t1 == t0:
            out.append(src_v[j]); continue
        f = (t - t0) / (t1 - t0)
        out.append(src_v[j] + (src_v[j + 1] - src_v[j]) * f)
    return out


def residual(pred, obs):
    """Predicted against observed, raw and after one constant time shift.

    The shift is REPORTED, never applied to a verdict. Three different frame
    callbacks -- the recorder's, the page's renderer and the gesture dispatch --
    sample the same frame at different points, so a sub-frame phase difference
    between two curves is an artefact of the instrument. Splitting the residual
    into "phase" and "not phase" says which part of it the model owns.
    """
    px = resample(pred["t"], pred["scrollX"], obs["t"])
    py = resample(pred["t"], pred["scrollY"], obs["t"])
    ex = [abs(a - b) for a, b in zip(px, obs["scrollX"])]
    ey = [abs(a - b) for a, b in zip(py, obs["scrollY"])]
    best, best_shift = None, None
    # A flat curve is aligned at every shift, so the search would report the
    # first one it tried and put a meaningless number in the summary.
    moved = max(obs["scrollX"]) - min(obs["scrollX"]) > 1.0
    if len(obs["t"]) > 8 and moved:
        for step in range(-60, 61):
            shift = step * 0.5
            sx = resample([t + shift for t in pred["t"]], pred["scrollX"], obs["t"])
            worst = max(abs(a - b) for a, b in zip(sx, obs["scrollX"]))
            if best is None or worst < best:
                best, best_shift = worst, shift
    return {
        "maxAbsErrX": round(max(ex) if ex else 0.0, 4),
        "maxAbsErrY": round(max(ey) if ey else 0.0, 4),
        "rmsErrX": round(math.sqrt(sum(v * v for v in ex) / len(ex)), 4) if ex else 0.0,
        "rmsErrY": round(math.sqrt(sum(v * v for v in ey) / len(ey)), 4) if ey else 0.0,
        "finalErrX": round(abs(px[-1] - obs["scrollX"][-1]), 4) if px else 0.0,
        "finalErrY": round(abs(py[-1] - obs["scrollY"][-1]), 4) if py else 0.0,
        "maxAbsErrXTimeAligned": round(best if best is not None else 0.0, 4),
        "bestTimeShiftMs": best_shift,
    }


def curve_stats(t, v):
    """Landmarks a motion gate is written in terms of."""
    if not t:
        return {}
    total = v[-1] - v[0]
    peak = max(abs(x - v[0]) for x in v)
    return {"total": round(total, 4), "peakExcursion": round(peak, 4)}


def decay_stats(t, v, release_t):
    """Release velocity and the decay landmarks, from the observed curve."""
    idx = [i for i, x in enumerate(t) if x >= release_t]
    if len(idx) < 6:
        return None
    i0 = idx[0]
    final = v[-1]
    # Velocity by central difference, smoothed over ~3 frames.
    def vel(i):
        a = max(i0, i - 1); b = min(len(t) - 1, i + 1)
        return (v[b] - v[a]) / ((t[b] - t[a]) / 1000.0) if t[b] != t[a] else 0.0
    window = range(i0, min(i0 + 4, len(t)))
    v0 = max((abs(vel(i)) for i in window), default=0.0)
    if v0 <= 0:
        return None
    # WHERE the peak is, not just how big it is. A curve that RAMPS UP after
    # release is already below half its own peak on its first sample, so a scan
    # that starts at the release instant answers "0 ms" for a page that has not
    # decayed at all. That is what it did: 1.7 ms against the Target's 180 ms,
    # on a page whose curve then tracked the Target's for the next 100 ms.
    i_peak = max(window, key=lambda i: abs(vel(i)))

    def time_to(frac):
        for i in range(i_peak, len(t)):
            if abs(vel(i)) <= frac * v0:
                return round(t[i] - release_t, 2)
        return None

    def time_to_still(eps_units_per_s):
        for i in range(i_peak, len(t)):
            if all(abs(vel(j)) <= eps_units_per_s for j in range(i, min(i + 5, len(t)))):
                return round(t[i] - release_t, 2)
        return None

    # Largest single-frame jerk after release. This is a SHAPE comparison --
    # how our ramp differs from the Target's -- and it is compared like every
    # other landmark, against the Target's own repeatability.
    jerk = 0.0
    for i in range(i0 + 2, len(t) - 1):
        dv = abs(vel(i) - vel(i - 1))
        jerk = max(jerk, dv)

    # The ABRUPT STOP test proper, which the jerk comparison above is not.
    #
    # "No abrupt stop" is a claim about our own curve, not about whether our
    # jerk equals the Target's: a page whose jerk is SMALLER than the Target's
    # is not stopping abruptly, yet a matching test fails it. This measures the
    # largest single-frame FRACTIONAL drop in speed after release, which is
    # scale-free, and it is one-sided -- smaller is never worse. The Target's
    # own value is what calibrates it.
    drop = 0.0
    drop_at = None
    for i in range(i0 + 2, len(t) - 1):
        prev, cur = abs(vel(i - 1)), abs(vel(i))
        if prev < 50.0:            # too slow for a fractional drop to mean anything
            continue
        f = (prev - cur) / prev
        if f > drop:
            drop, drop_at = f, round(t[i] - release_t, 2)

    return {"releaseVelocity": round(v0, 3),
            "timeTo50PctMs": time_to(0.5), "timeTo10PctMs": time_to(0.1),
            "timeToVisualStopMs": time_to_still(2.0),
            "travelAfterRelease": round(final - v[i0], 3),
            "maxFrameVelocityStep": round(jerk, 3),
            "maxSingleFrameSpeedDropFraction": round(drop, 5),
            "maxSingleFrameSpeedDropAtMs": drop_at}


def resize_continuity(run, obs):
    """Did a resize mid-motion stop, jump or strand the page?

    Trajectory RMS is the wrong instrument here. What matters is that the
    motion carries on through the resize, that the card field does not jump,
    and that the gesture layer is not left holding a drag that never ends.
    """
    sizes = [(f["w"], f["h"]) for f in run["frames"]]
    changes = [i for i in range(1, len(sizes)) if sizes[i] != sizes[i - 1]]
    if not changes:
        return None
    t = obs["t"]; x = obs["scrollX"]
    rows = []
    for i in changes:
        # Frame-to-frame step just before and just after the boundary. The
        # boundary frame itself is a re-seed and carries no delta by
        # construction, so it is skipped rather than counted as a stall.
        before = [abs(x[k] - x[k - 1]) for k in range(max(1, i - 6), i)]
        after = [abs(x[k] - x[k - 1]) for k in range(i + 2, min(len(x), i + 8))]
        rows.append({
            "atMs": t[i], "from": sizes[i - 1], "to": sizes[i],
            "meanStepBefore": round(sum(before) / len(before), 4) if before else 0.0,
            "meanStepAfter": round(sum(after) / len(after), 4) if after else 0.0,
        })
    moving_at_first = rows[0]["meanStepBefore"] > 0.5
    still_moving = any(r["meanStepAfter"] > 0.05 for r in rows)
    ups = [e for e in run["events"]
           if e["type"] in ("pointerup", "touchend", "pointercancel", "touchcancel")]
    return {"boundaries": rows,
            "velocityWasNonZeroAtFirstResize": moving_at_first,
            "motionContinuedAfterResize": still_moving,
            "gestureClosed": bool(ups),
            "totalTravel": round(x[-1] - x[0], 4)}


def release_time(run):
    ups = [e for e in run["events"]
           if e["type"] in ("pointerup", "touchend", "pointercancel", "touchcancel")]
    return ups[-1]["t"] if ups else None


if __name__ == "__main__":
    args = {a.split("=", 1)[0][2:]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--")}
    trace = json.loads(Path(args["trace"]).read_text())
    # The Target is captured one viewport per process -- the harness holds every
    # frame in memory until it writes, and four viewports in one process
    # exhausts Node's heap. The shards are merged here; the split changes
    # nothing a run measures.
    for extra in [e for e in args.get("extra", "").split(",") if e]:
        e = json.loads(Path(extra).read_text())
        trace["runs"].extend(e["runs"])
        trace.setdefault("errors", []).extend(e.get("errors", []))
    out_path = Path(args["out"])

    per_run = []
    for run in trace["runs"]:
        obs = MT.trajectory(run)
        rel = release_time(run)
        entry = {
            "viewport": run["id"], "sequence": run["sequence"], "repeat": run["repeat"],
            "frames": len(run["frames"]),
            "liveCardsMin": min(obs["liveCards"]) if obs["liveCards"] else 0,
            "worstPerCardSpread": round(max((s for s in obs["perCardSpread"] if s == s), default=0.0), 6),
            "observed": {"scrollX": curve_stats(obs["t"], obs["scrollX"]),
                         "scrollY": curve_stats(obs["t"], obs["scrollY"])},
            "releaseAtMs": rel,
            "decayX": decay_stats(obs["t"], obs["scrollX"], rel) if rel else None,
            "resizeContinuity": resize_continuity(run, obs),
            "_t": obs["t"], "_x": obs["scrollX"], "_y": obs["scrollY"],
        }
        pred = replay(run)
        entry["model"] = residual(pred, obs)
        entry["_pt"], entry["_px"], entry["_py"] = pred["t"], pred["scrollX"], pred["scrollY"]
        per_run.append(entry)

    # ---- repeatability of the Target against ITSELF, computed first ---------
    groups: dict[tuple[str, str], list[dict]] = {}
    for e in per_run:
        groups.setdefault((e["viewport"], e["sequence"]), []).append(e)

    repeat_rows = []
    for (vp, seq), rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        base_t = rows[0]["_t"]
        curves_x = [resample(r["_t"], r["_x"], base_t) for r in rows]
        curves_y = [resample(r["_t"], r["_y"], base_t) for r in rows]
        spread_x = max((max(c) - min(c) for c in zip(*curves_x)), default=0.0)
        spread_y = max((max(c) - min(c) for c in zip(*curves_y)), default=0.0)
        totals_x = [r["observed"]["scrollX"]["total"] for r in rows]
        totals_y = [r["observed"]["scrollY"]["total"] for r in rows]
        repeat_rows.append({
            "viewport": vp, "sequence": seq, "runs": len(rows),
            "worstPointwiseSpreadX": round(spread_x, 4),
            "worstPointwiseSpreadY": round(spread_y, 4),
            "totalsX": totals_x, "totalsY": totals_y,
            "totalSpreadX": round(max(totals_x) - min(totals_x), 4),
            "totalSpreadY": round(max(totals_y) - min(totals_y), 4),
        })

    worst_repeat = max((r["worstPointwiseSpreadX"] for r in repeat_rows), default=0.0)
    worst_repeat_y = max((r["worstPointwiseSpreadY"] for r in repeat_rows), default=0.0)

    # A residual is only meaningful beside the Target's own spread. A flick's
    # release velocity depends on sub-frame timing, so the Target does not
    # repeat itself exactly either; a model residual smaller than that spread
    # is at the noise floor, and one larger than it is a real disagreement.
    repeat_by_key = {(r["viewport"], r["sequence"]): r for r in repeat_rows}
    against_noise = []
    for (vp, seq), rows in sorted(groups.items()):
        if seq in TRAJECTORY_EXCLUDED:
            continue
        rep = repeat_by_key.get((vp, seq))
        if rep is None:
            continue
        worst = max(max(e["model"]["maxAbsErrX"], e["model"]["maxAbsErrY"]) for e in rows)
        aligned = max(e["model"]["maxAbsErrXTimeAligned"] for e in rows)
        final = max(max(e["model"]["finalErrX"], e["model"]["finalErrY"]) for e in rows)
        floor = 12.0   # world units; a sequence that moves nothing must not gate at zero
        allowed = max(2 * rep["worstPointwiseSpreadX"], floor)
        against_noise.append({
            "viewport": vp, "sequence": seq,
            "targetSelfRepeatability": rep["worstPointwiseSpreadX"],
            "modelWorstResidual": round(worst, 4),
            "modelWorstResidualTimeAligned": round(aligned, 4),
            "modelWorstFinalErr": round(final, 4),
            "allowed": round(allowed, 4),
            "rule": "max(2 * target self-repeatability, 12 world units)",
            # The raw peak is dominated by a sub-frame phase offset between the
            # recorder's frame callback and the page's: at 5000 units/s a 10 ms
            # offset is 50 units on its own. The aligned peak is the part of the
            # residual the MODEL owns, and the final error is where the motion
            # actually came to rest -- neither is a substitute for the other, so
            # all three are recorded.
            "withinTargetNoiseRaw": worst <= allowed,
            "withinTargetNoise": aligned <= allowed,
            "finalWithinTargetNoise": final <= allowed,
        })

    judged = [e for e in per_run if e["sequence"] not in TRAJECTORY_EXCLUDED]
    shifts = [e["model"]["bestTimeShiftMs"] for e in judged
              if e["model"]["bestTimeShiftMs"] is not None]
    model_summary = {
        "trajectoryExcluded": sorted(TRAJECTORY_EXCLUDED),
        "trajectoryExcludedWhy": "a resize re-tiles the grid mid-run, so the recovered "
                                 "trajectory is re-seeded and a pointwise residual across "
                                 "that boundary measures the re-seed. Judged on continuity "
                                 "instead; see resizeContinuity.",
        "runsJudged": len(judged),
        "worstMaxAbsErr": round(max([e["model"]["maxAbsErrX"] for e in judged]
                                    + [e["model"]["maxAbsErrY"] for e in judged]), 4),
        "worstRmsErr": round(max([e["model"]["rmsErrX"] for e in judged]
                                 + [e["model"]["rmsErrY"] for e in judged]), 4),
        "worstFinalErr": round(max([e["model"]["finalErrX"] for e in judged]
                                   + [e["model"]["finalErrY"] for e in judged]), 4),
        "worstFinalErrFraction": round(max(
            (max(e["model"]["finalErrX"], e["model"]["finalErrY"])
             / max(1.0, abs(e["observed"]["scrollX"]["total"]),
                   abs(e["observed"]["scrollY"]["total"])))
            for e in judged), 6),
        "worstMaxAbsErrTimeAligned": round(max(
            e["model"]["maxAbsErrXTimeAligned"] for e in judged), 4),
        "timeShiftMs": {"min": round(min(shifts), 2) if shifts else None,
                        "max": round(max(shifts), 2) if shifts else None,
                        "median": round(statistics.median(shifts), 2) if shifts else None},
        "timeShiftNote": "A single constant time offset per run, reported rather than "
                         "applied: the recorder's own frame callback, the page's render "
                         "callback and the gesture dispatch are three different points in "
                         "one frame, so a sub-frame phase difference is expected and is not "
                         "a property of the model. The raw residual is the headline; the "
                         "aligned one says how much of it is phase.",
    }

    for e in per_run:
        del e["_t"]; del e["_x"]; del e["_y"]; del e["_pt"]; del e["_px"]; del e["_py"]

    payload = {
        "what": "the motion source contract, replayed against the Target's own recorded input",
        "contract": "config/target-motion-source-v1.json",
        "contractIsSourceRead": "Every constant in the contract was read out of the Target's "
                                "application bundle. Nothing here fits a constant to a curve; "
                                "this file only asks whether the source model reproduces the "
                                "Target, and reports where it does not.",
        "trace": {"url": trace["url"], "startedAt": trace["startedAt"],
                  "repeat": trace["repeat"], "runs": len(trace["runs"])},
        "targetRepeatability": {
            "method": "the same trajectory run 3 times, resampled onto the first run's frame "
                      "times, worst pointwise spread across the runs",
            "rows": repeat_rows,
            "worstPointwiseSpreadX": round(worst_repeat, 4),
            "worstPointwiseSpreadY": round(worst_repeat_y, 4),
        },
        "modelVsTarget": model_summary,
        "modelResidualAgainstTargetNoise": {
            "what": "the model's worst residual beside the Target's own spread, per sequence",
            "rows": against_noise,
            "withinNoiseTimeAligned": sum(1 for r in against_noise if r["withinTargetNoise"]),
            "withinNoiseRaw": sum(1 for r in against_noise if r["withinTargetNoiseRaw"]),
            "finalWithinNoise": sum(1 for r in against_noise if r["finalWithinTargetNoise"]),
            "total": len(against_noise),
        },
        "resizeContinuity": [
            {"viewport": e["viewport"], "repeat": e["repeat"], **e["resizeContinuity"]}
            for e in per_run if e.get("resizeContinuity")],
        "runs": per_run,
        "consoleAndPageErrors": trace["errors"],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"target repeatability worst pointwise spread  X {worst_repeat:.3f}  Y {worst_repeat_y:.3f}")
    within = sum(1 for r in against_noise if r["withinTargetNoise"])
    raw = sum(1 for r in against_noise if r["withinTargetNoiseRaw"])
    fin = sum(1 for r in against_noise if r["finalWithinTargetNoise"])
    print(f"model residual within the Target's own noise: "
          f"time-aligned {within}/{len(against_noise)}  raw {raw}/{len(against_noise)}  "
          f"final {fin}/{len(against_noise)}")
    print(f"model vs target  worst max {model_summary['worstMaxAbsErr']:.3f}  "
          f"worst rms {model_summary['worstRmsErr']:.3f}  "
          f"worst final {model_summary['worstFinalErr']:.3f}  "
          f"time-aligned worst {model_summary['worstMaxAbsErrTimeAligned']:.3f}")
    print(f"  phase shift ms {model_summary['timeShiftMs']}  -> {out_path}")
