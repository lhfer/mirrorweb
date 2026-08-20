#!/usr/bin/env python3
"""Pixel diff between the media-only and glass+media beauty frames.

The FSX-A round reported these two states as byte identical and left it there.
Identical bytes are not an explanation: either the glass genuinely contributes
nothing to those pixels, which would be a finding about the shader, or the
frames were never redrawn. This measures the difference in pixels and pairs it
with the render-layer state that produced each frame, so the two cases cannot be
confused again.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image


def load(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.int16)


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/t1/beauty")
    payload = json.loads((root / "beauty.json").read_text())
    for vp in payload["viewports"]:
        shots = {s["state"]: s for s in vp["shots"]}
        a, b = shots.get("2-media-only"), shots.get("3-glass-media")
        if not a or not b:
            continue
        ia, ib = load(Path(a["png"])), load(Path(b["png"]))
        if ia.shape != ib.shape:
            vp["mediaVsGlassDiff"] = {"error": f"shape {ia.shape} vs {ib.shape}"}
            continue
        d = np.abs(ia - ib)
        per_px = d.max(axis=2)
        total = per_px.size
        changed = int((per_px > 0).sum())
        strong = int((per_px > 8).sum())
        vp["mediaVsGlassDiff"] = {
            "identicalBytes": a["sha256"] == b["sha256"],
            "changedPixels": changed,
            "changedPixelFraction": round(changed / total, 6),
            "pixelsOver8of255": strong,
            "meanAbsDelta": round(float(d.mean()), 4),
            "maxAbsDelta": int(d.max()),
            "p99AbsDelta": int(np.percentile(per_px, 99)),
            "glassMeshesVisibleMediaOnly": a["renderLayerState"]["actual"]["glassMeshesVisible"],
            "glassMeshesVisibleGlassMedia": b["renderLayerState"]["actual"]["glassMeshesVisible"],
            "drawPathMediaOnly": a["renderLayerState"]["drawPath"],
            "drawPathGlassMedia": b["renderLayerState"]["drawPath"],
        }
        # A visible difference map, so the claim is inspectable rather than a number.
        Image.fromarray(np.clip(per_px * 6, 0, 255).astype(np.uint8)).save(
            root / vp["id"] / "diff-media-vs-glass.png")
        print(f"{vp['id']:>10} changed={changed/total:7.4%} mean={d.mean():6.3f} max={d.max():3d} "
              f"glassVisible {a['renderLayerState']['actual']['glassMeshesVisible']} -> "
              f"{b['renderLayerState']['actual']['glassMeshesVisible']}")
    (root / "beauty.json").write_text(json.dumps(payload, indent=2))
    print(f"-> {root}/beauty.json")
