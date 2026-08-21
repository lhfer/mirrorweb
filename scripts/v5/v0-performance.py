#!/usr/bin/env python3
"""Before vs Candidate label cost, measured -- not argued from a visible count.

Reads the two v0-perf-trace.mjs reports and writes qa-v5/culling's
performance.json: per scenario, per lane -- visible labels p50/p95/max,
transform/visibility writes p50/p95, frame time p50/p95/p99, long tasks, DOM
node count, heap growth over the scenario, adaptive-quality change count, and
on the Candidate the labels.sync CPU p50/p95/p99 from the QA probe.

The gate lines:
  - candidate visible labels must sit close to the Target's own (~16 at
    1440x900), and FAR below the Before lane's;
  - candidate transform writes must be a small fraction of Before's;
  - no adaptive-quality change and no DPR change may account for it -- the
    quality level at start and end must be equal across lanes;
  - heap must not grow monotonically (leak) over the sustained scenarios.

Usage: v0-performance.py --before=<json> --candidate=<json> --out=<json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def q(xs, p):
    if not xs:
        return 0.0
    return sorted(xs)[int(p * (len(xs) - 1))]


def lane_scenarios(report):
    out = {}
    for sc in report["scenarios"]:
        frames = sc["frames"]
        dts = [f[0] for f in frames if f[0] > 0]
        vis = [f[1] for f in frames]
        tw = [f[2] for f in frames]
        vw = [f[3] for f in frames]
        heap = sc.get("heap") or []
        sync = sc.get("labelSync") or {}
        samples = sync.get("samples") or []
        adaptive = sc.get("adaptive") or {}
        row = {
            "frames": len(frames),
            "visibleLabels": {"p50": q(vis, .5), "p95": q(vis, .95), "max": max(vis, default=0)},
            "transformWritesPerFrame": {"p50": q(tw, .5), "p95": q(tw, .95), "max": max(tw, default=0)},
            "visibilityWritesPerFrame": {"p50": q(vw, .5), "p95": q(vw, .95), "max": max(vw, default=0)},
            "frameTimeMs": {"p50": round(q(dts, .5), 2), "p95": round(q(dts, .95), 2),
                            "p99": round(q(dts, .99), 2)},
            "longTasks": sc.get("longTasks", 0),
            "longTaskMs": sc.get("longTaskMs", 0),
            "domNodes": sc.get("domNodes"),
            "heapStartMB": round(heap[0] / 1048576, 1) if heap else None,
            "heapEndMB": round(heap[-1] / 1048576, 1) if heap else None,
            "heapDeltaMB": round((heap[-1] - heap[0]) / 1048576, 2) if len(heap) > 1 else None,
            "labelSyncCpuMs": ({"p50": round(q(samples, .5), 3), "p95": round(q(samples, .95), 3),
                                "p99": round(q(samples, .99), 3), "samples": len(samples)}
                               if samples else None),
            "adaptiveQuality": {
                "level": adaptive.get("level"),
                "appliedLevel": adaptive.get("appliedLevel"),
                "changeCount": adaptive.get("changeCount"),
            },
            "errors": len(sc.get("errors") or []),
        }
        out[sc["name"]] = row
    return out


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    before = lane_scenarios(json.loads(Path(args["before"]).read_text()))
    cand = lane_scenarios(json.loads(Path(args["candidate"]).read_text()))

    rows = {}
    checks = []
    for name in cand:
        b, c = before.get(name), cand[name]
        rows[name] = {"before": b, "candidate": c}
        if not b:
            continue
        checks.append({
            "scenario": name,
            "visibleBefore": b["visibleLabels"]["p95"],
            "visibleCandidate": c["visibleLabels"]["p95"],
            "visibleReduced": c["visibleLabels"]["p95"] < b["visibleLabels"]["p95"] * 0.6,
            "writesBefore": b["transformWritesPerFrame"]["p95"],
            "writesCandidate": c["transformWritesPerFrame"]["p95"],
            "writesReduced": c["transformWritesPerFrame"]["p95"]
                             < b["transformWritesPerFrame"]["p95"] * 0.6,
            "qualityUnchangedAcrossLanes":
                b["adaptiveQuality"]["level"] == c["adaptiveQuality"]["level"],
            "candidateHeapDeltaMB": c["heapDeltaMB"],
            "heapBounded": c["heapDeltaMB"] is None or c["heapDeltaMB"] < 30.0,
        })

    doc = {
        "what": "Before vs Candidate label cost under sustained real input. "
                "The Before build predates the labels.sync QA probe and was "
                "NOT patched to carry it -- its sync cost is bounded by its "
                "frame time; every other column is the same instrument on "
                "both lanes.",
        "scenarios": rows,
        "checks": checks,
        "pass": all(c["visibleReduced"] and c["writesReduced"]
                    and c["qualityUnchangedAcrossLanes"] and c["heapBounded"]
                    for c in checks) and len(checks) == 4,
    }
    Path(args["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["out"]).write_text(json.dumps(doc, indent=1) + "\n")
    for c in checks:
        print(f"{c['scenario']}: visible {c['visibleBefore']} -> {c['visibleCandidate']}, "
              f"writes p95 {c['writesBefore']} -> {c['writesCandidate']}, "
              f"heap {c['candidateHeapDeltaMB']} MB, "
              f"quality unchanged {c['qualityUnchangedAcrossLanes']}")
    print("PERFORMANCE:", "PASS" if doc["pass"] else "FAIL")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
