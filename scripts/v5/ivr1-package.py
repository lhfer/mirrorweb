#!/usr/bin/env python3
"""Integrated Visual Sprint 1 §十一 -- the private review package.

Hard limits enforced here: zip <= 60 MB, <= 8 videos, <= 24 full-page
stills (+ per-viewport contact sheets), plus the §九 overlays and raw data.
Stills are packaged as JPEG q95 (the pixel-exact PNGs stay in artifacts/);
videos are re-encoded to CRF 27 at half the screencast rate -- review
quality, honest wall-clock. Target pixels live ONLY in this zip.

Output: qa-v5/private/ivr1-integrated-review.zip
"""
from __future__ import annotations

import json
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent.parent
ART = REPO / "artifacts/integrated-review"
QA = REPO / "qa-v5/integrated-review"
PRIV = REPO / "qa-v5/private"
STAGE = REPO / "artifacts/integrated-review/package-stage"
ZIP = PRIV / "ivr1-integrated-review.zip"

VIDEO_PAIRS = ["desktop-slow-drag", "desktop-fast-flick",
               "mobile-long-drag-wrap", "orientation-change"]
VIEWPORTS = ["1440x900", "700x700", "390x844", "844x390"]
STILL_SETS = [
    ("target", ART / "target/stills", "the live Target, §四"),
    ("current-before", ART / "review-current/stills-before", "review=current (shipped default), before"),
    ("candidate-before", ART / "review-target/stills-before", "review=target, BEFORE the §七 fix"),
    ("candidate-after", ART / "review-target/stills", "review=target, AFTER the §七 exposure fix"),
]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{' '.join(map(str, cmd))}\n{r.stderr}")


def jpeg(src: Path, dst: Path, q=92):
    Image.open(src).convert("RGB").save(dst, quality=q, optimize=True)


def contact_sheet(vp: str, dst: Path):
    """target | candidate-before | candidate-after, one row, labelled."""
    cols = [("TARGET", ART / f"target/stills/{vp}.png"),
            ("CANDIDATE BEFORE", ART / f"review-target/stills-before/{vp}.png"),
            ("CANDIDATE AFTER", ART / f"review-target/stills/{vp}.png")]
    ims = [Image.open(p).convert("RGB") for _, p in cols]
    h = 620
    ims = [im.resize((round(im.width * h / im.height), h)) for im in ims]
    pad, cap = 8, 30
    W = sum(im.width for im in ims) + pad * 4
    sheet = Image.new("RGB", (W, h + cap + pad * 2), (10, 12, 20))
    dr = ImageDraw.Draw(sheet)
    x = pad
    for (label, _), im in zip(cols, ims):
        sheet.paste(im, (x, cap + pad))
        dr.text((x + 4, 8), f"{label}  {vp}", fill=(235, 235, 235))
        x += im.width + pad
    sheet.save(dst, quality=88, optimize=True)


def encode(frames_dir: Path, fps: float, dst: Path):
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-framerate", f"{fps:.2f}", "-i", str(frames_dir / "%05d.jpg"),
         "-vf", "select='not(mod(n\\,2))',scale=trunc(iw/2)*2:trunc(ih/2)*2",
         "-r", f"{fps / 2:.2f}", "-c:v", "libx264", "-preset", "medium",
         "-crf", "28", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)])


def main() -> int:
    PRIV.mkdir(parents=True, exist_ok=True)
    if STAGE.exists():
        import shutil
        shutil.rmtree(STAGE)
    (STAGE / "stills").mkdir(parents=True)
    (STAGE / "videos").mkdir()
    (STAGE / "contact-sheets").mkdir()
    (STAGE / "motion").mkdir()
    (STAGE / "perf").mkdir()
    (STAGE / "data").mkdir()

    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()

    stills = []
    for label, src, note in STILL_SETS:
        for vp in VIEWPORTS:
            p = src / f"{vp}.png"
            if not p.exists():
                raise SystemExit(f"missing still {p}")
            out = STAGE / "stills" / f"{label}-{vp}.jpg"
            jpeg(p, out)
            stills.append({"file": f"stills/{out.name}", "set": label, "vp": vp, "note": note})
    assert len(stills) <= 24, "still budget exceeded"

    sheets = []
    for vp in VIEWPORTS:
        out = STAGE / "contact-sheets" / f"{vp}.jpg"
        contact_sheet(vp, out)
        sheets.append(f"contact-sheets/{out.name}")

    videos = []
    for sc in VIDEO_PAIRS:
        for side, sdir in [("target", ART / "target/recordings"),
                           ("candidate", ART / "review-target/recordings")]:
            frames = sdir / sc
            idx = json.loads((frames / "index.json").read_text())
            dst = STAGE / "videos" / f"{side}-{sc}.mp4"
            encode(frames, idx["fps"], dst)
            videos.append({"file": f"videos/{dst.name}", "side": side, "scenario": sc,
                           "vp": idx["vp"], "spanSec": idx["spanSec"],
                           "driver": idx["driver"],
                           "provenance": idx.get("provenance")})
    assert len(videos) <= 8, "video budget exceeded"

    for p in sorted((ART / "motion").glob("*-overlay.png")):
        Image.open(p).save(STAGE / "motion" / p.name, optimize=True)
    for name in ["desktop-still-0.png", "mobile-still-0.png"]:
        p = ART / "perf" / name
        if p.exists():
            jpeg(p, STAGE / "perf" / (p.stem + ".jpg"))

    data_files = [
        QA / "p0-ranking.json", QA / "glass-selected-problem.json",
        QA / "glass-closure.json", QA / "typography-closure.json",
        QA / "motion-visual-diagnosis.json", QA / "perf-smoke.json",
        ART / "review-route-verification.json",
        ART / "typography/target/target-typography.json",
        ART / "typography/local/target-typography.json",
        ART / "motion/summary.json",
        ART / "perf/perf-smoke-raw.json",
    ]
    data = []
    for p in data_files:
        if p.exists():
            dst = STAGE / "data" / (p.parent.name + "-" + p.name
                                    if p.name == "target-typography.json" else p.name)
            dst.write_bytes(p.read_bytes())
            data.append(f"data/{dst.name}")

    manifest = {
        "what": "Integrated Visual Sprint 1 private review package. The ONLY place Target pixels live.",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reviewHead": head,
        "headSemantics": {
            "beforeCaptures": "f013671 (review-route head)",
            "afterCaptures": "working tree committed unchanged as 5833dd6",
            "typographyReads": "working tree committed unchanged as a3748fd",
            "reviewHead": "the head this package was assembled at",
        },
        "budgets": {"videos": f"{len(videos)}/8", "stills": f"{len(stills)}/24",
                     "contactSheets": len(sheets)},
        "encoding": "stills JPEG q92 (pixel-exact PNGs remain in local artifacts/); videos re-encoded CRF 28 at half screencast rate, wall-clock preserved",
        "stills": stills, "contactSheets": sheets, "videos": videos,
        "motionOverlays": sorted(p.name for p in (STAGE / "motion").glob("*.png")),
        "data": data,
    }
    (STAGE / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(STAGE.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(STAGE))
    mb = ZIP.stat().st_size / 1048576
    print(f"{ZIP}  {mb:.1f} MB  ({len(videos)} videos, {len(stills)} stills, "
          f"{len(sheets)} sheets)")
    if mb > 60:
        print("OVER BUDGET -- raise CRF / lower JPEG quality and rebuild")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
