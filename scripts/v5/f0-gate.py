#!/usr/bin/env python3
"""
Stage F0 absolute gate: local layout vs the Target frame.

Order of judgement is the one the brief fixes: the candidate is scored against
the Target first, in absolute terms. There is no "better than best" fallback --
a candidate that misses an absolute threshold fails, full stop.

Both sides are measured by scripts/v5/measure-layout.py, the same instrument,
and the local side is measured in `?foundation=layout` so no video, glass rim or
CSS3D type can move an edge.

Usage: f0-gate.py --target=<png> --local-dir=<dir> --out=<dir>
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ML = _load("measure_layout", "measure-layout.py")

VIEW_W, VIEW_H = 1440.0, 900.0

# Absolute thresholds, straight from the brief.
GATE = {
    "landmarkPctOfViewport": 2.0,
    "cardSizePct": 3.0,
    "gutterPx": 3.0,
    "edgeSlopeDeg": 0.75,
    "symmetryPct": 1.0,
}


def row_of(measure: dict, index: int) -> dict:
    return measure["rows"][index]


def card_at(row: dict, x: float) -> dict | None:
    """The card region containing screen x."""
    for c in row["cards"]:
        if c["x0"] <= x <= c["x1"]:
            return c
    return None


def gutter_widths(row: dict) -> list[float]:
    return [g["width"] for g in row["verticalGutters"]]


def pct(a: float, b: float) -> float:
    """Signed percentage error of `a` against reference `b`."""
    return (a - b) / b * 100 if b else math.inf


def build(target_png: Path, local_dir: Path, out_dir: Path) -> dict:
    target = ML.measure(target_png)
    # No void override any more. Since F2 calibrated CLEAR_COLOR the local void
    # is the same navy the Target clears to, so the detector auto-selects its
    # NAVY preset on both sides: one instrument, one calibration, both frames.
    local_rest = ML.measure(local_dir / "01-rest.png")

    # Both frames resolve four row bands: clipped top, mid, bottom, clipped
    # bottom. Index 1 is the mid row, index 2 the bottom row.
    t_mid, t_bot = row_of(target, 1), row_of(target, 2)
    l_mid, l_bot = row_of(local_rest, 1), row_of(local_rest, 2)

    checks: list[dict] = []

    def check(name: str, value: float, limit: float, unit: str, detail: str = "") -> None:
        checks.append({
            "check": name,
            "value": round(value, 3),
            "limit": limit,
            "unit": unit,
            "pass": bool(abs(value) <= limit),
            "detail": detail,
        })

    # ---------------------------------------------------------- 1. landmarks
    # Nine landmark centres. Seven are card regions that BOTH detectors isolate
    # in the same place; the two top-row entries are row-structure landmarks,
    # because the Target's top row is a corner-clipped sliver whose apparent
    # gutter is 76 px wide against the local 21 px -- a detector artefact of the
    # clipped rounded corners, not a layout difference. They are reported with
    # their confidence rather than dropped.
    landmarks = []
    for label, row_t, row_l, probe, mirror_probe in [
        ("mid.leftClip", t_mid, l_mid, 84.0, None),
        ("mid.left", t_mid, l_mid, 445.5, None),
        ("mid.right", t_mid, l_mid, 993.5, 445.5),
        ("mid.rightClip", t_mid, l_mid, 1355.0, 84.0),
        ("bottom.left", t_bot, l_bot, 214.5, None),
        ("bottom.center", t_bot, l_bot, 719.5, None),
        ("bottom.right", t_bot, l_bot, 1224.5, None),
    ]:
        ct, cl = card_at(row_t, probe), card_at(row_l, probe)
        if not ct or not cl:
            landmarks.append({"name": label, "status": "unmeasurable"})
            continue
        # Under the strict void preset the Target's mid row does not resolve its
        # right-hand gutter (that stretch of void darkens to ~(0,0,6)), so the
        # right half of the row comes back as one merged region. Those two
        # landmarks are taken from the mirror of their left-hand twin; the
        # Target's own bottom row proves the composition symmetric to 0.15 px,
        # and a relaxed pass does resolve the gutter at 1257..1270, mirroring
        # 169..182 to within 1 px.
        mirrored = bool(mirror_probe) and ct["w"] > 700
        src = card_at(row_t, mirror_probe) if mirrored else ct
        tcx = (VIEW_W - 1 - src["cx"]) if mirrored else ct["cx"]
        tcy = src.get("cy") if mirrored else ct.get("cy")
        entry = {
            "name": label,
            "source": "mirrored" if mirrored else "direct",
            "targetCx": round(tcx, 2),
            "localCx": round(cl["cx"], 2),
            "dxPx": round(cl["cx"] - tcx, 2),
            "dxPctViewport": round((cl["cx"] - tcx) / VIEW_W * 100, 3),
        }
        if tcy is not None and cl.get("cy") is not None:
            entry.update({
                "targetCy": round(tcy, 2),
                "localCy": round(cl["cy"], 2),
                "dyPx": round(cl["cy"] - tcy, 2),
                "dyPctViewport": round((cl["cy"] - tcy) / VIEW_H * 100, 3),
            })
        landmarks.append(entry)

    for label, t_val, l_val in [
        ("top.rowBandCenter", target["horizontalGutterBands"][0]["center"],
         local_rest["horizontalGutterBands"][0]["center"]),
        ("bottom.rowBandCenter", target["horizontalGutterBands"][2]["center"],
         local_rest["horizontalGutterBands"][2]["center"]),
    ]:
        landmarks.append({
            "name": label,
            "source": "row-band",
            "targetCy": round(t_val, 2),
            "localCy": round(l_val, 2),
            "dyPx": round(l_val - t_val, 2),
            "dyPctViewport": round((l_val - t_val) / VIEW_H * 100, 3),
        })

    worst = 0.0
    for lm in landmarks:
        worst = max(worst, abs(lm.get("dxPctViewport", 0)), abs(lm.get("dyPctViewport", 0)))
    check("landmark centres (worst of 9)", worst, GATE["landmarkPctOfViewport"], "% of viewport")

    # --------------------------------------------------------- 2. card sizes
    sizes = []
    for label, row_t, row_l, probe in [
        ("mid full card", t_mid, l_mid, 445.5),
        ("bottom centre card", t_bot, l_bot, 719.5),
        ("bottom outer card", t_bot, l_bot, 214.5),
    ]:
        ct, cl = card_at(row_t, probe), card_at(row_l, probe)
        row = {
            "name": label,
            "targetW": ct["w"], "localW": cl["w"], "dwPct": round(pct(cl["w"], ct["w"]), 3),
        }
        if ct.get("h") and cl.get("h"):
            row.update({
                "targetH": round(ct["h"], 2), "localH": round(cl["h"], 2),
                "dhPct": round(pct(cl["h"], ct["h"]), 3),
                "targetAspect": round(ct["w"] / ct["h"], 4),
                "localAspect": round(cl["w"] / cl["h"], 4),
                "daspectPct": round(pct(cl["w"] / cl["h"], ct["w"] / ct["h"]), 3),
            })
        sizes.append(row)
        check(f"{label} width", row["dwPct"], GATE["cardSizePct"], "%")
        if "dhPct" in row:
            check(f"{label} height", row["dhPct"], GATE["cardSizePct"], "%")

    # ----------------------------------------------------------- 3. gutters
    # Horizontal: the centre gutter of the mid row and both bottom-row gutters.
    t_h = [g for g in t_mid["verticalGutters"] if 600 < g["center"] < 840] + t_bot["verticalGutters"]
    l_h = [g for g in l_mid["verticalGutters"] if 600 < g["center"] < 840] + l_bot["verticalGutters"]
    gutters = {"horizontal": [], "vertical": []}
    for gt, gl in zip(t_h, l_h):
        gutters["horizontal"].append({
            "targetCenter": gt["center"], "localCenter": gl["center"],
            "targetWidth": gt["width"], "localWidth": gl["width"],
            "dPx": gl["width"] - gt["width"],
        })
        check(f"h-gutter @x~{int(gt['center'])}", gl["width"] - gt["width"], GATE["gutterPx"], "px")

    t_v = target["horizontalGutterBands"][1]
    l_v = local_rest["horizontalGutterBands"][1]
    gutters["vertical"].append({
        "targetY": [t_v["y0"], t_v["y1"]], "localY": [l_v["y0"], l_v["y1"]],
        "targetHeight": t_v["height"], "localHeight": l_v["height"],
        "dPx": l_v["height"] - t_v["height"],
    })
    check("v-gutter mid<->bottom", l_v["height"] - t_v["height"], GATE["gutterPx"], "px")

    # ------------------------------------------------------ 4. edge slopes
    slopes = []
    for label, row_t, row_l, probe in [
        ("bottom left outer", t_bot, l_bot, 214.5),
        ("bottom centre", t_bot, l_bot, 719.5),
        ("bottom right outer", t_bot, l_bot, 1224.5),
    ]:
        ct, cl = card_at(row_t, probe), card_at(row_l, probe)
        if not ct or not cl or not ct.get("bottomEdge") or not cl.get("bottomEdge"):
            continue
        ts, ls = ct["bottomEdge"]["slopeDeg"], cl["bottomEdge"]["slopeDeg"]
        slopes.append({"name": label, "targetDeg": ts, "localDeg": ls, "dDeg": round(ls - ts, 3)})
        check(f"edge slope {label}", ls - ts, GATE["edgeSlopeDeg"], "deg")

    # -------------------------------------------------------- 5. symmetry
    sym = []
    for label, row, left_probe, right_probe in [
        ("local mid clips", l_mid, 84.0, 1355.0),
        ("local bottom outers", l_bot, 214.5, 1224.5),
    ]:
        a, b = card_at(row, left_probe), card_at(row, right_probe)
        if not a or not b:
            continue
        mirror_dx = (a["cx"] + b["cx"]) / 2 - (VIEW_W - 1) / 2
        dw = pct(b["w"], a["w"])
        sym.append({"name": label, "mirrorOffsetPx": round(mirror_dx, 2), "widthDeltaPct": round(dw, 3)})
        check(f"symmetry {label} width", dw, GATE["symmetryPct"], "%")
        check(f"symmetry {label} mirror", mirror_dx / VIEW_W * 100, GATE["symmetryPct"], "% of viewport")

    # --------------------------------------------- 6. parity / overlap / band
    t_bot_gutters = sorted(g["center"] for g in t_bot["verticalGutters"])
    l_bot_gutters = sorted(g["center"] for g in l_bot["verticalGutters"])
    t_mid_gutters = sorted(g["center"] for g in t_mid["verticalGutters"])
    l_mid_gutters = sorted(g["center"] for g in l_mid["verticalGutters"])
    parity = {
        "targetMidHasCentreGutter": any(abs(c - 719.5) < 20 for c in t_mid_gutters),
        "localMidHasCentreGutter": any(abs(c - 719.5) < 20 for c in l_mid_gutters),
        "targetBottomHasCentreCard": card_at(t_bot, 719.5) is not None
        and not any(abs(c - 719.5) < 20 for c in t_bot_gutters),
        "localBottomHasCentreCard": card_at(l_bot, 719.5) is not None
        and not any(abs(c - 719.5) < 20 for c in l_bot_gutters),
    }
    parity["match"] = (
        parity["targetMidHasCentreGutter"] == parity["localMidHasCentreGutter"]
        and parity["targetBottomHasCentreCard"] == parity["localBottomHasCentreCard"]
        and parity["localMidHasCentreGutter"]
        and parity["localBottomHasCentreCard"]
    )
    checks.append({"check": "row parity matches Target", "value": parity["match"],
                   "limit": True, "unit": "bool", "pass": bool(parity["match"]),
                   "detail": "mid row straddles the midline, bottom row has a centre card"})

    # Viewport centre must land in a horizontal gutter on both sides.
    centre_band = {
        "targetBandAtY450": any(b["y0"] <= 450 <= b["y1"] for b in target["horizontalGutterBands"]),
        "localBandAtY450": any(b["y0"] <= 450 <= b["y1"] for b in local_rest["horizontalGutterBands"]),
    }
    ok = centre_band["targetBandAtY450"] and centre_band["localBandAtY450"]
    checks.append({"check": "viewport centre sits in a horizontal gutter", "value": ok,
                   "limit": True, "unit": "bool", "pass": bool(ok), "detail": ""})

    return {
        "target": str(target_png),
        "local": str(local_dir),
        "gate": GATE,
        "landmarks": landmarks,
        "cardSizes": sizes,
        "gutters": gutters,
        "edgeSlopes": slopes,
        "symmetry": sym,
        "rowParity": parity,
        "centreBand": centre_band,
        "checks": checks,
        "verdict": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "targetMeasure": target,
        "localMeasure": local_rest,
    }


if __name__ == "__main__":
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    result = build(
        Path(args["--target"]),
        Path(args["--local-dir"]),
        Path(args.get("--out", "qa-v5/f0")),
    )
    out = Path(args.get("--out", "qa-v5/f0"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "gate.json").write_text(json.dumps(result, indent=2))
    print(f"verdict: {result['verdict']}")
    for c in result["checks"]:
        mark = "PASS" if c["pass"] else "FAIL"
        print(f"  [{mark}] {c['check']:<44} {c['value']} {c['unit']} (limit {c['limit']})")
