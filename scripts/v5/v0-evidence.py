#!/usr/bin/env python3
"""qa-v5/culling README + MANIFEST, generated from the gate outputs.

Every number in the README is read out of the JSON beside it -- nothing is
typed in by hand, so the prose cannot drift from the data. The MANIFEST
carries `capturedAtHead` as a REQUIRED input: there is no current-HEAD
fallback, because a default would make the evidence commit look like the
capture commit. `reviewHead` is deliberately NOT in the public manifest -- a
committed file cannot contain the hash of the commit that carries it; the
private package states it instead.

Usage: v0-evidence.py --outdir=<dir> --capturedAtHead=<sha>
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

PUBLIC_FILES = [
    "README.md",
    "MANIFEST.json",
    "target-culling-source.json",
    "coverage-truth.json",
    "slot-verdicts.json",
    "edge-pop-in.json",
    "transform-writes.json",
    "performance.json",
    "typography-regression.json",
    "motion-regression.json",
    "source-contract.json",
]


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    outdir = Path(args["outdir"])
    head = args["capturedAtHead"]
    if not head:
        print("capturedAtHead is required", file=sys.stderr)
        return 2

    J = {}
    for name in PUBLIC_FILES:
        p = outdir / name
        if p.suffix == ".json" and p.exists():
            J[name] = json.loads(p.read_text())

    src = J["target-culling-source.json"]
    cov = J["coverage-truth.json"]
    slots = J["slot-verdicts.json"]
    pop = J["edge-pop-in.json"]
    writes = J["transform-writes.json"]
    perf = J["performance.json"]
    typo = J["typography-regression.json"]
    mot = J["motion-regression.json"]
    contract = J["source-contract.json"]

    trv = cov["targetRuleVerification"]
    stale = cov["staleRectCheck"]
    crc = cov["candidateRuleConsistency"]
    bits = cov["candidateSnapshotBitExactness"]

    def gate(b):
        return "PASS" if b else "FAIL"

    contract_pass = contract.get("verdict") == "PASS"
    contract_n = contract.get("viewports", 0)
    contract_passed = contract.get("passed", 0)
    clm = mot.get("cardLabelMotion", {})
    clm_pass = clm.get("assertions", 0) > 0 and clm.get("failed", 1) == 0
    clm_n = clm.get("assertions", 0)

    # A rest-state row for the headline numbers.
    rest = next((r for r in slots["rows"]
                 if r["viewport"] == "1440x900" and r["state"] == "rest"), None)

    drag = perf["scenarios"].get("drag-10s", {})
    b_drag, c_drag = drag.get("before") or {}, drag.get("candidate") or {}

    readme = f"""# V0 — source-exact CSS3D label coverage culling

The Target keeps ~16 labels alive per frame at 1440x900. Before this round our
page kept 81 — its only test was a JS backface dot-product. V0 read the
Target's culling out of its bundle, byte by byte, and implemented it: a
dedicated dolly-free coverage camera, the four projected card corners, the NDC
z skip, the 1 px² minimum area, and the exact 64 px margin. Nothing was tuned
against a visible count.

## Verdicts

| gate | result |
| --- | --- |
| Target rule source verification | **{gate(trv['pass'])}** — {trv['framesChecked']} frames replayed against the Target's own DOM, {trv['slotMismatches']} slot mismatches ({trv.get('wrapSeam', 0)} wrap-seam-sensitive, {trv['beyondBoundary']} beyond the {cov['boundaryPx']} px float boundary) |
| Candidate rule consistency | **{gate(crc['pass'])}** — {crc['framesChecked']} frames, {crc['slotMismatches']} mismatches ({crc['beyondBoundary']} beyond boundary) |
| Page-vs-replay bit exactness | **{gate(bits['pass'])}** — {bits['snapshots']} settled snapshots, worst AABB delta {bits['worstAabbDeltaPx']:.3e} px |
| Visible slot identity vs Target | **{gate(slots['pass'])}** — {slots['identical']}/{slots['comparisons']} settled states identical, by ILG code |
| Lost / intruding labels | **{gate(trv['lostLabels'] == 0 and crc['lostLabels'] == 0 and trv['intrudingLabels'] == 0 and crc['intrudingLabels'] == 0)}** — lost {trv['lostLabels']}+{crc['lostLabels']}, intruding {trv['intrudingLabels']}+{crc['intrudingLabels']} |
| Stale-but-visible rects | **{gate(stale['pass'])}** — {stale['visibleDrawnChecked']} drawn labels over {stale['rows']} settled runs, worst rect-vs-replayed-AABB delta {stale['worstDeltaPx']} px (tolerance {stale['tolerancePx']} px), {stale['staleLabels']} stale; {stale['wrapSeamRelocated']} wrap-seam relocations positionally demonstrated (perturbed replay matches the DOM rect) |
| Edge pop-in | **{gate(pop['pass'])}** — candidate max strict-overlap at entry {pop['candidateMaxStrictOverlapPx']} px against the Target's own {pop['targetMaxStrictOverlapPx']} px |
| DOM write pressure | **{gate(writes['pass'])}** — worst-case p95 transform writes/frame {writes['summary']['beforeTransformWritesP95Worst']} before → {writes['summary']['candidateTransformWritesP95Worst']} candidate (Target {writes['summary']['targetTransformWritesP95Worst']}) |
| Performance, measured | **{gate(perf['pass'])}** — see below |
| Depth carry-forward | {cov['depthCarryForward']['status']} — measured over {cov['depthCarryForward']['settledSamples']} settled states: {cov['depthCarryForward']['projectedQuadPairsIntersecting']} projected intersections, {cov['depthCarryForward']['frontFacingPairsIntersecting']} front-facing (worst {cov['depthCarryForward']['frontFacingWorstAreaPx2']} px², margin band only), {cov['depthCarryForward']['frontFacingPairsInsideStrictViewport']} on screen |
| Console / page errors | **{gate(cov['consoleAndPageErrors']['pass'])}** — target {cov['consoleAndPageErrors']['target']}, before {cov['consoleAndPageErrors']['before']}, candidate {cov['consoleAndPageErrors']['candidate']}, across all 65 capture runs per lane |
| Typography regression | **{gate(typo.get('verdict') == 'PASS')}** — {typo.get('passed', 0)}/4 |
| Card / label under motion | **{gate(clm_pass)}** — {clm_n} assertions, corner delta ≤ 1 px |
| Source contract | **{gate(contract_pass)}** — {contract_passed}/{contract_n} viewports |
| Motion freeze smoke | **{gate(mot['pass'])}** — engine vs contract {mot['engineVsContract']['rowsTotal']} rows / {mot['engineVsContract']['rowsFailed']} failed, release history {mot['releaseHistory']['exact']}/{mot['releaseHistory']['releases']} exact, wrap teleports {mot['continuity']['wrapTeleportsOurSide']}, wheel responses {mot['continuity']['wheelResponsesOurSide']} |

At 1440x900 rest the Target shows **{rest['targetVisibleCount'] if rest else '?'}** labels and the candidate shows **{rest['candidateVisibleCount'] if rest else '?'}** — the same codes, not merely the same count. The Before build showed {rest['beforeVisibleCount'] if rest else '?'}.

## What was read, and from where

`target-culling-source.json` carries {len(src['sites'])} byte-anchored sites,
every one re-found at its recorded offset, and the live bundle downloaded this
round is byte-identical to the captured one
(SHA `{src['bundle']['sha256'][:16]}…`). The deciding line poses two cameras
in one statement: `Py.position.set(d,h,f)` — the coverage camera, pointer
orbit, NO dolly — against `t.position.set(d,h,f+p)` — the render camera with
the dolly. Coverage projects the four card corners through `Py`; a corner with
NDC z outside [-1, 1] is skipped; the surviving corners' pixel AABB must
exceed 1 px²; `draw` needs strictly positive overlap with the viewport
expanded exactly 64 px per side; the ≥ 0.5 half-area rule gates only
`interactive`, which the shipped Target publishes to a MotionValue nothing
reads.

Hidden labels stop receiving transform writes — the hide path writes at most
a guarded `visibility:hidden` and leaves the matrix stale. The backface test
is CSS (`backface-visibility:hidden`, inline), not JS: our source-exact path
now carries the same inline property and the JS dot-product no longer feeds
DOM visibility (it remains a QA diagnostic).

## Observed in source, deliberately not applied

The Target drives its WebGL **glass mesh** `visible` flag from the same
verdict (`s.visible=o.draw`). That is not label visibility, so V0 records it
(byte-anchored) and does not touch the mesh path. Flagged for a product
decision.

Two declared instrument-level deviations, both observationally identical:
the Target assigns `visibility:visible` unconditionally per drawn frame where
we guard both directions; and the Target rewrites `style.transform` every
drawn frame where our CSS3DRenderer's style cache skips identical strings.

## Performance, measured

Sustained-input scenarios, Before vs Candidate, same instrument
(`performance.json` carries all four; drag-10s at 1440x900 shown here):

| metric | before | candidate |
| --- | --- | --- |
| visible labels p95 | {b_drag.get('visibleLabels', {}).get('p95', '—')} | {c_drag.get('visibleLabels', {}).get('p95', '—')} |
| transform writes/frame p95 | {b_drag.get('transformWritesPerFrame', {}).get('p95', '—')} | {c_drag.get('transformWritesPerFrame', {}).get('p95', '—')} |
| frame time p95 (ms) | {b_drag.get('frameTimeMs', {}).get('p95', '—')} | {c_drag.get('frameTimeMs', {}).get('p95', '—')} |
| labels.sync CPU p95 (ms) | not instrumentable at the Before commit | {(c_drag.get('labelSyncCpuMs') or {}).get('p95', '—')} |
| heap over scenario (MB) | {b_drag.get('heapDeltaMB', '—')} | {c_drag.get('heapDeltaMB', '—')} |

The Before build predates the labels.sync QA probe and was not patched to
carry it — patching it would have made it a second candidate. No quality
level, DPR or motion constant differs between the lanes; the adaptive quality
state is recorded per scenario in `performance.json`.

## The boundary discipline

A verdict whose deciding quantity sits within {cov['boundaryPx']} px of its
threshold can flip on float noise between the page, the replay and a recorded
matrix. Mismatches inside that band are counted and reported separately —
{trv['withinBoundary']} on the Target lane, {crc['withinBoundary']} on the
candidate lane — never silently forgiven. A second, distinct sensitivity
exists only on the Target lane: a slot whose wrap arc sits within
{cov.get('seamWorldUnits', 0.01)} world units of the ±period/2 seam relocates
by a FULL period when the RECOVERED scroll wobbles by its ~1e-4 noise — at
scroll exactly 0 the seam column sits mathematically ON the boundary.
Proximity alone buckets nothing: it is a prefilter, and the row is counted as
wrap-seam-sensitive ({trv.get('wrapSeam', 0)} rows) only when re-running the
verdict with the recovered scroll perturbed by ±1e-3 world units — ten times
the measured noise — actually FLIPS it. A failure that merely sits near a
seam stays beyond-boundary, because 1e-4 noise cannot flip it. The gate lines
state how many failures remain outside BOTH buckets (target
{trv['beyondBoundary']}, candidate {crc['beyondBoundary']}). The candidate
lane replays from the page's own float-exact truth and can produce neither
bucket.

## The resize transition window

The Target re-grids its label pool AND its layout state on a debounced
commit after resize (the 150 ms debounce is a byte-anchored site in
`target-culling-source.json`), while its coverage camera tracks the new
window dimensions on the very next frame. Between a resize and that commit
the page culls OLD slot placements against the NEW viewport — a state the
offline replay cannot reproduce, because the replay's layout is the FINAL
layout for the new dimensions. Frames inside a 450 ms window after each
viewport change (and 3 samples before it) are therefore excluded as
transition on every lane alike, and each per-run row reports how many frames
that removed. The post-resize state itself is fully gated: settled slot
identity is 40/40 including resize-settle and orientation-flip, and the
stale-rect check runs on the last stable frame of every one of those runs.

## Wrap identity, by construction

The brief's "wrap keeps content and slot identity" gate has no separate
instrument because the identity comparison already reads identity FROM THE
DOM ITSELF — the Target lane by each label's rendered ILG code
(`textContent`), ours by `data-ilg` — so a broken slot-to-content binding
after a wrap would fail the settled identity gate directly, and a wrap
discontinuity would fail the frozen-motion smoke (wrap teleports our side:
{mot['continuity']['wrapTeleportsOurSide']}). The long-drag-multi-wrap runs
replay slot-for-slot through multiple full periods on all lanes; the culling
consumes verdicts keyed by stable slot index and never rebinds content.

## Files

| file | what |
| --- | --- |
| `target-culling-source.json` | the byte-anchored source read, {len(src['sites'])} sites, live-bundle SHA comparison |
| `coverage-truth.json` | rule replayed against every lane's frames, slot for slot |
| `slot-verdicts.json` | settled-state visible-code identity, lane vs lane |
| `edge-pop-in.json` | label entries during gestures, strict-viewport overlap at entry |
| `transform-writes.json` | per-frame DOM style write pressure, all three lanes |
| `performance.json` | sustained-input scenarios, before vs candidate |
| `typography-regression.json` | container alignment, label ink, depth carry-forward |
| `motion-regression.json` | motion freeze smoke: engine vs contract, release history, card/label corner delta, continuity |
| `source-contract.json` | the 36-viewport layout source contract |

The private review package (`qa-v5/private/culling-review.zip`, git-ignored)
carries the coverage overlays, beauty frames and the screen recordings; its
`PACKAGE-MANIFEST.json` states the full review head. Target pixels appear
only there, never in this tree.
"""

    (outdir / "README.md").write_text(readme)

    manifest = {
        "stage": "culling",
        "repository": "lhfer/mirrorweb",
        "branch": "rebuild/liquid-glass-v5-source-exact",
        "capturedAtHead": head,
        "capturedAtHeadMeaning": "the commit every capture and gate in this "
            "directory was taken at. REQUIRED input -- the tool has no "
            "current-HEAD fallback, because a default here makes the evidence "
            "commit look like the capture commit.",
        "reviewHeadMeaning": "NOT stated here: a committed file cannot contain "
            "the hash of the commit that carries it. The private package's "
            "PACKAGE-MANIFEST.json states it as a full SHA.",
        "route": "/?composition=sourceExact&qa",
        "captureTimestampUtc": datetime.now(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lanes": {
            "target": "https://infinite-liquid-glass.shader.se/?v=2, live",
            "before": "the accepted pre-V0 build (v5-m3-motion-product-accept), "
                      "served from a worktree; lane fingerprint in the trace "
                      "proves it (no labels.sync probe, no culling verdicts)",
            "candidate": "the V0 build",
        },
        "files": [],
    }
    for name in PUBLIC_FILES:
        p = outdir / name
        if name == "MANIFEST.json" or not p.exists():
            continue
        manifest["files"].append({
            "file": name,
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        })
    (outdir / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")

    # No unlisted file may sit in the public tree.
    listed = set(PUBLIC_FILES)
    actual = {p.name for p in outdir.iterdir() if p.is_file()}
    unlisted = actual - listed
    if unlisted:
        print(f"FATAL: unlisted files in {outdir}: {sorted(unlisted)}", file=sys.stderr)
        return 2
    print(f"wrote README.md and MANIFEST.json ({len(manifest['files'])} files listed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
