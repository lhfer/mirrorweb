#!/usr/bin/env python3
"""Mean luminance and gradient energy of the centred card region of a frame.

Used to pick which real grid cell plays the role of the bright / dark /
high-texture / low-texture review state, instead of assuming one.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def stats(path: Path) -> dict[str, float]:
    with Image.open(path) as opened:
        opened.load()
        rgb = np.asarray(opened.convert("RGB"), dtype=np.float32) / 255.0
    height, width = rgb.shape[:2]
    half_w, half_h = int(width * 0.105), int(height * 0.135)
    cx, cy = width // 2, height // 2
    patch = rgb[cy - half_h:cy + half_h, cx - half_w:cx + half_w]
    luma = patch[..., 0] * 0.2126 + patch[..., 1] * 0.7152 + patch[..., 2] * 0.0722
    gx = np.abs(np.diff(luma, axis=1)).mean()
    gy = np.abs(np.diff(luma, axis=0)).mean()
    return {"centerLuma": float(luma.mean()), "centerTexture": float((gx + gy) / 2)}


def main() -> int:
    files = [Path(item) for item in sys.argv[1:]]
    print(json.dumps([stats(file) for file in files]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
