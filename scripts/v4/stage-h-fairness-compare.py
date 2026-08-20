#!/usr/bin/env python3
"""Compare two independent capture runs of the same fixed state set.

Two different standards, on purpose:

  media-only  strict byte equality. This layer is the media planes and the
              gutter with the glass, the shell and the typography hidden, so it
              carries no GPU-dependent shading. If two runs disagree here they
              were not looking at the same media, and the pair is not a fair
              comparison at all.

  beauty      perceptual tolerance. This is a WebGPU render; asking two
              processes for byte equality would be asking the wrong question.
              A state passes when no pixel moves more than `maxDelta` levels and
              the fraction of pixels moving more than 2 levels stays under
              `changedFraction`.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image

run_a, run_b, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
MAX_DELTA = 8
CHANGED_FRACTION = 0.001
KEY_STATES = ["high-texture", "left-tilt", "right-tilt", "partial-viewport"]

a = json.loads((run_a / "fairness-report.json").read_text())
b = json.loads((run_b / "fairness-report.json").read_text())

rows = []
for state in a["mediaOnlyHashes"]:
    media_ok = a["mediaOnlyHashes"][state] == b["mediaOnlyHashes"][state]
    x = np.asarray(Image.open(run_a / "beauty" / f"{state}.png").convert("RGB")).astype(np.int16)
    y = np.asarray(Image.open(run_b / "beauty" / f"{state}.png").convert("RGB")).astype(np.int16)
    d = np.abs(x - y)
    max_delta = int(d.max())
    changed = float((d.max(axis=2) > 2).mean())
    beauty_ok = max_delta <= MAX_DELTA and changed <= CHANGED_FRACTION
    rows.append({
        "stateId": state, "mediaOnlyByteIdentical": media_ok,
        "beautyMaxDelta": max_delta, "beautyChangedFraction": round(changed, 6),
        "beautyWithinTolerance": beauty_ok,
        "valid": media_ok and beauty_ok,
        "isKeyState": state in KEY_STATES,
    })

valid = [r for r in rows if r["valid"]]
blocked = [r["stateId"] for r in rows if not r["valid"]]
key_lost = [s for s in KEY_STATES if s in blocked]
report = {
    "generator": "stage-h-fairness-compare",
    "runs": [run_a.name, run_b.name],
    "stateManifestHash": a["stateManifestHash"],
    "manifestHashEqualAcrossRuns": a["stateManifestHash"] == b["stateManifestHash"],
    "standards": {
        "mediaOnly": "byte equality, no tolerance",
        "beauty": f"max per-pixel delta <= {MAX_DELTA} levels and <= {CHANGED_FRACTION:.3%} of pixels moving more than 2 levels",
        "why": "media-only carries no GPU-dependent shading, so byte equality is the right question there; beauty is a WebGPU render and byte equality across processes is not.",
    },
    "totalStates": len(rows),
    "mediaOnlyByteIdentical": sum(1 for r in rows if r["mediaOnlyByteIdentical"]),
    "beautyWithinTolerance": sum(1 for r in rows if r["beautyWithinTolerance"]),
    "validStateCount": len(valid),
    "blockedStates": blocked,
    "keyStates": KEY_STATES,
    "keyStatesLost": key_lost,
    "keyStatesAllPresent": not key_lost,
    "meetsBlindMinimum": len(valid) >= 12 and not key_lost,
    "states": rows,
}
out.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({k: report[k] for k in [
    "mediaOnlyByteIdentical", "beautyWithinTolerance", "validStateCount",
    "blockedStates", "keyStatesAllPresent", "meetsBlindMinimum"]}, indent=2))
