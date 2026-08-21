#!/usr/bin/env python3
"""The V1 absolute gate: effective WebGL visibility vs the byte-anchored rule.

Verdicts, each written as data:

1. CANDIDATE EFFECTIVE VISIBILITY vs TARGET RULE REPLAY -- per frame, the
   set of slots whose glass mesh was ACTUALLY visible must equal the set the
   byte-anchored coverage rule draws for that frame's engine truth, slot for
   slot. (The Target's mesh state is not externally readable; its side of
   the gate is the rule itself, byte-anchored in
   target-render-culling-source.json.)
2. LABEL / MESH AGREEMENT -- the label DOM the same verdict drove must show
   exactly the same slots, every frame: the Target wires both in one loop
   iteration, so any disagreement is a candidate bug. This is also the
   "no card missing under a shown label / no label missing over a shown
   card" gate, margin band included.
3. STRICT-VIEWPORT COMPLETENESS -- no frame may hide a card whose replayed
   quad overlaps the strict viewport.
4. SHELL / MEDIA COMPOSITION -- the shell count equals the glass count
   (shell rides the glass under beauty), and the media count equals the
   ACTIVE count whenever the frame was captured outside the scene-colour
   flip (media is deliberately not coverage-culled; the recorder samples on
   rAF, after the pipeline restored the final-pass state media=off), so the
   recorded media count must be 0 -- a nonzero value would mean a system
   overwrote the pipeline's pass state.
5. WRAP / RESIZE FRESHNESS -- per-frame equality (1) across
   long-drag-multi-wrap, resize-settle and orientation-flip runs proves no
   stale visibility survives a wrap or a re-grid; the settled snapshots are
   additionally checked against a fresh replay of their own truth.

Usage: v1-render-gate.py --trace=<render-trace.json> --outdir=<dir>
"""
from __future__ import annotations

import importlib.util
import json
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

SETTLED_STATES = ["rest", "pointer-corner-tl", "pointer-corner-tr",
                  "pointer-corner-br", "pointer-corner-bl", "resize-settle",
                  "orientation-flip"]


def stable_frames(frames):
    """Exclude +-3 samples around any viewport change: a resize applies
    mid-frame relative to the page's own writes. Our page re-layouts
    immediately (no debounce), so the V0 candidate discipline applies."""
    n = len(frames)
    hot = [False] * n
    for i, f in enumerate(frames):
        if i > 0 and (f["w"] != frames[i - 1]["w"] or f["h"] != frames[i - 1]["h"]):
            for k in range(max(0, i - 3), min(n, i + 4)):
                hot[k] = True
    return [f for i, f in enumerate(frames) if not hot[i]]


def check_run(run):
    frames = stable_frames(run["frames"])
    checked = 0
    mism_frames = 0
    mism_slots = []
    label_mism = 0
    strict_missing = 0
    media_leaks = 0
    shell_mism = 0
    layouts = {}
    for f in frames:
        if not f.get("truth") or not f.get("renderCulling"):
            continue
        w, h = f["w"], f["h"]
        frame = layouts.get((w, h))
        if frame is None:
            frame = layouts[(w, h)] = SL.layout(w, h)
        cam = VC.coverage_camera(f["truth"][2], f["truth"][3], frame)
        pred = VC.frame_verdicts(f["truth"][0], f["truth"][1], cam, frame)
        pred_glass = {c - 1 for c, v in pred.items() if v["draw"]}
        glass = set(f["glassIdx"])
        labels = set(f["labelIdx"])
        checked += 1
        if glass != pred_glass:
            mism_frames += 1
            for s in glass ^ pred_glass:
                v = pred.get(s + 1)
                mism_slots.append({
                    "t": f["t"], "slot": s,
                    "meshVisible": s in glass, "predictedDraw": s in pred_glass,
                    "boundaryMarginPx": round(v["boundaryMarginPx"], 6) if v else None,
                })
        if labels != glass:
            label_mism += 1
        for c, v in pred.items():
            if v["overlap"] > 0 and (c - 1) not in glass:
                strict_missing += 1
        if f["mediaCount"] != 0:
            media_leaks += 1
        if f["shellCount"] != len(glass):
            shell_mism += 1
    return {
        "viewport": run["viewport"], "state": run["state"],
        "framesChecked": checked,
        "framesExcludedAsTransition": len(run["frames"]) - len(frames),
        "framesWithMismatch": mism_frames,
        "slotMismatches": len(mism_slots),
        "labelMeshDisagreements": label_mism,
        "strictViewportMissing": strict_missing,
        "mediaPassLeaks": media_leaks,
        "shellGlassMismatches": shell_mism,
        "worstMismatches": sorted(mism_slots,
                                  key=lambda r: -(r["boundaryMarginPx"] or 0))[:5],
    }


def check_snapshot(run):
    snap = run.get("snapshot")
    frames = [f for f in run["frames"] if f.get("truth")]
    if not snap or not frames:
        return None
    f = frames[-1]
    frame = SL.layout(f["w"], f["h"])
    cam = VC.coverage_camera(f["truth"][2], f["truth"][3], frame)
    pred = VC.frame_verdicts(f["truth"][0], f["truth"][1], cam, frame)
    slots = snap["renderCullingTruth"]["slots"]
    mism = 0
    checked = 0
    for s in slots:
        if not s["active"]:
            continue
        p = pred.get(s["slotIndex"] + 1)
        if p is None:
            continue
        checked += 1
        if bool(s["effectiveGlassVisible"]) != bool(p["draw"]):
            mism += 1
    return {"viewport": run["viewport"], "state": run["state"],
            "activeChecked": checked, "effectiveVsReplayMismatches": mism,
            "pass": mism == 0}


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    trace = json.loads(Path(args["trace"]).read_text())
    outdir = Path(args["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)

    rows = [check_run(r) for r in trace["runs"]]
    snapshots = [s for s in (check_snapshot(r) for r in trace["runs"]
                             if r["state"] in SETTLED_STATES) if s]

    total = {k: sum(r[k] for r in rows) for k in
             ("framesChecked", "framesWithMismatch", "slotMismatches",
              "labelMeshDisagreements", "strictViewportMissing",
              "mediaPassLeaks", "shellGlassMismatches")}
    lane_errors = (sum(len(r.get("errors", [])) for r in trace["runs"])
                   + len(trace.get("errors", [])))
    doc = {
        "what": "V1 absolute gate: the effective WebGL visibility the one "
                "applier composed, replayed frame-for-frame against the "
                "byte-anchored coverage rule, plus label/mesh agreement, "
                "strict-viewport completeness, and pass-state integrity",
        "sourceMapping": "qa-v5/render-culling/target-render-culling-source.json",
        **total,
        "consoleAndPageErrors": lane_errors,
        "perRun": rows,
        "settledSnapshots": {
            "snapshots": len(snapshots),
            "pass": all(s["pass"] for s in snapshots),
            "perSnapshot": snapshots,
        },
        "pass": (total["slotMismatches"] == 0
                 and total["labelMeshDisagreements"] == 0
                 and total["strictViewportMissing"] == 0
                 and total["mediaPassLeaks"] == 0
                 and total["shellGlassMismatches"] == 0
                 and lane_errors == 0
                 and all(s["pass"] for s in snapshots)
                 and total["framesChecked"] > 0),
    }
    (outdir / "render-culling-truth.json").write_text(json.dumps(doc, indent=1) + "\n")
    print(f"effective visibility vs rule replay: {total['framesChecked']} frames, "
          f"{total['slotMismatches']} slot mismatches")
    print(f"label/mesh agreement: {total['labelMeshDisagreements']} disagreeing frames")
    print(f"strict viewport: {total['strictViewportMissing']} missing-card frames")
    print(f"pass-state integrity: {total['mediaPassLeaks']} media leaks, "
          f"{total['shellGlassMismatches']} shell mismatches")
    print(f"settled snapshots: {len(snapshots)}, "
          f"{'all PASS' if doc['settledSnapshots']['pass'] else 'FAIL'}")
    print(f"console/page errors: {lane_errors}")
    print("V1 RENDER GATE:", "PASS" if doc["pass"] else "FAIL")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
