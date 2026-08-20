#!/usr/bin/env python3
"""
Stage F2 absolute gate -- the approved contract, restored in full.

An earlier revision of this file replaced the contract's absolute 3 px gutter
threshold with a percentage of viewport width, and scored a check the contract
does not contain. Both are corrected here: the thresholds below are the approved
ones, gutters are judged in absolute pixels at every viewport, and every
contract item reports PASS / FAIL / NOT_MEASURED rather than being skipped when
it is hard to measure.

Findings that are real but outside the contract are reported under
`auxiliaryFindings`. They never change the verdict, and they are never used to
excuse a contract failure either.

Usage: f2-gate.py --pairs=<json> --out=<dir> [--f0=<f0 gate.json>]
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


def consensus_measure(pngs: list[str], frac: float = 0.8):
    """
    Measure a Target viewport from several frames instead of one.

    The cards contain video. A dark enough frame reads as void, which invents
    gutters and truncates card edges; several frames of the same viewport tell
    that apart, because a real gutter is void in every one of them. Thresholds
    are untouched -- this changes only how reliably the Target's structure is
    observed, and it can only make the Target's geometry MORE complete.
    """
    import numpy as np
    from PIL import Image
    edge_votes = band_votes = None
    for f in pngs:
        rgb = np.asarray(Image.open(f).convert("RGB"))
        edge_preset, band_preset = ML.pick_void(rgb)
        e = ML.void_mask(rgb, edge_preset)
        b = ML.void_mask(rgb, band_preset)
        edge_votes = e.astype(np.int16) if edge_votes is None else edge_votes + e
        band_votes = b.astype(np.int16) if band_votes is None else band_votes + b
    need = int(np.ceil(frac * len(pngs)))
    # Both presets get their own consensus. The detector uses the strict one for
    # card edges and the relaxed one for gutters and bands; collapsing them into
    # a single mask would hand edge tracing the wrong preset.
    return ML.measure(Path(pngs[0]), mask_override=(edge_votes >= need),
                      band_mask_override=(band_votes >= need))

# Approved contract. Do not relax to make a candidate green.
CONTRACT = {
    "cardCentrePctOfViewport": 2.0,
    "cardSizePct": 3.0,
    "gutterPx": 3.0,          # ABSOLUTE pixels, at every viewport
    "edgeYawDeg": 0.75,
    "rowParityMustMatch": True,
    "centreDarkBandMustMatch": True,
    "noCardOverlap": True,
    "largeVoidExcessPctOfFrame": 2.0,
    "f0RegressionMustPass": True,
}

ITEMS = ["cardCentre", "cardSize", "gutterPx", "edgeYaw", "rowParity",
         "centreDarkBand", "overlap", "largeVoid", "f0Regression"]


def _card(c: dict, row: dict, dpr: float) -> dict:
    """
    One card, with a validity flag on its traced edges.

    The detector finds a card's top and bottom edge by walking columns until it
    hits void. On a Target frame the cards contain video, and a dark enough
    frame stops that walk early -- which silently shortens the card and tilts
    its "edge". The local foundation frame has flat opaque slabs and can never
    do this, so an untested comparison is asymmetric in the Target's disfavour.
    The test: a traced edge is only trusted when it actually reached the row
    boundary. Rejections are counted and reported, never silently dropped.
    """
    tol = max(4.0, (row["y1"] - row["y0"]) * 0.03)
    top = c.get("topEdge") or {}
    bot = c.get("bottomEdge") or {}
    top_ok = bool(top) and abs(top.get("yAtCx", -1e9) - row["y0"]) <= tol and not row["clippedTop"]
    bot_ok = bool(bot) and abs(bot.get("yAtCx", -1e9) - row["y1"]) <= tol and not row["clippedBottom"]
    return {
        "x0": c["x0"] / dpr, "x1": c["x1"] / dpr, "w": c["w"] / dpr,
        "h": (c["h"] / dpr) if (c.get("h") and top_ok and bot_ok) else None,
        "cx": c["cx"] / dpr,
        "cy": (c["cy"] / dpr) if (c.get("cy") and top_ok and bot_ok) else None,
        "botSlope": bot.get("slopeDeg") if bot_ok else None,
        "edgeTraceValid": {"top": top_ok, "bottom": bot_ok},
        "unclipped": not (c["clipped"]["left"] or c["clipped"]["right"]),
    }


def normalise(measure: dict, dpr: float) -> dict:
    h_px = measure["size"]["h"]
    rows = []
    for r in measure["rows"]:
        rows.append({
            "y0": r["y0"] / dpr, "y1": r["y1"] / dpr,
            "cy": (r["y0"] + r["y1"]) / 2 / dpr,
            "clipped": bool(r["clippedTop"] or r["clippedBottom"]),
            "gutters": [{"c": g["center"] / dpr, "w": g["width"] / dpr}
                        for g in r["verticalGutters"]],
            "cards": [_card(c, r, dpr) for c in r["cards"]],
        })
    bands = [{"c": b["center"] / dpr, "y0": b["y0"] / dpr, "y1": b["y1"] / dpr,
              "edge": bool(b["y0"] <= 0 or b["y1"] >= h_px - 1)}
             for b in measure["horizontalGutterBands"]]
    return {"viewW": measure["size"]["w"] / dpr, "viewH": measure["size"]["h"] / dpr,
            "rows": rows, "bands": bands}


def nearest_pairs(a: list, b: list, key, tol: float):
    out, taken = [], set()
    for x in a:
        best, bi = None, None
        for i, y in enumerate(b):
            if i in taken:
                continue
            d = abs(key(x) - key(y))
            if best is None or d < best:
                best, bi = d, i
        if bi is not None and best <= tol:
            taken.add(bi)
            out.append((x, b[bi]))
    return out


def void_stats(png: Path) -> dict:
    """Void coverage and the largest contiguous void blob, as frame fractions."""
    import numpy as np
    from PIL import Image
    rgb = np.asarray(Image.open(png).convert("RGB"))
    void = ML.void_mask(rgb, ML.pick_void(rgb)[0])
    step = 4  # coarse grid: enough to spot a hole the size of a card
    g = void[::step, ::step]
    seen = np.zeros_like(g)
    best = 0
    h, w = g.shape
    for sy in range(h):
        for sx in range(w):
            if not g[sy, sx] or seen[sy, sx]:
                continue
            stack = [(sy, sx)]
            seen[sy, sx] = True
            size = 0
            while stack:
                y, x = stack.pop()
                size += 1
                for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                    if 0 <= ny < h and 0 <= nx < w and g[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            best = max(best, size)
    return {"voidFraction": float(g.mean()), "largestBlobFraction": best / g.size}


def quad_separation(a, b) -> float:
    best = -math.inf
    for poly in (a, b):
        for k in range(len(poly)):
            x0, y0 = poly[k]
            x1, y1 = poly[(k + 1) % len(poly)]
            nx, ny = -(y1 - y0), (x1 - x0)
            L = math.hypot(nx, ny)
            if L < 1e-9:
                continue
            nx, ny = nx / L, ny / L
            pa = [p[0] * nx + p[1] * ny for p in a]
            pb = [p[0] * nx + p[1] * ny for p in b]
            best = max(best, max(min(pb) - max(pa), min(pa) - max(pb)))
    return best


def overlap_check(local_json: Path, vw: float, vh: float) -> dict:
    if not local_json.exists():
        return {"status": "NOT_MEASURED", "reason": "no local quad json"}
    quads = json.loads(local_json.read_text()).get("quads", [])
    on = []
    for q in quads:
        pts = [(p[0] * vw, p[1] * vh) for p in q["quad"]]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        if max(xs) < -40 or min(xs) > vw + 40 or max(ys) < -40 or min(ys) > vh + 40:
            continue
        on.append({"i": q["i"], "j": q["j"], "poly": pts})
    worst = math.inf
    pairs = []
    for i in range(len(on)):
        for j in range(i + 1, len(on)):
            sep = quad_separation(on[i]["poly"], on[j]["poly"])
            worst = min(worst, sep)
            if sep <= 0:
                pairs.append({"a": [on[i]["i"], on[i]["j"]], "b": [on[j]["i"], on[j]["j"]],
                              "penetrationPx": round(-sep, 2)})
    return {"status": "PASS" if not pairs else "FAIL", "cards": len(on),
            "minSeparationPx": round(worst, 2) if on else None, "overlaps": pairs}


def compare(entry: dict) -> dict:
    frames = entry.get("targetFrames")
    t = normalise(consensus_measure(frames) if frames else ML.measure(Path(entry["targetPng"])),
                  entry.get("targetDpr", 1))
    l = normalise(ML.measure(Path(entry["localPng"])), entry.get("localDpr", 1))
    vw, vh = t["viewW"], t["viewH"]
    checks = []
    item_state = {k: "NOT_MEASURED" for k in ITEMS}

    def check(item, name, value, limit, unit, detail=""):
        ok = bool(abs(value) <= limit) if isinstance(value, (int, float)) and not isinstance(value, bool) \
            else bool(value == limit)
        checks.append({"item": item, "check": name,
                       "value": round(value, 3) if isinstance(value, float) else value,
                       "limit": limit, "unit": unit, "pass": ok, "detail": detail})
        item_state[item] = "FAIL" if (item_state[item] == "FAIL" or not ok) else "PASS"

    # Row usability, in two tiers.
    #
    # What contaminates a row's x-geometry is being a SLIVER -- a row reduced to
    # a thin cap by the frame edge, whose rounded corners open false, over-wide
    # gutters (the Target's top row at 1440x900 reads a 76 px "gutter" where the
    # real one is 21 px). Being clipped by a few pixels does not do that, and
    # excluding merely-clipped rows costs whole viewports: at 1366x768 the local
    # bottom row ends 5 px later than the Target's, which would otherwise leave
    # nothing measurable at all.
    #
    # So: horizontal geometry uses every paired non-sliver row; vertical
    # geometry still requires a row both sides render whole.
    def median_height(rows):
        hs = sorted(r["y1"] - r["y0"] for r in rows)
        return hs[len(hs) // 2] if hs else 0.0

    med = max(median_height(t["rows"]), median_height(l["rows"]))

    def sliver(r):
        return (r["y1"] - r["y0"]) < 0.6 * med

    # Merged regions. When the detector cannot resolve a gutter -- which happens
    # on Target frames because the cards contain video that can read as void,
    # and never on the local foundation frame whose slabs are opaque -- two
    # cards come back as one wide region. Comparing that region to a real card
    # is meaningless. A region wider than 1.3x the row's median unclipped card
    # is marked merged; it and the gutters either side of it are excluded, and
    # the exclusions are counted.
    merged_excluded = 0

    def mark_merged(row):
        widths = [c["w"] for c in row["cards"] if c["unclipped"]]
        if not widths:
            widths = [c["w"] for c in row["cards"]]
        if not widths:
            return
        med = sorted(widths)[len(widths) // 2]
        for c in row["cards"]:
            c["merged"] = bool(c["w"] > 1.30 * med)

    for r in t["rows"] + l["rows"]:
        mark_merged(r)

    # Mirror-symmetry resolvability test. Both compositions are symmetric about
    # the viewport centre -- independently verified, and true of the local
    # frames by construction. So a row whose DETECTED card boundaries are not
    # mirror-symmetric is a row the detector failed to resolve, not a row that
    # is genuinely lopsided. At 1920x1080 the Target's top row comes back as
    # 225/701/752/163 against a local 221/700/700/221: the detector missed one
    # gutter and invented another. Such a row is excluded from card and gutter
    # comparison on both sides, and the exclusions are counted.
    def symmetric(row, tol=6.0):
        edges = sorted([c["x0"] for c in row["cards"]] + [c["x1"] for c in row["cards"]])
        mirrored = sorted(vw - 1 - e for e in edges)
        if len(edges) != len(mirrored):
            return False
        return all(abs(a - b) <= tol for a, b in zip(edges, mirrored))

    asymmetric_excluded = 0
    all_pairs = nearest_pairs(t["rows"], l["rows"], lambda r: r["cy"], vh * 0.12)
    usable = []
    for a, b in all_pairs:
        if sliver(a) or sliver(b):
            continue
        if not symmetric(a) or not symmetric(b):
            asymmetric_excluded += 1
            continue
        usable.append((a, b))
    vertical_ok = [(a, b) for a, b in usable if not a["clipped"] and not b["clipped"]]
    slivers_excluded = len(all_pairs) - len(usable)
    rejected_edges = 0

    worst_c = worst_w = worst_h = worst_yaw = 0.0
    n_c = n_s = n_y = 0
    detail_cards = []
    for rt, rl in usable:
        cards_t = [c for c in rt["cards"] if not c.get("merged")]
        cards_l = [c for c in rl["cards"] if not c.get("merged")]
        merged_excluded += (len(rt["cards"]) - len(cards_t)) + (len(rl["cards"]) - len(cards_l))
        for ct, cl in nearest_pairs(cards_t, cards_l, lambda c: c["cx"], vw * 0.12):
            # Vertical component of the centre comes from the ROW band, which is
            # a full-width statistic and immune to the video-truncation problem.
            d = math.hypot(cl["cx"] - ct["cx"], rl["cy"] - rt["cy"])
            worst_c = max(worst_c, d / max(vw, vh) * 100)
            n_c += 1
            detail_cards.append({"row": round(rt["cy"], 1), "targetCx": round(ct["cx"], 1),
                                 "localCx": round(cl["cx"], 1), "centreErrPx": round(d, 2),
                                 "unclipped": bool(ct["unclipped"] and cl["unclipped"])})
            if ct["unclipped"] and cl["unclipped"]:
                worst_w = max(worst_w, abs(cl["w"] - ct["w"]) / ct["w"] * 100)
                n_s += 1
                if ct["h"] and cl["h"] and (rt, rl) in vertical_ok:
                    worst_h = max(worst_h, abs(cl["h"] - ct["h"]) / ct["h"] * 100)
            # Yaw conditioning. A card's bottom edge near the projection centre
            # has almost no lever arm: at 1440x900 the mid row's bottom edge
            # sits 10 px from the vanishing line, where a single pixel of trace
            # error is 5.7 degrees. Only edges with a real lever arm carry a
            # measurable yaw signal, on either side.
            lever_ok = rt["y1"] is not None and abs(rt["y1"] - vh / 2) >= vh * 0.15
            if ct["botSlope"] is not None and cl["botSlope"] is not None and lever_ok:
                worst_yaw = max(worst_yaw, abs(cl["botSlope"] - ct["botSlope"]))
                n_y += 1
            elif ct["unclipped"] and cl["unclipped"]:
                rejected_edges += 1
    if n_c:
        check("cardCentre", "card centres", worst_c, CONTRACT["cardCentrePctOfViewport"],
              "% of viewport", f"{n_c} paired cards")
    if n_s:
        check("cardSize", "unclipped card width", worst_w, CONTRACT["cardSizePct"], "%",
              f"{n_s} unclipped cards")
        if worst_h:
            check("cardSize", "unclipped card height", worst_h, CONTRACT["cardSizePct"], "%")
    if n_y:
        check("edgeYaw", "bottom edge slope", worst_yaw, CONTRACT["edgeYawDeg"], "deg",
              f"{n_y} edges with a valid trace and a usable lever arm on both "
              f"sides, {rejected_edges} rejected (truncated trace or too close "
              f"to the vanishing line)")

    worst_gc = worst_gw = 0.0
    n_g = 0
    gutters = []
    def clean_gutters(row):
        """Gutters not adjacent to a merged region."""
        bad = [c for c in row["cards"] if c.get("merged")]
        out = []
        for g in row["gutters"]:
            if any(abs(g["c"] - c["x0"]) < 4 or abs(g["c"] - c["x1"]) < 4 for c in bad):
                continue
            out.append(g)
        return out

    for rt, rl in usable:
        for gt, gl in nearest_pairs(clean_gutters(rt), clean_gutters(rl),
                                    lambda g: g["c"], vw * 0.12):
            worst_gc = max(worst_gc, abs(gl["c"] - gt["c"]))
            worst_gw = max(worst_gw, abs(gl["w"] - gt["w"]))
            n_g += 1
            gutters.append({"row": round(rt["cy"], 1), "targetCentre": round(gt["c"], 1),
                            "localCentre": round(gl["c"], 1),
                            "dCentrePx": round(gl["c"] - gt["c"], 2),
                            "targetWidth": round(gt["w"], 1), "localWidth": round(gl["w"], 1),
                            "dWidthPx": round(gl["w"] - gt["w"], 2)})
    if n_g:
        check("gutterPx", "gutter centre", worst_gc, CONTRACT["gutterPx"], "px", f"{n_g} gutters")
        check("gutterPx", "gutter width", worst_gw, CONTRACT["gutterPx"], "px")

    def parity(row, w):
        return "centre-gutter" if any(abs(g["c"] - w / 2) < w * 0.06 for g in row["gutters"]) \
            else "centre-card"
    # A row with no resolved gutter carries no parity information; classifying
    # it as "centre-card" by default would invent a mismatch.
    parity_rows = [{"row": round(rt["cy"], 1), "target": parity(rt, vw), "local": parity(rl, vw)}
                   for rt, rl in usable if rt["gutters"] and rl["gutters"]]
    parity_unclassifiable = len(usable) - len(parity_rows)
    if parity_rows:
        mismatch = sum(1 for p in parity_rows if p["target"] != p["local"])
        check("rowParity", "row parity", mismatch, 0, "rows",
              f"{len(parity_rows)} classifiable rows, {parity_unclassifiable} without a "
              "resolved gutter: "
              + " ".join(f"{p['row']}:{p['target']}/{p['local']}" for p in parity_rows))

    t_band = any(b["y0"] <= vh / 2 <= b["y1"] for b in t["bands"])
    l_band = any(b["y0"] <= vh / 2 <= b["y1"] for b in l["bands"])
    check("centreDarkBand", "viewport centre in a horizontal gutter", l_band, t_band, "bool",
          f"target {t_band}, local {l_band}")

    ov = overlap_check(Path(entry["localPng"]).with_suffix(".json"), vw, vh)
    if ov["status"] == "NOT_MEASURED":
        item_state["overlap"] = "NOT_MEASURED"
    else:
        check("overlap", "no card overlap", len(ov["overlaps"]), 0, "pairs",
              f"{ov['cards']} on-screen cards, min separation {ov['minSeparationPx']} px")

    tv = void_stats(Path(entry["targetPng"]))
    lv = void_stats(Path(entry["localPng"]))
    excess = (lv["largestBlobFraction"] - tv["largestBlobFraction"]) * 100
    check("largeVoid", "largest void blob excess", max(0.0, excess),
          CONTRACT["largeVoidExcessPctOfFrame"], "% of frame",
          f"target {tv['largestBlobFraction']*100:.2f}%, local {lv['largestBlobFraction']*100:.2f}%")

    t_bands = [b["c"] for b in t["bands"] if not b["edge"]]
    l_bands = [b["c"] for b in l["bands"] if not b["edge"]]
    matched = nearest_pairs([{"c": c} for c in t_bands], [{"c": c} for c in l_bands],
                            lambda x: x["c"], vh * 0.08)
    aux = {
        "targetRowBands": [round(x, 1) for x in t_bands],
        "localRowBands": [round(x, 1) for x in l_bands],
        "missingRowBands": len(t_bands) - len(matched),
        "inventedRowBands": len(l_bands) - len(matched),
        "worstRowBandCentrePx": round(max((abs(a["c"] - b["c"]) for a, b in matched), default=0.0), 2),
        "targetRowHeights": [round(r["y1"] - r["y0"] + 1, 1) for r in t["rows"] if not r["clipped"]],
        "localRowHeights": [round(r["y1"] - r["y0"] + 1, 1) for r in l["rows"] if not r["clipped"]],
        "voidFraction": {"target": round(tv["voidFraction"], 4), "local": round(lv["voidFraction"], 4)},
        "edgeTracesRejected": rejected_edges,
        "rowsUsableForVerticalGeometry": len(vertical_ok),
        "rowsPaired": len(usable),
        "sliverRowsExcluded": slivers_excluded,
        "mergedRegionsExcluded": merged_excluded,
        "asymmetricRowsExcluded": asymmetric_excluded,
        "parityRowsUnclassifiable": parity_unclassifiable,
        "note": "Auxiliary. Never changes the verdict and never excuses a contract failure.",
    }

    verdict = "PASS" if all(c["pass"] for c in checks) else "FAIL"
    return {"id": entry["id"], "viewport": [vw, vh], "verdict": verdict,
            "contractCoverage": item_state, "checks": checks,
            "gutters": gutters, "cards": detail_cards, "rowParity": parity_rows,
            "overlap": ov, "auxiliaryFindings": aux}


if __name__ == "__main__":
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    pairs = json.loads(Path(args["--pairs"]).read_text())
    out = Path(args.get("--out", "qa-v5/f2"))
    out.mkdir(parents=True, exist_ok=True)
    results = [compare(p) for p in pairs]

    f0_path = Path(args.get("--f0", "qa-v5/f0/gate.json"))
    if f0_path.exists():
        f0 = json.loads(f0_path.read_text())
        f0_state = "PASS" if f0.get("verdict") == "PASS" else "FAIL"
        f0_detail = {"verdict": f0.get("verdict"), "checks": len(f0.get("checks", [])),
                     "passed": sum(1 for c in f0.get("checks", []) if c["pass"]),
                     "source": str(f0_path)}
    else:
        f0_state, f0_detail = "NOT_MEASURED", {"reason": f"{f0_path} missing"}
    for r in results:
        r["contractCoverage"]["f0Regression"] = f0_state

    coverage = {}
    for k in ITEMS:
        states = [r["contractCoverage"][k] for r in results]
        coverage[k] = "FAIL" if "FAIL" in states else ("NOT_MEASURED" if "NOT_MEASURED" in states else "PASS")
    overall = "PASS" if all(v == "PASS" for v in coverage.values()) else "FAIL"

    payload = {"contract": CONTRACT, "verdict": overall, "contractCoverage": coverage,
               "f0Regression": f0_detail, "viewports": results}
    (out / "gate.json").write_text(json.dumps(payload, indent=2))
    print(f"F2 GATE: {overall}")
    print("  contractCoverage: " + json.dumps(coverage))
    for r in results:
        print(f"  {r['id']:<12} {int(r['viewport'][0])}x{int(r['viewport'][1])}  {r['verdict']}")
        for c in r["checks"]:
            print(f"      [{'PASS' if c['pass'] else 'FAIL'}] {c['check']:<38} "
                  f"{c['value']!s:>8} {c['unit']:<14} (limit {c['limit']})  {c['detail']}")
        a = r["auxiliaryFindings"]
        print(f"      (aux) rowBands t={len(a['targetRowBands'])} l={len(a['localRowBands'])} "
              f"missing={a['missingRowBands']} invented={a['inventedRowBands']} "
              f"tRowH={a['targetRowHeights']} lRowH={a['localRowHeights']}")
    sys.exit(0 if overall == "PASS" else 1)
