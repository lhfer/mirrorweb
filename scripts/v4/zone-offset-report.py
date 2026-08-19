#!/usr/bin/env python3
"""Per-zone refraction-offset spread and clamp saturation for one probe run.

Reported in raw 8-bit channel levels of the offset debug view. Saturation is
counted at the endpoints, so it does not depend on the renderer's output
transfer; the spread is comparable between two runs of the same build pipeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def main() -> None:
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    commit = sys.argv[3] if len(sys.argv) > 3 else "unspecified"

    probe = json.loads((src / "probe.json").read_text())
    quad = np.array(probe["centreQuad"]) * np.array([1440, 900])
    zones_img = np.asarray(Image.open(src / "optical-zones.png").convert("RGB")).astype(int)
    offset_img = np.asarray(Image.open(src / "refraction-offset.png").convert("RGB")).astype(int)

    x0, y0 = int(quad[:, 0].min()), int(quad[:, 1].min())
    x1, y1 = int(quad[:, 0].max()), int(quad[:, 1].max())
    zones_img, offset_img = zones_img[y0:y1, x0:x1], offset_img[y0:y1, x0:x1]

    r, g, b = zones_img[..., 0], zones_img[..., 1], zones_img[..., 2]
    peak = zones_img.max(axis=2)
    zones = {
        "shoulder": (r == peak) & (r > 60) & (g < r - 40) & (b < r - 40),
        "strongRim": (g == peak) & (g > 60) & (r < g - 40) & (b < g - 40),
        "sidewall": (b == peak) & (b > 60) & (r < b - 40) & (g < b - 40),
        "centreFace": (abs(r - g) < 12) & (abs(g - b) < 12) & (r > 60) & (r < 220),
    }

    ox, oy = offset_img[..., 0], offset_img[..., 1]
    report = {
        "note": "Refraction-offset debug crossed with the one-hot optical-zones debug, "
                "shell off, at rest, pointer centred, centre card only. Levels are raw "
                "8-bit channel values of the offset debug view, where 128 would be zero "
                "displacement. Clamp saturation is counted at the 0 and 255 endpoints and "
                "so is independent of the renderer's output transfer.",
        "source": "scripts/v4/capture-offset-saturation.mjs --shell=off",
        "commit": commit,
        "cardBox": [x0, y0, x1, y1],
        "maxRefractionUv": 0.125,
        "zones": {},
    }
    for name, mask in zones.items():
        count = int(mask.sum())
        if count == 0:
            continue
        pinned = ((ox <= 1) | (ox >= 254) | (oy <= 1) | (oy >= 254)) & mask
        report["zones"][name] = {
            "pixels": count,
            "pinnedAtClamp": int(pinned.sum()),
            "pinnedFraction": round(float(pinned.sum()) / count, 5),
            "offsetLevelRange": {
                "x": [int(ox[mask].min()), int(ox[mask].max())],
                "y": [int(oy[mask].min()), int(oy[mask].max())],
            },
            "offsetLevelSpread": {
                "x": int(ox[mask].max() - ox[mask].min()),
                "y": int(oy[mask].max() - oy[mask].min()),
            },
        }
    print(json.dumps(report["zones"], indent=2))
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
