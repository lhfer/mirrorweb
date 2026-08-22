#!/usr/bin/env python3
"""O5F §十C -- the reflection direction, checked end to end.

A summary view over the term decomposition's direction terms -- analytic
normal, faceDirection handling, world reflection vector, environment
rotations, equirect UV, raw HDR texel -- plus the constants compared source
to source: the bundle's envRotation / envRotationX against the uniforms our
truth blob carries. Nothing here re-measures; it reads the decomposition's
sealed comparisons and the two sources, so §十C's answer cannot drift from
§九's.

Output: qa-v5/optics-o5f/reflection-direction.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DEC = REPO / "qa-v5/optics-o5f/portrait-term-decomposition.json"
TRUTH_DIR = REPO / "artifacts/optics-o5f/decomposition"
BUNDLE = REPO / "artifacts/f27/bundles/03lo820gl57km.js"
OUT = REPO / "qa-v5/optics-o5f/reflection-direction.json"

DIRECTION_TERMS = ["analytic-normal", "reflection-vector", "equirect-uv",
                   "raw-env-sample"]


def main() -> int:
    dec = json.loads(DEC.read_text())
    truth = json.loads(
        (TRUTH_DIR / "truth-beauty-1440x900.json").read_text())
    src = truth["body"]["source"]

    data = BUNDLE.read_bytes()
    m = re.search(rb'envRotation:(-?[\d.]+),envRotationX:(-?[\d.]+)', data)
    bundle_rot = ({"envRotation": float(m.group(1)),
                   "envRotationX": float(m.group(2)),
                   "byteOffset": m.start()} if m else None)

    ours_rot = {"envRotation": src["envRotation"],
                "envRotationX": src["envRotationX"]}
    rot_match = (bundle_rot is not None
                 and bundle_rot["envRotation"] == ours_rot["envRotation"]
                 and bundle_rot["envRotationX"] == ours_rot["envRotationX"])

    terms = {t: dec["terms"][t] for t in DIRECTION_TERMS}
    doc = {
        "what": "§十C -- the reflection chain's direction terms, summarised "
                "from the §九 decomposition, plus the rotation constants "
                "compared source to source.",
        "faceDirection": "the analytic normal is multiplied by faceDirection "
                         "in the program and the replay assumes front faces "
                         "(+1); the analytic-normal term's agreement below "
                         "IS the check that this assumption holds on every "
                         "scored card -- a back-face would flip the normal "
                         "and fail the term at both viewports.",
        "rotations": {
            "bundle": bundle_rot,
            "candidateUniforms": ours_rot,
            "match": rot_match,
        },
        "equirectConvention": "u = atan2(d.z, d.x)/2pi + 0.5, v = "
                              "asin(clamp(d.y,-1,1))/pi + 0.5 -- three "
                              "0.185's own equirectUV, quoted in "
                              "o5f_terms.py; validated against the engine "
                              "at 1440x900 before 390x844 was read.",
        "hdrOrientation": "HDRLoader texData.flipY = true; the replay "
                          "samples with the same flip and validates.",
        "terms": terms,
        "allDirectionTermsMatchAtP0": all(
            terms[t]["status"] == "MATCHES" for t in DIRECTION_TERMS),
        "statuses": {t: terms[t]["status"] for t in DIRECTION_TERMS},
    }
    OUT.write_text(json.dumps(doc, indent=1))
    print(json.dumps(doc["statuses"], indent=0))
    print(f"rotations match: {rot_match}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
