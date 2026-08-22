#!/usr/bin/env python3
"""O5 §五 -- how the Target's material maps into our app, decided before code.

Every decision here is either a transcription (the Target's scheme adopted
unchanged) or a stated DEVIATION with the frozen constraint that forces it.
Nothing is left implicit, because the ways this lane can quietly go wrong are
all mapping errors: unit confusion, a re-derived layout, a mutated shared
texture, or a debug view that reintroduces the O4A shared-varying bug.

Two claims are verified numerically here rather than asserted:

  layoutReproducesL6   our frozen SourceExactLayoutFrame against the Target's
                       L6, at all five O5 viewports
  coverFitComparison   the Target's centred cover against our frozen MediaFit,
                       per clip -- the decision that follows is different
                       depending on how this lands, so it is measured first

Usage: o5-architecture.py [--out=<json>]
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

VIEWPORTS = [(1440, 900), (1920, 1080), (390, 844), (844, 390), (700, 700)]

# The three clips and their FROZEN focus/zoom (src/content/VideoClips.ts).
CLIPS = [("niulai-intro", 960, 540, 0.5, 0.5, 1.0),
         ("cursor-niulai", 960, 556, 0.5, 0.5, 1.0),
         ("pelican-ai", 960, 540, 0.5, 0.46, 1.06)]

TARGET_GRID = dict(perspective=1200, sphereRadius=5e3, planeAspect=4 / 3,
                   planeWidthRatio=.38, planeWidthRatioPortrait=.72,
                   referenceWidth=1728)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


SL = _load("o5_arch_layout", "source_layout.py")


def target_l6(w, h, r=TARGET_GRID):
    """The Target's L6, transcribed for comparison only."""
    n, a = max(w, 1), max(h, 1)
    s = max(n, a) / r["referenceWidth"]
    u = r["planeWidthRatioPortrait"] if a > n else r["planeWidthRatio"]
    c = n * u
    return dict(perspective=r["perspective"] * s,
                sphereRadius=r["sphereRadius"] * s,
                planeWidth=c, planeHeight=c / r["planeAspect"],
                cardScale=c / max(r["referenceWidth"] * r["planeWidthRatio"], 1))


def target_cover(sw, sh, plane_aspect):
    a = sw / sh
    if a > plane_aspect:
        e = plane_aspect / a
        return dict(scaleX=e, scaleY=1.0, offsetX=(1 - e) / 2, offsetY=0.0)
    s = a / plane_aspect
    return dict(scaleX=1.0, scaleY=s, offsetX=0.0, offsetY=(1 - s) / 2)


def frozen_cover(sw, sh, plane_aspect, fx, fy, zoom):
    """Our frozen MediaFit `cover`, transcribed from src/content/MediaFit.ts."""
    a = sw / sh
    rx = ry = 1.0
    if a > plane_aspect:
        rx = plane_aspect / a
    elif a < plane_aspect:
        ry = a / plane_aspect
    z = max(1.0, zoom)
    rx /= z
    ry /= z
    return dict(scaleX=rx, scaleY=ry,
                offsetX=min(max(fx, 0), 1) * (1 - rx),
                offsetY=(1 - min(max(fy, 0), 1)) * (1 - ry))


def main() -> int:
    out = REPO / "qa-v5/optics-o5/o5-architecture.json"
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k == "out":
            out = Path(v)

    layout_rows, layout_ok = [], True
    for w, h in VIEWPORTS:
        f, t = SL.layout(w, h), target_l6(w, h)
        fields = {}
        for k in ("planeWidth", "planeHeight", "sphereRadius", "cardScale",
                  "perspective"):
            same = abs(f[k] - t[k]) < 1e-9
            layout_ok &= same
            fields[k] = {"ours": round(f[k], 6), "target": round(t[k], 6),
                         "equal": same}
        layout_rows.append({"viewport": f"{w}x{h}", "fields": fields})

    cover_rows, cover_all_equal = [], True
    plane_aspect = TARGET_GRID["planeAspect"]
    for name, sw, sh, fx, fy, z in CLIPS:
        t = target_cover(sw, sh, plane_aspect)
        o = frozen_cover(sw, sh, plane_aspect, fx, fy, z)
        equal = all(abs(t[k] - o[k]) < 1e-12 for k in t)
        cover_all_equal &= equal
        cover_rows.append({
            "clip": name, "sourceWidth": sw, "sourceHeight": sh,
            "frozenFocus": {"focusX": fx, "focusY": fy, "zoom": z},
            "targetCentredCover": {k: round(v, 6) for k, v in t.items()},
            "frozenMediaFit": {k: round(v, 6) for k, v in o.items()},
            "equal": equal,
        })

    doc = {
        "what": "O5 §五 -- the architecture decision, fixed before any "
                "candidate code exists. Two lanes only; every deviation from "
                "the Target's own scheme is named, with the frozen constraint "
                "that forces it.",
        "lanes": {
            "current": {
                "switch": "opticalBody=current",
                "body": "existing convex ConvexGlassGeometryV4 + shared "
                        "LiquidGlassMaterialV4 body + reflection shell",
                "media": "separate media plane, MeshBasicMaterial per clip",
                "sceneColour": "SceneColorPipelineV4 pass runs and is sampled",
                "role": "exact rollback and the control for §六. Must remain "
                        "byte-identical to a 5a87751 build.",
            },
            "target-source": {
                "switch": "opticalBody=target-source",
                "body": "PlaneGeometry(1,1,16,12), one material PER CLIP, "
                        "positionNode sphere dome, SDF alpha, analytic bevel "
                        "normal, own-media per-IOR spectral refraction, "
                        "System B environment and white SDF rim in the SAME "
                        "material",
                "media": "the body material samples its own VideoTexture "
                         "directly; no media plane in Beauty",
                "sceneColour": "not sampled; the pass is skipped for this "
                               "lane at build time",
                "role": "the O5 candidate. Default stays `current` until "
                        "product review.",
            },
        },
        "decisions": [
            {
                "id": "unitPlaneAndScale",
                "decision": "Adopt the Target's unit-plane scheme unchanged: "
                            "PlaneGeometry(1,1,16,12), mesh scaled to "
                            "(planeWidth, planeHeight, 1), and a planeSize "
                            "uniform carrying the same two numbers.",
                "why": "The Target's shader uses planeSize BOTH to convert "
                       "positionLocal into card pixels and to undo the "
                       "anisotropic scale for direction vectors "
                       "(viewVector multiplies xy by planeSize, toWorldFn "
                       "divides by it). Baking the card size into the geometry "
                       "instead would break that pair and skew refraction and "
                       "reflection on non-square cards.",
                "kind": "TRANSCRIPTION",
            },
            {
                "id": "uniformsFromFrozenLayout",
                "decision": "planeSize, sphereRadius, cardScale come from the "
                            "FROZEN SourceExactLayoutFrame. L6 is never "
                            "re-derived in the material or the grid.",
                "why": "Layout is ACCEPTED/FROZEN and O5 may not modify layout "
                       "formulas. Our frame already reproduces L6 exactly at "
                       "every O5 viewport (see layoutReproducesL6), so reading "
                       "it is both correct and the only non-duplicating route.",
                "kind": "TRANSCRIPTION",
            },
            {
                "id": "coverFitMechanismNotValues",
                "decision": "Adopt the Target's coverScale/coverOffset "
                            "MECHANISM and clamp-then-cover ordering, but feed "
                            "it the FROZEN MediaFit values, not the Target's "
                            "centred formula.",
                "why": "Media focus/crop is frozen by §一.18. Clips 0 and 1 "
                       "(focus 0.5/0.5, zoom 1) reproduce the Target's centred "
                       "cover to the last bit; clip 2 carries a frozen "
                       "2026-08-20 product decision (focusY 0.46, zoom 1.06) "
                       "that the Target's formula does not express. Adopting "
                       "the Target's formula would silently re-crop that clip "
                       "and fail the Media Fit regression. The mapping is 1:1 "
                       "and lossless: coverScale = (repeatX, repeatY), "
                       "coverOffset = (offsetX, offsetY), which is exactly "
                       "three's texture repeat/offset convention.",
                "kind": "DEVIATION_FORCED_BY_FROZEN_SYSTEM",
                "evidence": "coverFitComparison below",
            },
            {
                "id": "candidateOwnsItsTextures",
                "decision": "The candidate lane creates its OWN VideoTexture "
                            "per clip (sRGB, ClampToEdge, no mipmaps) and "
                            "never mutates the control lane's reel textures.",
                "why": "The control lane must stay byte-identical for §六. "
                       "Mutating a shared texture's wrap or colour space to "
                       "suit the candidate would change the control's pixels "
                       "and forfeit the identity proof. Two textures over one "
                       "video element is the cost; it is paid once per clip, "
                       "not per card.",
                "kind": "DEVIATION_FORCED_BY_CONTROL_IDENTITY",
            },
            {
                "id": "materialPerClipBySlotIdentity",
                "decision": "One material per clip, assigned to cards by the "
                            "FROZEN slot identity. No per-card materials.",
                "why": "Matches the Target exactly, and is safe here because "
                       "nothing gives our cards per-card opacity: no site in "
                       "the Target bundle assigns .opacity on these materials, "
                       "and our own body has no per-card opacity either (only "
                       "the control lane's reflection shell has an "
                       "opacityNode, and the candidate has no shell). Slot "
                       "identity is frozen, so which clip a card shows does "
                       "not change.",
                "kind": "TRANSCRIPTION",
            },
            {
                "id": "noShellNoMediaPlaneInBeauty",
                "decision": "The candidate draws ONE mesh per card. No "
                            "reflection shell, no separate media plane in "
                            "Beauty. The media plane is retained for "
                            "media-only QA captures only.",
                "why": "The Target has no shell and no media plane: "
                       "reflection, refraction and media all live in one "
                       "material (absence claim noReflectionShell). Keeping "
                       "our shell would double-count the environment.",
                "kind": "TRANSCRIPTION",
            },
            {
                "id": "sceneColourPassSkipped",
                "decision": "The scene-colour pass is skipped for the "
                            "candidate lane, at build time.",
                "why": "The candidate body never samples it (absence claim "
                       "noSceneColourTarget). §十 explicitly allows removing "
                       "the pass. Build-time, so the control lane's pipeline "
                       "is untouched.",
                "kind": "TRANSCRIPTION",
            },
            {
                "id": "outputTransformTranscribedInertly",
                "decision": "Set `material.toneMapped = false`, exactly as the "
                            "Target does, and change NOTHING about the "
                            "renderer's tone mapping for this lane.",
                "why": "O4 found that three's WebGPU node renderer never reads "
                       "Material.toneMapped, and drew from it the conclusion "
                       "that the intent had to be implemented at the renderer "
                       "stage instead. Reading the Target's own bundle "
                       "reverses that: all four `.toneMapped` reads there are "
                       "WebGL-only parameter builders, none in the node path, "
                       "so the Target's flag is inert for exactly the same "
                       "reason ours is. Its cards ARE tone-mapped by its "
                       "output stage, despite the flag. Forcing NoToneMapping "
                       "on our candidate would therefore introduce a "
                       "difference the Target does not have. Being faithful "
                       "means reproducing the inertness.",
                "kind": "TRANSCRIPTION",
                "evidence": "three.webgpu.js: 0 occurrences of `.toneMapped`. "
                            "Target bundle: 4 occurrences, at bytes 216960, "
                            "217782, 282464 and 387472, all WebGL paths "
                            "(WebGLBackground and the WebGLProgram parameter "
                            "builders).",
                "supersedes": "the O4-era reading that this needed a renderer "
                              "stage deviation",
            },
            {
                "id": "sampleCountMapping",
                "decision": "high -> 5 samples, medium -> 5, low -> 3.",
                "why": "The Target has two device tiers (high 5 / low 3) and "
                       "we have three quality levels. Our adaptive quality "
                       "policy is frozen, so the candidate reads OUR level and "
                       "maps it. Mapping medium to 5 keeps the optical "
                       "behaviour identical across the two tiers a desktop "
                       "review will actually see; low keeps the Target's own "
                       "floor of 3.",
                "kind": "DEVIATION_3_TIER_TO_2_TIER",
            },
            {
                "id": "debugViewsAreBuildTime",
                "decision": "Every candidate debug view (SDF mask, normal, "
                            "media-only, glass-only) is a BUILD-TIME separate "
                            "program, never a runtime branch over a shared "
                            "varying.",
                "why": "This is the exact shape of the O4A defect: three's TSL "
                       "emits a shared varying's unpack into only the first "
                       "branch that references it, so every other branch reads "
                       "a zero-initialised private. A build-time program per "
                       "view cannot express that bug. It also keeps the Beauty "
                       "program free of debug branches entirely.",
                "kind": "DEVIATION_FORCED_BY_ENGINE_DEFECT",
            },
            {
                "id": "envSampleCeilingRetained",
                "decision": "O2's envSampleCeiling guard (clamp the HDR sample "
                            "at 16 before the LERP) is RETAINED in the "
                            "candidate, and recorded as a local deviation.",
                "why": "The Target has no such clamp. Ours exists because a "
                       "hot texel can inject Inf, and 0 * Inf = NaN would "
                       "destroy the envMixScale=0 floor. The ceiling is far "
                       "above envIntensity*envMaxMix, so it cannot bind in "
                       "normal rendering -- it is a NaN guard, not a look "
                       "control. Recorded rather than dropped.",
                "kind": "DEVIATION_LOCAL_SAFETY",
            },
            {
                "id": "coverageCullingUnchanged",
                "decision": "Coverage culling uses the already-frozen verdict. "
                            "Render-culling instruments may become mode-aware "
                            "(the candidate has one mesh per card where the "
                            "control has three), but the VERDICT -- which "
                            "slots draw -- is identical in both lanes.",
                "why": "§十二 allows mode-aware instruments and forbids a "
                       "changed verdict. Draw-call COUNTS legitimately differ "
                       "between a 3-mesh and a 1-mesh card; slot membership "
                       "must not.",
                "kind": "TRANSCRIPTION",
            },
            {
                "id": "layoutNotAdapted",
                "decision": "No layout, camera, card size or slot placement "
                            "changes to accommodate the material.",
                "why": "§一.18. The unit-plane scheme is designed to make this "
                       "unnecessary: the material adapts to the card through "
                       "planeSize, so the card never adapts to the material.",
                "kind": "CONSTRAINT",
            },
        ],
        "layoutReproducesL6": {
            "allEqual": layout_ok,
            "why": "If our frozen frame did not reproduce L6, every Target "
                   "constant would land at the wrong size and the whole "
                   "contract would be inapplicable. It does, exactly, at all "
                   "five O5 viewports including the new 700x700.",
            "rows": layout_rows,
        },
        "coverFitComparison": {
            "planeAspect": plane_aspect,
            "allEqual": cover_all_equal,
            "finding": "Clips 0 and 1 reproduce the Target's centred cover "
                       "exactly. Clip 2 differs by a frozen product decision "
                       "(focusY 0.46, zoom 1.06). Hence the "
                       "coverFitMechanismNotValues decision above.",
            "rows": cover_rows,
        },
        "notAdopted": [
            {"what": "The Target's device-tier predicate (coarse pointer / "
                     "cores / memory)",
             "why": "Our adaptive quality policy is frozen; we read our own "
                    "quality level instead."},
            {"what": "The Target's centred cover VALUES",
             "why": "Media focus/crop is frozen; the mechanism is adopted, the "
                    "values are ours."},
            {"what": "A renderer-stage tone-mapping override for the "
                     "candidate lane",
             "why": "The Target does not have one either. Its "
                    "`toneMapped:false` is as inert as ours, so overriding "
                    "would be a difference rather than a match."},
        ],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"layout reproduces L6: {layout_ok}")
    print(f"cover fit identical for all clips: {cover_all_equal}")
    for r in cover_rows:
        print(f"  {r['clip']:16} {'identical' if r['equal'] else 'DIFFERS (frozen focus/zoom)'}")
    print(f"decisions: {len(doc['decisions'])}")
    print(f"-> {out}")
    return 0 if layout_ok else 1


if __name__ == "__main__":
    sys.exit(main())
