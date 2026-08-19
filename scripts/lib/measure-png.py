#!/usr/bin/env python3
"""Read-only PNG measurement for Infinite Liquid Glass screenshots."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from collections import deque

from PIL import Image, ImageDraw


def load_rgb(path: Path) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    return np.asarray(img)


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(radius):
        nxt = out.copy()
        nxt[1:, :] |= out[:-1, :]
        nxt[:-1, :] |= out[1:, :]
        nxt[:, 1:] |= out[:, :-1]
        nxt[:, :-1] |= out[:, 1:]
        out = nxt
    return out


def erode(mask: np.ndarray, radius: int) -> np.ndarray:
    return ~dilate(~mask, radius)


def flood_from_border(open_cells: np.ndarray) -> np.ndarray:
    h, w = open_cells.shape
    reached = np.zeros_like(open_cells)
    q: deque[tuple[int, int]] = deque()
    for x in range(w):
        if open_cells[0, x]:
            q.append((0, x))
        if open_cells[h - 1, x]:
            q.append((h - 1, x))
    for y in range(h):
        if open_cells[y, 0]:
            q.append((y, 0))
        if open_cells[y, w - 1]:
            q.append((y, w - 1))
    while q:
        y, x = q.popleft()
        if reached[y, x] or not open_cells[y, x]:
            continue
        reached[y, x] = True
        if y > 0:
            q.append((y - 1, x))
        if y + 1 < h:
            q.append((y + 1, x))
        if x > 0:
            q.append((y, x - 1))
        if x + 1 < w:
            q.append((y, x + 1))
    return reached


def fill_holes(mask: np.ndarray) -> np.ndarray:
    inv = ~mask
    reached = flood_from_border(inv)
    holes = inv & ~reached
    return mask | holes


def label_components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    h, w = mask.shape
    labels = np.zeros((h, w), np.int32)
    parent = [0]

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    next_id = 0
    for y in range(h):
        row = mask[y]
        prev = labels[y - 1] if y else None
        for x in range(w):
            if not row[x]:
                continue
            left = labels[y, x - 1] if x else 0
            up = int(prev[x]) if prev is not None else 0
            if left and up:
                labels[y, x] = left
                a, b = find(left), find(up)
                if a != b:
                    parent[b] = a
            elif left:
                labels[y, x] = left
            elif up:
                labels[y, x] = up
            else:
                next_id += 1
                parent.append(next_id)
                labels[y, x] = next_id

    remap = {0: 0}
    current = 0
    for i in range(1, len(parent)):
        root = find(i)
        if root not in remap:
            current += 1
            remap[root] = current
    flat = labels.reshape(-1)
    for i, v in enumerate(flat):
        if v:
            flat[i] = remap[find(int(v))]
    return labels, current


def components(mask: np.ndarray) -> list[dict]:
    labels, count = label_components(mask)
    out = []
    for i in range(1, count + 1):
        ys, xs = np.where(labels == i)
        if xs.size == 0:
            continue
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        area = int(xs.size)
        cx = float(xs.mean())
        cy = float(ys.mean())
        out.append(
            {
                "id": i,
                "area": area,
                "bbox": {"x": x0, "y": y0, "w": x1 - x0 + 1, "h": y1 - y0 + 1},
                "cx": cx,
                "cy": cy,
            }
        )
    return out


def corner_sample(rgb: np.ndarray, inset: int = 8, size: int = 16) -> dict:
    h, w, _ = rgb.shape
    patches = [
        rgb[inset : inset + size, inset : inset + size],
        rgb[inset : inset + size, w - inset - size : w - inset],
        rgb[h - inset - size : h - inset, inset : inset + size],
        rgb[h - inset - size : h - inset, w - inset - size : w - inset],
    ]
    med = np.median(np.concatenate([p.reshape(-1, 3) for p in patches], axis=0), axis=0)
    return {
        "rgb": [int(med[0]), int(med[1]), int(med[2])],
        "hex": "#{:02x}{:02x}{:02x}".format(int(med[0]), int(med[1]), int(med[2])),
        "maxChannel": int(med.max()),
    }


def fit_slope_deg(xs: np.ndarray, ys: np.ndarray) -> float | None:
    if xs.size < 8:
        return None
    x = xs.astype(np.float64)
    y = ys.astype(np.float64)
    xm, ym = x.mean(), y.mean()
    den = ((x - xm) ** 2).sum()
    if den < 1:
        return None
    slope = ((x - xm) * (y - ym)).sum() / den
    return math.degrees(math.atan(slope))


def tile_metrics(mask: np.ndarray, rgb: np.ndarray, tile: dict) -> dict:
    x0 = tile["bbox"]["x"]
    y0 = tile["bbox"]["y"]
    w = tile["bbox"]["w"]
    h = tile["bbox"]["h"]
    x1, y1 = x0 + w, y0 + h
    local = mask[y0:y1, x0:x1]
    local_rgb = rgb[y0:y1, x0:x1]
    clipped = {
        "left": x0 <= 1,
        "right": x1 >= rgb.shape[1] - 1,
        "top": y0 <= 1,
        "bottom": y1 >= rgb.shape[0] - 1,
    }

    top_run = 0
    if local.any():
        for row in local:
            if row.any():
                xs = np.where(row)[0]
                top_run = int(xs.max() - xs.min() + 1)
                break
    radius_est = max(0.0, (w - top_run) / 2.0) if top_run else None

    top_xs = []
    top_ys = []
    for x in range(w):
        col = np.where(local[:, x])[0]
        if col.size:
            top_xs.append(x)
            top_ys.append(int(col[0]))
    tilt = fit_slope_deg(np.array(top_xs), np.array(top_ys)) if top_xs else None

    rim = local & ~erode(local, 8)
    interior = erode(local, max(10, min(w, h) // 12))
    rim_ab = 0.0
    interior_ab = 0.0
    rim_lum_p95 = 0.0
    highlight_dir = None
    if rim.any():
        rr = local_rgb[rim]
        rim_ab = float(np.mean(np.abs(rr[:, 0].astype(np.int16) - rr[:, 2].astype(np.int16))))
        lum = 0.2126 * rr[:, 0] + 0.7152 * rr[:, 1] + 0.0722 * rr[:, 2]
        rim_lum_p95 = float(np.percentile(lum, 95))
        bright = rim.copy()
        ys, xs = np.where(rim)
        keep = lum >= np.percentile(lum, 90)
        if keep.any():
            bx = float(xs[keep].mean())
            by = float(ys[keep].mean())
            highlight_dir = {
                "nx": round((bx / max(w - 1, 1)) - 0.5, 3),
                "ny": round((by / max(h - 1, 1)) - 0.5, 3),
            }
    if interior.any():
        ir = local_rgb[interior]
        interior_ab = float(np.mean(np.abs(ir[:, 0].astype(np.int16) - ir[:, 2].astype(np.int16))))

    mid_y = h // 2
    row = local[mid_y]
    xs = np.where(row)[0]
    rim_width = None
    if xs.size > 20:
        left = int(xs[0])
        run = 0
        for x in range(left, min(left + 80, w)):
            pix = local_rgb[mid_y, x]
            chroma = abs(int(pix[0]) - int(pix[2]))
            if chroma >= 12 or pix.max() >= 180:
                run += 1
            elif run >= 4:
                break
        rim_width = run if run else None

    return {
        **tile,
        "clipped": clipped,
        "aspect": round(w / h, 3) if h else None,
        "cornerRadiusPx": None if radius_est is None else round(radius_est, 1),
        "cornerRadiusOverWidth": None if radius_est is None else round(radius_est / w, 3),
        "topEdgeTiltDeg": None if tilt is None else round(tilt, 2),
        "rimChromaRB": round(rim_ab, 2),
        "interiorChromaRB": round(interior_ab, 2),
        "rimLuminanceP95": round(rim_lum_p95, 1),
        "highlightOffset": highlight_dir,
        "rimBandPx": rim_width,
    }


def smooth1d(values: np.ndarray, k: int = 11) -> np.ndarray:
    k = max(3, k | 1)
    pad = np.pad(values, k // 2, mode="edge")
    c = np.cumsum(pad)
    return (c[k:] - c[:-k]) / k


def gap_mask(rgb: np.ndarray) -> np.ndarray:
    r, g = rgb[:, :, 0], rgb[:, :, 1]
    mx = rgb.max(axis=2)
    return (r <= 8) & (g <= 14) & (mx <= 36)


def runs_below(values: np.ndarray, cutoff: float, min_len: int) -> list[tuple[int, int]]:
    out = []
    in_run = False
    start = 0
    for i, v in enumerate(values):
        if v <= cutoff and not in_run:
            start = i
            in_run = True
        if in_run and v > cutoff:
            if i - start >= min_len:
                out.append((start, i - 1))
            in_run = False
    if in_run and len(values) - start >= min_len:
        out.append((start, len(values) - 1))
    return out


def refine_cell(gap: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> dict | None:
    cell = gap[y0 : y1 + 1, x0 : x1 + 1]
    if cell.size == 0:
        return None
    content = ~cell
    if content.mean() < 0.18:
        return None
    row_frac = content.mean(axis=1)
    col_frac = content.mean(axis=0)
    ys = np.where(row_frac > 0.18)[0]
    xs = np.where(col_frac > 0.18)[0]
    if xs.size < 12 or ys.size < 8:
        return None
    rx0, rx1 = x0 + int(xs[0]), x0 + int(xs[-1])
    ry0, ry1 = y0 + int(ys[0]), y0 + int(ys[-1])
    w, h = rx1 - rx0 + 1, ry1 - ry0 + 1
    local = content[ry0 - y0 : ry1 - y0 + 1, rx0 - x0 : rx1 - x0 + 1]
    ys2, xs2 = np.where(local)
    if xs2.size == 0:
        return None
    return {
        "id": 0,
        "area": int(xs2.size),
        "bbox": {"x": rx0, "y": ry0, "w": w, "h": h},
        "cx": float(rx0 + xs2.mean()),
        "cy": float(ry0 + ys2.mean()),
    }


def detect_tiles(rgb: np.ndarray, threshold: int = 16, close_r: int = 8) -> tuple[list[dict], np.ndarray]:
    del threshold, close_r
    h, w = rgb.shape[:2]
    gap = gap_mask(rgb)
    # Overlay strip is never a tile gutter we want to keep as content.
    gap[-max(24, h // 22) :, :] = True
    row = smooth1d(gap.mean(axis=1), max(9, h // 80))
    row_bands = runs_below(row, 0.42, min_len=max(16, h // 40))
    if row_bands and row_bands[0][0] > 12:
        row_bands = [(0, max(12, row_bands[0][0] - 8))] + row_bands

    tiles = []
    for y0, y1 in row_bands:
        through = smooth1d(gap[y0 : y1 + 1].mean(axis=0), max(9, w // 90))
        min_w = max(48, w // 16)
        x_bands = runs_below(through, 0.55, min_len=min_w)
        for x0, x1 in x_bands:
            refined = refine_cell(gap, x0, x1, y0, y1)
            if not refined:
                continue
            bw, bh = refined["bbox"]["w"], refined["bbox"]["h"]
            if bw < w * 0.07 or bh < h * 0.04:
                continue
            tiles.append(tile_metrics(~gap, rgb, refined))

    tiles.sort(key=lambda t: (t["cy"], t["cx"]))
    for i, t in enumerate(tiles, start=1):
        t["id"] = i
    return tiles, ~gap


def assign_landmarks(tiles: list[dict], width: int, height: int) -> dict:
    if not tiles:
        return {}
    for t in tiles:
        t["nx"] = t["cx"] / width
        t["ny"] = t["cy"] / height
        t["nw"] = t["bbox"]["w"] / width
        t["nh"] = t["bbox"]["h"] / height

    center = min(tiles, key=lambda t: (t["nx"] - 0.5) ** 2 + (t["ny"] - 0.5) ** 2)
    rows: list[list[dict]] = []
    for t in sorted(tiles, key=lambda x: x["ny"]):
        placed = False
        for row in rows:
            if abs(row[0]["ny"] - t["ny"]) < 0.12:
                row.append(t)
                placed = True
                break
        if not placed:
            rows.append([t])
    for row in rows:
        row.sort(key=lambda t: t["nx"])
    rows.sort(key=lambda row: sum(t["ny"] for t in row) / len(row))

    def pick(pred):
        cands = [t for t in tiles if pred(t)]
        return min(cands, key=lambda t: (t["nx"] - 0.5) ** 2 + (t["ny"] - 0.5) ** 2) if cands else None

    names = {
        "center": center,
        "left": pick(lambda t: t["nx"] < center["nx"] - 0.12 and abs(t["ny"] - center["ny"]) < 0.12),
        "right": pick(lambda t: t["nx"] > center["nx"] + 0.12 and abs(t["ny"] - center["ny"]) < 0.12),
        "up": pick(lambda t: t["ny"] < center["ny"] - 0.12 and abs(t["nx"] - center["nx"]) < 0.16),
        "down": pick(lambda t: t["ny"] > center["ny"] + 0.12 and abs(t["nx"] - center["nx"]) < 0.16),
        "upLeft": pick(lambda t: t["nx"] < center["nx"] - 0.12 and t["ny"] < center["ny"] - 0.12),
        "upRight": pick(lambda t: t["nx"] > center["nx"] + 0.12 and t["ny"] < center["ny"] - 0.12),
        "downLeft": pick(lambda t: t["nx"] < center["nx"] - 0.12 and t["ny"] > center["ny"] + 0.12),
        "downRight": pick(lambda t: t["nx"] > center["nx"] + 0.12 and t["ny"] > center["ny"] + 0.12),
    }
    # Fill missing slots with leftover tiles nearest the expected cell.
    used = {id(v) for v in names.values() if v is not None}
    expected = {
        "left": (center["nx"] - 0.32, center["ny"]),
        "right": (center["nx"] + 0.32, center["ny"]),
        "up": (center["nx"], center["ny"] - 0.32),
        "down": (center["nx"], center["ny"] + 0.32),
        "upLeft": (center["nx"] - 0.28, center["ny"] - 0.30),
        "upRight": (center["nx"] + 0.28, center["ny"] - 0.30),
        "downLeft": (center["nx"] - 0.28, center["ny"] + 0.30),
        "downRight": (center["nx"] + 0.28, center["ny"] + 0.30),
    }
    leftovers = [t for t in tiles if id(t) not in used]
    for key, (ex, ey) in expected.items():
        if names[key] is None and leftovers:
            best = min(leftovers, key=lambda t: (t["nx"] - ex) ** 2 + (t["ny"] - ey) ** 2)
            names[key] = best
            leftovers.remove(best)

    return {"landmarks": names, "rows": [[id(t) for t in row] for row in rows], "rowCount": len(rows)}


def spacing_from_landmarks(lm: dict) -> dict:
    def gap(a, b, axis):
        if not a or not b:
            return None
        if axis == "x":
            a1 = a["bbox"]["x"] + a["bbox"]["w"]
            b0 = b["bbox"]["x"]
            return b0 - a1 if b["cx"] > a["cx"] else a["bbox"]["x"] - (b["bbox"]["x"] + b["bbox"]["w"])
        a1 = a["bbox"]["y"] + a["bbox"]["h"]
        b0 = b["bbox"]["y"]
        return b0 - a1 if b["cy"] > a["cy"] else a["bbox"]["y"] - (b["bbox"]["y"] + b["bbox"]["h"])

    c, l, r, u, d = lm.get("center"), lm.get("left"), lm.get("right"), lm.get("up"), lm.get("down")
    gaps = {
        "centerToLeftPx": gap(l, c, "x") if l and c else None,
        "centerToRightPx": gap(c, r, "x") if c and r else None,
        "centerToUpPx": gap(u, c, "y") if u and c else None,
        "centerToDownPx": gap(c, d, "y") if c and d else None,
    }
    return gaps


def mae(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return -1.0
    return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))


def phase_shift(a: np.ndarray, b: np.ndarray) -> dict:
    if a.shape != b.shape:
        return {"dx": None, "dy": None, "note": "shape mismatch"}
    ga = a.mean(axis=2).astype(np.float64)
    gb = b.mean(axis=2).astype(np.float64)
    ga -= ga.mean()
    gb -= gb.mean()
    fa = np.fft.fft2(ga)
    fb = np.fft.fft2(gb)
    r = fa * np.conj(fb)
    r /= np.abs(r) + 1e-9
    c = np.abs(np.fft.ifft2(r))
    dy, dx = np.unravel_index(int(np.argmax(c)), c.shape)
    if dy > a.shape[0] / 2:
        dy -= a.shape[0]
    if dx > a.shape[1] / 2:
        dx -= a.shape[1]
    peak = float(c.max() / (c.mean() + 1e-9))
    return {"dx": int(dx), "dy": int(dy), "peakRatio": round(peak, 2)}


def measure_loading(rgb: np.ndarray) -> dict:
    mx = rgb.max(axis=2)
    mask = mx >= 20
    if not mask.any():
        return {"found": False}
    ys, xs = np.where(mask)
    return {
        "found": True,
        "brightCount": int(xs.size),
        "bbox": {
            "x": int(xs.min()),
            "y": int(ys.min()),
            "w": int(xs.max() - xs.min() + 1),
            "h": int(ys.max() - ys.min() + 1),
        },
        "center": {"x": float(xs.mean()), "y": float(ys.mean())},
        "nx": float(xs.mean() / rgb.shape[1]),
        "ny": float(ys.mean() / rgb.shape[0]),
        "background": corner_sample(rgb),
    }


def downscale_for_detect(rgb: np.ndarray, max_side: int = 1280) -> tuple[np.ndarray, float]:
    h, w = rgb.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale >= 0.999:
        return rgb, 1.0
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    small = np.asarray(Image.fromarray(rgb).resize((nw, nh), Image.BILINEAR))
    return small, scale


def summarize_frame(path: Path, write_debug: Path | None = None) -> dict:
    rgb_full = load_rgb(path)
    rgb, scale = downscale_for_detect(rgb_full)
    h, w = rgb.shape[:2]
    tiles, mask = detect_tiles(rgb)
    assigned = assign_landmarks(tiles, w, h)
    landmarks = {}
    for key, tile in assigned.get("landmarks", {}).items():
        if not tile:
            landmarks[key] = None
            continue
        landmarks[key] = {
            "cx": round(tile["cx"], 1),
            "cy": round(tile["cy"], 1),
            "nx": round(tile["nx"], 4),
            "ny": round(tile["ny"], 4),
            "w": tile["bbox"]["w"],
            "h": tile["bbox"]["h"],
            "nw": round(tile["nw"], 4),
            "nh": round(tile["nh"], 4),
            "bbox": tile["bbox"],
            "clipped": tile["clipped"],
            "aspect": tile["aspect"],
            "cornerRadiusPx": tile["cornerRadiusPx"],
            "cornerRadiusOverWidth": tile["cornerRadiusOverWidth"],
            "topEdgeTiltDeg": tile["topEdgeTiltDeg"],
            "rimChromaRB": tile["rimChromaRB"],
            "interiorChromaRB": tile["interiorChromaRB"],
            "rimLuminanceP95": tile["rimLuminanceP95"],
            "highlightOffset": tile["highlightOffset"],
            "rimBandPx": tile["rimBandPx"],
        }

    inv = 1.0 / scale
    for key, item in landmarks.items():
        if not item:
            continue
        item["cx"] = round(item["cx"] * inv, 1)
        item["cy"] = round(item["cy"] * inv, 1)
        item["w"] = int(round(item["w"] * inv))
        item["h"] = int(round(item["h"] * inv))
        item["bbox"] = {
            "x": int(round(item["bbox"]["x"] * inv)),
            "y": int(round(item["bbox"]["y"] * inv)),
            "w": int(round(item["bbox"]["w"] * inv)),
            "h": int(round(item["bbox"]["h"] * inv)),
        }
        if item["cornerRadiusPx"] is not None:
            item["cornerRadiusPx"] = round(item["cornerRadiusPx"] * inv, 1)
        if item["rimBandPx"] is not None:
            item["rimBandPx"] = int(round(item["rimBandPx"] * inv))

    spacing = spacing_from_landmarks(assigned.get("landmarks", {}))
    if scale != 1.0:
        spacing = {
            k: None if v is None else round(v * inv, 1)
            for k, v in spacing.items()
        }

    if write_debug:
        vis = Image.fromarray(rgb_full)
        draw = ImageDraw.Draw(vis)
        colors = {
            "center": (0, 255, 180),
            "left": (255, 210, 0),
            "right": (255, 210, 0),
            "up": (80, 180, 255),
            "down": (80, 180, 255),
            "upLeft": (255, 90, 90),
            "upRight": (255, 90, 90),
            "downLeft": (255, 90, 90),
            "downRight": (255, 90, 90),
        }
        for key, tile in assigned.get("landmarks", {}).items():
            if not tile:
                continue
            b = landmarks[key]["bbox"]
            color = colors.get(key, (255, 255, 255))
            draw.rectangle([b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]], outline=color, width=2)
            cx, cy = landmarks[key]["cx"], landmarks[key]["cy"]
            draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=color)
            draw.text((b["x"] + 6, b["y"] + 6), key, fill=color)
        write_debug.parent.mkdir(parents=True, exist_ok=True)
        vis.save(write_debug)

    all_tiles = []
    for tile in tiles:
        all_tiles.append(
            {
                "cx": round(tile["cx"] * inv, 1),
                "cy": round(tile["cy"] * inv, 1),
                "nx": round(tile["cx"] / w, 4),
                "ny": round(tile["cy"] / h, 4),
                "w": int(round(tile["bbox"]["w"] * inv)),
                "h": int(round(tile["bbox"]["h"] * inv)),
                "nw": round(tile["bbox"]["w"] / w, 4),
                "nh": round(tile["bbox"]["h"] / h, 4),
                "topEdgeTiltDeg": tile["topEdgeTiltDeg"],
                "cornerRadiusPx": None
                if tile["cornerRadiusPx"] is None
                else round(tile["cornerRadiusPx"] * inv, 1),
                "rimBandPx": None if tile["rimBandPx"] is None else int(round(tile["rimBandPx"] * inv)),
                "rimChromaRB": tile["rimChromaRB"],
                "clipped": tile["clipped"],
            }
        )

    gutter_row = int(np.argmax(gap_mask(rgb).mean(axis=1)))
    gutter_rgb = rgb[max(0, gutter_row - 1) : gutter_row + 2]
    gmed = np.median(gutter_rgb.reshape(-1, 3), axis=0)
    background = {
        "method": "median of highest-gap row",
        "row": int(round(gutter_row * inv)),
        "rgb": [int(gmed[0]), int(gmed[1]), int(gmed[2])],
        "hex": "#{:02x}{:02x}{:02x}".format(int(gmed[0]), int(gmed[1]), int(gmed[2])),
        "cornerSampleNote": "corners contain clipped tiles; do not use as background",
        "cornerSample": corner_sample(rgb_full),
    }

    center = landmarks.get("center")
    return {
        "file": str(path),
        "pixels": {"w": rgb_full.shape[1], "h": rgb_full.shape[0]},
        "detectScale": scale,
        "tileCount": len(tiles),
        "allTiles": all_tiles,
        "background": background,
        "landmarks": landmarks,
        "spacingPx": spacing,
        "rowCount": assigned.get("rowCount"),
        "centerTile": center,
        "edgeTilt": {
            "left": None if not landmarks.get("left") else landmarks["left"]["topEdgeTiltDeg"],
            "right": None if not landmarks.get("right") else landmarks["right"]["topEdgeTiltDeg"],
            "center": None if not center else center["topEdgeTiltDeg"],
        },
    }


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/reference")
    out_dir = root / "measurements"
    out_dir.mkdir(parents=True, exist_ok=True)

    viewports = [
        "A-1440x900-dpr1",
        "B-1920x1080-dpr1",
        "C-1440x900-dpr2",
        "D-390x844-mobile",
        "E-844x390-mobile-land",
    ]
    frames = [
        "01-just-opened.png",
        "02-loading-25.png",
        "03-loading-50.png",
        "04-first-loaded-frame.png",
        "05-rest-2s.png",
        "06-rest-5s.png",
        "07-mouse-center.png",
        "08-slow-drag-left-400.png",
        "09-slow-diagonal-drag.png",
        "10-flick-0ms.png",
        "11-flick-250ms.png",
        "12-flick-500ms.png",
        "13-flick-1000ms.png",
        "14-flick-stopped.png",
        "15-wheel-vertical.png",
        "16-wheel-horizontal.png",
        "17-stress-30s.png",
        "18-resize-1100x720.png",
        "19-blur-focus.png",
    ]

    report: dict = {"viewports": {}}
    for vp in viewports:
        vdir = root / vp
        if not vdir.exists():
            report["viewports"][vp] = {"status": "missing"}
            continue
        entry: dict = {"frames": {}, "loading": {}, "motion": {}}
        loaded = {}
        for name in frames:
            fp = vdir / name
            if not fp.exists():
                continue
            rgb = load_rgb(fp)
            if name.startswith(("01-", "02-", "03-")):
                entry["loading"][name] = measure_loading(rgb)
                continue
            debug = out_dir / f"{vp}-{name.replace('.png', '')}-debug.png" if name in {
                "04-first-loaded-frame.png",
                "06-rest-5s.png",
                "08-slow-drag-left-400.png",
                "14-flick-stopped.png",
            } else None
            measured = summarize_frame(fp, debug)
            entry["frames"][name] = measured
            loaded[name] = rgb

        def pair(a: str, b: str) -> dict | None:
            if a in loaded and b in loaded:
                sa, _ = downscale_for_detect(loaded[a], 960)
                sb, _ = downscale_for_detect(loaded[b], 960)
                return {
                    "mae": round(mae(sa, sb), 3),
                    "phase": phase_shift(sa, sb),
                }
            return None

        entry["motion"] = {
            "idle_04_05": pair("04-first-loaded-frame.png", "05-rest-2s.png"),
            "idle_05_06": pair("05-rest-2s.png", "06-rest-5s.png"),
            "idle_04_06": pair("04-first-loaded-frame.png", "06-rest-5s.png"),
            "hover_06_07": pair("06-rest-5s.png", "07-mouse-center.png"),
            "dragLeft_07_08": pair("07-mouse-center.png", "08-slow-drag-left-400.png"),
            "diag_07_09": pair("07-mouse-center.png", "09-slow-diagonal-drag.png"),
            "flick_10_11": pair("10-flick-0ms.png", "11-flick-250ms.png"),
            "flick_11_12": pair("11-flick-250ms.png", "12-flick-500ms.png"),
            "flick_12_13": pair("12-flick-500ms.png", "13-flick-1000ms.png"),
            "flick_13_14": pair("13-flick-1000ms.png", "14-flick-stopped.png"),
            "flick_10_14": pair("10-flick-0ms.png", "14-flick-stopped.png"),
            "wheelV_14_15": pair("14-flick-stopped.png", "15-wheel-vertical.png"),
            "wheelH_15_16": pair("15-wheel-vertical.png", "16-wheel-horizontal.png"),
            "blur_06_19": pair("06-rest-5s.png", "19-blur-focus.png"),
        }
        if "04-first-loaded-frame.png" in entry["frames"] and "06-rest-5s.png" in entry["frames"]:
            c4 = entry["frames"]["04-first-loaded-frame.png"]["landmarks"].get("center")
            c6 = entry["frames"]["06-rest-5s.png"]["landmarks"].get("center")
            if c4 and c6:
                entry["motion"]["idleCenterDriftPx"] = {
                    "dx": round(c6["cx"] - c4["cx"], 2),
                    "dy": round(c6["cy"] - c4["cy"], 2),
                }
        report["viewports"][vp] = entry

    out_json = out_dir / "landmarks.json"
    out_json.write_text(json.dumps(report, indent=2))
    print(str(out_json))


if __name__ == "__main__":
    main()
