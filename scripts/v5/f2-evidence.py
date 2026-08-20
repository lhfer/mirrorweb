#!/usr/bin/env python3
"""F2 visual evidence: per-viewport Target/local overlays and a contact sheet.

Target pixels go to qa-v5/private/ (git-ignored); local-only output is tracked.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

VPS = ["1100x720", "1366x768", "1440x900", "1920x1080", "390x844", "844x390"]

def font(sz):
    try: return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", sz)
    except OSError: return ImageFont.load_default()

def label(img, text, sz=22):
    out = img.copy(); d = ImageDraw.Draw(out)
    d.rectangle([0, 0, 14 + int(len(text) * sz * 0.62), sz + 14], fill=(0, 0, 0))
    d.text((8, 6), text, fill=(255, 255, 255), font=font(sz))
    return out

def edges(base, other):
    """Target in red, local in cyan: aligned structure reads neutral."""
    a = np.asarray(base.convert("L"), np.float32)
    b = np.asarray(other.resize(base.size).convert("L"), np.float32)
    out = np.zeros(a.shape + (3,), np.float32)
    out[:, :, 0] = a; out[:, :, 1] = b; out[:, :, 2] = b
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))

if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    priv = root / "qa-v5/private/f2"; priv.mkdir(parents=True, exist_ok=True)
    tiles = []
    for vp in VPS:
        t = Image.open(root / f"artifacts/v5-target/{vp}-dpr1.png").convert("RGB")
        l = Image.open(root / f"qa-v5/f2/local/{vp}/01-rest.png").convert("RGB")
        b = Image.open(root / f"qa-v5/f2/beauty/{vp}/01-rest.png").convert("RGB")
        ov = edges(t, l)
        ov.save(priv / f"overlay-{vp}.png")
        Image.blend(t, l.resize(t.size), 0.5).save(priv / f"blend-{vp}.png")
        row = Image.new("RGB", (t.width * 3 + 40, t.height + 20), (16, 16, 20))
        row.paste(label(t, f"TARGET {vp}"), (10, 10))
        row.paste(label(l, f"LOCAL foundation"), (t.width + 20, 10))
        row.paste(label(ov, "TARGET red / LOCAL cyan"), (t.width * 2 + 30, 10))
        row.save(priv / f"triptych-{vp}.png")
        tiles.append((vp, row, b))

    # One contact sheet, every viewport scaled to a common width.
    W = 1500
    parts = []
    for vp, row, _ in tiles:
        k = W / row.width
        parts.append(row.resize((W, max(1, int(row.height * k)))))
    sheet = Image.new("RGB", (W + 20, sum(p.height for p in parts) + 20 * (len(parts) + 1)), (12, 12, 16))
    y = 20
    for p in parts:
        sheet.paste(p, (10, y)); y += p.height + 20
    sheet.save(priv / "contact-sheet-six-viewports.png")

    # Local-only beauty sheet is safe to track.
    bw = 760
    bparts = [b.resize((bw, max(1, int(b.height * bw / b.width)))) for _, _, b in tiles]
    cols, rows_n = 3, 2
    cw = max(p.width for p in bparts); ch = max(p.height for p in bparts)
    bs = Image.new("RGB", (cols * cw + 40, rows_n * ch + 40), (16, 16, 20))
    for n, (p, (vp, _, _)) in enumerate(zip(bparts, tiles)):
        r, c = divmod(n, cols)
        bs.paste(label(p, vp), (10 + c * (cw + 10), 10 + r * (ch + 10)))
    bs.save(root / "qa-v5/f2/beauty-six-viewports.png")
    print("f2 evidence written")
