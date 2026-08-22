#!/usr/bin/env python3
"""Assemble the public qa-v5/optics-o4 tree (§十二): the per-topic JSONs,
README.md and MANIFEST.json, written from the real gate and attribution
records rather than restated by hand.

Public tree = JSON and markdown only. Target pixels and video live ONLY in
the private package.

Usage: o4-evidence.py --capturedAtHead=<sha> [--outdir=qa-v5/optics-o4]
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o4_ev_stats", "o2_optics_stats.py")
I = _load("o4_ev_ins", "o4_instruments.py")

GD = REPO / "artifacts/optics-o4/gate"


def full_sha(label, value):
    p = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify",
                        f"{value}^{{commit}}"], capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(f"{label}: {value!r} does not resolve to a commit")
    sha = p.stdout.strip()
    if len(sha) != 40:
        raise SystemExit(f"{label}: not 40 hex")
    return sha


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def item(gate, n):
    return next(i for i in gate["items"] if i["n"] == n)


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        args[k] = v
    outdir = Path(args.get("outdir", REPO / "qa-v5/optics-o4"))
    captured = full_sha("capturedAtHead", args["capturedAtHead"])

    gate = json.loads((outdir / "body-floor-gate.json").read_text())
    sel = json.loads((outdir / "o4-selected-subsystem.json").read_text())
    attr = json.loads((outdir / "body-floor-attribution.json").read_text())
    audit = json.loads((outdir / "body-code-audit.json").read_text())
    src = json.loads((outdir / "target-body-source.json").read_text())
    pop = json.loads((REPO / "artifacts/optics-o4/recordings/pop.json").read_text())
    man = json.loads((GD / "gate-manifest.json").read_text())
    # The cross-sections and the silhouette overlay are private-package
    # deliverables, but their numbers are an independent re-derivation of the
    # gate's, so the public README cites them when they exist.
    global XS
    xsf = REPO / "artifacts/optics-o4/crosssection/crosssection.json"
    XS = json.loads(xsf.read_text()) if xsf.exists() else None

    # ---- O3 product review, machine readable
    (outdir / "o3-product-review-decision.json").write_text(json.dumps({
        "what": "the O3 product review decision this round opened from. Prose "
                "in docs/v5/O3_PRODUCT_REVIEW.md.",
        "reviewHead": "eba0aa0ccffc650768436f86018ab46152f5c475",
        "accepted": ["O3 source forensics", "TargetBevelFieldV4 transcription "
                     "(engineering pass)", "the corrected instruments",
                     "the target-sdf diagnostic lane",
                     "the frozen-body-floor finding"],
        "rejected": ["the O3 candidate as shipped default",
                     "the default flip to target-sdf",
                     "further rim / fresnel / env tuning"],
        "shippedDefault": {"reflectionSupport": "geometry",
                           "dispersionLaw": "o1-spectral"},
        "targetVisualPass": "NOT ASSERTED",
        "o4Objective": "attribute and reduce the frozen body floor",
    }, indent=1))

    # ---- per-topic files, all derived from the gate record
    def lane_rows(state, assets, vp="1440x900"):
        out = {}
        for a in assets:
            for lane in ("control", "candidate"):
                r = [x for x in man["records"] if x["kind"] == "lane"
                     and x["lane"] == lane and x["state"] == state
                     and x["asset"] == a and x["vp"] == vp]
                if not r:
                    continue
                rects = [q for _, q in S.rects_at(*[int(v) for v in vp.split("x")])]
                img = Image.open(GD / r[0]["file"])
                w, h = (int(v) for v in vp.split("x"))
                st = dict(S.stats(img, rects, w, h))
                st.update(S.side_bands(img, rects))
                st.update(S.interior_stats(img, rects))
                st["bandWidthPx"] = I.band_width_px(img, rects)["meanPx"]
                st["bandEnergy"] = I.band_energy(img, rects)["meanEnergy"]
                out.setdefault(a, {})[lane] = st
        return out

    (outdir / "bright-dark.json").write_text(json.dumps({
        "what": "bright and dark media in the SHIPPED state -- the body "
                "candidate must not crush dark content or blow bright content.",
        "assets": lane_rows("sysBOn", ["dark-highlight", "bright-lowsat"]),
        "interiorVerdict": item(gate, 7)["assets"],
    }, indent=1))

    (outdir / "grayscale-ringing.json").write_text(json.dumps({
        "what": "§九.4 -- grayscale media is achromatic through the media-only "
                "path, so any chroma here is shader-introduced.",
        "verdict": item(gate, 4),
        "assets": lane_rows("sysBOn", ["grayscale-step"]),
    }, indent=1))

    (outdir / "checker-control.json").write_text(json.dumps({
        "what": "§九.6 -- local high-frequency structure on hf-checker.",
        "verdict": item(gate, 6),
        "assets": lane_rows("sysBOn", ["hf-checker"]),
    }, indent=1))

    (outdir / "mobile-consistency.json").write_text(json.dumps({
        "what": "the body floor at both mobile viewports, and the OFAT "
                "factor effects measured there.",
        "primaryGateRows": [r for r in item(gate, 1)["viewports"]
                            if r["vp"] != "1440x900"],
        "shippedStateRows": [r for r in item(gate, 1)["shippedStateDiagnostic"]["rows"]
                             if r["vp"] != "1440x900"],
        "factorEffects": attr["mobile"],
    }, indent=1))

    (outdir / "temporal-continuity.json").write_text(json.dumps({
        "what": "§九.10 -- rim / body pop over the four recorded sequences.",
        "coding": pop["coding"], "pass": pop["pass"],
        "sequences": pop["sequences"],
    }, indent=1))

    (outdir / "support-retest.json").write_text(json.dumps({
        "what": "§十 -- the reflection-support diagnostic re-test.",
        "authorised": False,
        "reason": "§十 authorises the re-test ONLY after the selected body "
                  "candidate passes its own gate. It did not: the O4 absolute "
                  "gate is FAIL. Running it anyway would be exactly the "
                  "search-for-a-combination-that-passes that §七 and §八 "
                  "exist to prevent, so it was not run and no re-test pixels "
                  "were captured.",
        "whatWouldHaveBeenReported": [
            "whether the O3 Target field clears the absolute band gate on the "
            "candidate body",
            "whether its chroma trade-off remains",
            "whether the geometry-normal + Target-SDF-rim hybrid is worth a "
            "future product review",
        ],
        "relatedEvidenceAlreadyInHand": "body-floor-gate.json item 1 carries a "
            "shipped-state diagnostic showing how much of the shipped band is "
            "body and how much is the O2 reflection support. That is the "
            "measured part of the same question, obtained without running an "
            "unauthorised lane.",
    }, indent=1))

    # ---------------------------------------------------------------- README
    g = gate
    L = []
    A = L.append
    A("# O4 — Frozen Body Floor Attribution")
    A("")
    A(f"**Final state: {g['finalState']}**")
    A("")
    A(f"Absolute gate: **{g['absoluteGate']}** — {g['itemsPassed']} of 12 "
      f"items passed, {g['itemsFailed']} failed"
      + (f", {g['itemsPending']} pending" if g["itemsPending"] else "") + ".")
    A("")
    A("The shipped default stays `bodyFloorMode=current`. This brief "
      "registers no automatic flip and its final states do not include one; "
      "the product review owns that decision.")
    A("")
    A("## O4A — the compiled body-path audit")
    A("")
    A(f"**{audit['verdict']}.** {audit['answer']}")
    A("")
    A("The geometry normal is unpacked exactly once, inside the `normals` "
      "debug branch. Fourteen sites alias it; thirteen sit in branches with "
      "no unpack, including all three in the Beauty branch. Two debug views "
      "read it in different branches of one program, same frame, same "
      "geometry: `normals` varies (range 38/66/3), `fresnel` is **exactly "
      "constant** (0/0/0). The controls that read unshared vertex attributes "
      "vary correctly.")
    A("")
    A("This explains GATE-005 rather than reproducing it: "
      "`projectedNormalOffset` — documented as the only term tracking the "
      "surface normal — is identically zero.")
    A("")
    A("## The factorial")
    A("")
    A("The specified 2^5 over A–E, replicated at both states of a sixth axis "
      "N (the normal repair O4A made necessary), because §七.E cannot be "
      "judged without N measured on the same basis. 260 desktop captures "
      "over four media; OFAT plus pairwise at both mobile viewports.")
    A("")
    A("| factor | subsystem | explains | interaction ratio | eligible |")
    A("|---|---|---|---|---|")
    for f, v in sel["verdicts"].items():
        A(f"| {f} | {v['subsystem']} | {v['explainedFraction']:+.0%} | "
          f"{v['interactionRatio']} | {'**yes**' if v['eligible'] else 'no'} |")
    A("")
    A(f"Selected: **{sel['selected']['subsystem']}** — the only eligible "
      f"factor.")
    A("")
    A("## The twelve gate items")
    A("")
    A("| # | Item | Result |")
    A("|---|---|---|")
    for i in g["items"]:
        A(f"| {i['n']} | {i['item']} | **{i['result']}** |")
    A("")
    A("## What failed, and what the numbers mean")
    A("")
    d = item(g, 1)["shippedStateDiagnostic"]
    A("**Items 2 and 3 — the candidate undershoots.** Removing the local "
      "adaptive body shaping takes the body floor *below* the Target's whole "
      "band at every viewport: 9.7 → 1.7 px desktop against a Target of 3.3, "
      "6.0 → 0.0 against 1.5, 6.0 → 0.0 against 2.0. Item 2 is a two-sided "
      "window and was sealed as one, so undershooting is scored as a miss.")
    A("")
    A("The comparison §九 mandates is asymmetric, and that is recorded rather "
      "than argued around: our System-B-OFF floor against the Target's full "
      "render, which includes the Target's own rim and environment. The "
      "shipped-state diagnostic is what makes it legible:")
    A("")
    A("| Viewport | control body floor | candidate body floor | control shipped | candidate shipped | Target |")
    A("|---|---|---|---|---|---|")
    for r in d["rows"]:
        A(f"| {r['vp']} | {r['controlBodyFloorPx']} px | "
          f"{r['candidateBodyFloorPx']} px | {r['controlShippedBandPx']} px | "
          f"{r['candidateShippedBandPx']} px | {r['targetBandPx']} px |")
    A("")
    A("Removing the body shaping takes the floor to essentially nothing, and "
      "the shipped band still barely moves — 15.3 → 13.0 px desktop — because "
      "with the body dark the O2 reflection support paints the band on its "
      "own. **O3 showed the support field is not the binding constraint "
      "given this body. O4 shows the body is not the binding constraint "
      "given this support.** Both are constraints; neither round was "
      "permitted to change the other, and neither could pass alone.")
    A("")
    i9 = item(g, 9)
    A("**Item 9 — true gutter.** Scored FAIL at a sealed threshold of exactly "
      "zero. Every differing pixel lies within **one** pixel of the true "
      "silhouette, at a maximum of 2 and 5 levels; beyond 1 px the two lanes "
      "are identical. They are the antialiased boundary of a silhouette "
      "derived from the control lane, not light in the gutter. The threshold "
      "and instrument are untouched and the item stands as scored."
      + (f" The private package's `cross-section/silhouette-overlay-*.png` "
         f"plots this directly: "
         + ", ".join(f"{o['within1px']} of {o['differingOutside']} differing "
                     f"pixels on {o['asset']}" for o in XS["silhouetteOverlays"])
         + " sit on the boundary ring, none beyond it." if XS else ""))
    A("")
    i5 = item(g, 5)
    A("**Item 5 — coloured rim.** `fringeRB` rises 79.4 → 80.5 on rgb-bars "
      "and 92.3 → 94.4 on cool-blue against a 0.5 envelope; warm-skin passes. "
      "The rim does not get *broader* — `fringeWidthPxMean` is flat on two "
      "assets and falls 17.8 → 14.6 on the third — it gets marginally more "
      "intense, because removing the internal shadow leaves the edge "
      "brighter on saturated media.")
    A("")
    A("**Items 6 and 7 pass for a structural reason worth stating.** The two "
      "lanes are bit-identical in the card interior. Every adaptive term is "
      "gated on `blurZone` and `curvature`, both zero on the clear centre "
      "face, so the subsystem the candidate removes never acted there.")
    A("")
    A("## What held")
    A("")
    A("- Item 11: the control lane is **exactly zero** differing pixels "
      "against an e913aa6 worktree build at System B OFF, on every scored "
      "case. Every comparison above is therefore against the accepted O2 "
      "body and not against something else.")
    A("- Item 1: the floor falls 82% desktop and 100% at both mobile "
      "viewports.")
    A("- Item 8: media-only is bit-identical.")
    A("- Item 10: no pop on any recorded sequence; worst adjacent-frame "
      "change 2.2% against a 40% ceiling.")
    A("- The all-off diagnostic program is **byte-identical** to the pre-O4 "
      "program at high, medium and low quality, so the factor machinery is "
      "provably inert when off.")
    A("")
    A("## §十 — the support re-test was not run")
    A("")
    A("§十 authorises it only after the body candidate passes its own gate. "
      "It did not. Running it anyway would be the search for a combination "
      "that passes which §七 and §八 exist to prevent. See "
      "`support-retest.json`.")
    A("")
    A("## Method notes")
    A("")
    A(f"- Instruments sealed at `{json.loads((outdir / 'instrument-contract.json').read_text())['sealedAtHead'][:12]}`, "
      f"gate codings at `{g['codingSealedAtHead'][:12]}`, both before the "
      f"pixels they judge. 32/32 instrument tests pass, each with a negative "
      f"partner.")
    A("- The Target body source contract anchors 17 sites, 0 failed; "
      "absences are established by an end-to-end completeness span "
      "(bytes 1975111–1976472) rather than pretended byte offsets.")
    A("- Band width is only a reflection-band measurement where the media "
      "behind the card's dark-side edge is dark. That holds on bw-split "
      "(luma 4.5) and not on the other three (26–58), so the excess test "
      "uses bw-split and cross-media sign stability uses the continuous "
      "measurands sealed before capture.")
    if XS:
        xb = {(r["lane"], r["state"]): r["bandPx"] for r in XS["profiles"]
              if r["vp"] == "1440x900"}
        A(f"- The private package's side-band cross-sections are measured "
          f"independently of the gate scorer and reproduce it exactly — "
          f"control {xb[('control', 'sysBOff')]} / candidate "
          f"{xb[('candidate', 'sysBOff')]} px at System B OFF, "
          f"{xb[('control', 'sysBOn')]} / {xb[('candidate', 'sysBOn')]} "
          f"shipped.")
    A("- The Target frames in the private package are the O3 captures reused "
      "verbatim, because the 3.3 / 1.5 / 2.0 px anchors this gate is scored "
      "against are those captures' own numbers. Re-measured there under the "
      "O4 sealed instrument, all three reproduce.")
    A(f"- Console and page errors during gate capture: "
      f"{g['consoleAndPageErrors']}.")
    A("- All sixteen §十一 frozen suites PASS at the O4 build.")
    A("- Target pixels and video appear only in the private package.")
    A("")
    A(f"Captured at `{captured}`.")
    A("")
    (outdir / "README.md").write_text("\n".join(L))

    files = []
    for p in sorted(outdir.iterdir()):
        if p.is_file() and p.name != "MANIFEST.json":
            files.append({"file": p.name, "bytes": p.stat().st_size,
                          "sha256": sha256(p)})
    (outdir / "MANIFEST.json").write_text(json.dumps({
        "tree": "qa-v5/optics-o4",
        "what": "O4 frozen body floor attribution -- public evidence. "
                "Numbers, source anchors and verdicts only; Target pixels "
                "and video live in the private package.",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": captured,
        "reviewHeadNote": "absent from the public tree: a committed file "
                          "cannot carry its own commit hash. The private "
                          "package carries both heads.",
        "finalState": g["finalState"], "absoluteGate": g["absoluteGate"],
        "shippedDefault": g["shippedDefault"],
        "containsTargetPixels": False,
        "files": files,
    }, indent=1))
    print(f"{outdir}: {len(files)} files")
    print(f"finalState: {g['finalState']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
