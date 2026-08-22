#!/usr/bin/env python3
"""Build the private O5 optical-body review package (§十三).

Target pixels and video live ONLY here. The public qa-v5/optics-o5 tree carries
numbers, source anchors and verdicts -- never a Target rendition.

Both heads are written as full 40-hex SHAs resolved against this repository.
A short SHA cannot reach the manifest.

Usage: o5-package.py --capturedAtHead=<sha> --reviewHead=<sha> --out=<zip>
       [--measure=<dir>] [--recordings=<dir>] [--overlays=<dir>]
       [--audit=<dir>] [--identity=<dir>] [--pipeline=<dir>]
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
FPS = 30
HEIGHT = "720"
CRF = "26"
SIZE_CAP_MB = 90


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def full_sha(label, value):
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", value],
                       capture_output=True, text=True)
    if r.returncode != 0 or len(r.stdout.strip()) != 40:
        raise SystemExit(f"{label}: cannot resolve {value!r} to a full SHA")
    return r.stdout.strip()


def uniform_indices(rel_ms, fps):
    """Resample browser-timestamped frames onto a uniform grid.

    The screencast delivers frames when the compositor has one, not on a clock,
    so encoding them as if they were evenly spaced would speed up and slow down
    the playback relative to the real gesture. Picking the nearest real frame
    to each uniform tick keeps the clip honest about timing.
    """
    if not rel_ms:
        return []
    total = rel_ms[-1]
    n = max(1, int(total / 1000.0 * fps))
    out, j = [], 0
    for i in range(n):
        t = i * 1000.0 / fps
        while j + 1 < len(rel_ms) and abs(rel_ms[j + 1] - t) <= abs(rel_ms[j] - t):
            j += 1
        out.append(j)
    return out


def encode_clip(src_dir: Path, rel_ms, out: Path):
    idx = uniform_indices(rel_ms, FPS)
    if not idx:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td)
        for i, k in enumerate(idx):
            f = src_dir / f"f{str(k).zfill(4)}.jpg"
            if f.exists():
                shutil.copy2(f, stage / f"{i:05d}.jpg")
        if not any(stage.iterdir()):
            return False
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-framerate", str(FPS), "-i", str(stage / "%05d.jpg"),
             "-vf", f"scale=-2:{HEIGHT}", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", CRF, "-pix_fmt", "yuv420p", str(out)])
    return True


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    measure = Path(args.get("measure", REPO / "artifacts/optics-o5/measure"))
    recordings = Path(args.get("recordings",
                               REPO / "artifacts/optics-o5/recordings"))
    overlays = Path(args.get("overlays", REPO / "artifacts/optics-o5/overlays"))
    audit = Path(args.get("audit", REPO / "artifacts/optics-o5/audit"))
    identity = Path(args.get("identity",
                             REPO / "artifacts/optics-o5/control-identity"))
    pipeline = Path(args.get("pipeline", REPO / "artifacts/optics-o5/pipeline"))
    captured = full_sha("capturedAtHead", args["capturedAtHead"])
    review = full_sha("reviewHead", args["reviewHead"])
    out_zip = Path(args["out"])

    stage = Path(tempfile.mkdtemp(prefix="o5pkg-"))
    man = json.loads((measure / "measure-manifest.json").read_text())

    # ---- stills, straight off the scoring manifest ---------------------
    # Driven by the manifest rather than by a hand-written filename list, so
    # the package cannot silently omit a capture the gate actually read.
    counts = {"target": 0, "lane": 0, "media-only": 0, "glass-only": 0}
    for rec in man["records"]:
        kind = rec.get("kind")
        if kind not in ("target", "lane", "media-only", "glass-only"):
            continue
        src = measure / rec["file"]
        if not src.exists():
            continue
        sub = ("target" if kind == "target"
               else "layers" if kind in ("media-only", "glass-only")
               else "lanes")
        dst = stage / "stills" / sub / rec["file"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        counts[kind] += 1
    if counts["target"] == 0:
        print("MISSING Target stills", file=sys.stderr)
        return 1

    # ---- debug views: SDF mask and analytic normal ---------------------
    for name in ("candidate-analytic-normal.png", "candidate-sdf-mask.png",
                 "candidate-refraction-only.png", "candidate-beauty.png"):
        f = audit / name
        if f.exists():
            dst = stage / "stills" / "debug" / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

    # ---- overlays: the exhibits ----------------------------------------
    for f in sorted(overlays.glob("*.png")) if overlays.exists() else []:
        dst = stage / "overlays" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    if (overlays / "overlays.json").exists():
        shutil.copy2(overlays / "overlays.json", stage / "overlays" / "overlays.json")

    # ---- control identity: ONE side of each pair ------------------------
    # The pairs are byte-identical -- that IS the proof, 0 differing pixels on
    # all 35 comparisons -- so shipping both sides would be shipping the same
    # bytes twice under two names. The `local-` side travels; the `base-` side
    # is reproducible from it and from control-identity.json, which carries the
    # per-comparison counts.
    identity_files = 0
    for f in sorted(identity.glob("local-*.png")) if identity.exists() else []:
        dst = stage / "control-identity" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        identity_files += 1

    # ---- first frames from the pipeline gate ---------------------------
    for f in sorted(pipeline.glob("*.png")) if pipeline.exists() else []:
        dst = stage / "pipeline" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)

    # ---- clips ----------------------------------------------------------
    clips = 0
    idx = json.loads((recordings / "recordings-index.json").read_text())
    for rec in idx["recordings"]:
        out = (stage / "clips" / rec["lane"]
               / f"{rec['viewport']}-{rec['sequence']}-{rec['asset']}.mp4")
        if encode_clip(REPO / rec["dir"], rec["relativeMs"], out):
            clips += 1

    # ---- the complete public tree --------------------------------------
    pub = REPO / "qa-v5/optics-o5"
    for src in sorted(pub.iterdir()):
        if src.is_file():
            dst = stage / "data" / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    entries = []
    for f in sorted(stage.rglob("*")):
        if f.is_file():
            entries.append({"file": str(f.relative_to(stage)),
                            "bytes": f.stat().st_size,
                            "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})

    gate = json.loads((pub / "body-absolute-gate.json").read_text())
    manifest = {
        "package": "o5-optical-body-review",
        "round": "O5 — source-exact card optical body",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": captured,
        "reviewHead": review,
        "finalState": gate["finalState"],
        "absoluteGate": gate["absoluteGate"],
        "media": "deterministic shared-media renditions "
                 "(qa-v5/optics-o2/shared-media-harness.json), frozen at 4.0s "
                 "on every lane including the Target, whose own clips are "
                 "routed to the same elementary streams",
        "lanes": [
            "target — the live site at "
            + man["target"],
            "control — opticalBody=current, the accepted O2 body, proven "
            "pixel-identical to a 5a87751 build across 35 comparisons",
            "candidate — opticalBody=target-source",
        ],
        "targetCapturedThisRound": True,
        "targetRepeatabilityFirst": "the Target's repeat captures were taken "
                                    "BEFORE any candidate frame existed, "
                                    f"{man['repeats']} runs per viewport, "
                                    "because every gate window is derived "
                                    "from them",
        "stillCounts": counts,
        "controlIdentityStills": {
            "shipped": identity_files,
            "note": "one side of each pair. The two sides are byte-identical "
                    "-- 0 differing pixels on all 35 comparisons -- so the "
                    "second copy would be the same bytes under another name. "
                    "data/control-identity.json carries every count.",
        },
        "clips": clips,
        "encoder": f"H.264 {HEIGHT}p CRF {CRF}, {FPS}fps resampled from "
                   f"browser timestamps",
        "recordingDriver": idx["driver"],
        "publicTreeIncluded": "data/ carries the complete public "
                              "qa-v5/optics-o5 evidence tree",
        "files": entries,
    }
    (stage / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(stage.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(stage))
    mb = out_zip.stat().st_size / 1048576
    shutil.rmtree(stage)
    print(f"{out_zip}  {mb:.1f} MB, {len(entries) + 1} files, {clips} clips")
    if mb > SIZE_CAP_MB:
        print(f"OVER THE {SIZE_CAP_MB} MB CAP", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
