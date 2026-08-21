#!/usr/bin/env python3
"""The absolute coverage gate: rule vs Target, rule vs Candidate, lane vs lane.

FOUR verdicts come out of here, each written as data:

1. TARGET RULE SOURCE VERIFICATION -- the byte-anchored rule, replayed on the
   Target's OWN recorded frames (camera recovered from its CSS3D matrix with
   the dolly solved out, absolute scroll inverted from its live card
   matrices), must reproduce the Target's own per-frame visible label set,
   slot for slot.
2. CANDIDATE RULE CONSISTENCY -- the same replay on the Candidate's recorded
   engine truth must reproduce the Candidate's per-frame DOM, slot for slot,
   and the page-computed verdict snapshots must agree with the replay to
   float precision.
3. SLOT-LEVEL LANE IDENTITY -- at every SETTLED state (rest, pointer centre,
   four corners, after resize, after orientation flip) the Candidate's
   visible slot set must equal the Target's, BY ILG CODE, not by count.
4. LOST / INTRUDING LABELS -- no DOM-hidden label whose replayed AABB
   overlaps the strict viewport (a lost label), and no DOM-visible label
   whose replayed AABB sits outside the 64 px margin viewport (an intruder),
   beyond float-boundary noise.

Mismatches within BOUNDARY_PX of a deciding threshold are reported separately
as boundary-sensitive rather than silently forgiven: the number is in the
output and the gate line says how many of the failures it explains.

Usage: v0-coverage-truth.py --target=<trace> --before=<trace>
                            --candidate=<trace> --outdir=<dir>
"""
from __future__ import annotations

import importlib.util
import json
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


VC = _load("v0_culling", "v0_culling.py")
SL = sys.modules["source_layout"]

SETTLED_STATES = ["rest", "pointer-centre", "pointer-corner-tl", "pointer-corner-tr",
                  "pointer-corner-br", "pointer-corner-bl", "resize-settle",
                  "orientation-flip"]
GESTURE_STATES = ["slow-horizontal-drag", "fast-flick", "reverse-flick",
                  "touch-drag-release", "long-drag-multi-wrap"]

# A verdict whose deciding quantity sits within this of its threshold can flip
# on float noise between the page, the replay and the recorded matrix. The
# smoke measurement put replay-vs-page at 6.8e-13 px; recovered-scroll noise
# on the Target lane is bounded by the style string's precision. 0.05 px is
# five orders above both and five orders below one card.
BOUNDARY_PX = 0.05

# Snapshot AABBs must agree with the replay far below a pixel; measured
# 6.8e-13 px, gated at 1e-6.
SNAPSHOT_AABB_PX = 1e-6

# A slot whose wrap arc sits within this many WORLD UNITS of the +-period/2
# seam relocates by a FULL PERIOD when the recovered scroll wobbles by float
# noise -- and at scroll exactly 0 the seam column sits mathematically ON the
# boundary, so the Target lane (whose scroll is recovered, not read) can land
# either side. Measured recovered-scroll noise is ~1e-4 world units; one card
# is hundreds. Proximity alone does NOT bucket a mismatch: it is only the
# prefilter. The flip must REPRODUCE -- the verdict is re-run with the
# recovered scroll perturbed by +-SEAM_PERTURB_WORLD_UNITS (10x the measured
# noise) and the row is seam-bucketed only if the draw verdict actually flips
# under perturbation. A real rule failure that merely sits near a seam stays
# beyond-boundary, because 1e-4 noise cannot flip it. The candidate lane
# replays from the page's own truth and cannot produce seam rows at all.
SEAM_WORLD_UNITS = 0.01
SEAM_PERTURB_WORLD_UNITS = 1e-3

# A VISIBLE label's recorded DOM rect must match its replayed AABB at settled
# states to this tolerance (measured agreement is ~0.01 px; the recorder
# rounds rects to 0.01 px).
STALE_RECT_PX = 0.5


def obs_visible(pool, labels):
    return {pool[i] for i, rec in enumerate(labels) if rec is not None}


def frame_pool(run, f):
    pools = run.get("pools")
    if pools:
        return pools[min(f.get("pv", 0), len(pools) - 1)]
    return run["pool"]


# The Target re-grids its label pool AND its layout state on a DEBOUNCED
# commit after resize (the 150 ms debounce is a byte-anchored site in
# target-culling-source.json), while its coverage camera tracks the new
# window dimensions on the very next frame. Between the resize and the
# debounced commit the page therefore culls OLD slot placements against the
# NEW viewport -- a state the offline replay cannot reproduce, because
# SL.layout(w, h) is the FINAL layout for the new dimensions. Those frames
# are transition, not evidence either way; the settled gates (slot identity,
# stale rects) prove the post-resize state. 450 ms covers the debounce plus
# the React commit with margin.
POST_RESIZE_DEBOUNCE_MS = 450.0

RESIZE_STATES = {"resize-settle", "orientation-flip"}


def stable_frames(frames, state=None):
    """Frames outside every resize-transition window.

    A sample is excluded when it sits within 3 samples BEFORE a viewport
    change or pool rebind (a resize applies mid-frame relative to the page's
    own writes), or within POST_RESIZE_DEBOUNCE_MS AFTER one. For the states
    whose driver resizes IMMEDIATELY at start (resize-settle,
    orientation-flip) the run start is seeded as a change point, because the
    first sample can already carry the new dimensions and the change would
    otherwise be invisible. The per-run row reports how many frames this
    excluded."""
    n = len(frames)
    hot = [False] * n
    change_ts = [0.0] if state in RESIZE_STATES else []
    for i, f in enumerate(frames):
        changed = (i > 0 and (f["w"] != frames[i - 1]["w"]
                              or f["h"] != frames[i - 1]["h"])) or f.get("rd")
        if changed:
            change_ts.append(f["t"])
            for k in range(max(0, i - 3), i + 1):
                hot[k] = True
    for i, f in enumerate(frames):
        if any(ct <= f["t"] <= ct + POST_RESIZE_DEBOUNCE_MS for ct in change_ts):
            hot[i] = True
    return [f for i, f in enumerate(frames) if not hot[i]]


def seam_distance(code, scroll_x, scroll_y, frame):
    """Distance (world units) of a slot's wrap arcs from the +-period/2 seam."""
    p = SL.place(code - 1, scroll_x, scroll_y, frame)
    half_x, half_y = 0.5 * frame["periodX"], 0.5 * frame["periodY"]
    return min(abs(abs(p["xArc"]) - half_x), abs(abs(p["yArc"]) - half_y))


def seam_flip_reproduces(code, scroll_x, scroll_y, cam, frame, base_draw):
    """Does the slot's draw verdict actually FLIP when the recovered scroll is
    perturbed by 10x the measured noise? Bracketing, not proximity."""
    w, h = frame["viewport"]
    for dx, dy in ((SEAM_PERTURB_WORLD_UNITS, 0.0), (-SEAM_PERTURB_WORLD_UNITS, 0.0),
                   (0.0, SEAM_PERTURB_WORLD_UNITS), (0.0, -SEAM_PERTURB_WORLD_UNITS)):
        m = VC.slot_matrix(code - 1, scroll_x + dx, scroll_y + dy, frame)
        if VC.verdict(m, cam, w, h)["draw"] != base_draw:
            return True
    return False


def replay_inputs(run, f, pool, frame, lane):
    """(scroll_x, scroll_y, cam) for a frame, per lane discipline: the Target
    from its own recorded matrix and inverted card positions, our lanes from
    the page's published truth."""
    if lane == "target":
        pos = VC.parse_camera_position(f["camera"])
        if pos is None:
            return None
        cam = VC.camera_from_recorded_position(pos, frame)
        sc = VC.recover_scroll(pool, f["labels"], frame)
        if sc is None:
            return None
        return sc[0], sc[1], cam
    if not f.get("truth"):
        return None
    cam = VC.coverage_camera(f["truth"][2], f["truth"][3], frame)
    return f["truth"][0], f["truth"][1], cam


def check_stale_rects(run, lane):
    """Brief 7.8, made explicit: a label that IS visible must also be WHERE
    the rule says it is. The set comparison catches wrong visibility; this
    catches a frozen transform on a label that stayed visible -- a
    stale-but-visible label would pass every set check while standing at its
    old position. Settled states only, on the last stable frame: there the
    dolly is at rest, so the coverage AABB and the CSS3D-projected DOM rect
    legitimately coincide (mid-gesture they differ by the dolly BY DESIGN,
    and a per-frame version of this check would be wrong). Restricted to
    rule-DRAWN slots with all four corners in frustum: the BEFORE lane keeps
    backface and far-off-screen labels visible, and a behind-camera
    projection is not comparable to a DOM rect. On the Target lane a
    wrap-seam slot (the same bracketing as the rule check: near the seam AND
    the flip reproduces under 10x-noise perturbation) relocates by a full
    period on recovered-scroll noise -- its rect delta measures the seam, not
    a frozen transform -- so it is reported in its own bucket, never as
    stale and never silently."""
    frames = stable_frames(run["frames"], run["state"])
    if not frames:
        return None
    f = frames[-1]
    pool = frame_pool(run, f)
    frame = SL.layout(f["w"], f["h"])
    inputs = replay_inputs(run, f, pool, frame, lane)
    if inputs is None:
        return None
    scroll_x, scroll_y, cam = inputs
    pred = VC.frame_verdicts(scroll_x, scroll_y, cam, frame)
    checked = 0
    worst = 0.0
    stale = []
    seam_rows = []
    for i, rec in enumerate(f["labels"]):
        if rec is None or i >= len(pool):
            continue
        code = pool[i]
        v = pred.get(code)
        if not v or not v["draw"] or not v["aabb"] or not all(v["quad"]):
            continue
        rx, ry, rw, rh = rec[3], rec[4], rec[5], rec[6]
        ax0, ay0, ax1, ay1 = v["aabb"]
        d = max(abs(rx - ax0), abs(ry - ay0),
                abs(rx + rw - ax1), abs(ry + rh - ay1))
        if d > STALE_RECT_PX and lane == "target":
            # A seam slot can be DRAWN on both sides of the wrap (both
            # placements inside the margin viewport), so the draw-flip test
            # proves nothing here. The demonstration is positional: perturb
            # the recovered scroll by 10x its measured noise and show the
            # replayed AABB then MATCHES the recorded DOM rect -- i.e. the
            # DOM stands at the wrapped placement, not at a frozen one.
            seam = seam_distance(code, scroll_x, scroll_y, frame)
            if seam <= SEAM_WORLD_UNITS:
                w_, h_ = frame["viewport"]
                matched = None
                for dx, dy in ((SEAM_PERTURB_WORLD_UNITS, 0.0),
                               (-SEAM_PERTURB_WORLD_UNITS, 0.0),
                               (0.0, SEAM_PERTURB_WORLD_UNITS),
                               (0.0, -SEAM_PERTURB_WORLD_UNITS)):
                    m2 = VC.slot_matrix(code - 1, scroll_x + dx, scroll_y + dy,
                                        frame)
                    v2 = VC.verdict(m2, cam, w_, h_)
                    if not v2["aabb"]:
                        continue
                    b0, b1, b2, b3 = v2["aabb"]
                    d2 = max(abs(rx - b0), abs(ry - b1),
                             abs(rx + rw - b2), abs(ry + rh - b3))
                    if d2 <= STALE_RECT_PX:
                        matched = d2
                        break
                if matched is not None:
                    seam_rows.append({"code": code, "deltaPx": round(d, 3),
                                      "seamDistanceWorldUnits": round(seam, 6),
                                      "perturbedDeltaPx": round(matched, 4)})
                    continue
        checked += 1
        worst = max(worst, d)
        if d > STALE_RECT_PX:
            stale.append({"code": code, "deltaPx": round(d, 3),
                          "rect": [rx, ry, rw, rh],
                          "aabb": [round(x, 3) for x in v["aabb"]]})
    return {"viewport": run["viewport"], "state": run["state"],
            "visibleDrawnChecked": checked, "worstDeltaPx": round(worst, 4),
            "staleLabels": stale, "wrapSeamRelocated": seam_rows,
            "pass": len(stale) == 0}


def check_run_against_replay(run, lane):
    """Per-frame: replayed draw-set vs recorded DOM visible set."""
    all_frames = run["frames"]
    frames = stable_frames(all_frames, run["state"])
    checked = mismatched_frames = 0
    mism_slots = []
    lost, intruders = [], []
    layouts = {}
    for f in frames:
        pool = frame_pool(run, f)
        w, h = f["w"], f["h"]
        frame = layouts.get((w, h))
        if frame is None:
            frame = layouts[(w, h)] = SL.layout(w, h)
        inputs = replay_inputs(run, f, pool, frame, lane)
        if inputs is None:
            continue
        scroll_x, scroll_y, cam = inputs
        pred = VC.frame_verdicts(scroll_x, scroll_y, cam, frame)
        pred_vis = {c for c, v in pred.items() if v["draw"]}
        obs = obs_visible(pool, f["labels"])
        # Codes beyond the active pool (a lane's spare slots) never appear on
        # either side; codes the lane's pool lacks entirely cannot be judged.
        obs &= set(pred.keys())
        checked += 1
        if pred_vis == obs:
            continue
        mismatched_frames += 1
        for c in pred_vis ^ obs:
            v = pred[c]
            # Two distinct sensitivities, measured separately: the px margin
            # to the verdict threshold, and the world-unit distance to the
            # wrap seam. A seam slot relocates by a FULL PERIOD on recovered
            # -scroll noise, so its px margin says nothing about robustness.
            seam = seam_distance(c, scroll_x, scroll_y, frame)
            seam_sensitive = (lane == "target" and seam <= SEAM_WORLD_UNITS
                              and seam_flip_reproduces(c, scroll_x, scroll_y,
                                                       cam, frame, c in pred_vis))
            row = {"t": f["t"], "code": c,
                   "predictedDraw": c in pred_vis, "domVisible": c in obs,
                   "rejectionReason": v["rejectionReason"],
                   "boundaryMarginPx": round(v["boundaryMarginPx"], 6),
                   "seamDistanceWorldUnits": round(seam, 6),
                   "wrapSeamSensitive": seam_sensitive}
            mism_slots.append(row)
            if seam_sensitive:
                continue
            if c in pred_vis and v["overlap"] > 0:
                lost.append(row)      # rule says on screen, DOM hides it
            if c in obs and v["rejectionReason"] == "outsideMarginViewport" \
                    and v["boundaryMarginPx"] > BOUNDARY_PX:
                intruders.append(row)  # DOM shows it, rule puts it outside
    explained = [r for r in mism_slots
                 if r["boundaryMarginPx"] <= BOUNDARY_PX or r["wrapSeamSensitive"]]
    seam_rows = [r for r in mism_slots if r["wrapSeamSensitive"]]
    return {
        "viewport": run["viewport"], "state": run["state"],
        "framesChecked": checked,
        "framesExcludedAsTransition": len(all_frames) - len(frames),
        "framesWithMismatch": mismatched_frames,
        "slotMismatches": len(mism_slots),
        "slotMismatchesWithinBoundary": len(explained) - len(seam_rows),
        "slotMismatchesWrapSeam": len(seam_rows),
        "slotMismatchesBeyondBoundary": len(mism_slots) - len(explained),
        "lostLabels": len(lost),
        "intrudingLabels": len(intruders),
        "worstMismatches": sorted(
            (r for r in mism_slots
             if r["boundaryMarginPx"] > BOUNDARY_PX and not r["wrapSeamSensitive"]),
            key=lambda r: -r["boundaryMarginPx"])[:5],
    }


def check_snapshot(run):
    """Page-computed verdicts vs the replay, on the run's final truth."""
    snap = run.get("snapshot")
    frames = [f for f in run["frames"] if f.get("truth")]
    if not snap or not frames or "slots" not in snap:
        return None
    f = frames[-1]
    frame = SL.layout(f["w"], f["h"])
    cam = VC.coverage_camera(f["truth"][2], f["truth"][3], frame)
    pred = VC.frame_verdicts(f["truth"][0], f["truth"][1], cam, frame)
    worst = 0.0
    verdict_mism = 0
    checked = 0
    for s in snap["slots"]:
        v = s.get("culling")
        if not v or v["rejectionReason"] == "inactive":
            continue
        p = pred.get(s["slotIndex"] + 1)
        if p is None:
            continue
        checked += 1
        if v["coverageVisible"] != p["draw"] or v["strictViewportVisible"] != p["interactive"]:
            verdict_mism += 1
        if v.get("projectedAabbPx") and p["aabb"]:
            worst = max(worst, max(abs(a - b)
                        for a, b in zip(v["projectedAabbPx"], p["aabb"])))
    return {"viewport": run["viewport"], "state": run["state"],
            "slotsChecked": checked, "verdictMismatches": verdict_mism,
            "worstAabbDeltaPx": worst,
            "pass": verdict_mism == 0 and worst <= SNAPSHOT_AABB_PX}


def settled_visible(run):
    f = run["frames"][-1]
    return sorted(obs_visible(frame_pool(run, f), f["labels"]))


def _clip_half(poly, a, b):
    """Sutherland-Hodgman: keep the part of poly left of edge a->b."""
    out = []
    ax, ay = a
    bx, by = b

    def side(p):
        return (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)

    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        sp, sq = side(p), side(q)
        if sp <= 0:
            out.append(p)
        if (sp < 0) != (sq < 0) and sp != sq:
            k = sp / (sp - sq)
            out.append((p[0] + k * (q[0] - p[0]), p[1] + k * (q[1] - p[1])))
    return out


def _poly_area(poly):
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def _orient(q):
    s = sum(q[i][0] * q[(i + 1) % len(q)][1] - q[(i + 1) % len(q)][0] * q[i][1]
            for i in range(len(q)))
    return q if s < 0 else list(reversed(q))


def _poly_intersect(q1, q2):
    p = [tuple(pt) for pt in q2]
    for i in range(len(q1)):
        p = _clip_half(p, q1[i], q1[(i + 1) % len(q1)])
        if not p:
            return []
    return p


def depth_check(cand):
    """Do any two card planes ACTUALLY overlap where ink is painted? Measured
    as polygon intersection of the projected QUADS (not AABBs -- neighbouring
    tilted cards' AABBs overlap without the planes doing so), restricted to
    FRONT-FACING planes (the Target's backface test is CSS
    `backface-visibility:hidden`, so a coverage-drawn back-facing plane
    paints no ink and cannot conflict with anything), and the intersection
    clipped to the strict viewport (an overlap that lives entirely in the
    64 px margin band is never on screen). All three numbers are reported so
    the NOT-APPLICABLE claim is a measurement, not an assumption."""
    samples = 0
    any_pairs = 0
    front_pairs = 0
    front_worst_band = 0.0
    strict_pairs = 0
    strict_worst = 0.0
    strict_rows = []
    for run in cand["runs"]:
        if run["state"] not in SETTLED_STATES:
            continue
        snap = run.get("snapshot")
        if not snap or "slots" not in snap:
            continue
        f = run["frames"][-1]
        vp = _orient([(0.0, 0.0), (f["w"], 0.0), (f["w"], f["h"]), (0.0, f["h"])])
        quads = []
        for s in snap["slots"]:
            v = s.get("culling")
            if not v or not v["coverageVisible"]:
                continue
            q = [p for p in v["projectedQuad"] if p]
            if len(q) == 4:
                quads.append((s["slotIndex"] + 1, v["backfaceVisible"],
                              _orient([tuple(p) for p in q])))
        samples += 1
        for i in range(len(quads)):
            for j in range(i + 1, len(quads)):
                inter = _poly_intersect(quads[i][2], quads[j][2])
                a = _poly_area(inter) if inter else 0.0
                if a <= 1e-9:
                    continue
                any_pairs += 1
                if not (quads[i][1] and quads[j][1]):
                    continue
                front_pairs += 1
                front_worst_band = max(front_worst_band, a)
                on_screen = _poly_intersect(vp, inter)
                sa = _poly_area(on_screen) if on_screen else 0.0
                if sa > 1e-9:
                    strict_pairs += 1
                    strict_worst = max(strict_worst, sa)
                    strict_rows.append({"viewport": run["viewport"],
                                        "state": run["state"],
                                        "codes": [quads[i][0], quads[j][0]],
                                        "onScreenAreaPx2": round(sa, 2)})
    return {
        "settledSamples": samples,
        "projectedQuadPairsIntersecting": any_pairs,
        "frontFacingPairsIntersecting": front_pairs,
        "frontFacingWorstAreaPx2": round(front_worst_band, 2),
        "frontFacingPairsInsideStrictViewport": strict_pairs,
        "worstOnScreenAreaPx2": round(strict_worst, 2),
        "onScreenRows": strict_rows,
        "status": ("NOT APPLICABLE — no overlapping card planes on screen: "
                   f"{front_pairs} front-facing pairs intersect only inside "
                   "the 64 px margin band (worst "
                   f"{front_worst_band:.2f} px², never inside the strict "
                   "viewport), and every larger projected intersection "
                   "involves a back-facing plane that paints no ink (CSS "
                   "backface-visibility)"
                   if strict_pairs == 0 else
                   f"{strict_pairs} front-facing pairs overlap ON SCREEN, "
                   f"worst {strict_worst:.2f} px²"),
    }


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    target = json.loads(Path(args["target"]).read_text())
    before = json.loads(Path(args["before"]).read_text())
    cand = json.loads(Path(args["candidate"]).read_text())
    outdir = Path(args["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)

    # -- 1 & 2: rule replay per lane, per run --------------------------------
    target_rows = [check_run_against_replay(r, "target") for r in target["runs"]]
    cand_rows = [check_run_against_replay(r, "candidate") for r in cand["runs"]]
    snapshots = [s for s in (check_snapshot(r) for r in cand["runs"]) if s]

    def tally(rows):
        return {
            "runs": len(rows),
            "framesChecked": sum(r["framesChecked"] for r in rows),
            "framesWithMismatch": sum(r["framesWithMismatch"] for r in rows),
            "slotMismatches": sum(r["slotMismatches"] for r in rows),
            "withinBoundary": sum(r["slotMismatchesWithinBoundary"] for r in rows),
            "wrapSeam": sum(r["slotMismatchesWrapSeam"] for r in rows),
            "beyondBoundary": sum(r["slotMismatchesBeyondBoundary"] for r in rows),
            "lostLabels": sum(r["lostLabels"] for r in rows),
            "intrudingLabels": sum(r["intrudingLabels"] for r in rows),
        }

    t_sum, c_sum = tally(target_rows), tally(cand_rows)
    coverage = {
        "what": "the byte-anchored coverage rule replayed against every lane's "
                "own recorded frames, slot for slot",
        "boundaryPx": BOUNDARY_PX,
        "seamWorldUnits": SEAM_WORLD_UNITS,
        "targetRuleVerification": {
            **t_sum,
            "pass": t_sum["beyondBoundary"] == 0,
            "perRun": target_rows,
        },
        "candidateRuleConsistency": {
            **c_sum,
            "pass": c_sum["beyondBoundary"] == 0,
            "perRun": cand_rows,
        },
        "candidateSnapshotBitExactness": {
            "snapshots": len(snapshots),
            "pass": all(s["pass"] for s in snapshots),
            "worstAabbDeltaPx": max((s["worstAabbDeltaPx"] for s in snapshots),
                                    default=0.0),
            "perSnapshot": snapshots,
        },
        "depthCarryForward": depth_check(cand),
    }

    # -- console and page errors, straight from the captures ------------------
    def lane_errors(trace):
        return (sum(len(r.get("errors", [])) for r in trace["runs"])
                + len(trace.get("errors", [])))

    coverage["consoleAndPageErrors"] = {
        "target": lane_errors(target),
        "before": lane_errors(before),
        "candidate": lane_errors(cand),
        "pass": lane_errors(cand) == 0 and lane_errors(before) == 0,
    }

    # -- 7.8 stale-but-visible: rect vs replayed AABB at settled states ------
    stale_rows = []
    for lane_name, trace in (("target", target), ("before", before),
                             ("candidate", cand)):
        for run in trace["runs"]:
            if run["state"] not in SETTLED_STATES:
                continue
            row = check_stale_rects(run, lane_name)
            if row is not None:
                stale_rows.append({"lane": lane_name, **row})
    coverage["staleRectCheck"] = {
        "what": "a VISIBLE label must also be WHERE the rule says: recorded "
                "DOM rect vs replayed AABB per drawn slot, last stable frame "
                "of every settled state, all lanes. Catches a frozen "
                "transform that every set comparison would miss.",
        "tolerancePx": STALE_RECT_PX,
        "rows": len(stale_rows),
        "visibleDrawnChecked": sum(r["visibleDrawnChecked"] for r in stale_rows),
        "worstDeltaPx": max((r["worstDeltaPx"] for r in stale_rows), default=0.0),
        "staleLabels": sum(len(r["staleLabels"]) for r in stale_rows),
        "wrapSeamRelocated": sum(len(r["wrapSeamRelocated"]) for r in stale_rows),
        "pass": all(r["pass"] for r in stale_rows) and len(stale_rows) > 0,
        "perRun": stale_rows,
    }
    (outdir / "coverage-truth.json").write_text(json.dumps(coverage, indent=1) + "\n")

    # -- 3: settled-state slot identity, lane vs lane ------------------------
    def index(trace):
        return {(r["viewport"], r["state"]): r for r in trace["runs"]}

    ti, bi, ci = index(target), index(before), index(cand)
    rows = []
    for key in sorted(ci.keys()):
        vp, state = key
        if state not in SETTLED_STATES:
            continue
        tr, br, cr = ti.get(key), bi.get(key), ci.get(key)
        tv = settled_visible(tr) if tr else None
        cv = settled_visible(cr)
        bv = settled_visible(br) if br else None
        rows.append({
            "viewport": vp, "state": state,
            "targetVisibleCodes": tv, "candidateVisibleCodes": cv,
            "beforeVisibleCount": len(bv) if bv is not None else None,
            "targetVisibleCount": len(tv) if tv is not None else None,
            "candidateVisibleCount": len(cv),
            "identical": tv == cv,
        })
    identical = sum(1 for r in rows if r["identical"])
    slot_verdicts = {
        "what": "visible slot IDENTITY at every settled state -- by ILG code, "
                "never by count",
        "comparisons": len(rows),
        "identical": identical,
        "pass": identical == len(rows),
        "rows": rows,
    }
    (outdir / "slot-verdicts.json").write_text(json.dumps(slot_verdicts, indent=1) + "\n")

    # -- pop-in: label entries during gestures -------------------------------
    def entries(run):
        out = []
        prev = None
        for f in run["frames"]:
            pool = frame_pool(run, f)
            vis = obs_visible(pool, f["labels"])
            if prev is not None:
                for c in vis - prev:
                    i = pool.index(c)
                    rec = f["labels"][i]
                    rx, ry, rw, rh = rec[3], rec[4], rec[5], rec[6]
                    su = min(rx + rw, f["w"]) - max(rx, 0)
                    sc_ = min(ry + rh, f["h"]) - max(ry, 0)
                    out.append({"t": f["t"], "code": c,
                                "strictOverlapPx": round(min(su, sc_), 2)
                                if (su > 0 and sc_ > 0) else 0.0})
            prev = vis
        return out

    pop = {"what": "labels ENTERING visibility during gestures: how deep inside "
                   "the strict viewport was the label on its first visible "
                   "frame? 0 means it recovered inside the 64 px margin band, "
                   "before reaching the viewport -- the Target's own rule pops "
                   "a label deeper than 0 only when a frame's motion outruns "
                   "the band, so the gate is candidate-vs-target, not an "
                   "absolute no-entry line",
           "perLane": {}}
    for lane_name, trace in (("target", target), ("before", before), ("candidate", cand)):
        lane_rows = []
        for run in trace["runs"]:
            if run["state"] not in GESTURE_STATES:
                continue
            ee = entries(run)
            deep = [e["strictOverlapPx"] for e in ee]
            lane_rows.append({
                "viewport": run["viewport"], "state": run["state"],
                "entries": len(ee),
                "entriesInsideStrictViewport": sum(1 for d in deep if d > 0),
                "maxStrictOverlapPx": max(deep, default=0.0),
                "p95StrictOverlapPx": (sorted(deep)[int(0.95 * (len(deep) - 1))]
                                       if deep else 0.0),
            })
        pop["perLane"][lane_name] = lane_rows

    def lane_max(name):
        return max((r["maxStrictOverlapPx"] for r in pop["perLane"][name]), default=0.0)

    pop["candidateMaxStrictOverlapPx"] = lane_max("candidate")
    pop["targetMaxStrictOverlapPx"] = lane_max("target")
    pop["pass"] = pop["candidateMaxStrictOverlapPx"] <= max(
        pop["targetMaxStrictOverlapPx"] * 1.5, 8.0)
    (outdir / "edge-pop-in.json").write_text(json.dumps(pop, indent=1) + "\n")

    # -- transform / visibility write pressure -------------------------------
    def write_stats(trace):
        rows = []
        for run in trace["runs"]:
            frames = run["frames"][1:]  # first sample has no writes attributed
            if not frames:
                continue
            tw = [f["writes"][0] for f in frames]
            vw = [f["writes"][1] for f in frames]
            sw = [f["writes"][2] for f in frames]
            vis = [sum(1 for rec in f["labels"] if rec is not None) for f in frames]
            q = lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))]
            rows.append({
                "viewport": run["viewport"], "state": run["state"],
                "frames": len(frames),
                "visible": {"p50": q(vis, .5), "p95": q(vis, .95), "max": max(vis)},
                "transformWrites": {"p50": q(tw, .5), "p95": q(tw, .95), "max": max(tw)},
                "visibilityWrites": {"p50": q(vw, .5), "p95": q(vw, .95), "max": max(vw)},
                "sizeWrites": {"p50": q(sw, .5), "p95": q(sw, .95), "max": max(sw)},
            })
        return rows

    writes = {
        "what": "DOM style write pressure per frame, the same MutationObserver "
                "on every lane. A write that does not change the property "
                "value does not mutate and is not counted -- what is measured "
                "is style CHANGE pressure on the label pool",
        "target": write_stats(target),
        "before": write_stats(before),
        "candidate": write_stats(cand),
    }

    def agg(rows, key):
        vals = [r[key]["p95"] for r in rows]
        return max(vals) if vals else 0

    writes["summary"] = {
        "beforeTransformWritesP95Worst": agg(writes["before"], "transformWrites"),
        "candidateTransformWritesP95Worst": agg(writes["candidate"], "transformWrites"),
        "targetTransformWritesP95Worst": agg(writes["target"], "transformWrites"),
        "beforeVisibleP95Worst": agg(writes["before"], "visible"),
        "candidateVisibleP95Worst": agg(writes["candidate"], "visible"),
        "targetVisibleP95Worst": agg(writes["target"], "visible"),
    }
    s = writes["summary"]
    writes["pass"] = (s["candidateTransformWritesP95Worst"]
                      < s["beforeTransformWritesP95Worst"]
                      and s["candidateVisibleP95Worst"]
                      <= s["targetVisibleP95Worst"] + 4)
    (outdir / "transform-writes.json").write_text(json.dumps(writes, indent=1) + "\n")

    # -- console --------------------------------------------------------------
    ok = (coverage["targetRuleVerification"]["pass"]
          and coverage["candidateRuleConsistency"]["pass"]
          and coverage["candidateSnapshotBitExactness"]["pass"]
          and coverage["staleRectCheck"]["pass"]
          and coverage["consoleAndPageErrors"]["pass"]
          and slot_verdicts["pass"] and pop["pass"] and writes["pass"])
    print(f"target rule verification: {t_sum['framesChecked']} frames, "
          f"{t_sum['slotMismatches']} slot mismatches "
          f"({t_sum['withinBoundary']} within {BOUNDARY_PX}px boundary, "
          f"{t_sum['wrapSeam']} wrap-seam, "
          f"{t_sum['beyondBoundary']} beyond) -> "
          f"{'PASS' if coverage['targetRuleVerification']['pass'] else 'FAIL'}")
    print(f"candidate rule consistency: {c_sum['framesChecked']} frames, "
          f"{c_sum['slotMismatches']} mismatches "
          f"({c_sum['beyondBoundary']} beyond boundary) -> "
          f"{'PASS' if coverage['candidateRuleConsistency']['pass'] else 'FAIL'}")
    print(f"snapshot bit-exactness: {len(snapshots)} snapshots, worst AABB delta "
          f"{coverage['candidateSnapshotBitExactness']['worstAabbDeltaPx']:.3e} px -> "
          f"{'PASS' if coverage['candidateSnapshotBitExactness']['pass'] else 'FAIL'}")
    sr = coverage["staleRectCheck"]
    print(f"stale rects: {sr['visibleDrawnChecked']} drawn labels over "
          f"{sr['rows']} settled runs, worst delta {sr['worstDeltaPx']} px, "
          f"{sr['staleLabels']} stale, {sr['wrapSeamRelocated']} wrap-seam "
          f"-> {'PASS' if sr['pass'] else 'FAIL'}")
    print(f"slot identity: {identical}/{len(rows)} settled states identical -> "
          f"{'PASS' if slot_verdicts['pass'] else 'FAIL'}")
    print(f"edge pop-in: candidate max strict-overlap at entry "
          f"{pop['candidateMaxStrictOverlapPx']} px vs target "
          f"{pop['targetMaxStrictOverlapPx']} px -> "
          f"{'PASS' if pop['pass'] else 'FAIL'}")
    print(f"writes: before p95 {s['beforeTransformWritesP95Worst']} -> candidate "
          f"p95 {s['candidateTransformWritesP95Worst']} (target "
          f"{s['targetTransformWritesP95Worst']}) -> "
          f"{'PASS' if writes['pass'] else 'FAIL'}")
    ce = coverage["consoleAndPageErrors"]
    print(f"console/page errors: target {ce['target']}, before {ce['before']}, "
          f"candidate {ce['candidate']} -> {'PASS' if ce['pass'] else 'FAIL'}")
    print(f"depth: {coverage['depthCarryForward']['status']}")
    print("COVERAGE GATE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
