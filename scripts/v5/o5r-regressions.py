#!/usr/bin/env python3
"""§十四 -- every frozen regression, re-run at the O5R build.

The aggregation is NOT re-implemented. `o5-regressions.py` is imported and run
exactly as it sits on disk, so the seventeen suites it defines are scored by
the same code that scored them in O5 and a difference between the rounds cannot
come from a rewritten aggregator.

Three of its reads are REPO-absolute rather than under `--art`, and those point
at the sealed O5 tree. They are remapped -- explicitly, by name, listed in the
output -- so this round's suites read this round's captures:

    qa-v5/optics-o5/control-identity.json
        -> qa-v5/optics-o5r/control-identity.json
    artifacts/optics-o5/measure/measure-manifest.json
        -> artifacts/optics-o5r/measure/measure-manifest.json

`qa-v5/optics-o5/o5-architecture.json` is deliberately NOT remapped: it is the
frozen record of the product crops, and reading it from the sealed tree is the
point. The live re-verification at the O5R head is a separate added suite that
reads the card body truth out of this round's own captures.

Then the suites §十四 adds for this round are appended.

Usage: o5r-regressions.py --art=<dir> --out=<json> [--public=<json>]
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HERE = REPO / "scripts/v5"
MD = REPO / "artifacts/optics-o5r/measure"
QA = REPO / "qa-v5/optics-o5r"

REMAP = {
    "qa-v5/optics-o5/control-identity.json":
        "qa-v5/optics-o5r/control-identity.json",
    "artifacts/optics-o5/measure/measure-manifest.json":
        "artifacts/optics-o5r/measure/measure-manifest.json",
}
NOT_REMAPPED = {
    "qa-v5/optics-o5/o5-architecture.json":
        "the frozen record of the product crops. Read from the sealed tree on "
        "purpose; re-verified live by the added Media Fit / Focus suite.",
    "qa-v5/optics-o2/candidate-selection.json":
        "the frozen O2 dispersion selection. Re-asserted, not re-decided.",
}


def jload(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def run_sealed_aggregator(art, out):
    spec = importlib.util.spec_from_file_location("o5_regressions_rerun",
                                                  HERE / "o5-regressions.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["o5_regressions_rerun"] = mod
    spec.loader.exec_module(mod)

    original = mod.jload
    applied = []

    def remapping_jload(p):
        rel = None
        try:
            rel = str(Path(p).resolve().relative_to(REPO))
        except ValueError:
            pass
        if rel in REMAP:
            applied.append({"from": rel, "to": REMAP[rel]})
            return original(REPO / REMAP[rel])
        return original(p)

    mod.jload = remapping_jload
    argv = sys.argv
    sys.argv = ["o5-regressions.py", f"--art={art}", f"--out={out}"]
    try:
        rc = mod.main()
    finally:
        sys.argv = argv
        mod.jload = original
    return rc, applied


def added_suites():
    """The suites §十四 adds on top of the sealed seventeen."""
    out = []

    def add(name, ok, **detail):
        out.append({"name": name, "pass": bool(ok), "detail": detail})

    ident = jload(QA / "control-identity.json")
    add("Current Control Identity (O5R head)",
        ident and ident.get("verdict") == "PASS",
        verdict=(ident or {}).get("verdict"),
        comparisons=(ident or {}).get("comparisons"),
        differingPixels=(ident or {}).get("totalDifferingPixels"),
        note="opticalBody=current at the O5R head against a worktree build of "
             "the accepted body. The one authorised code change had to leave "
             "the shipped lane at exactly zero differing pixels.")

    seal = jload(QA / "sealed-lane-identity.json")
    add("Sealed O5 Lane Byte Identity",
        seal and seal.get("exactZero"),
        comparisons=(seal or {}).get("comparisons"),
        differingPixels=(seal or {}).get("totalDifferingPixels"),
        note="opticalBody=target-source still renders the frames the sealed O5 "
             "gate scored. Guaranteed structurally by a build-time flag that "
             "keeps the measurement expressions out of the Beauty program, "
             "rather than by trusting dead-code elimination.")

    orig = jload(QA / "original-o5-gate-regression.json")
    add("Original O5 Gate Re-run (§十三A)",
        orig and orig.get("identical"),
        sealed=(orig or {}).get("sealedVerdict"),
        rerun=(orig or {}).get("rerunVerdict"),
        identical=(orig or {}).get("identical"),
        note="the sealed gate, unedited, still produces its own verdict. Not "
             "restated as an O5R result.")

    # Adaptive quality: the sample counts are BUILD-TIME literals, so a quality
    # step rebuilds the material. 5 / 5 / 3 is the accepted policy and §十四
    # freezes it.
    perf = jload(REPO / "artifacts/optics-o5r/performance/performance-manifest.json")
    steps = [s for r in (perf or {}).get("records", [])
             if r.get("lane") == "candidate" for s in r.get("qualitySteps", [])]
    want = {"high": 5, "medium": 5, "low": 3}
    seen = {}
    for s in steps:
        seen.setdefault(s["level"], set()).add(s.get("samples"))
    quality_ok = bool(steps) and all(
        seen.get(k) == {v} for k, v in want.items())
    add("Candidate Quality 5 / 5 / 3", quality_ok,
        observed={k: sorted(v) for k, v in sorted(seen.items())},
        required=want, stepsObserved=len(steps),
        note=None if steps else "no quality steps recorded -- the §十二 "
                                "performance sessions have not run")

    # Media fit / focus, re-verified LIVE at the O5R head rather than from the
    # O5 record: the candidate's own cover transform, read out of the card body
    # truth this round captured.
    arch = jload(REPO / "qa-v5/optics-o5/o5-architecture.json")
    frozen_rows = ((arch or {}).get("coverFitComparison") or {}).get("rows", [])
    clip2 = next((r for r in frozen_rows if r["clip"] == "pelican-ai"), None)
    truths, cover_rows = [], []
    for vp in ("1440x900", "390x844", "844x390", "700x700"):
        t = jload(MD / f"o5r-unclamped-bodytruth-{vp}.json")
        if t:
            truths.append((vp, t))
    for vp, t in truths:
        for c in t.get("cards", []):
            cover_rows.append({"vp": vp, "slotIndex": c.get("slotIndex"),
                               "clipIndex": c.get("clipIndex"),
                               "coverScale": c.get("coverScale"),
                               "coverOffset": c.get("coverOffset")})
    # Every card that carries the frozen product crop must show a cover
    # transform that is NOT the Target's centred one. Centred cover puts the
    # offset at (1 - scale) / 2 on both axes; the 2026-08-20 crop does not.
    def is_centred(c):
        s, o = c.get("coverScale"), c.get("coverOffset")
        if not s or not o:
            return None
        return (abs(o[0] - (1 - s[0]) / 2) < 1e-4
                and abs(o[1] - (1 - s[1]) / 2) < 1e-4)
    crop_cards = [c for c in cover_rows if c["clipIndex"] == 2]
    crop_ok = bool(crop_cards) and all(is_centred(c) is False for c in crop_cards)
    add("Media Fit / Focus (re-verified at the O5R head)",
        bool(clip2) and crop_ok
        and clip2["frozenFocus"] == {"focusX": 0.5, "focusY": 0.46,
                                     "zoom": 1.06},
        frozenFocus=(clip2 or {}).get("frozenFocus"),
        croppedCardsChecked=len(crop_cards),
        croppedCardsUsingCentredCover=sum(
            1 for c in crop_cards if is_centred(c) is True),
        viewports=[vp for vp, _ in truths],
        note="clip 2 carries a frozen product crop the Target's centred cover "
             "formula does not express. The candidate reads its cover "
             "transform from the frozen media fit, so those cards must still "
             "NOT be centred -- if they became centred, the body would have "
             "silently re-cropped a frozen product decision.")

    # The frozen coverage verdict. §十四 is explicit that the rendering
    # architecture may differ but the verdict may not.
    truth = jload(REPO / "artifacts/optics-o5r/regressions/render/"
                         "render-culling-truth.json")
    add("V1 Render Coverage Verdict unchanged",
        truth and truth.get("pass") and truth.get("slotMismatches") == 0,
        framesChecked=(truth or {}).get("framesChecked"),
        slotMismatches=(truth or {}).get("slotMismatches"),
        note="which slots draw is the frozen verdict. The target-source body "
             "draws one mesh per card where the accepted body draws three; "
             "that is an architecture difference and it may not move the "
             "verdict.")
    return out


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    art = Path(args["art"])
    inner = art / "regressions-sealed-aggregator.json"

    rc, applied = run_sealed_aggregator(art, inner)
    sealed = jload(inner) or {"suites": []}
    suites = list(sealed.get("suites", [])) + added_suites()

    doc = {
        "what": "§十四 -- every frozen regression, re-run at the O5R build. "
                "The seventeen sealed suites are scored by o5-regressions.py "
                "imported unedited; the suites this round adds are appended "
                "after them.",
        "sealedAggregator": {
            "script": "scripts/v5/o5-regressions.py, imported and executed as "
                      "it sits on disk",
            "exitCode": rc,
            "pathsRemapped": applied,
            "pathsDeliberatelyNotRemapped": NOT_REMAPPED,
            "suiteCount": len(sealed.get("suites", [])),
        },
        "suiteCount": len(suites),
        "suitesPassed": sum(1 for s in suites if s["pass"]),
        "suitesFailed": [s["name"] for s in suites if not s["pass"]],
        "pass": all(s["pass"] for s in suites),
        "suites": suites,
    }
    Path(args["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["out"]).write_text(json.dumps(doc, indent=1) + "\n")
    if "public" in args:
        Path(args["public"]).parent.mkdir(parents=True, exist_ok=True)
        Path(args["public"]).write_text(json.dumps(doc, indent=1) + "\n")
    print()
    for s in suites:
        print(f"{'PASS' if s['pass'] else 'FAIL'}  {s['name']}")
    print(f"\nO5R REGRESSIONS: {doc['suitesPassed']}/{doc['suiteCount']} "
          f"{'PASS' if doc['pass'] else 'FAIL'}")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
