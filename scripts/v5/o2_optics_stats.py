#!/usr/bin/env python3
"""O2 metric module: every band statistic the O2 gates read.

Reuses the O0 machinery (card rects from the python layout twin, the o0
edge/interior bands) and adds the System B measurands:

  side_bands      bw-split only: the LEFT edge band sits over black media,
                  the RIGHT over white -- per-side edge luma/chroma is the
                  luminance-(in)dependence measurement in its purest form.
  ringing         edge chroma on an achromatic asset IS shader-introduced
                  colour; nothing else can put chroma there.
  reflection_band dark-side inward luminance profile: how wide the bright
                  band the glass paints over BLACK media is (px, and
                  normalised to card width).
  highlight_centroid  centroid of bright low-chroma pixels per card --
                  the pointer-reflection-path measurand.

All statistics are over the SAME twin card rects on every lane; media is
identical by the shared-media harness, so these are same-media numbers.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


O0 = _load("o0_optics_report_o2", "o0-optics-report.py")
VC = sys.modules["v0_culling"]
SL = sys.modules["source_layout"]

card_rects = O0.card_rects
stats = O0.stats


def rects_at(w, h, pointer_ndc=(0.0, 0.0), scroll=(0.0, 0.0)):
    """Twin card rects at ANY pointer/scroll (o0 card_rects generalised)."""
    frame = SL.layout(w, h)
    cam = VC.coverage_camera(pointer_ndc[0], pointer_ndc[1], frame)
    pred = VC.frame_verdicts(scroll[0], scroll[1], cam, frame)
    rects = []
    for code, v in pred.items():
        if not v["draw"] or not v["aabb"] or not all(v["quad"]):
            continue
        x0, y0, x1, y1 = v["aabb"]
        if x0 < 2 or y0 < 2 or x1 > w - 2 or y1 > h - 2:
            continue
        rects.append((code, (int(x0), int(y0), int(x1), int(y1))))
    return rects


def _lum(p):
    return 0.2126 * p[..., 0] + 0.7152 * p[..., 1] + 0.0722 * p[..., 2]


def side_bands(img, rects):
    """Per-side edge bands (outer 8% width, central 60% height)."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    L, R = [], []
    for (x0, y0, x1, y1) in rects:
        cw, ch = x1 - x0, y1 - y0
        yb0, yb1 = y0 + int(ch * 0.2), y1 - int(ch * 0.2)
        L.append(a[yb0:yb1, x0:x0 + int(cw * 0.08)].reshape(-1, 3))
        R.append(a[yb0:yb1, x1 - int(cw * 0.08):x1].reshape(-1, 3))
    L, R = np.concatenate(L), np.concatenate(R)
    ch = lambda p: float((p.max(axis=1) - p.min(axis=1)).mean())
    return {
        "darkSideEdgeLuma": round(float(_lum(L).mean()), 1),
        "brightSideEdgeLuma": round(float(_lum(R).mean()), 1),
        "darkOverBrightLumaRatio": round(float(_lum(L).mean() / max(1.0, _lum(R).mean())), 4),
        "darkSideEdgeChroma": round(ch(L), 2),
        "brightSideEdgeChroma": round(ch(R), 2),
        "sideChromaGap": round(abs(ch(L) - ch(R)), 2),
    }


def reflection_band(img, rects, media_luma=16.0, threshold=60.0):
    """bw-split dark side: per card, scan inward from the LEFT card edge at
    mid-height rows; band width = consecutive px with luma > threshold
    before the profile falls to media black. Returns mean px + normalised."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    widths, norms = [], []
    for (x0, y0, x1, y1) in rects:
        cw, ch = x1 - x0, y1 - y0
        mid0, mid1 = y0 + int(ch * 0.42), y0 + int(ch * 0.58)
        prof = _lum(a[mid0:mid1, x0:x0 + int(cw * 0.4)]).mean(axis=0)
        wpx = 0
        started = False
        for v in prof:
            if v > threshold:
                started = True
                wpx += 1
            elif started:
                break
        widths.append(wpx)
        norms.append(wpx / cw)
    return {"meanPx": round(float(np.mean(widths)), 1),
            "meanNormToCardWidth": round(float(np.mean(norms)), 4),
            "perCard": widths, "threshold": threshold}


def highlight_centroid(img, rect, luma_min=200.0, chroma_max=40.0):
    """Centroid of bright, unsaturated pixels inside one card (normalised
    to the card rect). None when fewer than 50 px qualify."""
    x0, y0, x1, y1 = rect
    a = np.asarray(img.convert("RGB"), dtype=np.float32)[y0:y1, x0:x1]
    lum = _lum(a)
    chroma = a.max(axis=2) - a.min(axis=2)
    mask = (lum > luma_min) & (chroma < chroma_max)
    ys, xs = np.nonzero(mask)
    if len(xs) < 50:
        return None
    return {"nx": round(float(xs.mean()) / (x1 - x0), 4),
            "ny": round(float(ys.mean()) / (y1 - y0), 4),
            "pixels": int(len(xs))}


def interior_stats(img, rects):
    """Interior (middle 55%) saturation and luminance -- the centre-
    unchanged measurand."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    px = []
    for (x0, y0, x1, y1) in rects:
        cw, ch = x1 - x0, y1 - y0
        px.append(a[y0 + int(ch * .225):y1 - int(ch * .225),
                    x0 + int(cw * .225):x1 - int(cw * .225)].reshape(-1, 3))
    p = np.concatenate(px)
    c = p.max(axis=1) - p.min(axis=1)
    mx = np.maximum(p.max(axis=1), 1e-3)
    return {"interiorSaturationMean": round(float((c / mx).mean()), 4),
            "interiorLuminanceMean": round(float(_lum(p).mean()), 2),
            "interiorChromaMean": round(float(c.mean()), 2)}
