"""
The Target's own layout algorithm, transcribed from its shipped bundle.

Stage F2.7 authorised one read-only source forensics pass. It found the whole
initialisation, so this file replaces regression guessing with arithmetic. Every
constant below is the Target's, read from its grid config object; every formula
is its own, re-expressed in Python. See docs/v5/TARGET_RESPONSIVE_SOURCE_FORENSICS.md
for the bundle URL and SHA-256 this was read from.

Nothing here is fitted. If a number disagrees with a Target frame, this file is
wrong, not the frame.
"""
from __future__ import annotations

import math

# The Target's grid configuration, read from the single source contract rather
# than copied. A second hand-written copy drifts silently; this one cannot.
import importlib.util as _ilu
from pathlib import Path as _Path

_spec = _ilu.spec_from_file_location("source_layout", _Path(__file__).resolve().parent / "source_layout.py")
_SL = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_SL)
CFG = dict(_SL.GRID)


def _edge(arc: float, half: float, persp: float, radius: float) -> float:
    """
    Screen position of a card's near edge at arc distance `arc` along the sphere.

    The card centre sits at R*sin(arc/R) laterally and R*(1-cos(arc/R)) further
    from the camera; both are divided by the same perspective denominator.
    """
    denom = persp + radius * (1 - math.cos(arc / radius))
    return radius * persp * math.sin(arc / radius) / denom - half * persp / denom


def _arc_to_cover(target: float, half: float, persp: float, radius: float) -> float:
    """Smallest arc length whose card edge still reaches `target` on screen."""
    horizon = radius * math.acos(radius / (persp + radius))
    if _edge(horizon, half, persp, radius) < target:
        return horizon
    lo, hi = 0.0, horizon
    for _ in range(24):
        mid = (lo + hi) * 0.5
        if _edge(mid, half, persp, radius) < target:
            lo = mid
        else:
            hi = mid
    return hi


def _even(value: float, lo: int, hi: int) -> int:
    """Clamp to [lo, hi] and force EVEN. Even counts are what put the viewport
    centre between two cells instead of on one."""
    n = min(hi, max(lo, math.ceil(value)))
    if n % 2 == 0:
        return n
    if n + 1 <= hi:
        return n + 1
    if n - 1 >= lo:
        return n - 1
    return n


def layout(width: float, height: float, cfg: dict = CFG, gap: float | None = None) -> dict:
    """The Target's layout for a viewport. Pure function of (width, height)."""
    g = cfg["gapRatio"] if gap is None else gap
    w = max(width, 1.0)
    h = max(height, 1.0)
    s = max(w, h) / cfg["referenceWidth"]
    persp = cfg["perspective"] * s
    radius = cfg["sphereRadius"] * s
    ratio = cfg["planeWidthRatioPortrait"] if h > w else cfg["planeWidthRatio"]
    plane_w = w * ratio
    plane_h = plane_w / cfg["planeAspect"]
    cell_w = plane_w * (1 + g)
    cell_h = plane_h * (1 + g)
    zoom_z = 0.1 * persp
    cover_x = 0.5 * w * cfg["coverageMargin"] + math.tan(0.05) * persp + zoom_z
    cover_y = 0.5 * h * cfg["coverageMargin"] + math.tan(0.05) * persp + zoom_z
    arc_x = _arc_to_cover(cover_x, 0.5 * plane_w, persp, radius)
    arc_y = _arc_to_cover(cover_y, 0.5 * plane_h, persp, radius)
    cols = _even(2 * arc_x / cell_w + 4, cfg["minCols"], cfg["maxCols"])
    rows = _even(2 * arc_y / cell_h + 4, cfg["minRows"], cfg["maxRows"])
    return {
        "cols": cols, "rows": rows, "perspective": persp, "sphereRadius": radius,
        "planeWidth": plane_w, "planeHeight": plane_h,
        "cellW": cell_w, "cellH": cell_h,
        "periodX": cols * cell_w, "periodY": rows * cell_h,
        "cardScale": plane_w / max(cfg["referenceWidth"] * cfg["planeWidthRatio"], 1.0),
        "maxZoomZ": zoom_z,
        "portrait": h > w,
    }


def wrap(value: float, period: float) -> float:
    """Symmetric modulo: the Target's own infinite-grid wrap, into [-P/2, P/2)."""
    half = 0.5 * period
    return ((value + half) % period + period) % period - half


def place(slot: int, scroll_x: float, scroll_y: float, lay: dict) -> dict:
    """
    World pose of one pool slot, exactly as the Target computes it.

    Slot index runs row-major over cols*rows. Odd POOL rows carry the half-cell
    brick offset -- which is why the visible phase is a property of the pool's
    row count, not of the viewport's aspect ratio.
    """
    cols, rows = lay["cols"], lay["rows"]
    R = lay["sphereRadius"]
    r = slot // cols
    i = r - (rows - 1) / 2
    brick = (r % 2) * lay["cellW"] * 0.5
    x_arc = wrap((slot % cols - (cols - 1) / 2) * lay["cellW"] + scroll_x + brick, lay["periodX"])
    y_arc = wrap(-i * lay["cellH"] - scroll_y, lay["periodY"])
    tx, ty = x_arc / R, y_arc / R
    cy = math.cos(ty)
    ux, uy, uz = math.sin(tx) * cy, math.sin(ty), math.cos(tx) * cy
    return {"slot": slot, "poolRow": r, "poolCol": slot % cols,
            "xArc": x_arc, "yArc": y_arc,
            "x": ux * R, "y": uy * R, "z": uz * R - R,
            "code": slot + 1}


def centre_row_phase(width: float, height: float) -> dict:
    """
    Which phase the row just below the viewport centre takes.

    Row counts are forced EVEN, so the centred row index is a half-integer and
    the two rows nearest the centre are pool rows rows/2 - 1 and rows/2. The
    lower one carries the brick offset exactly when rows/2 is odd. That single
    parity is the whole phase law: no aspect threshold, no breakpoint.
    """
    lay = layout(width, height)
    below = lay["rows"] // 2
    # Even pool rows take no brick offset, and with an EVEN column count that
    # leaves their cards on half-integer multiples of cellW -- a gutter on the
    # centre line. Odd pool rows take the half-cell offset, which lands them on
    # integers and puts a card on the centre line.
    card_centred = below % 2 == 1
    # Our own grid has restY0 = -cellH/2, so row j = 0 is the one just below the
    # centre, it is even, and it is card-centred with no offset. We therefore
    # need the half-cell shift exactly when the Target's lower row is NOT.
    return {
        "rows": lay["rows"], "cols": lay["cols"],
        "poolRowBelowCentre": below,
        "centreOfLowerRowIsCard": card_centred,
        "halfCellPhase": not card_centred,
    }
