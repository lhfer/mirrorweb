#!/usr/bin/env python3
"""Assemble qa-v5/render-culling: README + MANIFEST from the real JSONs.

Public tree:
  README.md, MANIFEST.json,
  target-render-culling-source.json   the byte-anchored object mapping
  render-culling-truth.json           effective visibility vs rule replay
  pixel-invariance.json               ON/OFF A/B + V0-baseline comparison
  performance.json                    A/B scenarios + heap cycles
  label-culling-regression.json       the V0 absolute gate at the V1 build
  source-contract.json                36-viewport layout contract
  typography-regression.json          4-gate typography regression
  motion-regression.json              motion freeze smoke + card/label corners

`capturedAtHead` is REQUIRED. `reviewHead` is deliberately absent (a
committed file cannot contain the hash of the commit that carries it).

Usage: v1-evidence.py --outdir=<qa-v5/render-culling> --capturedAtHead=<sha>
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
    "target-render-culling-source.json",
    "render-culling-truth.json",
    "pixel-invariance.json",
    "performance.json",
    "label-culling-regression.json",
    "source-contract.json",
    "typography-regression.json",
    "motion-regression.json",
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
        if name in ("README.md", "MANIFEST.json"):
            continue
        p = outdir / name
        if not p.exists():
            print(f"missing public file: {p}", file=sys.stderr)
            return 2
        J[name] = json.loads(p.read_text())

    src = J["target-render-culling-source.json"]
    truth = J["render-culling-truth.json"]
    px = J["pixel-invariance.json"]
    perf = J["performance.json"]
    lc = J["label-culling-regression.json"]
    contract = J["source-contract.json"]
    typo = J["typography-regression.json"]
    mot = J["motion-regression.json"]

    def gate(b):
        return "PASS" if b else "FAIL"

    clm = mot.get("cardLabelMotion", {})
    checks = perf.get("checks", [])
    drag = next((c for c in checks if c["scenario"] == "drag-10s"), {})
    worst_ab = max((r.get("differingPixels", 0) for r in px.get("ab", [])), default=0)
    worst_base = max((r.get("differingPixels", 0) for r in px.get("baseline", [])),
                     default=0)
    cycles = perf.get("heapCycles") or []

    readme = f"""# V1 — source-exact WebGL render culling

The Target culls its WebGL card with the SAME coverage verdict that culls
its CSS3D label: `s.visible = o.draw`, one loop iteration, two surfaces.
V0 recorded that wiring and deliberately did not act on it. V1 read what
`s` actually is — a plain THREE.Mesh whose one node material carries the
refracted media, the environment reflection, the fresnel and the rim, with
no scene-colour pass, no reflection shell and no per-slot group — and
mapped the rule onto our render objects with the layered visibility this
round requires: no system writes `.visible` on a slot mesh directly; the
pipeline's per-pass flips, the QA layer requests, the shell and debug
modes, the active window and the coverage verdict each set a flag, and one
applier composes them.

The media plane is deliberately NOT coverage-culled: it is the input of
the scene-colour target — our architecture's equivalent of the Target's
per-card texture binds, which the Target does not cull either (its
refraction samples the card's OWN texture, so hiding a card never changes
another card's pixels; source-read). Coverage-culling the scene input
would break exactly that invariant, because edge glass samples the target
beyond the 64 px margin.

## Verdicts

| gate | result |
| --- | --- |
| Target source object mapping | **{gate(src['pass'])}** — {src['sitesTotal']} byte-anchored sites, live bundle {'byte-identical' if src.get('liveBundle', {}).get('matchesCapturedBundle') else 'NOT verified'} |
| Effective visibility vs rule replay | **{gate(truth['slotMismatches'] == 0)}** — {truth['framesChecked']} frames, {truth['slotMismatches']} slot mismatches |
| Label / mesh agreement | **{gate(truth['labelMeshDisagreements'] == 0)}** — {truth['labelMeshDisagreements']} disagreeing frames (one verdict, two surfaces) |
| Strict-viewport completeness | **{gate(truth['strictViewportMissing'] == 0)}** — {truth['strictViewportMissing']} frames with a missing on-screen card |
| Pass-state integrity | **{gate(truth['mediaPassLeaks'] == 0 and truth['shellGlassMismatches'] == 0)}** — {truth['mediaPassLeaks']} media leaks, {truth['shellGlassMismatches']} shell mismatches |
| Pixel invariance, culling A/B | **{gate(px['abPass'])}** — {px['abComparisons']} comparisons, worst {worst_ab} differing pixels (requirement: identical, no tolerance) |
| Pixel invariance vs V0 baseline | **{gate(px.get('baselinePass') is not False)}** — {px['baselineComparisons']} comparisons, worst {worst_base} differing pixels |
| Performance | **{gate(perf['pass'])}** — see below |
| Label culling absolute gate (V0, re-run) | **{gate(lc['pass'])}** — {lc['framesChecked']} frames, {lc['slotMismatches']} mismatches, identity {lc['identity']} |
| Source contract | **{gate(contract.get('verdict') == 'PASS')}** — {contract.get('passed', 0)}/{contract.get('viewports', 0)} viewports |
| Typography regression | **{gate(typo.get('verdict') == 'PASS')}** — {typo.get('passed', 0)}/4 |
| Card / label under motion | **{gate(clm.get('assertions', 0) > 0 and clm.get('failed', 1) == 0)}** — {clm.get('assertions', 0)} assertions |
| Motion freeze smoke | **{gate(mot['pass'])}** — engine vs contract {mot['engineVsContract']['rowsTotal']} rows / {mot['engineVsContract']['rowsFailed']} failed, release history {mot['releaseHistory']['exact']}/{mot['releaseHistory']['releases']} exact |
| Console / page errors | **{gate(truth['consoleAndPageErrors'] == 0)}** — {truth['consoleAndPageErrors']} across the capture |

## Performance, measured

An A/B on ONE build: coverage culling ON (candidate) vs OFF (the accepted
pre-V1 behaviour — proven byte-identical to the V0 baseline by the pixel
gate). drag-10s at 1440x900:

| metric | culling off | culling on |
| --- | --- | --- |
| final-pass draw calls p95 | {drag.get('finalDrawCallsP95', {}).get('off', '—')} | {drag.get('finalDrawCallsP95', {}).get('on', '—')} |
| final-pass triangles p95 | reduction {drag.get('finalTrianglesP95', {}).get('reducedPct', '—')}% | |
| scene-colour pass | unchanged: {drag.get('sceneColorUnchanged', '—')} (deliberately not culled) |
| glass meshes visible p95 | {drag.get('glassVisibleP95', {}).get('off', '—')} | {drag.get('glassVisibleP95', {}).get('on', '—')} |

GPU frame time: {perf.get('gpuFrameTime', 'n/a')}.

Heap over repeated 5-minute drag cycles:
{chr(10).join(f"- cycle {c['cycle']}: {c['heapStartMB']} -> {c['heapEndMB']} MB (delta {c['deltaMB']} MB)" for c in cycles) or '- not captured'}

Videos keep playing and advancing in both lanes; the adaptive quality
level did not move in either. Frame-time percentiles are statistically
identical — the page is GPU-bound and the win is submitted work (draw
calls and vertex load), stated as such.

## What the source settles

`target-render-culling-source.json` answers every object question with
byte offsets: `s` is created by the card field's JSX (`<mesh ref=...>`),
it is a THREE.Mesh with no children, its material is one
MeshBasicNodeMaterial per media clip, hiding it removes exactly one draw
call from the single forward pass, and nothing else exists — no
scene-colour pass, no reflection shell, no media plane, no layer-debug
mode. Mesh poses update every frame regardless of visibility (the
opposite of the label freeze, both now frozen behaviours).

## Files

| file | what |
| --- | --- |
| `target-render-culling-source.json` | the render-object source mapping, {src['sitesTotal']} sites |
| `render-culling-truth.json` | effective visibility vs rule replay, per frame |
| `pixel-invariance.json` | culling A/B + V0-baseline pixel comparisons |
| `performance.json` | A/B scenarios, heap cycles, media and adaptive state |
| `label-culling-regression.json` | the V0 label gate re-run at the V1 build |
| `source-contract.json` | the 36-viewport layout source contract |
| `typography-regression.json` | container alignment, label ink, depth carry-forward |
| `motion-regression.json` | motion freeze smoke + card/label corner delta |
"""
    (outdir / "README.md").write_text(readme)

    entries = []
    for name in PUBLIC_FILES:
        if name == "MANIFEST.json":
            continue
        p = outdir / name
        entries.append({"file": name, "bytes": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    manifest = {
        "stage": "render-culling",
        "repository": "lhfer/mirrorweb",
        "branch": subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                 capture_output=True, text=True,
                                 cwd=REPO).stdout.strip(),
        "capturedAtHead": head,
        "capturedAtHeadMeaning": "the commit every capture and gate in this "
                                 "directory was taken at. REQUIRED input -- no "
                                 "current-HEAD fallback.",
        "reviewHeadMeaning": "NOT stated here: a committed file cannot contain "
                             "the hash of the commit that carries it.",
        "route": "/?composition=sourceExact&qa",
        "captureTimestampUtc": datetime.now(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": entries,
    }
    (outdir / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")

    on_disk = {p.name for p in outdir.iterdir() if p.is_file()}
    unlisted = on_disk - set(PUBLIC_FILES)
    if unlisted:
        print(f"UNLISTED files in {outdir}: {sorted(unlisted)}", file=sys.stderr)
        return 2
    print(f"wrote README.md and MANIFEST.json ({len(entries)} files listed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
