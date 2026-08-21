#!/usr/bin/env python3
"""V1 render-culling forensics: what IS the `s` in `s.visible = o.draw`?

The V0 round recorded the wiring site and deliberately did not act on it.
This script re-reads the Target bundle and answers the render-object
questions byte by byte: where `s` is created, its Three.js type, its
material, what a draw call for it contains, what hiding it can and cannot
affect, and whether any second object or pass exists that the verdict
would need to reach.

Every site is found by exact byte match and must occur EXACTLY ONCE in the
bundle (or the recorded count); a mismatch fails the run. The verbatim in
the output is sliced from the bundle itself, never retyped.

Usage: v1-render-forensics.py [--live-bundle=<path>] --out=<json>
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

# (id, verbatim, whatItSettles, confidence)
SITES = [
    # -- A. what `s` is ------------------------------------------------------
    ("meshJsx",
     '(0,eP.jsx)("mesh",{ref:e=>{a.current[t]=e},geometry:y,material:b[m[t]]?.material,frustumCulled:!1},t)',
     "`s` is a plain react-three-fiber \"mesh\" element -- a THREE.Mesh, not a "
     "Group and not a parent of anything. Its ref callback writes it into "
     "a.current[t], the exact array the visibility loop iterates. One shared "
     "geometry `y`; material comes from the per-MEDIA material array b, "
     "indexed by the slot->media assignment m[t]; frustumCulled is disabled, "
     "so the coverage verdict is the ONLY culling this mesh has.",
     "SOURCE_READ"),
    ("meshGroupParent",
     '(0,eP.jsx)("group",{children:Array.from({length:g},(e,t)=>',
     "Parent chain: every card mesh is a direct child of ONE anonymous "
     "<group>, which is a direct child of the scene. There is no per-slot "
     "group -- the mesh IS the whole WebGL card.",
     "SOURCE_READ"),
    ("planeGeometry",
     "new eF.PlaneGeometry(1,1,16,12)",
     "The shared card geometry: a unit plane, 16x12 segments. The dome shape "
     "comes from the material's positionNode, not from the geometry.",
     "SOURCE_READ"),
    ("materialClass",
     "new ek.MeshBasicNodeMaterial({transparent:!0,alphaTest:.001,depthWrite:!0,depthTest:!0,side:eF.FrontSide,toneMapped:!1})",
     "The material is a WebGPU MeshBasicNodeMaterial: transparent, "
     "alphaTest .001, depth write+test on, FRONT side only, NOT tone mapped. "
     "One instance per MEDIA (not per slot) -- slots showing the same clip "
     "share the material and its uniforms.",
     "SOURCE_READ"),
    ("materialPerMedia",
     "b=(0,eB.useMemo)(()=>c.map(e=>(function(e,t,r=bH,i)",
     "The material array b is built by mapping the MEDIA list c -- one "
     "material per clip, each closing over that clip's VideoTexture.",
     "SOURCE_READ"),
    ("positionNodeDome",
     "m.positionNode=(0,dB.vec3)(dB.positionLocal.xy,u(dB.positionLocal.xy.mul(n.planeSize)))",
     "positionNode bulges the plane onto a sphere section (z = "
     "sqrt(max(R^2-|p|^2,1)) - R, R = the LAYOUT sphere radius uniform). The "
     "glass body is this displaced plane -- there is no separate glass "
     "geometry.",
     "SOURCE_READ"),
    ("singleMaterialAllOptics",
     "m.colorNode=p(),m.opacityNode=g(),{material:m,uniforms:n}",
     "colorNode carries the ENTIRE card appearance -- refracted media, "
     "environment reflection, fresnel mix, rim light; opacityNode is the "
     "antialiased rounded-rect cutout. Glass Body, Media Plane and "
     "Reflection Shell are ONE node material on ONE mesh: one draw call per "
     "card, nothing else to hide.",
     "SOURCE_READ"),

    # -- B. the visibility wiring -------------------------------------------
    ("verdictWiring",
     "s.visible=o.draw,o.draw?i(a,s):n(a),o.interactive&&PA.push(a)",
     "The SAME coverage verdict, in the SAME loop iteration, writes the "
     "mesh's .visible AND draws/hides the CSS3D label (i = draw callback "
     "into the label DOM registry L7, n = hide callback). WebGL and CSS3D "
     "can never disagree by construction -- there is no second coverage "
     "state.",
     "SOURCE_READ"),
    ("nullMeshSkip",
     "PA.length=0;for(let a=0;a<e.length;a+=1){let s=e[a];if(!s)continue;",
     "A slot whose mesh ref is not mounted yet is skipped entirely -- "
     "neither mesh nor label changes state.",
     "SOURCE_READ"),
    ("meshPoseUnconditional",
     "t.position.set(PT.x*u,PT.y*u,PT.z*u-u),t.quaternion.setFromUnitVectors(P_,PT),t.scale.set(d,h,1)",
     "The mesh pose loop runs for EVERY mounted mesh EVERY frame, before the "
     "verdict, with no visibility check: hidden meshes keep receiving "
     "transforms. Culling skips the draw, never the pose. (The CSS3D label "
     "is the opposite: hidden labels keep a stale transform. Both are "
     "already frozen behaviours -- labels in V0, meshes here.)",
     "SOURCE_READ"),

    # -- C. the scene: what else could a draw call belong to ------------------
    ("canvasMount",
     '(0,eP.jsxs)(mL,{renderer:!0,dpr:PE.dpr,style:i,camera:n,children:[a,s,o]})',
     "One Canvas, WebGPU renderer, dpr capped by device tier, camera fov 45. "
     "The children are: the background node element, the PG scene wrapper, "
     "and a literal `false`.",
     "SOURCE_READ"),
    ("backgroundNode",
     '(0,eP.jsx)("primitive",{attach:"backgroundNode",object:i})',
     "The page background is a scene backgroundNode (a screen-space "
     "navy-to-black gradient: mix(#0a1c3d, #000) over screenUV), not a mesh. "
     "Card visibility cannot affect it and it cannot affect card culling.",
     "SOURCE_READ"),
    ("sceneChildren",
     "n=(0,eP.jsxs)(eB.Suspense,{fallback:null,children:[t,r,i]})",
     "PG renders exactly: PB (camera/scroll springs -- no objects), PP (the "
     "card field -- the ONLY object container), PF (onReady signal). The "
     "card meshes are the only WebGL objects in the scene; `s.visible` "
     "therefore toggles exactly one draw call and there is no reflection "
     "shell, media plane, or scene-color proxy anywhere to keep in sync.",
     "SOURCE_READ"),

    # -- D. passes: what a hidden mesh stops rendering ------------------------
    ("refractionSamplesOwnMedia",
     "a=S.add(r.xy.mul(i).mul(n.refractStrength).div(n.planeSize)),o=(0,dB.clamp)(a,0,1).mul(n.coverScale).add(n.coverOffset);_=_.add(s.sample(o)",
     "The refraction loop displaces UV WITHIN the card's own media texture "
     "(s = texture(clip video)) -- there is NO scene-color sampling, no "
     "readback, no second pass. Hiding a card cannot change what any other "
     "card refracts.",
     "SOURCE_READ"),
    ("envReflectionSameMaterial",
     "D=(0,dB.texture)(t,(0,dB.equirectUV)(P)).rgb",
     "The white-studio reflection is an equirect env-texture sample inside "
     "the same colorNode -- part of the same single draw call, not a "
     "separate shell object or pass.",
     "SOURCE_READ"),

    # -- E. media: what visibility does NOT touch -----------------------------
    ("videoPlaysFromMount",
     "t.muted=!0,t.play()}return()=>{for(let e of r)e.image.pause()}",
     "Every clip's HTMLVideoElement plays from the moment the media set "
     "mounts and pauses only on unmount. Per-slot visibility does not touch "
     "playback or decode -- the elements are shared by all slots showing "
     "that clip.",
     "SOURCE_READ"),
    ("videoTexturePerClip",
     "let e=new eF.VideoTexture(n);e.colorSpace=eF.SRGBColorSpace",
     "One VideoTexture per clip, sRGB, shared by every slot with that clip "
     "via the shared material. Whether the renderer skips the GPU upload for "
     "a clip whose every mesh is hidden is renderer-internal and not "
     "readable from this bundle.",
     "SOURCE_READ"),
    ("coverFitPerMedia",
     "b[e].uniforms.coverScale.value.set(t.scaleX,t.scaleY),b[e].uniforms.coverOffset.value.set(t.offsetX,t.offsetY)",
     "Cover fit is a per-MEDIA uniform recomputed when the plane aspect "
     "changes -- shared by all slots with that clip, unrelated to "
     "visibility.",
     "SOURCE_READ"),
    ("mediaAssignment",
     "material:b[m[t]]?.material",
     "The slot->clip assignment m is a neighbour-avoiding round-robin "
     "computed from cols x rows; it decides WHICH material a mesh gets and "
     "never changes with visibility.",
     "SOURCE_READ"),

    # -- F. modes -------------------------------------------------------------
    ("noLayerDebugMode",
     "bq={glass:bH,grid:bV,drag:bW}",
     "The settings store contains exactly glass (optics), grid (layout) and "
     "drag (motion) parameter groups. The shipped bundle has NO glass-off, "
     "media-only, layer-debug or URL-parameter surface that composes with "
     "mesh visibility -- searched: no glassOnly/mediaOnly/layers/leva/"
     "searchParams reads in the app module. The verdict is the only "
     "visibility writer.",
     "SOURCE_READ"),

    # -- G. carried context ---------------------------------------------------
    ("regridDebounce",
     "let r=window.setTimeout(e,150);return()=>window.clearTimeout(r)",
     "The cols x rows layout STATE (not just the label pool) commits on a "
     "150 ms debounce after resize -- the state setter u() lives inside this "
     "debounced callback. This upgrades the V0 gate's transition-window "
     "rationale from measured to source-read.",
     "SOURCE_READ"),
    ("deviceTierCaps",
     'PE={dpr:"low"===Pb?[1,1.5]:[1,2],maxDispersionSamples:"low"===Pb?3:1/0,videoCount:"low"===Pb?8:1/0,maxVideoHeight:"low"===Pb?540:1/0}',
     "Device-tier caps: dpr, dispersion sample count, clip count, video "
     "height. These are load-time constants, not per-frame quality "
     "adaptation -- the Target has no runtime adaptive quality for the "
     "verdict to compose with.",
     "SOURCE_READ"),
]

QUESTIONS = {
    "whereIsSCreated": "PP's JSX: <group>{Array.from({length: cols*rows}, (_, t) "
        "=> <mesh ref={e => a.current[t] = e} ...>)}</group> -- see meshJsx. "
        "a.current is the array the visibility loop iterates.",
    "threeJsType": "THREE.Mesh (r3f intrinsic \"mesh\"). Not a Group, not a "
        "parent; it has no children in JSX and nothing is ever attached to it.",
    "isMeshGroupOrParent": "Mesh. The only group is the single shared parent "
        "of all card meshes; hiding THAT would hide every card, and the "
        "Target never touches it.",
    "material": "MeshBasicNodeMaterial (WebGPU node material), one instance "
        "per media clip, shared across slots showing that clip. transparent, "
        "alphaTest .001, depth write+test, FrontSide, toneMapped false.",
    "whatSCorrespondsTo": {
        "glassBody": "YES -- the dome, bevel, rim and fresnel all live in this "
                     "mesh's material nodes",
        "reflectionShell": "NO SEPARATE OBJECT -- reflection is an env-texture "
                           "term inside the same colorNode",
        "mediaPlane": "NO SEPARATE OBJECT -- the media is the material's video "
                      "texture, refracted in the same colorNode",
        "cardGroup": "NO -- there is no per-slot group",
        "sceneColorProxy": "DOES NOT EXIST -- no scene-color pass anywhere",
    },
    "sChildren": "Empty. Labels are CSS3D DOM nodes in a separate tree, "
        "driven by the same verdict loop's callbacks.",
    "whichDrawCallsDoesVisibleToggle": "Exactly one: the mesh's single draw "
        "in the single forward pass. The scene contains only card meshes and "
        "a backgroundNode.",
    "affectsSceneColorPass": "No such pass exists (refraction samples the "
        "card's own media texture).",
    "affectsRefractionReflectionPass": "No such passes exist; both effects "
        "are terms of the one material.",
    "affectsMediaDecode": "No. Videos play from mount to unmount, shared "
        "across slots. Renderer-internal texture-upload skipping for fully "
        "hidden clips is not readable from the bundle (INFERRED possible, "
        "not relied on).",
    "affectsCss3d": "The same loop iteration drives the label DOM via "
        "draw/hide callbacks -- one verdict, two surfaces, zero drift.",
    "separateMediaController": "None. Cover-fit uniforms are per media and "
        "aspect-driven; playback is mount-driven.",
    "layerDebugGlassOffComposition": "No such mode ships. The verdict is the "
        "only writer of mesh.visible in the bundle.",
}

# What V1 implementation must therefore mirror -- and where our page differs.
IMPLEMENTATION_CONSTRAINTS = {
    "targetFact": "In the Target, ONE mesh is the whole WebGL card, so "
        "s.visible = o.draw is the complete render culling.",
    "ourPage": "Our source-exact composition renders a card as more than one "
        "WebGL object (glass mesh, media surface) with QA layer toggles and "
        "adaptive quality the Target does not have. The brief's layered "
        "visibility (coverageVisible AND requestedLayerVisible AND "
        "quality/runtime) is therefore the faithful mapping: the Target's "
        "single AND collapses because it has one object and no layer system.",
    "mustNotHideSlotGroup": "The Target has no per-slot group; hiding a "
        "whole slot group on our side is only equivalent if EVERY object in "
        "that group belongs to the card's pixels. Otherwise hide per object.",
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
        sites.append({
            "id": sid,
            "byteOffset": off if off >= 0 else None,
            "occurrences": n,
            "verbatim": verbatim,
            "whatItSettles": what,
            "confidence": conf,
        })

    doc = {
        "what": "V1 render-culling source forensics: the object behind "
                "`s.visible = o.draw`, its creation chain, material, passes, "
                "and everything hiding it can and cannot touch.",
        "bundle": {"path": str(BUNDLE.relative_to(REPO)), "sha256": sha,
                   "bytes": len(data)},
        "liveBundle": ({"sha256": live, "matchesCapturedBundle": live == sha}
                      if live else None),
        "objectCreationChain": "PP component -> <group> -> <mesh ref->a.current[t]> "
                               "(geometry: shared PlaneGeometry(1,1,16,12); "
                               "material: b[m[t]] per media)",
        "sceneParentChain": "scene -> group (single, anonymous) -> card meshes; "
                            "scene.backgroundNode = screen-space gradient node",
        "materialAndPass": "MeshBasicNodeMaterial per media; single forward "
                           "pass; no render targets, no scene-color pass, no "
                           "onBeforeRender hooks in the app module",
        "sites": sites,
        "questions": QUESTIONS,
        "implementationConstraints": IMPLEMENTATION_CONSTRAINTS,
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
