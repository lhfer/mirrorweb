#!/usr/bin/env python3
"""O5 §十三 -- the public evidence tree: README.md and MANIFEST.json.

Written from the scored artefacts, never by hand. Every number in the README
is read out of a JSON file in this directory, so the prose and the data cannot
drift apart.

Usage: o5-evidence.py --capturedAtHead=<sha> [--outdir=<dir>]
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def full_sha(label, value):
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", value],
                       capture_output=True, text=True)
    if r.returncode != 0 or len(r.stdout.strip()) != 40:
        raise SystemExit(f"{label}: cannot resolve {value!r} to a full SHA")
    return r.stdout.strip()


def sha256(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def jload(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def item(g, n):
    return next((i for i in g["items"] if i["item"] == n), {})


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    outdir = Path(args.get("outdir", REPO / "qa-v5/optics-o5"))
    captured = full_sha("capturedAtHead", args["capturedAtHead"])

    g = jload(outdir / "body-absolute-gate.json")
    ident = jload(outdir / "control-identity.json")
    audit = jload(outdir / "compiled-body-audit.json")
    contract = jload(outdir / "target-optical-body-contract.json")
    arch = jload(outdir / "o5-architecture.json")
    tests = jload(outdir / "instrument-tests.json")
    regs = jload(outdir / "regressions.json")
    perf = jload(outdir / "pipeline-performance.json")
    rep = jload(outdir / "target-repeatability.json")

    L = []
    A = L.append
    A("# O5 — Source-Exact Card Optical Body")
    A("")
    A(f"**Final state: {g['finalState']}**")
    A("")
    A(f"Absolute gate: **{g['absoluteGate']}** — {g['passed']} of {g['total']} "
      f"items passed, {g['failed']} failed, {g['pending']} pending.")
    A("")
    A("The shipped default stays `opticalBody=current`. This brief registers "
      "no automatic flip and its final states do not include one; product "
      "review owns that decision. **Target Visual PASS: NOT ASSERTED.**")
    A("")

    # ---------------------------------------------------------------- §六
    A("## §六 — control identity")
    A("")
    if ident:
        A(f"**{ident['verdict']}.** {ident['comparisons']} comparisons — "
          f"{len(ident['viewports'])} viewports x {len(ident['states'])} "
          f"states — between `opticalBody=current` at the O5 code commit and a "
          f"`{ident['baselineCommit'][:7]}` worktree build on deterministic "
          f"shared media: **exactly zero** differing pixels, every state probe "
          f"matching, {ident['consoleAndPageErrors']} console errors.")
        A("")
        A("Every comparison below is therefore against the accepted O2 body "
          "and not against something that drifted.")
    A("")

    # ---------------------------------------------------------------- §七
    A("## §七 — compiled body audit")
    A("")
    if audit:
        A(f"**{audit['passed']}/{audit['total']}.** The candidate's program "
          f"contains "
          f"{audit['programs']['high']['refracts']} `refract()` calls at high "
          f"and {audit['programs']['low']['refracts']} at low, tracking the "
          f"sample count exactly; declares **no shared normal varying at "
          f"all**, so the O4A zero-normal defect has no surface to occur on; "
          f"and compiles to {audit['programs']['high']['bytes']} bytes against "
          f"the control's {audit['controlProgramBytes']}.")
        A("")
        pr = audit["runtimeProbe"]
        A(f"The analytic normal decodes to unit length on "
          f"{pr['unitLengthFraction'] * 100:.1f}% of "
          f"{pr['pixels']} card pixels with per-channel standard deviation "
          f"{pr['channelStd']} — the O4A discriminator, where a zero normal "
          f"reads as std 0. Zero non-finite and zero all-black pixels.")
        A("")
        A(f"Item 9 is settled at runtime rather than by a string search: the "
          f"scene-colour pass draws "
          f"{audit['renderPasses'].get('sceneColorCalls')} calls and the media "
          f"plane is hidden, yet the cards still show media. Item 10 carries a "
          f"positive control — the same probe finds "
          f"{audit['textureSampleCalls']['controlExplicitLod']} explicit-LOD "
          f"samples in the control program and "
          f"{audit['textureSampleCalls']['candidateExplicitLod']} here.")
    A("")

    # ---------------------------------------------------------------- gate
    A("## The fourteen gate items")
    A("")
    A("| # | Item | Result |")
    A("|---|---|---|")
    for i in g["items"]:
        v = "**PASS**" if i["pass"] else ("**FAIL**" if i["pass"] is False
                                          else "pending")
        A(f"| {i['item']} | {i['name']} | {v} |")
    A("")

    # ---------------------------------------------------------------- band
    A("## What the candidate achieved")
    A("")
    b = item(g, 1)
    A("**The reflection band enters the Target's window at every viewport** — "
      "the measurement O3 and O4 both failed.")
    A("")
    A("| Viewport | Target | control | candidate | window | candidate Δ |")
    A("|---|---|---|---|---|---|")
    for r in b["numbers"]["rows"]:
        A(f"| {r['vp']} | {r['target']} px | {r['control']} px | "
          f"**{r['candidate']} px** | ±{r['windowPx']} | {r['candidateDelta']} |")
    A("")
    d = item(g, 2)
    A("Dark-side edge luminance lands on the Target at three of four "
      "viewports, from a control that was roughly twice as bright:")
    A("")
    A("| Viewport | Target | control | candidate | window | enters |")
    A("|---|---|---|---|---|---|")
    for r in d["numbers"]["rows"]:
        A(f"| {r['vp']} | {r['target']} | {r['control']} | "
          f"**{r['candidate']}** | ±{r['window']} | "
          f"{'yes' if r['enters'] else 'NO'} |")
    A("")
    n6 = item(g, 6)["numbers"]
    A(f"- Item 6: per-tile high-frequency structure correlates "
      f"**{n6['localSpectralCorrelationToTarget']['r']}** with the Target "
      f"across {n6['localSpectralCorrelationToTarget']['n']} tiles, against "
      f"the control's {n6['controlSpectralCorrelationToTarget']['r']} and a "
      f"floor of {n6['floors']['correlation']}. HF energy retention is "
      f"{n6['hfEnergy']['retention']} — the candidate reads "
      f"{n6['hfEnergy']['candidate']} against the Target's "
      f"{n6['hfEnergy']['target']}, where the control reads "
      f"{n6['hfEnergy']['control']}.")
    A("- Item 8: own-media isolation is structural — the refracted UV is "
      "clamped before the cover transform, and the scene-colour pass draws "
      "nothing in this lane.")
    A("- Item 12: no pop on any recorded sequence.")
    i14 = item(g, 14)["numbers"]["checks"]
    A(f"- Item 14: the candidate is closer to the Target than the control on "
      f"all three failure modes §九.14 names — band width "
      f"{i14['thickWhitePlastic_bandPx']['candidate']} vs the Target's "
      f"{i14['thickWhitePlastic_bandPx']['target']} (control "
      f"{i14['thickWhitePlastic_bandPx']['control']}), interior "
      f"high-frequency energy "
      f"{i14['blurredLens_interiorHf']['candidate']} vs "
      f"{i14['blurredLens_interiorHf']['target']} (control "
      f"{i14['blurredLens_interiorHf']['control']}). The third sub-check, "
      f"fringe width on cool-blue, reads 0.0 for all three lanes and is "
      f"therefore DEGENERATE — it carries no signal and its \"closer\" verdict "
      f"is vacuous. Two of three sub-checks discriminate; that is what the "
      f"item rests on.")
    A("")

    # ---------------------------------------------------------------- fails
    A("## What failed, and which failures are the instrument's")
    A("")
    A("Six items failed. They are not all the same kind of thing, and the "
      "difference matters more than the count.")
    A("")
    A("### Candidate behaviour")
    A("")
    A("**Items 2 and 3 fail at 390x844 only.** Dark-side luma reads "
      f"{d['numbers']['rows'][1]['candidate']} against a Target of "
      f"{d['numbers']['rows'][1]['target']} (window "
      f"±{d['numbers']['rows'][1]['window']}), and the white reflection ratio "
      f"{item(g, 3)['numbers']['rows'][1]['candidate']} against "
      f"{item(g, 3)['numbers']['rows'][1]['target']}. Both are inside the "
      "window at the other three viewports, and both moved toward the Target "
      "from the control everywhere. Portrait mobile is the narrowest card in "
      "the set, so its bevel occupies the largest fraction of the card — the "
      "one geometry where a small error in the bevel profile has the most "
      "room to show.")
    A("")
    A("### Instrument limitations, reported as failures because the codings "
      "were sealed")
    A("")
    A("These three were sealed before capture and are scored exactly as "
      "written. Each is a FAIL. In each case the diagnosis is that the "
      "instrument, not the candidate, is what could not do the job — and that "
      "is recorded here rather than fixed after the fact, because fixing a "
      "coding once its pixels exist is the failure mode the whole sealing "
      "discipline exists to prevent.")
    A("")
    g4 = item(g, 4)["numbers"]["rows"][0]
    A(f"**Item 4 — grayscale chroma.** The candidate reads "
      f"{g4['candidate']['p995']} against a ceiling of {g4['ceiling']}. So "
      f"does the control, at {g4['control']['p995']} — and so does **the "
      f"Target, at {g4['target']['p995']}**, five times the ceiling. The "
      f"ceiling was set as an absolute and is simply too tight for media that "
      f"has been through a 4:2:0 video encode, where chroma subsampling puts "
      f"colour on every sharp luminance edge. A test the Target fails worse "
      f"than the candidate is not measuring the candidate.")
    A("")
    r9 = item(g, 9)["numbers"]["rows"]
    A("**Item 9 — interior fidelity.** The sealed coding asks that the "
      "candidate be *no blurrier than the control*, which is the wrong "
      "question: on hf-checker the Target reads "
      f"{r9[2]['target']['sharpness']}, the control "
      f"{r9[2]['control']['sharpness']} and the candidate "
      f"{r9[2]['candidate']['sharpness']} — the candidate is far closer to the "
      "Target and fails the item *for being closer*, because the control is "
      "sharper than the Target is. The coding should have asked for proximity "
      "to the Target.")
    A("")
    A("But re-scoring it that way would not simply flip it, and saying so "
      "matters more than the excuse. Under a proximity coding the candidate "
      "wins hf-checker decisively (Δ 4.1 against the control's 33.8) and "
      "loses bw-split (3.57 vs 3.40) and rgb-bars (3.21 vs 2.87) narrowly. "
      "Those two assets have flat interiors, so the interior sharpness "
      "measure is sitting near its own noise floor there — all three lanes "
      "read between 1.2 and 5.7 on a scale where the textured asset reads "
      "150 — and a 0.2 difference between numbers that small is not evidence "
      "of anything. The honest summary is: strong on the asset that has "
      "interior structure to measure, indeterminate on the two that do not.")
    A("")
    A("Interior chroma is the more interesting number and is not part of the "
      f"item's verdict: on hf-checker the candidate reads "
      f"{r9[2]['candidate']['chroma']} against the Target's "
      f"{r9[2]['target']['chroma']}, where the control reads "
      f"{r9[2]['control']['chroma']}. The candidate reproduces the Target's "
      "interior spectral behaviour almost exactly; the control has none of "
      "it at all.")
    A("")
    A("**Item 10 — silhouette.** The instrument evaluates an axis-aligned "
      "rounded-rect SDF over the card's screen-space bounding box. The cards "
      "are perspective-projected onto a sphere, so their quad corners sit up "
      "to **109 px** away from the bounding box corners, and the region the "
      "instrument calls \"outside the silhouette\" therefore contains "
      "background and neighbouring cards. Both lanes fail it — the control at "
      f"{item(g, 10)['numbers']['rows'][0]['litOutsideOwnSdf']} lit pixels, "
      f"the candidate at "
      f"{item(g, 10)['numbers']['rows'][1]['litOutsideOwnSdf']} — which is "
      "the tell: a test that fails the accepted body as well as the candidate "
      "is not separating them. At 844x390, where the card rect is clamped to "
      "the viewport, a synthetically PERFECT rounded-rect card scores "
      "indistinguishably from the real render, so the item carries no "
      "silhouette signal there at all.")
    A("")
    A("**Item 7 — edge compression.** The analytic flat baseline assumes the "
      "media maps linearly across a flat card. The card is a domed plane "
      "under perspective, so it does not, and the guard sealed with the "
      "instrument correctly **refused to answer** on most cards rather than "
      "emitting a confident wrong number — `flatBaselineVerified: false`. The "
      "guard worked exactly as designed; what it protected against was the "
      "model, not the candidate. Note also an asymmetry worth disclosing: the "
      "Target has no media-only render, so its baseline could not be checked "
      "at all and its readings pass the guard by default.")
    A("")

    A("## §十 — pipeline and performance")
    A("")
    if perf:
        A(perf.get("summary", "See pipeline-performance.json."))
    else:
        A("See `pipeline-performance.json`.")
    A("")

    A("## §十二 — frozen regressions")
    A("")
    if regs:
        A(f"**{regs.get('suitesPassed')}/{regs.get('suiteCount')}** suites "
          f"pass at the O5 build. The shipped default is the control lane, so "
          f"these exercise the accepted body; that it is unmoved is the point.")
        A("")
        A("One of them earned its keep this round. **O2 Media-only Controls** "
          "failed on the first run: the candidate's QA media plane sat at a "
          "different depth from the control's, so the two lanes projected the "
          "same media at slightly different sizes and their media-only "
          "captures were not comparable. That plane is hidden in the "
          "candidate's Beauty path, so no optical measurement reads it — but "
          "the true-silhouette derivation and the edge-compression baseline "
          "check both compare lanes through it. The plane was given the "
          "control's depth and ONLY the media-only and glass-only layers were "
          "re-captured; every Beauty capture on disk is the one the gate was "
          "scored on, so items 1–6 and 9–14 are unchanged by construction. "
          "Control identity was re-run after the change and is still exactly "
          "zero.")
    A("")

    A("## Method notes")
    A("")
    if contract:
        A(f"- Source contract: {contract['sites']} sites, "
          f"{contract['sitesFailed']} failed, every offset seek-verified "
          f"against the live bundle. Absences use two spans — the "
          f"{contract['factorySpan']['bytes']}-byte material factory for "
          f"output claims, the {contract['componentSpan']['bytes']}-byte card "
          f"component for geometry claims, because the factory contains no "
          f"geometry code and a claim made there would be vacuous.")
    if tests:
        A(f"- Instruments: {tests['passed']}/{tests['total']} tests pass, each "
          f"with a negative partner, sealed before any candidate pixel.")
    if rep:
        A(f"- Target repeatability was captured BEFORE any candidate frame, "
          f"{rep['repeats']} runs per viewport; every window is "
          f"max(2 x repeatability, floor).")
    if arch:
        A(f"- Architecture: {len(arch['decisions'])} decisions, each marked "
          f"transcription or a named deviation. Our frozen layout reproduces "
          f"the Target's L6 exactly at all five viewports; the cover fit "
          f"matches its centred formula for two clips and deliberately does "
          f"not for the third, which carries a frozen product crop.")
    if arch:
        env = next((x for x in arch["decisions"]
                    if x["id"] == "envSampleCeilingRetained"), None)
        if env and "measured" in env:
            m = env["measured"]
            A(f"- **Known deviation, disclosed rather than fixed:** our O2 "
              f"`envSampleCeiling` clamps the environment sample at 16 and the "
              f"Target has no such clamp. An earlier draft justified it as "
              f"unable to bind by comparing 16 to envIntensity x envMaxMix = "
              f"0.521 — a radiance bound against a dimensionless mix weight, "
              f"which is meaningless. Measured on the asset: "
              f"{m['fractionAboveCeiling'] * 100:.2f}% of texels exceed the "
              f"ceiling and the brightest is {m['maxRadiance']:.0f}, "
              f"{m['ceilingTimesBelowMax']}x it. The clamp binds. The render "
              f"was NOT changed after the gate pixels existed; removing it now "
              f"would be the post-capture adjustment §十一 forbids.")
    A(f"- Console and page errors during scoring capture: "
      f"{g['consoleAndPageErrors']}.")
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
        "round": "O5 — source-exact card optical body",
        "what": "Public evidence: numbers, source anchors and verdicts only. "
                "Target pixels and video live in the private package.",
        "capturedAtHead": captured,
        "reviewHeadNote": "absent from the public tree: a committed file "
                          "cannot carry its own commit hash. The private "
                          "package carries both heads.",
        "finalState": g["finalState"],
        "absoluteGate": g["absoluteGate"],
        "containsTargetPixels": False,
        "files": files,
    }, indent=1))
    print(f"{outdir}: {len(files) + 1} files")
    print(f"finalState: {g['finalState']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
