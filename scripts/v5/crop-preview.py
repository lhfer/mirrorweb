#!/usr/bin/env python3
"""
Per-clip cover-crop preview.

Shows what `cover` keeps and what it throws away on the real source frame, so
the focus point can be confirmed (or corrected) before it ships. The crop window
is taken from the fit the running page reported, not recomputed here.

Usage: crop-preview.py --frames=<dir> --fits=<mediafit.json> --out=<dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CLIPS = [
    ("niulai-intro", "NL-01 牛来开场"),
    ("cursor-niulai", "NL-02 Cursor 牛来"),
    ("pelican-ai", "NL-03 鹈鹕测 AI"),
]


def font(size: int):
    for path in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def preview(frame: Path, fit: dict, title: str, out: Path) -> None:
    src = Image.open(frame).convert("RGB")
    w, h = src.size
    # Texture-matrix window -> source pixels. three's V origin is bottom-left.
    cx0 = fit["offsetX"] * w
    cw = fit["repeatX"] * w
    cy0 = (1.0 - fit["offsetY"] - fit["repeatY"]) * h
    ch = fit["repeatY"] * h

    dim = Image.new("RGB", (w, h), (0, 0, 0))
    canvas = Image.blend(src, dim, 0.62)
    canvas.paste(src.crop((int(cx0), int(cy0), int(cx0 + cw), int(cy0 + ch))), (int(cx0), int(cy0)))

    d = ImageDraw.Draw(canvas)
    d.rectangle([cx0, cy0, cx0 + cw - 1, cy0 + ch - 1], outline=(0, 230, 120), width=4)
    fx = cx0 + cw * 0.5
    fy = cy0 + ch * 0.5
    d.line([(fx - 22, fy), (fx + 22, fy)], fill=(255, 64, 64), width=3)
    d.line([(fx, fy - 22), (fx, fy + 22)], fill=(255, 64, 64), width=3)

    bar = 78
    out_img = Image.new("RGB", (w, h + bar), (16, 16, 20))
    out_img.paste(canvas, (0, bar))
    d2 = ImageDraw.Draw(out_img)
    d2.text((12, 8), title, fill=(255, 255, 255), font=font(24))
    kept = fit["repeatX"] * fit["repeatY"] * 100
    d2.text(
        (12, 42),
        f"source {fit['sourceWidth']}x{fit['sourceHeight']} (ar {fit['sourceAspect']:.3f})"
        f"  ->  card ar {fit['cardAspect']:.3f}   keeps {kept:.1f}% of frame"
        f"   crop x {int(cx0)}..{int(cx0 + cw)}   aspect err {fit['aspectErrorPct']:.4f}%",
        fill=(150, 220, 255),
        font=font(18),
    )
    out_img.save(out)
    print(out)


if __name__ == "__main__":
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    frames = Path(args["--frames"])
    fits = json.loads(Path(args["--fits"]).read_text())["clips"]
    out = Path(args["--out"])
    out.mkdir(parents=True, exist_ok=True)
    for (name, title), fit in zip(CLIPS, fits):
        preview(frames / f"{name}.png", fit, f"{title}  —  cover, focus 0.50 / 0.50, zoom 1",
                out / f"crop-{name}.png")
