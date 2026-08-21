#!/usr/bin/env python3
"""The ordering instrument, proved on the traces it is used on.

An M2 reply cited `qa-v5/motion-closure/callback-order-proof.json`. That file
was never written -- the numbers it described are real and live inside
`engine-vs-contract-v2.json` under `attribution`, but the path did not exist,
in the public tree or in the private package. This is the file, written rather
than cited, and extended with the thing M2 could not show.

THREE LAYERS, EACH STRICTLY STRONGER THAN THE LAST
--------------------------------------------------
1. THE M1 RULE, MEASURED. `event.t <= frame.t` attributed an event to a frame
   by comparing listener-entry `performance.now()` against the rAF timestamp,
   which is when the frame STARTED. Chrome dispatches input before the rAF
   block, so an event dispatched in frame N satisfies `event.t > frame_N.t`
   and the rule handed it to N+1. How often, per run, is column one.

2. THE COUNTER. One monotone counter bumped by every listener and every frame
   callback. It orders events against OUR callback as a recorded fact.

3. THE ENGINE'S OWN STEP, read INSIDE the listener. The counter cannot order an
   event against the PAGE's frame callback, which is invisible from outside;
   that residue is what M2 reported as a sub-frame race. Reading the engine's
   frame counter in the same dispatch the page's own handler runs in removes
   it: how many frames the model had integrated when the event arrived is a
   number, not an inference. The Target exposes no counter, which is why the
   Target is compared on scheduler-invariant landmarks and never frame by
   frame.

Usage: m3-callback-order.py --local=<trace> [--local=...]
                            [--target=<trace> ...] --out=<json>
"""
from __future__ import annotations

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


R = _load("m3_replay", "m3_replay.py")


def engine_step_layer(run):
    """Does the engine's own counter order every event, and is it monotone?"""
    evs = [e for e in run["events"] if e.get("engineStep") is not None]
    if not evs:
        return None
    steps = [e["engineStep"] for e in evs]
    monotone = all(b >= a for a, b in zip(steps, steps[1:]))
    frames = R.truth_series(run, "motionSteps") or []
    frame_steps = [s for s in frames if s is not None]
    covered = 0
    for e in evs:
        # The frame that integrated this event is the first frame sample whose
        # engine step is greater than the step read in the listener.
        if any(s > e["engineStep"] for s in frame_steps):
            covered += 1
    return {"eventsWithEngineStep": len(evs),
            "eventsTotal": len(run["events"]),
            "engineStepMonotoneAcrossEvents": monotone,
            "eventsFollowedByAnIntegratedFrame": covered,
            "everyEventPlaced": covered == len(evs)}


def main() -> int:
    args, locals_, targets = {}, [], []
    for a in sys.argv[1:]:
        if a.startswith("--local="):
            locals_.append(a.split("=", 1)[1])
        elif a.startswith("--target="):
            targets.append(a.split("=", 1)[1])
        else:
            k, v = a[2:].split("=", 1)
            args[k] = v

    rows = []
    for side, paths in (("ours", locals_), ("target", targets)):
        for path in paths:
            for run in json.loads(Path(path).read_text())["runs"]:
                if not R.has_order(run):
                    rows.append({"side": side, "viewport": run["id"],
                                 "sequence": run["sequence"], "repeat": run["repeat"],
                                 "status": "NO_CALLBACK_ORDER"})
                    continue
                st = R.attribution_stats(run)
                rows.append({
                    "side": side, "viewport": run["id"], "sequence": run["sequence"],
                    "repeat": run["repeat"],
                    "events": st["events"],
                    "misattributedByTheM1Rule": st["movedByOneFrameOrMore"],
                    "fraction": st["fraction"],
                    "medianFrameShift": st["medianFrameShift"],
                    "maxFrameShift": st["maxFrameShift"],
                    "engineStepLayer": engine_step_layer(run),
                    "status": "PASS",
                })

    scored = [r for r in rows if r["status"] == "PASS" and r["events"]]
    ours = [r for r in scored if r["side"] == "ours"]
    tgt = [r for r in scored if r["side"] == "target"]

    def frac(rs):
        return round(statistics.median([r["fraction"] for r in rs]), 4) if rs else None

    layers = [r["engineStepLayer"] for r in ours if r["engineStepLayer"]]
    doc = {
        "what": "how the replay decides which frame consumed which event, and how much "
                "that decision moved between rounds",
        "layers": {
            "m1Rule": "event.t <= frame.t -- two clocks from different points in the "
                      "frame pipeline. Measured below.",
            "m2Counter": "one monotone counter bumped by every listener and every frame "
                         "callback. Orders events against OUR callback as a recorded fact.",
            "m3EngineStep": "the engine's own frame counter, read INSIDE each listener. "
                            "Orders events against the PAGE's callback, which the counter "
                            "cannot see and which M2 had to report as a sub-frame race.",
        },
        "medianMisattributedFractionUnderTheM1Rule": {
            "ours": frac(ours), "target": frac(tgt),
        },
        "worstMisattributedFraction": round(max((r["fraction"] for r in scored),
                                                default=0.0), 4),
        "medianFrameShiftUnderTheM1Rule": (
            statistics.median([r["medianFrameShift"] for r in scored]) if scored else None),
        "engineStepLayerSummary": {
            "runsWithAnEngineStepOnEveryEvent":
                sum(1 for l in layers if l["eventsWithEngineStep"] == l["eventsTotal"]),
            "runsWithTheLayerAtAll": len(layers),
            "runsWhereTheCounterIsMonotone":
                sum(1 for l in layers if l["engineStepMonotoneAcrossEvents"]),
            "runsWhereEveryEventIsFollowedByAnIntegratedFrame":
                sum(1 for l in layers if l["everyEventPlaced"]),
            "note": "the Target has no such counter, which is exactly why the Target is "
                    "compared on scheduler-invariant landmarks and never frame by frame.",
        },
        "rows": rows,
    }
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{out}  rows={len(rows)} "
          f"medianM1Misattribution ours={frac(ours)} target={frac(tgt)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
