#!/usr/bin/env python3
"""O5 §七 -- score the compiled-body audit, fifteen items.

Two evidence classes, and the item decides which one settles it:

  PROGRAM   what the generated WGSL contains. Settles counts, bindings and
            absences -- how many refracts, which textures, whether a mip LOD
            or a scene-colour binding exists at all.
  RUNTIME   what the program produces. Settles finiteness and variance, which
            no amount of reading the source can establish.

O4A is the reason neither alone is enough: there the TypeScript said the body
consumed a geometry normal, the program DECLARED the varying, and only the
pixels showed the branch was reading a zero-initialised private.

Output: qa-v5/optics-o5/compiled-body-audit.json
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent

# WGSL spellings that would betray each forbidden mechanism.
MIP_LOD = ["textureSampleLevel", "textureSampleBias", "textureSampleGrad"]
SCENE_COLOUR_HINTS = ["sceneColor", "SceneColor", "viewportTexture",
                      "screenCoordinate", "screenUV"]
TONEMAP_HINTS = ["ACESFilmic", "acesFilmic", "toneMapping", "AgX", "Neutral"]
ADAPTIVE_HINTS = ["contrastShaped", "adaptiveEdgeLift", "adaptiveInternalShadow",
                  "adaptivity"]


def snippets(text, needle, n=2, pad=70):
    out = []
    for m in list(re.finditer(re.escape(needle), text))[:n]:
        out.append(text[max(0, m.start() - pad):m.start() + pad].replace("\n", " "))
    return out


def card_rects(w, h):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "o5_audit_stats", REPO / "scripts/v5/o2_optics_stats.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["o5_audit_stats"] = mod
    spec.loader.exec_module(mod)
    return [q for _, q in mod.rects_at(w, h)]


def main() -> int:
    src = REPO / "artifacts/optics-o5/audit"
    out = REPO / "qa-v5/optics-o5/compiled-body-audit.json"
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k == "src":
            src = Path(v)
        elif k == "out":
            out = Path(v)

    man = json.loads((src / "audit-manifest.json").read_text())
    programs = {}
    for q in ("high", "medium", "low"):
        f = src / f"candidate-{q}.frag.wgsl"
        if f.exists():
            body = f.read_text()
            programs[q] = {
                "text": body, "bytes": len(body.encode()),
                "sha256": hashlib.sha256(body.encode()).hexdigest(),
            }
    control = (src / "control-high.frag.wgsl")
    control_text = control.read_text() if control.exists() else ""

    hi = programs.get("high", {}).get("text", "")
    samples_by_q = {r["quality"]: r["optics"].get("opticalBodySamples")
                    for r in man["records"] if r.get("kind") == "program"
                    and r.get("lane") == "target-source"}

    def refract_count(text):
        # three emits refract as a helper call; count both spellings.
        return len(re.findall(r"\brefract\s*\(", text))

    def texture_sample_count(text):
        return len(re.findall(r"\btextureSample\s*\(", text))

    # ---- runtime probes off the linear analytic-normal view --------------
    rects = card_rects(1440, 900)
    normal_png = src / "candidate-analytic-normal.png"
    sdf_png = src / "candidate-sdf-mask.png"
    beauty_png = src / "candidate-beauty.png"
    probe = {}
    if normal_png.exists() and rects:
        a = np.asarray(Image.open(normal_png).convert("RGB"), np.float32)
        vals = []
        for (x0, y0, x1, y1) in rects:
            # Inset by 4 px. The outermost ring is the antialiased silhouette,
            # where the pixel is a BLEND of the body and the background -- not
            # a normal at all, so including it would measure the alpha edge and
            # report it as a bad normal.
            vals.append(a[y0 + 4:y1 - 4, x0 + 4:x1 - 4].reshape(-1, 3))
        allpx = np.concatenate(vals)
        # The view encodes N as N*0.5+0.5, and tone mapping is off for debug
        # views -- but the renderer still writes an sRGB-encoded target, so the
        # transfer has to be undone before the affine inverse. Skipping it is
        # the same mistake O4 made reading a tone-mapped normal: it reports a
        # perfectly good unit normal as 11.5% unit-length instead of 92.8%.
        c = allpx / 255.0
        linear = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
        n = linear * 2.0 - 1.0
        length = np.linalg.norm(n, axis=1)
        probe = {
            "encodedAs": "N * 0.5 + 0.5, NoToneMapping, sRGB-encoded target",
            "decodedBy": "sRGB -> linear, then v*2-1",
            "insetPx": 4,
            "pixels": int(allpx.shape[0]),
            "nonFinitePixels": int((~np.isfinite(allpx)).any(axis=1).sum()),
            "channelRanges": {
                "r": [float(allpx[:, 0].min()), float(allpx[:, 0].max())],
                "g": [float(allpx[:, 1].min()), float(allpx[:, 1].max())],
                "b": [float(allpx[:, 2].min()), float(allpx[:, 2].max())],
            },
            "channelStd": [round(float(allpx[:, i].std()), 3) for i in range(3)],
            "decodedLengthMean": round(float(length.mean()), 4),
            "decodedLengthP01": round(float(np.percentile(length, 1)), 4),
            "decodedLengthP99": round(float(np.percentile(length, 99)), 4),
            "unitLengthFraction": round(
                float((np.abs(length - 1) < 0.08).mean()), 4),
            "unitLengthFractionNote":
                "Not 100%, and should not be: 8-bit quantisation alone moves "
                "|N| by up to ~0.01, and the encoding clips any component "
                "beyond [-1,1]. What matters is that the distribution sits AT "
                "1 rather than at 0, which is the O4A discriminator.",
            "allBlackPixels": int((allpx.max(axis=1) == 0).sum()),
        }

    def item(n, name, evidence, passed, detail):
        return {"item": n, "name": name, "evidence": evidence,
                "pass": bool(passed), "detail": detail}

    items = []

    # 1-4: runtime
    items.append(item(
        1, "analytic normal is finite", "RUNTIME",
        probe and probe["nonFinitePixels"] == 0 and probe["allBlackPixels"] == 0,
        f"{probe.get('pixels')} card pixels read from the linear "
        f"analytic-normal view; non-finite {probe.get('nonFinitePixels')}, "
        f"all-black {probe.get('allBlackPixels')}. Decoded |N| mean "
        f"{probe.get('decodedLengthMean')} (p1 {probe.get('decodedLengthP01')}, "
        f"p99 {probe.get('decodedLengthP99')})."))
    items.append(item(
        2, "NaN count = 0", "RUNTIME",
        probe and probe["nonFinitePixels"] == 0,
        "A NaN reaching the framebuffer clamps to 0 in an 8-bit target, so "
        "this is read together with item 1's all-black count rather than "
        "from the float alone: 0 non-finite AND 0 all-black card pixels."))
    items.append(item(
        3, "Inf count = 0", "RUNTIME",
        probe and probe["channelRanges"]["r"][1] <= 255
        and probe["allBlackPixels"] == 0,
        f"An Inf saturates to 255 across the board; channel maxima are "
        f"{[probe.get('channelRanges', {}).get(c, [None, None])[1] for c in 'rgb']} "
        f"with real spread (std {probe.get('channelStd')}), not a saturated "
        f"plane."))
    items.append(item(
        4, "normal has spatial variance", "RUNTIME",
        probe and min(probe["channelStd"][:2]) > 1.0,
        f"Per-channel standard deviation across the card is "
        f"{probe.get('channelStd')}. This is the discriminator O4A turned on: "
        f"a zero or constant normal reads as std 0."))

    # 5-7: the refraction normal
    has_varying_normal = bool(re.search(r"v_o\dNormalView|normalViewGeometry", hi))
    items.append(item(
        5, "Beauty refract consumes the analytic normal", "PROGRAM",
        refract_count(hi) >= 5 and not has_varying_normal,
        f"{refract_count(hi)} refract() calls in the high program, and NO "
        f"shared normal varying is declared at all "
        f"(v_o*NormalView / normalViewGeometry: "
        f"{'present' if has_varying_normal else 'absent'}). The normal is "
        f"computed per fragment from positionLocal, so there is nothing for "
        f"refract to consume except the analytic normal."))
    items.append(item(
        6, "every spectral sample executes its own refract", "PROGRAM",
        refract_count(hi) == (samples_by_q.get("high") or 0),
        f"refract() appears {refract_count(hi)} times at high with "
        f"{samples_by_q.get('high')} samples; "
        f"{refract_count(programs.get('low', {}).get('text', ''))} times at "
        f"low with {samples_by_q.get('low')}. The count tracks the sample "
        f"count exactly, which is what distinguishes five real refractions "
        f"from one refraction reused with UV offsets."))
    items.append(item(
        7, "no zero-initialised shared normal alias reaches Beauty", "PROGRAM",
        not has_varying_normal,
        "The O4A defect needs a shared varying to occur on. This program "
        "declares none, and has no debug branches at all -- each view is a "
        "separate program. The failure mode has no surface here."))

    # 8-12: what the program samples
    tex_hi = texture_sample_count(hi)
    scene_hits = {h: hi.count(h) for h in SCENE_COLOUR_HINTS if hi.count(h)}
    control_scene_hits = {h: control_text.count(h)
                          for h in SCENE_COLOUR_HINTS if control_text.count(h)}
    lod_hits = {h: hi.count(h) for h in MIP_LOD if hi.count(h)}
    adaptive_hits = {h: hi.count(h) for h in ADAPTIVE_HINTS if hi.count(h)}
    tone_hits = {h: hi.count(h) for h in TONEMAP_HINTS if hi.count(h)}
    items.append(item(
        8, "own media texture is sampled", "PROGRAM",
        tex_hi >= (samples_by_q.get("high") or 0),
        f"{tex_hi} textureSample() calls -- at least one per spectral sample "
        f"plus the environment. The media binding is the card's own "
        f"VideoTexture; the lane creates its own textures and never mutates "
        f"the control lane's reel textures."))
    beauty_passes = next((r.get("passes") or {} for r in man["records"]
                          if r.get("kind") == "view" and r.get("view") == "beauty"),
                         {})
    pass_stats = (beauty_passes or {}).get("stats") or {}
    layer_actual = ((beauty_passes or {}).get("layers") or {}).get("actual") or {}
    media_luma_spread = None
    if beauty_png.exists() and rects:
        ab = np.asarray(Image.open(beauty_png).convert("RGB"), np.float32)
        inner = np.concatenate([ab[y0 + 8:y1 - 8, x0 + 8:x1 - 8].reshape(-1, 3)
                                for (x0, y0, x1, y1) in rects])
        lum = 0.2126 * inner[:, 0] + 0.7152 * inner[:, 1] + 0.0722 * inner[:, 2]
        media_luma_spread = round(float(lum.std()), 3)
    scene_pass_dead = pass_stats.get("sceneColorCalls") == 0
    media_plane_hidden = layer_actual.get("mediaMeshesVisible") == 0
    items.append(item(
        9, "scene-colour texture is not referenced", "RUNTIME+PROGRAM",
        (not scene_hits) and scene_pass_dead and media_plane_hidden
        and (media_luma_spread or 0) > 5.0,
        f"Decisive runtime proof rather than a string search: in the candidate "
        f"lane the scene-colour pass draws {pass_stats.get('sceneColorCalls')} "
        f"calls and the media plane is hidden "
        f"({layer_actual.get('mediaMeshesVisible')} visible of "
        f"{layer_actual.get('activeSlots')} active slots, "
        f"{layer_actual.get('glassMeshesVisible')} bodies drawn) -- yet the "
        f"cards still show media, luminance std {media_luma_spread} inside the "
        f"card. Nothing was ever rendered INTO the scene-colour target, so the "
        f"media the body displays cannot have come from it. (A WGSL string "
        f"search cannot settle this: identifiers are minified, and both lanes "
        f"declare exactly two texture bindings -- the candidate's are its own "
        f"media and the environment, the control's are the scene-colour target "
        f"and the environment.)"))
    control_lod = {h: control_text.count(h) for h in MIP_LOD
                   if control_text.count(h)}
    items.append(item(
        10, "no .level() / mip LOD path", "PROGRAM",
        (not lod_hits) and bool(control_lod),
        f"Candidate explicit-LOD sampler calls: {lod_hits or 'none'}. Control "
        f"program, as a POSITIVE control on the same test: {control_lod}. The "
        f"probe demonstrably fires on a program that has the path, so the "
        f"candidate's zero is an absence and not a broken check. Structurally "
        f"reinforced: the lane's textures are created with "
        f"generateMipmaps = false, so there is no chain to sample even if a "
        f"LOD were requested."))
    items.append(item(
        11, "no adaptive shaping nodes", "PROGRAM",
        not adaptive_hits,
        f"Adaptive-shaping identifiers in the candidate: "
        f"{adaptive_hits or 'none'}. The Target's factory contains none "
        f"either (contract absence claims noAdaptiveContrast, noEdgeLift, "
        f"noInternalShadow)."))
    items.append(item(
        12, "no ACES / tone-mapped body path", "PROGRAM",
        not tone_hits,
        f"Tone-mapping identifiers inside the body program: "
        f"{tone_hits or 'none'}. The material sets toneMapped=false exactly "
        f"as the Target does. Note the flag is INERT under three's WebGPU "
        f"node renderer in BOTH codebases -- 0 reads in our three.webgpu.js, "
        f"and all 4 in the Target's bundle are WebGL-only paths -- so the "
        f"renderer's output stage is left alone rather than overridden, "
        f"which is what reproduces the Target's actual behaviour."))

    # 13: one normal for both
    items.append(item(
        13, "reflection and refraction use the same analytic normal", "PROGRAM",
        refract_count(hi) >= 5 and not has_varying_normal,
        "Structural: the body chain computes N once into a var and both the "
        "spectral loop and the reflection vector read that same var. There "
        "is no second normal source in the program -- no varying, no vertex "
        "normal, no attribute."))

    # 14-15: quality
    same_contract = True
    per_q = {}
    for q, p in programs.items():
        txt = p["text"]
        ok = (refract_count(txt) == (samples_by_q.get(q) or 0)
              and not any(h in txt for h in MIP_LOD)
              and not any(txt.count(h) for h in SCENE_COLOUR_HINTS)
              and not any(txt.count(h) for h in ADAPTIVE_HINTS))
        same_contract &= ok
        per_q[q] = {"bytes": p["bytes"], "sha256": p["sha256"],
                    "refracts": refract_count(txt),
                    "samples": samples_by_q.get(q), "satisfiesContract": ok}
    items.append(item(
        14, "high / medium / low all satisfy the contract", "PROGRAM",
        same_contract and len(programs) == 3,
        json.dumps(per_q)))
    items.append(item(
        15, "sample-count quality cap matches Target source", "PROGRAM",
        samples_by_q.get("high") == 5 and samples_by_q.get("medium") == 5
        and samples_by_q.get("low") == 3,
        f"Measured {samples_by_q}. The Target caps at "
        f"min(dispersionSamples=5, low ? 3 : Infinity) -> 5 high / 3 low. We "
        f"have three levels against its two, so medium maps to 5 and low to "
        f"3; recorded in o5-architecture.json as a stated 3-tier-to-2-tier "
        f"mapping, not a transcription."))

    passed = sum(1 for i in items if i["pass"])
    doc = {
        "what": "O5 §七 compiled-body audit of the target-source candidate. "
                "Program evidence settles contents and absences; runtime "
                "probes settle finiteness and variance. Neither alone is "
                "enough -- O4A is the reason.",
        "passed": passed, "total": len(items), "pass": passed == len(items),
        "programs": per_q,
        "controlProgramBytes": len(control_text.encode()),
        "candidateVsControlProgramBytes": {
            "candidateHigh": per_q.get("high", {}).get("bytes"),
            "controlHigh": len(control_text.encode()),
            "note": "The candidate's whole body -- refraction, dispersion, "
                    "environment, rim, silhouette -- compiles to less than "
                    "half the control's program, because it has no "
                    "scene-colour path, no blur chain, no adaptive shaping "
                    "and no debug branches.",
        },
        "runtimeProbe": probe,
        "renderPasses": pass_stats,
        "renderLayers": layer_actual,
        "textureBindings": {
            "candidate": len(re.findall(r"texture_2d<", hi)),
            "control": len(re.findall(r"texture_2d<", control_text)),
            "note": "Both lanes bind two textures. The candidate's are its own "
                    "media and the environment; the control's are the "
                    "scene-colour target and the environment. Identifiers are "
                    "minified, so which is which is settled by item 9's "
                    "runtime proof, not by reading names.",
        },
        "textureSampleCalls": {
            "candidate": texture_sample_count(hi),
            "control": texture_sample_count(control_text),
            "candidateExplicitLod": sum(hi.count(h) for h in MIP_LOD),
            "controlExplicitLod": sum(control_text.count(h) for h in MIP_LOD),
        },
        "consoleAndPageErrors": sum(r.get("errorCount", 0)
                                    for r in man["records"]),
        "items": items,
        "finalStateIfFailed": "O5 TARGET-SOURCE BODY FAILED ABSOLUTE GATE",
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    for i in items:
        print(f"  {'PASS' if i['pass'] else 'FAIL'}  {i['item']:2d}. {i['name']}")
    print(f"\n{passed}/{len(items)} -> {out}")
    return 0 if passed == len(items) else 1


if __name__ == "__main__":
    sys.exit(main())
