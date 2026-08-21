#!/usr/bin/env python3
"""Write the Target-only scheduler-invariant baseline. Reads no candidate.

ORDER MATTERS AND IS AUDITABLE
------------------------------
Every threshold in this file is `max(2 * the Target's own repeatability,
a floor declared here)`. Both halves are computed from the Target alone. This
script cannot read a candidate trace -- it takes no argument that would let it
-- and the file it writes is committed BEFORE the candidate is captured, so
"the floors were not adjusted after seeing the candidate" is a claim git can
settle rather than a promise in a commit message.

The repeatability is the spread of the Target against ITSELF: the same
sequence, same viewport, run three times, landmark computed three times, spread
taken as the full range. A landmark the Target cannot reproduce to better than
X is not a landmark a candidate can be held to better than X.

Usage:
  m2-baseline.py --target=<trace.json> [--extra=<trace.json> ...] --out=<dir>
"""
from __future__ import annotations

import hashlib
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


MT = _load("motion_trace", "motion_trace.py")
LM = _load("m2_landmarks", "m2_landmarks.py")

# ---------------------------------------------------------------------------
# FLOORS. Declared here, before any candidate exists, and hashed into the file.
#
# A repeatability of zero -- which a sequence that moves nothing legitimately
# has -- must not produce a threshold of zero. Each floor is the smallest
# difference in that unit a reviewer would call a difference.
# ---------------------------------------------------------------------------
FLOORS = {
    # World units. The sphere radius is ~1000 units and a card is ~200 wide,
    # so 12 units is about a twentieth of a card: below what anyone can see,
    # above what the recovery's own 0.03-unit noise can manufacture.
    "travelWorldUnits": 12.0,
    # Dimensionless scroll-per-pixel. 0.05 is a twentieth of the gesture.
    "followRatio": 0.05,
    # World units per second, from a 75 ms line fit rather than one frame.
    # Kept at the M1 number: the ruler changed, the size of a real difference
    # did not.
    "releaseVelocity": 60.0,
    # Milliseconds. Two frames at the ~120 Hz both pages run at is 16.6 ms;
    # a decay landmark is a time constant, not a frame, and 60 ms is the
    # smallest difference in a settling time a viewer would notice.
    "decayMs": 60.0,
    # Radians of camera orbit. The whole orbit is +-0.05 rad, so 0.002 is 4%
    # of the full sweep.
    "orbitRad": 0.002,
    # Milliseconds, for a step response. Two frames at 120 Hz.
    "settleMs": 16.6,
    # The camera's distance off its orbit sphere, as a fraction of the radius.
    # The Target's dolly reaches ~0.22, so 0.01 is a fiftieth of it -- a page
    # that dropped the dolly misses by twenty-two floors.
    "dollyRatio": 0.01,
    # Integral of the dolly envelope over the run, in fraction-seconds.
    "dollyIntegral": 0.02,
    # Whole reversals. One is one.
    "reversalCount": 1.0,
}

# Landmarks whose absence on a sequence is expected rather than a fault.
OPTIONAL = {"followRatioX", "followRatioY", "pointerSettle63Ms",
            "robustReleaseVelocity50Ms", "robustReleaseVelocity75Ms",
            "robustReleaseVelocity100Ms", "timeTo50PctMs", "timeTo10PctMs",
            "timeToVisualStopMs", "travelAfterReleaseX", "travelAfterReleaseY",
            "dollyPeakTimeMs", "touchMouseFollowParity"}

MOUSE_DRAGS = ("slow-horizontal-drag", "slow-vertical-drag", "diagonal-drag",
               "medium-drag")


def spread(values: list[float]) -> float:
    """Full range across the repeats. Not a standard deviation: with three
    samples an s.d. underestimates the spread it is trying to describe, and the
    thing being asked is "how far apart can two runs of the same thing be"."""
    vals = [v for v in values if v is not None]
    return 0.0 if len(vals) < 2 else max(vals) - min(vals)


def load_runs(paths: list[Path]) -> list[dict]:
    runs = []
    for p in paths:
        d = json.loads(p.read_text())
        for r in d["runs"]:
            r["_source"] = p.name
            runs.append(r)
    return runs


def main() -> int:
    args = {}
    extras = []
    for a in sys.argv[1:]:
        if a.startswith("--extra="):
            extras.append(Path(a.split("=", 1)[1]))
        elif a.startswith("--"):
            k, v = a[2:].split("=", 1)
            args[k] = v
    paths = [Path(args["target"])] + extras
    out_dir = Path(args["out"])
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = load_runs(paths)
    if not runs:
        print("no target runs", file=sys.stderr)
        return 1
    if not all(r["frames"] and r["frames"][0].get("ord") is not None for r in runs):
        print("target trace carries no callback order -- this is an M1 trace", file=sys.stderr)
        return 1

    # ---- landmarks, per grid, per run ------------------------------------
    per_grid: dict = {}
    unreadable = []
    parity_inputs: dict = {}
    for hz in LM.GRIDS:
        cells: dict = {}
        for run in runs:
            key = (run["id"], run["sequence"])
            obs = MT.trajectory(run)
            marks = LM.scheduler_invariant(run, obs, hz)
            if not marks:
                live = [n for n in obs.get("liveCards", []) if n is not None]
                unreadable.append({"viewport": run["id"], "sequence": run["sequence"],
                                   "repeat": run["repeat"], "hz": hz,
                                   "liveCardsMin": min(live) if live else None,
                                   "status": "INSTRUMENT_UNREADABLE",
                                   "why": "the scroll recovery fell below "
                                          f"{LM.MIN_LIVE_CARDS} live cards"})
                continue
            cells.setdefault(key, []).append(marks)
            if run["sequence"] in MOUSE_DRAGS or run["sequence"] == "touch-drag-release":
                parity_inputs.setdefault((hz, run["id"], run["sequence"]), []).append(
                    marks.get("followRatioX"))
        per_grid[hz] = cells

    # ---- touch / mouse parity, one number per viewport --------------------
    for hz in LM.GRIDS:
        for vp in sorted({r["id"] for r in runs}):
            mouse = [v for s in MOUSE_DRAGS
                     for v in parity_inputs.get((hz, vp, s), []) if v is not None]
            touch = [v for v in parity_inputs.get((hz, vp, "touch-drag-release"), [])
                     if v is not None]
            if not mouse or not touch:
                continue
            m = statistics.median(mouse)
            if abs(m) < 1e-6:
                continue
            # One value per repeat, so the parity has a repeatability of its own.
            per_grid[hz].setdefault((vp, "PARITY"), [])
            for t in touch:
                per_grid[hz][(vp, "PARITY")].append(
                    {"touchMouseFollowParity": round(t / m, 5)})

    # ---- thresholds -------------------------------------------------------
    baseline = {}
    for hz, cells in per_grid.items():
        rows = {}
        for (vp, seq), marks_list in sorted(cells.items()):
            names = sorted({k for m in marks_list for k in m})
            entry = {}
            for name in names:
                vals = [m.get(name) for m in marks_list]
                present = [v for v in vals if v is not None]
                if not present:
                    continue
                sp = spread(present)
                unit = LM.UNIT.get(name)
                if unit is None:
                    continue
                floor = FLOORS[unit]
                entry[name] = {
                    "targetMean": round(statistics.mean(present), 5),
                    "targetValues": [round(v, 5) for v in present],
                    "repeats": len(present),
                    "repeatabilitySpread": round(sp, 5),
                    "unit": unit,
                    "floor": floor,
                    "threshold": round(max(2.0 * sp, floor), 5),
                    "thresholdRule": "max(2 * target repeatability spread, declared floor)",
                    "gateType": LM.gate_type(name),
                    "productGated": name not in LM.EXCEPTION_RAW,
                }
            if entry:
                rows[f"{vp}|{seq}"] = entry
        baseline[f"{int(hz)}Hz"] = rows

    # ---- raw metrics, recorded for the exception, never thresholded -------
    raw = {}
    for run in runs:
        obs = MT.trajectory(run)
        rm = LM.raw_metrics(run, obs)
        if rm:
            raw.setdefault(f"{run['id']}|{run['sequence']}", []).append(rm)
    raw_summary = {}
    for key, lst in sorted(raw.items()):
        names = sorted({k for m in lst for k in m})
        raw_summary[key] = {n: round(statistics.mean([m[n] for m in lst if n in m]), 5)
                            for n in names if any(n in m for m in lst)}

    doc = {
        "what": "The Target's own scheduler-invariant landmarks and the thresholds "
                "derived from its own repeatability. Written before any candidate "
                "trace was captured.",
        "capturedFrom": [str(p) for p in paths],
        "targetUrl": "https://infinite-liquid-glass.shader.se/?v=2",
        "runs": len(runs),
        "repeatsPerCell": 3,
        "grids": [f"{int(h)}Hz" for h in LM.GRIDS],
        "gridNote": "Landmarks are read off a UNIFORM timeline -- position "
                    "interpolated onto a fixed grid, derivatives over a short "
                    "window, peaks as running medians or windowed RMS. Endpoints "
                    "are never interpolated, so the final rest position is what "
                    "the page actually finished at.",
        "floors": FLOORS,
        "floorsNote": "Declared in m2-baseline.py before any candidate existed and "
                      "hashed into this file. The compare script recomputes this "
                      "file's SHA-256 and refuses to run against a modified copy.",
        "visualStopUnitsPerSecond": LM.VISUAL_STOP_UNITS_PER_S,
        "reversalFloorUnitsPerSecond": LM.REVERSAL_FLOOR_UNITS_PER_S,
        "minLiveCards": LM.MIN_LIVE_CARDS,
        "gateTypes": {
            "two-sided": "a difference in either direction is a difference",
            "one-sided-upper": "only an EXCESS over the Target is a defect; a "
                               "candidate that is smoother is recorded as "
                               "SMOOTHER_THAN_TARGET and does not fail",
            "one-sided-lower": "only a SHORTFALL is a defect; no landmark uses "
                               "this today, and the mechanism exists so that one "
                               "added later needs no rewrite",
        },
        "exceptionRawMetrics": sorted(LM.EXCEPTION_RAW),
        "exceptionRawNote": "Computed with a single-frame ruler, which is exactly "
                            "the ruler the Target's two-rAF architecture moves. "
                            "Written out, never a product FAIL. See MOTION-EXC-01.",
        "instrumentUnreadable": unreadable,
        "landmarks": baseline,
        "rawMetricsTargetMeans": raw_summary,
    }
    path = out_dir / "target-scheduler-invariant-baseline.json"
    body = json.dumps(doc, indent=1, sort_keys=False)
    path.write_text(body)
    sha = hashlib.sha256(body.encode()).hexdigest()
    (out_dir / "target-scheduler-invariant-baseline.sha256").write_text(
        f"{sha}  target-scheduler-invariant-baseline.json\n")
    cells = sum(len(v) for v in baseline.values())
    marks = sum(len(e) for v in baseline.values() for e in v.values())
    print(f"baseline -> {path}")
    print(f"  {len(runs)} target runs, {cells} cells, {marks} landmark thresholds")
    print(f"  unreadable runs: {len(unreadable)}")
    print(f"  sha256 {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
