#!/usr/bin/env python3
"""VC2 §五 -- the derivation shared by preregistration and comparison.

One derivation, applied to whatever run is handed to it. Nothing in here knows
which page it is reading, so a Target run and a Candidate run cannot be
measured by two subtly different pieces of code.

Per frame, per tracked card, the recorder stored two things: the sixteen
numbers of the card's CSS3D matrix and the browser's own projected screen rect.
Everything §五 asks for is derived from those:

  centre            rect centre, in CSS px
  projected size    rect width/height -- what the dolly actually changes
  matrix scale      basis-column lengths of the matrix3d
  rotation          screen-plane angle of the first basis column
  depth             the matrix's translateZ
  neighbours        nearest in-row / in-column card inside the tracked block
  gutters           edge-to-edge gap to those neighbours
  row stagger       horizontal phase difference between adjacent rows
  centre distance   distance from the viewport centre

Trajectories are UNWRAPPED before any cross-page comparison: when a card's
occupant rotates it jumps by a full grid period, and a wrap that lands one
frame apart on the two pages would otherwise show up as a metre-sized
trajectory error that no viewer could see. The wrap events themselves are
reported separately, which is where wrap continuity is actually judged.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

FRAME_MS = 1000.0 / 60.0


def load_run(p: Path) -> dict:
    d = json.loads(Path(p).read_text())
    frames = d["frames"]
    n_cards = len(d["tracked"])
    t = np.array([f[0] for f in frames], dtype=float)
    vw = np.array([f[1] for f in frames], dtype=float)
    vh = np.array([f[2] for f in frames], dtype=float)
    rect = np.full((len(frames), n_cards, 4), np.nan)
    mat = np.full((len(frames), n_cards, 16), np.nan)
    hid = np.zeros((len(frames), n_cards), dtype=bool)
    for fi, f in enumerate(frames):
        for rank, hidden, m, r in f[3]:
            if rank >= n_cards:
                continue
            hid[fi, rank] = bool(hidden)
            if r:
                rect[fi, rank] = r
            if m:
                mat[fi, rank] = m
    return {"meta": {k: v for k, v in d.items() if k != "frames"},
            "t": t, "vw": vw, "vh": vh, "rect": rect, "mat": mat, "hidden": hid}


def derive(run: dict) -> dict:
    """Per-frame geometry for one run."""
    rect, mat, hid = run["rect"], run["mat"], run["hidden"]
    cx = rect[:, :, 0] + rect[:, :, 2] / 2.0
    cy = rect[:, :, 1] + rect[:, :, 3] / 2.0
    w, h = rect[:, :, 2], rect[:, :, 3]
    # A hidden card's transform is stale on BOTH pages -- neither keeps writing
    # a culled card. Those samples are dropped rather than compared.
    off = hid | ~np.isfinite(cx) | (w <= 1)
    cx = np.where(off, np.nan, cx)
    cy = np.where(off, np.nan, cy)
    w = np.where(off, np.nan, w)
    h = np.where(off, np.nan, h)

    scale_x = np.linalg.norm(mat[:, :, 0:3], axis=2)
    scale_y = np.linalg.norm(mat[:, :, 4:7], axis=2)
    rot = np.degrees(np.arctan2(mat[:, :, 1], mat[:, :, 0]))
    depth = mat[:, :, 14]

    vcx = run["vw"][:, None] / 2.0
    vcy = run["vh"][:, None] / 2.0
    dist_centre = np.hypot(cx - vcx, cy - vcy)

    # Grid pitch from the first fully visible frame: the median horizontal gap
    # between distinct card centres in the tracked block.
    pitch = np.nan
    for fi in range(cx.shape[0]):
        xs = np.sort(cx[fi][np.isfinite(cx[fi])])
        if xs.size >= 3:
            d = np.diff(xs)
            d = d[d > 1.0]
            if d.size:
                pitch = float(np.median(d))
                break

    return {"cx": cx, "cy": cy, "w": w, "h": h, "scaleX": scale_x, "scaleY": scale_y,
            "rot": rot, "depth": depth, "distCentre": dist_centre, "pitch": pitch,
            "t": run["t"], "vw": run["vw"], "vh": run["vh"], "off": off}


def unwrap(series: np.ndarray, jump: float) -> tuple[np.ndarray, list]:
    """Remove occupant-rotation discontinuities; report where they were."""
    out = series.copy()
    events = []
    for c in range(series.shape[1]):
        acc = 0.0
        last = np.nan
        for i in range(series.shape[0]):
            v = series[i, c]
            if not math.isfinite(v):
                out[i, c] = np.nan
                continue
            if math.isfinite(last):
                d = v - last
                if abs(d) > jump:
                    acc -= d
                    events.append({"card": int(c), "frame": int(i), "deltaPx": round(float(d), 2)})
            last = v
            out[i, c] = v + acc
    return out, events


def gutters(g: dict) -> dict:
    """Per-frame nearest-neighbour gaps and the stagger between adjacent rows."""
    cx, cy, w, h = g["cx"], g["cy"], g["w"], g["h"]
    n_f, n_c = cx.shape
    hg = np.full(n_f, np.nan)
    vg = np.full(n_f, np.nan)
    stag = np.full(n_f, np.nan)
    for fi in range(n_f):
        x, y = cx[fi], cy[fi]
        ww, hh = w[fi], h[fi]
        ok = np.isfinite(x) & np.isfinite(y)
        if ok.sum() < 3:
            continue
        idx = np.where(ok)[0]
        row_tol = float(np.nanmedian(hh[ok])) * 0.5
        col_tol = float(np.nanmedian(ww[ok])) * 0.5
        hgs, vgs = [], []
        for i in idx:
            same_row = [j for j in idx if j != i and abs(y[j] - y[i]) < row_tol]
            if same_row:
                j = min(same_row, key=lambda k: abs(x[k] - x[i]))
                hgs.append(abs(x[j] - x[i]) - (ww[i] + ww[j]) / 2.0)
            same_col = [j for j in idx if j != i and abs(x[j] - x[i]) < col_tol]
            if same_col:
                j = min(same_col, key=lambda k: abs(y[k] - y[i]))
                vgs.append(abs(y[j] - y[i]) - (hh[i] + hh[j]) / 2.0)
        if hgs:
            hg[fi] = float(np.median(hgs))
        if vgs:
            vg[fi] = float(np.median(vgs))
        # Row stagger: cluster into rows by y, take each row's mean x, and read
        # the phase difference between the two most populated adjacent rows.
        order = idx[np.argsort(y[idx])]
        rows, cur = [], [order[0]]
        for k in order[1:]:
            if abs(y[k] - y[cur[-1]]) < row_tol:
                cur.append(k)
            else:
                rows.append(cur)
                cur = [k]
        rows.append(cur)
        rows = [r for r in rows if len(r) >= 2]
        if len(rows) >= 2:
            a, b = rows[0], rows[1]
            stag[fi] = float(np.mean(x[b]) - np.mean(x[a]))
    return {"hGutter": hg, "vGutter": vg, "rowStagger": stag}


def resample(t: np.ndarray, y: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Linear resample onto a common time grid; NaN gaps stay NaN."""
    out = np.full((grid.size,) + y.shape[1:], np.nan)
    if y.ndim == 1:
        good = np.isfinite(y)
        if good.sum() >= 2:
            out = np.interp(grid, t[good], y[good], left=np.nan, right=np.nan)
        return out
    for c in range(y.shape[1]):
        good = np.isfinite(y[:, c])
        if good.sum() >= 2:
            out[:, c] = np.interp(grid, t[good], y[good, c], left=np.nan, right=np.nan)
    return out


def stats(d: np.ndarray) -> dict:
    v = d[np.isfinite(d)]
    if v.size == 0:
        return {"n": 0, "median": None, "p95": None, "max": None, "mean": None}
    return {"n": int(v.size), "median": round(float(np.median(v)), 3),
            "p95": round(float(np.percentile(v, 95)), 3),
            "max": round(float(v.max()), 3), "mean": round(float(v.mean()), 3)}


def series_of(path: Path) -> dict:
    """Everything a comparison needs from one recorded run."""
    run = load_run(path)
    g = derive(run)
    pitch = g["pitch"] if math.isfinite(g["pitch"]) else 300.0
    ux, wrap_x = unwrap(g["cx"], pitch * 0.6)
    uy, wrap_y = unwrap(g["cy"], pitch * 0.6)
    gut = gutters(g)
    # Frame-to-frame centre jump AFTER unwrapping: a real visual discontinuity
    # (a pop) survives unwrapping; an occupant rotation does not.
    step = np.hypot(np.diff(ux, axis=0), np.diff(uy, axis=0))
    return {
        "meta": run["meta"], "t": g["t"], "pitch": pitch,
        "cx": ux, "cy": uy, "rawCx": g["cx"], "w": g["w"], "h": g["h"],
        "scaleX": g["scaleX"], "rot": g["rot"], "depth": g["depth"],
        "distCentre": g["distCentre"],
        "hGutter": gut["hGutter"], "vGutter": gut["vGutter"], "rowStagger": gut["rowStagger"],
        "wrapEvents": wrap_x + wrap_y, "stepPx": step,
        "fps": round(float(len(g["t"]) / max(g["t"][-1] / 1000.0, 1e-6)), 2) if g["t"].size else 0,
    }


COMPARED = [
    ("centreX", "cx", "px", "single-card centre trajectory, horizontal"),
    ("centreY", "cy", "px", "single-card centre trajectory, vertical"),
    ("projectedWidth", "w", "px", "projected card width -- the dolly observable"),
    ("projectedHeight", "h", "px", "projected card height"),
    ("hGutter", "hGutter", "px", "edge-to-edge gap to the horizontal neighbour"),
    ("vGutter", "vGutter", "px", "edge-to-edge gap to the vertical neighbour"),
    ("rowStagger", "rowStagger", "px", "horizontal phase between adjacent rows"),
    ("rotation", "rot", "deg", "screen-plane rotation of the card basis"),
]


def compare(a: dict, b: dict) -> dict:
    """a vs b on a common time grid. Both must be the same scenario."""
    if not (a["t"].size and b["t"].size):
        return {"gridFrames": 0, "gridSpanMs": 0.0, "rows": {}}
    # The grid starts at the LATER of the two first samples: below that, one
    # side has nothing recorded and every resampled value would be NaN.
    t0 = max(a["t"][0], b["t"][0])
    t_end = min(a["t"][-1], b["t"][-1])
    grid = np.arange(t0, t_end, FRAME_MS)
    out = {"gridFrames": int(grid.size), "gridSpanMs": round(float(t_end - t0), 1),
           "fps": {"a": a["fps"], "b": b["fps"]}, "rows": {}}
    for name, key, unit, why in COMPARED:
        ra = resample(a["t"], a[key], grid)
        rb = resample(b["t"], b[key], grid)
        d = np.abs(ra - rb)
        row = {"unit": unit, "what": why, "delta": stats(d)}
        # Rest-frame value on each side, so a constant offset is legible.
        for side, r in (("a", ra), ("b", rb)):
            v = r[0] if r.ndim == 1 else r[0][np.isfinite(r[0])]
            row[f"{side}AtRest"] = (round(float(v), 3) if np.ndim(v) == 0 and np.isfinite(v)
                                    else (None if np.ndim(v) == 0 or v.size == 0
                                          else [round(float(x), 2) for x in v[:4]]))
        out["rows"][name] = row
    # Dolly: projected width relative to that card's own rest width.
    for side, s in (("a", a), ("b", b)):
        w0 = np.nanmedian(s["w"][:3], axis=0)
        rel = s["w"] / w0[None, :]
        out.setdefault("dolly", {})[side] = {
            "maxScale": round(float(np.nanmax(rel)), 4),
            "minScale": round(float(np.nanmin(rel)), 4),
            "excursion": round(float(np.nanmax(rel) - np.nanmin(rel)), 4),
        }
    out["dolly"]["excursionDelta"] = round(
        abs(out["dolly"]["a"]["excursion"] - out["dolly"]["b"]["excursion"]), 4)
    out["wrap"] = {
        "a": {"events": len(a["wrapEvents"]), "maxStepPx": round(float(np.nanmax(a["stepPx"])), 2)
              if np.isfinite(a["stepPx"]).any() else None},
        "b": {"events": len(b["wrapEvents"]), "maxStepPx": round(float(np.nanmax(b["stepPx"])), 2)
              if np.isfinite(b["stepPx"]).any() else None},
    }
    return out
