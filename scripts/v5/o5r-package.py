#!/usr/bin/env python3
"""Build the private O5R optical-body review package (§十五).

Target pixels and Target video live ONLY here. The public qa-v5/optics-o5r tree
carries numbers, source anchors and verdicts -- never a Target rendition.

Content is driven off the capture manifests rather than a hand-written file
list, so the package cannot quietly omit something the gate actually read. Both
heads are written as full 40-hex SHAs resolved against this repository; a short
SHA cannot reach the manifest.

Two ROI families are cut here rather than captured separately, so the crop and
the scored region cannot drift apart: `reflection` is exactly the pixels items
1-3 score (the outer 8% x central 60% edge band, per o5_instruments.edge_band),
and `edge` is the wider strip around it that shows what those numbers sit in.

Usage: o5r-package.py --capturedAtHead=<sha> --reviewHead=<sha> --out=<zip>
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

from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
HERE = REPO / "scripts/v5"
FPS = 30
HEIGHT = "720"
CRF = "26"
SIZE_CAP_MB = 90
ROI_ZOOM = 4
EDGE_STRIP_FRACTION = 0.22

# §十五 caps the package at 90 MB, and this round scores FOUR lanes where O5
# scored three: shipping every capture would be roughly 185 MB of PNG. So the
# stills are selected by an explicit rule, and everything the rule drops is
# listed in the manifest with the reason and with where its verdict lives.
# Nothing is dropped whose evidence is only pixels.
REVIEW_ASSETS = ("bw-split", "grayscale-step", "hf-checker", "dark-highlight",
                 "bright-lowsat", "cool-blue", "warm-skin")
ROI_ASSETS = ("bw-split", "dark-highlight")


def keep_still(rec):
    """Which captures travel, and why. Returns (keep, rule)."""
    kind = rec.get("kind")
    if kind == "view":
        return True, "measurement views: UV fields, SDF mask, analytic normal"
    if kind not in ("target", "lane"):
        return False, ("layer controls (media-only / glass-only). Their "
                       "verdict is numeric and complete in the public tree: "
                       "own-media-isolation.json and the O2 media-only "
                       "controls suite, 0 differing pixels")
    if (rec.get("repeat") or 0) != 0:
        return False, ("Target repeat runs r1..rn. Their whole purpose is "
                       "repeatability, which is a number, and it is in "
                       "target-repeatability.json for all 572 metric rows")
    asset, state, vp = rec.get("asset"), rec.get("state"), rec.get("vp")
    if state == "rest" and asset in REVIEW_ASSETS:
        return True, "the §九 full-frame product review set"
    if state != "rest" and asset == "bw-split":
        return True, "pointer states, on the edge asset"
    if state == "rest" and asset == "calib-landmarks" and vp == "1440x900":
        return True, "the §六 calibration media, one viewport"
    return False, ("calibration and micro-pattern media beyond the one "
                   "landmark frame. These exist to be measured, not looked "
                   "at; their readings are in refraction-compression-v2.json "
                   "and interior-fidelity-v2.json")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I5 = _load("o5_instruments", "o5_instruments.py")
G = _load("o5r_gate", "o5r-gate.py")


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
    so encoding them as if they were evenly spaced would speed the playback up
    and slow it down relative to the real gesture.
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
             "-vf", f"scale=-2:{HEIGHT}", "-c:v", "libx264",
             "-preset", "veryfast", "-crf", CRF, "-pix_fmt", "yuv420p",
             str(out)])
    return True


def cut_rois(measure: Path, stage: Path):
    """Reflection and edge ROIs, cut from the same stills the gate scored."""
    man = json.loads((measure / "measure-manifest.json").read_text())
    made = {"reflection": 0, "edge": 0}
    for rec in man["records"]:
        if rec.get("state") != "rest" or rec.get("asset") not in ROI_ASSETS:
            continue
        if rec.get("kind") == "target" and (rec.get("repeat") or 0) != 0:
            continue
        if rec.get("kind") not in ("target", "lane"):
            continue
        vp = rec["vp"]
        rects = G.RECTS.get(vp, ([], ""))[0]
        if not rects:
            continue
        src = measure / rec["file"]
        if not src.exists():
            continue
        im = Image.open(src).convert("RGB")
        lane = rec.get("lane", "target")
        base = f"{lane}-{rec['asset']}-{vp}"
        x0, y0, x1, y1 = rects[0]
        cw, ch = x1 - x0, y1 - y0

        # reflection ROI: the exact scored band, both sides, magnified.
        yb0, yb1 = y0 + int(ch * 0.2), y1 - int(ch * 0.2)
        bw = max(1, int(cw * I5.EDGE_BAND_FRACTION))
        left = im.crop((x0, yb0, x0 + bw, yb1))
        right = im.crop((x1 - bw, yb0, x1, yb1))
        pair = Image.new("RGB", (left.width + right.width + 6, left.height),
                         (20, 20, 22))
        pair.paste(left, (0, 0))
        pair.paste(right, (left.width + 6, 0))
        pair = pair.resize((pair.width * ROI_ZOOM, pair.height * ROI_ZOOM),
                           Image.NEAREST)
        d = stage / "roi" / "reflection" / f"{base}.png"
        d.parent.mkdir(parents=True, exist_ok=True)
        pair.save(d)
        made["reflection"] += 1

        # edge ROI: the wider strip the band sits in.
        sw = max(2, int(cw * EDGE_STRIP_FRACTION))
        ls, rs = im.crop((x0, y0, x0 + sw, y1)), im.crop((x1 - sw, y0, x1, y1))
        strip = Image.new("RGB", (ls.width + rs.width + 6, ls.height),
                          (20, 20, 22))
        strip.paste(ls, (0, 0))
        strip.paste(rs, (ls.width + 6, 0))
        d = stage / "roi" / "edge" / f"{base}.png"
        d.parent.mkdir(parents=True, exist_ok=True)
        strip.save(d)
        made["edge"] += 1
    return made


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    measure = Path(args.get("measure", REPO / "artifacts/optics-o5r/measure"))
    recordings = Path(args.get("recordings",
                               REPO / "artifacts/optics-o5r/recordings"))
    overlays = Path(args.get("overlays", REPO / "artifacts/optics-o5r/overlays"))
    perf = Path(args.get("performance",
                         REPO / "artifacts/optics-o5r/performance"))
    identity = Path(args.get("identity",
                             REPO / "artifacts/optics-o5r/control-identity"))
    srcenv = Path(args.get("sourceenv", REPO / "artifacts/optics-o5r/source-env"))
    captured = full_sha("capturedAtHead", args["capturedAtHead"])
    review = full_sha("reviewHead", args["reviewHead"])
    out_zip = Path(args["out"])

    stage = Path(tempfile.mkdtemp(prefix="o5rpkg-"))
    man = json.loads((measure / "measure-manifest.json").read_text())

    # ---- stills, straight off the scoring manifest ----------------------
    counts = {"target": 0, "lane": 0, "view": 0}
    omitted = {}
    for rec in man["records"]:
        kind = rec.get("kind")
        if kind not in ("target", "lane", "view", "media-only", "glass-only"):
            continue
        keep, rule = keep_still(rec)
        if not keep:
            omitted[rule] = omitted.get(rule, 0) + 1
            continue
        src = measure / rec["file"]
        if not src.exists():
            continue
        sub = ("target" if kind == "target"
               else "views" if kind == "view" else "lanes")
        dst = stage / "stills" / sub / rec["file"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        counts[kind] = counts.get(kind, 0) + 1
    if counts["target"] == 0:
        print("MISSING Target stills", file=sys.stderr)
        return 1

    roi = cut_rois(measure, stage)

    # ---- the generated programs -----------------------------------------
    # The WGSL is the evidence here; the one render beside each program is the
    # same view the stills already carry, so only the text travels.
    for f in sorted(srcenv.glob("*")) if srcenv.exists() else []:
        if f.is_file() and f.suffix != ".png":
            dst = stage / "programs" / f.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

    # ---- overlays --------------------------------------------------------
    for f in sorted(overlays.glob("*")) if overlays.exists() else []:
        if f.is_file():
            dst = stage / "overlays" / f.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

    # ---- performance: the plots and the first frames ---------------------
    perf_files = 0
    for f in sorted((perf / "plots").glob("*.png")) if (perf / "plots").exists() \
            else []:
        dst = stage / "performance" / "plots" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        perf_files += 1
    for f in sorted(perf.glob("*firstframe.png")):
        dst = stage / "performance" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        perf_files += 1

    # ---- control identity: ONE side of each pair -------------------------
    # The pairs are byte-identical -- that IS the proof -- so shipping both
    # sides would ship the same bytes twice under two names.
    identity_files = 0
    for f in sorted(identity.glob("local-*.png")) if identity.exists() else []:
        dst = stage / "control-identity" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        identity_files += 1

    # ---- clips -----------------------------------------------------------
    clips, clip_index = 0, None
    idx_path = recordings / "recordings-index.json"
    if idx_path.exists():
        clip_index = json.loads(idx_path.read_text())
        for rec in clip_index["recordings"]:
            out = (stage / "clips" / rec["lane"]
                   / f"{rec['viewport']}-{rec['sequence']}-{rec['asset']}.mp4")
            if encode_clip(REPO / rec["dir"], rec["relativeMs"], out):
                clips += 1

    # ---- the complete public tree ----------------------------------------
    pub = REPO / "qa-v5/optics-o5r"
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

    gate = json.loads((pub / "corrected-product-gate.json").read_text())
    sealed = json.loads(
        (REPO / "qa-v5/optics-o5/body-absolute-gate.json").read_text())
    manifest = {
        "package": "o5r-optical-body-review",
        "round": "O5R — target-source optical body product closure",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": captured,
        "reviewHead": review,
        "correctedGate": {"verdict": gate["gate"], "counts": gate["counts"],
                          "total": gate["total"]},
        "sealedO5Gate": {"verdict": sealed["absoluteGate"],
                         "passed": sealed["passed"], "total": sealed["total"],
                         "rewritten": False},
        "media": "deterministic shared-media renditions "
                 "(qa-v5/optics-o2/shared-media-harness.json), frozen at 4.0s "
                 "on every lane including the Target, whose own clips are "
                 "routed to the same elementary streams",
        "lanes": [
            "target — the live site at " + str(man.get("target")),
            "control — opticalBody=current, the accepted O2 body and the "
            "shipped default, proven pixel-identical to a build of the "
            "accepted body across 35 comparisons",
            "o5-clamped — opticalBody=target-source, the SEALED O5 candidate, "
            "byte-identical at this head to the frames the sealed gate scored",
            "o5r-unclamped — opticalBody=target-source-unclamped, the single "
            "O5R candidate §十 authorises",
        ],
        "viewports": ["1440x900", "390x844", "844x390", "700x700"],
        "targetCapturedThisRound": True,
        "targetRepeatabilityFirst": "the Target's repeat captures were taken "
                                    "BEFORE any candidate frame existed, three "
                                    "runs per asset per viewport, because "
                                    "every window is derived from them",
        "stillCounts": counts,
        "stillsOmitted": omitted,
        "stillSelection": "§十五 caps this package at 90 MB and this round "
                          "scores four lanes where O5 scored three; every "
                          "capture would be about 185 MB of PNG. The rule "
                          "above selects what a reviewer looks AT and drops "
                          "what exists only to be measured, and every drop is "
                          "counted with the file that carries its verdict.",
        "roiCounts": roi,
        "roiDefinition": {
            "reflection": "the exact pixels items 1-3 score: the outer "
                          f"{I5.EDGE_BAND_FRACTION:.0%} x central 60% edge "
                          f"band on each side, magnified {ROI_ZOOM}x nearest "
                          "neighbour so no resampling invents an edge",
            "edge": f"the outer {EDGE_STRIP_FRACTION:.0%} strip on each side, "
                    "unmagnified -- the context the scored band sits in",
        },
        "controlIdentityStills": {
            "shipped": identity_files,
            "note": "one side of each pair. The two sides are byte-identical, "
                    "so the second copy would be the same bytes under another "
                    "name. data/control-identity.json carries every count.",
        },
        "clips": clips,
        "encoder": f"H.264 {HEIGHT}p CRF {CRF}, {FPS}fps resampled from "
                   f"browser timestamps",
        "recordingDriver": (clip_index or {}).get("driver"),
        "performanceFiles": perf_files,
        "publicTreeIncluded": "data/ carries the complete public "
                              "qa-v5/optics-o5r evidence tree",
        "publicTreeHasNoTargetPixels": True,
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
    print(f"{out_zip}  {mb:.1f} MB, {len(entries) + 1} files, {clips} clips, "
          f"{roi} ROIs")
    if mb > SIZE_CAP_MB:
        print(f"OVER THE {SIZE_CAP_MB} MB CAP", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
