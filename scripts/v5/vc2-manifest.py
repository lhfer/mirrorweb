#!/usr/bin/env python3
"""VC2 §十 -- the public manifest, and the check that the tree obeys its limits.

Public evidence is capped at ten files and may carry no images. This walks the
published directory, hashes every file, reads each one's own verdict out of it
rather than restating one, and fails if the tree broke a limit.

Usage: vc2-manifest.py [--dir=qa-v5/visual-convergence]
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".webm"}


def git(*a) -> str:
    return subprocess.run(["git", "-C", str(REPO), *a],
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    d = REPO / args.get("dir", "qa-v5/visual-convergence")
    out_p = d / "MANIFEST.json"

    files = sorted(p for p in d.iterdir() if p.is_file() and p.name != "MANIFEST.json")
    verdicts = {}
    for p in files:
        if p.suffix != ".json":
            continue
        try:
            j = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        for k in ("verdict", "grade"):
            if k in j:
                verdicts[p.name] = j[k]["value"] if isinstance(j.get(k), dict) else j[k]
                break

    head = git("rev-parse", "HEAD")
    doc = {
        "round": "MirrorWeb V5 -- Visual Convergence Sprint 2",
        "reviewCandidateUrl": "http://127.0.0.1:5293/?review=target",
        "reviewCurrentUrl": "http://127.0.0.1:5293/?review=current",
        "howToServe": "npm run review",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "reviewHead": head,
        "baseline": "7672ec3d8feab7defb2aa30265b6ff528fe2bf1b (Integrated Visual Sprint 1)",
        "commits": [ln for ln in git("log", "--oneline",
                                     "7672ec3..HEAD").splitlines()],
        "files": [{"file": p.name, "bytes": p.stat().st_size,
                   "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                   "verdict": verdicts.get(p.name)} for p in files],
        "privatePackage": {
            "path": "qa-v5/private/vc2-visual-convergence.zip",
            "why": "Target pixels live there and nowhere else in this repo",
        },
        "notAsserted": ["Target Visual PASS"],
        "notTouched": ["the shipped optical default (opticalBody=current)", "main",
                       "motion code", "the SourceExact layout contract",
                       "TargetOpticalBodyV5 and every optical constant",
                       "card label markup and card typography CSS"],
        "finalProductState": "READY FOR MATCHED-CONTENT VISUAL PRODUCT REVIEW",
        "stateBasis": "§八's ten conditions all pass and the honest grade is MATERIAL AND "
                      "POINTABLE AT 1x -- the bottom 144 rows of all four review viewports "
                      "went from 13-19 luma levels off the Target to under 0.9, and the "
                      "footer geometry from a 59 px mobile displacement to under 0.05 px. "
                      "See product-closure.json.",
    }
    limits = {
        "publicFileLimit": 10, "publicFiles": len(files) + 1,
        "imagesInPublicTree": [p.name for p in d.rglob("*") if p.suffix.lower() in IMAGE_EXT],
    }
    limits["pass"] = limits["publicFiles"] <= limits["publicFileLimit"] \
        and not limits["imagesInPublicTree"]
    doc["deliveryLimits"] = limits
    out_p.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"{limits['publicFiles']}/{limits['publicFileLimit']} public files, "
          f"images={len(limits['imagesInPublicTree'])} -> {out_p}")
    for f in doc["files"]:
        print(f"  {f['file']:<36} {f['verdict']}")
    return 0 if limits["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
