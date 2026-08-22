#!/usr/bin/env python3
"""Build qa-v5/private/o2-optics-review.zip -- the O2 private review package.

Contents (§九): Target / V1 Before / B-only / A+B lanes under the SAME
deterministic media -- full-frame stills, Edge + Reflection ROI crops,
media-only, envMix=0 floor, shell-only control, H.264 720p clips (desktop
pointer sweep / slow drag / fast flick, mobile touch, bright / dark /
checker / grayscale sweeps), capturedAtHead + reviewHead + per-file
SHA-256. The builder re-reads the zip and fails on any unlisted file.

Target pixels live ONLY in this package, never in the public tree.

Usage: o2-package.py --measure=<dir> --recordings=<dir>
       --capturedAtHead=<sha> --reviewHead=<sha> --out=<zip>
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

import importlib.util

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FPS, HEIGHT, CRF = 60, 720, "26"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o2_optics_stats_pkg", "o2_optics_stats.py")


def run(cmd):
    subprocess.run(cmd, check=True)


def uniform_indices(rel_ms, fps):
    if not rel_ms:
        return []
    step = 1000.0 / fps
    n = int(rel_ms[-1] / step) + 1
    out, j = [], 0
    for i in range(n):
        t = i * step
        while j + 1 < len(rel_ms) and abs(rel_ms[j + 1] - t) <= abs(rel_ms[j] - t):
            j += 1
        out.append(j)
    return out


def encode_clip(src_dir: Path, rel_ms, out: Path):
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td)
        for i, k in enumerate(uniform_indices(rel_ms, FPS)):
            f = src_dir / f"f{k:04d}.jpg"
            if f.exists():
                shutil.copy2(f, stage / f"{i:05d}.jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-framerate", str(FPS), "-i", str(stage / "%05d.jpg"),
             "-vf", f"scale=-2:{HEIGHT}", "-c:v", "libx264", "-preset", "slow",
             "-crf", CRF, "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             str(out)])


def roi_crops(measure: Path, stage: Path):
    """Edge ROI (left bevel) + Reflection ROI (dark half upper band) of the
    largest twin card, per lane, bw-split desktop."""
    from PIL import Image
    rects = sorted((r for _, r in S.rects_at(1440, 900)),
                   key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    x0, y0, x1, y1 = rects[-1]
    edge = (max(0, x0 - 30), y0 + int((y1 - y0) * 0.2),
            x0 + 140, y1 - int((y1 - y0) * 0.2))
    refl = (x0, y0, (x0 + x1) // 2, y0 + int((y1 - y0) * 0.55))
    lanes = {
        "target": "target-rest-bw-split-1440x900.png",
        "before": "local-v1-before-bw-split-1440x900.png",
        "b-only": "local-v1-fullB-bw-split-1440x900.png",
        "a-plus-b": "local-o1-fullB-bw-split-1440x900.png",
    }
    out = []
    for lane, f in lanes.items():
        img = Image.open(measure / f)
        for name, box in [("edge-roi", edge), ("reflection-roi", refl)]:
            dst = stage / "roi" / f"{lane}-{name}.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            img.crop(box).save(dst)
            out.append(dst)
    return out


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    measure = Path(args["measure"])
    recordings = Path(args["recordings"])
    captured = args["capturedAtHead"]
    review = args["reviewHead"]
    out_zip = Path(args["out"])

    stage = Path(tempfile.mkdtemp(prefix="o2pkg-"))

    # ---- stills: the §九 states, all four lanes
    stills = [
        # full frame, four lanes, key assets
        *(f"target-rest-{a}-1440x900.png" for a in
          ["bw-split", "grayscale-step", "rgb-bars", "hf-checker",
           "dark-highlight", "bright-lowsat", "warm-skin", "cool-blue"]),
        *(f"local-v1-before-{a}-1440x900.png" for a in
          ["bw-split", "grayscale-step", "rgb-bars", "cool-blue"]),
        *(f"local-v1-fullB-{a}-1440x900.png" for a in
          ["bw-split", "grayscale-step", "rgb-bars", "cool-blue"]),
        *(f"local-o1-fullB-{a}-1440x900.png" for a in
          ["bw-split", "grayscale-step", "rgb-bars", "hf-checker",
           "dark-highlight", "bright-lowsat", "warm-skin", "cool-blue"]),
        # floors and controls (bw-split): envMix=0, LERP-only, shell-only==before
        "local-o1-envmix0-bw-split-1440x900.png",
        "local-o1-lerponly-bw-split-1440x900.png",
        "local-v1-envmix0-bw-split-1440x900.png",
        "local-v1-lerponly-bw-split-1440x900.png",
        # media-only
        "local-v1-mediaonly-bw-split-1440x900.png",
        "local-o1-mediaonly-bw-split-1440x900.png",
        # mobile
        "target-rest-bw-split-390x844.png",
        "local-v1-before-bw-split-390x844.png",
        "local-o1-fullB-bw-split-390x844.png",
        "target-rest-bw-split-844x390.png",
        "local-o1-fullB-bw-split-844x390.png",
        # pointer states
        *(f"target-{p}-bw-split-1440x900.png" for p in ["pl", "pbr", "pr"]),
        *(f"local-o1-fullB-{p}-bw-split-1440x900.png" for p in ["pl", "pbr", "pr"]),
    ]
    for f in stills:
        src = measure / f
        if not src.exists():
            print(f"MISSING still: {f}", file=sys.stderr)
            return 1
        dst = stage / "stills" / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    roi_crops(measure, stage)

    # ---- clips
    idx = json.loads((recordings / "recordings-index.json").read_text())
    for rec in idx["recordings"]:
        clip = stage / "clips" / rec["lane"] / f"{rec['viewport']}-{rec['sequence']}-{rec['asset']}.mp4"
        encode_clip(REPO / rec["dir"], rec["relativeMs"], clip)

    # ---- manifest
    entries = []
    for f in sorted(stage.rglob("*")):
        if f.is_file():
            entries.append({
                "file": str(f.relative_to(stage)),
                "bytes": f.stat().st_size,
                "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
            })
    manifest = {
        "package": "o2-optics-review",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": captured,
        "reviewHead": review,
        "media": "deterministic shared-media renditions (qa-v5/optics-o2/shared-media-harness.json), frozen at 4.0s on every lane",
        "lanes": ["target (routed)", "before (V1 accepted 5159cf8)",
                  "b-only (dispersionLaw=v1-taps)", "a-plus-b (dispersionLaw=o1-spectral)"],
        "encoder": f"H.264 720p CRF {CRF}, {FPS}fps resampled from browser timestamps",
        "recordingDriver": idx["driver"],
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

    with zipfile.ZipFile(out_zip) as z:
        names = set(z.namelist())
    listed = {e["file"] for e in manifest["files"]} | {"MANIFEST.json"}
    unlisted = names - listed
    if unlisted:
        print(f"UNLISTED files in zip: {sorted(unlisted)[:5]}", file=sys.stderr)
        return 1
    size = out_zip.stat().st_size
    print(f"{out_zip}  {size/1048576:.1f} MB, {len(names)} files")
    if size > 80 * 1048576:
        print("OVER the 80MB budget", file=sys.stderr)
        return 1
    shutil.rmtree(stage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
