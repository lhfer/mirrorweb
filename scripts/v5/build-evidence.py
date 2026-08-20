#!/usr/bin/env python3
"""
Visual evidence for the V5 F0/F1 review.

Anything that embeds Target pixels is written under qa-v5/private/, which is
git-ignored, matching how the repo already handles Target-adjacent frames.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def load(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def label(img: Image.Image, text: str) -> Image.Image:
    out = img.copy()
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 22)
    except OSError:
        font = ImageFont.load_default()
    d.rectangle([0, 0, 12 + int(len(text) * 13), 36], fill=(0, 0, 0))
    d.text((8, 6), text, fill=(255, 255, 255), font=font)
    return out


def blend(a: Image.Image, b: Image.Image, alpha=0.5) -> Image.Image:
    return Image.blend(a, b.resize(a.size), alpha)


def difference(a: Image.Image, b: Image.Image, gain=3.0) -> Image.Image:
    x = np.asarray(a, np.int16)
    y = np.asarray(b.resize(a.size), np.int16)
    return Image.fromarray(np.clip(np.abs(x - y) * gain, 0, 255).astype(np.uint8))


def edge_overlay(base: Image.Image, other: Image.Image) -> Image.Image:
    """Target in red, local in cyan: aligned edges read white/grey."""
    a = np.asarray(base.convert("L"), np.float32)
    b = np.asarray(other.resize(base.size).convert("L"), np.float32)
    out = np.zeros(a.shape + (3,), np.float32)
    out[:, :, 0] = a
    out[:, :, 1] = b
    out[:, :, 2] = b
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def sheet(tiles: list[tuple[str, Image.Image]], cols: int, scale: float) -> Image.Image:
    w = int(tiles[0][1].width * scale)
    h = int(tiles[0][1].height * scale)
    rows = (len(tiles) + cols - 1) // cols
    out = Image.new("RGB", (cols * w + (cols + 1) * 10, rows * h + (rows + 1) * 10), (18, 18, 22))
    for n, (name, img) in enumerate(tiles):
        r, c = divmod(n, cols)
        out.paste(label(img, name).resize((w, h)), (10 + c * (w + 10), 10 + r * (h + 10)))
    return out


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    priv = root / "qa-v5/private"
    priv.mkdir(parents=True, exist_ok=True)

    target = load(root / "artifacts/reference/A-1440x900-dpr1/06-rest-5s.png")
    local_beauty = load(root / "qa-v5/f0/beauty/01-rest.png")
    local_found = load(root / "qa-v5/private/foundation-annotated/01-rest.png")
    local_clean = load(root / "qa-v5/f0/foundation/01-rest.png")

    blend(target, local_beauty).save(priv / "overlay-blend-1440x900.png")
    edge_overlay(target, local_clean).save(priv / "overlay-edges-1440x900.png")
    difference(target, local_beauty).save(priv / "overlay-difference-1440x900.png")

    sheet([
        ("TARGET rest 1440x900", target),
        ("LOCAL beauty rest", local_beauty),
        ("LOCAL foundation=layout", local_found),
        ("blend 50/50", blend(target, local_beauty)),
        ("edges TARGET=red LOCAL=cyan", edge_overlay(target, local_clean)),
        ("abs difference x3", difference(target, local_beauty)),
    ], cols=3, scale=0.5).save(priv / "contact-sheet-1440x900.png")

    target_resize = load(root / "artifacts/reference/A-1440x900-dpr1/18-resize-1100x720.png")
    local_partial = load(root / "qa-v5/f0/partial/01-rest.png")
    sheet([
        ("TARGET 1100x720", target_resize),
        ("LOCAL 1100x720 foundation", local_partial),
        ("blend 50/50", blend(target_resize, local_partial)),
    ], cols=3, scale=0.62).save(priv / "contact-sheet-1100x720.png")

    states = ["01-rest", "02-drag-x-110", "03-drag-x-220", "04-drag-x-330", "05-drag-x-440", "06-drag-xy-260-180"]
    sheet([(s, load(root / f"qa-v5/f0/foundation/{s}.png")) for s in states],
          cols=3, scale=0.42).save(root / "qa-v5/f0/offset-sweep-sheet.png")

    sheet([
        ("F1 cover (ships)", load(root / "qa-v5/f1/calibration-cover.png")),
        ("F1 contain (debug)", load(root / "qa-v5/f1/calibration-contain.png")),
        ("F1 stretch (the old bug)", load(root / "qa-v5/f1/calibration-stretch.png")),
        ("clips cover, media only", load(root / "qa-v5/f1/clips-cover.png")),
        ("clips stretch, media only", load(root / "qa-v5/f1/clips-stretch.png")),
        ("clips cover, beauty", load(root / "qa-v5/f1/beauty-cover.png")),
    ], cols=3, scale=0.42).save(root / "qa-v5/f1/mediafit-sheet.png")
    print("evidence written")
