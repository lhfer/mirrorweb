#!/usr/bin/env python3
"""Does the FROZEN CONTRACT reproduce the Target? Landmark by landmark.

WHY THIS DECIDES THE ROUND
--------------------------
The gate compares our page against the Target. When a landmark fails, that
comparison alone cannot say which of two very different things happened:

  (i)  our engine does not implement the frozen contract, or
  (ii) the frozen contract does not reproduce the Target, and our engine
       implements it faithfully.

Those need opposite responses -- (i) is a code defect, (ii) is a Source
Baseline residual this round accepted and is forbidden to re-fit -- and they
are indistinguishable from the candidate-vs-Target number alone.

So this replays the frozen contract on the TARGET'S OWN recorded input,
computes the SAME scheduler-invariant landmarks on the prediction, and compares
them with the landmarks computed on what the Target actually did, against the
SAME sealed thresholds. A landmark the contract already misses on the Target's
own input is a landmark no faithful implementation of that contract can pass.

Only the scroll-derived landmarks are covered here -- travel, follow ratio,
release velocity, decay times, overshoot, reversals. The orbit and the dolly
are read from the camera matrix rather than from the scroll, so they cannot be
computed from a replay; the dolly gets its own three-way attribution in
m2-dolly-attribution.py.

Usage:
  m2-contract-vs-target.py --baseline=<dir> --target=<trace> [--targetExtra=...]
                           --out=<json>
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
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
R = _load("m2_replay", "m2_replay.py")

# Landmarks read off the scroll trajectory, and therefore computable from a
# replay. Everything else comes from the camera matrix.
SCROLL_LANDMARKS = {
    "totalX", "totalY", "restX", "restY", "residualDriftX",
    "velocityIntegralX", "velocityIntegralY", "overshootX", "overshootY",
    "directionReversals", "followRatioX", "followRatioY",
    "robustReleaseVelocity50Ms", "robustReleaseVelocity75Ms",
    "robustReleaseVelocity100Ms",
    "timeTo50PctMs", "timeTo10PctMs", "timeToVisualStopMs",
    "travelAfterReleaseX", "travelAfterReleaseY",
}


def main() -> int:
    args, extra = {}, []
    for a in sys.argv[1:]:
        if a.startswith("--targetExtra="):
            extra.append(a.split("=", 1)[1])
        elif a.startswith("--"):
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

    runs = []
    for p in [args["target"]] + extra:
        runs.extend(json.loads(Path(p).read_text())["runs"])

    rows = []
    for hz in LM.GRIDS:
        grid = f"{int(hz)}Hz"
        cells = {}
        for run in runs:
            if run["sequence"] in LM.WHEEL_SEQUENCES or LM.reseeded(run):
                continue
            obs = MT.trajectory(run)
            live = [n for n in obs.get("liveCards", []) if n is not None]
            if live and min(live) < LM.MIN_LIVE_CARDS:
                continue
            try:
                pred = R.replay(run)
            except ValueError:
                continue
            # The contract's own trajectory, dressed as an observation so the
            # SAME landmark reader runs on it. Nothing else about the run is
            # substituted: the release time, the drag span and the viewport all
            # still come from the Target's own recording.
            synth = {"t": pred["t"], "scrollX": pred["scrollX"],
                     "scrollY": pred["scrollY"], "liveCards": obs.get("liveCards", [])}
            m_pred = LM.scheduler_invariant(run, synth, hz)
            m_obs = LM.scheduler_invariant(run, obs, hz)
            if not m_pred or not m_obs:
                continue
            cells.setdefault((run["id"], run["sequence"]), []).append((m_obs, m_pred))

        for (vp, seq), lst in sorted(cells.items()):
            spec = baseline["landmarks"][grid].get(f"{vp}|{seq}")
            if not spec:
                continue
            for name in sorted(SCROLL_LANDMARKS):
                if name not in spec:
                    continue
                o = [a.get(name) for a, _ in lst if a.get(name) is not None]
                p_ = [b.get(name) for _, b in lst if b.get(name) is not None]
                if not o or not p_:
                    continue
                om, pm = statistics.mean(o), statistics.mean(p_)
                thr = spec[name]["threshold"]
                ok, status = LM.judge(name, pm, om, thr)
                rows.append({
                    "grid": grid, "viewport": vp, "sequence": seq, "landmark": name,
                    "targetObserved": round(om, 5),
                    "contractPredicted": round(pm, 5),
                    "delta": round(pm - om, 5),
                    "threshold": thr,
                    "targetRepeatability": spec[name]["repeatabilitySpread"],
                    "gateType": spec[name]["gateType"],
                    "contractReproducesTarget": ok,
                    "status": status,
                })

    fails = [r for r in rows if not r["contractReproducesTarget"]]
    by_lm = {}
    for r in fails:
        by_lm.setdefault(r["landmark"], 0)
        by_lm[r["landmark"]] += 1
    totals = {}
    for r in rows:
        totals.setdefault(r["landmark"], 0)
        totals[r["landmark"]] += 1

    doc = {
        "what": "the frozen motion contract replayed on the TARGET'S OWN recorded input, "
                "compared with what the Target actually did, on the same landmarks and "
                "against the same sealed thresholds",
        "why": "a candidate-vs-Target failure cannot distinguish 'our engine does not "
               "implement the contract' from 'the contract does not reproduce the "
               "Target'. Those need opposite responses. This separates them.",
        "howToRead": "a landmark listed in `contractCannotReproduce` is one the FROZEN "
                     "CONTRACT already misses on the Target's own input. No faithful "
                     "implementation of that contract can pass it, so a candidate "
                     "failure on the same landmark is a Source Baseline residual and not "
                     "a code defect. Landmarks NOT listed there are ones the contract "
                     "does reproduce, where a candidate failure would be ours.",
        "scope": "scroll-derived landmarks only. The orbit and the dolly are read from "
                 "the camera matrix, not from the scroll, so they cannot be computed "
                 "from a replay; the dolly has its own three-way attribution in "
                 "dolly-attribution.json.",
        "baselineSha256": sha,
        "comparisons": len(rows),
        "contractReproducesTargetIn": len(rows) - len(fails),
        "contractCannotReproduce": dict(sorted(by_lm.items(), key=lambda kv: -kv[1])),
        "cellsPerLandmark": totals,
        "rows": rows,
    }
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2))
    print(f"contract vs target -> {out}")
    print(f"  {len(rows)} comparisons, contract reproduces the Target in "
          f"{len(rows)-len(fails)}, misses in {len(fails)}")
    for k, v in sorted(by_lm.items(), key=lambda kv: -kv[1]):
        print(f"    {k:32s} {v}/{totals[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
