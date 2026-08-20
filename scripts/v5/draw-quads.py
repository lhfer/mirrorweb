#!/usr/bin/env python3
"""Draw model-predicted card quads onto a frame, for visual fit verification."""
from __future__ import annotations

import json
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import importlib.util

spec = importlib.util.spec_from_file_location("fitlayout", __file__.rsplit("/", 1)[0] + "/fit-layout.py")
fit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fit)


def main(src: str, dst: str, params_json: str, cells: str = "auto"):
    p = json.loads(params_json)
    img = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(img)
    grid = [(i, j) for j in (-1, 0, 1, 2) for i in (-3, -2, -1, 0, 1, 2, 3)]
    for i, j in grid:
        q = fit.card_quad(i, j, p)
        xs, ys = q[:, 0], q[:, 1]
        if xs.max() < -60 or xs.min() > 1500 or ys.max() < -60 or ys.min() > 960:
            continue
        pts = [(float(x), float(y)) for x, y in q]
        d.polygon(pts, outline=(255, 64, 64))
        d.line(pts + [pts[0]], fill=(255, 64, 64), width=2)
        cx, cy = float(xs.mean()), float(ys.mean())
        d.line([(cx - 9, cy), (cx + 9, cy)], fill=(0, 255, 128), width=2)
        d.line([(cx, cy - 9), (cx, cy + 9)], fill=(0, 255, 128), width=2)
        d.text((cx + 12, cy - 20), f"{i},{j}", fill=(0, 255, 128))
    img.save(dst)
    print(dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
