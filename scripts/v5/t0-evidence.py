#!/usr/bin/env python3
"""T0 evidence: the render loop, and the two comparisons it used to falsify.

Local pixels only. Frames are capped once, at 720 px, on the way in -- the FSX-A
bundle capped at 900 in the script and 720 in the tree, so re-running re-encoded
committed frames and invalidated their hashes.
"""
from __future__ import annotations
import json, shutil
from pathlib import Path
from PIL import Image

ART = Path("artifacts/t1")
PUB = Path("qa-v5/t1")
CAP = 720
VPS = ["1440x900", "390x844", "700x700"]
STATES = ["2-media-only", "3-glass-media", "diff-media-vs-glass"]

if __name__ == "__main__":
    (PUB / "local" / "t0-render-loop").mkdir(parents=True, exist_ok=True)
    for vp in VPS:
        for st in STATES:
            src = ART / "beauty-before" / vp / f"{st}.png"
            if not src.exists():
                continue
            im = Image.open(src).convert("RGB")
            im.thumbnail((CAP, CAP), Image.LANCZOS)
            im.save(PUB / "local" / "t0-render-loop" / f"{vp}-{st}.png", optimize=True)
    # Three recording frames per device: first, middle, last.
    for name in ["desktop", "mobile"]:
        frames = sorted((ART / "recording-before" / name).glob("*.png"))
        if not frames:
            continue
        for tag, p in [("first", frames[0]), ("middle", frames[len(frames) // 2]),
                       ("last", frames[-1])]:
            im = Image.open(p).convert("RGB")
            im.thumbnail((CAP, CAP), Image.LANCZOS)
            im.save(PUB / "local" / "t0-render-loop" / f"recording-{name}-{tag}.png", optimize=True)
    shutil.copy2(ART / "recording-before/recording.json", PUB / "recording.json")
    beauty = json.loads((ART / "beauty-before/beauty.json").read_text())
    # The JSON is the evidence; the full-resolution frames stay under artifacts/.
    for vp in beauty["viewports"]:
        for shot in vp["shots"]:
            shot["png"] = shot["png"].replace("artifacts/t1/beauty-before/",
                                              "artifacts/ (git-ignored) ")
    (PUB / "beauty-before.json").write_text(json.dumps(beauty, indent=2))
    print("t0 evidence assembled")
