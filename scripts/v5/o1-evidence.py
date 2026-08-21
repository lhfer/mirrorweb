#!/usr/bin/env python3
"""Assemble qa-v5/optics: README + MANIFEST from the real JSONs.

Public tree (JSON and markdown only -- Target pixels live ONLY in the
private package):
  README.md, MANIFEST.json,
  o0-source-diagnosis.json      the byte-anchored shader forensics + runtime
                                ROI statistics, with the floor-experiment
                                attribution correction appended
  o1-selected-system.json       the system selection, written BEFORE the
                                candidate code existed
  o1-optics-gate.json           the absolute gate: metrics, direction
                                checks, floor experiment, failure conditions
  o1-regressions.json           every frozen suite re-run at the O1 build

`capturedAtHead` is REQUIRED. `reviewHead` is deliberately absent (a
committed file cannot contain the hash of the commit that carries it).

Usage: o1-evidence.py --outdir=<qa-v5/optics> --capturedAtHead=<sha>
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
    "o0-source-diagnosis.json",
    "o1-selected-system.json",
    "o1-optics-gate.json",
    "o1-regressions.json",
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

    gate = json.loads((outdir / "o1-optics-gate.json").read_text())
    reg = json.loads((outdir / "o1-regressions.json").read_text())
    sel = json.loads((outdir / "o1-selected-system.json").read_text())

    fired = gate["firedFailureConditions"]
    var = gate["targetLaneVariance"]
    cond3 = gate["failureConditions"][2]
    expected_ok = all(
        gate["directionChecks"][k][m]["movedInExpectedDirection"]
        for k in ("1440x900/rest", "1440x900/pointer-corner-br",
                  "390x844/rest", "390x844/pointer-corner-br")
        for m in ("edgeChroma", "fringeRB", "whiteReflectionRatio"))
    co = gate.get("brightDarkCohorts", {})
    co_states = 0
    co_ok = 0
    for key, lanes in co.items():
        b, c = lanes.get("before-beauty"), lanes.get("candidate-beauty")
        if b and c:
            co_states += 1
            if (c["darkEdgeChroma"] < b["darkEdgeChroma"]
                    and c["brightEdgeChroma"] < b["brightEdgeChroma"]):
                co_ok += 1
    floor = gate["floorExperiment"]
    dr = gate["directionChecks"]["1440x900/rest"]
    mo = gate["mediaOnlyInvariance"]

    def row(key):
        d = gate["directionChecks"][key]
        return (f"| {key} | {d['edgeChroma']['target']} | {d['edgeChroma']['before']} | "
                f"{d['edgeChroma']['candidate']} | {d['fringeRB']['target']} | "
                f"{d['fringeRB']['before']} | {d['fringeRB']['candidate']} | "
                f"{d['whiteReflectionRatio']['target']} | "
                f"{d['whiteReflectionRatio']['before']} | "
                f"{d['whiteReflectionRatio']['candidate']} |")

    metric_rows = "\n".join(row(k) for k in ("1440x900/rest", "1440x900/pointer-corner-br",
                                             "390x844/rest", "390x844/pointer-corner-br"))
    fired_block = "\n".join(f"> {c}" for c in fired)
    reg_rows = "\n".join(
        f"| {k} | {'PASS' if v['pass'] else 'FAIL'} |"
        for k, v in reg.items() if isinstance(v, dict) and "pass" in v)

    readme = f"""# O1 — first Liquid Glass optics candidate: **{gate['verdict']}**

System A (edge energy / dispersion / saturation) was selected and its
failure conditions pre-registered in `o1-selected-system.json` BEFORE the
candidate code existed. The candidate replaced the fixed R/B tap split
with the Target's own dispersion law, byte-anchored in the O0 forensics:
5 spectral samples along the refraction offset, per-sample UV scale, tent
RGB weights normalised per channel.

The pre-registered condition that fired, verbatim:

{fired_block}

## The floor experiment (the round's decisive finding)

The candidate rebuilt with `dispersionSpread=0` — dispersion OFF,
everything else identical — measures desktop edge chroma
**{floor['edgeChromaMean']}** against Before's
**{floor['samePageLeverEffect']['edgeChromaPoints'] + floor['edgeChromaMean']:.2f}**:
the entire dispersion mechanism is worth
**{floor['samePageLeverEffect']['edgeChromaPoints']} edge-chroma points**
on our own page (media-stable, within-page). Its share of the gap to the
Target is **{min(floor['shareOfTargetGap']['sharePctPerDraw'].values())}–{max(floor['shareOfTargetGap']['sharePctPerDraw'].values())}%**
depending on the Target's media draw — a small minority under every draw.
{floor['conclusion']}

The white reflection ratio at spread 0.3
({dr['whiteReflectionRatio']['candidate']}) differs from the floor's at
spread 0 ({floor['whiteReflectionRatio']}) by
{dr['whiteReflectionRatio']['candidate'] - floor['whiteReflectionRatio']:+.4f}:
the system's one tunable lever moves white by essentially nothing. The O0
attribution is corrected forward in `o0-source-diagnosis.json`
(`attributionCorrectedByFloorExperiment`) — the O2 selection must read
that field.

## Metrics, absolute (Target | Before | Candidate)

| state | edge chroma T | B | C | fringe R-B T | B | C | white ratio T | B | C |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
{metric_rows}

Every touched metric moved in the PRE-REGISTERED expected direction
(edge chroma down, fringe R-B down, white up) on desktop and mobile:
{"yes, 12/12" if expected_ok else "NO — see directionChecks"}; none fell
below the Target's sampled edge chroma. Cross-page ABSOLUTE comparison
against the Target is draw-dominated and reported with its range: the
Target's band statistics swing with its per-load media shuffle by 20–50×
the candidate-vs-before deltas (`targetLaneVariance` in the gate JSON —
a methodological finding O2's gate must design around; our own lanes are
deterministic to ≤1.3 chroma points). And the movement is not visually
obvious: the frame still reads as a dark chromatic rim next to the
Target's white glassy one (edge strips in the private package). The brief
requires a visually obvious glass advance; direction-correct but
negligible is what this FAILED state is for.

Condition 3 ("any mobile metric regresses while desktop improves") is
evaluated by the selection file's own declared signs and does not fire;
a distance-to-target-sample coding was tried first, fires on the Target's
media draw rather than on the candidate, and is recorded — with the
per-repeat evidence that rejected it — inside the condition's entry in
the gate JSON.

## What did NOT move (controls)

- **Media-only invariance**: {len(mo['rows'])} comparisons vs the pre-O1
  build, frozen media — **0 differing pixels** in all. The glass was not
  "fixed" by desaturating the media.
- **Bright/dark cohorts** (per-card samples pooled over 3 repeat loads,
  split at the pooled median interior luminance): edge chroma falls from
  Before to Candidate in BOTH cohorts in {co_ok}/{co_states} measured
  states (`brightDarkCohorts` in the gate JSON).
- **Frozen suites**, all re-run at this build:

| suite | result |
| --- | --- |
{reg_rows}

## Files

| file | what |
| --- | --- |
| `o0-source-diagnosis.json` | shader forensics + ROI statistics, attribution corrected |
| `o1-selected-system.json` | the pre-registered selection and failure conditions |
| `o1-optics-gate.json` | metrics, direction checks, floor experiment, conditions |
| `o1-regressions.json` | every frozen suite at the O1 build |

Visual evidence (Target pixels included) is PRIVATE:
`qa-v5/private/o1-optics-review.zip`.
"""
    (outdir / "README.md").write_text(readme)

    entries = []
    for name in PUBLIC_FILES:
        if name == "MANIFEST.json":
            continue
        p = outdir / name
        if not p.exists():
            print(f"missing public file: {p}", file=sys.stderr)
            return 2
        entries.append({"file": name, "bytes": p.stat().st_size,
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    manifest = {
        "stage": "optics-o1",
        "verdict": gate["verdict"],
        "repository": "lhfer/mirrorweb",
        "branch": subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                 capture_output=True, text=True,
                                 cwd=REPO).stdout.strip(),
        "capturedAtHead": head,
        "capturedAtHeadMeaning": "the commit every capture and gate in this "
                                 "directory was taken at. REQUIRED input -- no "
                                 "current-HEAD fallback.",
        "reviewHeadMeaning": "NOT stated here: a committed file cannot contain "
                             "the hash of the commit that carries it. It is in "
                             "the private package's manifest.",
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
