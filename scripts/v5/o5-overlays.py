#!/usr/bin/env python3
"""O5 §十三 -- the four overlays the private package must carry.

A number in a JSON file is a claim; an overlay is the same claim in a form a
reviewer can check by looking. These four are the ones where the measurement
is easy to get wrong in a way the number alone would hide:

  edge ROI               the exact strip every band and luma reading is taken
                         from, at 4x, for Target / control / candidate side by
                         side
  reflection ROI         the same strip on the bright side, where the white
                         reflection ratio is read
  landmark overlay       item 7's exhibit: the analytic FLAT position of each
                         media landmark and where it actually landed, so the
                         displacement being scored is visible as a distance
  spectral overlay       item 6's exhibit: per-tile high-frequency energy as a
                         heat map, so "reproduces the Target's structure" can
                         be seen rather than taken on a correlation coefficient

Usage: o5-overlays.py [--measure=<dir>] [--out=<dir>]
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o5_ov_stats", "o2_optics_stats.py")
I = _load("o5_ov_ins", "o5_instruments.py")
G = _load("o5_ov_gate", "o5-gate.py")

LANES = ["target", "control", "candidate"]
COLOUR = {"target": (250, 220, 120), "control": (240, 120, 100),
          "candidate": (110, 190, 255)}


def rgb(p):
    return np.asarray(Image.open(p).convert("RGB"), np.float32)


def label(d, xy, text, fill=(240, 240, 245)):
    d.text(xy, text, fill=fill)


def edge_roi(md, man, out, vp, asset, side, name):
    """The exact band the scalar instruments read, at 4x, three lanes stacked."""
    rects, _ = G.rects_for(vp)
    if not rects:
        return None
    SCALE, PAD = 4, 30
    tiles, rows = [], []
    for lane in LANES:
        rec = G.one(man, lane=lane, state="rest", asset=asset, vp=vp,
                    **({"repeat": None} if lane == "target" else {}))
        if rec is None:
            continue
        a = rgb(md / rec["file"])
        crops = [I.edge_band(a, r, side) for r in rects]
        h = min(c.shape[0] for c in crops)
        strip = np.concatenate([c[:h] for c in crops], axis=1)
        tiles.append((lane, strip))
        lum = 0.2126 * strip[..., 0] + 0.7152 * strip[..., 1] + 0.0722 * strip[..., 2]
        rows.append({"lane": lane, "meanLuma": round(float(lum.mean()), 2)})
    if not tiles:
        return None
    tw = max(t.shape[1] for _, t in tiles) * SCALE
    th = max(t.shape[0] for _, t in tiles) * SCALE
    im = Image.new("RGB", (tw + 2 * PAD, (th + 26) * len(tiles) + PAD),
                   (16, 16, 20))
    d = ImageDraw.Draw(im)
    for i, (lane, strip) in enumerate(tiles):
        img = Image.fromarray(np.clip(strip, 0, 255).astype(np.uint8), "RGB")
        img = img.resize((strip.shape[1] * SCALE, strip.shape[0] * SCALE),
                         Image.NEAREST)
        y = PAD // 2 + i * (th + 26)
        im.paste(img, (PAD, y + 18))
        label(d, (PAD, y + 2),
              f"{lane}   mean luma {rows[i]['meanLuma']}", COLOUR[lane])
    label(d, (PAD, im.height - 16),
          f"{asset} {vp} -- {side} edge band, outer 8% x central 60%, 4x nearest")
    im.save(out / name)
    return {"file": name, "vp": vp, "asset": asset, "side": side, "rows": rows}


def landmark_overlay(md, man, out, vp, asset, name):
    """Item 7's exhibit: flat position vs measured position, per card."""
    rects, _ = G.rects_for(vp)
    if not rects or asset not in G.LANDMARKS:
        return None
    panels, meta = [], []
    for lane in LANES:
        rec = G.one(man, lane=lane, state="rest", asset=asset, vp=vp,
                    **({"repeat": None} if lane == "target" else {}))
        if rec is None:
            continue
        a = rgb(md / rec["file"])
        rect = rects[0]
        x0, y0, x1, y1 = rect
        card = a[y0:y1, x0:x1].copy()
        if lane == "target":
            sx, ox = G.target_cover_x(asset)
        else:
            sx, ox = G.frozen_cover_x(asset, 0)
        res = I.edge_compression(Image.open(md / rec["file"]), rect,
                                 G.LANDMARKS[asset], sx, ox)
        img = Image.fromarray(np.clip(card * 0.55, 0, 255).astype(np.uint8), "RGB")
        d = ImageDraw.Draw(img)
        cw = x1 - x0
        for row in res["landmarks"]:
            fx = row["flatNx"] * cw
            mx = row["measuredNx"] * cw
            d.line([(fx, 0), (fx, img.height)], fill=(120, 250, 140), width=2)
            d.line([(mx, 0), (mx, img.height)], fill=(255, 90, 90), width=2)
            d.rectangle([min(fx, mx), img.height // 2 - 5,
                         max(fx, mx), img.height // 2 + 5],
                        fill=(255, 200, 60))
            label(d, (min(fx, mx) + 3, img.height // 2 + 8),
                  f"{row['displacementPx']:+.2f}px", (255, 220, 120))
        label(d, (6, 4), f"{lane}   mean outward {res['meanOutwardPx']}px  "
                         f"({res['matched']}/{res['expected']} paired)",
              COLOUR[lane])
        panels.append(img)
        meta.append({"lane": lane, "meanOutwardPx": res["meanOutwardPx"],
                     "matched": res["matched"], "expected": res["expected"],
                     "landmarks": res["landmarks"]})
    if not panels:
        return None
    W = max(p.width for p in panels)
    H = sum(p.height for p in panels) + 24 * len(panels) + 22
    im = Image.new("RGB", (W + 20, H), (16, 16, 20))
    d = ImageDraw.Draw(im)
    y = 4
    for p in panels:
        im.paste(p, (10, y))
        y += p.height + 24
    label(d, (10, H - 16),
          "green = analytic FLAT position (no refraction)   "
          "red = measured   bar = the displacement being scored")
    im.save(out / name)
    return {"file": name, "vp": vp, "asset": asset, "panels": meta}


def spectral_overlay(md, man, out, vp, name):
    """Item 6's exhibit: per-tile HF energy as a heat map, three lanes."""
    rects, _ = G.rects_for(vp)
    if not rects:
        return None
    tile = I.SPECTRAL_TILE_PX
    panels, meta = [], []
    for lane in LANES:
        rec = G.one(man, lane=lane, state="rest", asset="hf-checker", vp=vp,
                    **({"repeat": None} if lane == "target" else {}))
        if rec is None:
            continue
        a = rgb(md / rec["file"])
        x0, y0, x1, y1 = rects[0]
        blk = a[y0:y1, x0:x1]
        p = 0.2126 * blk[..., 0] + 0.7152 * blk[..., 1] + 0.0722 * blk[..., 2]
        lap = np.zeros_like(p)
        lap[1:-1, 1:-1] = np.abs(4 * p[1:-1, 1:-1] - p[:-2, 1:-1] - p[2:, 1:-1]
                                 - p[1:-1, :-2] - p[1:-1, 2:])
        th, tw = lap.shape[0] // tile, lap.shape[1] // tile
        hm = lap[:th * tile, :tw * tile].reshape(th, tile, tw, tile).mean(axis=(1, 3))
        norm = hm / max(hm.max(), 1e-6)
        # A blue-to-amber ramp: low energy reads cool, high reads hot, and the
        # midtones stay distinguishable, which a plain grey ramp does not.
        heat = np.stack([np.clip(norm * 2.2, 0, 1),
                         np.clip(norm * 1.5, 0, 1),
                         np.clip(1.1 - norm * 1.6, 0, 1)], axis=-1) * 255
        img = Image.fromarray(heat.astype(np.uint8), "RGB").resize(
            (tw * tile, th * tile), Image.NEAREST)
        d = ImageDraw.Draw(img)
        label(d, (6, 4), f"{lane}   mean HF {round(float(hm.mean()), 2)}",
              (20, 20, 24))
        panels.append(img)
        meta.append({"lane": lane, "meanTileHf": round(float(hm.mean()), 3),
                     "tiles": int(hm.size)})
    if not panels:
        return None
    W = sum(p.width for p in panels) + 12 * (len(panels) + 1)
    H = max(p.height for p in panels) + 34
    im = Image.new("RGB", (W, H), (16, 16, 20))
    d = ImageDraw.Draw(im)
    x = 12
    for p in panels:
        im.paste(p, (x, 6))
        x += p.width + 12
    label(d, (12, H - 18),
          f"hf-checker {vp} -- per-{tile}px-tile high-frequency energy. "
          f"Blur loses energy everywhere; desaturation keeps it. "
          f"The gate correlates these maps tile by tile.")
    im.save(out / name)
    return {"file": name, "vp": vp, "panels": meta}


def main() -> int:
    md = REPO / "artifacts/optics-o5/measure"
    out = REPO / "artifacts/optics-o5/overlays"
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k == "measure":
            md = Path(v)
        elif k == "out":
            out = Path(v)
    out.mkdir(parents=True, exist_ok=True)
    G.MD = md
    man = json.loads((md / "measure-manifest.json").read_text())

    made = {"edgeRoi": [], "reflectionRoi": [], "landmark": [], "spectral": []}
    for vp in ["1440x900", "390x844", "844x390", "700x700"]:
        r = edge_roi(md, man, out, vp, "bw-split", "left",
                     f"edge-roi-dark-bw-split-{vp}.png")
        if r:
            made["edgeRoi"].append(r)
        r = edge_roi(md, man, out, vp, "bw-split", "right",
                     f"reflection-roi-bright-bw-split-{vp}.png")
        if r:
            made["reflectionRoi"].append(r)
        for asset in ["cover-control", "rgb-bars"]:
            r = landmark_overlay(md, man, out, vp, asset,
                                 f"landmark-overlay-{asset}-{vp}.png")
            if r:
                made["landmark"].append(r)
    r = spectral_overlay(md, man, out, "1440x900", "spectral-overlay-1440x900.png")
    if r:
        made["spectral"].append(r)

    (out / "overlays.json").write_text(json.dumps({
        "what": "O5 §十三 overlays. Each renders a measurement the gate scores "
                "into a form a reviewer can check by eye.",
        **made,
    }, indent=1))
    for k, v in made.items():
        print(f"  {k:16} {len(v)}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
