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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a.split("=", 1)[0][2:]: a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    stage = args[0]
    root = Path("qa-v5") / stage
    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    gate = root / "gate.json"
    verdict = json.loads(gate.read_text()).get("verdict") if gate.exists() else None
    # Explicit overrides. A manifest written by the commit it describes cannot
    # know its own hash, so a later hygiene pass has to be able to state the
    # real HEAD, the real code commit and the real verdict rather than leaving
    # nulls and a stale hash behind.
    verdict = flags.get("verdict", verdict)
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != "MANIFEST.json":
            files.append({"path": str(p), "bytes": p.stat().st_size, "sha256": sha(p)})
    payload = {
        "stage": stage,
        "repository": "lhfer/mirrorweb",
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "head": flags.get("head", git("rev-parse", "HEAD")),
        "codeCommit": flags.get("code", args[1] if len(args) > 1 else None),
        "evidenceCommit": flags.get("evidence", "this commit"),
        "headSemantics": flags.get(
            "semantics",
            "`head` is the commit the evidence was CAPTURED at. The evidence "
            "commit that carries these files is necessarily later, and a file "
            "cannot contain its own hash; no hygiene commit is created to chase "
            "one."),
        "route": flags.get("route",
                            "/?optics=v4 (beauty) and /?optics=v4&foundation=layout&annotate=0 (gate)"),
        "captureTimestampUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "fixedCaptureConditions": json.loads(flags["fixed"]) if "fixed" in flags else FIXED,
        "gateVerdict": verdict,
        "privateReviewPackage": flags.get("private"),
        "supersedes": flags.get("supersedes"),
        "targetPixelPolicy": "This directory contains LOCAL pixels and Target-derived NUMBERS "
                             "only. Target pixels and Target/local overlays live in "
                             "qa-v5/private/, which is git-ignored.",
        "files": files,
    }
    (root / "MANIFEST.json").write_text(json.dumps(payload, indent=2))
    print(f"{root}/MANIFEST.json  ({len(files)} files)")
