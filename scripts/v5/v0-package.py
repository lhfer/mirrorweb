#!/usr/bin/env python3
"""Build the private V0 culling review package.

Contents, per the brief:
  overlays/       coverage overlay panels -- Target / Before / Candidate, the
                  strict viewport, the 64 px margin band, every replayed AABB
                  coloured by verdict, slot codes, and the DOM state as a dot
  beauty/         the candidate at rest, one clean frame per viewport
  clips/          three lanes x five gestures, H.264 720p, uniform 60 Hz
  compare/        Target-vs-Candidate side-by-side per gesture, one timeline
  numbers/        the public qa-v5/culling JSONs, verbatim
  PACKAGE-MANIFEST.json

The BEFORE lane is the point of this package: the same gestures on the
accepted pre-V0 build show ~81 labels alive and text standing far outside the
viewport; the candidate lane shows the Target's own ~16 with labels waking
inside the 64 px band. If the before and candidate lanes were
indistinguishable, the round changed nothing.

`capturedAt` and `reviewHead` are REQUIRED, no fallback -- see m3-package.py
for why the fallback was removed. Build AFTER the evidence commit.

Usage:
  v0-package.py --rec=<recordings dir> --overlays=<dir> --beauty=<dir>
                --closure=<qa-v5/culling> --out=<zip>
                --capturedAt=<sha> --reviewHead=<sha>
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# The encode/align/hash helpers, shared with the motion package rather than
# copied: one implementation of "resample onto a uniform 60 Hz timeline".
M3P = _load("m3_package", "m3-package.py")

FPS, HEIGHT = 60, 720

# The orientation-flip sequence changes frame dimensions MID-clip (390x844 ->
# 844x390 -> back). libx264 cannot change resolution mid-stream and a bare
# scale=-2:720 still yields varying widths, so that clip is encoded onto a
# fixed 1280x720 canvas, each frame scaled to fit and padded; and it is
# excluded from the hstack side-by-sides, which would hit the same wall twice.
CANVAS_STATES = {"orientation-flip"}


def pad_encode(seq_dir, out, fps, height):
    import subprocess
    out.parent.mkdir(parents=True, exist_ok=True)
    width = 16 * height // 9
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
          f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x101418")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-framerate", str(fps), "-i", str(seq_dir / "%05d.jpg"),
                    "-vf", vf, "-c:v", "libx264", "-preset", "slow",
                    "-crf", M3P.CRF, "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(out)], check=True)
LANES = ["v0Target", "v0Before", "v0Candidate"]
CLIPS = [("1440x900", "slow-horizontal-drag"), ("1440x900", "fast-flick"),
         ("390x844", "touch-drag-release"), ("390x844", "long-drag-multi-wrap"),
         ("390x844", "orientation-flip")]

# The COMPLETE public tree, verbatim -- including README.md: the public
# MANIFEST lists it with a SHA, and a package that carries the manifest but
# not a file it references fails its own audit.
NUMBERS = ["README.md", "target-culling-source.json", "coverage-truth.json",
           "slot-verdicts.json", "edge-pop-in.json", "transform-writes.json",
           "performance.json", "typography-regression.json",
           "motion-regression.json", "source-contract.json", "MANIFEST.json"]


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    for req in ("capturedAt", "reviewHead"):
        if not args.get(req):
            print(f"{req} is required, and there is no fallback", file=sys.stderr)
            return 2

    rec = Path(args["rec"])
    closure = Path(args["closure"])
    out_zip = Path(args["out"])
    work = REPO / "artifacts/culling/package"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    indexes = {}
    for lane in LANES:
        p = rec / f"{lane}-index.json"
        if not p.exists():
            print(f"missing recording index: {p}", file=sys.stderr)
            return 2
        idx = json.loads(p.read_text())
        indexes[lane] = {(r["viewport"], r["sequence"]): r for r in idx["recordings"]}

    # ---- clips: every lane on ONE uniform 60 Hz grid ----------------------
    pairs = 0
    for vp, seq in CLIPS:
        staged = {}
        for lane in LANES:
            r = indexes[lane].get((vp, seq))
            if r is None:
                print(f"missing clip {lane} {vp} {seq}", file=sys.stderr)
                return 2
            src = REPO / r["dir"]
            stage = work / "frames" / lane / f"{vp}-{seq}"
            n = M3P.stage_uniform(src, r["relativeMs"], stage, FPS)
            if n == 0:
                print(f"no frames staged for {lane} {vp} {seq}", file=sys.stderr)
                return 2
            staged[lane] = stage
            clip = work / "clips" / f"{lane}-{vp}-{seq}.mp4"
            if seq in CANVAS_STATES:
                pad_encode(stage, clip, FPS, HEIGHT)
            else:
                M3P.encode(stage, clip, FPS, HEIGHT)
        if seq in CANVAS_STATES:
            continue
        M3P.encode(staged["v0Target"],
                   work / "compare" / f"target-vs-candidate-{vp}-{seq}.mp4",
                   FPS, HEIGHT, extra_in=staged["v0Candidate"])
        M3P.encode(staged["v0Before"],
                   work / "compare" / f"before-vs-candidate-{vp}-{seq}.mp4",
                   FPS, HEIGHT, extra_in=staged["v0Candidate"])
        pairs += 2

    # ---- overlays, beauty, numbers ----------------------------------------
    for name, src in (("overlays", Path(args["overlays"])), ("beauty", Path(args["beauty"]))):
        dest = work / name
        dest.mkdir()
        found = sorted(src.glob("*.png"))
        if not found:
            print(f"no PNGs in {src}", file=sys.stderr)
            return 2
        for p in found:
            shutil.copy2(p, dest / p.name)
    numbers = work / "numbers"
    numbers.mkdir()
    for name in NUMBERS:
        p = closure / name
        if not p.exists():
            print(f"missing public number file: {p}", file=sys.stderr)
            return 2
        shutil.copy2(p, numbers / name)

    # ---- manifest, then zip -----------------------------------------------
    files = sorted(p for p in work.rglob("*") if p.is_file()
                   and "frames/" not in str(p.relative_to(work)))
    entries = [{"path": str(p.relative_to(work)), "bytes": p.stat().st_size,
                "sha256": M3P.sha256_file(p)} for p in files]
    manifest = {
        "package": out_zip.name,
        "capturedAtHead": args["capturedAt"],
        "reviewHead": args["reviewHead"],
        "capturedAtHeadMeaning": "the commit the recorded behaviour was built at",
        "reviewHeadMeaning": "the branch tip this package reviews",
        "containsTargetPixels": True,
        "whyPrivate": "the v0Target lane, the side-by-sides and the target overlay "
                      "panels contain Target pixels. Nothing in this package is "
                      "committed.",
        "lanes": {
            "v0Target": "the Target itself",
            "v0Before": "the accepted pre-V0 build -- backface-only labels, ~81 "
                        "alive at 1440x900",
            "v0Candidate": "the V0 build -- the Target's coverage culling, read "
                           "from its bundle",
        },
        "beforeLaneIsThePoint":
            "exactly one thing changed this round: which labels are kept alive. "
            "The before lane is our page as the motion round left it, so the "
            "difference -- 81 labels against 16, text standing far outside the "
            "viewport against labels waking inside the 64 px band -- is visible "
            "rather than asserted.",
        "alignment": "every clip is resampled onto ONE uniform 60 Hz timeline by "
                     "its own browser frame timestamps before being encoded.",
        "encoding": f"H.264, CRF {M3P.CRF}, {HEIGHT}p, {FPS} fps",
        "sideBySidePairs": pairs,
        "fileCount": len(entries),
        "files": entries,
    }
    (work / "PACKAGE-MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    files = sorted(p for p in work.rglob("*") if p.is_file()
                   and "frames/" not in str(p.relative_to(work)))
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, str(p.relative_to(work)))
    size = out_zip.stat().st_size
    print(f"package -> {out_zip}  {size / 1e6:.1f} MB, {len(files)} files")
    if size > 50 * 1024 * 1024:
        print("FATAL: the package exceeds 50 MB", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
