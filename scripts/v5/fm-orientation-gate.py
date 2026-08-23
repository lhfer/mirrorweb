#!/usr/bin/env python3
"""Final Motion §三 -- the orientation relayout, judged.

Two independent things are settled here and they are kept apart on purpose.

FIRST, what the pre-registered §五 number actually measured. The round opened
on "one ~36.7 px single-frame step against the Target's 4.5 px maximum". That
number comes from `vc2_card_geom.unwrap`, which subtracts the WHOLE frame
delta whenever it exceeds 0.6 x pitch. At an orientation flip every tracked
card moves hundreds of pixels on BOTH pages, so the estimator erases whatever
is above the threshold and reports whatever falls below it. The arithmetic,
per card, is published rather than described.

SECOND, the observable the same recordings DO support: what the flip costs the
main thread. That is measured on the wall clock with one instrument installed
on both pages, at five runs a side, and attributed by taking one layer out of
the document and re-measuring.

Nothing here is a new threshold invented after seeing a result. The §五
threshold is left exactly where it was and its verdict is reported as it
falls; the correction is to the CLAIM the number supports, and the original
number is republished beside it.

Usage: fm-orientation-gate.py [--vc2=<dir>] [--traces=<dir>] [--out=<json>]
"""
from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _load("vc2_card_geom", "vc2_card_geom.py")


# ---------------------------------------------------------------------------
# 1. what the pre-registered estimator did at the flip
# ---------------------------------------------------------------------------

def artifact_arithmetic(vc2: Path) -> dict:
    """Per card, at the one frame the viewport changed: the raw delta, whether
    each axis cleared the unwrap threshold, and what survived into `stepPx`."""
    out = {"estimator": "vc2_card_geom.unwrap(series, 0.6 * pitch) -- subtracts "
                        "the WHOLE frame delta when |d| exceeds the threshold, so a "
                        "jump above it contributes exactly 0 and a jump below it "
                        "contributes its full magnitude",
           "runs": []}
    for side in ("target", "local"):
        for r in range(3):
            p = vc2 / side / f"orientation-change-r{r}.json"
            if not p.exists():
                continue
            run = G.load_run(p)
            raw = G.derive(run)
            s = G.series_of(p)
            flip = int(np.argmax(run["vw"] > 500))
            thr = s["pitch"] * 0.6
            cards = []
            for c in range(raw["cx"].shape[1]):
                dx = raw["cx"][flip, c] - raw["cx"][flip - 1, c]
                dy = raw["cy"][flip, c] - raw["cy"][flip - 1, c]
                if not (np.isfinite(dx) and np.isfinite(dy)):
                    cards.append({"card": c, "sampled": False,
                                  "why": "culled on one of the two frames; both "
                                         "pages cull through the relayout"})
                    continue
                ux = s["cx"][flip, c] - s["cx"][flip - 1, c]
                uy = s["cy"][flip, c] - s["cy"][flip - 1, c]
                cards.append({
                    "card": c, "sampled": True,
                    "rawDeltaPx": [round(float(dx), 2), round(float(dy), 2)],
                    "rawDistancePx": round(float(np.hypot(dx, dy)), 2),
                    "clearedThreshold": [bool(abs(dx) > thr), bool(abs(dy) > thr)],
                    "reportedStepPx": round(float(np.hypot(ux, uy)), 2),
                })
            step = s["stepPx"].copy()
            worst = float(np.nanmax(step))
            step_ex = step.copy()
            step_ex[flip - 1, :] = np.nan
            out["runs"].append({
                "side": side, "repeat": r, "flipFrame": flip,
                "unwrapThresholdPx": round(float(thr), 2),
                "reportedMaxStepPx": round(worst, 2),
                "reportedMaxStepAtFlip": bool(
                    np.nanmax(step[flip - 1, :]) >= worst - 1e-9),
                "maxStepExcludingTheRelayoutFramePx": round(float(np.nanmax(step_ex)), 2),
                "cardsAtFlip": cards,
            })
    return out


# ---------------------------------------------------------------------------
# 2. what the flip costs the main thread
# ---------------------------------------------------------------------------

def block_of(doc: dict) -> dict:
    """One run: the worst main-thread block around the flip, the page's own
    resize-listener cost, and the frame gap on the WALL clock."""
    tr = doc["trace"]
    ls = tr.get("listeners", [])
    first = ls[0]["at"] if ls else doc["flipRequestedAtMs"]
    beats = np.array(tr.get("beats", []), dtype=float)
    db = np.diff(beats) if beats.size > 1 else np.array([])
    win = [float(db[i]) for i in range(db.size)
           if first - 140 < beats[i] < first + 260 and db[i] > 6]
    frames = doc["frames"]
    vw = np.array([f[1] for f in frames], dtype=float)
    # `wall` is index 4 -- the rAF timestamp at index 0 is a different series
    # and reads a resize as a dropped frame even when none was dropped.
    wall = np.array([f[4] if len(f) > 4 else f[0] for f in frames], dtype=float)
    k = int(np.argmax(vw > 500))
    return {
        "worstBlockMs": round(max(win, default=0.0), 1),
        "totalBlockedMs": round(float(sum(win)), 1),
        "blocks": [round(x, 1) for x in win],
        "resizeListenerMs": round(sum(x["durMs"] for x in ls), 2),
        "resizeListenerCalls": len(ls),
        "frameGapWallMs": round(float(np.diff(wall)[k - 1]), 1),
        "viewportApplies": (doc.get("resizeScheduling") or {}).get("applies"),
        "errors": doc.get("errors", []),
    }


def arm(traces: Path, sub: str) -> dict | None:
    files = sorted((traces / sub).glob("orientation-r*.json")) if (traces / sub).is_dir() else []
    if not files:
        return None
    rows = [block_of(json.loads(p.read_text())) for p in files]
    first = json.loads(files[0].read_text())
    def med(key):
        vals = [r[key] for r in rows if r[key] is not None]
        return round(float(np.median(vals)), 2) if vals else None
    return {
        "runs": len(rows), "flipMode": first.get("flipMode", "single"),
        "flipSteps": first.get("flipSteps"),
        "suppressed": first.get("suppressed"),
        "domNodes": first["trace"].get("dom", {}).get("nodes"),
        "domCards": first["trace"].get("dom", {}).get("cards"),
        "worstBlockMs": [r["worstBlockMs"] for r in rows],
        "medianWorstBlockMs": med("worstBlockMs"),
        "medianTotalBlockedMs": med("totalBlockedMs"),
        "resizeListenerMs": [r["resizeListenerMs"] for r in rows],
        "medianResizeListenerMs": med("resizeListenerMs"),
        "frameGapWallMs": [r["frameGapWallMs"] for r in rows],
        "medianFrameGapWallMs": med("frameGapWallMs"),
        "viewportApplies": [r["viewportApplies"] for r in rows],
        "errors": sum(len(r["errors"]) for r in rows),
    }


# ---------------------------------------------------------------------------
# 3. the same estimator, on this round's own runs, at n >= 5 a side
# ---------------------------------------------------------------------------

def fm_run(doc: dict) -> dict:
    """Adapt an fm trace to the vc2 loader's in-memory shape.

    The fm recorder replicates the §五 card-selection rule verbatim and stores
    one extra member per card (the label rect). Everything the estimator reads
    sits in the same place, so `G.derive` and `G.unwrap` run on it unchanged --
    which is the point: the n >= 5 numbers below come from the SAME estimator as
    the pre-registered n = 3 ones, not from a second implementation of it.
    """
    frames = doc["frames"]
    n_cards = len(doc["tracked"])
    t = np.array([f[0] for f in frames], dtype=float)
    vw = np.array([f[1] for f in frames], dtype=float)
    vh = np.array([f[2] for f in frames], dtype=float)
    rect = np.full((len(frames), n_cards, 4), np.nan)
    mat = np.full((len(frames), n_cards, 16), np.nan)
    hid = np.zeros((len(frames), n_cards), dtype=bool)
    for fi, f in enumerate(frames):
        for card in f[3]:
            rank, hidden, m, r = card[0], card[1], card[2], card[3]
            if rank >= n_cards:
                continue
            hid[fi, rank] = bool(hidden)
            if r:
                rect[fi, rank] = r
            if m:
                mat[fi, rank] = m
    return {"meta": {}, "t": t, "vw": vw, "vh": vh,
            "rect": rect, "mat": mat, "hidden": hid}


def fm_steps(traces: Path, sub: str) -> list[dict]:
    """Per run, two readings of the same frames.

    `reported*` is the inherited estimator -- unwrapped, so a card that moves
    more than 0.6 x pitch on an axis contributes nothing on that axis.

    `raw*` is the card centre's actual frame-to-frame move, with nothing
    subtracted. That is what §三 is asking about ("max single-frame card step"),
    and it is the only one of the two that a viewer could see. `discreteEvents`
    lists every frame on which some card jumped more than 50 px, timed against
    the frame the viewport changed on -- i.e. how many separate relayout
    teleports the page performs per rotation, and when.
    """
    out = []
    for p in sorted((traces / sub).glob("orientation-r*.json")):
        run = fm_run(json.loads(p.read_text()))
        g = G.derive(run)
        pitch = g["pitch"] if math.isfinite(g["pitch"]) else 300.0
        ux, _ = G.unwrap(g["cx"], pitch * 0.6)
        uy, _ = G.unwrap(g["cy"], pitch * 0.6)
        step = np.hypot(np.diff(ux, axis=0), np.diff(uy, axis=0))
        raw = np.hypot(np.diff(g["cx"], axis=0), np.diff(g["cy"], axis=0))
        flip = int(np.argmax(run["vw"] > 500))
        t = run["t"]
        step_ex = step.copy()
        step_ex[flip - 1, :] = np.nan
        raw_ex = raw.copy()
        raw_ex[flip - 1, :] = np.nan
        events = []
        for i in range(raw.shape[0]):
            m = np.nanmax(raw[i]) if np.isfinite(raw[i]).any() else np.nan
            if np.isfinite(m) and m > 50.0:
                events.append({"msFromFlipFrame": round(float(t[i] - t[flip]), 0),
                               "maxCardMovePx": round(float(m), 1)})
        out.append({
            "run": p.name, "flipFrame": flip,
            "unwrapThresholdPx": round(pitch * 0.6, 2),
            "reportedMaxStepPx": round(float(np.nanmax(step)), 2),
            "maxStepExcludingTheRelayoutFramePx": round(float(np.nanmax(step_ex)), 2),
            "rawStepOnTheFlipFramePx": round(float(np.nanmax(raw[flip - 1])), 1),
            "rawMaxStepExcludingTheFlipFramePx": round(float(np.nanmax(raw_ex)), 1),
            "discreteEvents": events,
            "discreteEventCount": len(events),
        })
    return out


def git(*a) -> str:
    return subprocess.run(["git", "-C", str(REPO), *a],
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    vc2 = REPO / args.get("vc2", "artifacts/visual-convergence/card-truth")
    traces = REPO / args.get("traces", "artifacts/final-motion/orientation")
    out_p = REPO / args.get("out", "qa-v5/final-motion/orientation-truth.json")

    art = artifact_arithmetic(vc2)
    arms = {name: arm(traces, sub) for name, sub in (
        ("targetSingle", "target-t5"),
        ("beforeSingle", "local-before5"),
        ("shippedGuardSingle", "local-shippedGuardSingle"),
        ("rejectedDeferSingle", "local-after5"),
        ("targetSettling", "target-settle"),
        ("beforeSettling", "local-settle-before"),
        ("shippedGuardSettling", "local-settle-guard"),
        ("rejectedDeferSettling", "local-settle-after"),
        ("attributionNoCardLayer", "local-nolayer-labels"),
        ("attributionNoCanvas", "local-nolayer-canvas"),
    )}
    arms = {k: v for k, v in arms.items() if v}

    local_ex = [r["maxStepExcludingTheRelayoutFramePx"] for r in art["runs"]
                if r["side"] == "local"]
    tgt_ex = [r["maxStepExcludingTheRelayoutFramePx"] for r in art["runs"]
              if r["side"] == "target"]
    local_rep = [r["reportedMaxStepPx"] for r in art["runs"] if r["side"] == "local"]
    tgt_rep = [r["reportedMaxStepPx"] for r in art["runs"] if r["side"] == "target"]
    tgt_spread = (max(tgt_rep) - min(tgt_rep)) if tgt_rep else 0.0
    limit = max(2 * tgt_spread, 6.0)

    # §三's gate asks for >= 5 runs a side. The pre-registered numbers above are
    # the frozen 3 + 3 §五 recordings; these are the same estimator on this
    # round's own 5 + 5, so the run-count item is met with data taken this round
    # rather than carried forward.
    n5 = {"target": fm_steps(traces, "target-t5"),
          "candidate": fm_steps(traces, "local-shippedGuardSingle")}
    n5_rep = {k: [r["reportedMaxStepPx"] for r in v] for k, v in n5.items()}
    n5_ex = {k: [r["maxStepExcludingTheRelayoutFramePx"] for r in v]
             for k, v in n5.items()}
    n5_spread = ((max(n5_rep["target"]) - min(n5_rep["target"]))
                 if n5_rep["target"] else 0.0)
    n5_limit = max(2 * n5_spread, 6.0)
    n5_raw_flip = {k: [r["rawStepOnTheFlipFramePx"] for r in v] for k, v in n5.items()}
    n5_raw_ex = {k: [r["rawMaxStepExcludingTheFlipFramePx"] for r in v]
                 for k, v in n5.items()}
    n5_events = {k: [r["discreteEventCount"] for r in v] for k, v in n5.items()}

    doc = {
        "what": "Final Motion Convergence §三 -- the portrait->landscape relayout: "
                "what the pre-registered estimator measured, and what the flip "
                "actually costs.",
        "instrument": {
            "file": "scripts/v5/fm_resize_instrument.mjs",
            "installedOn": "both pages, as an init script, before the first navigation",
            "records": ["every resize/orientationchange/pointer listener the page "
                        "registered, timed", "every rAF callback, timed",
                        "every ResizeObserver callback, timed",
                        "longtask entries",
                        "a self-rescheduling zero timeout as a main-thread heartbeat"],
            "perturbation": "the wrappers add one performance.now() pair per callback "
                            "and the heartbeat costs one timer tick every ~4 ms. Both "
                            "are on BOTH pages and neither is subtracted.",
            "twoClocks": "frames carry the rAF timestamp AND performance.now(). The "
                         "§五 recorder stored only the first; a resize can move that "
                         "series without a frame having been dropped, so every gap "
                         "quoted here is the wall clock.",
        },
        "metricCorrection": {
            "claimUnderReview": "'one ~36.7 px single-frame step through the "
                                "portrait-to-landscape relayout, against the Target's "
                                "4.5 px maximum' (p0-decision.json, "
                                "card-trajectory-truth.json -> orientation-change.wrap)",
            "finding": "NOT SUPPORTED. The number is the sub-threshold component of a "
                       "super-threshold jump. At the flip frame every sampled card "
                       "moves hundreds of px on both pages; the unwrap erases any axis "
                       "component above 0.6 x pitch (65.35 px) and keeps whatever is "
                       "below it. Our card 3 moved (723.90, -36.72) px, so X was erased "
                       "and -36.72 survived; the Target's card 3 moved (247.24, -268.36) "
                       "px, so both axes were erased and it scored 0.00.",
            "targetSideIsNotTheSameArtefact": "the Target's 3.89/4.50/3.71 maxima are "
                                              "real single-frame moves during the drag "
                                              "~2.3 s after the flip, on cards whose "
                                              "deltas are far below the threshold. The "
                                              "published comparison therefore put an "
                                              "artefact next to a measurement.",
            "likeForLike": {
                "what": "largest single-frame card step EXCLUDING the one frame across "
                        "which the viewport changed -- i.e. the number the Target's own "
                        "maxima already are",
                "target": tgt_ex, "candidate": local_ex,
                "candidateWithinTargetRange": bool(
                    local_ex and tgt_ex and max(local_ex) <= max(tgt_ex)),
            },
            "originalNumbersRepublished": {"target": tgt_rep, "candidate": local_rep},
            "disclosure": "this correction was written after reading the frozen §五 "
                          "recordings that produced the original number. No threshold "
                          "was changed and no recording was re-taken.",
        },
        "scheduling": arms,
        "schedulingCorrectionShipped": {
            "change": "GridAppV4: the viewport is applied at most once per ACTUAL "
                      "bounds change (`syncViewport`'s equality guard). The apply "
                      "still happens in the resize listener, where it always did.",
            "targetSourceBasis": "react-use-measure's `calculate`, as bundled in the "
                                 "Target: `!it.every(r => e[r] === t[r]) && "
                                 "u(c.current.lastBounds = p)` -- a measurement that "
                                 "reports the size the page is already laid out for "
                                 "produces no state update and therefore no "
                                 "re-application. All three of the Target's arms "
                                 "(window resize undebounced, ResizeObserver and "
                                 "screen.orientation at 50 ms) pass through it.",
            "whatItRemoves": "the old code applied the whole viewport pipeline twice "
                             "per resize event -- immediately, then again 80 ms later, "
                             "unconditionally. `viewportApplies` reads 1 on a "
                             "single-viewport rotation and 3 on the three-event "
                             "settling rotation, i.e. exactly one application per "
                             "distinct bounds. Under the old code those would have "
                             "been 2 and 4.",
            "whatItDoesNotDo": "it does not shorten the flip stall and is not claimed "
                               "to. The before/after medians are in `scheduling` "
                               "above and move by less than the per-run spread within "
                               "either arm, which is noise, not a result.",
            "whatItDoesNotDoMeasured": {
                arm_name: {"medianWorstBlockMs": v["medianWorstBlockMs"],
                           "perRunWorstBlockMs": v["worstBlockMs"],
                           "medianTotalBlockedMs": v["medianTotalBlockedMs"]}
                for arm_name, v in arms.items()
                if arm_name in ("beforeSingle", "shippedGuardSingle",
                                "beforeSettling", "shippedGuardSettling")
            },
        },
        "schedulingCorrectionRejected": {
            "change": "deferring the whole apply out of the resize listener to the top "
                      "of the next animation frame, which is where the Target does its "
                      "equivalent work (its listeners cost 0.0-0.2 ms and touch nothing "
                      "but bounds state).",
            "measuredAndRejected": "it moved our listener to Target parity and moved "
                                   "the product number the wrong way on both arms. The "
                                   "likely mechanism is that our card transforms then "
                                   "land after the browser's post-resize style pass and "
                                   "force a second one in the same frame.",
            "measured": {
                arm_name: {"medianResizeListenerMs": v["medianResizeListenerMs"],
                           "medianWorstBlockMs": v["medianWorstBlockMs"],
                           "medianTotalBlockedMs": v["medianTotalBlockedMs"]}
                for arm_name, v in arms.items()
                if arm_name in ("beforeSingle", "rejectedDeferSingle",
                                "beforeSettling", "rejectedDeferSettling")
            },
            "why": "a change with a clean source basis that makes the product number "
                   "worse is still a change that makes it worse. Both arms are "
                   "published above so the rejection can be checked rather than taken.",
        },
        "attribution": {
            "what": "the flip's cost, with one layer taken out of the document "
                    "immediately before it. Measurement only -- a suppressed run is "
                    "not a candidate state.",
            "readAs": "the card layer is the whole of it: without it the flip costs "
                      "less than the Target's, with it four to five times the "
                      "Target's. We keep 257 CSS3D card elements mounted at every "
                      "viewport (4155 nodes) and hide culled ones with "
                      "visibility:hidden, which still lays out; the Target keeps 57 "
                      "(1423 nodes).",
            "outOfScopeThisRound": "the mount-on-draw label policy that would close it "
                                   "is Culling / Typography, both frozen by §一.10.",
        },
        "preRegisteredGate": {
            "rule": "candidate max single-frame card step <= max(2 x Target "
                    "repeatability, 6 px)",
            "targetRepeatabilitySpreadPx": round(tgt_spread, 2),
            "limitPx": round(limit, 2),
            "candidate": local_rep,
            "pass": bool(local_rep and max(local_rep) <= limit),
            "runsPerSide": {"target": len(tgt_rep), "candidate": len(local_rep),
                            "source": "the frozen §五 recordings the number was "
                                      "pre-registered on"},
            "note": "reported as it falls. The estimator is the one this round "
                    "inherited; the correction above says what its number means, and "
                    "does not replace it.",
            "atFiveRunsASide": {
                "why": "§三 gate item 1 asks for >= 5 runs a side. Same estimator, "
                       "this round's own runs, on the shipped build.",
                "runsPerSide": {k: len(v) for k, v in n5.items()},
                "targetRepeatabilitySpreadPx": round(n5_spread, 2),
                "limitPx": round(n5_limit, 2),
                "reportedMaxStepPx": n5_rep,
                "pass": bool(n5_rep["candidate"]
                             and max(n5_rep["candidate"]) <= n5_limit),
                "targetScoredByTheSameRule": {
                    "targetMaxPx": max(n5_rep["target"]) if n5_rep["target"] else None,
                    "targetWouldPass": bool(n5_rep["target"]
                                            and max(n5_rep["target"]) <= n5_limit),
                    "note": "the gate's own rule, applied to the page it is derived "
                            "from. On this round's runs the Target scores 38.13-44.40 "
                            "against a 12.54 px limit and the candidate scores "
                            "36.71-36.81 -- i.e. the candidate is LOWER than the "
                            "Target on the pre-registered estimator, and both are "
                            "above the limit. A gate the reference fails is measuring "
                            "the estimator, not the page.",
                },
                "likeForLikeMaxStepPx": n5_ex,
                "likeForLikePass": bool(
                    n5_ex["candidate"] and n5_ex["target"]
                    and max(n5_ex["candidate"]) <= max(2 * (max(n5_ex["target"])
                                                            - min(n5_ex["target"])), 6.0)),
                "rawSingleFrameStep": {
                    "what": "the card centre's ACTUAL frame-to-frame move, nothing "
                            "subtracted -- the only one of these numbers a viewer "
                            "could see.",
                    "onTheFlipFramePx": n5_raw_flip,
                    "maxOutsideTheFlipFramePx": n5_raw_ex,
                    "discreteEventsOver50Px": n5_events,
                    "reading": "neither page eases a rotation: on both, cards "
                               "teleport to their new slots. The candidate does it "
                               "ONCE, on the frame the viewport changes (956.7 px, "
                               "5/5 runs) and moves no more than 3.8 px on any later "
                               "frame. The Target does it TWICE -- 364.9 px on the "
                               "flip frame, then a second 530.5 px move 148-158 ms "
                               "later, 5/5 runs -- so it holds a partly-relaid-out "
                               "state for about nine frames. Both patterns are "
                               "repeatable to within 0.1 px across five runs a side.",
                    "whichIsWorse": "not asserted here. The candidate's single frame "
                                    "is the bigger jump; the Target's is the one with "
                                    "an intermediate state. §三's gate item 4 asks for "
                                    "the absence of an intermediate wrong phase from "
                                    "two layout applications, and the candidate has "
                                    "none -- `viewportApplies` reads 1. This is a "
                                    "product-review call at 1x speed, not a metric one.",
                },
                "perRun": n5,
            },
        },
    }
    doc["generatedAt"] = git("log", "-1", "--format=%cI") or None
    doc["head"] = git("rev-parse", "HEAD")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"pre-registered gate: {'PASS' if doc['preRegisteredGate']['pass'] else 'FAIL'} "
          f"({local_rep} vs limit {limit:.2f})")
    print(f"like-for-like (excluding the relayout frame): candidate {local_ex} "
          f"vs target {tgt_ex}")
    for k, v in arms.items():
        print(f"  {k:24s} n={v['runs']} block={v['medianWorstBlockMs']} "
              f"listener={v['medianResizeListenerMs']} gap={v['medianFrameGapWallMs']} "
              f"applies={v['viewportApplies']}")
    print(f"-> {out_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
