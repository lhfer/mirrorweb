#!/usr/bin/env python3
"""Score the V1 A/B perf traces: coverage culling ON vs OFF, same build.

What the brief asks, measured not asserted: WebGL objects visible, draw
calls and triangles per pass, CPU frame percentiles, labels.sync, renderer
memory, video decode state, adaptive quality changes, and heap over
repeated 5-minute cycles. GPU frame time is reported as not instrumentable
(the renderer is created without timestamp tracking) rather than faked.

Usage: v1-performance.py --on=<json> --off=<json> [--cycles=<json>]
                         --out=<json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def q(xs, p):
    if not xs:
        return None
    return sorted(xs)[min(len(xs) - 1, int(p * (len(xs) - 1)))]


def scenario_stats(sc):
    frames = sc["frames"][1:]
    dts = [f[0] for f in frames if f[0] > 0]
    final_calls = [f[1] for f in frames if f[1] >= 0]
    final_tris = [f[2] for f in frames if f[2] >= 0]
    scene_calls = [f[3] for f in frames if f[3] >= 0]
    glass = [f[4] for f in frames]
    sync = sc.get("labelSync", {}).get("samples", [])
    heap = sc.get("heap", [])
    media = sc.get("media", [])
    media_before = sc.get("mediaBefore", [])
    # The clips LOOP (~4.5 s), so currentTime can wrap below its start value
    # during a 10-20 s scenario: "playing" means the clock MOVED and the
    # element is not paused, not that it moved forward.
    advanced = None
    if media and media_before:
        advanced = sum(1 for a, b in zip(media_before, media)
                       if not b["paused"]
                       and abs(b["currentTime"] - a["currentTime"]) > 0.05)
    return {
        "frames": len(frames),
        "frameTimeMs": {"p50": q(dts, .5), "p95": q(dts, .95), "p99": q(dts, .99)},
        "glassVisible": {"p50": q(glass, .5), "p95": q(glass, .95), "max": max(glass, default=0)},
        "finalDrawCalls": {"p50": q(final_calls, .5), "p95": q(final_calls, .95),
                           "max": max(final_calls, default=0)},
        "finalTriangles": {"p50": q(final_tris, .5), "p95": q(final_tris, .95),
                           "max": max(final_tris, default=0)},
        "sceneColorDrawCalls": {"p50": q(scene_calls, .5), "p95": q(scene_calls, .95)},
        "labelSyncCpuMs": ({"p50": q(sync, .5), "p95": q(sync, .95), "p99": q(sync, .99)}
                           if sync else None),
        "longTasks": sc.get("longTasks", 0),
        "domNodes": sc.get("domNodes"),
        "heapStartMB": heap[0] if heap else None,
        "heapEndMB": heap[-1] if heap else None,
        "heapDeltaMB": (round(heap[-1] - heap[0], 2) if len(heap) > 1 else None),
        "videosAdvancing": advanced,
        "videoCount": len(media),
        "adaptiveQuality": {
            "level": sc.get("adaptive", {}).get("level"),
            "appliedLevel": sc.get("adaptive", {}).get("appliedLevel"),
            "changeCount": sc.get("adaptive", {}).get("changeCount"),
        },
        "errors": len(sc.get("errors", [])),
    }


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    on = json.loads(Path(args["on"]).read_text())
    off = json.loads(Path(args["off"]).read_text())
    cycles = json.loads(Path(args["cycles"]).read_text()) if args.get("cycles") else None

    on_by = {s["name"]: scenario_stats(s) for s in on["scenarios"]}
    off_by = {s["name"]: scenario_stats(s) for s in off["scenarios"]}

    checks = []
    for name in on_by:
        a, b = off_by.get(name), on_by[name]
        if not a:
            continue
        calls_off = a["finalDrawCalls"]["p95"] or 0
        calls_on = b["finalDrawCalls"]["p95"] or 0
        tris_off = a["finalTriangles"]["p95"] or 0
        tris_on = b["finalTriangles"]["p95"] or 0
        checks.append({
            "scenario": name,
            "finalDrawCallsP95": {"off": calls_off, "on": calls_on,
                                  "reduced": calls_on < calls_off},
            "finalTrianglesP95": {"off": tris_off, "on": tris_on,
                                  "reducedPct": (round(100 * (1 - tris_on / tris_off), 1)
                                                 if tris_off else None)},
            # The scene pass is not coverage-culled; its per-frame media
            # draw count follows the overscan frustum, which follows the
            # scroll trajectory -- and the two lanes are two INDEPENDENT
            # input runs, so the tail of that distribution wanders by a call
            # (the M3 dolly-cell pattern). p50 must be EXACT; the p95 is
            # allowed +-1 call of cross-run input variation. The exact
            # invariant -- culling does not alter the scene pass -- is
            # proven per frame by the render gate (0 media leaks) and by the
            # byte-identical pixel A/B.
            "sceneColorUnchanged": (
                a["sceneColorDrawCalls"]["p50"] == b["sceneColorDrawCalls"]["p50"]
                and abs((a["sceneColorDrawCalls"]["p95"] or 0)
                        - (b["sceneColorDrawCalls"]["p95"] or 0)) <= 1),
            "glassVisibleP95": {"off": a["glassVisible"]["p95"],
                                "on": b["glassVisible"]["p95"]},
            "videosPlayingBothLanes": (a["videosAdvancing"], b["videosAdvancing"]),
            "videosPlayingOk": (a["videosAdvancing"] == a["videoCount"]
                                and b["videosAdvancing"] == b["videoCount"]
                                and a["videoCount"] > 0),
            "adaptiveUnchanged": (a["adaptiveQuality"]["appliedLevel"]
                                  == b["adaptiveQuality"]["appliedLevel"]
                                  and (a["adaptiveQuality"]["changeCount"] or 0) == 0
                                  and (b["adaptiveQuality"]["changeCount"] or 0) == 0),
            "heapBounded": (b["heapDeltaMB"] is None or b["heapDeltaMB"] < 30),
            "errorsZero": a["errors"] == 0 and b["errors"] == 0,
        })

    cycle_rows = []
    if cycles:
        for c in cycles.get("heapCycles", []):
            cycle_rows.append({"cycle": c["cycle"],
                               "heapStartMB": c["heapStartMB"],
                               "heapEndMB": c["heapEndMB"],
                               "deltaMB": (round(c["heapEndMB"] - c["heapStartMB"], 2)
                                           if c["heapStartMB"] is not None else None)})

    ok = (len(checks) > 0
          and all(c["finalDrawCallsP95"]["reduced"] for c in checks)
          and all(c["sceneColorUnchanged"] for c in checks)
          and all(c["adaptiveUnchanged"] for c in checks)
          and all(c["heapBounded"] for c in checks)
          and all(c["errorsZero"] for c in checks)
          and all(c["videosPlayingOk"] for c in checks)
          and (not cycle_rows or all((r["deltaMB"] or 0) < 40 for r in cycle_rows)))
    doc = {
        "what": "V1 A/B on one build: coverage culling ON vs OFF. OFF is the "
                "accepted pre-V1 behaviour (proven byte-identical by the "
                "pixel gate); ON is the candidate.",
        "gpuFrameTime": on.get("gpuFrameTime"),
        "scenarios": {n: {"off": off_by.get(n), "on": on_by[n]} for n in on_by},
        "checks": checks,
        "heapCycles": cycle_rows or None,
        "pass": ok,
    }
    Path(args["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["out"]).write_text(json.dumps(doc, indent=1) + "\n")
    for c in checks:
        print(f"{c['scenario']}: final calls p95 {c['finalDrawCallsP95']['off']} -> "
              f"{c['finalDrawCallsP95']['on']}, tris p95 -{c['finalTrianglesP95']['reducedPct']}%, "
              f"scene unchanged {c['sceneColorUnchanged']}, adaptive ok {c['adaptiveUnchanged']}")
    for r in cycle_rows:
        print(f"heap cycle {r['cycle']}: {r['heapStartMB']} -> {r['heapEndMB']} MB")
    print("V1 PERFORMANCE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
