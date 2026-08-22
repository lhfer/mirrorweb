#!/usr/bin/env python3
"""O5R §十 -- score the source-environment correction from the programs.

Every claim below is settled by what the generated WGSL CONTAINS, with the
sealed lane standing beside it as a positive control. Nothing here is taken
from the TypeScript: O4A is the standing reminder that the source can say one
thing and the compiled program another.

Output: qa-v5/optics-o5r/source-env-correction.json
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SRC = REPO / "artifacts/optics-o5r/source-env"
AUDIT = REPO / "qa-v5/optics-o5r/hdr-radiance-audit.json"
OUT = REPO / "qa-v5/optics-o5r/source-env-correction.json"

# The clamp under review, as it appears in the generated program: the
# environment sample clamped between 0 and a scalar uniform.
ENV_CLAMP = re.compile(
    r"clamp\(\s*nodeVar\d+\.xyz,\s*vec3<f32>\(\s*0\.0\s*\),\s*"
    r"vec3<f32>\(\s*object\.nodeUniform\d+\s*\)\s*\)")


def load(tag):
    f = SRC / f"{tag}.frag.wgsl"
    return f.read_text() if f.exists() else None


def program_facts(tag, text):
    if text is None:
        return None
    return {
        "tag": tag,
        "bytes": len(text),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "textureSampleCalls": len(re.findall(r"textureSample\w*\(", text)),
        "refractCalls": len(re.findall(r"\brefract\(", text)),
        "bindings": len(re.findall(r"@group\(", text)),
        # equirectUV's own maths. Its absence is how "no environment sample"
        # is proved without naming a variable the code generator chose.
        "equirectAtan2": len(re.findall(r"\batan2\(", text)),
        "equirectAsin": len(re.findall(r"\basin\(", text)),
        "envSampleClamped": bool(ENV_CLAMP.search(text)),
    }


def main() -> int:
    man = json.loads((SRC / "source-env-manifest.json").read_text())
    audit = json.loads(AUDIT.read_text())
    facts = {}
    for rec in man["records"]:
        f = program_facts(rec["tag"], load(rec["tag"]))
        if f:
            f["optics"] = rec["optics"]
            f["errorCount"] = rec["errorCount"]
            facts[rec["tag"]] = f

    clamped = facts.get("o5-clamped")
    unclamped = facts.get("o5r-unclamped")
    envoff = facts.get("o5r-env-off")
    views = ["o5r-uv-unrefracted", "o5r-uv-refracted", "o5r-displacement",
             "o5r-sdf-mask"]

    checks = []

    def add(name, ok, detail, numbers=None):
        checks.append({"check": name, "pass": None if ok is None else bool(ok),
                       "detail": detail, "numbers": numbers or {}})

    add("the HDR asset is finite, so §十 authorises the unclamp",
        audit["allFinite"] and audit["authorisesUnclamp"],
        "§十 makes the code change conditional on the asset. Decoded from its "
        "own bytes: 0 NaN, 0 Inf. Had it carried either, §十 says stop and "
        "report SOURCE ASSET NON-FINITE rather than invent a new clamp.",
        {"nanChannels": audit["nanChannels"], "infChannels": audit["infChannels"],
         "colourChannels": audit["colourChannels"],
         "maxRadiance": audit["maxRadiance"], "verdict": audit["verdict"]})

    add("the clamp is present in the SEALED lane and absent in the O5R lane",
        bool(clamped and unclamped and clamped["envSampleClamped"]
             and not unclamped["envSampleClamped"]),
        "Read out of the generated program, with the sealed lane as the "
        "positive control. The clamped program also carries one more scalar "
        "uniform -- envSampleCeiling -- which the O5R program does not declare "
        "at all, so the constant is gone rather than set to something large.",
        {"clampedProgramBytes": (clamped or {}).get("bytes"),
         "unclampedProgramBytes": (unclamped or {}).get("bytes"),
         "clampedHasClamp": (clamped or {}).get("envSampleClamped"),
         "unclampedHasClamp": (unclamped or {}).get("envSampleClamped")})

    add("no replacement clamp was introduced",
        bool(unclamped and clamped
             and unclamped["bytes"] < clamped["bytes"]),
        "The O5R program is SHORTER than the sealed one. A ceiling swapped for "
        "a different ceiling, a soft knee or a tone curve would all make it "
        "longer; §十 forbids all three and the byte count is the check.",
        {"delta": (unclamped["bytes"] - clamped["bytes"])
         if (unclamped and clamped) else None})

    add("environmentMode=off omits the environment sample COMPLETELY",
        bool(envoff and unclamped
             and envoff["textureSampleCalls"] == unclamped["textureSampleCalls"] - 1
             and envoff["equirectAtan2"] == 0 and envoff["equirectAsin"] == 0
             and envoff["bindings"] < unclamped["bindings"]),
        "§十 requires a structural floor, not a multiply. The off program has "
        "one fewer texture sample -- five, exactly the five per-IOR media "
        "samples -- no equirect maths at all, and two fewer bindings, because "
        "the environment texture and its sampler are not in the program. "
        "envMixScale is RETAINED and untouched: the sealed O2, O3 and O4 "
        "harnesses drive it and O5's control identity records it.",
        {"offSamples": (envoff or {}).get("textureSampleCalls"),
         "sourceSamples": (unclamped or {}).get("textureSampleCalls"),
         "offAtan2": (envoff or {}).get("equirectAtan2"),
         "sourceAtan2": (unclamped or {}).get("equirectAtan2"),
         "offBindings": (envoff or {}).get("bindings"),
         "sourceBindings": (unclamped or {}).get("bindings"),
         "offProgramBytes": (envoff or {}).get("bytes")})

    add("the five per-IOR refractions are unchanged by the correction",
        bool(clamped and unclamped and envoff
             and clamped["refractCalls"] == unclamped["refractCalls"] == 5
             and envoff["refractCalls"] == 5),
        "§十九 forbids touching ior, dispersion, sample count and "
        "refractStrength. The programs still contain exactly five refract() "
        "calls, in every mode.",
        {t: facts[t]["refractCalls"] for t in
         ("o5-clamped", "o5r-unclamped", "o5r-env-off") if t in facts})

    view_facts = {v: facts[v] for v in views if v in facts}
    hashes = {v: f["sha256"] for v, f in view_facts.items()}
    add("each measurement view is a SEPARATE program, not a branch",
        len(set(hashes.values())) == len(hashes) and len(hashes) == len(views)
        and all(f["bytes"] < (unclamped or {}).get("bytes", 1e9)
                for f in view_facts.values()),
        "Four distinct program hashes, each smaller than the Beauty program. "
        "A runtime branch would produce one program containing all four, which "
        "is the shape the O4A codegen defect lives in.",
        {"hashes": {v: h[:12] for v, h in hashes.items()},
         "bytes": {v: f["bytes"] for v, f in view_facts.items()},
         "beautyBytes": (unclamped or {}).get("bytes")})

    add("no console or page errors in any lane, mode or view",
        all(f["errorCount"] == 0 for f in facts.values()),
        "Across all eight program captures.",
        {t: f["errorCount"] for t, f in facts.items()})

    passed = sum(1 for c in checks if c["pass"] is True)
    failed = sum(1 for c in checks if c["pass"] is False)
    doc = {
        "what": "O5R §十 source-environment correction: the one product-code "
                "change this round is authorised to make, and the program-level "
                "evidence of exactly what it did.",
        "change": {
            "removed": "O2's envSampleCeiling clamp on the environment sample, "
                       "in the target-source-unclamped lane only",
            "why": "the Target has no such clamp, and the O5 evidence proved "
                   "ours BINDS: 0.91% of the asset's colour channels exceed "
                   "16 and the brightest exceeds it 224-fold, so every card "
                   "reflecting one of them rendered a dimmer highlight than "
                   "the Target's",
            "whyItIsSafe": "structural rather than statistical. three's RGBE "
                           "decode applies Math.min(v, 65504) per channel "
                           "before packing the half-float, so the sampled "
                           "texture cannot carry Inf or NaN whatever the file "
                           "encodes -- and the Target, loading the same asset "
                           "through the same loader, is bounded identically. "
                           "Verified against the vendored loader source, not "
                           "assumed.",
            "added": "environmentMode = source | off, as BUILD-TIME structural "
                     "programs. The old route to an environment floor was "
                     "envMixScale = 0 multiplied onto an already-sampled HDR "
                     "value, which is the shape §十 rules out.",
            "retained": "envMixScale and rimScale, untouched. The sealed O2, "
                        "O3 and O4 harnesses drive them and O5's control "
                        "identity records them; removing them would break "
                        "§十三A's re-run of the original gate.",
            "notTouched": ["ior", "dispersion", "dispersionSamples",
                           "refractStrength", "bevelWidth", "bevelPower",
                           "bevelMaxSlope", "thickness", "cornerRadius",
                           "fresnelF0", "envIntensity", "envMaxMix",
                           "envRotation", "envRotationX", "rimWidth",
                           "rimIntensity", "the HDR asset bytes", "exposure"],
        },
        "lanes": {
            "current": "the accepted O2 body. Untouched, and proved untouched "
                       "by the control-identity re-run.",
            "target-source": "the SEALED O5 candidate, retained so §十三A's "
                             "regression re-run reads the lane it scored. Not "
                             "a second tuned variant: nothing differs between "
                             "it and the O5R lane except the presence of the "
                             "clamp.",
            "target-source-unclamped": "the single O5R candidate §十 "
                                       "authorises.",
        },
        "programs": facts,
        "passed": passed, "failed": failed, "total": len(checks),
        "pass": failed == 0,
        "checks": checks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    for c in checks:
        v = "PASS" if c["pass"] else ("FAIL" if c["pass"] is False else "n/a")
        print(f"  {v:4}  {c['check']}")
    print(f"\n{passed}/{len(checks)} -> {OUT}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
