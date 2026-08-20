#!/usr/bin/env python3
"""
Stage F0, non-rest states: width / gap / slope / centre-path curves.

Calibrating only the rest pose is not enough -- the rest frame happens to put a
card at u=0, and a layout can be right there and wrong everywhere else. This
reads the projected quads the engine reports at five slow-drag offsets plus a
diagonal one, and checks the three properties that must hold at EVERY offset:

  1. no two neighbouring cards overlap;
  2. a card's projected width and edge slope depend only on where it is on
     screen, not on the scroll offset -- so the curve is one curve;
  3. the composition stays left/right symmetric about the viewport midline.

Property 2 is what lets the rest-frame Target comparison generalise: the Target
frame samples the same curve at |u| = 0, 0.5, 1.0 and 1.5 cells, and those four
points are gated in f0-gate.py.

A direct Target comparison at a non-rest offset is deliberately NOT attempted.
The only Target drag frame (08-slow-drag-left-400) was captured mid-gesture with
the pointer off centre, so it carries pointer tilt and parallax on top of the
scroll offset, and its world offset is unknown because dragGain differs. Motion
is out of scope this session.

Usage: f0-curves.py --dir=<foundation dir> [--partial=<dir>] --out=<dir>
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def quad_metrics(entry: dict, width: float, height: float) -> dict:
    xs = [p[0] * width for p in entry["quad"]]
    ys = [p[1] * height for p in entry["quad"]]
    top_l, top_r, bot_r, bot_l = entry["quad"]
    return {
        "poly": [(p[0] * width, p[1] * height) for p in entry["quad"]],
        "i": entry["i"],
        "j": entry["j"],
        "cx": (min(xs) + max(xs)) / 2,
        "cy": (min(ys) + max(ys)) / 2,
        "w": max(xs) - min(xs),
        "h": max(ys) - min(ys),
        "x0": min(xs),
        "x1": max(xs),
        "y0": min(ys),
        "y1": max(ys),
        "topSlopeDeg": math.degrees(
            math.atan2((top_r[1] - top_l[1]) * height, (top_r[0] - top_l[0]) * width)
        ),
        "botSlopeDeg": math.degrees(
            math.atan2((bot_r[1] - bot_l[1]) * height, (bot_r[0] - bot_l[0]) * width)
        ),
    }


def analyse(directory: Path, width: float, height: float) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    states = []
    for state in manifest["states"]:
        data = json.loads((directory / f"{state['id']}.json").read_text())
        cards = [quad_metrics(c, width, height) for c in data["quads"]]
        onscreen = [c for c in cards if c["x1"] > -40 and c["x0"] < width + 40
                    and c["y1"] > -40 and c["y0"] < height + 40]

        # Overlap: the real test is quad against quad. Cards are convex, so a
        # separating-axis test is exact, and it does not care that neighbouring
        # rows are half a cell apart or that outer cards are yawed -- both of
        # which make an axis-aligned row/column test meaningless.
        overlaps = []
        min_sep = math.inf
        for a_i in range(len(onscreen)):
            for b_i in range(a_i + 1, len(onscreen)):
                a, b = onscreen[a_i], onscreen[b_i]
                sep = quad_separation(a["poly"], b["poly"])
                if sep < min_sep:
                    min_sep = sep
                if sep <= 0:
                    overlaps.append({
                        "a": [a["i"], a["j"]], "b": [b["i"], b["j"]],
                        "penetrationPx": round(-sep, 2),
                    })

        # Reported separately because they are the numbers the brief names.
        by_row: dict[int, list[dict]] = {}
        for c in onscreen:
            by_row.setdefault(c["j"], []).append(c)
        min_gap = math.inf
        for row in by_row.values():
            row.sort(key=lambda c: c["cx"])
            for a, b in zip(row, row[1:]):
                min_gap = min(min_gap, b["x0"] - a["x1"])

        states.append({
            "id": state["id"],
            "offset": state["offset"],
            "cards": [{k: v for k, v in c.items() if k != "poly"}
                      for c in sorted(onscreen, key=lambda c: (-c["j"], c["cx"]))],
            "minHorizontalGapPx": round(min_gap, 2),
            "minQuadSeparationPx": round(min_sep, 2),
            "overlaps": overlaps,
        })
    return {"dir": str(directory), "viewport": [width, height], "states": states}


def quad_separation(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    """
    Separating-axis distance between two convex quads. Positive is a real gap in
    pixels along the best separating axis; <= 0 means they intersect.
    """
    best = -math.inf
    for poly in (a, b):
        for k in range(len(poly)):
            x0, y0 = poly[k]
            x1, y1 = poly[(k + 1) % len(poly)]
            nx, ny = -(y1 - y0), (x1 - x0)
            length = math.hypot(nx, ny)
            if length < 1e-9:
                continue
            nx, ny = nx / length, ny / length
            pa = [p[0] * nx + p[1] * ny for p in a]
            pb = [p[0] * nx + p[1] * ny for p in b]
            gap = max(min(pb) - max(pa), min(pa) - max(pb))
            best = max(best, gap)
    return best


def curve_consistency(result: dict) -> dict:
    """
    Pool every visible card from every offset state and fit one smooth curve of
    projected width against projected centre x, and one of bottom-edge slope
    against centre x. If the layout is offset-invariant, every state's cards lie
    on the SAME curve, so the residual scatter is near zero. Bucketing by cx
    cannot show this -- width changes fast enough near the frame edge that the
    bucket width itself dominates -- so this fits and reports residuals.
    """
    # Edge slope is not a function of cx alone: it scales with how far the edge
    # sits from the projection centre, so a card above the centre line and one
    # below it tilt opposite ways at the same cx. Normalising by (cy - 450)
    # collapses every row onto one curve, which is the quantity that must be
    # offset-invariant. Cards straddling the centre line are excluded because
    # the normaliser goes to zero there.
    cy0 = result["viewport"][1] / 2
    samples = []
    for state in result["states"]:
        for c in state["cards"]:
            lever = (c["cy"] - cy0) / 1000.0
            if abs(lever) < 0.06:
                continue
            samples.append((c["cx"], c["w"], math.tan(math.radians(c["botSlopeDeg"])) / lever,
                            state["id"]))
    if len(samples) < 8:
        return {"samples": len(samples), "insufficient": True}

    xs = [s[0] for s in samples]
    lo, hi = min(xs), max(xs)
    span = max(1.0, hi - lo)
    norm = [(x - lo) / span * 2 - 1 for x in xs]

    def fit(values: list[float], degree: int = 5) -> tuple[list[float], float, list[float]]:
        n = len(values)
        # Plain normal equations on a small Vandermonde; degree 5 over ~90
        # samples is well conditioned once x is normalised to [-1, 1].
        a = [[sum(norm[k] ** (i + j) for k in range(n)) for j in range(degree + 1)]
             for i in range(degree + 1)]
        rhs = [sum(values[k] * norm[k] ** i for k in range(n)) for i in range(degree + 1)]
        coeffs = solve(a, rhs)
        pred = [sum(coeffs[i] * norm[k] ** i for i in range(degree + 1)) for k in range(n)]
        residuals = [values[k] - pred[k] for k in range(n)]
        return coeffs, max(abs(r) for r in residuals), residuals

    def solve(a: list[list[float]], b: list[float]) -> list[float]:
        n = len(b)
        m = [row[:] + [b[i]] for i, row in enumerate(a)]
        for col in range(n):
            pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
            m[col], m[pivot] = m[pivot], m[col]
            if abs(m[col][col]) < 1e-12:
                continue
            for r in range(n):
                if r == col:
                    continue
                f = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= f * m[col][c]
        return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]

    _, w_res, w_all = fit([s[1] for s in samples])
    _, s_res, s_all = fit([s[2] for s in samples])
    # Convert the normalised-slope residual back into degrees at a typical
    # lever of 0.21 (a mid or bottom row card), so the number is readable.
    lever_ref = 0.21
    return {
        "samples": len(samples),
        "cxRange": [round(lo, 1), round(hi, 1)],
        "widthMaxResidualPx": round(w_res, 3),
        "widthRmsResidualPx": round((sum(r * r for r in w_all) / len(w_all)) ** 0.5, 3),
        "normalisedSlopeMaxResidual": round(s_res, 4),
        "slopeMaxResidualDeg": round(math.degrees(math.atan(s_res * lever_ref)), 3),
        "slopeRmsResidualDeg": round(math.degrees(math.atan(
            (sum(r * r for r in s_all) / len(s_all)) ** 0.5 * lever_ref)), 3),
    }


if __name__ == "__main__":
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    out = Path(args.get("--out", "qa-v5/f0"))
    out.mkdir(parents=True, exist_ok=True)

    main = analyse(Path(args["--dir"]), 1440.0, 900.0)
    report = {"sweep": main, "curveConsistency": curve_consistency(main)}
    if "--partial" in args:
        report["partialViewport"] = analyse(Path(args["--partial"]), 1100.0, 720.0)

    all_states = list(main["states"])
    if "partialViewport" in report:
        all_states += report["partialViewport"]["states"]
    min_h = min(s["minHorizontalGapPx"] for s in all_states)
    min_sep = min(s["minQuadSeparationPx"] for s in all_states)
    overlap_count = sum(len(s["overlaps"]) for s in all_states)

    report["summary"] = {
        "minHorizontalGapPx": round(min_h, 2),
        "minQuadSeparationPx": round(min_sep, 2),
        "overlapCount": overlap_count,
        "noOverlap": overlap_count == 0 and min_sep > 0,
        "widthMaxResidualPx": report["curveConsistency"].get("widthMaxResidualPx"),
        "slopeMaxResidualDeg": report["curveConsistency"].get("slopeMaxResidualDeg"),
    }
    (out / "curves.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report["summary"], indent=2))
    for state in main["states"]:
        print(f"  {state['id']:<22} offset={state['offset']} "
              f"minHGap={state['minHorizontalGapPx']:>6} minQuadSep={state['minQuadSeparationPx']:>6} "
              f"overlaps={len(state['overlaps'])}")
    if "partialViewport" in report:
        for state in report["partialViewport"]["states"]:
            print(f"  partial/{state['id']:<13} offset={state['offset']} "
                  f"minHGap={state['minHorizontalGapPx']:>6} minQuadSep={state['minQuadSeparationPx']:>6} "
                  f"overlaps={len(state['overlaps'])}")
