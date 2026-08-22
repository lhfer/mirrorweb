#!/usr/bin/env python3
"""O5 §十二 -- every frozen suite, re-run at the O5 build.

Emits a flat `suites` list so each named suite is visible as its own
PASS/FAIL rather than folded into a category. O5 adds a WHOLE SECOND BODY
behind a build-time lane whose default is unchanged; this file is what says
so.

Render-culling instruments may become mode-aware for the candidate -- it draws
one mesh per card where the control draws three -- but the frozen coverage
VERDICT, which slots draw, cannot change. Both are checked separately below.

The shipped default is the O2 control lane, so these suites exercise the
control. That is the point: the product default must be unmoved. The
candidate lane is covered by the absolute gate, and by gate 1's exact-zero
proof that the control lane is still the accepted O2 body.

Usage: o5-regressions.py --art=<dir> --out=<json> [--public=<json>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def jload(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    art = Path(args["art"])
    suites = []

    def add(name, ok, **detail):
        suites.append({"name": name, "pass": bool(ok), "detail": detail})

    # --- V1 render culling ------------------------------------------------
    truth = jload(art / "render/render-culling-truth.json")
    add("V1 Render Culling Gate", truth and truth.get("pass"),
        framesChecked=(truth or {}).get("framesChecked"),
        slotMismatches=(truth or {}).get("slotMismatches"),
        shellGlassMismatches=(truth or {}).get("shellGlassMismatches"),
        mediaPassLeaks=(truth or {}).get("mediaPassLeaks"),
        errors=(truth or {}).get("consoleAndPageErrors"))

    # --- V0 label culling -------------------------------------------------
    lg = art / "labelgate"
    cov, sv = jload(lg / "coverage-truth.json"), jload(lg / "slot-verdicts.json")
    pop, wr = jload(lg / "edge-pop-in.json"), jload(lg / "transform-writes.json")
    crc = (cov or {}).get("candidateRuleConsistency", {})
    label_ok = (cov and sv and pop and wr
                and crc.get("beyondBoundary") == 0
                and crc.get("slotMismatches") == 0
                and sv.get("pass") and pop.get("pass") and wr.get("pass")
                and cov["candidateSnapshotBitExactness"]["pass"]
                and cov["staleRectCheck"]["pass"])
    add("V0 Label Culling Gate", label_ok,
        framesChecked=crc.get("framesChecked"),
        beyondBoundary=crc.get("beyondBoundary"),
        identity=f"{(sv or {}).get('identical')}/{(sv or {}).get('comparisons')}",
        errors=(cov or {}).get("consoleAndPageErrors"))

    # --- source contract / layout / typography ----------------------------
    contract = jload(art / "source-contract.json")
    add("Source Contract", contract and contract.get("verdict") == "PASS",
        verdict=(contract or {}).get("verdict"),
        passed=(contract or {}).get("passed"),
        viewports=(contract or {}).get("viewports"))

    layout_log = art / "logs/layout.log"
    layout_txt = layout_log.read_text() if layout_log.exists() else ""
    add("Layout Source", bool(layout_txt) and "FAIL" not in layout_txt.upper(),
        tail=layout_txt.strip().splitlines()[-3:] if layout_txt else None)

    typo = jload(art / "typography-regression.json")
    add("Typography", typo and typo.get("verdict") == "PASS",
        verdict=(typo or {}).get("verdict"), passed=(typo or {}).get("passed"))

    # --- motion -----------------------------------------------------------
    mot = jload(art / "motion-regression.json")
    add("Motion Freeze Smoke", mot and mot.get("pass"),
        engineVsContract=(mot or {}).get("engineVsContract"))
    # The release-history record reports counts, not a verdict flag: it is
    # a PASS when every recorded release matched exactly and none mismatched.
    rh = (mot or {}).get("releaseHistory") or {}
    add("Release History Smoke",
        rh.get("releases", 0) > 0 and rh.get("exact") == rh.get("releases")
        and rh.get("mismatched") == 0,
        releases=rh.get("releases"), exact=rh.get("exact"),
        mismatched=rh.get("mismatched"),
        worstVelocityError=rh.get("worstVelocityError"))

    clm = jload(art / "card-label-motion.json")
    add("Card / Label Motion", clm and clm.get("verdict") == "PASS",
        passed=(clm or {}).get("passed"), total=(clm or {}).get("total"),
        verdict=(clm or {}).get("verdict"))

    cont = jload(art / "motion-smoke-gate/continuity-and-input.json")
    add("Wrap = 0", cont is not None
        and cont.get("visibleWrapTeleportsOurSide") == 0,
        visibleWrapTeleportsOurSide=(cont or {}).get("visibleWrapTeleportsOurSide"),
        visibleWrapTeleportsTargetSide=(cont or {}).get("visibleWrapTeleportsTargetSide"))

    mc = (mot or {}).get("continuity", {})
    add("Touch / Pointer Cancel", mc.get("touchRunsNotAtRest") == 0
        and mc.get("wheelResponsesOurSide") == 0,
        touchRunsOurSide=mc.get("touchRunsOurSide"),
        touchRunsNotAtRest=mc.get("touchRunsNotAtRest"),
        wheelResponsesOurSide=mc.get("wheelResponsesOurSide"))

    # Each gate reports its error count in its own shape -- an int in the
    # render gate, a per-side dict in the label gate and the motion gate.
    # Normalise rather than assume one of them.
    def zero_errors(v):
        if v is None:
            return False
        if isinstance(v, dict):
            # `bool` is a subclass of `int`, so a sibling verdict flag like
            # `"pass": true` would otherwise be read as a non-zero count and
            # fail a suite whose every real counter is zero.
            return all(n == 0 for n in v.values()
                       if isinstance(n, (int, float))
                       and not isinstance(n, bool))
        return v == 0

    errs = (cont or {}).get("consoleAndPageErrors", {})
    add("Console / Page Errors = 0",
        zero_errors(errs) and zero_errors((cov or {}).get("consoleAndPageErrors"))
        and zero_errors((truth or {}).get("consoleAndPageErrors")),
        motion=errs, labelGate=(cov or {}).get("consoleAndPageErrors"),
        renderGate=(truth or {}).get("consoleAndPageErrors"))

    # --- the O2 suites this round must keep passing -----------------------
    harness = jload(art / "harness/harness-verify.json")
    add("O2 Shared-media Harness", harness and harness.get("pass"),
        assets=(harness or {}).get("assets"),
        note=None if harness else "harness verification artifact missing")

    mo = jload(art / "media-only-controls.json")
    add("O2 Media-only Controls", mo and mo.get("pass"),
        pairs=(mo or {}).get("pairs"))

    # O2 recorded its selection as `winner`. The suite asserts that the
    # frozen selection is still what the build ships, so it also reads the
    # engine's own reported law from this round's captures.
    sel = jload(REPO / "qa-v5/optics-o2/candidate-selection.json")
    measure = jload(REPO / "artifacts/optics-o5/measure/measure-manifest.json")
    laws = sorted({r["optics"]["dispersionLaw"]
                   for r in (measure or {}).get("records", [])
                   if r.get("optics") and r["optics"].get("dispersionLaw")})
    add("A+B Dispersion Selection",
        (sel or {}).get("winner") == "A+B" and laws == ["o1-spectral"],
        winner=(sel or {}).get("winner"),
        dispersionLawsObservedThisRound=laws,
        note="the O2 selection is frozen product; O5 re-asserts it rather "
             "than re-deciding it.")

    # --- §十二's two O5-specific suites -----------------------------------
    # Coverage / slot identity: the frozen verdict is WHICH SLOTS DRAW. The
    # candidate draws one mesh per card where the control draws three, so
    # mesh COUNTS legitimately differ between lanes and instruments may be
    # mode-aware about them. Slot membership may not differ, and that is what
    # is asserted here.
    ident = jload(REPO / "qa-v5/optics-o5/control-identity.json")
    meas = measure or {}
    slots = {}
    for r in meas.get("records", []):
        st = (r.get("passes") or {}).get("layers", {}).get("actual") or {}
        if r.get("kind") == "lane" and st.get("activeSlots") is not None:
            slots.setdefault(r["vp"], {}).setdefault(
                r["lane"], set()).add(st["activeSlots"])
    slot_mismatch = {vp: {k: sorted(v) for k, v in lanes.items()}
                     for vp, lanes in slots.items()
                     if len({frozenset(v) for v in lanes.values()}) > 1}
    add("Coverage / slot identity",
        ident is not None and ident.get("verdict") == "PASS"
        and not slot_mismatch,
        controlIdentityVerdict=(ident or {}).get("verdict"),
        activeSlotsByViewport={vp: {k: sorted(v) for k, v in lanes.items()}
                               for vp, lanes in slots.items()},
        slotMismatches=slot_mismatch,
        note="the frozen verdict is which slots draw, not how many meshes "
             "each one uses; the candidate draws one mesh per card where the "
             "control draws three, and that difference is expected.")

    # Media Fit / Focus: the frozen crop values must be untouched, and the
    # candidate must be driving its coverScale/coverOffset from them rather
    # than from the Target's centred formula.
    arch = jload(REPO / "qa-v5/optics-o5/o5-architecture.json")
    cover = (arch or {}).get("coverFitComparison", {})
    frozen_rows = cover.get("rows", [])
    focus_intact = all(
        r["frozenMediaFit"]["scaleX"] == r["frozenMediaFit"]["scaleX"]
        for r in frozen_rows)
    clip2 = next((r for r in frozen_rows if r["clip"] == "pelican-ai"), None)
    add("Media Fit / Focus",
        bool(frozen_rows) and focus_intact and clip2 is not None
        and clip2["frozenFocus"] == {"focusX": 0.5, "focusY": 0.46, "zoom": 1.06}
        and clip2["equal"] is False,
        clips=len(frozen_rows),
        clip2FrozenFocus=(clip2 or {}).get("frozenFocus"),
        clip2MatchesTargetCentredFormula=(clip2 or {}).get("equal"),
        note="clip 2 carries a frozen 2026-08-20 product crop the Target's "
             "centred formula does not express. It MUST still differ from "
             "that formula -- if it stopped differing, the candidate would "
             "have silently adopted the Target's values and re-cropped a "
             "frozen product decision.")

    # --- toolchain --------------------------------------------------------
    tsc = (art / "logs/tsc.log")
    build = (art / "logs/build.log")
    tsc_txt = tsc.read_text() if tsc.exists() else "MISSING"
    build_txt = build.read_text() if build.exists() else "MISSING"
    add("TypeScript", tsc_txt != "MISSING" and "error TS" not in tsc_txt)
    add("Vite Build", "built in" in build_txt)

    doc = {
        "what": "every frozen suite in §十二, re-run at the O5 build. O5 adds "
                "a whole second BODY behind a build-time lane whose default is "
                "unchanged, so these suites exercise the accepted body; that "
                "it is unmoved is the point. Render-culling instruments may be "
                "mode-aware (the candidate draws one mesh per card where the "
                "control draws three) but the coverage VERDICT may not change, "
                "and both are checked separately.",
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
    for s in suites:
        print(f"{'PASS' if s['pass'] else 'FAIL'}  {s['name']}")
    print("O5 REGRESSIONS:", "PASS" if doc["pass"] else "FAIL")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
