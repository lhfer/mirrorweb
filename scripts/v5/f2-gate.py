#!/usr/bin/env python3
"""
Stage F2 absolute gate: local composition vs the Target, at every viewport.

Unlike the F0 gate this cannot probe fixed 1440-space x positions -- that would
silently gate only the anchor viewport. Every feature is derived from each
frame's own measured structure, so the same code judges a 390-wide portrait
frame and a 1920-wide desktop one.

Compared, per viewport:
  * how many row bands are visible, and where their centres sit
  * where the vertical gutters sit inside each row
  * the size of every card the frame does not clip

Thresholds scale with the viewport, because 3 px means something different at
390 wide than at 1920 wide.

Usage: f2-gate.py --pairs=<json> --out=<dir>
  pairs json: [{"id","targetPng","localPng","dpr"}, ...]
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ML = _load("measure_layout", "measure-layout.py")

GATE = {
    "rowBandPctOfHeight": 2.0,
    "gutterCentrePctOfWidth": 2.0,
    "cardSizePct": 3.0,
    "gutterWidthPctOfWidth": 0.6,
    "rowCountMustMatch": True,
}


def normalise(measure: dict, dpr: float) -> dict:
    """Everything in CSS pixels, so a DPR3 Target frame compares with a DPR1
    local one."""
    w = measure["size"]["w"] / dpr
    h = measure["size"]["h"] / dpr
    rows = []
    for r in measure["rows"]:
        rows.append({
            "y0": r["y0"] / dpr,
            "y1": r["y1"] / dpr,
            "cy": (r["y0"] + r["y1"]) / 2 / dpr,
            "clipped": bool(r["clippedTop"] or r["clippedBottom"]),
            "gutters": [{"c": g["center"] / dpr, "w": g["width"] / dpr} for g in r["verticalGutters"]],
            "cards": [
                {
                    "x0": c["x0"] / dpr, "x1": c["x1"] / dpr, "w": c["w"] / dpr,
                    "h": (c["h"] / dpr) if c.get("h") else None,
                    "unclipped": not (c["clipped"]["left"] or c["clipped"]["right"]),
                }
                for c in r["cards"]
            ],
        })
    # A band that touches the frame edge is a truncated observation, not a row
    # separator: at 1366x768 the Target's last five scanlines read as a "band"
    # simply because the bottom row has not started yet. Dropping them on both
    # sides is what makes the band count comparable.
    bands = [
        b["center"] / dpr
        for b in measure["horizontalGutterBands"]
        if b["y0"] > 0 and b["y1"] < measure["size"]["h"] - 1 and b["height"] >= 5
    ]
    return {"viewW": w, "viewH": h, "bands": bands, "rows": rows}


def pair_up(a: list[float], b: list[float], max_distance: float | None = None):
    """
    Greedy nearest-neighbour pairing of two sorted feature lists.

    `max_distance` refuses absurd pairings. Without it a feature the local frame
    simply does not have gets matched to whatever is nearest, turning a missing
    feature into a huge position error and hiding the real cause.
    """
    out = []
    used = set()
    for x in a:
        best, bi = None, None
        for i, y in enumerate(b):
            if i in used:
                continue
            d = abs(x - y)
            if best is None or d < best:
                best, bi = d, i
        if bi is not None and (max_distance is None or best <= max_distance):
            used.add(bi)
            out.append((x, b[bi]))
    return out


def compare(entry: dict) -> dict:
    t = normalise(ML.measure(Path(entry["targetPng"])), entry.get("targetDpr", 1))
    l = normalise(ML.measure(Path(entry["localPng"])), entry.get("localDpr", 1))
    vw, vh = t["viewW"], t["viewH"]
    checks = []

    def check(name, value, limit, unit, detail=""):
        checks.append({"check": name, "value": round(float(value), 3), "limit": limit,
                       "unit": unit, "pass": bool(abs(value) <= limit), "detail": detail})

    # ---- row structure ----------------------------------------------------
    # Split, because the two directions mean different things. A LOCAL band the
    # Target does not have is structure this build invented -- always a defect.
    # A TARGET band the local frame does not have is structure this build is
    # missing, which at tall portrait viewports is the missing vertical grid
    # curvature (see docs/v5/RESPONSIVE_SCALING.md) rather than a scaling error.
    band_pairs = pair_up(t["bands"], l["bands"], max_distance=vh * 0.08)
    matched_local = {b for _, b in band_pairs}
    check(f"{entry['id']} invented bands", len([b for b in l["bands"] if b not in matched_local]),
          0, "bands", f"local bands with no Target counterpart")
    check(f"{entry['id']} missing bands", len(t["bands"]) - len(band_pairs), 0, "bands",
          f"target {len(t['bands'])}, local {len(l['bands'])}, matched {len(band_pairs)}")
    worst_band = max((abs(a - b) for a, b in band_pairs), default=0.0)
    check(f"{entry['id']} row band centres", worst_band / vh * 100,
          GATE["rowBandPctOfHeight"], "% of height",
          f"worst {worst_band:.1f} px over {len(band_pairs)} bands")

    # ---- gutters, row by row ---------------------------------------------
    worst_gc, worst_gw = 0.0, 0.0
    gutters = []
    # Rows are paired by where they sit vertically, not by index. Index pairing
    # silently shifts the whole comparison by one row whenever one side clips a
    # row the other does not, which turns a real parity difference into a set of
    # small, meaningless errors.
    #
    # Pairing uses every row, including clipped ones, so a row that one side
    # clips by a pixel still finds its partner; the per-row comparisons below
    # then only run where both rows are unclipped.
    row_pairs = []
    taken = set()
    for rt in t["rows"]:
        best, bi = None, None
        for i, rl in enumerate(l["rows"]):
            if i in taken:
                continue
            d = abs(rt["cy"] - rl["cy"])
            if best is None or d < best:
                best, bi = d, i
        if bi is not None and best <= vh * 0.12:
            taken.add(bi)
            row_pairs.append((rt, l["rows"][bi]))
    row_pairs = [(a, b) for a, b in row_pairs if not a["clipped"] and not b["clipped"]]

    # Gutter matching tolerance is a quarter of a cell: wide enough to absorb
    # position error, far too narrow to accept a half-cell parity swap.
    quarter_cell = vw * 0.5 * 0.25 if vw else 0
    tol = max(20.0, quarter_cell)
    missing = 0
    for rt, rl in row_pairs:
        tg = [g["c"] for g in rt["gutters"]]
        lg = [g["c"] for g in rl["gutters"]]
        pairs_g = pair_up(tg, lg, max_distance=tol)
        missing += len(tg) - len(pairs_g)
        for gt, gl in pairs_g:
            worst_gc = max(worst_gc, abs(gt - gl))
            gutters.append({"row": round(rt["cy"], 1), "targetCentre": round(gt, 1),
                            "localCentre": round(gl, 1), "dPx": round(gl - gt, 2)})
        for gt, gl in pair_up([g["w"] for g in rt["gutters"]], [g["w"] for g in rl["gutters"]]):
            worst_gw = max(worst_gw, abs(gt - gl))
    # One unmatched gutter is detector sensitivity -- the strict void preset
    # resolves a gutter on one side and not the other. More than one, or a whole
    # row's worth, is a parity or offset difference.
    check(f"{entry['id']} unmatched gutters", missing, 1, "gutters",
          f"{missing} Target gutters with no local counterpart within {tol:.0f} px")
    check(f"{entry['id']} gutter centres", worst_gc / vw * 100,
          GATE["gutterCentrePctOfWidth"], "% of width", f"worst {worst_gc:.1f} px")
    check(f"{entry['id']} gutter widths", worst_gw / vw * 100,
          GATE["gutterWidthPctOfWidth"], "% of width", f"worst {worst_gw:.1f} px")

    # ---- card sizes -------------------------------------------------------
    cards = []
    worst_w, worst_h = 0.0, 0.0
    for rt, rl in row_pairs:
        ct = [c for c in rt["cards"] if c["unclipped"]]
        cl = [c for c in rl["cards"] if c["unclipped"]]
        for a, b in pair_up([c["w"] for c in ct], [c["w"] for c in cl]):
            worst_w = max(worst_w, abs(b - a) / a * 100)
            cards.append({"row": round(rt["cy"], 1), "targetW": round(a, 1),
                          "localW": round(b, 1), "dPct": round((b - a) / a * 100, 3)})
        hts_t = [c["h"] for c in ct if c["h"]]
        hts_l = [c["h"] for c in cl if c["h"]]
        for a, b in pair_up(hts_t, hts_l):
            worst_h = max(worst_h, abs(b - a) / a * 100)
    if cards:
        check(f"{entry['id']} unclipped card width", worst_w, GATE["cardSizePct"], "%")
    if worst_h:
        check(f"{entry['id']} unclipped card height", worst_h, GATE["cardSizePct"], "%")

    return {
        "id": entry["id"], "viewport": [vw, vh],
        "targetBands": [round(x, 1) for x in t["bands"]],
        "localBands": [round(x, 1) for x in l["bands"]],
        "gutters": gutters, "cards": cards, "checks": checks,
        "verdict": "PASS" if all(c["pass"] for c in checks) else "FAIL",
    }


if __name__ == "__main__":
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    pairs = json.loads(Path(args["--pairs"]).read_text())
    out = Path(args.get("--out", "qa-v5/f2"))
    out.mkdir(parents=True, exist_ok=True)
    results = [compare(p) for p in pairs]
    overall = "PASS" if all(r["verdict"] == "PASS" for r in results) else "FAIL"
    payload = {"gate": GATE, "verdict": overall, "viewports": results}
    (out / "gate.json").write_text(json.dumps(payload, indent=2))
    print(f"F2 GATE: {overall}")
    for r in results:
        print(f"  {r['id']:<14} {int(r['viewport'][0])}x{int(r['viewport'][1])}  {r['verdict']}")
        for c in r["checks"]:
            mark = "PASS" if c["pass"] else "FAIL"
            print(f"      [{mark}] {c['check'].split(' ', 1)[1]:<26} {c['value']:>8} {c['unit']:<12} "
                  f"(limit {c['limit']})  {c['detail']}")
    sys.exit(0 if overall == "PASS" else 1)
