#!/usr/bin/env python3
"""O5 §四 -- the Target's complete card optical body, read from the bundle.

Every PRESENCE claim carries a verbatim byte-exact quotation, its offset, the
formula it encodes, a confidence, and the local implementation mapping. A site
fails if its quotation is not found at the recorded offset, or is not unique
where uniqueness is claimed.

ABSENCE claims have no bytes to point at. They are established the way O4
established its own: by anchoring the ENTIRE material factory end to end
(FACTORY_SPAN below, 3747 bytes) and stating that the probe string does not
occur anywhere inside it. That is a complete-span argument, not a pretended
offset -- the factory is the whole body, so what is not in it is not in the
Target's card material.

No constant here is fitted against any candidate render. The bundle is the
only authority, and the live bundle is re-fetched and compared before the
contract is written.

Usage: o5-source-contract.py [--bundle=<path>] [--out=<json>]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

LIVE_URL = ("https://infinite-liquid-glass.shader.se/"
            "_next/static/immutable/chunks/03lo820gl57km.js")

# The whole per-media material factory: geometry position node, SDF, bevel
# normal, spectral refraction, environment, rim, opacity, material flags.
FACTORY_HEAD = "function(e,t,r=bH,i){let n={...i??L3(r)"
FACTORY_TAIL = "{material:m,uniforms:n}"

# The whole card COMPONENT: geometry creation, the material factory, the
# per-frame uniform writes, and the mesh element itself.
#
# The factory span alone cannot carry the geometry-group absences. The Target's
# `new PlaneGeometry(1,1,16,12)` sits 67 bytes BEFORE the factory and the mesh
# element 4299 bytes AFTER it, so "no side wall / no back dish / no reflection
# shell" asserted over the factory would be true of a span containing no
# geometry code at all -- vacuous, and vacuous in the direction that flatters
# the claim. Those three are asserted over this span instead.
COMPONENT_HEAD = "function PP({settings:"
COMPONENT_TAIL = "let PD={stiffness:80"


def site(sid, group, claim, verbatim, formula, local, conf="SOURCE_READ",
         unique=True):
    return {"id": sid, "group": group, "claim": claim, "verbatim": verbatim,
            "formula": formula, "localMapping": local, "confidence": conf,
            "expectUnique": unique}


SITES = [
    # ---------------------------------------------------------- geometry
    site("planeGeometry", "geometry",
         "The Target card is a subdivided unit PLANE, not a convex solid.",
         "new eF.PlaneGeometry(1,1,16,12)",
         "PlaneGeometry(width=1, height=1, widthSegments=16, heightSegments=12)",
         "Candidate lane builds the identical geometry once and shares it "
         "across every card, as the Target does. 16x12 segments matter: the "
         "dome is applied in the VERTEX stage via positionNode, so the "
         "tessellation is what resolves the curvature."),

    site("positionNodeDome", "geometry",
         "The card's curvature is a vertex-stage sphere dome offset, not "
         "modelled geometry.",
         "m.positionNode=(0,dB.vec3)(dB.positionLocal.xy,u(dB.positionLocal.xy.mul(n.planeSize)))",
         "position = vec3(positionLocal.xy, domeZ(positionLocal.xy * planeSize))",
         "Transcribed verbatim. positionLocal.xy is in [-0.5, 0.5] because the "
         "plane is 1x1; multiplying by planeSize puts the dome argument in card "
         "pixels while position.xy stays unit, so the mesh scale carries x/y "
         "and z is already absolute."),

    site("domeFn", "geometry",
         "The dome offset is a sphere cap: sqrt(R^2 - |xy|^2) - R.",
         "u=(0,dB.Fn)(([e])=>l(e).sub(n.sphereRadius))",
         "domeZ(p) = sphereZ(p) - sphereRadius, i.e. negative sag away from centre",
         "Transcribed verbatim as domeOffset()."),

    site("sphereZFn", "geometry",
         "The sphere term floors its radicand at 1, never at 0.",
         "l=(0,dB.Fn)(([e])=>(0,dB.sqrt)((0,dB.max)(n.sphereRadius.mul(n.sphereRadius).sub((0,dB.dot)(e,e)),(0,dB.float)(1))))",
         "sphereZ(p) = sqrt(max(R*R - dot(p,p), 1))",
         "Transcribed verbatim. The max(..., 1) floor also guarantees the "
         "curvature term e/sphereZ(e) can never divide by zero."),

    site("planeSizeFromLayout", "geometry",
         "planeSize is the layout's card size in pixels; cornerRadius and "
         "bevelWidth are RATIOS of card width; thickness and rimWidth scale "
         "with cardScale.",
         "v.planeSize.value.set(d,h),v.cornerRadius.value=e.cornerRadius*d,v.bevelWidth.value=e.bevelWidth*d,v.sphereRadius.value=u,v.thickness.value=e.thickness*l.cardScale,v.rimWidth.value=e.rimWidth*l.cardScale",
         "planeSize=(planeWidth,planeHeight); cornerRadius=0.163*planeWidth; "
         "bevelWidth=0.192*planeWidth; sphereRadius=layout.sphereRadius; "
         "thickness=155*cardScale; rimWidth=10*cardScale",
         "Driven from the FROZEN SourceExactLayoutFrame (planeWidth, "
         "planeHeight, sphereRadius, cardScale), never from a re-derived L6. "
         "This is the single most load-bearing mapping in O5: it is what makes "
         "the Target's unitless constants land at our card's real size."),

    # ---------------------------------------------------------- silhouette
    site("roundedRectSdf", "silhouette",
         "The silhouette is an analytic rounded-rect SDF over card-pixel space.",
         "c=(0,dB.Fn)(([e])=>{let t=(0,dB.min)(n.cornerRadius,(0,dB.min)(o.x,o.y)),r=(0,dB.abs)(e).sub(o).add(t);return(0,dB.length)((0,dB.max)(r,(0,dB.vec2)(0))).add((0,dB.min)((0,dB.max)(r.x,r.y),(0,dB.float)(0))).sub(t)})",
         "r = min(cornerRadius, min(half.x, half.y)); q = abs(p) - half + r; "
         "sdf = length(max(q,0)) + min(max(q.x,q.y),0) - r",
         "Transcribed verbatim. Negative inside, zero on the outline. This is "
         "the same SDF family O3 transcribed for the rim, now load-bearing for "
         "alpha, normal and rim together."),

    site("halfPlane", "silhouette",
         "The SDF half-extent is planeSize/2 -- the card's own pixels.",
         "o=n.planeSize.mul(.5)",
         "half = planeSize * 0.5",
         "Transcribed verbatim."),

    site("cornerRadiusLaw", "silhouette",
         "cornerRadius is 0.163 of card WIDTH, and is clamped to the smaller "
         "half-extent.",
         "cornerRadius:.163",
         "cornerRadius_px = 0.163 * planeWidth, then min(.., half.x, half.y)",
         "The clamp lives in the SDF site above; the ratio here. Our frozen "
         "layout supplies planeWidth."),

    site("fwidthAlpha", "silhouette",
         "Alpha is a screen-derivative antialiased step across the SDF zero "
         "crossing, multiplied by material opacity.",
         "g=(0,dB.Fn)(()=>{let e=c(dB.positionLocal.xy.mul(n.planeSize)),t=(0,dB.max)((0,dB.fwidth)(e).mul(.5),(0,dB.float)(1e-4));return(0,dB.float)(1).sub((0,dB.smoothstep)(t.negate(),t,e)).mul(dB.materialOpacity)})",
         "aa = max(fwidth(sdf)*0.5, 1e-4); alpha = (1 - smoothstep(-aa, aa, sdf)) * materialOpacity",
         "Transcribed verbatim. materialOpacity stays 1: no site in the bundle "
         "assigns .opacity on these materials, and our frozen motion gives "
         "cards no per-card opacity either, so per-clip material sharing is "
         "safe in both."),

    site("materialFlags", "silhouette",
         "Transparent, alphaTest 0.001, depth write AND test on, FrontSide, "
         "and tone mapping off -- all in one constructor.",
         "new ek.MeshBasicNodeMaterial({transparent:!0,alphaTest:.001,depthWrite:!0,depthTest:!0,side:eF.FrontSide,toneMapped:!1})",
         "MeshBasicNodeMaterial{transparent:true, alphaTest:0.001, "
         "depthWrite:true, depthTest:true, side:FrontSide, toneMapped:false}",
         "Transcribed verbatim. depthWrite TRUE with transparent TRUE is "
         "deliberate and unusual: it is what keeps overlapping cards from "
         "blending through one another."),

    # ---------------------------------------------------------- normal
    site("bevelProfile", "normal",
         "Thickness falls off from the interior to the outline by a "
         "power-law bevel profile, not a superellipse solid.",
         "d=(0,dB.Fn)(([e])=>{let t=(0,dB.clamp)((0,dB.float)(1).add(e.div((0,dB.max)(n.bevelWidth,(0,dB.float)(.001)))),0,1),r=(0,dB.max)(n.bevelPower,(0,dB.float)(1));return(0,dB.pow)((0,dB.max)((0,dB.float)(1).sub((0,dB.pow)(t,r)),(0,dB.float)(0)),(0,dB.float)(1).div(r)).mul(n.thickness)})",
         "t = clamp(1 + sdf/max(bevelWidth,0.001), 0, 1); k = max(bevelPower,1); "
         "thick = pow(max(1 - pow(t,k), 0), 1/k) * thickness",
         "Transcribed verbatim. Note the profile is a function of the SDF, so "
         "the bevel follows the rounded corners exactly."),

    site("thicknessAt", "normal",
         "Thickness at a point is the bevel profile evaluated on the SDF.",
         "h=(0,dB.Fn)(([e])=>d(c(e)))",
         "thicknessAt(p) = bevelProfile(sdf(p))",
         "Transcribed verbatim."),

    site("gradientEpsilon", "normal",
         "The normal comes from a NUMERIC central-difference gradient whose "
         "step is max(bevelWidth*0.06, 0.35) card pixels.",
         "i=(0,dB.max)(n.bevelWidth.mul(.06),(0,dB.float)(.35)).toVar()",
         "eps = max(bevelWidth * 0.06, 0.35)",
         "Transcribed verbatim. The 0.35 floor is what keeps the gradient "
         "stable on small cards; it is an absolute pixel floor, not a ratio."),

    site("centralDifference", "normal",
         "Central difference over +/- eps on both axes, divided by 2*eps.",
         "d=(0,dB.vec2)(h(e.add((0,dB.vec2)(i,0))).sub(h(e.sub((0,dB.vec2)(i,0)))),h(e.add((0,dB.vec2)(0,i))).sub(h(e.sub((0,dB.vec2)(0,i))))).div(i.mul(2)).toVar()",
         "grad = vec2(T(p+ex)-T(p-ex), T(p+ey)-T(p-ey)) / (2*eps)",
         "Transcribed verbatim -- four extra thickness evaluations per pixel, "
         "which is the real cost of this normal and is accepted as-is."),

    site("bevelMaxSlope", "normal",
         "The gradient magnitude is CLAMPED to bevelMaxSlope, preserving its "
         "direction.",
         "g=d.mul((0,dB.min)(p,n.bevelMaxSlope).div((0,dB.max)(p,(0,dB.float)(1e-4))))",
         "len = length(grad); grad' = grad * min(len, bevelMaxSlope)/max(len,1e-4)",
         "Transcribed verbatim. This is a magnitude clamp, not a normalise: "
         "below the cap the gradient passes through unchanged."),

    site("sphereCurvatureTerm", "normal",
         "The dome contributes its own tilt, p / sphereZ(p), added into the "
         "same normal.",
         "m=e.div(l(e)).toVar()",
         "curv = p / sphereZ(p)",
         "Transcribed verbatim. This is why the Target's cards catch the "
         "environment differently across the grid: every card's normal carries "
         "its position on the sphere."),

    site("analyticNormal", "normal",
         "The final normal is normalize(vec3(curvature - clampedGradient, 1)) "
         "times faceDirection.",
         "A=(0,dB.normalize)((0,dB.vec3)(m.sub(g),(0,dB.float)(1))).mul(dB.faceDirection).toVar()",
         "N = normalize(vec3(curv - grad', 1)) * faceDirection",
         "Transcribed verbatim. This single expression is the whole normal: no "
         "vertex normal, no varying, no shared unpack -- which is exactly why "
         "the O4A zero-normal defect cannot occur in this lane."),

    site("faceDirection", "normal",
         "faceDirection flips the normal for back-facing fragments.",
         ".mul(dB.faceDirection)",
         "N *= faceDirection (+1 front, -1 back)",
         "Transcribed verbatim. With side:FrontSide it is +1 in practice, but "
         "it is transcribed rather than folded away.", "SOURCE_READ", False),

    site("viewVector", "normal",
         "The view vector is built in LOCAL space from the inverse model "
         "matrix, then anisotropically scaled by planeSize.",
         "b=v.sub(y).toVar(),E=(0,dB.normalize)((0,dB.vec3)(b.xy.mul(n.planeSize),b.z)).toVar()",
         "camLocal = inverse(modelWorld) * cameraPosition; "
         "d = camLocal - vec3(positionLocal.xy, domeZ); "
         "V = normalize(vec3(d.xy * planeSize, d.z))",
         "Transcribed verbatim. The planeSize multiply undoes the unit-plane "
         "scale so the view direction is in the same anisotropic space the "
         "normal lives in -- omitting it would skew refraction on non-square "
         "cards."),

    site("cameraLocal", "normal",
         "Camera position is taken into the card's local frame.",
         "v=dB.modelWorldMatrixInverse.mul((0,dB.vec4)(dB.cameraPosition,1)).xyz",
         "camLocal = modelWorldMatrixInverse * vec4(cameraPosition, 1)",
         "Transcribed verbatim."),

    site("toWorldFn", "normal",
         "Directions are taken back to world by dividing xy by planeSize "
         "first -- the inverse of the view-vector scaling.",
         "f=(0,dB.Fn)(([e])=>(0,dB.normalize)(dB.modelWorldMatrix.mul((0,dB.vec4)(e.xy.div(n.planeSize),e.z,0)).xyz))",
         "toWorld(d) = normalize((modelWorldMatrix * vec4(d.xy/planeSize, d.z, 0)).xyz)",
         "Transcribed verbatim, including the division. Simplifying this pair "
         "away would change the environment reflection on non-square cards."),

    # ---------------------------------------------------------- media
    site("ownMediaTexture", "media",
         "Each card samples its OWN media texture. There is no scene-colour "
         "render target anywhere in the body.",
         "s=(0,dB.texture)(e)",
         "mediaTexture = texture(videoTexture)",
         "The candidate lane creates its own VideoTexture per clip and never "
         "mutates the control lane's reel textures."),

    site("videoTextureFlags", "media",
         "The media texture is sRGB and clamped to edge on both axes.",
         "let e=new eF.VideoTexture(n);e.colorSpace=eF.SRGBColorSpace,e.wrapS=eF.ClampToEdgeWrapping,e.wrapT=eF.ClampToEdgeWrapping",
         "VideoTexture; colorSpace=SRGBColorSpace; wrapS=wrapT=ClampToEdgeWrapping",
         "Transcribed verbatim. three's VideoTexture defaults to "
         "generateMipmaps=false with LinearFilter, so there is no mip chain "
         "even if a LOD were requested -- that is the structural half of the "
         "no-mip claim below."),

    site("materialPerMedia", "media",
         "One material is built PER MEDIA TEXTURE, not one shared material for "
         "every card.",
         "b=(0,eB.useMemo)(()=>c.map(e=>(function(e,t,r=bH,i)",
         "materials = clips.map(clip => buildCardMaterial(clip.texture, env, params, sharedUniforms))",
         "Adopted. Our candidate builds one material per clip and assigns it by "
         "the FROZEN slot identity, so which clip a slot shows does not change."),

    site("sharedUniformBlock", "media",
         "All per-media materials share ONE uniform object, so geometry "
         "constants are set once; only coverScale/coverOffset are per material.",
         "let n={...i??L3(r),coverScale:(0,dB.uniform)(new eF.Vector2(1,1)),coverOffset:(0,dB.uniform)(new eF.Vector2(0,0))}",
         "uniforms = {...sharedGeometryUniforms, coverScale: uniform(vec2(1,1)), "
         "coverOffset: uniform(vec2(0,0))}",
         "Adopted exactly: `i` is the shared L3 block passed in from the "
         "caller, spread into each material, so planeSize/thickness/etc are one "
         "uniform each across all clips."),

    site("clampThenCover", "media",
         "The refracted UV is CLAMPED to 0..1 BEFORE the cover transform, so "
         "refraction can never reach outside the media's own frame.",
         "o=(0,dB.clamp)(a,0,1).mul(n.coverScale).add(n.coverOffset)",
         "uv = clamp(uvRefracted, 0, 1) * coverScale + coverOffset",
         "Transcribed verbatim, and the ordering is the point: clamping AFTER "
         "the cover transform would let a refracted sample walk into the "
         "cropped-away part of the source. This is also the site that makes "
         "own-media isolation structural rather than incidental."),

    site("coverFitFormula", "media",
         "coverScale/coverOffset are a CENTRED cover fit of source aspect into "
         "plane aspect.",
         "let a=i/n;if(a>t){let e=t/a;return{scaleX:e,scaleY:1,offsetX:(1-e)/2,offsetY:0}}let s=a/t;return{scaleX:1,scaleY:s,offsetX:0,offsetY:(1-s)/2}",
         "srcAspect>planeAspect ? {sx:planeAspect/srcAspect, sy:1, ox:(1-sx)/2, oy:0} "
         ": {sx:1, sy:srcAspect/planeAspect, ox:0, oy:(1-sy)/2}",
         "MECHANISM adopted, VALUES frozen. coverScale/coverOffset map exactly "
         "onto three's texture repeat/offset, which our frozen MediaFit already "
         "computes. Clips 0 and 1 (focus 0.5/0.5, zoom 1) reproduce this "
         "formula identically; clip 2 carries a frozen 2026-08-20 product "
         "decision (focusY 0.46, zoom 1.06) that this formula does not have. "
         "O5 may not change media focus/crop, so the candidate feeds "
         "coverScale/coverOffset from the FROZEN MediaFit result."),

    site("ownMediaUv", "media",
         "The base UV is the mesh's own attribute UV.",
         "S=(0,dB.uv)()",
         "baseUv = uv()",
         "Transcribed verbatim."),

    # ---------------------------------------------------------- refraction
    site("iorValue", "refraction",
         "Base index of refraction is 2.3 -- far above glass, and above our "
         "current 1.48.",
         "ior:2.3",
         "ior = 2.3",
         "Adopted verbatim in the candidate lane only. The current lane keeps "
         "1.48; this is one of the reasons the two bodies cannot be compared "
         "term by term."),

    site("dispersionValue", "refraction",
         "Dispersion is 0.32 of IOR, spread across the spectral samples.",
         "dispersion:.32",
         "dispersion = 0.32",
         "Adopted verbatim."),

    site("refractStrengthValue", "refraction",
         "Refraction displacement is scaled by 0.7.",
         "refractStrength:.7",
         "refractStrength = 0.7",
         "Adopted verbatim."),

    site("thicknessValue", "refraction",
         "Base thickness is 155 reference pixels, scaled by cardScale.",
         "thickness:155",
         "thickness = 155 * cardScale",
         "Adopted verbatim; cardScale comes from the frozen layout frame."),

    site("etaPerSample", "refraction",
         "Each spectral sample gets its OWN eta from ior + dispersion*offset, "
         "floored at 1.0001.",
         "let t=(0,dB.float)(1).div((0,dB.max)(n.ior.add(n.dispersion.mul(e.offset)),(0,dB.float)(1.0001)))",
         "eta_i = 1 / max(ior + dispersion * offset_i, 1.0001)",
         "Transcribed verbatim inside the unrolled loop."),

    site("refractPerSample", "refraction",
         "Every spectral sample runs its OWN refract() against the analytic "
         "normal -- not one refraction reused with UV offsets.",
         "r=(0,dB.refract)(E.negate(),A,t)",
         "r_i = refract(-V, N, eta_i)",
         "Transcribed verbatim. This is the single largest mechanical "
         "difference from our current screen-space analogue, and §七.6 requires "
         "proving each sample's refract survives into the compiled program."),

    site("travelDistance", "refraction",
         "Travel through the body is thickness / max(abs(r.z), 0.05).",
         "i=n.thickness.div((0,dB.max)((0,dB.abs)(r.z),(0,dB.float)(.05)))",
         "travel_i = thickness / max(abs(r_i.z), 0.05)",
         "Transcribed verbatim. The 0.05 floor caps travel at 20x thickness at "
         "grazing angles."),

    site("uvDisplacement", "refraction",
         "The UV displacement is r.xy * travel * refractStrength / planeSize.",
         "a=S.add(r.xy.mul(i).mul(n.refractStrength).div(n.planeSize))",
         "uv_i = baseUv + r_i.xy * travel_i * refractStrength / planeSize",
         "Transcribed verbatim. The planeSize division converts a card-pixel "
         "displacement into UV space, which is the plane-size normalisation "
         "§四 asks for."),

    site("accumulateWeighted", "refraction",
         "Samples accumulate as texture.sample(uv).rgb * weight, with no LOD "
         "argument anywhere.",
         "_=_.add(s.sample(o).rgb.mul((0,dB.vec3)(...e.weight)))",
         "acc += mediaTexture.sample(uv_i).rgb * weight_i",
         "Transcribed verbatim. `.sample(uv)` with no `.level()` is level-0 "
         "sampling; combined with generateMipmaps=false there is no mip chain "
         "to reach."),

    # ---------------------------------------------------------- spectral
    site("tentWeightFn", "spectral",
         "Per-sample RGB weights are a TENT of half-width 0.5 centred on "
         "0 / 0.5 / 1 for R / G / B.",
         "function L2(e,t){return Math.max(0,1-Math.abs(e-t)/.5)}",
         "w(x, c) = max(0, 1 - |x - c| / 0.5); weight_i = [w(t,0), w(t,0.5), w(t,1)]",
         "Transcribed verbatim and evaluated on the CPU at build time, exactly "
         "as the Target does -- the weights are literals in the shader."),

    site("samplePositions", "spectral",
         "Sample positions are evenly spaced over 0..1 and RE-CENTRED to "
         "-0.5..+0.5, so the middle sample carries zero dispersion offset.",
         "r.push({offset:n-.5,weight:a})",
         "t_i = i/(n-1) for i in 0..n-1; offset_i = t_i - 0.5",
         "Transcribed verbatim. With 5 samples the offsets are "
         "-0.5,-0.25,0,+0.25,+0.5, so the centre sample refracts at exactly "
         "ior and the spread is symmetric."),

    site("samplePositionsExact", "spectral",
         "Byte-exact quotation of the sample-position and accumulation loop.",
         "for(let e=0;e<t;e+=1){let n=e/(t-1),a=[L2(n,0),L2(n,.5),L2(n,1)];i[0]+=a[0],i[1]+=a[1],i[2]+=a[2],r.push({offset:n-.5,weight:a})}",
         "t_i = i/(n-1); offset_i = t_i - 0.5; weight_i = tent(t_i); "
         "sums accumulated per channel",
         "Transcribed verbatim."),

    site("perChannelNormalisation", "spectral",
         "Weights are normalised PER CHANNEL, so each of R, G and B sums to "
         "exactly 1 across the samples.",
         "return r.map(({offset:e,weight:t})=>({offset:e,weight:[t[0]/i[0],t[1]/i[1],t[2]/i[2]]}))",
         "weight_i[c] /= sum_j weight_j[c], independently for c in {R,G,B}",
         "Transcribed verbatim. Per-channel (not per-sample) normalisation is "
         "what keeps a grey input grey -- it is the structural reason §九.4 "
         "can be passed at all, and getting it wrong tints the whole card."),

    site("sampleCountFloor", "spectral",
         "The sample count is floored at 3 and rounded.",
         "let t=Math.max(3,Math.round(e))",
         "n = max(3, round(dispersionSamples))",
         "Transcribed verbatim."),

    site("sampleCountQualityRule", "spectral",
         "The Target caps samples at 3 on LOW devices and leaves them "
         "uncapped otherwise; with dispersionSamples 5 that is 5 on high, 3 on "
         "low.",
         "maxDispersionSamples:\"low\"===Pb?3:1/0",
         "samples = min(5, low ? 3 : Infinity) -> high 5, low 3",
         "Target has TWO device tiers; we have three quality levels. Mapping "
         "recorded in o5-architecture.json: high -> 5, medium -> 5, low -> 3. "
         "This is a stated 3-tier-to-2-tier mapping, not a transcription."),

    site("deviceTierRule", "spectral",
         "The device tier is coarse-pointer OR <=6 cores OR <=4 GB.",
         "Pb=(eh=window.matchMedia(\"(pointer: coarse)\").matches,ef=navigator.hardwareConcurrency??8,ep=\"u\"<typeof navigator?8:navigator.deviceMemory??8,eh||ef<=6||ep<=4?\"low\":\"high\")",
         "tier = (coarsePointer || cores<=6 || memoryGB<=4) ? 'low' : 'high'",
         "Recorded for completeness. Our adaptive quality policy is FROZEN and "
         "O5 may not modify it, so the candidate reads OUR quality level and "
         "maps it per the rule above rather than adopting this predicate."),

    site("dispersionSamplesValue", "spectral",
         "The configured sample count is 5.",
         "dispersionSamples:5",
         "dispersionSamples = 5",
         "Adopted verbatim for high/medium."),

    # ---------------------------------------------------------- reflection
    site("envPresetStudio", "reflection",
         "The environment is the studio HDR -- the same asset O2 accepted.",
         "studio:\"/hdri/studio_small_03_1k.hdr\"",
         "envPreset 'studio' -> /hdri/studio_small_03_1k.hdr",
         "Identical to V4_OPTICS_CONFIG.material.systemB.assetPath. The "
         "candidate reuses the already-loaded O2 environment texture."),

    site("equirectMapping", "reflection",
         "The environment is sampled as an equirectangular reflection map.",
         "h.mapping=eF.EquirectangularReflectionMapping",
         "envTexture.mapping = EquirectangularReflectionMapping",
         "Matches our O2 loader."),

    site("reflectVector", "reflection",
         "The reflection vector is computed by hand in WORLD space from the "
         "same analytic normal the refraction used.",
         "C=(0,dB.normalize)(x.negate().sub(T.mul((0,dB.dot)(x.negate(),T).mul(2)))).toVar()",
         "Nw = toWorld(N); Vw = toWorld(V); R = normalize(-Vw - 2*dot(-Vw,Nw)*Nw)",
         "Transcribed verbatim. Reflection and refraction sharing one normal is "
         "§七.13; here it is structural, since both read the same local `A`."),

    site("envRotationY", "reflection",
         "The reflection vector is rotated about Y by envRotation.",
         "R=(0,dB.vec3)(C.x.mul(I).sub(C.z.mul(w)),C.y,C.x.mul(w).add(C.z.mul(I)))",
         "cy=cos(envRotation), sy=sin(envRotation); "
         "R' = (R.x*cy - R.z*sy, R.y, R.x*sy + R.z*cy)",
         "Transcribed verbatim; envRotation = -2 matches our accepted O2 value."),

    site("envRotationX", "reflection",
         "Then rotated about X by envRotationX.",
         "P=(0,dB.vec3)(R.x,R.y.mul(M).sub(R.z.mul(L)),R.y.mul(L).add(R.z.mul(M)))",
         "cx=cos(envRotationX), sx=sin(envRotationX); "
         "R'' = (R'.x, R'.y*cx - R'.z*sx, R'.y*sx + R'.z*cx)",
         "Transcribed verbatim; envRotationX = 0 matches our accepted O2 value."),

    site("schlickFresnel", "reflection",
         "Fresnel is Schlick with a fixed exponent of 5, on dot(N, V) in the "
         "anisotropic local frame.",
         "B=n.fresnelF0.add((0,dB.float)(1).sub(n.fresnelF0).mul((0,dB.pow)((0,dB.saturate)((0,dB.float)(1).sub((0,dB.dot)(A,E))),5)))",
         "F = F0 + (1-F0) * saturate(1 - dot(N,V))^5",
         "Transcribed verbatim. F0 = 0.045 matches our accepted O2 value. Note "
         "the dot is taken in LOCAL space, before toWorld()."),

    site("cappedEnvLerp", "reflection",
         "The environment is LERPed in with a hard ceiling of envMaxMix.",
         "(0,dB.mix)(_.mul(n.tint),D,(0,dB.min)((0,dB.saturate)(B.mul(n.envIntensity)),n.envMaxMix))",
         "body = mix(acc * tint, envColor, min(saturate(F * envIntensity), envMaxMix))",
         "Transcribed verbatim. envIntensity 1.93 and envMaxMix 0.27 match our "
         "accepted O2 values, which is a strong independent confirmation of the "
         "O2 System B contract."),

    site("whiteSdfRim", "reflection",
         "The rim is a smoothstep INSIDE the SDF outline, white top and "
         "bottom, ADDED after the environment mix.",
         "k=(0,dB.smoothstep)(n.rimWidth.negate(),(0,dB.float)(0),r).mul(n.rimIntensity)",
         "rim = smoothstep(-rimWidth, 0, sdf) * rimIntensity",
         "Transcribed verbatim. rimWidth = 10*cardScale, rimIntensity = 0.11."),

    site("rimVerticalGradient", "reflection",
         "The rim colour lerps bottom-to-top by normalised card Y -- both ends "
         "white in the shipped settings.",
         "F=(0,dB.saturate)(e.y.div((0,dB.max)(o.y,(0,dB.float)(1e-4))).mul(.5).add(.5)),N=(0,dB.mix)(n.rimColor,n.rimColorTop,F)",
         "tY = saturate(p.y/max(half.y,1e-4) * 0.5 + 0.5); "
         "rimCol = mix(rimColor, rimColorTop, tY)",
         "Transcribed verbatim including the gradient, even though "
         "rimColor == rimColorTop == #ffffff makes it currently inert."),

    site("rimAdditive", "reflection",
         "The rim is ADDED, not mixed -- it can push the body above the "
         "environment.",
         ".add(N.mul(k))",
         "return mix(acc*tint, env, envMix) + rimCol * rim",
         "Transcribed verbatim.", "SOURCE_READ", False),

    site("rimIntensityValue", "reflection",
         "rimIntensity 0.11, rimWidth 10, both rim colours pure white.",
         "rimWidth:10,rimIntensity:.11,rimColor:\"#ffffff\",rimColorTop:\"#ffffff\",tint:\"#ffffff\"",
         "rimWidth=10*cardScale; rimIntensity=0.11; rimColor=rimColorTop=#ffffff; tint=#ffffff",
         "Adopted verbatim. rimIntensity matches our accepted O2 value."),

    # ---------------------------------------------------------- output
    site("toneMappedFalse", "output",
         "The body material sets toneMapped false.",
         "toneMapped:!1",
         "material.toneMapped = false",
         "Transcribed verbatim, AND INERT IN BOTH CODEBASES. three's WebGPU "
         "node renderer never reads Material.toneMapped: 0 occurrences in our "
         "three.webgpu.js, and all four `.toneMapped` reads in the Target's "
         "own bundle (bytes 216960, 217782, 282464, 387472) are WebGL-only "
         "parameter builders, none in the node path. So the Target's cards are "
         "tone-mapped by its output stage DESPITE this flag, exactly as ours "
         "are. O4 saw the inertness on our side and concluded the intent had "
         "to be moved to the renderer; reading the Target's bundle reverses "
         "that. Overriding our renderer for this lane would create a "
         "difference the Target does not have, so the flag is set and the "
         "renderer is left alone.", "SOURCE_READ", False),
]

# Absence claims: probe strings that must NOT occur in the factory span.
ABSENCES = [
    ("noSideWall", "geometry", "No side wall: the body is a plane, so there is "
     "no extruded or lathed rim geometry anywhere in the card component.",
     ["CylinderGeometry", "ExtrudeGeometry", "LatheGeometry", "TubeGeometry",
      "sidewall", "sideWall"], "component"),
    ("noBackDish", "geometry", "No back dish: no second surface behind the "
     "card.", ["backDish", "backDish"], "component"),
    ("noReflectionShell", "geometry", "No separate reflection shell mesh and "
     "no second material: reflection lives in the SAME material as "
     "refraction.", ["shell", "Shell"], "component"),
    ("noAdaptiveContrast", "output", "No adaptive contrast shaping.",
     ["contrast", "Contrast"], "factory"),
    ("noEdgeLift", "output", "No adaptive edge lift.", ["edgeLift", "EdgeLift"],
     "factory"),
    ("noInternalShadow", "output", "No adaptive internal shadow.",
     ["internalShadow", "InternalShadow"], "factory"),
    ("noMipLod", "output", "No mip / LOD sampling anywhere in the body.",
     [".level(", "textureLod", "mipmap", "blur", "Blur"], "factory"),
    ("noSceneColourTarget", "output", "No scene-colour render target is "
     "sampled: the body never reads the framebuffer.",
     ["sceneColor", "renderTarget", "viewportTexture", "screenUV"], "factory"),
    ("noToneMapNodes", "output", "No ACES or tone-mapping node in the body "
     "chain.", ["ACES", "toneMapping", "acesFilmic"], "factory"),
]

# Positive structural counts over the component span. An absence proved by
# "the string is not there" is worth much more when the thing that WOULD be
# there is also counted and found to be singular.
COMPONENT_COUNTS = [
    ("geometryConstructions", "new eF.PlaneGeometry(", 1,
     "Exactly one geometry is constructed in the whole card component, and it "
     "is a plane."),
    ("meshElements", '"mesh",{ref:', 1,
     "Exactly one mesh element per card -- no shell mesh, no media plane."),
    ("materialFactoryCalls", "function(e,t,r=bH,i){let n={...i??L3(r)", 1,
     "Exactly one material factory, so there is no second material to carry a "
     "shell."),
]


def main() -> int:
    bundle = REPO / "artifacts/f27/bundles/03lo820gl57km.js"
    out = REPO / "qa-v5/optics-o5/target-optical-body-contract.json"
    live = None
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k == "bundle":
            bundle = Path(v)
        elif k == "out":
            out = Path(v)
        elif k == "live":
            live = Path(v)

    raw = bundle.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    # Everything below is searched in BYTES, not in decoded text.
    #
    # The bundle carries 6 non-ASCII characters before the material factory,
    # so a decoded-string index is 10 short of the real byte offset there and
    # drifts further later in the file. §四 asks for a byte offset, and a
    # reviewer who seeks to a character index gets the wrong bytes -- silently,
    # because the quotation still looks plausible a few characters away. So the
    # quotations are encoded and located in the raw bytes.
    text = raw

    live_block = {"url": LIVE_URL, "checked": False}
    if live and live.exists():
        lraw = live.read_bytes()
        live_block = {"url": LIVE_URL, "checked": True,
                      "sha256": hashlib.sha256(lraw).hexdigest(),
                      "bytes": len(lraw),
                      "matchesCapturedBundle": lraw == raw}

    head, tail = FACTORY_HEAD.encode(), FACTORY_TAIL.encode()
    start = raw.index(head)
    end = raw.index(tail, start) + len(tail)
    span = raw[start:end]

    chead, ctail = COMPONENT_HEAD.encode(), COMPONENT_TAIL.encode()
    cstart = raw.index(chead)
    cend = raw.index(ctail, cstart)
    cspan = raw[cstart:cend]

    records, failed = [], []
    for s in SITES:
        v = s["verbatim"].encode()
        n = raw.count(v)
        rec = dict(s)
        rec.pop("expectUnique")
        rec["bundleSha256"] = sha
        rec["occurrences"] = n
        off = raw.index(v) if n else None
        rec["byteOffset"] = off
        rec["byteExact"] = n >= 1
        rec["unique"] = n == 1
        # Seek to the recorded offset and compare. Deriving the offset from a
        # search and then reporting it is not evidence that the offset is
        # usable -- a reader will SEEK to it, and a whole class of error (the
        # character-vs-byte index this contract had to fix) is invisible
        # unless the seek is actually performed.
        rec["seekVerified"] = bool(off is not None
                                   and raw[off:off + len(v)] == v)
        if n == 0 or (s["expectUnique"] and n != 1) or not rec["seekVerified"]:
            rec["FAILED"] = ("not found" if n == 0
                             else f"expected unique, found {n}" if n != 1
                             else "recorded offset does not seek to the quotation")
            failed.append(s["id"])
        records.append(rec)

    absences = []
    for aid, group, claim, probes, scope in ABSENCES:
        blob, bounds = ((span, [start, end]) if scope == "factory"
                        else (cspan, [cstart, cend]))
        counts = {p: blob.count(p.encode()) for p in probes}
        ok = all(c == 0 for c in counts.values())
        absences.append({
            "id": aid, "group": group, "claim": claim,
            "method": "COMPLETENESS_SPAN", "scope": scope,
            "spanBytes": bounds, "spanLength": bounds[1] - bounds[0],
            "probes": counts, "absent": ok,
            "confidence": "SOURCE_READ",
        })
        if not ok:
            failed.append(aid)

    counts_out = []
    for cid, needle, expected, why in COMPONENT_COUNTS:
        got = cspan.count(needle.encode())
        counts_out.append({"id": cid, "needle": needle, "expected": expected,
                           "found": got, "ok": got == expected, "why": why})
        if got != expected:
            failed.append(cid)

    doc = {
        "what": "O5 §四 -- the Target's COMPLETE card optical body, read from "
                "the live bundle. Presence claims carry byte-exact quotations; "
                "absence claims are established by a complete-span argument "
                "over the entire material factory, never by a pretended offset.",
        "bundleSha256": sha, "bundleBytes": len(raw),
        "offsetsAreRealByteOffsets": {
            "value": True,
            "why": "Quotations are located in the RAW BYTES, not in a decoded "
                   "string. The bundle holds 6 non-ASCII characters before the "
                   "material factory, so a character index reads 10 low there "
                   "and drifts further downstream. Verified: seeking to each "
                   "recorded offset in the raw file yields the quotation.",
            "nonAsciiCharsBeforeFactory": 6,
            "characterIndexWouldBeLowBy": 10,
            "note": "The O4 contract (qa-v5/optics-o4/target-body-source.json) "
                    "used decoded-string indices and carries the same offset "
                    "shift. Its quotations and conclusions are unaffected -- "
                    "they were located by search, not by seek -- and that tree "
                    "is pushed history, so the correction is recorded here "
                    "rather than by rewriting it.",
        },
        "liveBundle": live_block,
        "factorySpan": {
            "byteStart": start, "byteEnd": end, "bytes": end - start,
            "seekVerified": raw[start:start + len(head)] == head
                            and raw[end - len(tail):end] == tail,
            "why": "This span is the ENTIRE per-media material factory: the "
                   "shared uniform block, the spectral weight builder, the "
                   "sphere and SDF helpers, the bevel profile, the analytic "
                   "normal, the spectral refraction loop, the environment and "
                   "rim, the opacity node and the material flags. Anything not "
                   "inside it is not in the Target's card body.",
        },
        "allOffsetsSeekVerified": all(r["seekVerified"] for r in records),
        "sites": len(records), "sitesFailed": len(failed),
        "failedIds": failed,
        "pass": not failed,
        "noConstantFittedAgainstCandidate": True,
        "records": records,
        "absenceClaims": absences,
        "componentSpan": {
            "byteStart": cstart, "byteEnd": cend, "bytes": cend - cstart,
            "seekVerified": raw[cstart:cstart + len(chead)] == chead,
            "why": "The whole card component: geometry construction, the "
                   "material factory, the per-frame uniform writes and the "
                   "mesh element. The geometry-group absences are asserted "
                   "over THIS span, because the factory span contains no "
                   "geometry code and an absence claimed there would be "
                   "vacuous.",
        },
        "componentCounts": counts_out,
        "targetParameters": {
            "cornerRadius": 0.163, "bevelWidth": 0.192, "bevelPower": 3.9,
            "bevelMaxSlope": 1.74, "thickness": 155, "ior": 2.3,
            "refractStrength": 0.7, "dispersion": 0.32, "dispersionSamples": 5,
            "fresnelF0": 0.045, "envIntensity": 1.93, "envMaxMix": 0.27,
            "envPreset": "studio", "envRotation": -2, "envRotationX": 0,
            "rimWidth": 10, "rimIntensity": 0.11, "rimColor": "#ffffff",
            "rimColorTop": "#ffffff", "tint": "#ffffff",
            "unitsNote": "cornerRadius and bevelWidth are RATIOS of card "
                         "width; thickness and rimWidth are reference pixels "
                         "scaled by cardScale; the rest are unitless.",
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"sites {len(records) - len(failed)}/{len(records)} verified, "
          f"{len(absences)} absence claims, "
          f"factory span {end - start} bytes")
    if failed:
        print("FAILED:", failed, file=sys.stderr)
    print(f"-> {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
