#!/usr/bin/env python3
"""VC2 §八.5 -- does the chrome improvement survive real motion?

A still proves the scrim is there when nothing is happening. §八 asks whether
it still holds during a real drag, flick and touch, which is a different
question: the cards moving under it change what it is darkening, and a fixed
overlay could in principle be composited differently while the page is busy.

So the same measurement the stills got is run over the recorded frames: mean
luma of the bottom 144 rows of every sampled frame, Target against Candidate,
on the same gesture with matched media and matched copy. Frames are paired by
normalised position in the clip and grouped by frame size, so the orientation
scenario -- where the frame changes shape mid-recording -- is compared like
with like.

Usage: vc2-recording-band.py [--a=<target rec dir>] [--b=<candidate rec dir>]
                             [--out=<json>] [--every=8]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent


def band_luma(p: Path, rows: int = 144) -> tuple[float, tuple[int, int]]:
    a = np.asarray(Image.open(p).convert("RGB"), dtype=np.float64)
    band = a[-rows:]
    y = 0.2126 * band[:, :, 0] + 0.7152 * band[:, :, 1] + 0.0722 * band[:, :, 2]
    return float(y.mean()), (a.shape[1], a.shape[0])


def series(dirp: Path, every: int) -> list[tuple[float, float, tuple[int, int]]]:
    files = sorted(dirp.glob("*.jpg"))
    if not files:
        return []
    out = []
    for i in range(0, len(files), every):
        mean, size = band_luma(files[i])
        out.append((i / max(len(files) - 1, 1), mean, size))
    return out


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    a_dir = REPO / args.get("a", "artifacts/visual-convergence/recordings-after/target")
    b_dir = REPO / args.get("b", "artifacts/visual-convergence/recordings-after/review-target")
    out_p = REPO / args.get("out", "artifacts/visual-convergence/recording-band.json")
    every = int(args.get("every", 8))

    doc = {"what": "bottom-144-row mean luma over recorded frames, Target vs Candidate, "
                   "same gesture, matched media and copy",
           "a": str(a_dir.relative_to(REPO)), "b": str(b_dir.relative_to(REPO)),
           "sampledEveryNthFrame": every, "scenarios": {}}
    for sub in sorted(p for p in a_dir.iterdir() if p.is_dir()):
        name = sub.name
        pb = b_dir / name
        if not pb.exists():
            continue
        sa, sb = series(sub, every), series(pb, every)
        if not sa or not sb:
            continue
        # Pair by normalised clip position, within matching frame sizes.
        pairs = []
        for fa, ma, siz in sa:
            same = [(abs(fb - fa), mb) for fb, mb, sizb in sb if sizb == siz]
            if not same:
                continue
            _, mb = min(same, key=lambda x: x[0])
            pairs.append((round(fa, 4), round(ma, 3), round(mb, 3), round(mb - ma, 3)))
        if not pairs:
            continue
        d = np.array([p[3] for p in pairs])
        idx = json.loads((sub / "index.json").read_text())
        doc["scenarios"][name] = {
            "vp": idx.get("vp"), "resizeTo": idx.get("resizeTo"),
            "framesCompared": len(pairs),
            "bandDelta": {"mean": round(float(d.mean()), 3),
                          "median": round(float(np.median(d)), 3),
                          "p95Abs": round(float(np.percentile(np.abs(d), 95)), 3),
                          "maxAbs": round(float(np.abs(d).max()), 3)},
            "targetBandMean": round(float(np.mean([p[1] for p in pairs])), 3),
            "candidateBandMean": round(float(np.mean([p[2] for p in pairs])), 3),
            "samples": pairs[:: max(1, len(pairs) // 12)],
        }
        b = doc["scenarios"][name]["bandDelta"]
        print(f"{name:<26} frames={len(pairs):<4} bandΔ mean={b['mean']:+7.3f} "
              f"p95|Δ|={b['p95Abs']:6.3f} max|Δ|={b['maxAbs']:6.3f}")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, indent=1))
    print(f"-> {out_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
