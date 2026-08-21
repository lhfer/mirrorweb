#!/usr/bin/env python3
"""O2 System B source contract: byte-anchor everything the System B
implementation must match, in the Target's bundle.

Re-verifies the six O0 sites System B rests on (same ids, same offsets,
raw-byte comparison) and adds the environment-pipeline anchors this round
needs: where the HDR comes from, how it is loaded and parameterised, how
the reflection vector is built and rotated, and the shipped settings.

Every site must be byte-exact at its offset and unique in the bundle.
Optionally re-verifies the live bundle is still byte-identical.

Usage: o2-system-b-forensics.py --out=<json> [--live-bundle=<file>]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BUNDLE = REPO / "artifacts/f27/bundles/03lo820gl57km.js"
O0_DIAGNOSIS = REPO / "qa-v5/optics/o0-source-diagnosis.json"

REUSED_O0_IDS = ["bevelNormal", "envReflection", "fresnelMix", "outputMix",
                 "rimLight", "settingsBH", "materialNotToneMapped"]

NEW_SITES = {
    "presetMapStudio": {
        "verbatim": 'studio:"/hdri/studio_small_03_1k.hdr"',
        "whatItSettles": "the shipped env preset resolves to the SITE-RELATIVE "
                         "/hdri/studio_small_03_1k.hdr (every other, unused "
                         "preset resolves to the drei-assets CDN pin). The "
                         "served file is byte-identical to "
                         "drei-assets@456060a's copy of Poly Haven's CC0 "
                         "studio_small_03 (SHA 29267a4a..., verified against "
                         "both distributions).",
    },
    "hdrLoaderParams": {
        "verbatim": "colorSpace:iR.LinearSRGBColorSpace,minFilter:iR.LinearFilter,"
                    "magFilter:iR.LinearFilter,generateMipmaps:!1,flipY:!0",
        "whatItSettles": "HDRLoader output texture parameters: HalfFloat data "
                         "(loader type), LinearSRGB, Linear min/mag, NO "
                         "mipmaps, flipY true. Sampling is therefore implicit "
                         "level 0.",
    },
    "hdrLoaderClass": {
        "verbatim": "class iM extends iR.DataTextureLoader{constructor(e){"
                    "super(e),this.type=iR.HalfFloatType}",
        "whatItSettles": "the loader is three's HDRLoader (RGBE), type "
                         "HalfFloatType.",
    },
    "equirectMappingAssign": {
        "verbatim": "(0,eB.useLayoutEffect)(()=>{h.mapping="
                    "eF.EquirectangularReflectionMapping},[h])",
        "whatItSettles": "the ONLY post-load processing: equirect mapping "
                         "assignment. No PMREM, no scene.environment -- the "
                         "raw texture goes into the material factory.",
    },
    "reflectVectorWorld": {
        "verbatim": "T=f(A).toVar(),x=f(E).toVar(),C=(0,dB.normalize)"
                    "(x.negate().sub(T.mul((0,dB.dot)(x.negate(),T)"
                    ".mul(2)))).toVar()",
        "whatItSettles": "the reflection vector: world-space bevel normal "
                         "T=f(A) and world-space view direction x=f(E); "
                         "C = reflect(-x, T) = -x - 2*dot(-x,T)*T. f is the "
                         "view->world rotation; A is the analytic bevel "
                         "normal (site bevelNormal), NOT a geometry normal.",
    },
    "envRotationMath": {
        "verbatim": "I=(0,dB.cos)(n.envRotation),w=(0,dB.sin)(n.envRotation),"
                    "R=(0,dB.vec3)(C.x.mul(I).sub(C.z.mul(w)),C.y,"
                    "C.x.mul(w).add(C.z.mul(I))),M=(0,dB.cos)(n.envRotationX),"
                    "L=(0,dB.sin)(n.envRotationX),P=(0,dB.vec3)(R.x,"
                    "R.y.mul(M).sub(R.z.mul(L)),R.y.mul(L).add(R.z.mul(M)))",
        "whatItSettles": "the env sampling direction: the reflection vector "
                         "rotated by envRotation (-2 rad) about Y, then "
                         "envRotationX (0) about X, then equirectUV.",
    },
    "settingsRotationSlice": {
        "verbatim": 'envPreset:"studio",envRotation:-2,envRotationX:0,'
                    'rimWidth:10,rimIntensity:.11',
        "whatItSettles": "the shipped env/rim settings slice inside bH.",
    },
}

QUESTIONS = {
    "sourceFormula": {
        "statement": "finalColor = mix(refractedMedia * tint, envReflection, "
                     "min(saturate(fresnel * envIntensity), envMaxMix)) "
                     "+ whiteRim * rimStrength",
        "bundleIdentifiers": "outputMix site: mix(_.mul(n.tint), D, "
                             "min(saturate(B.mul(n.envIntensity)), "
                             "n.envMaxMix)).add(N.mul(k)) -- _ = refracted "
                             "own-media sum, D = env sample, B = Schlick "
                             "fresnel, N = rimColor (white), k = rim "
                             "smoothstep * rimIntensity",
        "confidence": "SOURCE_READ",
    },
    "fresnelLaw": {
        "statement": "Schlick: B = F0 + (1 - F0) * pow(saturate(1 - "
                     "dot(N, V)), 5) with F0 = 0.045, exponent literal 5; "
                     "N is the analytic bevel normal, V the view direction "
                     "(fresnelMix site).",
        "confidence": "SOURCE_READ",
    },
    "sourceParameters": {
        "fresnelF0": 0.045, "fresnelExponent": 5, "envIntensity": 1.93,
        "envMaxMix": 0.27, "envRotationY": -2, "envRotationX": 0,
        "rimWidth": 10, "rimIntensity": 0.11, "tint": "#ffffff (all-white)",
        "confidence": "SOURCE_READ (settingsBH verbatim)",
    },
    "environmentPipeline": {
        "asset": "/hdri/studio_small_03_1k.hdr, byte-identical to "
                 "drei-assets@456060a / Poly Haven CC0 studio_small_03 "
                 "(SHA 29267a4a...)",
        "loader": "three HDRLoader, HalfFloatType, LinearSRGBColorSpace, "
                  "Linear filters, generateMipmaps false, flipY true",
        "processing": "EquirectangularReflectionMapping assignment ONLY -- "
                      "no PMREM, no scene.environment, no blur; sampled at "
                      "implicit level 0 through equirectUV(P)",
        "confidence": "SOURCE_READ",
    },
    "whereReflectionLives": {
        "statement": "inside the ONE body material's colorNode, as a capped "
                     "LERP toward the env sample -- there is NO separate "
                     "reflection shell, no PBR material, no additive white "
                     "pass (V1 mapping: single mesh, single material carries "
                     "every optical term).",
        "confidence": "SOURCE_READ (V1 target-render-culling-source.json "
                      "singleMaterialAllOptics + this file's outputMix)",
    },
    "toneMappingContext": {
        "statement": "the material is toneMapped:false and the renderer "
                     "never sets a tone mapping (o0 site "
                     "materialNotToneMapped) -- the env LERP output reaches "
                     "the screen without ACES. OUR body is toneMapped under "
                     "ACES exposure 1.05 and tone mapping is FROZEN this "
                     "round; the deviation is pre-registered in "
                     "o2-selected-system.json.",
        "confidence": "SOURCE_READ",
    },
}


def main() -> int:
    args = {a[2:].split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:]}
    data = BUNDLE.read_bytes()
    sha = hashlib.sha256(data).hexdigest()

    o0 = json.loads(O0_DIAGNOSIS.read_text())
    sites = []
    ok = True
    for row in o0["sites"]:
        if row["id"] not in REUSED_O0_IDS:
            continue
        v = row["verbatim"].encode("utf-8", "surrogateescape")
        exact = data[row["byteOffset"]:row["byteOffset"] + len(v)] == v
        occ = data.count(v)
        ok = ok and exact and occ == 1
        sites.append({"id": row["id"], "byteOffset": row["byteOffset"],
                      "occurrences": occ, "byteExact": exact,
                      "reusedFrom": "qa-v5/optics/o0-source-diagnosis.json",
                      "verbatim": row["verbatim"],
                      "whatItSettles": row["whatItSettles"]})
    for sid, spec in NEW_SITES.items():
        v = spec["verbatim"].encode("utf-8")
        off = data.find(v)
        occ = data.count(v)
        exact = off >= 0
        ok = ok and exact and occ == 1
        sites.append({"id": sid, "byteOffset": off, "occurrences": occ,
                      "byteExact": exact, "verbatim": spec["verbatim"],
                      "whatItSettles": spec["whatItSettles"]})

    live = None
    lb = args.get("live-bundle")
    if lb:
        live_sha = hashlib.sha256(Path(lb).read_bytes()).hexdigest()
        live = {"sha256": live_sha, "matchesCapturedBundle": live_sha == sha}
        ok = ok and live["matchesCapturedBundle"]

    doc = {
        "what": "O2 System B source contract: every byte anchor the System B "
                "implementation must match. Six sites re-verified from the "
                "accepted O0 diagnosis; the environment pipeline anchored "
                "fresh this round.",
        "bundle": {"file": str(BUNDLE.relative_to(REPO)), "sha256": sha,
                   "bytes": len(data)},
        "liveBundle": live,
        "sitesTotal": len(sites),
        "sites": sites,
        "questions": QUESTIONS,
        "pass": ok,
    }
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n")
    for s in sites:
        print(f"{s['id']:24s} off={s['byteOffset']} occ={s['occurrences']} "
              f"exact={s['byteExact']}")
    print("SYSTEM B SOURCE CONTRACT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
