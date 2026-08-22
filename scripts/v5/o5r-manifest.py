#!/usr/bin/env python3
"""§十五 -- the public O5R manifest, and the check that the tree matches it.

Two failure modes matter and both are checked here rather than trusted: a file
§十五 names that is missing, and a file in the tree that §十五 does not name.
The second is the one that slips through -- a stray intermediate left behind in
an evidence tree is indistinguishable, to a reader, from evidence.

The tree is also scanned for Target pixels. §十五 requires that the public tree
carry none, and "we did not copy any" is a weaker statement than "there are no
image files here at all".

Output: qa-v5/optics-o5r/MANIFEST.json
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
QA = REPO / "qa-v5/optics-o5r"

REQUIRED = [
    "README.md",
    "MANIFEST.json",
    "o5-product-review.json",
    "instrument-contract.json",
    "instrument-tests.json",
    "hdr-radiance-audit.json",
    "source-env-correction.json",
    "grayscale-v2.json",
    "saturated-edge-v2.json",
    "refraction-compression-v2.json",
    "interior-fidelity-v2.json",
    "silhouette-v2.json",
    "portrait-closure.json",
    "target-repeatability.json",
    "original-o5-gate-regression.json",
    "corrected-product-gate.json",
    "pipeline-performance-v2.json",
    "regressions.json",
]
# Written by the gate as one file per topic, plus the two identity records the
# round rests on. Named here so "no unlisted files" stays a real check.
ALSO_EXPECTED = [
    "control-identity.json", "sealed-lane-identity.json",
    "reflection-band.json", "dark-side-luma.json",
    "white-reflection-ratio.json", "own-media-isolation.json",
    "pointer-path.json", "temporal-continuity.json",
    "mobile-consistency.json", "full-frame-readiness.json",
]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".mp4", ".webm", ".gif", ".webp",
                  ".avif", ".bmp", ".tiff"}


def main() -> int:
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    present = sorted(p.name for p in QA.iterdir() if p.is_file())
    named = set(REQUIRED) | set(ALSO_EXPECTED)
    # MANIFEST.json is this file. It is required and it is written below, so
    # checking for it before writing it would fail on every first run.
    missing = [f for f in REQUIRED
               if f not in present and f != "MANIFEST.json"]
    unlisted = [f for f in present if f not in named]
    images = [f for f in present if Path(f).suffix.lower() in IMAGE_SUFFIXES]

    files = []
    for name in present:
        if name == "MANIFEST.json":
            continue
        p = QA / name
        files.append({"file": name, "bytes": p.stat().st_size,
                      "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})

    gate = json.loads((QA / "corrected-product-gate.json").read_text())
    doc = {
        "what": "§十五 -- the public O5R evidence tree. Numbers, source anchors "
                "and verdicts only.",
        "round": "O5R — target-source optical body product closure",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": head,
        "correctedGate": {"verdict": gate["gate"], "counts": gate["counts"],
                          "total": gate["total"]},
        "verification": {
            "requiredFiles": len(REQUIRED),
            "missing": missing,
            "unlisted": unlisted,
            "imageOrVideoFiles": images,
            "publicTreeHasNoTargetPixels": not images,
            "note": "the tree carries no image or video files at all, which is "
                    "a stronger statement than 'no Target renditions were "
                    "copied'. Target pixels live only in "
                    "qa-v5/private/o5r-optical-body-review.zip.",
            "pass": not missing and not unlisted and not images,
        },
        "fileCount": len(files),
        "files": files,
    }
    (QA / "MANIFEST.json").write_text(json.dumps(doc, indent=1))
    v = doc["verification"]
    print(f"{len(files)} files, missing {len(missing)}, unlisted "
          f"{len(unlisted)}, images {len(images)}")
    if missing:
        print("  MISSING:", ", ".join(missing))
    if unlisted:
        print("  UNLISTED:", ", ".join(unlisted))
    print(f"-> {QA}/MANIFEST.json  {'PASS' if v['pass'] else 'FAIL'}")
    return 0 if v["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
