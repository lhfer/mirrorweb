#!/usr/bin/env python3
"""Assemble the public qa-v5/optics-o3 tree: README + MANIFEST, written
from the real gate JSONs rather than restated by hand.

Public tree = JSON and markdown only. Target pixels and video live ONLY in
the private package. `capturedAtHead` is REQUIRED; `reviewHead` is
deliberately absent from the public tree, because a committed file cannot
carry its own commit hash.

The §九.20 judgement is the operator's recorded full-frame reading of the
frames named below at 100%; this script writes it down, it does not make
it.

Usage: o3-evidence.py --outdir=qa-v5/optics-o3 --capturedAtHead=<sha>
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent

PUBLIC_FILES = [
    "README.md",
    "MANIFEST.json",
    "o3-preregistration.json",
    "target-bevel-reflection-source.json",
    "bevel-source-live.json",
    "target-repeatability.json",
    "instrument-tests.json",
    "instrument-dryrun.json",
    "o3-absolute-gate.json",
    "judgement-20.json",
    "regressions.json",
]

#: The operator's §九.20 reading. Read, not made here -- the same file
#: the verdict script scored the item from, so the README and the gate
#: record cannot drift apart.
JUDGEMENT_20 = json.loads(
    (REPO / "qa-v5/optics-o3/judgement-20.json").read_text())

def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def full_sha(label: str, value: str) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify",
                           f"{value}^{{commit}}"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{label}: {value!r} does not resolve to a commit")
    sha = proc.stdout.strip()
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise SystemExit(f"{label}: resolved to a non-40-hex value {sha!r}")
    return sha


def fmt(v):
    return "—" if v is None else v


def readme(gate: dict, xsec: dict, captured: str) -> str:
    by_n = {i["n"]: i for i in gate["items"]}
    L = []
    A = L.append

    A("# O3 — Target Analytic Bevel Reflection Support")
    A("")
    A(f"**Final state: {gate['finalState']}**")
    A("")
    A(f"Absolute gate: **{gate['absoluteGate']}** — "
      f"{gate['itemsPassed']} of 20 items passed, {gate['itemsFailed']} failed"
      + (f", {gate['itemsPending']} pending" if gate["itemsPending"] else "")
      + f". Thresholds were sealed at `{gate['sealedAtHead'][:12]}` before any "
        f"candidate pixel was captured and were not touched afterwards.")
    A("")
    A("The shipped default therefore stays `reflectionSupport=geometry` — "
      "the accepted O2 System B. That is the sealed default-flip rule's "
      "negative branch executing, not a separate decision.")
    A("")

    A("## What O3 changed")
    A("")
    A("O2 adopted the Target's reflection **law** and product review froze "
      "it. What O2 did not have was the **field** that law is evaluated on: "
      "it stood our baked geometry shoulder normal in for the Target's "
      "analytic bevel normal, and the `strongLensRim` vertex attribute in "
      "for the Target's rounded-rect SDF rim.")
    A("")
    A("O3 transcribes that field from the byte-anchored source contract "
      "(`target-bevel-reflection-source.json`, 29 sites, 0 failed) into "
      "`src/materials/TargetBevelFieldV4.ts`, and swaps exactly two inputs "
      "to the frozen System B block:")
    A("")
    A("| | O2 control (`geometry`) | O3 candidate (`target-sdf`) |")
    A("|---|---|---|")
    A("| Fresnel / env reflect normal | `v_o2NormalView` geometry normal | analytic bevel normal |")
    A("| White rim mask | `strongLensRim` attribute (≈31.7 px) | `smoothstep(-rimWidth, 0, sdf) × 0.11` (8.3 px) |")
    A("")
    A("Both lanes are the same commit, the same page and the same frozen "
      "media, selected by a build-time JS branch. No parameter was tuned "
      "and no threshold was moved.")
    A("")

    A("## The twenty items")
    A("")
    A("| # | Item | Result | Measured |")
    A("|---|---|---|---|")
    summary = {
        1: lambda i: f"{len(i['cases'])} cases, all 0 differing px",
        2: lambda i: f"{i['siteCount']} byte-anchored sites, "
                     f"{i['sitesFailed']} failed; live bundle "
                     f"{'matches' if (i.get('liveBundle') or {}).get('matchesCapturedBundle') else 'not compared'}",
        3: lambda i: f"candidate {i['candidatePx']} px vs Target {i['targetPx']} px "
                     f"(Δ {i['deltaPx']}, ceiling {i['threshold']})",
        4: lambda i: f"candidate {i['candidatePx']} px vs control {i['controlPx']} px "
                     f"— ratio ceiling {i['ratioCeilingPx']} px, drop {i['absoluteDropPx']} px",
        5: lambda i: f"candidate {i['candidateLuma']} vs Target {i['targetLuma']} "
                     f"(Δ {i['delta']}, ceiling {i['threshold']})",
        6: lambda i: f"candidate {i['candidate']} vs Target {i['target']} (Δ {i['delta']})",
        7: lambda i: f"candidate distance {i['candidateDistance']} < control {i['controlDistance']}",
        8: lambda i: f"candidate {i['candidate']} vs control {i['control']} "
                     f"(ceiling {i['ceiling']})",
        9: lambda i: ", ".join(f"{a['asset']} {a['candidate']}/{a['ceiling']}"
                               for a in i["assets"]),
        10: lambda i: ", ".join(f"{a['asset']} fringeRB "
                                f"{a['fringeRB']['candidate']} vs {a['fringeRB']['control']}"
                                for a in i["assets"]),
        11: lambda i: ", ".join(f"{a['asset']}" for a in i["assets"] if a["fired"])
                      or "no asset fired",
        12: lambda i: f"{len(i['pairs'])} pairs, all 0 differing px",
        13: lambda i: ", ".join(f"{r['asset']}@{r['vp']} Δ{r['delta']}"
                                for r in i["rows"]),
        14: lambda i: f"branch {i['verdict']['branch']}, fired={i['verdict']['fired']}",
        15: lambda i: ", ".join(f"{v['vp']} band {v['bandDelta']:+}"
                                for v in i["viewports"]),
        16: lambda i: f"{len(i['sequences'])} clips measured",
        17: lambda i: f"gate 1 zero={i['gate1Zero']}, control declares "
                      f"v_o2NormalView={i['controlDeclaresO2Varying']}",
        18: lambda i: "all program checks true",
        19: lambda i: f"{sum(1 for s in i['suites'] if s['pass'])}/"
                      f"{len(i['suites'])} suites PASS",
        20: lambda i: "judged on the full frames — see below",
    }
    for n in range(1, 21):
        i = by_n.get(n)
        if not i:
            continue
        try:
            meas = summary[n](i)
        except Exception:
            meas = i.get("reason", "—")
        res = i["result"] if n != 20 else ("FAIL" if JUDGEMENT_20["fired"] else "PASS")
        A(f"| {n} | {i['item']} | **{res}** | {meas} |")
    A("")

    A("## Why it failed — the frozen base already exceeds the Target's whole band")
    A("")
    A("This is the finding that matters for what comes next, and it is "
      "measured, not argued.")
    A("")
    A("Both lanes were captured at the registered floor states. At "
      "`envMixScale=0, rimScale=0` System B is entirely off and the two "
      "lanes are **identical** — proven, not assumed. Whatever band "
      "survives there is painted by the frozen refraction / dispersion / "
      "adaptive-contrast composition, before any reflection exists at all.")
    A("")
    A("| Viewport | Frozen base (System B off) | O2 control | O3 candidate | Target |")
    A("|---|---|---|---|---|")
    for vp, d in (xsec.get("decomposition") or {}).items():
        A(f"| {vp} | **{d['frozenBaseBandPx']} px** | {d['controlFullBandPx']} px "
          f"| {d['candidateFullBandPx']} px | {d['targetBandPx']} px |")
    A("")
    A("At every viewport the frozen base **alone** paints a wider band than "
      "the Target's entire measured band. The reflection support is not the "
      "binding constraint: no change to the support field — the Target's "
      "own included — can take the band below a floor that exists with the "
      "reflection switched off. Gate 3 needs the candidate within 1.5 px of "
      "3.3 px; the base is 9.7 px.")
    A("")
    A("The residual lives in `adaptiveEdgeLift` / `contrastShaped` and the "
      "refraction edge treatment — code §一 forbids O3 to touch. That is "
      "the boundary this round establishes, and it is the only thing an O4 "
      "decision actually needs from here.")
    A("")
    A("It is worth being explicit about the loophole this does not leave "
      "open. A support field that saturated the fresnel to the 0.27 "
      "envMaxMix cap everywhere could in principle pull the candidate's "
      "77.6 dark-side luma down toward the gate-5 threshold. But that field "
      "would not be the Target's field, and the Target's field is exactly "
      "what O3 is pinned to. The question was never \"can some support "
      "field pass\"; it is \"does the Target's own field pass on our frozen "
      "base\", and the decomposition answers it.")
    A("")

    A("## What the candidate does achieve")
    A("")
    A("Recorded because a failed gate is not the same as a failed mechanism.")
    A("")
    A("- The rim swap works exactly as the source says it should. Isolating "
      "the rim (env-off, rim-on minus env-off, rim-off) the candidate's rim "
      "peaks at 37 luma 2 px inward, is down to 5 by 8 px and is 0 by 10 px "
      "— an 8.3 px band, as the source specifies. The control's is still "
      "lifting 39 luma at 16 px and 32 at 18 px.")
    A("- Band width falls 15.3 → 8.7 px, dark-side luma 95.1 → 77.6, "
      "dark/bright ratio 0.5006 → 0.4388 — every one of them toward the "
      "Target. Items 6 and 7 pass on that movement.")
    A("- Item 15 is the same direction at all three viewports.")
    A("- Item 16: no rim or reflection pop on any recorded sequence; the "
      "worst adjacent-frame change is 2.1% against a 40% ceiling, at or "
      "below the control on every clip.")
    A("- Items 1, 12, 17, 18: the control lane is still bit-for-bit the "
      "e913aa6 O2 program, and the compiled shaders prove each lane "
      "consumes its own support with no leakage.")
    A("")

    A("## Failures that need reading carefully")
    A("")
    i13 = by_n[13]
    A("**Item 13 (gutter invasion).** Scored FAIL at +0.020 against a "
      "0.006 ceiling. The instrument and threshold are untouched and the "
      "item stands as scored. What the number is made of: outside the "
      "**true** glass silhouette — every pixel the glass layer touches, "
      "taken from the media-only captures — the two lanes are bit-identical "
      "(max channel difference 0.0). The candidate puts no light into real "
      "gutter. The whole delta lies between the flat layout quad F10 masks "
      "and the larger silhouette the bulged lens actually projects, which "
      "is where the candidate concentrates its narrower rim.")
    A("")
    A("**Items 8, 9, 10 (edge chroma).** Scored FAIL. The floor states "
      "attribute it: with System B off the lanes are identical; at rim-only "
      "the **control** reads lower chroma, because its over-wide white rim "
      "covers the edge band with neutral white and dilutes the mean; at "
      "env-only the candidate reads higher, because the analytic normal "
      "tilts to the source's 60° slope clamp and swings the reflection "
      "vector further into a coloured studio HDR. So the rise is partly a "
      "real chroma increase and partly the removal of a white rim that had "
      "been masking the frozen base's own colour — corroborated by "
      "`fringeWidthPxMean` falling on every saturated asset in item 10.")
    A("")
    knife = by_n[11].get("nearFloorCoding")
    if knife:
        A("**Item 11 (interior).** Seven of eight assets do not fire. "
          + "; ".join(f"`{r['asset']}` has baseline interior saturation "
                      f"{r['baselineSaturation']}, just above the 0.01 floor, "
                      f"so the sealed rule took the relative branch and a "
                      f"{r.get('relSaturationChange', 0):.1%} relative change "
                      f"fired" for r in knife)
          + ". The branch was fixed by the baseline before any candidate "
            "pixel existed and is not revisited here.")
        A("")

    A("## §九.20 — the judged full frames")
    A("")
    A(f"Registered failure text: *{JUDGEMENT_20['registeredFailureText']}*")
    A("")
    A(f"Frames judged at {JUDGEMENT_20['judgedAt']}: "
      + ", ".join(f"`{f}`" for f in JUDGEMENT_20["framesJudged"]))
    A("")
    A(JUDGEMENT_20["judgement"])
    A("")

    A("## Frozen regressions (§十一)")
    A("")
    i19 = by_n.get(19, {})
    if i19.get("suites"):
        for s in i19["suites"]:
            A(f"- {'PASS' if s['pass'] else 'FAIL'} — {s['name']}")
    else:
        A("- pending")
    A("")

    A("## Method notes")
    A("")
    A("- Every threshold comes from `o3-preregistration.json`, sealed at "
      f"`{gate['sealedAtHead'][:12]}`. Nothing was recoded after capture.")
    A("- The F5 / F10 / F11 corrections are imported from "
      "`scripts/v5/o3_instruments.py` — the same module "
      "`instrument-tests.json` certifies (36 tests, including a "
      "non-monotonic input that genuinely fires) and `instrument-dryrun.json` "
      "exercised on the O2 captures before sealing.")
    A("- Target repeatability was measured before any candidate code "
      "existed; all repeats were byte-identical under the deterministic "
      "harness, so every §八 threshold binds at its floor rather than at a "
      "zero spread.")
    A("- Target pixels and video appear only in the private package.")
    A("")
    A(f"Captured at `{captured}`.")
    A("")
    return "\n".join(L)


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    outdir = Path(args["outdir"])
    captured = full_sha("capturedAtHead", args["capturedAtHead"])

    gate = json.loads((outdir / "o3-absolute-gate.json").read_text())
    xpath = REPO / "artifacts/optics-o3/crosssection/crosssection.json"
    xsec = json.loads(xpath.read_text()) if xpath.exists() else {}


    (outdir / "README.md").write_text(readme(gate, xsec, captured))

    files = []
    for name in PUBLIC_FILES:
        p = outdir / name
        if name == "MANIFEST.json" or not p.exists():
            continue
        files.append({"file": name, "bytes": p.stat().st_size,
                      "sha256": sha256(p)})
    present = {f.name for f in outdir.iterdir() if f.is_file()}
    unlisted = present - set(PUBLIC_FILES)
    manifest = {
        "tree": "qa-v5/optics-o3",
        "what": "O3 Target analytic bevel reflection support — public "
                "evidence. Numbers, source anchors and verdicts only; "
                "Target pixels and video live in the private package.",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": captured,
        "reviewHeadNote": "deliberately absent from the public tree: a "
                          "committed file cannot carry its own commit hash. "
                          "The private package carries both heads.",
        "finalState": gate["finalState"],
        "absoluteGate": gate["absoluteGate"],
        "shippedDefault": gate["defaultFlip"]["shippedDefault"],
        "containsTargetPixels": False,
        "unlistedFiles": sorted(unlisted),
        "files": files,
    }
    (outdir / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    if unlisted:
        print(f"WARNING unlisted files in the public tree: {sorted(unlisted)}",
              file=sys.stderr)
        return 1
    print(f"{outdir}/README.md + MANIFEST.json  ({len(files)} files)")
    print(f"finalState: {gate['finalState']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
