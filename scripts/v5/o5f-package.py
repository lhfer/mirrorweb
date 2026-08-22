#!/usr/bin/env python3
"""Build the private O5F optical-body review package (§十五).

Target pixels and Target video live ONLY here. The public qa-v5/optics-o5f
tree carries numbers, source anchors and verdicts -- never a Target rendition.

O5R correction E is applied here: `capturedAtHead` is the SHA the final
candidate captures actually ran at, `reviewHead` is the SHA of the final
evidence commit, both resolved to full 40-hex against this repository. The
package is built AFTER the evidence commit, so reviewHead names a commit that
exists and contains everything data/ carries.

This round captured no new Target frames: §十 reuses the SEALED O5R Target
captures as the reference (their repeatability was measured before any O5R
candidate frame existed). The Target stills here are therefore copied from
the O5R measure tree with that provenance stated, not silently mixed in.

Usage: o5f-package.py --capturedAtHead=<sha> --reviewHead=<sha> --out=<zip>
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
                       "verdict is numeric and complete in the public tree")
    if (rec.get("repeat") or 0) != 0:
        return False, ("Target repeat runs r1..rn. Their whole purpose is "
                       "repeatability, which is a number in the sealed "
                       "target-repeatability.json")
    asset, state, vp = rec.get("asset"), rec.get("state"), rec.get("vp")
    if state == "rest" and asset in REVIEW_ASSETS:
        return True, "the full-frame product review set"
    if state != "rest" and asset == "bw-split":
        return True, "pointer states, on the edge asset"
    if state == "rest" and asset == "calib-landmarks" and vp == "1440x900":
        return True, "the calibration media, one viewport"
    return False, ("calibration and micro-pattern media beyond the one "
                   "landmark frame; their readings are numeric and public")


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I5 = _load("o5_instruments", "o5_instruments.py")
G = _load("o5r_gate_pkg", "o5r-gate.py")


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def full_sha(label, value):
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", value],
                       capture_output=True, text=True)
    if r.returncode != 0 or len(r.stdout.strip()) != 40:
        raise SystemExit(f"{label}: cannot resolve {value!r} to a full SHA")
    return r.stdout.strip()


def uniform_indices(rel_ms, fps):
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


def cut_rois(manifest_records, base_dir: Path, stage: Path, made):
    """Reflection and edge ROIs, cut from the same stills the gates scored."""
    for rec in manifest_records:
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
        src = base_dir / rec["file"]
        if not src.exists():
            continue
        im = Image.open(src).convert("RGB")
        lane = rec.get("lane", "target")
        base = f"{lane}-{rec['asset']}-{vp}"
        x0, y0, x1, y1 = rects[0]
        cw, ch = x1 - x0, y1 - y0

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


def copy_tree_files(src: Path, dst_dir: Path, pattern="*", suffix=None):
    n = 0
    if not src.exists():
        return n
    for f in sorted(src.glob(pattern)):
        if f.is_file() and (suffix is None or f.suffix == suffix):
            dst = dst_dir / f.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            n += 1
    return n


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    measure = Path(args.get("measure", REPO / "artifacts/optics-o5f/measure"))
    o5r_measure = Path(args.get("o5rmeasure",
                                REPO / "artifacts/optics-o5r/measure"))
    recordings = Path(args.get("recordings",
                               REPO / "artifacts/optics-o5f/recordings"))
    stress = Path(args.get("stress", REPO / "artifacts/optics-o5f/stress"))
    cycle = Path(args.get("cycle",
                          REPO / "artifacts/optics-o5f/quality-cycle"))
    identity = Path(args.get("identity",
                             REPO / "artifacts/optics-o5f/identity"))
    dec = Path(args.get("decomposition",
                        REPO / "artifacts/optics-o5f/decomposition"))
    rot = Path(args.get("rotation",
                        REPO / "artifacts/optics-o5f/clip-rotation"))
    captured = full_sha("capturedAtHead", args["capturedAtHead"])
    review = full_sha("reviewHead", args["reviewHead"])
    out_zip = Path(args["out"])

    stage = Path(tempfile.mkdtemp(prefix="o5fpkg-"))
    man = json.loads((measure / "measure-manifest.json").read_text())
    o5r_man = json.loads((o5r_measure / "measure-manifest.json").read_text())

    # ---- lane + view stills off THIS round's manifest --------------------
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
        sub = "views" if kind == "view" else "lanes"
        dst = stage / "stills" / sub / rec["file"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        counts[kind] = counts.get(kind, 0) + 1

    # ---- Target stills: the SEALED O5R captures, with provenance ---------
    for rec in o5r_man["records"]:
        if rec.get("kind") != "target":
            continue
        keep, rule = keep_still(rec)
        if not keep:
            omitted[rule] = omitted.get(rule, 0) + 1
            continue
        src = o5r_measure / rec["file"]
        if not src.exists():
            continue
        dst = stage / "stills" / "target-sealed-o5r" / rec["file"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        counts["target"] += 1
    if counts["target"] == 0:
        print("MISSING Target stills", file=sys.stderr)
        return 1

    roi = {"reflection": 0, "edge": 0}
    cut_rois(man["records"], measure, stage, roi)
    cut_rois([r for r in o5r_man["records"] if r.get("kind") == "target"],
             o5r_measure, stage, roi)

    # ---- Phase A evidence: heap plots, cycle references, identity --------
    plots = copy_tree_files(stress / "plots", stage / "phase-a" / "heap-plots")
    plots += copy_tree_files(stress, stage / "phase-a" / "session-frames",
                             "*firstframe.png")
    cycle_refs = copy_tree_files(cycle, stage / "phase-a" / "cycle-references",
                                 "ref-*.png")
    cycle_refs += copy_tree_files(cycle, stage / "phase-a" / "cycle-mismatches",
                                  "mismatch-*.png")
    identity_files = copy_tree_files(identity, stage / "phase-a" / "identity",
                                     "local-*.png")

    # ---- Phase B evidence: decomposition views, clip-rotation frames -----
    dec_files = copy_tree_files(dec, stage / "phase-b" / "decomposition",
                                "*.png")
    dec_files += copy_tree_files(dec, stage / "phase-b" / "decomposition",
                                 "*.wgsl.txt")
    rot_files = copy_tree_files(rot, stage / "phase-b" / "clip-rotation",
                                "*.png")

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
    pub = REPO / "qa-v5/optics-o5f"
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

    stress_doc = json.loads((pub / "material-cache-stress.json").read_text())
    ident_doc = json.loads((pub / "material-cache-identity.json").read_text())
    closure = json.loads((pub / "portrait-closure.json").read_text())
    o5r_gate = json.loads(
        (REPO / "qa-v5/optics-o5r/corrected-product-gate.json").read_text())
    manifest = {
        "package": "o5f-optical-body-review",
        "round": "O5F — material cache and portrait source reconciliation",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": captured,
        "reviewHead": review,
        "headSemantics": "capturedAtHead is the commit the final candidate "
                         "captures ran at; reviewHead is the final evidence "
                         "commit. O5R correction E applied: the O5R package "
                         "recorded a pre-forensics reviewHead; this one is "
                         "built after the evidence commit it names.",
        "phaseA": {"identity": ident_doc["verdict"],
                   "stress": stress_doc["verdict"],
                   "checks": f"{stress_doc['passed']}/{stress_doc['total']}"},
        "portraitClosure": {"finalState": closure["finalState"],
                            "classification": closure.get("classification")},
        "sealedO5RGate": {"verdict": o5r_gate["gate"],
                          "counts": o5r_gate["counts"], "rewritten": False},
        "media": "deterministic shared-media renditions "
                 "(qa-v5/optics-o2/shared-media-harness.json), frozen at 4.0s "
                 "on every lane including the Target",
        "lanes": [
            "target — the SEALED O5R captures, reused as §十's reference; "
            "no Target frame was recaptured this round",
            "control — opticalBody=current, the shipped default",
            "o5-clamped — opticalBody=target-source, the SEALED O5 candidate",
            "o5r-unclamped — opticalBody=target-source-unclamped, the only "
            "active optics candidate",
        ],
        "viewports": ["1440x900", "390x844", "844x390", "700x700"],
        "targetCapturedThisRound": False,
        "targetProvenance": "stills/target-sealed-o5r/ are byte copies of "
                            "the O5R measure captures whose repeatability "
                            "was measured before any candidate frame "
                            "existed; the sealed windows derive from them.",
        "stillCounts": counts,
        "stillsOmitted": omitted,
        "stillSelection": "§十五 caps this package at 90 MB; the rule keeps "
                          "what a reviewer looks AT and drops what exists "
                          "only to be measured, counting every drop with "
                          "the public file that carries its verdict.",
        "roiCounts": roi,
        "roiDefinition": {
            "reflection": "the exact pixels the sealed items score: the "
                          f"outer {I5.EDGE_BAND_FRACTION:.0%} x central 60% "
                          f"edge band on each side, magnified {ROI_ZOOM}x "
                          "nearest neighbour",
            "edge": f"the outer {EDGE_STRIP_FRACTION:.0%} strip on each "
                    "side, unmagnified",
        },
        "phaseAFiles": {"heapPlotsAndFrames": plots,
                        "cycleReferenceStills": cycle_refs,
                        "identityStills": identity_files,
                        "note": "identity pairs are byte-identical; one "
                                "side travels."},
        "phaseBFiles": {"decompositionViewsAndPrograms": dec_files,
                        "clipRotationFrames": rot_files},
        "clips": clips,
        "encoder": f"H.264 {HEIGHT}p CRF {CRF}, {FPS}fps resampled from "
                   "browser timestamps",
        "recordingDriver": (clip_index or {}).get("driver"),
        "publicTreeIncluded": "data/ carries the complete public "
                              "qa-v5/optics-o5f evidence tree",
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
          f"ROIs {roi}")
    if mb > SIZE_CAP_MB:
        print(f"OVER THE {SIZE_CAP_MB} MB CAP", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
