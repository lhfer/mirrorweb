#!/usr/bin/env python3
"""
Seal the private Motion review package.

The package is built AFTER the final evidence commit, so its manifest can name
that commit. Two heads are recorded rather than one, because they are genuinely
different facts and collapsing them is how the last package ended up claiming a
commit its pixels predated:

  capturedAtHead  the commit the PIXELS were captured at
  reviewHead      the commit this package was BUILT at, and the tip a reviewer
                  should check out

`--refresh` re-copies the text evidence out of the public tree first, so a late
correction to a JSON or a README reaches the package without re-encoding a
single image.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

PUB = Path("qa-v5/motion")
PRIV = Path("qa-v5/private/motion")
ZIP = Path("qa-v5/private/motion-review.zip")
TEXT = ["README.md", "MANIFEST.json", "target-motion-contract.json",
        "input-trajectories.json", "drag-response.json", "flick-decay.json",
        "wheel-normalization.json", "pointer-orbit.json", "touch-runtime.json",
        "wrap-continuity.json", "typography-regression.json", "source-contract.json",
        "engine-vs-contract.json", "resize-continuity.json", "gate-summary.json",
        "card-label-motion.json", "highlight-path.json", "legacy-invariance.json",
        "depth-carry-forward.json",
        "release-decay.png"]
DOCS = ["docs/v5/SOURCE_EXACT_MOTION.md", "docs/v5/CURRENT_STATUS.md"]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    flags = {a.split("=", 1)[0][2:]: a.split("=", 1)[1]
             for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    if "--refresh" in sys.argv:
        for n in TEXT:
            if (PUB / n).exists():
                shutil.copy2(PUB / n, PRIV / n)
        for d in DOCS:
            if Path(d).exists():
                shutil.copy2(d, PRIV / Path(d).name)

    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True).stdout.strip()
    review_head = flags.get("review", git("rev-parse", "HEAD"))
    files = [{"path": str(p.relative_to(PRIV.parent)), "bytes": p.stat().st_size, "sha256": sha(p)}
             for p in sorted(PRIV.rglob("*"))
             if p.is_file() and p.name != "PACKAGE-MANIFEST.json"]
    payload = {
        "package": str(ZIP),
        "describes": "the files inside THIS package, not the public evidence tree",
        "note": "qa-v5/motion/MANIFEST.json is also included and describes the public tree; the two "
                "cover different file sets on purpose. This manifest is what the zip's own "
                "contents hash to.",
        "repository": "lhfer/mirrorweb",
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "capturedAtHead": flags.get("captured", ""),
        "reviewHead": review_head,
        "headSemantics": "`capturedAtHead` is the commit the PIXELS in this package were captured "
                         "at. `reviewHead` is the commit this package was BUILT at -- after the "
                         "final evidence commit, so the manifest can name it -- and is the tip to "
                         "check out. The two differ because no image was re-encoded to chase a "
                         "later hash.",
        "builtAtUtc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "supersedes": flags.get("supersedes", ""),
        "containsTargetPixels": True,
        "files": files,
    }
    (PRIV / "PACKAGE-MANIFEST.json").write_text(json.dumps(payload, indent=2))
    if ZIP.exists():
        ZIP.unlink()
    subprocess.run(["zip", "-q", "-r", ZIP.name, PRIV.name], cwd=PRIV.parent, check=True)
    print(f"{ZIP}  ({len(files)} files, {ZIP.stat().st_size / 1e6:.1f} MB)")
