#!/usr/bin/env python3
"""The scheduler-invariant motion gate: the candidate against a sealed baseline.

WHAT THIS ROUND CHANGED, AND WHY
--------------------------------
1. The baseline is READ, not computed here. It was written by m2-baseline.py
   from the Target alone and committed before the candidate was captured. This
   script recomputes its SHA-256 and refuses to run against a modified copy, so
   "the floors were not moved after seeing the candidate" is enforced rather
   than promised.

2. The systematic-sign summary is DIRECTION-AWARE. The M1 gate applied the
   one-sided rule per cell and then a plain two-sided sign test to the summary,
   so a candidate that was smoother than the Target in every single cell -- the
   one thing a one-sided-upper landmark exists to allow -- was reported as a
   systematic FAIL. Three landmarks failed that way and not one of them was a
   defect.

3. Landmarks are read off a uniform 120 Hz and 60 Hz timeline. The Target
   computes in framer-motion's frame loop and paints in r3f's; we do both in
   one. That difference moves every single-frame number and none of the
   landmarks a viewer can see. The single-frame numbers are still computed and
   still written out -- under MOTION-EXC-01, where the product decided them.

4. Engine-vs-contract is measured against the engine's OWN published state,
   read in the same frame callback as the DOM, and replayed in true callback
   order. No card-matrix recovery is involved, so it tests the engine and not
   the reader.

Usage:
  m2-motion-gate.py --baseline=<dir> --target=<trace> [--targetExtra=...]
                    --local=<trace> [--localExtra=...] --out=<dir>
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
MC = _load("m0_motion_contract", "m0-motion-contract.py")
LM = _load("m2_landmarks", "m2_landmarks.py")
R = _load("m2_replay", "m2_replay.py")
G1 = _load("m1_motion_gate", "m1-motion-gate.py")   # wrap / resize definitions, unchanged

STATUS_PASS = {"PASS", "SMOOTHER_THAN_TARGET", "STRONGER_THAN_TARGET"}


def group(runs):
    out = {}
    for run in runs:
        out.setdefault((run["id"], run["sequence"]), []).append(run)
    return out


def load_runs(paths):
    runs, errors = [], []
    for p in paths:
        d = json.loads(Path(p).read_text())
        errors.extend(d.get("errors", []))
        runs.extend(d["runs"])
    return runs, errors


def mean_of(vals):
    v = [x for x in vals if x is not None]
    return statistics.mean(v) if v else None


def sign_test_p(n, k):
    tail = min(k, n - k)
    return min(1.0, 2.0 * sum(math.comb(n, i) for i in range(tail + 1)) / (2 ** n))


# ---------------------------------------------------------------------------
# engine vs contract, v2
# ---------------------------------------------------------------------------

def engine_vs_contract(runs, worst_recovery):
    """The engine against the frozen contract, on the engine's own numbers.

    The M1 version compared a model replay against a trajectory RECOVERED from
    the card matrices, with events attributed to frames by a clock comparison
    that was wrong nine times in ten. It reported a persistent final error of
    2.6% to 14.6% of travel, identical to four decimal places on every repeat
    of a sequence -- which is the signature of a constant, not of an engine.

    This version reads the engine's own published state in the same frame
    callback as the DOM, replays the contract in true callback order, and
    compares field by field. The recovery is still measured, against that same
    truth, because the Target comparison depends on it being accurate -- but no
    verdict here goes through it.

    Absolute gate: final target error <= max(4 * worst recovery error, 0.1).
    """
    limit = max(4.0 * worst_recovery, 0.1)
    rows, misses = [], []
    for run in runs:
        if not R.has_order(run):
            continue
        tx = R.truth_series(run, "scrollX")
        if tx is None:
            continue
        pred = R.replay(run)
        # Every run starts from wherever the previous one left the page -- the
        # recorder never resets the engine, because the Target cannot be reset
        # and one recorder drives both. So the comparison is of the run's own
        # displacement, which is what a trajectory comparison is anyway.
        def rel(field):
            s = R.truth_series(run, field)
            return None if s is None or s[0] is None else [v - s[0] for v in s]

        obs_x, obs_y = rel("scrollX"), rel("scrollY")
        tgt_x, tgt_y = rel("scrollTargetX"), rel("scrollTargetY")
        travel = max(1.0, abs(obs_x[-1] - obs_x[0]), abs(obs_y[-1] - obs_y[0]))
        ex = [abs(a - b) for a, b in zip(pred["scrollX"], obs_x)]
        ey = [abs(a - b) for a, b in zip(pred["scrollY"], obs_y)]
        etx = [abs(a - b) for a, b in zip(pred["targetX"], tgt_x)]
        ety = [abs(a - b) for a, b in zip(pred["targetY"], tgt_y)]

        steps = R.truth_series(run, "motionSteps")
        step_deltas = sorted({steps[i] - steps[i - 1] for i in range(1, len(steps))
                              if steps[i] is not None and steps[i - 1] is not None})
        lrs = R.truth_series(run, "lastReleaseStep")
        eng_rel_idx = None
        if lrs and lrs[-1] is not None and lrs[-1] >= 0 and steps[0] is not None:
            eng_rel_idx = lrs[-1] - steps[0]
        rv = R.truth_series(run, "releaseVelocityX")
        rvy = R.truth_series(run, "releaseVelocityY")

        # The sub-frame ambiguity, measured rather than assumed away.
        #
        # The callback counter orders events against OUR sample callback. The
        # page's own frame callback is elsewhere in the same rAF block and is
        # not visible from outside, so an event dispatched between the two has
        # a lower `ord` than our sample but was not seen by the page until the
        # next frame. Replaying a second time with the release pinned to the
        # frame the engine RECORDED committing it on bounds how much that
        # window can be worth.
        pinned_delta = None
        try:
            pin = R.replay(run, pin_release_step=True)
            pinned_delta = round(max(abs(a - b) for a, b in
                                     zip(pin["scrollX"], pred["scrollX"])), 6)
        except Exception:
            pinned_delta = None

        final_target_err = max(etx[-1], ety[-1])
        final_value_err = max(ex[-1], ey[-1])
        ok = final_target_err <= limit and final_value_err <= limit
        row = {
            "viewport": run["id"], "sequence": run["sequence"], "repeat": run["repeat"],
            "frames": len(run["frames"]), "travel": round(travel, 3),
            "springValueMaxErr": round(max(max(ex), max(ey)), 6),
            "springValueFinalErr": round(final_value_err, 6),
            "springTargetMaxErr": round(max(max(etx), max(ety)), 6),
            "springTargetFinalErr": round(final_target_err, 6),
            "finalErrFraction": round(final_value_err / travel, 8),
            "finalRestValueOurs": round(obs_x[-1], 4),
            "finalRestValueContract": round(pred["scrollX"][-1], 4),
            "engineReleaseFrameIndex": eng_rel_idx,
            "contractReleaseFrameIndex": pred["releaseStep"] if pred["releaseStep"] >= 0 else None,
            "releaseFrameAgrees": (eng_rel_idx == pred["releaseStep"]
                                   if eng_rel_idx is not None and pred["releaseStep"] >= 0
                                   else None),
            "engineReleaseVelocity": [round(rv[-1], 4) if rv and rv[-1] is not None else None,
                                      round(rvy[-1], 4) if rvy and rvy[-1] is not None else None],
            "contractReleaseVelocity": [round(pred["releaseVelocity"][0], 4),
                                        round(pred["releaseVelocity"][1], 4)],
            "engineStepsPerRecordedFrame": step_deltas,
            "subFrameAmbiguityWorldUnits": pinned_delta,
            "eventsAfterLastFrame": pred["eventsAfterLastFrame"],
            "attribution": R.attribution_stats(run),
            "threshold": round(limit, 6),
            "status": "PASS" if ok else "FAIL",
        }
        rows.append(row)
        if not ok:
            misses.append(row)
    return rows, misses, limit


def recovery_accuracy(runs):
    """How close the card-matrix recovery is to the engine's own scroll.

    This is what licenses using the recovery on a Target that publishes
    nothing. Measured on OUR page, where both numbers exist, frame by frame,
    read in the same callback.
    """
    rows = []
    for run in runs:
        tx = R.truth_series(run, "scrollX")
        ty = R.truth_series(run, "scrollY")
        if tx is None:
            continue
        obs = MT.trajectory(run)
        live = [n for n in obs.get("liveCards", []) if n is not None]
        if live and min(live) < LM.MIN_LIVE_CARDS:
            continue
        rx = [abs(a - (b - tx[0])) for a, b in zip(obs["scrollX"], tx)]
        ry = [abs(a - (b - ty[0])) for a, b in zip(obs["scrollY"], ty)]
        rows.append({"viewport": run["id"], "sequence": run["sequence"],
                     "repeat": run["repeat"],
                     "worstX": round(max(rx), 6), "worstY": round(max(ry), 6),
                     "medianX": round(statistics.median(rx), 6)})
    worst = max((max(r["worstX"], r["worstY"]) for r in rows), default=0.03)
    return rows, worst


# ---------------------------------------------------------------------------

def main() -> int:
    args, t_extra, l_extra = {}, [], []
    for a in sys.argv[1:]:
        if a.startswith("--targetExtra="):
            t_extra.append(a.split("=", 1)[1])
        elif a.startswith("--localExtra="):
            l_extra.append(a.split("=", 1)[1])
        elif a.startswith("--"):
            k, v = a[2:].split("=", 1)
            args[k] = v

    base_dir = Path(args["baseline"])
    base_path = base_dir / "target-scheduler-invariant-baseline.json"
    sha_path = base_dir / "target-scheduler-invariant-baseline.sha256"
    body = base_path.read_text()
    actual = hashlib.sha256(body.encode()).hexdigest()
    declared = sha_path.read_text().split()[0]
    if actual != declared:
        print("BASELINE SHA MISMATCH -- refusing to gate against a modified baseline",
              file=sys.stderr)
        print(f"  declared {declared}\n  actual   {actual}", file=sys.stderr)
        return 2
    baseline = json.loads(body)

    target_runs, target_errors = load_runs([args["target"]] + t_extra)
    local_runs, local_errors = load_runs([args["local"]] + l_extra)
    for side, runs in (("target", target_runs), ("ours", local_runs)):
        bad = [r for r in runs if not R.has_order(r)]
        if bad:
            print(f"{side}: {len(bad)} runs carry no callback order -- M1 traces",
                  file=sys.stderr)
            return 2

    out_dir = Path(args["out"])
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- 1. engine against the contract, on the engine's own numbers -------
    rec_rows, worst_recovery = recovery_accuracy(local_runs)
    evc_rows, evc_misses, evc_limit = engine_vs_contract(local_runs, worst_recovery)

    # ---- 2. landmarks -----------------------------------------------------
    T, L = group(target_runs), group(local_runs)
    obs_cache = {}

    def obs_of(run):
        k = id(run)
        if k not in obs_cache:
            obs_cache[k] = MT.trajectory(run)
        return obs_cache[k]

    compare_rows, failures, unreadable = [], [], []
    ours_marks = {}
    for hz in LM.GRIDS:
        grid_key = f"{int(hz)}Hz"
        cells = {}
        parity = {}
        for key, runs in sorted(L.items()):
            for run in runs:
                obs = obs_of(run)
                m = LM.scheduler_invariant(run, obs, hz)
                if not m:
                    live = [n for n in obs.get("liveCards", []) if n is not None]
                    unreadable.append({"side": "ours", "grid": grid_key,
                                       "viewport": key[0], "sequence": key[1],
                                       "repeat": run["repeat"],
                                       "liveCardsMin": min(live) if live else None,
                                       "status": "INSTRUMENT_UNREADABLE"})
                    continue
                cells.setdefault(key, []).append(m)
                if key[1] in G1_MOUSE or key[1] == "touch-drag-release":
                    parity.setdefault((key[0], key[1]), []).append(m.get("followRatioX"))
        for vp in sorted({k[0] for k in L}):
            mouse = [v for s in G1_MOUSE for v in parity.get((vp, s), []) if v is not None]
            touch = [v for v in parity.get((vp, "touch-drag-release"), []) if v is not None]
            if mouse and touch:
                med = statistics.median(mouse)
                if abs(med) > 1e-6:
                    cells.setdefault((vp, "PARITY"), [])
                    for t in touch:
                        cells[(vp, "PARITY")].append(
                            {"touchMouseFollowParity": round(t / med, 5)})
        ours_marks[grid_key] = cells

        for cell_key, spec in sorted(baseline["landmarks"][grid_key].items()):
            vp, seq = cell_key.split("|", 1)
            rows = cells.get((vp, seq))
            for name, s in sorted(spec.items()):
                gate_kind = s["gateType"]
                if rows is None:
                    compare_rows.append({
                        "grid": grid_key, "viewport": vp, "sequence": seq,
                        "landmark": name, "gateType": gate_kind,
                        "target": s["targetMean"], "ours": None,
                        "status": "INSTRUMENT_UNREADABLE",
                        "why": "no readable candidate run in this cell"})
                    continue
                ours = mean_of([m.get(name) for m in rows])
                if ours is None:
                    compare_rows.append({
                        "grid": grid_key, "viewport": vp, "sequence": seq,
                        "landmark": name, "gateType": gate_kind,
                        "target": s["targetMean"], "ours": None,
                        "status": "NOT_APPLICABLE",
                        "why": "the landmark is not defined on the candidate's run "
                               "of this sequence"})
                    continue
                ok, status = LM.judge(name, ours, s["targetMean"], s["threshold"])
                if not s["productGated"]:
                    status = "ACCEPTED_DEVIATION" if not ok else status
                    ok = True
                row = {"grid": grid_key, "viewport": vp, "sequence": seq,
                       "landmark": name, "gateType": gate_kind,
                       "productGated": s["productGated"],
                       "target": s["targetMean"], "ours": round(ours, 5),
                       "delta": round(ours - s["targetMean"], 5),
                       "targetRepeatability": s["repeatabilitySpread"],
                       "threshold": s["threshold"], "floor": s["floor"],
                       "thresholdRule": s["thresholdRule"],
                       "status": status, "pass": ok}
                compare_rows.append(row)
                if not ok:
                    failures.append(row)

    # ---- 2b. coverage asymmetry, counted rather than left implicit --------
    #
    # The comparison loop iterates BASELINE cells, so a cell the Target could
    # not be read on is a cell the candidate is never asked about, however
    # readable the candidate was. That is the right behaviour -- there is
    # nothing to compare against -- but it is a hole in coverage and a hole in
    # coverage that nobody counted is how a gate reports 870 comparisons and
    # means 806.
    coverage = []
    for hz in LM.GRIDS:
        grid_key = f"{int(hz)}Hz"
        base_cells = {tuple(k.split("|", 1)) for k in baseline["landmarks"][grid_key]}
        ours_cells = {k for k in ours_marks[grid_key]}
        coverage.append({
            "grid": grid_key,
            "baselineCells": len(base_cells),
            "candidateCells": len(ours_cells),
            "candidateReadableButNoTargetBaseline":
                sorted(f"{a}|{b}" for a, b in (ours_cells - base_cells)),
            "targetBaselineButCandidateUnreadable":
                sorted(f"{a}|{b}" for a, b in (base_cells - ours_cells)),
        })

    # ---- 3. systematic sign, DIRECTION-AWARE ------------------------------
    systematic, by_landmark = [], {}
    for r in compare_rows:
        if "pass" not in r or r.get("ours") is None:
            continue
        by_landmark.setdefault((r["grid"], r["landmark"]), []).append(r)
    for (grid, name), rows in sorted(by_landmark.items()):
        diffs = [r["ours"] - r["target"] for r in rows]
        n = sum(1 for d in diffs if abs(d) > 1e-12)
        if n < 8:
            continue
        k = sum(1 for d in diffs if d > 0)
        p_val = sign_test_p(n, k)
        med_abs = statistics.median([abs(d) for d in diffs])
        med_rep = statistics.median([r["targetRepeatability"] for r in rows])
        lopsided = p_val < 0.001
        bigger = med_abs > med_rep
        kind = LM.gate_type(name)
        gated = rows[0].get("productGated", True)
        # The direction the lopsidedness points in, and whether that direction
        # is one this landmark is allowed to be lopsided in.
        ours_higher = k > n - k
        if kind == "one-sided-upper":
            offending = ours_higher
        elif kind == "one-sided-lower":
            offending = not ours_higher
        else:
            offending = True
        fails = lopsided and bigger and offending and gated
        if not gated:
            status = "ACCEPTED_DEVIATION" if (lopsided and bigger) else "PASS"
        elif fails:
            status = "FAIL"
        elif lopsided and bigger and not offending:
            status = ("SMOOTHER_THAN_TARGET" if kind == "one-sided-upper"
                      else "STRONGER_THAN_TARGET")
        else:
            status = "PASS"
        row = {"grid": grid, "landmark": name, "gateType": kind,
               "productGated": gated, "cells": n, "oursHigherIn": k,
               "signTestP": round(p_val, 8),
               "medianAbsDelta": round(med_abs, 6),
               "medianTargetRepeatability": round(med_rep, 6),
               "lopsided": lopsided, "largerThanTargetOwnSpread": bigger,
               "directionIsGated": offending,
               "status": status, "pass": not fails}
        systematic.append(row)
        if fails:
            failures.append({**row, "viewport": "ALL", "sequence": "ALL",
                             "target": None, "ours": None,
                             "delta": row["medianAbsDelta"],
                             "threshold": row["medianTargetRepeatability"]})

    # ---- 4. raw metrics, reported for MOTION-EXC-01 ------------------------
    raw_rows = []
    for side, data in (("target", T), ("ours", L)):
        for key, runs in sorted(data.items()):
            for run in runs:
                rm = LM.raw_metrics(run, obs_of(run))
                if rm:
                    raw_rows.append({"side": side, "viewport": key[0],
                                     "sequence": key[1], "repeat": run["repeat"], **rm})

    # ---- 5. checks carried forward, unchanged in definition ----------------
    wheel_rows, wrap_rows, touch_rows, resize_rows = [], [], [], []
    for side, data in (("target", T), ("ours", L)):
        for key, runs in sorted(data.items()):
            for run in runs:
                obs = obs_of(run)
                travel = max(abs(obs["scrollX"][-1] - obs["scrollX"][0]),
                             abs(obs["scrollY"][-1] - obs["scrollY"][0]))
                if key[1] in G1.WHEEL_SEQUENCES:
                    prevented = [e["defaultPrevented"] for e in run["events"]
                                 if e["type"] == "wheel"]
                    wheel_rows.append({
                        "side": side, "viewport": key[0], "sequence": key[1],
                        "repeat": run["repeat"], "wheelEvents": len(prevented),
                        "deltaModes": sorted({e["deltaMode"] for e in run["events"]
                                              if e["type"] == "wheel"
                                              and e["deltaMode"] is not None}),
                        "trustedWheelEvents": sum(1 for e in run["events"]
                                                  if e["type"] == "wheel" and e.get("isTrusted")),
                        "anyDefaultPrevented": any(prevented),
                        "scrollTravel": round(travel, 5),
                        "status": "PASS" if travel <= 1.0 else "FAIL"})
                if key[1] in ("long-drag-multi-wrap", "fast-flick"):
                    wc = G1.wrap_continuity(run, obs)
                    if wc:
                        wrap_rows.append({"side": side, "viewport": key[0],
                                          "sequence": key[1], "repeat": run["repeat"], **wc})
                if key[1] in ("touch-drag-release", "pointercancel",
                              "lostpointercapture", "medium-drag"):
                    last = obs["scrollX"]
                    touch_rows.append({
                        "side": side, "viewport": key[0], "sequence": key[1],
                        "repeat": run["repeat"],
                        "eventTypes": sorted({e["type"] for e in run["events"]}),
                        "pointerTypes": sorted({e["pointerType"] for e in run["events"]
                                                if e["pointerType"]}),
                        "totalX": round(last[-1] - last[0], 4),
                        "cameToRestByEndOfRun": (abs(last[-1] - last[-6]) < 0.5
                                                 if len(last) > 6 else None)})
                if key[1] == "resize-during-motion":
                    cont = MC.resize_continuity(run, obs)
                    if cont:
                        resize_rows.append({"side": side, "viewport": key[0],
                                            "repeat": run["repeat"], **cont})

    teleports_ours = sum(r.get("visibleTeleports", 0) for r in wrap_rows if r["side"] == "ours")
    teleports_target = sum(r.get("visibleTeleports", 0) for r in wrap_rows
                           if r["side"] == "target")
    wheel_our_fail = [r for r in wheel_rows if r["side"] == "ours" and r["status"] != "PASS"]
    not_at_rest = [r for r in touch_rows
                   if r["side"] == "ours" and r["cameToRestByEndOfRun"] is False]
    our_errors = [e for e in local_errors if "recorder was gone" not in e]

    # ---- verdict ----------------------------------------------------------
    gated_failures = [f for f in failures]
    verdict_inputs = {
        "landmarkFailures": len(gated_failures),
        "engineVsContractFailures": len(evc_misses),
        "visibleWrapTeleportsOurSide": teleports_ours,
        "wheelResponsesOurSide": len(wheel_our_fail),
        "gesturesNeverAtRestOurSide": len(not_at_rest),
        "consoleAndPageErrorsOurSide": len(our_errors),
    }
    verdict = "PASS" if all(v == 0 for v in verdict_inputs.values()) else "FAIL"

    def w(name, payload):
        (out_dir / name).write_text(json.dumps(payload, indent=2))

    w("engine-vs-contract-v2.json", {
        "what": "our engine against the frozen motion contract, on OUR page's own real "
                "input, replayed in true callback order, compared against the engine's "
                "own published state rather than a recovery of it",
        "whyV2": "the M1 comparison attributed events to frames with `event.t <= frame.t`. "
                 "Those are two different points in the frame pipeline -- listener entry on "
                 "performance.now() against the rAF timestamp, which is the frame's START. "
                 "Chrome dispatches input before the rAF block, so 90% of all recorded "
                 "events were handed to the following frame. That is the whole of the "
                 "'persistent final error': 0.1457 of travel on every reverse-flick row and "
                 "0.0527 on every fast-flick row, identical across four viewports and three "
                 "repeats, which is the signature of a constant and not of an engine.",
        "absoluteGate": "final target error <= max(4 * worst recovery error, 0.1 world units)",
        "worstRecoveryError": round(worst_recovery, 6),
        "threshold": round(evc_limit, 6),
        "recoveryAccuracy": {
            "what": "the card-matrix scroll recovery against the engine's own scroll, "
                    "read in the same frame callback. This is what licenses using the "
                    "recovery on a Target that publishes nothing.",
            "worstWorldUnits": round(worst_recovery, 6),
            "rows": rec_rows},
        "rowsTotal": len(evc_rows),
        "rowsFailed": len(evc_misses),
        "worstFinalErrFraction": round(max((r["finalErrFraction"] for r in evc_rows),
                                           default=0.0), 8),
        "worstSpringTargetFinalErr": round(max((r["springTargetFinalErr"] for r in evc_rows),
                                               default=0.0), 6),
        "releaseFrameDisagreements": [r for r in evc_rows if r["releaseFrameAgrees"] is False],
        "brokenOut": {
            s: [r for r in evc_rows if r["sequence"] == s]
            for s in ("fast-flick", "reverse-flick", "pointercancel")},
        "rows": evc_rows,
    })

    w("scheduler-invariant-gate.json", {
        "what": "the candidate against the sealed Target baseline, on landmarks read "
                "off a uniform timeline",
        "baselineSha256": actual,
        "baselineFile": str(base_path),
        "grids": [f"{int(h)}Hz" for h in LM.GRIDS],
        "statusVocabulary": {
            "PASS": "within threshold",
            "FAIL": "outside threshold in a direction this landmark gates",
            "ACCEPTED_DEVIATION": "outside threshold on a raw single-frame metric the "
                                  "product accepted under MOTION-EXC-01",
            "SMOOTHER_THAN_TARGET": "outside threshold on a one-sided-upper landmark, in "
                                    "the direction that is not a defect",
            "STRONGER_THAN_TARGET": "outside threshold on a one-sided-lower landmark, in "
                                    "the direction that is not a defect",
            "NOT_APPLICABLE": "the landmark is not defined on this sequence",
            "INSTRUMENT_UNREADABLE": "the recovery fell below the minimum live cards; no "
                                     "number was produced and none is gated",
        },
        "comparisons": len(compare_rows),
        "coverage": coverage,
        "failures": failures,
        "instrumentUnreadable": unreadable,
        "systematicSign": {
            "what": "landmarks whose difference lands on the SAME SIDE cell after cell",
            "rule": "FAIL when the sign is lopsided beyond a two-sided sign test at "
                    "p < 0.001, AND the median absolute difference exceeds the Target's "
                    "own median repeatability, AND the direction is one this landmark's "
                    "gate type treats as a defect.",
            "whatWasWrongBefore": "the M1 gate applied the one-sided rule per cell and a "
                                  "plain two-sided sign test here, so being smoother than "
                                  "the Target in every cell was reported as a systematic "
                                  "FAIL. Three landmarks failed that way; none was a defect.",
            "rows": systematic},
        "rows": compare_rows,
    })

    w("raw-scheduler-metrics.json", {
        "what": "the single-frame numbers, both sides, reported and NOT gated",
        "why": "every one of these is read with a one-frame ruler, which is exactly the "
               "ruler the Target's two-rAF architecture moves. They stay in the record so "
               "that 'we did not reproduce the Target's scheduling' is a number a reviewer "
               "can see rather than a sentence in a document. See "
               "product-exception-candidate.json.",
        "rows": raw_rows,
    })

    w("continuity-and-input.json", {
        "what": "wheel absence, wrap continuity, touch parity and resize continuity, both sides",
        "definitionsUnchangedFrom": "qa-v5/motion (M1). The definitions are imported from "
                                    "m1-motion-gate.py rather than restated, so a change "
                                    "here would have to be a change there.",
        "wheel": wheel_rows, "wrap": wrap_rows, "touch": touch_rows, "resize": resize_rows,
        "visibleWrapTeleportsOurSide": teleports_ours,
        "visibleWrapTeleportsTargetSide": teleports_target,
        "consoleAndPageErrors": {"target": len(target_errors), "ours": len(our_errors),
                                 "oursIncludingHarnessReloads": len(local_errors),
                                 "targetSamples": target_errors[:5],
                                 "ourSamples": our_errors[:5]},
    })

    summary = {
        "verdict": verdict,
        "verdictInputs": verdict_inputs,
        "baselineSha256": actual,
        "comparisons": len(compare_rows),
        "productGatedComparisons": sum(1 for r in compare_rows if r.get("productGated")),
        "failures": failures,
        "failureLandmarks": sorted({f["landmark"] for f in failures}),
        "acceptedDeviations": sum(1 for r in compare_rows
                                  if r.get("status") == "ACCEPTED_DEVIATION"),
        "smootherThanTarget": sum(1 for r in compare_rows
                                  if r.get("status") == "SMOOTHER_THAN_TARGET"),
        "instrumentUnreadable": len(unreadable),
        "coverage": coverage,
        "engineVsContract": {
            "rows": len(evc_rows), "failed": len(evc_misses),
            "worstFinalErrFraction": round(max((r["finalErrFraction"] for r in evc_rows),
                                               default=0.0), 8),
            "worstSpringTargetFinalErr": round(max((r["springTargetFinalErr"]
                                                    for r in evc_rows), default=0.0), 6),
            "threshold": round(evc_limit, 6),
            "worstRecoveryError": round(worst_recovery, 6)},
        "systematicSign": {"rows": len(systematic),
                           "failures": [r for r in systematic if not r["pass"]]},
        "wheel": {"ourFailures": len(wheel_our_fail), "rows": len(wheel_rows)},
        "wrap": {"ours": teleports_ours, "target": teleports_target},
        "notAtRest": len(not_at_rest),
        "consoleAndPageErrorsOurSide": len(our_errors),
    }
    w("gate-summary.json", summary)

    print(f"GATE: {verdict}")
    for k, v in verdict_inputs.items():
        print(f"  {k}: {v}")
    print(f"  comparisons {len(compare_rows)}  gated {summary['productGatedComparisons']}"
          f"  acceptedDeviations {summary['acceptedDeviations']}"
          f"  smootherThanTarget {summary['smootherThanTarget']}")
    print(f"  engine-vs-contract worst final fraction "
          f"{summary['engineVsContract']['worstFinalErrFraction']:.3e}"
          f"  (threshold {evc_limit:.4f} world units)")
    return 0 if verdict == "PASS" else 1


G1_MOUSE = ("slow-horizontal-drag", "slow-vertical-drag", "diagonal-drag", "medium-drag")

if __name__ == "__main__":
    raise SystemExit(main())
