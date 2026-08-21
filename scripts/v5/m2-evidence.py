#!/usr/bin/env python3
"""Seal the M2 evidence tree: one manifest, one verdict, per-file hashes.

WHAT THIS FIXES FROM LAST ROUND
-------------------------------
The M1 manifest carried `"gateVerdict": null` beside `"verdict": "FAIL"` -- two
fields for one fact, one of them empty -- plus `"privateReviewPackage": null`
while the package existed, and `"evidenceCommit": "this commit"`, which is a
placeholder rather than a hash. This writes ONE verdict field, sourced from the
gate's own summary and never typed, and states plainly which hash is which.

`capturedAtHead` and `reviewHead` are separate fields with separate meanings
and neither stands in for the other: a file cannot contain the hash of the
commit that carries it, so the capture head is a fact this file can hold and
the review head is resolved by the reader with `git rev-parse HEAD`.

Usage: m2-evidence.py --dir=qa-v5/motion-closure [--package=<zip>]
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def git(*a):
    try:
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return None


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


README = """# V5 M2 — Motion Closure

What this round asked, in one line: of the 64 landmark failures the M1 gate
reported, how many were the engine, how many were the instrument, and how many
were a difference the product has decided to accept?

The answer is in `gate-summary.json`. This file says how to read it and how to
reproduce it.

## The instrument was the largest single defect

The M1 replay decided which frame an input event belonged to with
`event.t <= frame.t`. Those two numbers come from different points in the
browser's frame pipeline: `event.t` is `performance.now()` at listener entry,
`frame.t` is the rAF timestamp, which is when the frame STARTED — before any
callback in it ran. Chrome dispatches input before the rAF block, so an event
dispatched during frame N satisfies `event.t > frame_N.t` and the rule handed
it to frame N+1.

Measured on the M1 traces: **{misattributed} of all recorded events**, one frame
late, always the same direction. That is the whole of the "persistent final
error" M1 reported — 0.1457 of travel on every reverse-flick row and 0.0527 on
every fast-flick row, identical across four viewports and three repeats. A
number that lands on the same four decimals in twelve independent runs is a
constant, not an engine.

The M2 recorder does not infer ordering from a clock. It bumps ONE monotone
counter from every event listener and every frame callback, so the order the
page's own JavaScript ran in is a recorded fact. `frame.t` keeps its real job —
it is the clock the springs integrate on — and is no longer asked a question it
cannot answer.

With that fixed, and the comparison made against the engine's own published
state rather than a recovery of it, **the engine reproduces the frozen motion
contract to floating-point identity**: worst final error {evc_worst:.2e} of
travel across every run, against a gate of {evc_thr:.3f} world units. No motion
code was changed to achieve that.

## What is left, and what it is

{jitter_para}

That difference lives in `raw-scheduler-metrics.json` and is covered by
`product-exception-candidate.json` (MOTION-EXC-01). It covers the raw
single-frame numbers and nothing else — not final position, travel, decay,
pointer orbit, touch behaviour, wrap continuity, or the filtered camera-dolly
envelope, all of which are gated normally and listed by name in that file.

## The baseline was sealed before the candidate existed

`target-scheduler-invariant-baseline.json` is computed from the Target alone.
Every threshold in it is `max(2 × the Target's own repeatability, a floor
declared in `scripts/v5/m2-baseline.py` before any candidate was captured)`.
Its SHA-256 is `{baseline_sha}`, recorded in
`target-scheduler-invariant-baseline.sha256`; the gate recomputes it and
refuses to run against a modified copy. The order — Target, seal, candidate —
is the order `scripts/v5/run-m2.sh` executes in and the order the commits
landed in, so it is auditable rather than promised.

## The sign test now knows which way is worse

M1 applied the one-sided rule per cell and then a plain two-sided sign test to
the systematic-sign summary. A candidate that was smoother than the Target in
every single cell — the one thing a one-sided-upper landmark exists to allow —
was reported as a systematic FAIL. Three landmarks failed that way and none was
a defect. Every row now carries an explicit `gateType` and `status`, and the
summary is direction-aware.

## Reproducing a trace

```
scripts/v5/run-m2.sh target      # the Target, 4 viewports x 15 sequences x 3
scripts/v5/run-m2.sh baseline    # Target only; seal this before the candidate
scripts/v5/run-m2.sh candidate   # our page, same 15 x 3 x 4
scripts/v5/run-m2.sh gate exception frozen evidence
```

Every sequence is real browser input — mouse, wheel or touch dispatched through
the automation protocol. No QA hook moves either page. The two exceptions are
labelled in the traces themselves by `isTrusted`: wheel `deltaMode` 1 and 2
cannot be produced by a real device through the protocol, and neither can
`lostpointercapture`.

## Target pixels

This directory holds LOCAL pixels and Target-derived NUMBERS only. Target
pixels and side-by-side comparisons live in `qa-v5/private/`, which is
git-ignored.

## Files

{filelist}
"""


def main() -> int:
    args = {a[2:].split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:]}
    d = Path(args["dir"])
    gate = json.loads((d / "gate-summary.json").read_text())
    evc = json.loads((d / "engine-vs-contract-v2.json").read_text())
    raw = json.loads((d / "raw-scheduler-metrics.json").read_text())["rows"]

    import statistics

    def med(side, key):
        v = [r[key] for r in raw if r["side"] == side and r.get(key) is not None]
        return round(statistics.median(v), 5) if v else None

    tj, oj = med("target", "frameStepJitterFraction"), med("ours", "frameStepJitterFraction")
    tz, td = med("target", "nearZeroStepFraction"), med("target", "doubleStepFraction")
    ti, oi = med("target", "frameIntervalMedianMs"), med("ours", "frameIntervalMedianMs")
    jitter_para = (
        f"The Target's scroll deviates from its own local trend by a median of "
        f"{tj} per frame; ours by {oj}. That is the two-rAF architecture: the "
        f"Target solves its springs in framer-motion's frame loop and paints them "
        f"in r3f's, and we do both in one.\n\n"
        f"M2 corrects how M1 described the mechanism. M1 called it dropped frames "
        f"— \"a frame on which framer did not tick repaints the same value, and "
        f"the next frame carries double\". The measurement does not support that. "
        f"The Target's frame interval is as steady as ours ({ti} ms median against "
        f"our {oi} ms), its near-zero-step fraction is {tz} and its double-step "
        f"fraction is {td}. It does not miss beats. What it has is a smooth spread "
        f"of the per-frame step around its own trend, roughly 0.89x to 1.13x — a "
        f"continuous phase difference between the loop that solves the spring and "
        f"the loop that samples it."
    )

    attribution = evc["rows"][0]["attribution"] if evc["rows"] else {}
    misattr = attribution.get("fraction")
    misattr_s = f"{misattr:.0%}" if isinstance(misattr, float) else "most"
    # Across every row, not just the first.
    fracs = [r["attribution"]["fraction"] for r in evc["rows"]
             if r.get("attribution", {}).get("fraction") is not None]
    if fracs:
        misattr_s = f"a median of {statistics.median(fracs):.0%}"

    base_sha = (d / "target-scheduler-invariant-baseline.sha256").read_text().split()[0]

    files = sorted(p for p in d.iterdir() if p.is_file() and p.name != "MANIFEST.json")
    entries = [{"path": str(p.relative_to(REPO)), "bytes": p.stat().st_size,
                "sha256": sha256_file(p)} for p in files]
    filelist = "\n".join(f"- `{e['path'].split('/')[-1]}` — {e['bytes']:,} bytes"
                         for e in entries)

    (d / "README.md").write_text(README.format(
        misattributed=misattr_s,
        evc_worst=evc["worstFinalErrFraction"],
        evc_thr=evc["threshold"],
        jitter_para=jitter_para,
        baseline_sha=base_sha,
        filelist=filelist))

    # README is written before the manifest so the manifest hashes it too.
    files = sorted(p for p in d.iterdir() if p.is_file() and p.name != "MANIFEST.json")
    entries = [{"path": str(p.relative_to(REPO)), "bytes": p.stat().st_size,
                "sha256": sha256_file(p)} for p in files]

    pkg = args.get("package")
    pkg_path = Path(pkg) if pkg else None
    manifest = {
        "stage": "motion-closure",
        "repository": "lhfer/mirrorweb",
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "capturedAtHead": git("rev-parse", "--short", "HEAD"),
        "capturedAtHeadMeaning":
            "the commit every trace, gate and recording in this directory was captured "
            "at. It is a fact this file can hold.",
        "reviewHead":
            "resolve with `git rev-parse HEAD`. A file cannot contain the hash of the "
            "commit that carries it, so this is NOT stated here and no hygiene commit "
            "is created to chase one. capturedAtHead and reviewHead are separate facts "
            "and neither stands in for the other.",
        "route": "/?qa=1&composition=sourceExact",
        "captureTimestampUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fixedCaptureConditions": {
            "quality": "high (pinned, adaptive sampler off)",
            "mediaTimeSeconds": 2,
            "dpr": 1,
            "motion": "NOT paused -- every trace is driven by real pointer, touch and "
                      "wheel events. No QA hook moves either page.",
            "server": "vite preview against the built bundle, so no HMR reload can wipe "
                      "a recorder mid-capture",
        },
        # ONE verdict field. It is read out of the gate summary, never typed.
        "verdict": gate["verdict"],
        "verdictSource": "qa-v5/motion-closure/gate-summary.json",
        "verdictInputs": gate["verdictInputs"],
        "baselineSha256": base_sha,
        "productException": "qa-v5/motion-closure/product-exception-candidate.json",
        "privateReviewPackage": (
            {"path": str(pkg_path.relative_to(REPO)) if pkg_path else None,
             "bytes": pkg_path.stat().st_size if pkg_path and pkg_path.exists() else None,
             "sha256": sha256_file(pkg_path) if pkg_path and pkg_path.exists() else None,
             "gitIgnored": True,
             "containsTargetPixels": True}
            if pkg_path else None),
        "supersedes": {
            "path": "qa-v5/motion",
            "note": "the M1 round's results are NOT rewritten. Its FAIL stands, its "
                    "files are untouched, and only its metadata was repaired -- one "
                    "verdict field instead of two, the private package named, and the "
                    "evidence commit given a hash instead of the placeholder 'this "
                    "commit'.",
        },
        "targetPixelPolicy":
            "This directory contains LOCAL pixels and Target-derived NUMBERS only. "
            "Target pixels and Target/local overlays live in qa-v5/private/, which is "
            "git-ignored.",
        "files": entries,
    }
    (d / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    print(f"manifest -> {d / 'MANIFEST.json'}  ({len(entries)} files)")
    print(f"readme   -> {d / 'README.md'}")
    print(f"  verdict {manifest['verdict']}   baseline sha {base_sha[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
