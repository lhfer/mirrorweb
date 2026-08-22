#!/usr/bin/env python3
"""O5F §七 -- the sealed stress-gate definitions.

Every constant and formula the Phase A memory gate binds to lives HERE, and
the contract generator and the scorer both import it -- so a threshold cannot
be one thing in the contract and another in the verdict. Committed with the
material-cache code, before any cached-candidate capture exists.

The two heap thresholds are TARGET-RELATIVE in the O5R sense: the sealed part
is the FORMULA and the floor; the control-derived term is filled in by the
three control sessions captured in the same run. That is the same pattern the
O5R gate used for Target windows -- what is fixed in advance is how the number
will be computed, so nothing can be tuned after seeing the candidate.
"""
from __future__ import annotations

import statistics

# ---------------------------------------------------------------- sampling
SAMPLE_INTERVAL_MS = 10000
SESSION_MINUTES = 15
CANDIDATE_SESSIONS = 3
CONTROL_SESSIONS = 3
QUALITY_CYCLES = 300              # x4 steps = 1,200 quality changes (§七.1)
QUALITY_CYCLE_ORDER = ["high", "medium", "low", "high"]

# ---------------------------------------------------------------- floors
# §七.5: final-third heap slope <= max(control repeatability window, floor).
HEAP_SLOPE_FLOOR_MB_PER_MIN = 0.35
# §七.6: ten-minute GC-trough rise <= max(2 x control spread, floor).
TROUGH_RISE_FLOOR_MB = 4.0

# ---------------------------------------------------------------- cache facts
# What the §五 truth surface must hold after warm-up, given three clips and
# the two product sets (5-sample for high+medium, 3-sample for low) built at
# initialisation. V5_BODY_SAMPLES in src/materials/TargetOpticalBodyV5.ts is
# the source of the 5/5/3 mapping.
PRODUCT_CLIPS = 3
PRODUCT_CACHE_SIZE = 2
PRODUCT_CREATION_COUNT = PRODUCT_CACHE_SIZE * PRODUCT_CLIPS
EXPECTED_SAMPLES = {"high": 5, "medium": 5, "low": 3}

# Pool-state keys scored for growth (the LIVE counts a leak would move), and
# the monotonic-by-design counters reported but never scored. Identical to the
# O5R §十二 partition.
RESOURCE_KEYS = ("materials", "geometries", "textures", "videos", "slots")
MONOTONIC_KEYS = ("created", "destroyed", "remaps")
VIEWPORT_KEYS = ("activeSlots", "cols", "rows", "quality")


def slope_mb_per_min(points):
    """Least squares on (minutes, MB). None with fewer than 3 points."""
    xs = [p[0] / 60000.0 for p in points]
    ys = [p[1] for p in points]
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return None if den == 0 else round(num / den, 4)


def trough_mb(values):
    """Mean of the lowest tenth (at least one sample). O5R's definition.

    The heap sawtooths under GC and a least-squares line through a sawtooth
    mostly reports where the endpoints landed; a leak raises the FLOOR the
    collector can return to, and this reads that floor.
    """
    if len(values) < 3:
        return None
    lo = sorted(values)[: max(1, len(values) // 10)]
    return round(statistics.mean(lo), 2)


def trough_rise_mb(heap_series):
    """finalThirdTrough - firstThirdTrough over one session's heap samples.

    On a 15-minute session the third midpoints sit ~10 minutes apart, which is
    what makes this the §七.6 "ten-minute GC-trough rise" -- the same
    measurand O5R §十二 reported.
    """
    hs = [h for h in heap_series if h is not None]
    if len(hs) < 9:
        return None
    third = len(hs) // 3
    a = trough_mb(hs[:third])
    b = trough_mb(hs[-third:])
    if a is None or b is None:
        return None
    return {"firstThirdTroughMB": a, "finalThirdTroughMB": b,
            "riseMB": round(b - a, 2)}


def heap_slope_threshold(control_final_third_slopes):
    """§七.5. max(control repeatability window, 0.35 MB/min floor).

    The control repeatability window is the largest |final-third slope| any of
    the three control sessions produced: a slope the shipped lane itself
    reaches under the identical workload cannot be evidence against the
    candidate.
    """
    window = max((abs(s) for s in control_final_third_slopes
                  if s is not None), default=0.0)
    return round(max(window, HEAP_SLOPE_FLOOR_MB_PER_MIN), 4)


def trough_rise_threshold(control_rises_mb):
    """§七.6. max(2 x control-session spread, 4 MB floor).

    The spread is max - min of the three control sessions' trough rises --
    how much the measurand moves between runs when nothing is wrong.
    """
    rises = [r for r in control_rises_mb if r is not None]
    spread = (max(rises) - min(rises)) if len(rises) >= 2 else 0.0
    return round(max(2 * spread, TROUGH_RISE_FLOOR_MB), 2)
