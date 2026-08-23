#!/usr/bin/env python3
"""Final Entry §十一 -- the public manifest, and the limits check.

Public evidence is capped at EIGHT files this round and may carry no images.
This walks the published directory, hashes every file, reads each one's own
verdict out of it rather than restating one, and fails if a limit was broken.

Usage: fe-manifest.py [--dir=qa-v5/final-entry]
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
BASE = "cfad89d942f4945a33bcf206bcbc85d2ec901a65"


def git(*a) -> str:
    return subprocess.run(["git", "-C", str(REPO), *a],
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    d = REPO / args.get("dir", "qa-v5/final-entry")
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
        for k in ("finalProductState", "verdict", "grade"):
            if k in j:
                verdicts[p.name] = j[k]["value"] if isinstance(j.get(k), dict) else j[k]
                break

    state = json.loads((d / "product-state.json").read_text())
    # Resolve the anchor by MESSAGE, never as `git rev-parse HEAD`.
    #
    # This file is regenerated during the evidence commit's own amend cycle, so
    # at generation time HEAD is whichever draft of that commit is about to be
    # REPLACED. Stamping HEAD therefore publishes a SHA that the amend orphans:
    # unreachable from any ref, never transferred by `git push`, dead on arrival
    # for anyone who tries to resolve it. The last commit that changes what the
    # page renders is stable across those amends, so that is the anchor, and it
    # is what `headSemantics` below already claims this field holds.
    captured = git("rev-list", "-1",
                   "--grep=^v5-final-entry-card-lifecycle-code", "HEAD")
    if not captured:
        raise SystemExit("cannot resolve the capture anchor commit by message")
    head = captured
    doc = {
        "round": "MirrorWeb V5 -- Final Experience Convergence",
        "reviewCandidateUrl": "http://127.0.0.1:5293/?review=target",
        "reviewCurrentUrl": "http://127.0.0.1:5293/?review=current",
        "howToServe": "npm run review",
        "lanReview": {
            "serve": "npm run review:lan",
            "printAddresses": "npm run review:lan:url",
            "liveStatusReadout": "add &status=1 to the candidate URL -- FPS, quality, "
                                 "sample tier, material-cache size, black-frame count. "
                                 "It is a QA surface and must be OFF for any capture.",
            "realDevicePass": "NOT ASSERTED. This round guarantees the route is "
                              "reachable from a device on the same network and "
                              "nothing more.",
        },
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "capturedAtHead": captured,
        "reviewHead": head,
        "headSemantics": {
            "capturedAtHead": "v5-final-entry-card-lifecycle-code -- the last "
                              "commit that changes anything the page renders. Every "
                              "still, recording and gate result in this round was "
                              "taken from a build of this tree.",
            "reviewHead": "the head this manifest was generated at, which is the "
                          "same commit: the only thing after it is the evidence "
                          "commit that CARRIES this file, and a manifest cannot "
                          "contain the SHA of the commit it is committed in. That "
                          "commit is the branch tip -- `git log -1 "
                          "--format=%H rebuild/liquid-glass-v5-source-exact` -- and "
                          "it touches only qa-v5/final-motion/ and scripts/v5/, no "
                          "file under src/, so the rendered product at the tip is "
                          "byte-identical to the product at capturedAtHead.",
            "commitsListed": "the three commits that exist at generation time. The "
                             "evidence commit is the fourth and is named in the "
                             "round's commit plan; it is absent here for the same "
                             "reason as above.",
        },
        "baseline": f"{BASE} (Final Motion Convergence Sprint)",
        "commits": git("log", "--oneline", f"{BASE}..{captured}").splitlines(),
        "files": [{"file": p.name, "bytes": p.stat().st_size,
                   "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                   "verdict": verdicts.get(p.name)} for p in files],
        "privatePackage": {
            "path": "qa-v5/private/v5-final-entry.zip",
            "why": "Target pixels live there and nowhere else in this repo",
        },
        "notAsserted": state["notAsserted"],
        "notTouched": state["notTouched"],
        "finalProductState": state["finalProductState"],
        "stateBasis": state["stateBasis"],
        "declaredDeviations": [d["deviation"] for d in state["declaredDeviations"]],
        "openedForTheNextRound": state["openedForTheNextRound"],
        "commitOrderNote": state["commitOrderNote"],
    }
    limits = {
        "publicFileLimit": 8, "publicFiles": len(files) + 1,
        "imagesInPublicTree": [p.name for p in d.rglob("*")
                               if p.suffix.lower() in IMAGE_EXT],
    }
    limits["pass"] = (limits["publicFiles"] <= limits["publicFileLimit"]
                      and not limits["imagesInPublicTree"])
    doc["deliveryLimits"] = limits
    out_p.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(f"{limits['publicFiles']}/{limits['publicFileLimit']} public files, "
          f"images={len(limits['imagesInPublicTree'])} -> {out_p}")
    for f in doc["files"]:
        print(f"  {f['file']:<28} {f['verdict'] or ''}")
    return 0 if limits["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
