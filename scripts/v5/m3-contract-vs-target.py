#!/usr/bin/env python3
"""Four numbers per exact cell, so attribution stops being a guess.

WHY THIS DECIDES THE ROUND
--------------------------
A candidate-vs-Target failure cannot say which of these happened:

  (i)   our engine does not implement the frozen contract;
  (ii)  the contract does not reproduce the Target and our engine is faithful;
  (iii) the two sides were driven by different input, because a synthetic
        gesture does not land on identical pixels at identical times twice.

They need different responses, and the candidate-vs-Target number alone cannot
tell them apart. M2 separated (i) from (ii) but then attributed by LANDMARK
NAME -- if a landmark failed anywhere on the contract's own replay, every
candidate failure carrying that name was called inherited. That shortcut is
banned this round by name, and rightly: a landmark can be reproduced perfectly
in one cell and missed in another.

So every number here is per EXACT CELL -- (grid, viewport, sequence, landmark)
-- and there are four of them:

  targetObserved            what the Target did
  contractOnTargetInput     the frozen contract, replayed on the TARGET's input
  contractOnCandidateInput  the frozen contract, replayed on OUR input
  candidateObserved         what our engine did

From those, three residuals that do not overlap:

  inherited   = contractOnTargetInput - targetObserved
  candidate   = candidateObserved     - contractOnCandidateInput
  inputStream = contractOnCandidateInput - contractOnTargetInput

WHAT THIS COVERS
----------------
Scroll-derived landmarks, and the camera dolly. The dolly is read off the
camera matrix rather than the scroll, but it is a pure function of the
magnitude spring, so the contract's own dolly envelope can be synthesised from
a replay and read with exactly the same reader. The pointer orbit is not
covered: it is read from the camera matrix and driven by pointer events whose
timing the replay does reproduce, but the orbit landmarks are already at
parity and adding a fourth partially-covered column would obscure that.

ONE INSTRUMENT LIMIT, STATED
----------------------------
Our own traces carry the RAW rAF timestamps, so a replay of our input uses the
same clock the engine used. The Target's traces predate that field and carry
`t = raf - t0` rounded to a thousandth. framer-motion's velocity window is a
strict `> 100 ms`, so a history point exactly one window old can fall on either
side of that comparison depending on the time origin -- purely in the last bit
of a double. Every Target replay is therefore run THREE times, with the
comparison nudged either way, and a cell whose answer moves is flagged
`windowBoundarySensitive` and carries both readings. It is never resolved by
picking whichever fits.

Usage:
  m3-contract-vs-target.py --baseline=<dir> --target=<trace> [--targetExtra=...]
                           --local=<trace> [--localExtra=...] --out=<json>
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

SCROLL_LANDMARKS = {
    "totalX", "totalY", "restX", "restY", "residualDriftX",
    "velocityIntegralX", "velocityIntegralY", "overshootX", "overshootY",
    "directionReversals", "followRatioX", "followRatioY",
    "robustReleaseVelocity50Ms", "robustReleaseVelocity75Ms",
    "robustReleaseVelocity100Ms",
    "timeTo50PctMs", "timeTo10PctMs", "timeToVisualStopMs",
    "travelAfterReleaseX", "travelAfterReleaseY",
}
DOLLY_LANDMARKS = {
    "dollyMedianPeak3", "dollyRms30Peak", "dollyPeakTimeMs", "dollyEnvelopeIntegral",
}
COVERED = SCROLL_LANDMARKS | DOLLY_LANDMARKS

# The nudge is the smallest that can move a strict `>` comparison on a number
# near 100. It is not a tolerance and it is never used to choose an answer.
EPS = 1e-9


def readable(run):
    if run["sequence"] in LM.WHEEL_SEQUENCES or LM.reseeded(run):
        return None
    obs = MT.trajectory(run)
    live = [n for n in obs.get("liveCards", []) if n is not None]
    if live and min(live) < LM.MIN_LIVE_CARDS:
        return None
    return obs


_REPLAY_CACHE: dict = {}


def cached_replay(run, epsilon):
    """The replay does not depend on the resampling grid, so run it once."""
    key = (id(run), epsilon)
    if key not in _REPLAY_CACHE:
        try:
            _REPLAY_CACHE[key] = R.replay(run, window_epsilon=epsilon)
        except ValueError:
            _REPLAY_CACHE[key] = None
    return _REPLAY_CACHE[key]


def predicted_marks(run, obs, hz, epsilon=0.0):
    """Landmarks of the contract's own trajectory, read with the same reader."""
    pred = cached_replay(run, epsilon)
    if pred is None:
        return None
    persp = MT.frame_for(*run["viewport"])["perspective"]
    maxz = SM.CAMERA["velocityDolly"]["maxZoomZFactor"] * persp
    synth = {"t": pred["t"], "scrollX": pred["scrollX"], "scrollY": pred["scrollY"],
             "liveCards": obs.get("liveCards", [])}
    dolly = (pred["t"], [SM.dolly(m, maxz) / persp for m in pred["magnitude"]])
    return LM.scheduler_invariant(run, synth, hz, dolly=dolly)


def mean_of(vals):
    v = [x for x in vals if x is not None]
    return statistics.mean(v) if v else None


def main() -> int:
    args, t_extra, l_extra = {}, [], []
    for a in sys.argv[1:]:
        if a.startswith("--targetExtra="):
            t_extra.append(a.split("=", 1)[1])
        elif a.startswith("--localExtra="):
            l_extra.append(a.split("=", 1)[1])
        else:
            k, v = a[2:].split("=", 1)
            args[k] = v

    base_dir = Path(args["baseline"])
    body = (base_dir / "target-scheduler-invariant-baseline.json").read_text()
    sha = hashlib.sha256(body.encode()).hexdigest()
    declared = (base_dir / "target-scheduler-invariant-baseline.sha256").read_text().split()[0]
    if sha != declared:
        print("BASELINE SHA MISMATCH -- refusing to run against a modified baseline",
              file=sys.stderr)
        return 2
    baseline = json.loads(body)

    def load(paths):
        runs = []
        for p in paths:
            runs.extend(json.loads(Path(p).read_text())["runs"])
        return runs

    target_runs = load([args["target"]] + t_extra)
    local_runs = load([args["local"]] + l_extra)

    rows, sensitive = [], []
    for hz in LM.GRIDS:
        grid = f"{int(hz)}Hz"
        cells = {}
        for side, runs in (("target", target_runs), ("candidate", local_runs)):
            for run in runs:
                obs = readable(run)
                if obs is None:
                    continue
                m_obs = LM.scheduler_invariant(run, obs, hz)
                m_pred = predicted_marks(run, obs, hz)
                if not m_obs or not m_pred:
                    continue
                key = (run["id"], run["sequence"])
                slot = cells.setdefault(key, {"target": [], "candidate": []})
                entry = {"obs": m_obs, "pred": m_pred}
                if side == "target":
                    # The Target's traces carry no raw rAF clock, so the window
                    # boundary is bracketed rather than assumed.
                    entry["predLo"] = predicted_marks(run, obs, hz, -EPS)
                    entry["predHi"] = predicted_marks(run, obs, hz, +EPS)
                slot[side].append(entry)

        for (vp, seq), slot in sorted(cells.items()):
            spec = baseline["landmarks"][grid].get(f"{vp}|{seq}")
            if not spec:
                continue
            for name in sorted(COVERED):
                if name not in spec:
                    continue
                t_obs = mean_of([e["obs"].get(name) for e in slot["target"]])
                t_pred = mean_of([e["pred"].get(name) for e in slot["target"]])
                c_obs = mean_of([e["obs"].get(name) for e in slot["candidate"]])
                c_pred = mean_of([e["pred"].get(name) for e in slot["candidate"]])
                if t_obs is None or t_pred is None:
                    continue
                lo = mean_of([(e.get("predLo") or {}).get(name) for e in slot["target"]])
                hi = mean_of([(e.get("predHi") or {}).get(name) for e in slot["target"]])
                thr = spec[name]["threshold"]
                boundary = (lo is not None and hi is not None
                            and abs(hi - lo) > max(1e-9, 0.01 * thr))
                ok, status = LM.judge(name, t_pred, t_obs, thr)
                row = {
                    "grid": grid, "viewport": vp, "sequence": seq, "landmark": name,
                    "exactCellKey": f"{grid}|{vp}|{seq}|{name}",
                    "targetObserved": round(t_obs, 5),
                    "contractOnTargetInput": round(t_pred, 5),
                    "contractOnCandidateInput": None if c_pred is None else round(c_pred, 5),
                    "candidateObserved": None if c_obs is None else round(c_obs, 5),
                    "inheritedResidual": round(t_pred - t_obs, 5),
                    "candidateResidual": (None if c_obs is None or c_pred is None
                                          else round(c_obs - c_pred, 5)),
                    "inputStreamResidual": (None if c_pred is None
                                            else round(c_pred - t_pred, 5)),
                    "threshold": thr,
                    "targetRepeatability": spec[name]["repeatabilitySpread"],
                    "gateType": spec[name]["gateType"],
                    "productGated": spec[name]["productGated"],
                    "contractReproducesTarget": ok,
                    "status": status,
                    "windowBoundarySensitive": boundary,
                    "contractOnTargetInputWindowLow": None if lo is None else round(lo, 5),
                    "contractOnTargetInputWindowHigh": None if hi is None else round(hi, 5),
                }
                rows.append(row)
                if boundary:
                    sensitive.append(row["exactCellKey"])

    fails = [r for r in rows if not r["contractReproducesTarget"]]
    # A reviewer's first question about a bracketed replay is whether the cells
    # the contract MISSES are the same cells the bracket cannot resolve -- i.e.
    # whether "the contract misses N cells" is a measurement or an artefact of
    # the window boundary. It is answered here rather than left to be asked.
    fails_boundary = [r for r in fails if r["windowBoundarySensitive"]]
    closes = []
    for r in fails_boundary:
        lo = r["contractOnTargetInputWindowLow"]
        hi = r["contractOnTargetInputWindowHigh"]
        t_obs = r["targetObserved"]
        thr = r["threshold"]
        for alt in (lo, hi):
            if alt is None:
                continue
            if LM.judge(r["landmark"], alt, t_obs, thr)[0]:
                closes.append(r["exactCellKey"])
                break
    by_lm, totals = {}, {}
    for r in rows:
        totals[r["landmark"]] = totals.get(r["landmark"], 0) + 1
    for r in fails:
        by_lm[r["landmark"]] = by_lm.get(r["landmark"], 0) + 1

    doc = {
        "what": "four numbers per exact cell: what the Target did, what the frozen "
                "contract does on the Target's own input, what it does on ours, and "
                "what our engine did",
        "why": "so a failure can be attributed to the contract, to our engine or to the "
               "difference between two synthetic input streams, per cell rather than "
               "per landmark name.",
        "exactCellKey": "grid|viewport|sequence|landmark",
        "residuals": {
            "inheritedResidual": "contractOnTargetInput - targetObserved. The frozen "
                                 "contract's own distance from the Target. No faithful "
                                 "implementation of that contract can close it.",
            "candidateResidual": "candidateObserved - contractOnCandidateInput. How far "
                                 "our engine is from the contract on the same input. "
                                 "This one is ours.",
            "inputStreamResidual": "contractOnCandidateInput - contractOnTargetInput. "
                                   "The same contract, two input streams. Neither an "
                                   "engine defect nor a contract defect.",
        },
        "scope": "scroll-derived landmarks and the camera dolly. The dolly is read off "
                 "the camera matrix, but it is a pure function of the magnitude spring, "
                 "so the contract's own envelope is synthesised from the replay and read "
                 "with the same reader. The pointer orbit is not covered here.",
        "windowBoundary": {
            "what": "the Target's traces carry no raw rAF timestamp, and the library's "
                    "velocity window is a strict `> 100 ms`. A history point exactly one "
                    "window old lands on either side of that comparison depending on the "
                    "time origin -- 7048.6-6948.6 is 99.99999999999909 and 142.3-42.3 is "
                    "100.00000000000001.",
            "howItIsHandled": "every Target replay is run three times, nudged either way "
                              "by 1e-9, and a cell whose answer moves by more than 1% of "
                              "its own threshold is flagged with both readings. It is "
                              "never resolved by picking the one that fits.",
            "sensitiveCells": len(sensitive),
            "sensitiveCellKeys": sorted(set(sensitive)),
            "amongTheCellsTheContractMisses": {
                "misses": len(fails),
                "ofThoseWindowBoundarySensitive": len(fails_boundary),
                "ofThoseThatWouldCloseUnderTheOtherReading": len(closes),
                "cellsThatWouldClose": sorted(set(closes)),
                "reading": "a miss that would close under the other reading is not "
                           "counted as closed. It is reported here and left as a miss, "
                           "because choosing the reading that fits is the failure mode "
                           "this bracket exists to prevent. The number that matters for "
                           "attribution is the first one: the contract's misses that are "
                           "NOT boundary sensitive are measurements the boundary cannot "
                           "explain away.",
            },
            "notAnIssueOnOurSide": "our traces carry the raw rAF timestamps the engine "
                                   "stamped its own history with, so there is nothing to "
                                   "bracket -- see release-history-proof.json.",
        },
        "baselineSha256": sha,
        "comparisons": len(rows),
        "contractReproducesTargetIn": len(rows) - len(fails),
        "contractCannotReproduce": dict(sorted(by_lm.items(), key=lambda kv: -kv[1])),
        "cellsPerLandmark": totals,
        "rows": rows,
    }
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"contract vs target v2 -> {out}")
    print(f"  {len(rows)} exact cells, contract reproduces the Target in "
          f"{len(rows)-len(fails)}, misses in {len(fails)}, "
          f"{len(set(sensitive))} window-boundary sensitive")
    for k, v in sorted(by_lm.items(), key=lambda kv: -kv[1]):
        print(f"    {k:32s} {v}/{totals[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
