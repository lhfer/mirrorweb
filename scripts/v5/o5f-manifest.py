#!/usr/bin/env python3
"""O5F §十五 -- the public O5F manifest, and the check that the tree matches.

Same two failure modes as every round: a file §十五 names that is missing,
and a file in the tree §十五 does not name. The tree is also scanned for
image or video suffixes -- the public tree must carry no Target pixels, and
"no image files at all" is the stronger statement.

`portrait-source-code.json` is conditional: it exists exactly when §十一's
one authorised correction was made, and the manifest accepts either state
rather than defaulting one of them to an error.

Output: qa-v5/optics-o5f/MANIFEST.json
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
QA = REPO / "qa-v5/optics-o5f"

REQUIRED = [
    "README.md",
    "MANIFEST.json",
    "o5r-product-review.json",
    "material-cache-contract.json",
    "material-cache-identity.json",
    "material-cache-stress.json",
    "portrait-term-decomposition.json",
    "clip-index-attribution.json",
    "target-mobile-tier.json",
    "reflection-direction.json",
    "output-transform.json",
    "roi-isolation.json",
    "portrait-closure.json",
    "original-o5-gate-regression.json",
    "o5r-gate-regression.json",
    "regressions.json",
]
ALSO_EXPECTED = [
    "control-identity.json",       # the sealed aggregator's schema view
    "sealed-lane-identity.json",
    "portrait-source-code.json",   # exists iff the §十一 correction was made
]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".mp4", ".webm", ".gif", ".webp",
                  ".avif", ".bmp", ".tiff"}


def main() -> int:
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    present = sorted(p.name for p in QA.iterdir() if p.is_file())
    named = set(REQUIRED) | set(ALSO_EXPECTED)
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

    stress = json.loads((QA / "material-cache-stress.json").read_text())
    ident = json.loads((QA / "material-cache-identity.json").read_text())
    doc = {
        "what": "§十五 -- the public O5F evidence tree. Numbers, source "
                "anchors and verdicts only.",
        "round": "O5F — material cache and portrait source reconciliation",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": head,
        "phaseA": {"identity": ident["verdict"],
                   "stress": stress["verdict"],
                   "stressChecks": f"{stress['passed']}/{stress['total']}"},
        "verification": {
            "requiredFiles": len(REQUIRED),
            "missing": missing,
            "unlisted": unlisted,
            "imageOrVideoFiles": images,
            "publicTreeHasNoTargetPixels": not images,
            "note": "the tree carries no image or video files at all. "
                    "Target pixels live only in "
                    "qa-v5/private/o5f-optical-body-review.zip.",
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
