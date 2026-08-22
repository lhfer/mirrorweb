#!/usr/bin/env python3
"""Build the private O3 optics review package (§十).

Target pixels and video live ONLY here. The public qa-v5/optics-o3 tree
carries numbers, source anchors and our own frames -- never a Target
rendition.

Both heads are written as full 40-hex SHAs, resolved against this
repository, by the same `full_sha` guard the O2 packager was corrected to
use. A short SHA cannot reach the manifest.

Usage: o3-package.py --measure=<dir> --recordings=<dir> --crosssection=<dir>
       --capturedAtHead=<sha> --reviewHead=<sha> --out=<zip>
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FPS = 30
HEIGHT = "720"
CRF = "23"
SIZE_CAP_MB = 70


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o3_pkg_stats", "o2_optics_stats.py")


def run(cmd):
    subprocess.run(cmd, check=True)


def full_sha(label: str, value: str) -> str:
    """Resolve to a full 40-hex commit SHA or refuse.

    §二 required both heads to stop being written short. Resolution
    happens against this repository, so a value that does not name a real
    commit here cannot reach the manifest either.
    """
    proc = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify",
                           f"{value}^{{commit}}"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{label}: {value!r} does not resolve to a commit "
                         f"in {REPO}")
    sha = proc.stdout.strip()
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise SystemExit(f"{label}: resolved to a non-40-hex value {sha!r}")
    return sha


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
    """Edge ROI (the left bevel over black media) and Reflection ROI (the
    dark half's upper band) of the largest twin card, per lane.

    These are the DETAIL views. §九.20 is judged on the full frames, not
    on these -- a 2x crop is exactly how a wide frame stops looking wide.
    """
    from PIL import Image
    rects = sorted((r for _, r in S.rects_at(1440, 900)),
                   key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    x0, y0, x1, y1 = rects[-1]
    edge = (max(0, x0 - 30), y0 + int((y1 - y0) * 0.2), x0 + 140,
            y1 - int((y1 - y0) * 0.2))
    refl = (x0, y0, (x0 + x1) // 2, y0 + int((y1 - y0) * 0.55))
    corner = (max(0, x0 - 24), max(0, y0 - 24), x0 + 190, y0 + 190)
    lanes = {
        "target": "target-rest-bw-split-1440x900.png",
        "o2-control": "control-full-bw-split-1440x900.png",
        "o3-candidate": "candidate-full-bw-split-1440x900.png",
    }
    out = []
    for lane, f in lanes.items():
        img = Image.open(measure / f)
        for name, box in [("edge-roi", edge), ("reflection-roi", refl),
                          ("corner-roi", corner)]:
            dst = stage / "roi" / f"{lane}-{name}.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            img.crop(box).save(dst)
            out.append(dst)
    return out


DESKTOP = ["bw-split", "grayscale-step", "rgb-bars", "hf-checker",
           "dark-highlight", "bright-lowsat", "warm-skin", "cool-blue"]


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    measure = Path(args["measure"])
    recordings = Path(args["recordings"])
    xsec = Path(args["crosssection"])
    captured = full_sha("capturedAtHead", args["capturedAtHead"])
    review = full_sha("reviewHead", args["reviewHead"])
    out_zip = Path(args["out"])

    stage = Path(tempfile.mkdtemp(prefix="o3pkg-"))

    stills = [
        # --- §十 core stills: Target / O2 control / O3 candidate, full frame
        *(f"target-rest-{a}-1440x900.png" for a in DESKTOP),
        *(f"control-full-{a}-1440x900.png" for a in DESKTOP),
        *(f"candidate-full-{a}-1440x900.png" for a in DESKTOP),
        # --- floor decomposition (bw-split): the diagnosis exhibit
        *(f"{lane}-{st}-bw-split-1440x900.png"
          for lane in ("control", "candidate")
          for st in ("env0rim0", "env0rim1", "env1rim0")),
        # --- support-field debug views (candidate lane only carries them)
        *(f"{lane}-debug-{m}-{a}-1440x900.png"
          for lane in ("control", "candidate")
          for m in ("rim-mask", "analytic-normal")
          for a in ("bw-split", "rgb-bars")),
        # --- media-only
        *(f"{lane}-mediaonly-{a}-1440x900.png"
          for lane in ("control", "candidate") for a in ("bw-split", "rgb-bars")),
        # --- mobile
        *(f"target-rest-bw-split-{vp}.png" for vp in ("390x844", "844x390")),
        *(f"{lane}-full-bw-split-{vp}.png"
          for lane in ("control", "candidate") for vp in ("390x844", "844x390")),
        # --- pointer states
        *(f"target-{p}-bw-split-1440x900.png" for p in ("pl", "pbr", "pr")),
        *(f"{lane}-full-{p}-bw-split-1440x900.png"
          for lane in ("control", "candidate") for p in ("pl", "pbr", "pr")),
    ]
    missing = []
    for f in stills:
        src = measure / f
        if not src.exists():
            missing.append(f)
            continue
        dst = stage / "stills" / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if missing:
        print(f"MISSING stills ({len(missing)}): {missing[:6]}", file=sys.stderr)
        return 1

    roi_crops(measure, stage)

    # --- cross-section charts: §十's top-band and side-band deliverable
    for f in sorted(xsec.glob("*.png")):
        dst = stage / "cross-section" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    shutil.copy2(xsec / "crosssection.json", stage / "cross-section" / "crosssection.json")

    # --- clips
    idx = json.loads((recordings / "recordings-index.json").read_text())
    for rec in idx["recordings"]:
        clip = (stage / "clips" / rec["lane"]
                / f"{rec['viewport']}-{rec['sequence']}-{rec['asset']}.mp4")
        encode_clip(REPO / rec["dir"], rec["relativeMs"], clip)

    # --- the scored verdict travels with the pixels
    for name in ("o3-absolute-gate.json", "o3-preregistration.json",
                 "target-bevel-reflection-source.json",
                 "target-repeatability.json"):
        src = REPO / "qa-v5/optics-o3" / name
        if src.exists():
            shutil.copy2(src, stage / name)

    entries = []
    for f in sorted(stage.rglob("*")):
        if f.is_file():
            entries.append({"file": str(f.relative_to(stage)),
                            "bytes": f.stat().st_size,
                            "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    manifest = {
        "package": "o3-optics-review",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": captured,
        "reviewHead": review,
        "media": "deterministic shared-media renditions "
                 "(qa-v5/optics-o2/shared-media-harness.json), frozen at 4.0s "
                 "on every lane",
        "lanes": [
            "target (routed, same frozen media)",
            "o2 control (reflectionSupport=geometry -- the accepted O2 System B)",
            "o3 candidate (reflectionSupport=target-sdf -- the Target's "
            "analytic bevel normal and rounded-rect SDF rim)",
        ],
        "lanesShareOneBuild": "the two local lanes are the same commit, the "
                              "same page and the same frozen media; they "
                              "differ by ?reflectionSupport alone",
        "encoder": f"H.264 720p CRF {CRF}, {FPS}fps resampled from browser "
                   f"timestamps",
        "recordingDriver": idx["driver"],
        "judgedFullFrames": {
            "note": "§九.20 is judged on these three at 100%, not on the ROI crops",
            "target": "stills/target-rest-bw-split-1440x900.png",
            "o2Control": "stills/control-full-bw-split-1440x900.png",
            "o3Candidate": "stills/candidate-full-bw-split-1440x900.png",
        },
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
    if size > SIZE_CAP_MB * 1048576:
        print(f"OVER the {SIZE_CAP_MB}MB budget", file=sys.stderr)
        return 1
    shutil.rmtree(stage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
