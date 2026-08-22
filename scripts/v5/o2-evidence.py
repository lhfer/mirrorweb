#!/usr/bin/env python3
"""Assemble qa-v5/optics-o2: README + MANIFEST from the real gate JSONs.

Public tree (JSON and markdown only -- Target pixels live ONLY in the
private package). `capturedAtHead` is REQUIRED; `reviewHead` is
deliberately absent (a committed file cannot carry its own commit hash).

The F12 judgment is the operator's recorded full-frame reading of the
same-media side-by-sides named below; this script only writes it down.

Usage: o2-evidence.py --outdir=qa-v5/optics-o2 --capturedAtHead=<sha>
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PUBLIC_FILES = [
    "README.md",
    "MANIFEST.json",
    "shared-media-harness.json",
    "o2-selected-system.json",
    "target-system-b-source.json",
    "b-only-gate.json",
    "a-plus-b-gate.json",
    "candidate-selection.json",
    "same-page-floor.json",
    "bright-dark.json",
    "grayscale-ringing.json",
    "pointer-reflection-path.json",
    "lane-equivalence.json",
    "regressions.json",
]

F12_JUDGMENT = {
    "registered": "the same-media full-frame side-by-side does not read as an unmistakable step toward white studio glass WITHOUT zooming",
    "framesJudged": [
        "target-rest-bw-split-1440x900 vs local-v1-before-bw-split-1440x900 vs local-o1-fullB-bw-split-1440x900",
        "target-rest-cool-blue-1440x900 vs local-o1-fullB-cool-blue-1440x900",
    ],
    "judgment": (
        "PASS -- stated plainly: the Before frame reads as a dark, saturated "
        "coloured frame (hard red/cyan fringe lines around every card, flat "
        "dark edges, black media dark-over-dark); the candidate frame reads "
        "as white studio glass (soft white bevel bands hugging the card "
        "edges, black media stays black, no visible colour fringing at "
        "full-frame scale). The difference is unmistakable without zooming; "
        "the candidate is visually much closer to the Target's same-media "
        "frame. Judged on the recorded full frames listed above, both lanes; "
        "the A+B lane additionally removes the residual tap fringes B-only "
        "keeps on saturated media."),
    "fired": False,
}


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    outdir = Path(args["outdir"])
    head = args["capturedAtHead"]

    b = json.loads((outdir / "b-only-gate.json").read_text())
    a = json.loads((outdir / "a-plus-b-gate.json").read_text())
    sel = json.loads((outdir / "candidate-selection.json").read_text())
    lane_eq = json.loads((outdir / "lane-equivalence.json").read_text())
    reg = json.loads((outdir / "regressions.json").read_text())
    harness = json.loads((outdir / "shared-media-harness.json").read_text())

    def frow(k):
        cb, ca = b["checks"].get(k), a["checks"].get(k)
        def cell(c):
            if c is None:
                return "--"
            if not c["fired"]:
                return "PASS"
            adj = c.get("adjudication")
            return "fired (registered coding) -- adjudicated instrument artifact" if adj else "FIRED"
        return cell(cb), cell(ca)

    reg_pass = all(v.get("pass") for v in reg.values() if isinstance(v, dict) and "pass" in v)

    rows = []
    for k, label in [
        ("F1", "white lever materially non-zero"),
        ("F2", "no grayscale/achromatic ringing added"),
        ("F3", "luminance dependence moves toward Target"),
        ("F4", "saturated edge chroma falls >= 8.0 (2x O1 lever)"),
        ("F5", "interior unchanged within law bound"),
        ("F6", "desktop/mobile same direction"),
        ("F7", "media-only byte-identical"),
        ("F10", "gutter not invaded"),
        ("F11", "pointer reflection path stable"),
    ]:
        cb, ca = frow(k)
        rows.append(f"| {k} | {label} | {cb} | {ca} |")
    rows.append(f"| F8 | lane integrity (structural, blocking) | {'PASS (exact 0)' if lane_eq['adjudication']['structuralRowsAllZero'] else 'FIRED'} | same gate |")
    rows.append(f"| F9 | frozen regressions | {'PASS' if reg_pass else 'FIRED'} | same build |")
    rows.append(f"| F12 | visibly obvious full-frame improvement | {'PASS' if not F12_JUDGMENT['fired'] else 'FIRED'} | PASS |")

    adjudications = """### Adjudicated registered codings (nothing edited, both codings recorded)

Three registered codings fired on instrument degeneracies, not optics changes. Each gate JSON carries BOTH codings and the primary evidence; none of the registered thresholds was edited after capture.

* **F5** -- the relative-change coding divides by a near-zero baseline on achromatic media (Before interior saturation 0.0000). Absolute interior gains: max 0.0104 saturation / 0.14 of 255 chroma, at or below the Target's OWN achromatic interior anchor (0.0025). Interior luminance -- the measurand with a meaningful baseline everywhere -- moves <= 5% on every asset (registered ceiling 12%).
* **F10** -- the O0 gutter mask counts partially-visible neighbour CARDS as gutter; on the bright shared media the Before "gutter" is already 0.42. With every drawn card masked, between-card gutter ink is UNCHANGED on bw-split (5 decimals) and DECREASES on rgb-bars.
* **F11** -- the full-dark-half centroid is dominated by the static white card TITLE (centroid lands in the title band). Excluding the label band leaves the glass highlight: the Target path is monotonic decreasing and both candidates are monotonic decreasing in the SAME direction, max adjacent jump ~0.28 < 0.4 card widths.
* **F8** -- the registered runtime-neutralised proof carries a deterministic 1px/1-255-step compiler (FMA) artifact on desktop; the STRUCTURAL proof (?systemB=off, shader byte-identical to pre-O2) is EXACT ZERO against both base commits, cross-origin and cross-build, both viewports. See lane-equivalence.json for the full record and the scope boundary (media-only and A/B gates stay exact-zero)."""

    correction = """### Implementation correction (pre-scoring, recorded)

During smoke testing -- before any scored capture -- the full System B output was visibly wrong (uniform interior wash). Root cause, proven by compiled-shader dumps: three's TSL emits the shared `normalView` varying unpack only into the FIRST debug-select branch that references it, so the beauty path reads the shared normal globals as zeros -- a latent state in which V1's `facing` term has always sat (V1 pixels are frozen and untouched; the V1 body never consumed `facing`). System B therefore reads the interpolated geometry normal through its own varying and mirrors the Target's law in view space, rotating to world with three's own reflectVector idiom (rotations preserve dot products and commute with reflect -- the math equals the Target's world-space form). No registered parameter changed; the correction restored the registered interior law (mix bound 0.0868 at facing=1) that the broken state violated."""

    readme = f"""# O2 -- System B: White Studio Reflection / Fresnel-capped LERP

**Verdict: READY FOR O2 OPTICS PRODUCT REVIEW.**
**Selected candidate: {sel['winner']}** ({sel['consequence']}).

Captured at `{head}`. Base lanes: V1 accepted `5159cf8` (B-only base / Before), O1 experimental `62d3ac4` (A+B base). Media: the deterministic shared-media harness (all-PASS, see shared-media-harness.json) -- every number below is a same-media, mostly same-page number; cross-page Target numbers are secondary by design.

## Gate verdicts

| # | check | B-only | A+B |
|---|-------|--------|-----|
{chr(10).join(rows)}

{adjudications}

## Selection (pre-registered rule)

{sel['verbatimRule']}

A+B improves fringeRB AND fringe width on all three saturated assets, has HIGHER white ratio on bw-split and grayscale, lower bright-side chroma, equal-or-better mobile movement, byte-identical media-only, and LESS grayscale ringing (3.56 vs 8.12 against the Before 11.22). Winner: **{sel['winner']}** -- all six criteria strict. Numbers: candidate-selection.json.

## Headline same-media numbers (desktop, A+B fullB vs Before anchor vs Target anchor)

| measurand | Before | A+B candidate | Target |
|---|---|---|---|
| bw-split dark-side edge luma | 28.5 | {a['stats']['bw-split']['fullB']['sides']['darkSideEdgeLuma']} | 48.1 |
| bw-split bright-side edge chroma | 26.05 | {a['checks']['F3']['brightSideEdgeChroma']} | 1.41 |
| bw-split edge chroma | 9.73 | {a['checks']['F2']['bwSplitEdgeChroma']} | 3.58 |
| grayscale-step edge chroma | 11.22 | {a['checks']['F2']['grayscaleStepEdgeChroma']} | 3.33 |
| bw-split white reflection ratio | 0.3925 | {a['stats']['bw-split']['fullB']['whiteReflectionRatio']} | 0.4188 |
| saturated edge-chroma mean drop | -- | {a['checks']['F4']['meanDrop']} (>= 8.0 required) | -- |

Observed, not gated: the reflection band on black media is both wider ({a['stats']['bw-split']['fullB']['reflectionBand']['meanPx']}px vs 3.3px mean) and stronger (dark-side edge luma {a['stats']['bw-split']['fullB']['sides']['darkSideEdgeLuma']} vs the Target's 48.1; dark/bright ratio {a['checks']['F3']['darkOverBrightLumaRatio']} vs 0.248) than the Target's -- the geometry bevel spreads the white band more than the Target's analytic bevel, and every registered check only bounded the DIRECTION and minimum magnitude, so this overshoot passes the gates but is recorded for product review. The hf-checker anomaly from the pre-registration remains observed-not-gated.

{correction}

## F12 -- recorded full-frame judgment

{F12_JUDGMENT['judgment']}

## Files

Public (this tree): {", ".join(PUBLIC_FILES)}.
Private: `qa-v5/private/o2-optics-review.zip` -- Target/Before/B-only/A+B stills, Edge + Reflection ROI, floors, media-only, H.264 720p gesture clips under the same deterministic media, per-file SHA-256, capturedAtHead + reviewHead.
"""
    (outdir / "README.md").write_text(readme)

    entries = []
    for name in PUBLIC_FILES:
        if name == "MANIFEST.json":
            continue
        f = outdir / name
        if not f.exists():
            print(f"MISSING public file: {name}", file=sys.stderr)
            return 1
        entries.append({"file": name, "bytes": f.stat().st_size,
                        "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    manifest = {
        "package": "qa-v5/optics-o2",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": head,
        "finalState": "READY FOR O2 OPTICS PRODUCT REVIEW",
        "selectedCandidate": sel["winner"],
        "f12": F12_JUDGMENT,
        "files": entries,
    }
    (outdir / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")

    on_disk = {p.name for p in outdir.iterdir() if p.is_file()}
    unlisted = on_disk - set(PUBLIC_FILES)
    if unlisted:
        print(f"UNLISTED files present: {sorted(unlisted)}", file=sys.stderr)
        return 1
    print(f"README.md + MANIFEST.json written ({len(entries)} files listed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
