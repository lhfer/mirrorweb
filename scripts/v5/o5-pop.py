#!/usr/bin/env python3
"""O5 §九.12 -- temporal pop over the recorded sequences.

The sealed coding, unchanged: per recorded frame, the FULL-FRAME count of
bright low-chroma pixels (luma > 200, chroma < 40). A pop is a
discontinuity, so the test is on adjacent frames --

  * no adjacent-frame RELATIVE change above 40%
  * no frame at zero while both its neighbours are non-zero (a rim break)

Full frame rather than per card, for the reason registered before capture:
a per-card measure would need per-frame scroll and pointer state, which the
CDP screencast does not carry, and reconstructing it afterwards would be
exactly the post-hoc re-interpretation §十一 forbids this round. The static
label ink is included and is CONSTANT, so it cannot manufacture a
discontinuity -- it can only dilute one, which the recorded per-lane
comparison makes visible.

The gate is scored on the CANDIDATE. Control and Target are measured the
same way and recorded beside it, so a reader can tell a candidate-specific
pop from a property of the metric.

Usage: o5-pop.py [--recordings=<dir>] [--out=<json>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent

LUMA_MIN = 200.0
CHROMA_MAX = 40.0
MAX_REL_JUMP = 0.40


def counts_for(frame_dir: Path) -> list[int]:
    out = []
    for f in sorted(frame_dir.glob("f*.jpg")):
        a = np.asarray(Image.open(f).convert("RGB"), dtype=np.float32)
        lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
        chroma = a.max(axis=2) - a.min(axis=2)
        out.append(int(((lum > LUMA_MIN) & (chroma < CHROMA_MAX)).sum()))
    return out


def judge(counts: list[int]) -> dict:
    if len(counts) < 3:
        return {"frames": len(counts), "fired": True,
                "reasons": ["too few frames to judge a discontinuity"]}
    reasons = []
    jumps = []
    for i in range(1, len(counts)):
        prev, cur = counts[i - 1], counts[i]
        base = max(prev, 1)
        rel = abs(cur - prev) / base
        jumps.append(rel)
        if rel > MAX_REL_JUMP:
            reasons.append(f"frame {i}: {prev} -> {cur} ({rel:.1%} > "
                           f"{MAX_REL_JUMP:.0%})")
    for i in range(1, len(counts) - 1):
        if counts[i] == 0 and counts[i - 1] > 0 and counts[i + 1] > 0:
            reasons.append(f"frame {i}: rim break -- zero between "
                           f"{counts[i - 1]} and {counts[i + 1]}")
    return {"frames": len(counts),
            "minCount": int(min(counts)), "maxCount": int(max(counts)),
            "meanCount": int(np.mean(counts)),
            "maxAdjacentRelJump": round(float(max(jumps)), 4) if jumps else None,
            "fired": bool(reasons),
            "reasons": reasons[:8],
            "reasonCount": len(reasons)}


def main() -> int:
    opts = {"recordings": REPO / "artifacts/optics-o5/recordings",
            "out": REPO / "artifacts/optics-o5/recordings/pop.json"}
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k in opts:
            opts[k] = Path(v)
    rd = Path(opts["recordings"])
    index = json.loads((rd / "recordings-index.json").read_text())

    seqs = []
    for rec in index["recordings"]:
        d = REPO / rec["dir"]
        counts = counts_for(d)
        v = judge(counts)
        seqs.append({"lane": rec["lane"], "viewport": rec["viewport"],
                     "sequence": rec["sequence"], "asset": rec["asset"],
                     "dir": rec["dir"], **v,
                     "counts": counts})
        print(f"{rec['lane']:10s} {rec['viewport']:9s} {rec['sequence']:22s} "
              f"{rec['asset']:15s} fired={v['fired']} "
              f"maxJump={v.get('maxAdjacentRelJump')}")

    scored = [s for s in seqs if s["lane"] == "candidate"]
    result = {
        "what": "O5 §九.12 -- temporal pop, scored on the candidate "
                "lane with the control and Target measured identically "
                "alongside it.",
        "coding": {"lumaMin": LUMA_MIN, "chromaMax": CHROMA_MAX,
                   "maxAdjacentRelativeJump": MAX_REL_JUMP,
                   "scope": "full frame", "sealed": True},
        "scoredLane": "candidate",
        "pass": bool(scored) and all(not s["fired"] for s in scored),
        "sequences": [{k: v for k, v in s.items() if k != "counts"} for s in seqs],
        "countsByClip": {f"{s['lane']}/{s['viewport']}-{s['sequence']}-{s['asset']}":
                         s["counts"] for s in seqs},
    }
    Path(opts["out"]).write_text(json.dumps(result, indent=1))
    print(f"\ncandidate pass: {result['pass']}\n-> {opts['out']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
