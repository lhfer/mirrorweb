#!/usr/bin/env python3
"""Every release, as the engine recorded it, against the contract replay.

WHY THIS FILE EXISTS
--------------------
M2 could not settle five runs. All five were at the release instant and all
five turned on the same unobservable: when the pointerup was dispatched between
two of our sample callbacks, had the page's own frame callback already run and
pushed another point into the gesture history? A longer history means a longer
velocity window means a different fling. Nothing outside the page can see that
callback, so M2 replayed both orderings and reported three runs as a race and
two as failures.

The answer was never outside the page. It was inside it. The model now records
each release as it commits it -- the complete history, the two points the
100 ms window used, the velocity that came out, the scroll target either side
of the fling -- and the recorder reads the engine's own frame counter inside
every event listener. This file puts those two recordings beside the replay's
reconstruction and reports, per release, whether they agree to floating point.

Nothing here is inferred. A field that disagrees is printed with both values.

Usage: m3-release-history.py --local=<trace> [--local=... ] --out=<json>
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


R = _load("m3_replay", "m3_replay.py")


def terminal_event(run):
    """The event that ended the gesture, with the stamps the recorder took."""
    for e in reversed(run["events"]):
        if e.get("terminal"):
            return e
    return None


def main() -> int:
    args, locals_ = {}, []
    for a in sys.argv[1:]:
        if a.startswith("--local="):
            locals_.append(a.split("=", 1)[1])
        else:
            k, v = a[2:].split("=", 1)
            args[k] = v

    rows, no_record = [], []
    for path in locals_:
        for run in json.loads(Path(path).read_text())["runs"]:
            recs = run.get("releaseRecords") or []
            ev = terminal_event(run)
            if not recs:
                if ev is not None and any(f.get("truth") and f["truth"][12] == 1
                                          for f in run["frames"]):
                    no_record.append({"viewport": run["id"],
                                      "sequence": run["sequence"],
                                      "repeat": run["repeat"],
                                      "why": "a gesture ran but no release was recorded"})
                continue
            rec = recs[-1]
            pred = R.replay(run)
            win = pred["releaseWindow"] or {}
            steps = R.truth_series(run, "motionSteps")
            base = next((s for s in steps if s is not None), 0)
            vx_err = abs(pred["releaseVelocity"][0] - rec["computedVelocityX"])
            vy_err = abs(pred["releaseVelocity"][1] - rec["computedVelocityY"])
            fling = math.hypot(rec["flingDeltaX"], rec["flingDeltaY"])
            expect_fling_x = rec["computedVelocityX"] * 0.1
            rows.append({
                "viewport": run["id"], "sequence": run["sequence"],
                "repeat": run["repeat"],
                "cancelled": rec["cancelled"],
                # --- where the release sat in the frame, from both sides ----
                "releaseCallbackOrder": None if ev is None else ev["ord"],
                "releaseEventTimeStamp": None if ev is None else ev["timeStamp"],
                "releaseListenerEntryTime": None if ev is None else ev["t"],
                "engineStepAtListener": None if ev is None else ev.get("engineStep"),
                "engineStepRecordedByModel": rec["recordedAtStep"],
                "listenerAndModelAgreeOnStep": (
                    None if ev is None or ev.get("engineStep") is None
                    else ev["engineStep"] == rec["recordedAtStep"]),
                "releaseFrameIndex": rec["commitStep"] - base,
                "commitStep": rec["commitStep"],
                "framesBetweenRecordAndCommit": rec["commitStep"] - rec["recordedAtStep"],
                # --- the window the engine actually used --------------------
                "historyCount": rec["historyCount"],
                "newestHistoryPointUsed": rec["newestUsed"],
                "oldestHistoryPointUsed": rec["oldestUsed"],
                "velocityWindowMs": rec["velocityWindowMs"],
                "windowSpanMs": round(rec["windowDtMs"], 6),
                "clampedToSecondPoint": rec["clampedToSecondPoint"],
                "historyFirstPoint": rec["history"][0] if rec["history"] else None,
                "historyLastPoint": rec["history"][-1] if rec["history"] else None,
                # --- what came out of it ------------------------------------
                "computedVelocityX": rec["computedVelocityX"],
                "computedVelocityY": rec["computedVelocityY"],
                "releasePoint": [rec["releasePointX"], rec["releasePointY"]],
                "releaseDelta": [rec["releaseDeltaX"], rec["releaseDeltaY"]],
                "releaseOffset": [rec["releaseOffsetX"], rec["releaseOffsetY"]],
                "targetXBeforeRelease": rec["targetXBeforeRelease"],
                "targetYBeforeRelease": rec["targetYBeforeRelease"],
                "flingDeltaX": rec["flingDeltaX"], "flingDeltaY": rec["flingDeltaY"],
                "targetXAfterRelease": rec["targetXAfterRelease"],
                "targetYAfterRelease": rec["targetYAfterRelease"],
                "flingIsVelocityTimesContractFling": abs(
                    rec["flingDeltaX"] - expect_fling_x) <= 1e-9,
                # --- the replay's own reconstruction ------------------------
                "contractVelocityX": pred["releaseVelocity"][0],
                "contractVelocityY": pred["releaseVelocity"][1],
                "contractHistoryCount": pred["releaseHistoryCount"],
                "contractWindowSpanMs": round(win.get("dtMs", 0.0), 6),
                "contractNewestUsed": win.get("newest"),
                "contractOldestUsed": win.get("oldest"),
                "releaseOrderedAfterDispatch": pred["releaseOrderedAfterDispatch"],
                "velocityErrorX": vx_err, "velocityErrorY": vy_err,
                "historyCountAgrees": pred["releaseHistoryCount"] == rec["historyCount"],
                "windowSpanAgrees": abs(win.get("dtMs", 0.0) - rec["windowDtMs"]) <= 1e-9,
                "status": "EXACT" if vx_err == 0.0 and vy_err == 0.0 else "MISMATCH",
                "flingMagnitude": round(fling, 6),
            })

    exact = [r for r in rows if r["status"] == "EXACT"]
    mismatched = [r for r in rows if r["status"] != "EXACT"]
    pinned = [r for r in rows if r["releaseOrderedAfterDispatch"]]
    doc = {
        "what": "every release the engine committed, recorded from inside the model "
                "and compared field by field against the contract replay",
        "why": "M2 had to infer the release window from an external scroll curve and "
               "could not settle five runs. A window that is recorded cannot be "
               "mis-inferred. See the module docstring of scripts/v5/m3-release-history.py.",
        "vocabulary": {
            "EXACT": "the replay's release velocity equals the engine's recorded one "
                     "to floating point",
            "MISMATCH": "it does not, and both values are in the row",
        },
        "requirement": "180/180 EXACT. There is no 'likely subframe race', no 'probably "
                       "instrument' and no 'alternate almost matches' in this file: with "
                       "the release recorded from inside the model there is no external "
                       "ordering left to be uncertain about.",
        "releases": len(rows),
        "exact": len(exact),
        "mismatched": len(mismatched),
        "worstVelocityError": max((max(r["velocityErrorX"], r["velocityErrorY"])
                                   for r in rows), default=0.0),
        "orderedAfterDispatchCount": len(pinned),
        "orderedAfterDispatchNote":
            "runs where the engine's recorded history was one point longer than the "
            "replay's had reached, so the page's own frame callback dispatched a pan "
            "between the release and our sample. Counted rather than guessed: the "
            "engine wrote the length down.",
        "listenerStepAgreement": {
            "agree": sum(1 for r in rows if r["listenerAndModelAgreeOnStep"] is True),
            "disagree": sum(1 for r in rows if r["listenerAndModelAgreeOnStep"] is False),
            "what": "the engine's frame counter read in the RECORDER's pointerup "
                    "listener against the counter the model wrote in its own. They run "
                    "in the same event dispatch, so they must agree; if they ever "
                    "disagreed, the recorder would be seeing a different frame from the "
                    "page and nothing else in this round could be trusted.",
        },
        "medianWindowSpanMs": round(statistics.median(
            [r["windowSpanMs"] for r in rows]), 4) if rows else None,
        "clampedToSecondPointCount": sum(1 for r in rows if r["clampedToSecondPoint"]),
        "gesturesWithNoRecordedRelease": no_record,
        "rows": rows,
    }
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{out}  releases={len(rows)} exact={len(exact)} mismatched={len(mismatched)}")
    return 1 if mismatched or no_record else 0


if __name__ == "__main__":
    raise SystemExit(main())
