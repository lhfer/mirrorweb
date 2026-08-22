#!/usr/bin/env python3
"""O5F §十B -- score the Target mobile sample tier.

Three facts, none inferred from viewport dimensions:

  1. THE PREDICATE, from the bundle. The archived card bundle carries the
     device-tier expression at a real byte offset; it is located here by
     regex over raw bytes and quoted. The tier is (pointer: coarse) OR
     hardwareConcurrency <= 6 OR deviceMemory <= 4 -- a device predicate,
     with no viewport term at all.
  2. THE LIVE RUNTIME. o5f-target-tier.mjs loaded the live page in the exact
     capture contexts and hooked shader-module creation; the card body
     program's refract-call count IS its sample count (the sealed compiled
     audit established that equivalence: \\brefract\\s*\\( appears exactly
     `samples` times). The predicate inputs were read live in each context.
  3. THE BUNDLE IDENTITY. Every live response containing
     "maxDispersionSamples" was hashed; it must equal the archived bundle,
     or fact 1 describes a different program than fact 2 ran.

Output: qa-v5/optics-o5f/target-mobile-tier.json
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
RAW = REPO / "artifacts/optics-o5f/target-tier/target-tier-raw.json"
BUNDLE = REPO / "artifacts/f27/bundles/03lo820gl57km.js"
OUT = REPO / "qa-v5/optics-o5f/target-mobile-tier.json"

OUR_SAMPLES_AT_CAPTURE = {
    # V5_BODY_SAMPLES[quality] at the captures' quality (adaptive off, high).
    "1440x900": 5, "390x844": 5, "844x390": 5, "700x700": 5,
}


def main() -> int:
    raw = json.loads(RAW.read_text())
    data = BUNDLE.read_bytes()
    bundle_sha = hashlib.sha256(data).hexdigest()

    # --- 1: the predicate, from raw bundle bytes ---------------------------
    pred = re.search(
        rb'matchMedia\("\(pointer: coarse\)"\)\.matches[^;]{0,400}?'
        rb'maxDispersionSamples:"low"===\w+\?3:1/0', data)
    if not pred:
        print("FATAL: predicate site not found in archived bundle")
        return 2
    excerpt = data[pred.start():pred.end()].decode("utf-8", errors="replace")
    tier_terms = {
        "pointerCoarse": 'window.matchMedia("(pointer: coarse)").matches',
        "cores": "navigator.hardwareConcurrency ?? 8, low when <= 6",
        "memory": "navigator.deviceMemory ?? 8, low when <= 4",
    }

    def predicted_tier(env):
        if env is None:
            return None
        coarse = bool(env.get("pointerCoarse"))
        cores = env.get("hardwareConcurrency") or 8
        mem = env.get("deviceMemory") or 8
        return "low" if (coarse or cores <= 6 or mem <= 4) else "high"

    # --- 2 + 3: per-context live readings ----------------------------------
    rows = []
    live_matches_archive = True
    for rec in raw["records"]:
        vp = rec["vp"]
        env = (rec.get("probe") or {}).get("envAtLoad")
        tier = predicted_tier(env)
        expected = {"low": 3, "high": 5}.get(tier)
        observed = None
        refract_calls = None
        prog = rec.get("bodyProgram")
        if prog:
            text = (RAW.parent / prog["file"]).read_text()
            refract_calls = len(re.findall(r"\brefract\s*\(", text))
            observed = refract_calls
        for b in rec.get("bundlesWithPredicate", []):
            if b["sha256"] != bundle_sha:
                live_matches_archive = False
        ours = OUR_SAMPLES_AT_CAPTURE.get(vp)
        rows.append({
            "vp": vp,
            "mobileEmulation": rec.get("mobileEmulation"),
            "loaded": rec.get("loaded"),
            "predicateInputs": env,
            "predictedTier": tier,
            "predictedSamples": expected,
            "observedRefractCalls": refract_calls,
            "observedSamples": observed,
            "agreement": (observed == expected
                          if observed is not None and expected is not None
                          else None),
            "ourCandidateSamples": ours,
            "mismatchWithOurs": (observed is not None and ours is not None
                                 and observed != ours),
            "bundles": rec.get("bundlesWithPredicate"),
            "bodyProgram": prog,
            "errorCount": rec.get("errorCount"),
        })

    p0 = next((r for r in rows if r["vp"] == "390x844"), None)
    landscape = next((r for r in rows if r["vp"] == "844x390"), None)

    # The counting-convention CONTROL. "refract-call count IS the sample
    # count" was established on OUR three build's compiled programs; before a
    # mobile-context reading may mean anything, the same equivalence has to be
    # shown to hold on the Target's compiled output. The desktop 1440x900
    # context is the known-tier case: its predicate inputs predict "high",
    # so its program must count exactly 5. If it does not, the convention
    # does not transfer and EVERY reading here is INSTRUMENT_UNREADABLE --
    # never a divergence, never a match.
    control = next((r for r in rows if r["vp"] == "1440x900"), None)
    convention_ok = (control is not None
                     and control["predictedTier"] == "high"
                     and control["observedRefractCalls"] == 5)
    counting_control = {
        "vp": "1440x900",
        "why": "desktop context with a known predicted tier (high -> 5); "
               "observing exactly 5 refract calls in the Target's live "
               "program validates the count-equals-samples convention on "
               "the Target's own compiled output, not just ours.",
        "predictedTier": None if control is None else control["predictedTier"],
        "observedRefractCalls": None if control is None
        else control["observedRefractCalls"],
        "validated": convention_ok,
    }
    readable = convention_ok and all(
        r["loaded"] and r["observedSamples"] is not None for r in rows)

    doc = {
        "what": "§十B -- the Target's mobile sample tier, proven from the "
                "live runtime and the bundle, never inferred from viewport "
                "dimensions.",
        "bundlePredicate": {
            "file": "artifacts/f27/bundles/03lo820gl57km.js",
            "byteOffset": pred.start(),
            "excerpt": excerpt,
            "terms": tier_terms,
            "reading": "low = (pointer: coarse) OR cores <= 6 OR "
                       "deviceMemory <= 4; maxDispersionSamples = low ? 3 : "
                       "Infinity; samples = min(5, maxDispersionSamples). "
                       "No viewport term exists in the predicate.",
            "archivedBundleSha256": bundle_sha,
        },
        "liveBundleMatchesArchive": live_matches_archive,
        "captureContextRule": raw["contextRule"],
        "countingConventionControl": counting_control,
        "rows": rows,
        "conclusion": {
            "p0": None if p0 is None else {
                "vp": "390x844",
                "targetSamplesObserved": p0["observedSamples"],
                "ourCandidateSamples": p0["ourCandidateSamples"],
                "sampleTierMismatch": p0["mismatchWithOurs"],
            },
            "landscape": None if landscape is None else {
                "vp": "844x390",
                "targetSamplesObserved": landscape["observedSamples"],
                "ourCandidateSamples": landscape["ourCandidateSamples"],
                "sampleTierMismatch": landscape["mismatchWithOurs"],
            },
        },
        "status": "READABLE" if readable else "INSTRUMENT_UNREADABLE",
        "unreadableNote": None if readable else
            ("the desktop control did not validate the refract-count "
             "convention on the Target's own program; no reading here can "
             "prove a tier." if not convention_ok else
             "a context that did not load or yielded no refract-bearing "
             "program cannot prove a tier; it is not converted into either "
             "verdict."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    for r in rows:
        print(f"{r['vp']:>9}: coarse={((r['predicateInputs'] or {}).get('pointerCoarse'))} "
              f"predicted={r['predictedSamples']} observed={r['observedSamples']} "
              f"ours={r['ourCandidateSamples']} mismatch={r['mismatchWithOurs']}")
    print(f"counting convention (1440x900 control): "
          f"{'validated' if convention_ok else 'NOT validated'}")
    print(f"live bundle == archive: {live_matches_archive}")
    print(f"-> {OUT}  [{doc['status']}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
