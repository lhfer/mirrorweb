#!/usr/bin/env python3
"""O5F -- every frozen regression, re-run at the O5F build.

The aggregation is NOT re-implemented. `o5-regressions.py` is imported and
run exactly as it sits on disk, so the seventeen suites it defines are scored
by the same code that scored them in O5 and O5R, and a difference between
rounds cannot come from a rewritten aggregator.

Two of its reads are REPO-absolute and point at the sealed O5 tree. They are
remapped -- explicitly, by name, listed in the output -- so this round's
suites read this round's captures:

    qa-v5/optics-o5/control-identity.json
        -> qa-v5/optics-o5f/control-identity.json
    artifacts/optics-o5/measure/measure-manifest.json
        -> artifacts/optics-o5f/measure/measure-manifest.json

`qa-v5/optics-o5/o5-architecture.json` is deliberately NOT remapped: it is
the frozen record of the product crops, and reading it from the sealed tree
is the point. The live re-verification at the O5F head is a separate added
suite reading this round's own bodytruth captures.

Then the suites this round adds are appended.

Usage: o5f-regressions.py --art=<dir> --out=<json> [--public=<json>]
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HERE = REPO / "scripts/v5"
MD = REPO / "artifacts/optics-o5f/measure"
QA = REPO / "qa-v5/optics-o5f"

REMAP = {
    "qa-v5/optics-o5/control-identity.json":
        "qa-v5/optics-o5f/control-identity.json",
    "artifacts/optics-o5/measure/measure-manifest.json":
        "artifacts/optics-o5f/measure/measure-manifest.json",
}
NOT_REMAPPED = {
    "qa-v5/optics-o5/o5-architecture.json":
        "the frozen record of the product crops. Read from the sealed tree "
        "on purpose; re-verified live by the added Media Fit / Focus suite.",
    "qa-v5/optics-o2/candidate-selection.json":
        "the frozen O2 dispersion selection. Re-asserted, not re-decided.",
}


def jload(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def run_sealed_aggregator(art, out):
    spec = importlib.util.spec_from_file_location("o5_regressions_rerun_f",
                                                  HERE / "o5-regressions.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["o5_regressions_rerun_f"] = mod
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
    """The suites O5F adds on top of the sealed seventeen."""
    out = []

    def add(name, ok, **detail):
        out.append({"name": name, "pass": bool(ok), "detail": detail})

    ident = jload(QA / "material-cache-identity.json")
    a = (ident or {}).get("A_controlIdentity", {})
    b = (ident or {}).get("B_candidateIdentity", {})
    c = (ident or {}).get("C_programIdentity", {})
    add("Current Control Identity (O5F head)",
        ident and a.get("allExactZero") and a.get("allProbesMatch"),
        comparisons=a.get("comparisons"), allExactZero=a.get("allExactZero"),
        note="opticalBody=current at the O5F head against a 445037e "
             "worktree build. The material cache had to leave the shipped "
             "lane at exactly zero differing pixels.")
    add("Candidate Pixel Identity (§六B)",
        ident and b.get("allExactZero") and b.get("allProbesMatch"),
        comparisons=b.get("comparisons"), allExactZero=b.get("allExactZero"),
        note="target-source-unclamped at the O5F head against 445037e: the "
             "cache changed no optical output. §四 rule 10, proven rather "
             "than asserted.")
    add("Program Identity (§六C)",
        ident and c.get("allMatch"),
        allMatch=c.get("allMatch"),
        note="generated WGSL sha256, vertex and fragment, at both sample "
             "tiers and back: the cached programs are the O5R programs.")

    stress = jload(QA / "material-cache-stress.json")
    add("Material Cache Stress Gate (§七)",
        stress and stress.get("verdict") == "PASS",
        passed=(stress or {}).get("passed"), total=(stress or {}).get("total"),
        note="the pre-registered Phase A gate: 1,200 quality changes with "
             "per-tier reference-still identity, three candidate and three "
             "control 15-minute sessions, sealed thresholds.")

    seal = jload(QA / "sealed-lane-identity.json")
    add("Sealed Lane Identity (O5F head, full measure suite)",
        seal and seal.get("exactZero"),
        comparisons=(seal or {}).get("comparisons"),
        differingPixels=(seal or {}).get("totalDifferingPixels"),
        byLane=(seal or {}).get("byLane"),
        note="control, o5-clamped and o5r-unclamped re-captured at the O5F "
             "head across the whole measure suite and compared against the "
             "sealed O5R tree, exact zero.")

    orig = jload(QA / "original-o5-gate-regression.json")
    add("Original O5 Gate Re-run",
        orig and orig.get("identical"),
        sealed=(orig or {}).get("sealedVerdict"),
        rerun=(orig or {}).get("rerunVerdict"),
        note="the sealed gate, unedited, still produces its own 8/14. Not "
             "restated as an O5F result.")

    o5rg = jload(QA / "o5r-gate-regression.json")
    add("O5R Corrected Gate Re-run",
        o5rg and o5rg.get("identical"),
        sealed=(o5rg or {}).get("sealedVerdict"),
        rerun=(o5rg or {}).get("rerunVerdict"),
        note="the sealed corrected gate, unedited, still produces its own "
             "7/14. Not restated as an O5F result.")

    # Quality 5/5/3 from this round's own stress captures.
    cyc = jload(REPO / "artifacts/optics-o5f/quality-cycle/quality-cycle.json")
    sess = jload(REPO / "artifacts/optics-o5f/stress/sessions-manifest.json")
    want = {"high": 5, "medium": 5, "low": 3}
    seen = {}
    for s in (cyc or {}).get("steps", []):
        seen.setdefault(s["level"], set()).add(s.get("samples"))
    for r in (sess or {}).get("records", []):
        if r.get("lane") != "candidate":
            continue
        for s in r.get("qualitySteps", []):
            seen.setdefault(s["level"], set()).add(s.get("samples"))
    quality_ok = bool(seen) and all(seen.get(k) == {v}
                                    for k, v in want.items())
    add("Candidate Quality 5 / 5 / 3", quality_ok,
        observed={k: sorted(v) for k, v in sorted(seen.items())},
        required=want,
        note="now read off the CACHED sets: the sample count follows the "
             "active set, and the original UUIDs return at every revisit.")

    # Media fit / focus, re-verified LIVE at the O5F head.
    arch = jload(REPO / "qa-v5/optics-o5/o5-architecture.json")
    frozen_rows = ((arch or {}).get("coverFitComparison") or {}).get("rows", [])
    clip2 = next((r for r in frozen_rows if r["clip"] == "pelican-ai"), None)
    truths, cover_rows = [], []
    for vp in ("1440x900", "390x844", "844x390", "700x700"):
        t = jload(MD / f"o5r-unclamped-bodytruth-{vp}.json")
        if t:
            truths.append((vp, t))
    for vp, t in truths:
        for card in t.get("cards", []):
            cover_rows.append({"vp": vp, "slotIndex": card.get("slotIndex"),
                               "clipIndex": card.get("clipIndex"),
                               "coverScale": card.get("coverScale"),
                               "coverOffset": card.get("coverOffset")})

    def is_centred(card):
        s, o = card.get("coverScale"), card.get("coverOffset")
        if not s or not o:
            return None
        return (abs(o[0] - (1 - s[0]) / 2) < 1e-4
                and abs(o[1] - (1 - s[1]) / 2) < 1e-4)

    crop_cards = [card for card in cover_rows if card["clipIndex"] == 2]
    crop_ok = bool(crop_cards) and all(is_centred(card) is False
                                       for card in crop_cards)
    add("Media Fit / Focus (re-verified at the O5F head)",
        bool(clip2) and crop_ok
        and clip2["frozenFocus"] == {"focusX": 0.5, "focusY": 0.46,
                                     "zoom": 1.06},
        frozenFocus=(clip2 or {}).get("frozenFocus"),
        croppedCardsChecked=len(crop_cards),
        croppedCardsUsingCentredCover=sum(
            1 for card in crop_cards if is_centred(card) is True),
        viewports=[vp for vp, _ in truths],
        note="clip 2 carries a frozen product crop the Target's centred "
             "cover formula does not express. The cached sets read their "
             "cover transforms from the frozen media fit, so those cards "
             "must still NOT be centred -- across every cached set, since "
             "applyMediaFits now writes into all of them.")

    truth = jload(REPO / "artifacts/optics-o5f/regressions/render/"
                         "render-culling-truth.json")
    add("V1 Render Coverage Verdict unchanged",
        truth and truth.get("pass") and truth.get("slotMismatches") == 0,
        framesChecked=(truth or {}).get("framesChecked"),
        slotMismatches=(truth or {}).get("slotMismatches"),
        note="which slots draw is the frozen verdict; the cache rebinding "
             "materials may not move it.")
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
        "what": "every frozen regression, re-run at the O5F build. The "
                "seventeen sealed suites are scored by o5-regressions.py "
                "imported unedited; the suites this round adds are appended "
                "after them.",
        "sealedAggregator": {
            "script": "scripts/v5/o5-regressions.py, imported and executed "
                      "as it sits on disk",
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
    print(f"\nO5F REGRESSIONS: {doc['suitesPassed']}/{doc['suiteCount']} "
          f"{'PASS' if doc['pass'] else 'FAIL'}")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
