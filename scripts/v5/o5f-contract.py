#!/usr/bin/env python3
"""O5F §四-§七 -- the material-cache contract, sealed before any capture.

Generated from o5f_stress.py -- the module the scorer itself imports -- so a
threshold cannot be one thing here and another in the verdict. Committed in
the material-cache CODE commit: every gate below is registered before the
cached candidate produces a single scored pixel or heap sample.

Output: qa-v5/optics-o5f/material-cache-contract.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = REPO / "qa-v5/optics-o5f/material-cache-contract.json"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o5f_stress_c", "o5f_stress.py")

BASELINE = "445037e11eb44ae07bca6360707e043d969b1d4b"

doc = {
    "what": "O5F Phase A -- the finite material-set cache: what was built, "
            "the identity gate that must pass before any memory scoring, and "
            "the pre-registered stress gate. Sealed in the material-cache "
            "code commit, before any cached-candidate capture.",
    "baselineCommit": BASELINE,

    "problem": {
        "statement": "O5R §十二: the candidate lane retains ~68 KB per "
                     "quality step. setQuality() rebuilt one material per "
                     "clip, rebound every slot and disposed the previous "
                     "set; the dispose did not return the memory. The "
                     "quality-cycle diagnostic arm rose 39.36 MB in six "
                     "minutes against <= 2.06 MB in every other arm; the "
                     "shipped lane is flat under the identical workload.",
        "why_rebuild_existed": "the spectral sample count is a build-time "
                               "literal (the Target bakes its weights on the "
                               "CPU), so 5-sample and 3-sample bodies are "
                               "different PROGRAMS, not a uniform.",
        "why_rebuild_was_wasteful": "high and medium both use 5 samples, yet "
                                    "every high<->medium step rebuilt and "
                                    "disposed three materials for an "
                                    "identical program.",
    },

    "cache": {
        "keyFields": ["sampleCount (5|3)", "bodyView", "environmentMode",
                      "clampMode", "opticalBody lane"],
        "keyFormat": "samples=<n>|view=<view>|env=<mode>|clamp=<clamped|"
                     "unclamped>|lane=<opticalBody>",
        "entryOwns": ["one material per clip", "per-clip coverScale/"
                      "coverOffset uniforms", "material UUIDs",
                      "creation generation"],
        "entriesShare": ["the Video elements", "the candidate VideoTextures",
                         "the HDR environment texture", "the 16x12 body "
                         "plane geometry", "the layout uniform block"],
        "productSets": "one 5-sample set shared by high and medium, one "
                       "3-sample set for low -- BOTH built at initialisation "
                       "on the product Beauty path (§四 rule 2, second "
                       "option), so no later transition can create a "
                       "material and the first drop to low binds a set that "
                       "already exists.",
        "qaViews": "QA measurement views create only the set they use, "
                   "through the same keyed map -- finite because the key "
                   "space is finite and a capture page holds its view and "
                   "quality for its whole life.",
        "qualityChange": "switch the active cached set and rebind "
                         "slot.material references. Nothing is created once "
                         "both product sets exist; nothing is EVER disposed "
                         "on a switch; the inactive set stays cached so the "
                         "original material UUIDs return on the next visit.",
        "resize": "applyMediaFits writes coverScale/coverOffset into EVERY "
                  "cached set, active or not (§四 rule 5).",
        "dispose": "all cached sets are disposed exactly once, in "
                   "disposePool, and nowhere else (§四 rule 8).",
        "retiredDefect": "until O5F, the candidate lane fell through to the "
                         "control lane's quality path, which rebound every "
                         "glass mesh to the CONVEX volume geometry on the "
                         "first quality step -- collapsing the 16x12 "
                         "tessellation the vertex-stage dome is resolved "
                         "by. §四.4 defines a candidate quality change as a "
                         "set switch plus a material rebind and nothing "
                         "else; implementing that definition retires the "
                         "defect. The card's 16x12 plane is part of the "
                         "source contract, not a quality knob. Demonstrated "
                         "in the identity evidence: at the baseline build a "
                         "high->low->high cycle does not return to the "
                         "original pixels; at the O5F build it must, "
                         "exactly.",
        "opticalOutputUnchanged": "§四 rule 10: no Target-source optical "
                                  "output changes. Proven by the §六 gate "
                                  "below, not asserted.",
    },

    "truthSurface": {
        "surface": "__ILG_QA__.getBodyMaterialCacheTruth()",
        "fields": ["activeKey", "cacheKeys", "cacheSize",
                   "sets[].sampleCount", "sets[].materialUuids",
                   "sets[].coverScale", "sets[].coverOffset",
                   "materialCreationCount", "materialDisposalCount",
                   "cacheSwitchCount", "videoTextureUuids",
                   "environmentUuid", "quality", "opticalBody", "bodyView",
                   "rendererTextures", "rendererGeometries",
                   "rendererPrograms"],
        "invariants": [
            "after warm-up cacheSize is constant",
            "creationCount is constant",
            "VideoTexture UUIDs never change",
            "high and medium use the same material UUIDs",
            "low uses the cached 3-sample UUIDs",
            "returning to high restores the original 5-sample UUIDs",
        ],
        "rendererCounts": "renderer.info.memory (three 0.185 WebGPU) DOES "
                          "publish textures, geometries and programs; O5R "
                          "reported the program count as unavailable and "
                          "this round corrects that. A field the backend "
                          "does not carry reads null, never a substitute.",
    },

    "identityGate": {
        "order": "§六 runs BEFORE any memory scoring.",
        "baseline": "a git worktree at the baseline commit, built with the "
                    "same node_modules and vite, served locally; media "
                    "routes injected per-context identically on both sides.",
        "A_controlIdentity": {
            "lane": "opticalBody=current",
            "states": 35,
            "coding": "5 viewports x 7 fixed states (rest, pointer x3, "
                      "slow-drag, fast-flick, touch), the O5 control-"
                      "identity harness. Every pair must differ by EXACTLY "
                      "ZERO pixels with every probe field matching.",
        },
        "B_candidateIdentity": {
            "lane": "opticalBody=target-source-unclamped",
            "states": 35,
            "coding": "same 35 states, same deterministic media, same "
                      "frozen time. EXACTLY ZERO differing pixels. This is "
                      "what proves §四 rule 10 -- the cache changed no "
                      "optical output.",
        },
        "C_programIdentity": {
            "coding": "sha256 of the generated WGSL, vertex AND fragment "
                      "stages separately, at the 5-sample tier and after a "
                      "switch to the 3-sample tier, O5F against baseline. "
                      "All four pairs must match exactly.",
        },
        "failureState": "O5F MATERIAL CACHE IDENTITY FAILED -- stop before "
                        "portrait work.",
    },

    "stressGate": {
        "preRegistered": "thresholds sealed here, in the code commit, "
                         "before the cached candidate is measured. The "
                         "control-derived terms are filled by the three "
                         "control sessions of the same run -- the formula "
                         "is sealed, so nothing can be tuned after seeing "
                         "the candidate (the O5R target-relative-window "
                         "pattern).",
        "runs": [
            f"1,200 quality changes: {' -> '.join(S.QUALITY_CYCLE_ORDER)} "
            f"repeated {S.QUALITY_CYCLES} times, media frozen, page paused",
            f"{S.CANDIDATE_SESSIONS} independent {S.SESSION_MINUTES}-minute "
            "candidate sessions",
            f"{S.CONTROL_SESSIONS} independent {S.SESSION_MINUTES}-minute "
            "control sessions",
            "desktop drag / wrap, mobile touch / wrap, resize / orientation "
            "cycles -- the rotating O5R §十二 session workload, unchanged",
        ],
        "sampling": {
            "intervalMs": S.SAMPLE_INTERVAL_MS,
            "perSample": ["JS heap", "material cache truth (incl. UUIDs)",
                          "VideoTexture UUIDs", "renderer texture / "
                          "geometry / program counts", "pool state",
                          "video element count", "active slot count",
                          "console/page errors"],
            "screenshots": "first frame before any QA hook, then one per "
                           "minute; all travel in the review package",
        },
        "checks": [
            {"n": 1, "check": "after both product sets exist, "
                              "materialCreationCount does not increase",
             "threshold": f"== {S.PRODUCT_CREATION_COUNT} at ready and at "
                          "every later sample"},
            {"n": 2, "check": "cacheSize remains finite and constant",
             "threshold": f"== {S.PRODUCT_CACHE_SIZE} at every sample"},
            {"n": 3, "check": "high <-> medium creates zero material",
             "threshold": "creationCount identical across every "
                          "high<->medium step of the cycle harness"},
            {"n": 4, "check": "the original material UUIDs return after "
                              "every cycle",
             "threshold": "per-tier UUID list identical at every visit "
                          "across all 1,200 steps; VideoTexture and "
                          "environment UUIDs never change"},
            {"n": 5, "check": "final-third heap slope",
             "threshold": "<= max(control repeatability window, "
                          f"{S.HEAP_SLOPE_FLOOR_MB_PER_MIN} MB/min floor); "
                          "window = max |final-third slope| over the "
                          "control sessions",
             "formula": "o5f_stress.heap_slope_threshold"},
            {"n": 6, "check": "ten-minute GC-trough rise",
             "threshold": "<= max(2 x control-session spread, "
                          f"{S.TROUGH_RISE_FLOOR_MB} MB floor); spread = "
                          "max - min of the control sessions' rises; trough "
                          "= mean of the lowest tenth per third (O5R's "
                          "definition, unchanged)",
             "formula": "o5f_stress.trough_rise_threshold"},
            {"n": 7, "check": "no texture / geometry / video-element growth",
             "threshold": "pool LIVE counts (materials, geometries, "
                          "textures, videos, slots) and created-destroyed "
                          "zero-delta first sample to last; video elements "
                          "first == last == max; renderer texture and "
                          "geometry counts zero-delta across post-warm-up "
                          "samples at the matched desktop/high phase state; "
                          "renderer program count constant after every tier "
                          "has been visited once. created/destroyed/remaps "
                          "are monotonic by design and are reported, never "
                          "scored"},
            {"n": 8, "check": "no first-frame black card",
             "threshold": "the pre-hook first frame is captured and travels "
                          "in the review package; startup luma reported as "
                          "a diagnostic; any transition blackout is caught "
                          "deterministically by check 9's exact-zero pixel "
                          "identity"},
            {"n": 9, "check": "no quality-transition pop",
             "threshold": "on the paused, media-frozen cycle harness: a "
                          "reference still per tier on its first post-warm-"
                          "up visit, then EVERY later visit to that tier "
                          "must equal its reference with 0 differing "
                          "pixels. Cross-tier (high vs medium) difference "
                          "is reported as a diagnostic, never scored -- "
                          "5-sample and 3-sample programs legitimately "
                          "differ"},
            {"n": 10, "check": "sample count remains 5 / 5 / 3",
             "threshold": "opticalBodySamples reads "
                          f"{S.EXPECTED_SAMPLES} at every step"},
        ],
        "failureState": "O5F MATERIAL CACHE FAILED -- stop; do not modify "
                        "optics to compensate.",
    },
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, indent=1))
print(f"-> {OUT}")
print(f"   checks: {len(doc['stressGate']['checks'])}, "
      f"floors: slope {S.HEAP_SLOPE_FLOOR_MB_PER_MIN} MB/min, "
      f"trough {S.TROUGH_RISE_FLOOR_MB} MB")
