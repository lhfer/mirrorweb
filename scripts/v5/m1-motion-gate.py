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
    "latencyMs": 34.0,          # two frames at 60 Hz
    "orbitRad": 0.002,
    "settleMs": 34.0,           # two frames at 60 Hz
    "zeroMotionWorldUnits": 1.0,
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


def landmarks(run, obs):
    """Input-normalised numbers, so two event streams can be compared."""
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
                    "maxFrameVelocityStep": decay["maxFrameVelocityStep"]})

    pt = MT.pointer_track(run)
    if pt:
        out["orbitYawMin"] = round(min(p[1] for p in pt), 6)
        out["orbitYawMax"] = round(max(p[1] for p in pt), 6)
        out["orbitPitchMin"] = round(min(p[2] for p in pt), 6)
        out["orbitPitchMax"] = round(max(p[2] for p in pt), 6)
    # Amplitude is not dynamics. Two pages can orbit to the same extremes and
    # get there at completely different speeds, so the smoothing constant is
    # its own landmark.
    settle = MT.pointer_settle_63(run)
    if settle is not None:
        out["pointerSettle63Ms"] = settle
    return out


LANDMARK_UNIT = {
    "totalX": "travelWorldUnits", "totalY": "travelWorldUnits",
    "followRatioX": "followRatio", "followRatioY": "followRatio",
    "latencyMs": "latencyMs",
    "releaseVelocity": "releaseVelocity",
    "timeTo50PctMs": "decayMs", "timeTo10PctMs": "decayMs",
    "timeToVisualStopMs": "decayMs",
    "travelAfterRelease": "travelWorldUnits",
    "maxFrameVelocityStep": "releaseVelocity",
    "orbitYawMin": "orbitRad", "orbitYawMax": "orbitRad",
    "orbitPitchMin": "orbitRad", "orbitPitchMax": "orbitRad",
    "pointerSettle63Ms": "settleMs",
}


def wrap_continuity(run, obs):
    """Does a card ever jump on screen when the grid wraps?

    Wrapping is supposed to be invisible: a card that leaves one edge reappears
    at the other, and the page hides it while it is out of view. A wrap is a
    defect only if a card that is LIVE in both frames moves by far more than the
    field moved -- that is a visible teleport rather than a recycle.

    Both sides are measured from the same recorded matrices, so this asks the
    same question of the Target as of us.
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
    return {"framePairs": len(frames) - 1, "cardFrameChecks": checked,
            "visibleTeleports": jumps, "worstExcessWorldUnits": round(worst, 3),
            "worstAt": worst_at}


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
    for e in extra_l:
        local["runs"].extend(e["runs"])

    T, L = analyse(target), analyse(local)

    # ---- 1. Target repeatability, and the thresholds it produces -----------
    thresholds, repeat_rows = {}, []
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
    })

    w("flick-decay.json", {
        "what": "release velocity and the decay curve after it",
        "note": "the Target has no decay law of its own: the release is a single jump of "
                "velocity * 0.1 on the spring's target, and the spring carries the rest. "
                "maxFrameVelocityStep is the abrupt-stop check.",
        "rows": [r for r in compare_rows
                 if r.get("landmark") in ("releaseVelocity", "timeTo50PctMs", "timeTo10PctMs",
                                          "timeToVisualStopMs", "travelAfterRelease",
                                          "maxFrameVelocityStep")],
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
                 or r.get("landmark") == "pointerSettle63Ms"],
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
        "what": "does any visible card teleport when the infinite grid recycles?",
        "rule": "a card live in two consecutive frames must not move by more than "
                "max(4x, +40) the field's own median step",
        "rows": wrap_rows,
        "visibleTeleports": sum(r["visibleTeleports"] for r in wrap_rows),
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

    verdict = "PASS" if not failures else "FAIL"
    summary = {
        "verdict": verdict,
        "landmarkComparisons": len([r for r in compare_rows if "pass" in r]),
        "landmarkFailures": failures,
        "notMeasurableOnBothSides": [r for r in compare_rows if r.get("status")],
        "wheel": {"passed": sum(1 for r in wheel_rows if r["pass"]), "total": len(wheel_rows)},
        "visibleTeleports": sum(r["visibleTeleports"] for r in wrap_rows),
        "runsThatDidNotComeToRest": [
            {k: r[k] for k in ("side", "viewport", "sequence", "repeat")}
            for r in touch_rows if r["cameToRestByEndOfRun"] is False],
        "engineVsContractWorstFinalErrFraction": round(
            max((r["finalErrFraction"] for r in engine_rows), default=0.0), 6),
    }
    w("gate-summary.json", summary)
    passed = summary["landmarkComparisons"] - len(failures)
    print(f"motion gate {verdict}  landmarks {passed}/{summary['landmarkComparisons']}  "
          f"wheel {summary['wheel']['passed']}/{summary['wheel']['total']}  "
          f"engine-vs-contract worst final {summary['engineVsContractWorstFinalErrFraction']:.5f}")
    for f in failures[:25]:
        print(f"  FAIL {f['viewport']:9} {f['sequence']:22} {f['landmark']:20} "
              f"target={f['target']} ours={f['ours']} delta={f['delta']} thr={f['threshold']}")
