#!/usr/bin/env python3
"""Is any label ink outside the card it belongs to?

The structural check says the clip layer has `overflow: hidden` at the card box.
This is the pixel version of the same question: render the labels alone, take
every non-background pixel, and count how many fall outside the union of the
card silhouettes. A container that is too big, a clip that is not applied, or
text escaping into the gutter all show up here as ink where no card is.

Also writes a card-mask / label-bounds overlay so the claim is inspectable.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw


def quad_mask(size, quads, grow=0.0):
    """Rasterise the card quads. `grow` dilates each quad about its centre."""
    img = Image.new("L", size, 0)
    d = ImageDraw.Draw(img)
    for q in quads:
        if grow:
            cx = sum(p[0] for p in q) / 4.0
            cy = sum(p[1] for p in q) / 4.0
            q = [[cx + (p[0] - cx) * (1 + grow), cy + (p[1] - cy) * (1 + grow)] for p in q]
        d.polygon([tuple(p) for p in q], fill=255)
    return np.asarray(img) > 0


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/t1/depth-clipping")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "qa-v5/t1/label-ink.json")
    report = {"method": "labels-only capture; ink = any pixel above the background floor; "
                        "card silhouette = the projected card mid-plane quads",
              "inkThreshold": 24, "viewports": [], "assertions": []}
    for shot in sorted(root.glob("*-labels-only.png")):
        vid = shot.name.replace("-labels-only.png", "")
        quads = json.loads((root / f"{vid}-quads.json").read_text())
        img = np.asarray(Image.open(shot).convert("RGB"), dtype=np.int16)
        h, w, _ = img.shape
        ink = img.max(axis=2) > report["inkThreshold"]
        cards = quad_mask((w, h), [c["quad"] for c in quads["cards"]])
        # 1 px of tolerance for the rasteriser's own edge, not for the result.
        cards_grown = quad_mask((w, h), [c["quad"] for c in quads["cards"]], grow=0.004)
        outside = int((ink & ~cards_grown).sum())
        total = int(ink.sum())
        entry = {"id": vid, "viewport": [w, h], "inkPixels": total,
                 "inkOutsideCardSilhouettes": outside,
                 "fractionOutside": round(outside / total, 8) if total else 0.0,
                 "cardsRasterised": len(quads["cards"]),
                 "labelsOnlyPng": str(shot)}
        report["viewports"].append(entry)
        # Overlay: green = card silhouettes, magenta = ink outside them.
        ov = np.zeros((h, w, 3), dtype=np.uint8)
        ov[..., 1] = np.where(cards, 60, 0)
        ov[ink] = [255, 255, 255]
        ov[ink & ~cards_grown] = [255, 0, 255]
        d = ImageDraw.Draw(Image.fromarray(ov))
        Image.fromarray(ov).save(root / f"{vid}-mask-and-bounds.png")
        print(f"{vid:>10} ink={total:8d} outside={outside:6d} ({outside/max(total,1):.4%})")
    worst = max((v["fractionOutside"] for v in report["viewports"]), default=0.0)
    report["assertions"].append({
        "assertion": "no label ink outside the card silhouettes",
        "pass": worst <= 0.001,
        "detail": {"worstFractionOutside": worst, "limit": 0.001,
                   "note": "the limit is a rasteriser edge allowance, not a text allowance"}})
    report["passed"] = sum(1 for a in report["assertions"] if a["pass"])
    report["total"] = len(report["assertions"])
    report["verdict"] = "PASS" if report["passed"] == report["total"] else "FAIL"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"label ink {report['verdict']}  worst outside fraction {worst}")
