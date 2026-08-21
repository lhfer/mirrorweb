#!/usr/bin/env python3
"""Where the magnitude MotionValue's two writers sit in the Target's frame.

WHY THIS FILE EXISTS
--------------------
M1 saw 17 camera-dolly failures and attributed them to the Target's frame-step
jitter. M2 tested that and refuted it by measurement: feeding the magnitude
spring the Target's OWN jittered scroll instead of a smooth replay moved the
dolly peak by 0.3%, while the Target's observed dolly differed from the frozen
law by 17.7% in median absolute residual. M2 then recorded a hypothesis --
that the magnitude source `g` has two writers that disagree by construction --
and explicitly refused to act on it, because closing a residual by choosing
whichever order fits best is a fit, not a reading.

So this round reads it. Not the residual: the bundle. Every row below carries
its own byte offset into the Target's application bundle and the verbatim text
at that offset, and every row is marked SOURCE_READ, MEASURED or INFERRED. The
conclusion is only as good as the rows marked SOURCE_READ, and there is
exactly one INFERRED row in the chain, which is named rather than smoothed
over.

Usage: m3-writer-order-forensics.py --bundle=<js> --out=<json>
                                    [--target=<trace> ...]
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
REPO = HERE.parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


MT = _load("motion_trace", "motion_trace.py")
SM = _load("source_motion", "source_motion.py")
# The M3 replay, not the M2 one. Both are honest, but they stamp the gesture
# history from different clocks -- M2 from the listener-entry time, M3 from
# the event's own timeStamp, which is the number the engine stamps with --
# and the 100 ms velocity window is a strict `>`, so the two can disagree on
# the last history point of a fling. dolly-envelope.json measures the same
# thing through the M3 replay; this probe used to run the M2 one, and the two
# files quoted different ratios for one measurement. They now share a replay.
R = _load("m3_replay", "m3_replay.py")
LM = _load("m2_landmarks", "m2_landmarks.py")


# Every claim below is anchored to a byte offset in the bundle and to the exact
# text at it. `verify()` re-finds each one, so a bundle that ever changes makes
# this file fail rather than quietly describe a different program.
SITES = [
    ("frameStepList", 1242977,
     'mQ=["setup","read","resolveKeyframes","preUpdate","update","preRender",'
     '"render","postRender"]',
     "The frame's eight steps, in the order they are processed."),
    ("frameLoop", 1243826,
     "o.process(n),l.process(n),u.process(n),c.process(n),d.process(n),"
     "h.process(n),f.process(n),p.process(n)",
     "One rAF callback runs all eight steps in that order. `update` is the "
     "fifth, `postRender` the eighth: everything scheduled onto postRender "
     "during update runs later in the SAME frame."),
    ("stepScheduler", 1243334,
     "schedule:(e,n=!1,s=!1)=>{let o=s&&i?t:r;return n&&a.add(e),o.add(e),e}",
     "schedule(callback, keepAlive, immediate). With immediate set AND the "
     "step already processing, the callback is added to `t` -- the Set being "
     "iterated RIGHT NOW -- so it runs later in this same step. Otherwise it "
     "is added to `r`, next time round."),
    ("stepProcess", 1243441,
     "process:e=>{if(s=e,i){n=!0;return}i=!0;let a=t;t=r,r=a,t.forEach(o),"
     "t.clear(),i=!1,n&&(n=!1,l.process(e))}",
     "The two Sets are swapped and the pending one is iterated. Set.forEach "
     "visits entries added during iteration, which is what makes `immediate` "
     "an append rather than a defer. Insertion order is execution order."),
    ("keepAliveWrapper", 1243278,
     "function o(t){a.has(t)&&(l.schedule(t),e()),t(s)}",
     "A keepAlive callback re-schedules itself BEFORE it runs, so keepAlive "
     "callbacks keep their relative order frame after frame."),
    ("panHandlePointerMove", 1321444,
     "this.handlePointerMove=(e,t)=>{this.lastMoveEvent=e,"
     "this.lastRawMoveEventInfo=t,this.lastMoveEventInfo="
     "So(t,this.transformPagePoint),mH.update(this.updatePoint,!0)}",
     "PanSession's pointermove listener records the point and schedules "
     "updatePoint on the `update` step with keepAlive -- so the dispatch "
     "re-runs every frame while the gesture is alive, not only on frames that "
     "carried a move."),
    ("panUpdatePointDispatch", 1321273,
     "this.history.push({...a,timestamp:s});let{onStart:o,onMove:l}="
     "this.handlers;i||(o&&o(this.lastMoveEvent,r),this.startEvent="
     "this.lastMoveEvent),l&&l(this.lastMoveEvent,r)",
     "updatePoint pushes the point into history with the FRAME's timestamp "
     "and then calls the onMove handler."),
    ("Sy", 1332746,
     "let Sy=e=>(t,r)=>{e&&mH.update(()=>e(t,r),!1,!0)}",
     "THE DECIDING LINE. Every pan handler is wrapped in this. It schedules "
     "the application's callback onto `update` with immediate=true, and "
     "updatePoint is itself running inside the update step -- so the "
     "application's onPan is APPENDED TO THE LIVE UPDATE SET and runs after "
     "every callback already queued in it, including all three spring ticks."),
    ("panFeatureHandlers", 1371814,
     "createPanHandlers(){let{onPanSessionStart:e,onPanStart:t,onPan:r,"
     "onPanEnd:i}=this.node.getProps();return{onSessionStart:Sy(e),"
     "onStart:Sy(t),onMove:Sy(r),onEnd:(e,t)=>{delete this.session,"
     "i&&mH.postRender(()=>i(e,t))}}}",
     "onPan goes through Sy. onPanEnd does NOT: it is scheduled straight onto "
     "`postRender` from inside the pointerup listener, which runs in the "
     "input-dispatch phase -- so it is the FIRST entry in that frame's "
     "postRender set, ahead of any spring retarget queued during update."),
    ("driver", 1257250,
     "let va=e=>{let t=({timestamp:t})=>e(t);return{start:(e=!0)=>"
     "mH.update(t,e),stop:()=>mV(t),now:()=>mj.isProcessing?mj.timestamp:"
     "mq.now()}}",
     "The default animation driver ticks on the `update` step with keepAlive. "
     "Both scroll springs and the magnitude spring tick there."),
    ("animationPlay", 1263626,
     "play(){if(this.isStopped)return;let{driver:e=va,startTime:t}="
     "this.options;this.driver||(this.driver=e(e=>this.tick(e)))",
     "and nothing overrides that default for these springs: `driver` is not "
     "among the options useSpring passes."),
    ("springAttach", 1374882,
     "e.attach((e,t)=>{s=e,i=e=>{var r,i;return t((r=e,(i=o)?r+i:r))},"
     "mH.postRender(u)},l)",
     "useSpring attaches a passive effect to its OUTPUT value. Setting the "
     "output records the new target and schedules the RETARGET on postRender "
     "-- after every writer in that frame's update step has had its say."),
    ("springSourceBridge", 1374967,
     'An(t)){let i=!0===r.skipInitialAnimation,n=t.on("change",t=>{var r,n,a,s;'
     'i?(i=!1,e.jump((r=t,(n=o)?r+n:r),!1)):e.set((a=t,(s=o)?a+s:a))})',
     "and the source is bridged to the output through a plain change "
     "subscription, which fires SYNCHRONOUSLY inside the source's own set()."),
    ("attachOnly", 1245366,
     "attach(e,t){this.passiveEffect=e,this.stopPassiveEffect=t}",
     "The only way a MotionValue acquires a passive effect."),
    ("motionValueSet", 1245424,
     "set(e){this.passiveEffect?this.passiveEffect(e,this.updateAndNotify):"
     "this.updateAndNotify(e)}",
     "A value with no passive effect updates and notifies immediately."),
    ("getVelocity", 1246070,
     "getVelocity(){let e=mq.now();if(!this.canTrackVelocity||void 0==="
     "this.prevFrameValue||e-this.updatedAt>30)return 0;let t=Math.min("
     "this.updatedAt-this.prevUpdatedAt,30);return mU(parseFloat(this.current)"
     "-parseFloat(this.prevFrameValue),t)}",
     "The scroll writer's number: a ONE-FRAME BACKWARD DIFFERENCE of the "
     "spring's output, capped at 30 ms and zeroed once the value is stale. "
     "Not the spring's analytic velocity."),
    ("appSprings", 1376866,
     "u=l.spring,c=l.magnitudeSpring,d=_D(0),h=_D(0),f=_F(d,u),p=_F(h,u),"
     "g=_D(0),m=_F(g,c)",
     "The application's five values: scroll targets d,h; scroll springs f,p; "
     "magnitude source g; magnitude spring m. d, h and g are plain "
     "MotionValues -- no passive effect, so a set() on them notifies at once."),
    ("appScrollWriter", 1376998,
     't=()=>{let e=f.on("change",e=>{bK.set(e);let t=f.getVelocity(),'
     'r=p.getVelocity();bY.set(t),bJ.set(r),g.set(_O(t,r))})',
     "WRITER B. Runs inside the scroll spring's own tick, in the update step."),
    ("appGestureWriterPan", 1377531,
     "i=(e,t)=>{d.set(d.get()+1.5*t.delta.x),h.set(h.get()+1.5*t.delta.y),"
     "bY.set(t.velocity.x),bJ.set(t.velocity.y),g.set(_O(t.velocity.x,"
     "t.velocity.y))}",
     "WRITER A, drag half. The FINGER's velocity, not the spring's."),
    ("appGestureWriterPanEnd", 1377765,
     "n=(e,t)=>{d.set(d.get()+t.velocity.x*l.fling),h.set(h.get()+"
     "t.velocity.y*l.fling),bY.set(t.velocity.x),bJ.set(t.velocity.y),"
     "g.set(_O(t.velocity.x,t.velocity.y))}",
     "WRITER A, release half."),
]


def verify(bundle_text: str) -> list:
    rows = []
    for key, offset, text, why in SITES:
        found = bundle_text.find(text)
        rows.append({
            "id": key,
            "recordedByteOffset": offset,
            "foundAtByteOffset": found,
            "matches": found == offset,
            "verbatim": text,
            "whatItSettles": why,
            "confidence": "SOURCE_READ",
        })
    return rows


def probe(target_traces: list) -> dict:
    """The same two orders, replayed on the TARGET's own recorded input."""
    rows = []
    for path in target_traces:
        for run in json.loads(Path(path).read_text())["runs"]:
            if run["sequence"] in LM.WHEEL_SEQUENCES:
                continue
            traj = MT.trajectory(run)
            live = [n for n in traj.get("liveCards", []) if n is not None]
            if live and min(live) < LM.MIN_LIVE_CARDS:
                continue
            persp = MT.frame_for(*run["viewport"])["perspective"]
            obs = []
            for s in run["frames"]:
                p = MT.camera_position(s)
                if p is not None:
                    obs.append(math.dist(p, (0.0, 0.0, 0.0)) / persp - 1.0)
            a = LM.R.median_peak(obs, 3)
            peaks = {}
            for order in ("gestureLastWhileActive", "scrollLastAlways"):
                pred = R.replay(run, writer_order=order)
                maxz = SM.CAMERA["velocityDolly"]["maxZoomZFactor"] * persp
                peaks[order] = LM.R.median_peak(
                    [SM.dolly(m, maxz) / persp for m in pred["magnitude"]], 3)
            if min(peaks.values()) <= 1e-9:
                continue
            rows.append({
                "viewport": run["id"], "sequence": run["sequence"],
                "repeat": run["repeat"],
                "targetObservedPeak": round(a, 6),
                "contractPeakGestureLast": round(peaks["gestureLastWhileActive"], 6),
                "contractPeakScrollLast": round(peaks["scrollLastAlways"], 6),
                "ratioGestureLast": round(a / peaks["gestureLastWhileActive"], 4),
                "ratioScrollLast": round(a / peaks["scrollLastAlways"], 4),
            })

    def stats(key):
        v = [r[key] for r in rows]
        return {
            "signedMedianRatio": round(statistics.median(v), 4),
            "medianAbsoluteResidual": round(
                statistics.median([abs(x - 1.0) for x in v]), 4),
            "worstAbsoluteResidual": round(max(abs(x - 1.0) for x in v), 4),
            "runs": len(v),
        }

    by_seq = {}
    for seq in sorted({r["sequence"] for r in rows}):
        rs = [r for r in rows if r["sequence"] == seq]
        by_seq[seq] = {
            "scrollLastAlways": round(
                statistics.median([r["ratioScrollLast"] for r in rs]), 4),
            "gestureLastWhileActive": round(
                statistics.median([r["ratioGestureLast"] for r in rs]), 4),
            "runs": len(rs),
        }
    return {"rows": rows,
            "replayAndClock":
                "scripts/v5/m3_replay.py, gesture history stamped from the event's "
                "own timeStamp and the springs integrated on the raw rAF clock where "
                "the trace carries one. dolly-envelope.json measures the same ratio "
                "through the same replay, so the two files agree by construction "
                "rather than by coincidence. An earlier draft of this probe ran the "
                "M2 replay, which stamps from the listener-entry time, and reported "
                "0.9843 / 1.57% where this reports the numbers below -- the same "
                "conclusion from a slightly different last history point on some "
                "flings, but two numbers for one measurement.",
            "whyTheseDifferSlightlyFromDollyEnvelope":
                "dolly-envelope.json reports 0.9514 / 17.82% and 1.0249 / 2.58% against this "
                "file's 0.955 / 17.68% and 1.0261 / 2.64%. Same replay, same clock, same "
                "constants -- the two differ only in which runs each includes: this probe "
                "takes every non-wheel run with enough live cards (124), while the envelope "
                "reads through the landmark reader's own admission rule (120). Neither is a "
                "filtered-to-fit set and the conclusion is the same in both.",
            "scrollLastAlways": stats("ratioScrollLast"),
            "gestureLastWhileActive": stats("ratioGestureLast"),
            "bySequence": by_seq}


def main() -> int:
    args, targets = {}, []
    for a in sys.argv[1:]:
        if a.startswith("--target="):
            targets.append(a.split("=", 1)[1])
        else:
            k, v = a[2:].split("=", 1)
            args[k] = v

    bundle = Path(args["bundle"])
    text = bundle.read_text(encoding="utf-8", errors="replace")
    sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
    sites = verify(text)
    bad = [r["id"] for r in sites if not r["matches"]]
    measured = probe(targets) if targets else None

    order_wins = None
    if measured:
        order_wins = ("gestureLastWhileActive"
                      if measured["gestureLastWhileActive"]["medianAbsoluteResidual"]
                      < measured["scrollLastAlways"]["medianAbsoluteResidual"]
                      else "scrollLastAlways")

    doc = {
        "what": "the intra-frame execution order of the magnitude MotionValue's "
                "two writers in the Target, read out of the Target's own bundle",
        "bundle": {
            "path": str(bundle.relative_to(REPO)) if bundle.is_absolute()
                    else str(bundle),
            "sha256": sha,
            "bytes": bundle.stat().st_size,
        },
        "theTwoWriters": {
            "A_gesture": {
                "call": "g.set(Math.hypot(t.velocity.x, t.velocity.y))",
                "wherePlaced": "the application's onPan and onPanEnd handlers",
                "whatItMeasures": "the FINGER's velocity, straight out of "
                                  "PanSession's 100 ms history window",
                "byteOffsets": [1377531, 1377765],
            },
            "B_scrollMotionValue": {
                "call": "g.set(Math.hypot(f.getVelocity(), p.getVelocity()))",
                "wherePlaced": "the two scroll springs' own change handlers",
                "whatItMeasures": "the SPRING's one-frame backward difference "
                                  "-- the finger's velocity times the 1.5 drag "
                                  "gain, minus the spring's own lag",
                "byteOffsets": [1376998],
            },
            "whyTheyDisagree": "by construction, and by a factor near the drag "
                               "gain while a finger is down. They are not two "
                               "estimates of one quantity; they are two "
                               "different quantities written to one value.",
        },
        "schedulerStep": {
            "steps": ["setup", "read", "resolveKeyframes", "preUpdate", "update",
                      "preRender", "render", "postRender"],
            "panSessionDispatch": "update (keepAlive, re-runs every frame while "
                                  "the gesture is alive)",
            "applicationOnPan": "update, immediate=true -- appended to the LIVE "
                                "update set, so after every spring tick in it",
            "applicationOnPanEnd": "postRender, scheduled from the pointerup "
                                   "listener in the input-dispatch phase, so "
                                   "first in that frame's postRender set",
            "springTick": "update (keepAlive)",
            "springRetarget": "postRender",
            "magnitudeSpringConsumesTargetAt": "postRender, from `g`'s value as "
                                               "it stands at that moment",
        },
        "immediateAndKeepAlive": {
            "signature": "schedule(callback, keepAlive=false, immediate=false)",
            "panSessionUpdatePoint": {"keepAlive": True, "immediate": False},
            "applicationOnPanViaSy": {"keepAlive": False, "immediate": True},
            "springDriverStart": {"keepAlive": True, "immediate": False},
            "whyImmediateDecidesIt": "immediate=true while the step is being "
                                     "processed adds to the Set currently being "
                                     "iterated, and Set.forEach visits entries "
                                     "added during iteration. So onPan runs "
                                     "AFTER everything already queued in the "
                                     "update step, no matter where updatePoint "
                                     "itself sits in that set. The order does "
                                     "not depend on registration order, which "
                                     "is what makes it deterministic.",
        },
        "writerRegistrationOrder": [
            "PanSession.updatePoint  (update, on the first pointermove)",
            "scrollX spring tick     (update, when d.set() first starts it)",
            "scrollY spring tick     (update)",
            "magnitude spring tick   (update, when g.set() first starts it)",
            "application onPan       (update, appended live, every frame)",
        ],
        "writerExecutionOrder": {
            "dragFrame": [
                "update: PanSession.updatePoint -> pushes history, dispatches onPan via Sy",
                "update: scrollX tick -> f change -> WRITER B writes g",
                "update: scrollY tick -> p change -> WRITER B writes g",
                "update: magnitude tick -> m advances on LAST frame's solve",
                "update: onPan -> d.set, h.set, WRITER A writes g   <-- LAST",
                "postRender: scroll retarget, then magnitude retarget to g = WRITER A",
            ],
            "releaseFrame": [
                "input dispatch: pointerup -> PanSession.end() cancels updatePoint,",
                "                onPanEnd scheduled onto postRender  <-- FIRST in that set",
                "update: scrollX/scrollY ticks -> WRITER B writes g",
                "update: magnitude tick",
                "postRender: onPanEnd -> d.set(+fling), WRITER A writes g   <-- LAST",
                "postRender: magnitude retarget to g = WRITER A",
            ],
            "postReleaseFrame": [
                "update: scrollX/scrollY ticks -> WRITER B writes g",
                "update: magnitude tick",
                "postRender: magnitude retarget to g = WRITER B "
                "(there is no gesture writer left)",
            ],
        },
        "conclusion": {
            "order": "gestureLastWhileActive",
            "statement": "The gesture writer is the last writer on every frame "
                         "that carries a pan dispatch and on the release frame. "
                         "The scroll writer stands alone on every frame that "
                         "carries neither -- which is every frame after the "
                         "release.",
            "isThisAChoice": "No. It follows from two lines of the bundle: "
                             "`Sy` scheduling onPan with immediate=true, and "
                             "the pan feature scheduling onPanEnd straight onto "
                             "postRender. Neither depends on registration "
                             "order, machine speed or refresh rate.",
            "confidence": "SOURCE_READ",
        },
        "inferredRows": [
            {
                "claim": "Chrome dispatches pointer input before the rAF "
                         "callback block of the same frame, so onPanEnd's "
                         "postRender entry is queued before any retarget "
                         "scheduled during that frame's update step.",
                "confidence": "INFERRED",
                "whyNotSourceRead": "it is a property of the browser, not of "
                                    "the bundle, so it cannot be read out of "
                                    "the bundle.",
                "whatWouldFalsifyIt": "a release frame on which the magnitude "
                                      "retargeted to the scroll writer's value. "
                                      "The measured column below is the check: "
                                      "if this were wrong the release-phase "
                                      "sequences would not close, and they do.",
            },
        ],
        "sourceRead": {"sites": sites, "allSitesMatch": not bad,
                       "mismatched": bad},
        "measured": measured,
        "measuredReading": None if not measured else {
            "whatWasReplayed": "the frozen contract, driven by the TARGET's own "
                               "recorded input, once per writer order, compared "
                               "against the Target's own observed camera dolly. "
                               "No constant was changed between the two runs.",
            "scrollLastAlways": measured["scrollLastAlways"],
            "gestureLastWhileActive": measured["gestureLastWhileActive"],
            "orderThatReproducesTheTarget": order_wins,
            "note": "the two orders differ ONLY in which of the two writers the "
                    "magnitude spring retargets to. Everything else -- drag "
                    "gain, fling, all three springs, the dolly law, the "
                    "publication delay -- is identical between them.",
        },
        "whatThisDoesNotCover": [
            "The scroll path. onPanEnd running at postRender also means its "
            "`d.set(+fling)` schedules the SCROLL retarget into the NEXT "
            "frame's postRender, one frame later than a drag frame does. That "
            "is a real source-read asymmetry, it is recorded here, and it is "
            "NOT implemented this round: the product re-authorised the release "
            "history window and the magnitude writer order, and this is "
            "neither.",
            "MotionValue.updateAndNotify advances prevFrameValue and updatedAt "
            "even when the value is unchanged, and only skips the notify; the "
            "transcription returns early instead. The two differ only where a "
            "spring emits the same float twice, which is the last frame or two "
            "before rest. Recorded, not changed.",
        ],
    }
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{out}  sites={len(sites)} mismatched={len(bad)} "
          f"measuredRuns={0 if not measured else len(measured['rows'])}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
