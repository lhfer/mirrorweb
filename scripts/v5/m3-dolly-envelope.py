#!/usr/bin/env python3
"""The camera dolly and the release, before and after the writer order.

The M2 gate failed 92 dolly rows. M2 also measured, and refuted, the mechanism
M1 had blamed: feeding the magnitude spring the Target's OWN jittered scroll
moved the dolly peak by 0.3% while the Target's observed dolly stood 17.7% (in
median absolute residual) away from the frozen law. Jitter was not it.

The mechanism was in the bundle: the magnitude source has two writers, they
disagree by roughly the drag gain, and the Target's frame scheduler runs the
gesture writer last on every frame that carries a pan dispatch. See
magnitude-writer-order-source.json for the derivation with byte offsets.

This file is the before-and-after, scored against the SAME sealed thresholds
the M2 baseline fixed before any candidate existed. Three sides on every exact
cell -- the Target, the M2 candidate (scroll writer last, the control) and the
M3 candidate (the recovered order) -- so "the dolly rows closed" is a count and
not a claim.

Both readings of the residual are reported, because they say different things:
the SIGNED median ratio is what a reviewer sees on average, and the MEDIAN
ABSOLUTE residual is what any single sequence sees. The signed number is much
the smaller of the two, because the drag and flick residuals had opposite signs
and cancelled.

Usage:
  m3-dolly-envelope.py --baseline=<dir> --target=<t> [--targetExtra=...]
                       --local=<t> [--localExtra=...]
                       [--control=<m2 trace> ...] --out=<json>
"""
from __future__ import annotations

import hashlib
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
LM = _load("m2_landmarks", "m2_landmarks.py")
R = _load("m3_replay", "m3_replay.py")
SM = _load("source_motion", "source_motion.py")

# The landmark list the brief names for this gate.
LANDMARKS = ["dollyMedianPeak3", "dollyRms30Peak", "dollyPeakTimeMs",
             "dollyEnvelopeIntegral",
             "robustReleaseVelocity50Ms", "robustReleaseVelocity75Ms",
             "robustReleaseVelocity100Ms",
             "travelAfterReleaseX", "travelAfterReleaseY",
             "timeTo50PctMs", "timeTo10PctMs", "timeToVisualStopMs"]


def readable(run):
    if run["sequence"] in LM.WHEEL_SEQUENCES or LM.reseeded(run):
        return None
    obs = MT.trajectory(run)
    live = [n for n in obs.get("liveCards", []) if n is not None]
    if live and min(live) < LM.MIN_LIVE_CARDS:
        return None
    return obs


def mean_of(vals):
    v = [x for x in vals if x is not None]
    return statistics.mean(v) if v else None


def observed_dolly_peak(run):
    persp = MT.frame_for(*run["viewport"])["perspective"]
    vs = []
    for s in run["frames"]:
        p = MT.camera_position(s)
        if p is not None:
            vs.append(math.dist(p, (0.0, 0.0, 0.0)) / persp - 1.0)
    return LM.R.median_peak(vs, 3) if len(vs) > 8 else None


def contract_dolly_peak(run, order):
    persp = MT.frame_for(*run["viewport"])["perspective"]
    maxz = SM.CAMERA["velocityDolly"]["maxZoomZFactor"] * persp
    pred = R.replay(run, writer_order=order)
    return LM.R.median_peak([SM.dolly(m, maxz) / persp for m in pred["magnitude"]], 3)


def main() -> int:
    args, t_extra, l_extra, control = {}, [], [], []
    for a in sys.argv[1:]:
        if a.startswith("--targetExtra="):
            t_extra.append(a.split("=", 1)[1])
        elif a.startswith("--localExtra="):
            l_extra.append(a.split("=", 1)[1])
        elif a.startswith("--control="):
            control.append(a.split("=", 1)[1])
        else:
            k, v = a[2:].split("=", 1)
            args[k] = v

    base_dir = Path(args["baseline"])
    body = (base_dir / "target-scheduler-invariant-baseline.json").read_text()
    sha = hashlib.sha256(body.encode()).hexdigest()
    declared = (base_dir / "target-scheduler-invariant-baseline.sha256").read_text().split()[0]
    if sha != declared:
        print("BASELINE SHA MISMATCH", file=sys.stderr)
        return 2
    baseline = json.loads(body)

    def load(paths):
        runs = []
        for p in paths:
            runs.extend(json.loads(Path(p).read_text())["runs"])
        return runs

    sides = {"candidate": load([args["local"]] + l_extra)}
    if control:
        sides["m2Control"] = load(control)
    target_runs = load([args["target"]] + t_extra)

    rows = []
    for hz in LM.GRIDS:
        grid = f"{int(hz)}Hz"
        marks = {}
        for side, runs in sides.items():
            for run in runs:
                obs = readable(run)
                if obs is None:
                    continue
                m = LM.scheduler_invariant(run, obs, hz)
                if m:
                    marks.setdefault((run["id"], run["sequence"]), {}) \
                         .setdefault(side, []).append(m)
        for cell_key, spec in sorted(baseline["landmarks"][grid].items()):
            vp, seq = cell_key.split("|", 1)
            slot = marks.get((vp, seq), {})
            for name in LANDMARKS:
                if name not in spec:
                    continue
                s = spec[name]
                row = {"grid": grid, "viewport": vp, "sequence": seq, "landmark": name,
                       "exactCellKey": f"{grid}|{vp}|{seq}|{name}",
                       "target": s["targetMean"], "threshold": s["threshold"],
                       "gateType": s["gateType"], "productGated": s["productGated"]}
                for side in ("m2Control", "candidate"):
                    v = mean_of([m.get(name) for m in slot.get(side, [])])
                    row[side] = None if v is None else round(v, 5)
                    if v is None:
                        row[f"{side}Status"] = "INSTRUMENT_UNREADABLE"
                        continue
                    ok, status = LM.judge(name, v, s["targetMean"], s["threshold"])
                    if not s["productGated"]:
                        status = "ACCEPTED_DEVIATION" if not ok else status
                        ok = True
                    row[f"{side}Status"] = status
                    row[f"{side}Pass"] = ok
                    row[f"{side}Delta"] = round(v - s["targetMean"], 5)
                rows.append(row)

    # The dolly ratio, both orders, on the Target's own input. This is the
    # measurement the round turns on and it is repeated here so the dolly file
    # stands on its own.
    ratios = {"gestureLastWhileActive": [], "scrollLastAlways": []}
    for run in target_runs:
        if readable(run) is None:
            continue
        a = observed_dolly_peak(run)
        if a is None:
            continue
        for order in ratios:
            b = contract_dolly_peak(run, order)
            if b > 1e-9:
                ratios[order].append(a / b)

    def summarise(v):
        if not v:
            return None
        return {"signedMedianRatio": round(statistics.median(v), 4),
                "signedMedianPercent": round((statistics.median(v) - 1) * 100, 2),
                "medianAbsoluteResidual": round(
                    statistics.median([abs(x - 1) for x in v]), 4),
                "medianAbsoluteResidualPercent": round(
                    statistics.median([abs(x - 1) for x in v]) * 100, 2),
                "runs": len(v)}

    def count(side, prefix):
        got = [r for r in rows if r.get(f"{side}Status") is not None
               and r["landmark"].startswith(prefix)]
        return {"cells": len(got),
                "failed": sum(1 for r in got if r.get(f"{side}Status") == "FAIL"),
                "unreadable": sum(1 for r in got
                                  if r.get(f"{side}Status") == "INSTRUMENT_UNREADABLE")}

    doc = {
        "what": "the camera dolly and the release, scored against the sealed M2 baseline, "
                "with the M2 candidate beside the M3 candidate",
        "baselineSha256": sha,
        "landmarks": LANDMARKS,
        "grids": [f"{int(h)}Hz" for h in LM.GRIDS],
        "dollyResidualOnTheTargetsOwnInput": {
            "what": "the Target's observed dolly peak divided by the frozen law "
                    "replayed on the Target's own input, once per writer order",
            "readBothWays": "the SIGNED median ratio and the MEDIAN ABSOLUTE residual "
                            "say different things and both are reported. Under the "
                            "pre-M3 order the signed number is much the smaller of the "
                            "two because the drag and flick residuals have opposite "
                            "signs and cancel: reporting only the signed number "
                            "understates what any single sequence shows.",
            "replayAndClock":
                "scripts/v5/m3_replay.py, gesture history stamped from the event's own "
                "timeStamp. magnitude-writer-order-source.json reports the same ratio "
                "through the same replay; these are the numbers to quote.",
            "scrollLastAlways": summarise(ratios["scrollLastAlways"]),
            "gestureLastWhileActive": summarise(ratios["gestureLastWhileActive"]),
        },
        "dollyCells": {"m2Control": count("m2Control", "dolly"),
                       "candidate": count("candidate", "dolly")},
        "releaseCells": {
            "m2Control": {k: count("m2Control", p)[k]
                          for p in ("robustReleaseVelocity",) for k in ("cells", "failed")},
            "candidate": {k: count("candidate", p)[k]
                          for p in ("robustReleaseVelocity",) for k in ("cells", "failed")},
        },
        "allCells": {"m2Control": count("m2Control", ""),
                     "candidate": count("candidate", "")},
        "rows": rows,
    }
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n")
    d = doc["dollyResidualOnTheTargetsOwnInput"]
    print(f"dolly envelope -> {out}")
    print(f"  scrollLastAlways        signed {d['scrollLastAlways']['signedMedianRatio']} "
          f"absolute {d['scrollLastAlways']['medianAbsoluteResidualPercent']}%")
    print(f"  gestureLastWhileActive  signed {d['gestureLastWhileActive']['signedMedianRatio']} "
          f"absolute {d['gestureLastWhileActive']['medianAbsoluteResidualPercent']}%")
    print(f"  dolly cells failed: m2Control {doc['dollyCells']['m2Control']['failed']}"
          f"/{doc['dollyCells']['m2Control']['cells']}"
          f"  candidate {doc['dollyCells']['candidate']['failed']}"
          f"/{doc['dollyCells']['candidate']['cells']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
