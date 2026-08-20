#!/usr/bin/env python3
"""Per-stage MANIFEST.json: what was captured, under what fixed conditions, and
the SHA-256 of every evidence file, so a reviewer can verify the bundle."""
from __future__ import annotations
import hashlib, json, subprocess, sys, time
from pathlib import Path

FIXED = {
    "quality": "high (pinned; adaptive quality must not drift between captures)",
    "mediaTimeSeconds": 2,
    "mediaState": "frozen, frame-matched across runs",
    "dpr": 1,
    "pointer": [0, 0],
    "offset": "0,0 for gate captures; 260,180 additionally for session B",
    "motion": "paused",
}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    stage = sys.argv[1]
    root = Path("qa-v5") / stage
    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    gate = root / "gate.json"
    verdict = json.loads(gate.read_text()).get("verdict") if gate.exists() else None
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != "MANIFEST.json":
            files.append({"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)})
    payload = {
        "stage": stage,
        "repository": "lhfer/mirrorweb",
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "head": git("rev-parse", "HEAD"),
        "codeCommit": sys.argv[2] if len(sys.argv) > 2 else None,
        "evidenceCommit": "this commit",
        "route": "/?optics=v4 (beauty) and /?optics=v4&foundation=layout&annotate=0 (gate)",
        "captureTimestampUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fixedCaptureConditions": FIXED,
        "gateVerdict": verdict,
        "targetPixelPolicy": "This directory contains LOCAL pixels and Target-derived NUMBERS "
                             "only. Target pixels and Target/local overlays live in "
                             "qa-v5/private/, which is git-ignored.",
        "files": files,
    }
    (root / "MANIFEST.json").write_text(json.dumps(payload, indent=2))
    print(f"{root}/MANIFEST.json  ({len(files)} files)")
