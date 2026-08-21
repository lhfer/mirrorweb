#!/usr/bin/env python3
"""O0 runtime half: ROI statistics on the Target and candidate captures.

Card rectangles come from the SAME python layout/culling twin on both lanes
(scroll 0, the state's pointer orbit) -- the geometry was proven identical
to the Target slot-for-slot in V0, so the bands land on the same cards on
both pages. Media differs between the pages, so every number is a
DISTRIBUTION statistic, never a pixel match.

Per analysed card (front-facing, fully inside the strict viewport):
  edge band   the outer ring of the projected AABB (bevel territory)
  interior    the AABB shrunk to its middle 55%
  gutter      the strips between adjacent card AABBs

Metrics:
  edgeChromaMean/P95      chroma = max(RGB)-min(RGB) in the edge band
  fringeRB                mean |R-B| in the edge band (cyan/magenta axis)
  whiteReflectionRatio    edge-band pixels bright AND unsaturated
  edgeLuminanceMean       edge-band mean luma
  interiorSaturationMean  HSV S over the interior
  gutterInkRatio          gutter pixels brighter than the background could be
  fringeWidthPx           mean run of chroma>40 crossing the vertical edges

Merges the forensics JSON (--forensics) and writes the full O0 diagnosis.

Usage: o0-optics-report.py --dir=<captures> --forensics=<json> --out=<json>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

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

POINTER = {"rest": (0.0, 0.0), "pointer-corner-br": (1.0, 1.0)}


def card_rects(w, h, state):
    """Projected AABBs of DRAWN, front-facing, fully-on-screen cards."""
    frame = SL.layout(w, h)
    px, py = POINTER[state]
    cam = VC.coverage_camera(px, py, frame)
    pred = VC.frame_verdicts(0.0, 0.0, cam, frame)
    rects = []
    for c, v in pred.items():
        if not v["draw"] or not v["aabb"] or not all(v["quad"]):
            continue
        x0, y0, x1, y1 = v["aabb"]
        if x0 < 2 or y0 < 2 or x1 > w - 2 or y1 > h - 2:
            continue
        rects.append((int(x0), int(y0), int(x1), int(y1)))
    return rects


def stats(img, rects, w, h):
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    edge_px = []
    interior_px = []
    fringe_widths = []
    card_mask = np.zeros(a.shape[:2], dtype=bool)
    for (x0, y0, x1, y1) in rects:
        cw, ch = x1 - x0, y1 - y0
        card_mask[y0:y1, x0:x1] = True
        ix0, iy0 = x0 + int(cw * 0.225), y0 + int(ch * 0.225)
        ix1, iy1 = x1 - int(cw * 0.225), y1 - int(ch * 0.225)
        band = np.ones((ch, cw), dtype=bool)
        bx = int(cw * 0.15)
        by = int(ch * 0.15)
        band[by:ch - by, bx:cw - bx] = False
        roi = a[y0:y1, x0:x1]
        edge_px.append(roi[band])
        interior_px.append(a[iy0:iy1, ix0:ix1].reshape(-1, 3))
        # fringe width: chroma runs crossing the left and right edges
        mid = (y0 + y1) // 2
        for rows in range(mid - int(ch * 0.2), mid + int(ch * 0.2), max(1, ch // 10)):
            for ex in (x0, x1):
                lo, hi = max(0, ex - 22), min(w, ex + 22)
                strip = a[rows, lo:hi]
                chroma = strip.max(axis=1) - strip.min(axis=1)
                fringe_widths.append(int((chroma > 40).sum()))
    edge = np.concatenate(edge_px) if edge_px else np.zeros((0, 3))
    inter = np.concatenate(interior_px) if interior_px else np.zeros((0, 3))

    def chroma(p):
        return p.max(axis=1) - p.min(axis=1)

    def sat(p):
        mx = p.max(axis=1)
        c = chroma(p)
        return np.where(mx > 1e-3, c / np.maximum(mx, 1e-3), 0)

    ec = chroma(edge)
    white = ((edge.min(axis=1) > 180).sum() / max(1, len(edge)))
    # gutter: everything NOT card and not within 4px of one, minus the page
    # margin -- restricted to the bounding box of the analysed cards
    if rects:
        gx0 = min(r[0] for r in rects); gy0 = min(r[1] for r in rects)
        gx1 = max(r[2] for r in rects); gy1 = max(r[3] for r in rects)
        sub = a[gy0:gy1, gx0:gx1]
        subm = card_mask[gy0:gy1, gx0:gx1]
        grow = np.zeros_like(subm)
        grow[4:-4, 4:-4] = subm[4:-4, 4:-4]
        for s in (subm[8:, :], subm[:-8, :]):
            pass
        gutter = sub[~subm]
        # the background is a navy->black gradient; luma above 80 in the
        # gutter is ink that does not belong there
        gl = 0.2126 * gutter[:, 0] + 0.7152 * gutter[:, 1] + 0.0722 * gutter[:, 2]
        gutter_ratio = float((gl > 80).sum() / max(1, len(gl)))
    else:
        gutter_ratio = None
    lum = 0.2126 * edge[:, 0] + 0.7152 * edge[:, 1] + 0.0722 * edge[:, 2]
    return {
        "cardsAnalysed": len(rects),
        "edgeChromaMean": round(float(ec.mean()), 2) if len(ec) else None,
        "edgeChromaP95": round(float(np.percentile(ec, 95)), 2) if len(ec) else None,
        "fringeRB": round(float(np.abs(edge[:, 0] - edge[:, 2]).mean()), 2) if len(edge) else None,
        "whiteReflectionRatio": round(float(white), 4),
        "edgeLuminanceMean": round(float(lum.mean()), 2) if len(lum) else None,
        "interiorSaturationMean": round(float(sat(inter).mean()), 4) if len(inter) else None,
        "interiorLuminanceMean": round(float((0.2126 * inter[:, 0] + 0.7152 * inter[:, 1]
                                              + 0.0722 * inter[:, 2]).mean()), 2) if len(inter) else None,
        "gutterInkRatio": gutter_ratio,
        "fringeWidthPxMean": round(float(np.mean(fringe_widths)), 2) if fringe_widths else None,
    }


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    d = Path(args["dir"])
    index = json.loads((d / "index.json").read_text())
    forensics = json.loads(Path(args["forensics"]).read_text())

    runtime = {}
    for s in index["shots"]:
        w, h = map(int, s["vp"].split("x"))
        img = Image.open(s["file"])
        rects = card_rects(w, h, s["state"])
        runtime.setdefault(f"{s['vp']}/{s['state']}", {})[s["lane"]] = stats(img, rects, w, h)

    # candidate interior saturation shift vs its own media-only control
    shifts = {}
    for key, lanes in runtime.items():
        b = lanes.get("candidate-beauty")
        m = lanes.get("candidate-media-only")
        if b and m and b["interiorSaturationMean"] and m["interiorSaturationMean"]:
            shifts[key] = {
                "beautyOverMediaOnlySaturation":
                    round(b["interiorSaturationMean"] / m["interiorSaturationMean"], 3),
                "beautyOverMediaOnlyLuminance":
                    round(b["interiorLuminanceMean"] / m["interiorLuminanceMean"], 3),
            }

    doc = {
        **forensics,
        "what": "O0 optics source diagnosis: the Target's complete glass "
                "shader byte-anchored (sites), plus runtime ROI statistics "
                "on both pages (runtime). Media differs between the pages, "
                "so runtime numbers are distribution statistics, never pixel "
                "matches.",
        "runtime": runtime,
        "candidateInteriorShiftVsOwnMediaOnly": shifts,
        "runtimeMethod": {
            "cardRects": "projected AABBs from the SAME layout/culling twin "
                         "on both lanes (proven slot-identical in V0), "
                         "front-facing fully-on-screen cards only",
            "edgeBand": "outer 15% ring of the AABB",
            "interior": "middle 55% of the AABB",
            "chroma": "max(RGB)-min(RGB); fringeRB = mean |R-B| (the "
                      "cyan/magenta axis); white = min(RGB) > 180",
            "gutter": "non-card pixels between analysed cards; ink = "
                      "luma > 80 over the navy-black gradient",
            "confidence": "RUNTIME_MEASURED",
        },
    }
    Path(args["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["out"]).write_text(json.dumps(doc, indent=1) + "\n")
    for key, lanes in runtime.items():
        t = lanes.get("target", {})
        c = lanes.get("candidate-beauty", {})
        print(f"{key}: edge chroma {t.get('edgeChromaMean')} vs {c.get('edgeChromaMean')}, "
              f"fringeRB {t.get('fringeRB')} vs {c.get('fringeRB')}, "
              f"white {t.get('whiteReflectionRatio')} vs {c.get('whiteReflectionRatio')}, "
              f"interior sat {t.get('interiorSaturationMean')} vs {c.get('interiorSaturationMean')}, "
              f"gutter {t.get('gutterInkRatio')} vs {c.get('gutterInkRatio')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
