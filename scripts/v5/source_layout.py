"""
The Target's layout, in Python, reading the SAME contract the TypeScript reads.

config/target-layout-source-v2.json is the single source of every constant.
This module holds none of its own. `npm run v5:target-layout-source` proves this
module, src/layout/SourceExactLayout.ts and the live Target DOM all agree.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "config" / "target-layout-source-v2.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text())
GRID = CONTRACT["grid"]
CAMERA = CONTRACT["camera"]
REFERENCE_PLANE_WIDTH = GRID["referenceWidth"] * GRID["planeWidthRatio"]


def _edge_at(arc: float, half: float, persp: float, radius: float) -> float:
    denom = persp + radius * (1 - math.cos(arc / radius))
    return radius * persp * math.sin(arc / radius) / denom - half * persp / denom


def _arc_to_cover(target: float, half: float, persp: float, radius: float) -> float:
    horizon = radius * math.acos(radius / (persp + radius))
    if _edge_at(horizon, half, persp, radius) < target:
        return horizon
    lo, hi = 0.0, horizon
    for _ in range(24):
        mid = (lo + hi) * 0.5
        if _edge_at(mid, half, persp, radius) < target:
            lo = mid
        else:
            hi = mid
    return hi


def _force_even(value: float, lo: int, hi: int) -> int:
    n = min(hi, max(lo, math.ceil(value)))
    if n % 2 == 0:
        return n
    if n + 1 <= hi:
        return n + 1
    if n - 1 >= lo:
        return n - 1
    return n


def layout(width: float, height: float) -> dict:
    g = GRID
    w = max(width, 1.0)
    h = max(height, 1.0)
    s = max(w, h) / g["referenceWidth"]
    persp = g["perspective"] * s
    radius = g["sphereRadius"] * s
    portrait = h > w
    plane_w = w * (g["planeWidthRatioPortrait"] if portrait else g["planeWidthRatio"])
    plane_h = plane_w / g["planeAspect"]
    cell_w = plane_w * (1 + g["gapRatio"])
    cell_h = plane_h * (1 + g["gapRatio"])
    zoom_z = 0.1 * persp
    cover_x = 0.5 * w * g["coverageMargin"] + math.tan(0.05) * persp + zoom_z
    cover_y = 0.5 * h * g["coverageMargin"] + math.tan(0.05) * persp + zoom_z
    cols = _force_even(2 * _arc_to_cover(cover_x, 0.5 * plane_w, persp, radius) / cell_w + 4,
                       g["minCols"], g["maxCols"])
    rows = _force_even(2 * _arc_to_cover(cover_y, 0.5 * plane_h, persp, radius) / cell_h + 4,
                       g["minRows"], g["maxRows"])
    return {
        "viewport": [w, h],
        "perspective": persp, "sphereRadius": radius,
        "planeWidth": plane_w, "planeHeight": plane_h,
        "cellW": cell_w, "cellH": cell_h, "cols": cols, "rows": rows,
        "periodX": cols * cell_w, "periodY": rows * cell_h,
        "portrait": portrait,
        "cardScale": plane_w / REFERENCE_PLANE_WIDTH,
        "activeSlotCount": cols * rows,
        "bundleHash": CONTRACT["target"]["appBundleSha256"],
        "layoutVersion": CONTRACT["layoutVersion"],
    }


def wrap(value: float, period: float) -> float:
    half = 0.5 * period
    return ((value + half) % period + period) % period - half


def place(slot_index: int, scroll_x: float, scroll_y: float, frame: dict) -> dict:
    cols, rows, R = frame["cols"], frame["rows"], frame["sphereRadius"]
    pool_row = slot_index // cols
    pool_col = slot_index % cols
    brick = (pool_row % 2) * frame["cellW"] * 0.5
    x_arc = wrap((pool_col - (cols - 1) / 2) * frame["cellW"] + scroll_x + brick, frame["periodX"])
    y_arc = wrap(-(pool_row - (rows - 1) / 2) * frame["cellH"] - scroll_y, frame["periodY"])
    tx, ty = x_arc / R, y_arc / R
    cy = math.cos(ty)
    nx, ny, nz = math.sin(tx) * cy, math.sin(ty), math.cos(tx) * cy
    return {"slotIndex": slot_index, "poolRow": pool_row, "poolCol": pool_col,
            "xArc": x_arc, "yArc": y_arc,
            "x": nx * R, "y": ny * R, "z": nz * R - R,
            "nx": nx, "ny": ny, "nz": nz, "code": slot_index + 1}


def camera(frame: dict) -> dict:
    """Source-exact camera. No pitch, no zoom, no anamorphic term."""
    h = frame["viewport"][1]
    return {
        "position": [0.0, 0.0, frame["perspective"]],
        "lookAt": [0.0, 0.0, 0.0],
        "fovDeg": math.degrees(2 * math.atan(h / 2 / frame["perspective"])),
        "near": CAMERA["near"], "far": CAMERA["far"],
    }
