#!/usr/bin/env python3
"""Build the PRIVATE O1 optics review package (Target pixels live here and
only here).

  clips/      target / before / candidate, the SAME real-input gestures the
              motion gates measure (m2 sequence module), H.264 720p
  stills/     every measured lane/layer/state capture (JPEG q90)
  roi/        edge-strip comparisons [target|before|candidate] and metric
              overlays with the measured bands drawn on
  floor/      the dispersionSpread=0 floor capture (PNG, the decisive
              experiment)
  mediaonly/  the desktop frozen-media invariance pair (PNG -- lossless,
              because the claim about them is bit-exactness) + result.json
  data/       copies of the four public JSONs

MANIFEST carries capturedAtHead, reviewHead (both REQUIRED), and a sha256
per file; the builder re-reads the zip and fails on any unlisted file.

Usage: o1-package.py --rec=<dir> --shots=<o1-final> --floor=<png>
       --mediaonly=<dir> --qa=<qa-v5/optics> --capturedAt=<sha>
       --reviewHead=<sha> --out=<zip>
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

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CAP_BYTES = 70 * 1024 * 1024
FPS, HEIGHT, CRF = 60, 720, "26"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


O0 = _load("o0_optics_report_pkg", "o0-optics-report.py")


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-1500:]}")


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


def edge_strip(shots: Path, vp: str, state: str, out: Path):
    """[target | before | candidate] crops around the SAME card's left edge."""
    w, h = map(int, vp.split("x"))
    rects = O0.card_rects(w, h, state)
    if not rects:
        return False
    x0, y0, x1, y1 = max(rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    cx0, cx1 = max(0, x0 - 40), min(w, x0 + 150)
    cy0 = y0 + int((y1 - y0) * 0.2)
    cy1 = y0 + int((y1 - y0) * 0.8)
    panels = []
    for lane, fname in (("target", f"target-{vp}-{state}-r0.png"),
                        ("before", f"before-beauty-{vp}-{state}-r0.png"),
                        ("candidate", f"candidate-beauty-{vp}-{state}-r0.png")):
        img = Image.open(shots / fname).convert("RGB")
        crop = img.crop((cx0, cy0, cx1, cy1))
        crop = crop.resize((crop.width * 2, crop.height * 2), Image.NEAREST)
        panel = Image.new("RGB", (crop.width, crop.height + 28), (16, 20, 24))
        panel.paste(crop, (0, 28))
        ImageDraw.Draw(panel).text((6, 7), lane, fill=(235, 235, 235))
        panels.append(panel)
    hh = max(p.height for p in panels)
    strip = Image.new("RGB", (sum(p.width for p in panels) + 8, hh), (16, 20, 24))
    xx = 0
    for p in panels:
        strip.paste(p, (xx, 0))
        xx += p.width + 4
    out.parent.mkdir(parents=True, exist_ok=True)
    strip.save(out)
    return True


def metric_overlay(shots: Path, gate: dict, lane: str, out: Path):
    """The desktop-rest capture with every measured card's AABB and edge
    band drawn on, and the lane's numbers printed."""
    vp, state = "1440x900", "rest"
    fname = (f"target-{vp}-{state}-r0.png" if lane == "target"
             else f"{lane}-beauty-{vp}-{state}-r0.png")
    img = Image.open(shots / fname).convert("RGB")
    dr = ImageDraw.Draw(img)
    for (x0, y0, x1, y1) in O0.card_rects(1440, 900, state):
        dr.rectangle([x0, y0, x1, y1], outline=(80, 220, 120), width=2)
        bx, by = int((x1 - x0) * 0.15), int((y1 - y0) * 0.15)
        dr.rectangle([x0 + bx, y0 + by, x1 - bx, y1 - by],
                     outline=(240, 180, 60), width=2)
    key = "target" if lane == "target" else f"{lane}-beauty"
    m = gate["metrics"][f"{vp}/{state}"][key]
    txt = (f"{lane}  edgeChroma={m['edgeChromaMean']}  fringeRB={m['fringeRB']}  "
           f"white={m['whiteReflectionRatio']}  edgeLuma={m['edgeLuminanceMean']}")
    dr.rectangle([0, 0, 900, 26], fill=(10, 12, 16))
    dr.text((8, 6), txt, fill=(235, 235, 235))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    rec = Path(args["rec"])
    shots = Path(args["shots"])
    qa = Path(args["qa"])
    out_zip = Path(args["out"])
    captured, review = args["capturedAt"], args["reviewHead"]
    if not captured or not review:
        print("capturedAt and reviewHead are required", file=sys.stderr)
        return 2
    gate = json.loads((qa / "o1-optics-gate.json").read_text())

    stage = Path(tempfile.mkdtemp(prefix="o1-package-"))
    # ---- clips ----
    for lane in ("target", "before", "candidate"):
        idx = json.loads((rec / f"{lane}-index.json").read_text())
        for r in idx["recordings"]:
            encode_clip(REPO / r["dir"], r["relativeMs"],
                        stage / "clips" / f"{lane}-{r['viewport']}-{r['sequence']}.mp4")
    # ---- stills: repeat 0 of the metric lanes plus every layer control;
    # repeats 1-2 exist only as numbers in the gate JSON ----
    for p in sorted(shots.glob("*.png")):
        if p.stem.endswith(("-r1", "-r2")):
            continue
        d = stage / "stills" / (p.stem + ".jpg")
        d.parent.mkdir(parents=True, exist_ok=True)
        Image.open(p).convert("RGB").save(d, quality=90)
    # ---- roi ----
    for vp in ("1440x900", "390x844"):
        for state in ("rest", "pointer-corner-br"):
            edge_strip(shots, vp, state,
                       stage / "roi" / f"edge-compare-{vp}-{state}.png")
    for lane in ("target", "before", "candidate"):
        metric_overlay(shots, gate, lane,
                       stage / "roi" / f"metric-overlay-{lane}-1440x900-rest.png")
    # ---- floor + media-only ----
    (stage / "floor").mkdir(parents=True)
    shutil.copy2(args["floor"], stage / "floor" / "floor-1440x900-rest.png")
    mo = Path(args["mediaonly"])
    (stage / "mediaonly").mkdir(parents=True)
    for f in ("o1-1440x900-rest.png", "pre-1440x900-rest.png", "result.json"):
        shutil.copy2(mo / f, stage / "mediaonly" / f)
    # ---- data ----
    (stage / "data").mkdir(parents=True)
    for f in ("o0-source-diagnosis.json", "o1-selected-system.json",
              "o1-optics-gate.json", "o1-regressions.json"):
        shutil.copy2(qa / f, stage / "data" / f)

    readme = f"""# O1 optics review package (PRIVATE -- contains Target pixels)

Verdict: **{gate['verdict']}** -- the pre-registered failure condition
"{gate['firedFailureConditions'][0]}" fired; see data/o1-optics-gate.json.

clips/      real-input gestures (the m2 sequence module), three lanes.
            Local lanes have media FROZEN at t=2s; the Target's media
            cannot be frozen and is live.
stills/     every measured lane/layer/state capture (JPEG q90).
roi/        edge-compare-*: [target|before|candidate] crops of the SAME
            card edge, 2x nearest. metric-overlay-*: the measured card
            AABBs (green) and edge bands (amber) with the lane's numbers.
floor/      the dispersionSpread=0 build, desktop rest: the decisive
            attribution experiment (the whole dispersion mechanism is worth
            {gate['floorExperiment']['samePageLeverEffect']['edgeChromaPoints']} edge-chroma points on our page --
            {min(gate['floorExperiment']['shareOfTargetGap']['sharePctPerDraw'].values())}-{max(gate['floorExperiment']['shareOfTargetGap']['sharePctPerDraw'].values())}% of the Target gap across observed draws).
mediaonly/  frozen-media media-only pair, O1 vs pre-O1: 0 differing pixels
            (PNG, lossless, because the claim is bit-exactness).
data/       copies of the public qa-v5/optics JSONs.
"""
    (stage / "README.md").write_text(readme)

    files = sorted(p for p in stage.rglob("*") if p.is_file())
    entries = [{"file": str(p.relative_to(stage)), "bytes": p.stat().st_size,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
               for p in files]
    manifest = {
        "package": "o1-optics-review",
        "verdict": gate["verdict"],
        "repository": "lhfer/mirrorweb",
        "branch": subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                 capture_output=True, text=True,
                                 cwd=REPO).stdout.strip(),
        "capturedAtHead": captured,
        "reviewHead": review,
        "builtUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "files": entries,
    }
    (stage / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(stage))

    # ---- self-audit: every manifest entry present and matching, nothing
    # unlisted, size under the cap ----
    with zipfile.ZipFile(out_zip) as z:
        names = set(z.namelist())
        listed = {e["file"] for e in entries} | {"MANIFEST.json"}
        assert names == listed, f"unlisted or missing: {names ^ listed}"
        for e in entries:
            assert hashlib.sha256(z.read(e["file"])).hexdigest() == e["sha256"], e["file"]
    size = out_zip.stat().st_size
    assert size <= CAP_BYTES, f"package {size/1e6:.1f} MB exceeds the 70 MB cap"
    shutil.rmtree(stage)
    print(f"{out_zip}  {size/1048576:.1f} MB, {len(entries) + 1} files, "
          f"capturedAtHead={captured[:12]} reviewHead={review[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
