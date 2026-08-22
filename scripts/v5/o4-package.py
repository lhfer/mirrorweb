#!/usr/bin/env python3
"""Build the private O4 optics review package (§十二).

Target pixels and video live ONLY here. The public qa-v5/optics-o4 tree
carries numbers, source anchors and our own frames -- never a Target
rendition.

Both heads are written as full 40-hex SHAs, resolved against this
repository, by the same `full_sha` guard the O2 packager was corrected to
use. A short SHA cannot reach the manifest.

Usage: o4-package.py --measure=<dir> --recordings=<dir> --crosssection=<dir>
       --capturedAtHead=<sha> --reviewHead=<sha> --out=<zip>
       [--o3measure=<dir>] [--factorial=<dir>]
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
SIZE_CAP_MB = 80


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o3_pkg_stats", "o2_optics_stats.py")
INS = _load("o4_pkg_ins", "o4_instruments.py")


def run(cmd):
    subprocess.run(cmd, check=True)


def target_provenance(o3measure: Path):
    """Re-measure the reused Target frames under the O4 SEALED instrument.

    The reuse is only honest if these frames still yield the anchors the
    gate was scored against. Measuring them here with o4_instruments -- not
    with the O3 code that produced the anchors -- is an independent check:
    if the O4 band coding read these pixels differently, the numbers below
    would disagree with the anchors and the discrepancy would ship in the
    manifest rather than hide in a footnote.
    """
    from PIL import Image
    anchors = {"1440x900": 3.3, "390x844": 1.5, "844x390": 2.0}
    rows, agree = [], True
    for vp, anchor in anchors.items():
        w, h = (int(x) for x in vp.split("x"))
        rects = [q for _, q in S.rects_at(w, h)]
        basis = "fully-visible cards"
        if not rects:
            VC, SL = sys.modules["v0_culling"], sys.modules["source_layout"]
            frame = SL.layout(w, h)
            cam = VC.coverage_camera(0.0, 0.0, frame)
            cand = []
            for v in VC.frame_verdicts(0.0, 0.0, cam, frame).values():
                if v.get("draw") and v.get("aabb"):
                    x0, y0, x1, y1 = v["aabb"]
                    cand.append((x1 - x0, (int(max(x0, 0)), int(max(y0, 0)),
                                           int(min(x1, w)), int(min(y1, h)))))
            rects = [max(cand)[1]] if cand else []
            basis = "no fully-visible card -- widest drawn card"
        f = o3measure / f"target-rest-bw-split-{vp}.png"
        got = INS.band_width_px(Image.open(f), rects)["meanPx"] if f.exists() else None
        agree = agree and got == anchor
        rows.append({"viewport": vp, "file": f"stills/target/{f.name}",
                     "o3Anchor": anchor, "remeasuredUnderO4Instrument": got,
                     "rectBasis": basis, "agrees": got == anchor})
    return {
        "why": "§十二 lists Target first and states no condition on it. This "
               "round captured no Target renders of its own, and should not "
               "have: the band anchors the O4 primary gate is scored against "
               "ARE these captures' own numbers. Recapturing would score the "
               "gate against one set of pixels and ship another.",
        "source": "artifacts/optics-o3/measure -- the O3 scoring captures, "
                  "same harness, same deterministic shared media, same 4.0s "
                  "freeze, same viewports as this round's local lanes.",
        "capturedAtO3Head": "669046eb16d21fbcc73543b33b2500e2d425c871",
        "routedFrom": "https://infinite-liquid-glass.shader.se/?v=2",
        "verification": "each reused frame re-measured HERE with the O4 "
                        "sealed band instrument (scripts/v5/o4_instruments.py), "
                        "not with the O3 code that produced the anchors.",
        "allAnchorsReproduce": agree,
        "anchors": rows,
    }


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
    """Edge ROI, Reflection ROI and Corner ROI of the largest twin card, per
    lane, in BOTH states. These are the DETAIL views; the full frames are
    what a reader should judge the body change on."""
    from PIL import Image
    rects = sorted((r for _, r in S.rects_at(1440, 900)),
                   key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    x0, y0, x1, y1 = rects[-1]
    edge = (max(0, x0 - 30), y0 + int((y1 - y0) * 0.2), x0 + 140,
            y1 - int((y1 - y0) * 0.2))
    refl = (x0, y0, (x0 + x1) // 2, y0 + int((y1 - y0) * 0.55))
    corner = (max(0, x0 - 24), max(0, y0 - 24), x0 + 190, y0 + 190)
    out = []
    for lane in ("control", "candidate"):
        for state in ("sysBOff", "sysBOn"):
            f = measure / f"{lane}-{state}-bw-split-1440x900.png"
            if not f.exists():
                continue
            img = Image.open(f)
            for name, box in [("edge-roi", edge), ("reflection-roi", refl),
                              ("corner-roi", corner)]:
                dst = stage / "roi" / f"{lane}-{state}-{name}.png"
                dst.parent.mkdir(parents=True, exist_ok=True)
                img.crop(box).save(dst)
                out.append(dst)
    return out


DESKTOP = ["bw-split", "grayscale-step", "rgb-bars", "hf-checker",
           "dark-highlight", "bright-lowsat", "warm-skin", "cool-blue"]
LANES = ["control", "candidate"]
STATES = ["sysBOff", "sysBOn"]


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    measure = Path(args["measure"])
    recordings = Path(args["recordings"])
    xsec = Path(args["crosssection"])
    o3measure = Path(args.get("o3measure", REPO / "artifacts/optics-o3/measure"))
    factorial = Path(args.get("factorial", REPO / "artifacts/optics-o4/factorial"))
    captured = full_sha("capturedAtHead", args["capturedAtHead"])
    review = full_sha("reviewHead", args["reviewHead"])
    out_zip = Path(args["out"])

    stage = Path(tempfile.mkdtemp(prefix="o3pkg-"))

    stills = [
        # --- both lanes, both states, every desktop asset
        *(f"{lane}-{st}-{a}-1440x900.png"
          for lane in LANES for st in STATES for a in DESKTOP),
        # --- both mobile viewports
        *(f"{lane}-{st}-{a}-{vp}.png"
          for lane in LANES for st in STATES for a in ("bw-split", "rgb-bars")
          for vp in ("390x844", "844x390")),
        # --- media-only, the true-silhouette basis
        *(f"{lane}-mediaonly-{a}-1440x900.png"
          for lane in LANES for a in ("bw-split", "rgb-bars")),
        *(f"{lane}-mediaonly-bw-split-{vp}.png"
          for lane in LANES for vp in ("390x844", "844x390")),
        # --- pointer states, shipped
        *(f"{lane}-sysBOn-{p}-bw-split-1440x900.png"
          for lane in LANES for p in ("pl", "pbr", "pr")),
        # --- the accepted O2 baseline the control is proven equal to
        *(f"baseline-e913aa6-sysBOff-{a}-{vp}.png"
          for a, vp in [("bw-split", "1440x900"), ("rgb-bars", "1440x900"),
                        ("grayscale-step", "1440x900"),
                        ("bw-split", "390x844"), ("bw-split", "844x390")]),
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

    # --- Target. §十二 lists the Target first and states no condition on it.
    # O4 captured no Target renders of its own, and should not have: the
    # 3.3 / 1.5 / 2.0 px band anchors this round's primary gate is scored
    # against ARE these captures' own numbers. Recapturing would score the
    # gate against one set of pixels and ship another. So the O3 frames are
    # reused verbatim, with provenance, and re-measured under the O4 sealed
    # instrument in target_provenance() below to prove the reuse is faithful.
    tmissing = []
    for f in sorted(p.name for p in o3measure.glob("target-*.png")):
        src = o3measure / f
        if not src.exists():
            tmissing.append(f)
            continue
        dst = stage / "stills" / "target" / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if not (stage / "stills" / "target").exists():
        print("MISSING Target stills -- §十二 requires them", file=sys.stderr)
        return 1

    # --- every key diagnostic floor: the OFAT lanes of the factorial, which
    # are the pixels the attribution was computed from. 000000 is the control
    # floor, one bit per factor, 111111 all-on.
    fmissing = []
    for code in ("000000", "100000", "010000", "001000",
                 "000100", "000010", "000001", "111111"):
        src = factorial / f"1440x900-bw-split-{code}.png"
        if not src.exists():
            fmissing.append(src.name)
            continue
        dst = stage / "stills" / "diagnostic-floors" / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    if fmissing:
        print(f"MISSING diagnostic floors: {fmissing}", file=sys.stderr)
        return 1

    roi_crops(measure, stage)

    # --- cross-section charts: §十's top-band and side-band deliverable
    for f in sorted(xsec.glob("*.png")) if xsec.exists() else []:
        dst = stage / "cross-section" / f.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
    if (xsec / "crosssection.json").exists():
        shutil.copy2(xsec / "crosssection.json",
                     stage / "cross-section" / "crosssection.json")

    # --- clips
    idx = json.loads((recordings / "recordings-index.json").read_text())
    for rec in idx["recordings"]:
        clip = (stage / "clips" / rec["lane"]
                / f"{rec['viewport']}-{rec['sequence']}-{rec['asset']}.mp4")
        encode_clip(REPO / rec["dir"], rec["relativeMs"], clip)

    # --- the scored verdict travels with the pixels
    # §十二: data/ contains the COMPLETE public optics-o4 evidence tree.
    pub = REPO / "qa-v5/optics-o4"
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
    manifest = {
        "package": "o4-optics-review",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": captured,
        "reviewHead": review,
        "media": "deterministic shared-media renditions "
                 "(qa-v5/optics-o2/shared-media-harness.json), frozen at 4.0s "
                 "on every lane",
        "lanes": [
            "control (bodyFloorMode=current -- the accepted O2 body, proven "
            "pixel-identical to an e913aa6 build at System B OFF)",
            "candidate (bodyFloorMode=remove-adaptive-shaping)",
        ],
        "states": ["sysBOff -- the primary gate state (System B neutralised)",
                   "sysBOn -- the shipped state"],
        "lanesShareOneBuild": "the two local lanes are the same commit, the "
                              "same page and the same frozen media; they "
                              "differ by ?bodyFloorMode alone",
        "encoder": f"H.264 720p CRF {CRF}, {FPS}fps resampled from browser "
                   f"timestamps",
        "recordingDriver": idx["driver"],
        "publicTreeIncluded": "data/ carries the complete public "
                              "qa-v5/optics-o4 evidence tree",
        "target": target_provenance(o3measure),
        "diagnosticFloors": "stills/diagnostic-floors carries the OFAT lanes "
                            "the attribution was computed from -- 000000 is "
                            "the control body floor, one bit per factor in "
                            "V4_BODY_DIAG_ORDER (A refraction offset, B blur, "
                            "C adaptive shaping, D dispersion, E output "
                            "transform, N normal repair), 111111 all-on.",
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
