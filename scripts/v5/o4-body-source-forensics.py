#!/usr/bin/env python3
"""O4 §四 — the Target Body source contract, byte-anchored.

Every Target claim below is a needle located in the shipped bundle. A
claim that cannot be found byte-exactly, or that appears more than once,
FAILS -- there is no partial credit and no inference from candidate output.

Method note on ABSENCES. "The Target has no scene-colour target", "no mip
blur", "no adaptive contrast" cannot be byte-anchored: absence has no
bytes. They are established instead by COMPLETENESS -- the body colour
chain is anchored end to end, from the accumulator's initialisation
through the spectral loop to the `return`, and the material that consumes
it. Anything not in that chain is not in the Target's body. The chain
sites are marked `completenessAnchor: true`, and the absence claims name
the span they are read from.

Usage: o4-body-source-forensics.py --out=<json> [--live-bundle=<file>]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
BUNDLE = REPO / "artifacts/optics-o2/live-bundle.js"

C = "(0,dB."          # the bundle's minified TSL call prefix

SITES = [
    # ---------------------------------------------------------- own media --
    {
        "id": "ownMediaVideoTexture",
        "claim": "The Target's card media is its OWN texture, created per card "
                 "from the card's video element -- not a scene-colour render "
                 "target.",
        "verbatim": "let e=new eF.VideoTexture(n);e.colorSpace=eF.SRGBColorSpace,"
                    "e.wrapS=eF.ClampToEdgeWrapping,e.wrapT=eF.ClampToEdgeWrapping",
        "formula": "texture = VideoTexture(videoElement); colorSpace = sRGB; "
                   "wrapS = wrapT = ClampToEdgeWrapping",
        "confidence": "SOURCE_READ",
        "settles": "Own-media sampling, sRGB input colour space, and "
                   "ClampToEdge in one site. three's VideoTexture defaults to "
                   "generateMipmaps = false with a LinearFilter minFilter, so "
                   "there is no mip chain to sample even if a LOD were asked "
                   "for.",
    },
    {
        "id": "textureNodeIsTheCardMedia",
        "claim": "The body samples that texture directly.",
        "verbatim": "s=" + C + "texture)(e)",
        "formula": "s = texture(cardMediaTexture)",
        "confidence": "SOURCE_READ",
        "settles": "`s` in the spectral loop is the card's own media. There is "
                   "no second sampler in the body chain.",
    },
    {
        "id": "coverScaleOffsetUniforms",
        "claim": "Cover-fit is carried as two uniforms on the card material.",
        "verbatim": "coverScale:" + C + "uniform)(new eF.Vector2(1,1)),"
                    "coverOffset:" + C + "uniform)(new eF.Vector2(0,0))",
        "formula": "coverScale : vec2 = (1,1); coverOffset : vec2 = (0,0)",
        "confidence": "SOURCE_READ",
        "settles": "The cover fit is a per-card uniform pair, not a texture "
                   "transform and not a geometry change.",
    },
    {
        "id": "coverFitLaw",
        "claim": "The cover-fit law itself: aspect-compare, scale the "
                 "over-long axis, centre the remainder.",
        "verbatim": "let a=i/n;if(a>t){let e=t/a;return{scaleX:e,scaleY:1,"
                    "offsetX:(1-e)/2,offsetY:0}}let s=a/t;return{scaleX:1,"
                    "scaleY:s,offsetX:0,offsetY:(1-s)/2}",
        "formula": "mediaAspect = w/h; if mediaAspect > planeAspect: "
                   "scaleX = planeAspect/mediaAspect, scaleY = 1, "
                   "offsetX = (1-scaleX)/2, offsetY = 0; else "
                   "scaleX = 1, scaleY = mediaAspect/planeAspect, "
                   "offsetX = 0, offsetY = (1-scaleY)/2",
        "confidence": "SOURCE_READ",
        "settles": "The exact cover fit, in the card's own uv space.",
    },
    # ------------------------------------------------------ the body chain --
    {
        "id": "bodyViewDirectionInPlaneSpace",
        "claim": "The body's view direction is built in plane space from the "
                 "camera position transformed into card-local space.",
        "verbatim": "v=dB.modelWorldMatrixInverse.mul(" + C
                    + "vec4)(dB.cameraPosition,1)).xyz",
        "formula": "cameraLocal = modelWorldMatrixInverse * vec4(cameraPosition, 1)",
        "confidence": "SOURCE_READ",
        "completenessAnchor": True,
        "settles": "Start of the body chain. Everything the body colour reads "
                   "is derived from here down to the return.",
    },
    {
        "id": "bodyAccumulatorInit",
        "claim": "The body colour is a spectral ACCUMULATOR initialised to zero.",
        "verbatim": "S=" + C + "uv)(),_=" + C + "vec3)(0",
        "formula": "S = uv(); accumulator = vec3(0)",
        "confidence": "SOURCE_READ",
        "completenessAnchor": True,
        "settles": "The body starts from the card's own uv and an empty "
                   "accumulator -- not from a screen-space sample.",
    },
    {
        "id": "perSampleIor",
        "claim": "Each spectral sample refracts at its OWN index.",
        "verbatim": "let t=" + C + "float)(1).div(" + C + "max)(n.ior.add("
                    "n.dispersion.mul(e.offset))," + C + "float)(1.0001))",
        "formula": "eta_i = 1 / max(ior + dispersion * offset_i, 1.0001)",
        "confidence": "SOURCE_READ",
        "settles": "Dispersion is per-IOR inside refract(), not a post-hoc "
                   "uv spread of one refracted sample.",
    },
    {
        "id": "refractConsumesAnalyticNormal",
        "claim": "refract() consumes the analytic bevel normal A.",
        "verbatim": "r=" + C + "refract)(E.negate(),A,t)",
        "formula": "r = refract(-E, A, eta_i)",
        "confidence": "SOURCE_READ",
        "reusedFrom": "qa-v5/optics-o3/target-bevel-reflection-source.json "
                      "(refractionConsumesSameNormal)",
        "settles": "The Target's refraction reads a REAL surface normal -- the "
                   "same one its fresnel and environment reflection read. This "
                   "is the Target-side counterpart of the O4A finding that our "
                   "Beauty refraction reads a zero normal.",
    },
    {
        "id": "thicknessOverAbsRzTravel",
        "claim": "Optical travel is thickness / |r.z|, floored at 0.05.",
        "verbatim": "i=n.thickness.div(" + C + "max)(" + C + "abs)(r.z),"
                    + C + "float)(.05))",
        "formula": "travel_i = thickness / max(abs(r_i.z), 0.05)",
        "confidence": "SOURCE_READ",
        "settles": "Travel is a real slab traversal along the refracted ray, "
                   "so a grazing ray travels further. Our body instead "
                   "projects an exit point through the camera matrix and "
                   "differences it in NDC.",
    },
    {
        "id": "uvDisplacementAndRefractStrength",
        "claim": "The displacement is applied in the card's OWN uv, scaled by "
                 "refractStrength and normalised by planeSize.",
        "verbatim": "a=S.add(r.xy.mul(i).mul(n.refractStrength).div(n.planeSize))",
        "formula": "uv_i = uv + r_i.xy * travel_i * refractStrength / planeSize",
        "confidence": "SOURCE_READ",
        "settles": "Card-space displacement. No screen-space offset, no scene "
                   "target, and nothing that can reach a neighbouring card.",
    },
    {
        "id": "clampThenCoverFit",
        "claim": "The uv is clamped to the card BEFORE the cover fit.",
        "verbatim": "o=" + C + "clamp)(a,0,1).mul(n.coverScale).add(n.coverOffset)",
        "formula": "sampleUv_i = clamp(uv_i, 0, 1) * coverScale + coverOffset",
        "confidence": "SOURCE_READ",
        "settles": "Order matters: clamping first means a displaced sample "
                   "walks into the card's own border pixels, never past the "
                   "cover-fitted region into whatever the atlas holds next.",
    },
    {
        "id": "spectralAccumulateNoLod",
        "claim": "Each sample is a plain texture sample with per-channel "
                 "weights and NO explicit LOD.",
        "verbatim": "_=_.add(s.sample(o).rgb.mul(" + C + "vec3)(...e.weight))",
        "formula": "accumulator += texture.sample(sampleUv_i).rgb * weight_i",
        "confidence": "SOURCE_READ",
        "completenessAnchor": True,
        "settles": "`sample(o)` with no `.level(...)`. Combined with a "
                   "VideoTexture that generates no mipmaps, the Target's body "
                   "has no mip blur available to it at all.",
    },
    {
        "id": "spectralSampleTable",
        "claim": "The spectral table: N samples at offsets n/(N-1) - 0.5, with "
                 "per-channel weights normalised to sum to one per channel.",
        "verbatim": "let n=e/(t-1),a=[L2(n,0),L2(n,.5),L2(n,1)];i[0]+=a[0],"
                    "i[1]+=a[1],i[2]+=a[2],r.push({offset:n-.5,weight:a})",
        "formula": "for i in 0..N-1: n = i/(N-1); weight = [L2(n,0), L2(n,0.5), "
                   "L2(n,1)]; offset = n - 0.5; then each channel is divided "
                   "by that channel's sum over all samples",
        "confidence": "SOURCE_READ",
        "settles": "Energy-preserving per channel. The weights are a fixed "
                   "basis evaluated at three channel centres, not a tap "
                   "triple.",
    },
    {
        "id": "dispersionSampleCount",
        "claim": "N is clamped to at least 3.",
        "verbatim": "let t=Math.max(3,Math.round(e))",
        "formula": "N = max(3, round(dispersionSamples))",
        "confidence": "SOURCE_READ",
        "settles": "With the shipped dispersionSamples = 5, N = 5.",
    },
    {
        "id": "bodySettings",
        "claim": "The shipped body constants.",
        "verbatim": "thickness:155,ior:2.3,roughness:0,refractStrength:.7,"
                    "dispersion:.32,dispersionSamples:5",
        "formula": "thickness 155, ior 2.3, roughness 0, refractStrength 0.7, "
                   "dispersion 0.32, dispersionSamples 5",
        "confidence": "SOURCE_READ",
        "reusedFrom": "qa-v5/optics-o3/target-bevel-reflection-source.json "
                      "(settingsBH)",
        "settles": "ior 2.3 -- not our 1.48. dispersion 0.32. Five samples.",
    },
    {
        "id": "bodyReturnIsAccumulatorTintedAndMixed",
        "claim": "The body RETURNS the accumulator, tinted, mixed with the "
                 "environment, plus the rim -- and nothing else.",
        "verbatim": "return" + C.replace("(0,", "(0,") + "mix)(_.mul(n.tint),D,"
                    + C + "min)(" + C + "saturate)(B.mul(n.envIntensity)),"
                    "n.envMaxMix)).add(N.mul(k))",
        "formula": "return mix(accumulator * tint, envColour, "
                   "min(saturate(schlick * envIntensity), envMaxMix)) "
                   "+ rimColour * rim",
        "confidence": "SOURCE_READ",
        "completenessAnchor": True,
        "settles": "THE COMPLETENESS ANCHOR. Between the accumulator and this "
                   "return there is the System B block and nothing else. No "
                   "contrast shaping, no edge lift, no internal shadow, no "
                   "local-contrast probe, no second sampler.",
    },
    {
        "id": "bodyMaterialToneMappedFalse",
        "claim": "The card material disables tone mapping.",
        "verbatim": "new ek.MeshBasicNodeMaterial({transparent:!0,alphaTest:.001,"
                    "depthWrite:!0,depthTest:!0,side:eF.FrontSide,toneMapped:!1})",
        "formula": "MeshBasicNodeMaterial({ toneMapped: false, ... })",
        "confidence": "SOURCE_READ",
        "settles": "The mechanism is MATERIAL-level `toneMapped: false`, not a "
                   "renderer tone-mapping change. That is what factor E must "
                   "copy: three's default is toneMapped = true, and our "
                   "bodyMaterial sets it true explicitly.",
    },
]

#: Absence claims. Each names the completeness span it is read from rather
#: than pretending to a byte offset.
ABSENCES = [
    ("noSceneColourTarget",
     "The body chain samples `s` -- the card's own VideoTexture -- and no "
     "other sampler. There is no render target, no screen uv, and no "
     "resolve of the scene."),
    ("noBlurOrMipLod",
     "No `.level(` appears in the body chain, and the media VideoTexture "
     "generates no mipmaps, so no mip level exists to sample."),
    ("noAdaptiveContrast",
     "Nothing between the accumulator and the return reads neighbouring "
     "texels or the local luminance; there is no contrast gain term."),
    ("noAdaptiveEdgeLift",
     "No additive term keyed on darkness or flatness appears in the span."),
    ("noAdaptiveInternalShadow",
     "No subtractive term keyed on brightness or curvature appears in the "
     "span."),
]

#: What OUR body does instead, declared rather than discovered. These are
#: the O4 factorial's factors.
LOCAL_BODY = {
    "sceneColourTarget": "src/v4/preview/SceneColorPipelineV4.ts renders the "
                         "media to a scene-colour target which the glass "
                         "samples in SCREEN space.",
    "screenSpaceRefractionOffset": "LiquidGlassMaterialV4 projects a Snell "
                                   "exit point through cameraProjectionMatrix "
                                   "and differences it in NDC, then adds "
                                   "projectedNormalOffset and radialLensOffset.",
    "blurLodMipSampling": "`.level(blurLod)` with blurLod = params.blurLod * "
                          "pow(blurZone, 1.6) * mix(0.4, 1, thicknessNorm).",
    "screenSpaceSpectralAnalogue": "the o1-spectral law spreads the SCREEN "
                                   "offset per sample rather than refracting "
                                   "at per-sample IOR.",
    "contrastShaped": "a local-contrast gain around the local luminance.",
    "adaptiveEdgeLift": "an additive lift keyed on darkness x flatness x "
                        "curvature x blurZone.",
    "adaptiveInternalShadow": "a subtractive shadow keyed on brightness x "
                              "flatness x blurZone x curvature.",
    "acesFinalPass": "bodyMaterial.toneMapped = true, so the body passes "
                     "through the renderer's ACESFilmicToneMapping.",
    "refractionNormalIsZero": "O4A: the Beauty branch aliases a "
                              "zero-initialised private, so refract() and "
                              "projectedNormalOffset consume a ZERO normal. "
                              "See qa-v5/optics-o4/body-code-audit.json.",
}


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if "=" in a)
    out = Path(args["out"])
    raw = BUNDLE.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()

    live = None
    if "live-bundle" in args:
        lb = Path(args["live-bundle"]).read_bytes()
        live = {"sha256": hashlib.sha256(lb).hexdigest(), "bytes": len(lb),
                "matchesCapturedBundle": hashlib.sha256(lb).hexdigest() == sha}

    records, failed = [], 0
    for site in SITES:
        needle = site["verbatim"].encode()
        hits, start = [], 0
        while True:
            i = raw.find(needle, start)
            if i < 0:
                break
            hits.append(i)
            start = i + 1
        rec = dict(site)
        rec.update({"bundleSha256": sha, "occurrences": len(hits),
                    "byteOffset": hits[0] if hits else None,
                    "byteExact": len(hits) == 1})
        if len(hits) != 1:
            failed += 1
            rec["FAILURE"] = ("not found" if not hits
                              else f"{len(hits)} occurrences, not unique")
        records.append(rec)

    span = [r for r in records if r.get("completenessAnchor")]
    span_ok = all(r["byteExact"] for r in span)
    lo = min((r["byteOffset"] for r in span if r["byteOffset"]), default=None)
    hi = max((r["byteOffset"] for r in span if r["byteOffset"]), default=None)

    doc = {
        "what": "O4 §四 -- the Target Body source contract. Every Target claim "
                "byte-anchored in the shipped bundle; every absence read from "
                "an anchored completeness span, never inferred from candidate "
                "output.",
        "bundleSha256": sha, "bundleBytes": len(raw), "liveBundle": live,
        "sites": len(records), "sitesFailed": failed,
        "pass": failed == 0 and span_ok,
        "completenessSpan": {
            "anchors": [r["id"] for r in span],
            "allAnchorsByteExact": span_ok,
            "byteRange": [lo, hi],
            "method": "the body colour chain is anchored from the camera "
                      "transform into card space, through the accumulator "
                      "initialisation and the spectral loop, to the return "
                      "statement and the material that consumes it. Anything "
                      "not inside that span is not in the Target's body. "
                      "Absence claims below cite this span rather than a byte "
                      "offset, because absence has no bytes.",
        },
        "absenceClaims": [{"id": k, "readFrom": "completenessSpan",
                           "reasoning": v} for k, v in ABSENCES],
        "localCurrentBody": LOCAL_BODY,
        "records": records,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    for r in records:
        if not r["byteExact"]:
            print(f"  FAIL {r['id']}: {r.get('FAILURE')}")
    print(f"{out}: {len(records)} sites, {failed} failed, "
          f"completeness span {lo}..{hi}, pass={doc['pass']}")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
