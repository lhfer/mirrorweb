#!/usr/bin/env python3
"""O0: the Target's optics, read from its bundle before anyone touches a dial.

Every site is found by exact byte match in the captured bundle (SHA-pinned,
live-verified this round) and must occur exactly once. The output is the
source half of qa-v5/optics/o0-source-diagnosis.json; the runtime half
(ROI measurements on both pages) is appended by o0-optics-measure.

Usage: o0-optics-forensics.py [--live-bundle=<path>] --out=<json>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

BUNDLE = REPO / "artifacts/f27/bundles/03lo820gl57km.js"
BUNDLE_SHA = "4983307288d9e6c544751d1f969a0bc5c4fdb86ebbe5c93ee97aa74ceb0b3754"

SITES = [
    # -- geometry ------------------------------------------------------------
    ("glassGeometryIsPlane",
     "new eF.PlaneGeometry(1,1,16,12)",
     "The Target's glass has NO volume: one unit plane, 16x12 segments. "
     "There is no front/side/back structure, no sidewall, no back dish -- "
     "everything else is shading.",
     "SOURCE_READ"),
    ("domePositionNode",
     "m.positionNode=(0,dB.vec3)(dB.positionLocal.xy,u(dB.positionLocal.xy.mul(n.planeSize)))",
     "The plane is bulged onto a sphere section: z = sqrt(max(R^2-|p|^2,1)) "
     "- R with R = the LAYOUT sphere radius (uniform, written per frame). "
     "The card's curvature IS the grid sphere's curvature.",
     "SOURCE_READ"),
    ("roundedRectSdf",
     "let t=(0,dB.min)(n.cornerRadius,(0,dB.min)(o.x,o.y)),r=(0,dB.abs)(e).sub(o).add(t);return(0,dB.length)((0,dB.max)(r,(0,dB.vec2)(0))).add((0,dB.min)((0,dB.max)(r.x,r.y),(0,dB.float)(0))).sub(t)",
     "The card outline is a rounded-rectangle SDF in plane-pixel space; "
     "cornerRadius is settings.cornerRadius (0.163) x planeWidth, capped at "
     "the half extent.",
     "SOURCE_READ"),
    ("alphaCutout",
     "return(0,dB.float)(1).sub((0,dB.smoothstep)(t.negate(),t,e)).mul(dB.materialOpacity)",
     "opacityNode: an fwidth-antialiased cutout of the SDF. The glass NEVER "
     "paints outside the rounded rect -- zero gutter invasion is structural, "
     "not tuned.",
     "SOURCE_READ"),

    # -- thickness / bevel ---------------------------------------------------
    ("bevelThicknessLaw",
     "let t=(0,dB.clamp)((0,dB.float)(1).add(e.div((0,dB.max)(n.bevelWidth,(0,dB.float)(.001)))),0,1),r=(0,dB.max)(n.bevelPower,(0,dB.float)(1));return(0,dB.pow)((0,dB.max)((0,dB.float)(1).sub((0,dB.pow)(t,r)),(0,dB.float)(0)),(0,dB.float)(1).div(r)).mul(n.thickness)",
     "Thickness profile: a superellipse of the SDF -- t = clamp(1 + "
     "sdf/bevelWidth, 0, 1); thickness x (1 - t^p)^(1/p) with p = "
     "bevelPower. Values: bevelWidth 0.192 x planeWidth, bevelPower 3.9, "
     "thickness 155 x cardScale. Flat centre, all the action in the bevel "
     "band.",
     "SOURCE_READ"),
    ("bevelNormal",
     "g=d.mul((0,dB.min)(p,n.bevelMaxSlope).div((0,dB.max)(p,(0,dB.float)(1e-4)))),m=e.div(l(e)).toVar(),A=(0,dB.normalize)((0,dB.vec3)(m.sub(g),(0,dB.float)(1))).mul(dB.faceDirection).toVar()",
     "The shading normal = sphere term (p/|sphere z|) minus the numeric "
     "thickness gradient, slope-clamped at bevelMaxSlope 1.74. One surface, "
     "one normal -- no internal fold, no return path, no second refraction "
     "event.",
     "SOURCE_READ"),

    # -- refraction ----------------------------------------------------------
    ("refractionLaw",
     "let t=(0,dB.float)(1).div((0,dB.max)(n.ior.add(n.dispersion.mul(e.offset)),(0,dB.float)(1.0001))),r=(0,dB.refract)(E.negate(),A,t),i=n.thickness.div((0,dB.max)((0,dB.abs)(r.z),(0,dB.float)(.05))),a=S.add(r.xy.mul(i).mul(n.refractStrength).div(n.planeSize))",
     "Refraction: eta = 1/(ior + dispersion*offset); refract the view ray "
     "at the bevel normal; travel = thickness/|r.z| (a slab-depth model); "
     "UV shift = r.xy * travel * refractStrength / planeSize. ior 2.3, "
     "refractStrength 0.7. The displacement DIVERGES toward the rim as r.z "
     "-> 0 (clamped at .05) -- that is the Target's edge compression: media "
     "squeezed by the bevel normal, inside the card's own texture.",
     "SOURCE_READ"),
    ("refractionSamplesOwnMedia",
     "o=(0,dB.clamp)(a,0,1).mul(n.coverScale).add(n.coverOffset);_=_.add(s.sample(o).rgb.mul((0,dB.vec3)(...e.weight)))",
     "The refracted sample is CLAMPED to the card's own media rect (cover "
     "fit) -- no scene-colour, no neighbour bleed, and at the rim the media "
     "clamps to its border pixels rather than escaping.",
     "SOURCE_READ"),

    # -- dispersion ----------------------------------------------------------
    ("dispersionWeights",
     "function L2(e,t){return Math.max(0,1-Math.abs(e-t)/.5)}",
     "Spectral weights: per sample at spectral position n in [0,1], RGB "
     "weights are tent functions centred at 0 / 0.5 / 1 with half-width "
     "0.5, normalised so each channel sums to 1 across samples. 5 samples "
     "(dispersionSamples), dispersion 0.32 spread on the IOR. The fringe is "
     "an IOR spread inside the card's own media -- NOT a screen-space RGB "
     "shift.",
     "SOURCE_READ"),

    # -- reflection / environment -------------------------------------------
    ("envReflection",
     "D=(0,dB.texture)(t,(0,dB.equirectUV)(P)).rgb",
     "Reflection: mirror the view ray at the world-space normal, rotate by "
     "envRotation (-2 rad about Y) then envRotationX (0), sample the "
     "equirect environment AT LEVEL 0 -- no roughness, no blur, no PMREM. "
     "The env preset is 'studio': /hdri/studio_small_03_1k.hdr on the "
     "Target's own origin -- the white-studio reflection is a real HDR "
     "studio, not a colour.",
     "SOURCE_READ"),
    ("fresnelMix",
     "B=n.fresnelF0.add((0,dB.float)(1).sub(n.fresnelF0).mul((0,dB.pow)((0,dB.saturate)((0,dB.float)(1).sub((0,dB.dot)(A,E))),5)))",
     "Schlick fresnel, F0 = 0.045, exponent 5, against the BEVEL normal -- "
     "so the fresnel rises exactly where the bevel turns the normal, i.e. "
     "the white ring lives on the bevel band.",
     "SOURCE_READ"),
    ("outputMix",
     "return(0,dB.mix)(_.mul(n.tint),D,(0,dB.min)((0,dB.saturate)(B.mul(n.envIntensity)),n.envMaxMix)).add(N.mul(k))",
     "The final colour: mix(refractedMedia * tint(#fff), envReflection, "
     "min(saturate(fresnel * envIntensity 1.93), envMaxMix 0.27)) + rim. "
     "The env can replace AT MOST 27% of the media colour -- the white "
     "reflection is a capped LERP, not additive energy, so it "
     "DE-saturates the rim band toward the studio white instead of adding "
     "chroma.",
     "SOURCE_READ"),
    ("rimLight",
     "k=(0,dB.smoothstep)(n.rimWidth.negate(),(0,dB.float)(0),r).mul(n.rimIntensity)",
     "Rim: smoothstep over the last rimWidth (10 x cardScale) px of the "
     "SDF, intensity 0.11, colour WHITE top and bottom (rimColor = "
     "rimColorTop = #ffffff) -- an additive white line, no hue.",
     "SOURCE_READ"),

    # -- tone / colour pipeline ----------------------------------------------
    ("materialNotToneMapped",
     "m=new ek.MeshBasicNodeMaterial({transparent:!0,alphaTest:.001,depthWrite:!0,depthTest:!0,side:eF.FrontSide,toneMapped:!1})",
     "toneMapped: FALSE. The card's colour -- media, reflection and rim -- "
     "reaches the framebuffer without any tone-mapping curve. Combined with "
     "the app never setting renderer.toneMapping (no such write exists in "
     "the app module; the three.js default is NoToneMapping), the Target "
     "output transform is: sRGB encode only. No ACES, no exposure, no "
     "contrast curve, no saturation stage anywhere in the chain.",
     "SOURCE_READ"),
    ("settingsBH",
     "bH={cornerRadius:.163,bevelWidth:.192,bevelPower:3.9,bevelMaxSlope:1.74,thickness:155,ior:2.3,roughness:0,refractStrength:.7,dispersion:.32,dispersionSamples:5,fresnelF0:.045,envIntensity:1.93,envMaxMix:.27,envPreset:\"studio\",envRotation:-2,envRotationX:0,rimWidth:10,rimIntensity:.11,rimColor:\"#ffffff\",rimColorTop:\"#ffffff\",tint:\"#ffffff\"}",
     "The complete shipped optics parameter set. Note roughness: 0 exists "
     "as a setting but NO roughness uniform is created and no blur path "
     "exists in the material -- it is dead.",
     "SOURCE_READ"),
    ("backgroundGradient",
     'e=(0,dB.mix)((0,dB.color)("#0a1c3d"),(0,dB.color)("#000000"),dB.screenUV.x.sub(dB.screenUV.y).add(1).mul(.5))',
     "The page behind the cards: a screen-space navy (#0a1c3d) to black "
     "diagonal gradient as the scene backgroundNode.",
     "SOURCE_READ"),
    ("videoColorSpace",
     "e.colorSpace=eF.SRGBColorSpace,e.wrapS=eF.ClampToEdgeWrapping",
     "Media textures are sRGB, clamped to edge -- the refracted sample "
     "clamp lands on repeated border pixels, which is what the edge "
     "compression squeezes against.",
     "SOURCE_READ"),
]

QUESTIONS = {
    "glassGeometry": "A domed unit plane -- no volume, no front/side/back split.",
    "sceneColorSampling": "None. Refraction displaces UV within the card's own "
        "media texture, cover-fitted and clamped.",
    "refractionDisplacementLaw": "refract(-E, bevelNormal, 1/(ior+dispersion*o)); "
        "travel = thickness/max(|r.z|,.05); uvShift = r.xy*travel*refractStrength"
        "/planeSize. Diverges toward the rim: media compression at the bevel.",
    "thicknessIor": "thickness 155*cardScale over a superellipse bevel "
        "(width .192*planeW, power 3.9); ior 2.3.",
    "dispersionChannelOffsets": "5 IOR samples spread by 0.32, tent RGB weights "
        "centred 0/.5/1 width .5, channel-normalised. In-media, not screen-space.",
    "reflectionEnvironmentContribution": "equirect studio_small_03_1k.hdr, level 0, "
        "rotated -2 rad Y; mixed in by min(saturate(fresnel*1.93), 0.27).",
    "roughnessBlur": "NONE in the shipped shader. The roughness setting is dead.",
    "fresnelRimLaw": "Schlick F0 .045 pow 5 on the bevel normal; additive white "
        "rim smoothstep over the outer 10*cardScale px, intensity .11.",
    "toneMapping": "None -- material toneMapped:false, renderer left at the "
        "NoToneMapping default. sRGB encode only.",
    "outputColorSpace": "Renderer default sRGB; video textures sRGB.",
    "saturationContrastPath": "None exists. tint is #ffffff. Any saturation "
        "difference against our candidate comes from OUR pipeline (ACES "
        "film curve + exposure 1.05), not from a Target boost.",
    "whiteStudioReflectionSource": "/hdri/studio_small_03_1k.hdr on the Target "
        "origin (downloadable), preset 'studio'.",
    "edgeCompressionMagnification": "The 1/|r.z| divergence at the bevel, "
        "clamped at .05, refractStrength .7 -- compression INTO the card's "
        "own media, clamped to its border.",
    "gutterInvasion": "Structurally zero: the SDF alpha cutout ends the card "
        "at its rounded rect; rim light lives INSIDE the SDF (smoothstep "
        "of negative band).",
    "internalFoldReturnPath": "None -- one refraction event on one surface.",
    "brightDarkHighTextureBehaviour": "Not decidable from source alone -- "
        "runtime ROI measurement (o0 runtime half / O1 gate).",
}


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    data = BUNDLE.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != BUNDLE_SHA:
        print(f"bundle SHA mismatch: {sha}", file=sys.stderr)
        return 2
    live = None
    if args.get("live-bundle"):
        lp = Path(args["live-bundle"])
        if lp.exists():
            live = hashlib.sha256(lp.read_bytes()).hexdigest()

    sites = []
    failed = 0
    for sid, verbatim, what, conf in SITES:
        needle = verbatim.encode()
        n = data.count(needle)
        off = data.find(needle)
        if n != 1:
            print(f"FAIL {sid}: {n} occurrences", file=sys.stderr)
            failed += 1
        sites.append({"id": sid, "byteOffset": off if off >= 0 else None,
                      "occurrences": n, "verbatim": verbatim,
                      "whatItSettles": what, "confidence": conf})

    doc = {
        "what": "O0 optics source diagnosis, bundle half: the Target's "
                "complete glass shader, byte-anchored. The runtime half "
                "(ROI measurements on both pages) is a separate artefact.",
        "bundle": {"path": str(BUNDLE.relative_to(REPO)), "sha256": sha,
                   "bytes": len(data)},
        "liveBundle": ({"sha256": live, "matchesCapturedBundle": live == sha}
                      if live else None),
        "sites": sites,
        "questions": QUESTIONS,
        "sitesTotal": len(SITES),
        "sitesFailed": failed,
        "pass": failed == 0,
    }
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1) + "\n")
    print(f"{len(SITES)} sites, {failed} failed"
          + (f"; live bundle {'MATCHES' if live == sha else 'DIFFERS'}" if live else ""))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
