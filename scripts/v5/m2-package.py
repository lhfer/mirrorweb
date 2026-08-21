#!/usr/bin/env python3
"""Build the private visual review package: MP4 clips, comparisons, curves.

WHY MP4 AND NOT GIF
-------------------
The M1 package shipped GIFs, and an earlier pass of it put 274 MB of them into
the public tree. GIF is a poor fit twice over: it cannot carry 60 distinct
frames a second without exploding, and quantising to 128 colours destroys
exactly the thing under review -- a glass surface's gradients. H.264 at a
sensible CRF carries the motion at a fraction of the size.

WHAT IS IN THE PACKAGE
----------------------
Six clips, in three lanes each:
  target      the Target itself
  before      our page built at the M1 tip
  candidate   our page at this round's head
plus, per clip, a timestamp-aligned Target-vs-Candidate side-by-side, a uniform
60 Hz comparison, and the release / dolly curves.

The `before` lane is worth stating plainly: no motion behaviour changed this
round. The product code that changed was readbacks, comments and one rename.
So `before` and `candidate` are expected to be indistinguishable, and the lane
is in the package as the CONTROL that says so -- if they differ, the claim that
this round changed no behaviour is wrong.

Usage:
  m2-package.py --rec=<recordings dir> --closure=<qa-v5/motion-closure>
                --out=<zip> [--traces=<artifacts/motion>]
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARD_CAP_BYTES = 100 * 1024 * 1024
TARGET_CAP_BYTES = 80 * 1024 * 1024
LANES = ("target", "before", "candidate")
FPS = 60
HEIGHT = 720
CRF = "26"


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {r.stderr[-1500:]}")
    return r


def uniform_indices(rel_ms: list[float], fps: int) -> list[int]:
    """Nearest recorded frame for each slot of a fixed timeline.

    The screencast is variable-rate -- it delivers a frame when the compositor
    produces one -- so two clips of the same gesture do not have the same frame
    count and frame k of one is not frame k of the other. Resampling both onto
    the same fixed grid by their own browser timestamps is what makes a
    side-by-side an actual comparison rather than two videos playing at once.
    """
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


def stage_uniform(src: Path, rel_ms: list[float], dest: Path, fps: int) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    idx = uniform_indices(rel_ms, fps)
    for i, k in enumerate(idx):
        f = src / f"f{k:04d}.jpg"
        if f.exists():
            shutil.copy2(f, dest / f"{i:05d}.jpg")
    return len(idx)


def encode(seq_dir: Path, out: Path, fps: int, height: int, extra_in: Path | None = None):
    out.parent.mkdir(parents=True, exist_ok=True)
    if extra_in is None:
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-framerate", str(fps), "-i", str(seq_dir / "%05d.jpg"),
               "-vf", f"scale=-2:{height}", "-c:v", "libx264", "-preset", "slow",
               "-crf", CRF, "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    else:
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-framerate", str(fps), "-i", str(seq_dir / "%05d.jpg"),
               "-framerate", str(fps), "-i", str(extra_in / "%05d.jpg"),
               "-filter_complex",
               f"[0:v]scale=-2:{height},pad=iw+4:ih:0:0:color=0x101418[a];"
               f"[1:v]scale=-2:{height}[b];[a][b]hstack=inputs=2,scale=trunc(iw/2)*2:{height}",
               "-c:v", "libx264", "-preset", "slow", "-crf", CRF,
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    run(cmd)


# --------------------------------------------------------------------------
# curves, drawn with PIL because matplotlib is not installed here
# --------------------------------------------------------------------------

def plot(series: list[tuple[str, list[float], list[float], tuple[int, int, int]]],
         title: str, ylab: str, out: Path, w=1100, h=420):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 13)
        small = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 11)
    except Exception:
        font = small = ImageFont.load_default()
    im = Image.new("RGB", (w, h), (14, 16, 22))
    d = ImageDraw.Draw(im)
    pad_l, pad_r, pad_t, pad_b = 78, 18, 40, 34
    xs = [x for _, X, _, _ in series for x in X]
    ys = [y for _, _, Y, _ in series for y in Y]
    if not xs or not ys:
        return
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys + [0.0]), max(ys)
    if x1 <= x0 or y1 <= y0:
        return
    def px(x): return pad_l + (x - x0) / (x1 - x0) * (w - pad_l - pad_r)
    def py(y): return h - pad_b - (y - y0) / (y1 - y0) * (h - pad_t - pad_b)
    for i in range(5):
        yy = y0 + (y1 - y0) * i / 4
        d.line([(pad_l, py(yy)), (w - pad_r, py(yy))], fill=(36, 40, 50))
        d.text((6, py(yy) - 7), f"{yy:9.3g}", font=small, fill=(130, 138, 152))
    for i in range(6):
        xx = x0 + (x1 - x0) * i / 5
        d.line([(px(xx), pad_t), (px(xx), h - pad_b)], fill=(30, 34, 42))
        d.text((px(xx) - 18, h - pad_b + 8), f"{xx:.0f}", font=small, fill=(130, 138, 152))
    for name, X, Y, col in series:
        pts = [(px(a), py(b)) for a, b in zip(X, Y)]
        if len(pts) > 1:
            d.line(pts, fill=col, width=2)
    d.text((pad_l, 8), title, font=font, fill=(226, 231, 240))
    d.text((6, 8), ylab, font=small, fill=(150, 158, 172))
    lx = w - pad_r - 210
    for i, (name, _, _, col) in enumerate(series):
        d.line([(lx, pad_t + 12 + i * 17), (lx + 24, pad_t + 12 + i * 17)], fill=col, width=3)
        d.text((lx + 30, pad_t + 5 + i * 17), name, font=small, fill=(200, 206, 218))
    d.text((pad_l, h - 14), "milliseconds from the start of the gesture",
           font=small, fill=(120, 128, 142))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)


def sha256_file(p: Path) -> str:
    hh = hashlib.sha256()
    with p.open("rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            hh.update(c)
    return hh.hexdigest()


def main() -> int:
    args = {a[2:].split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:]}
    rec = Path(args["rec"])
    closure = Path(args["closure"])
    out_zip = Path(args["out"])
    traces = Path(args.get("traces", REPO / "artifacts/motion"))
    work = Path(args.get("work", REPO / "artifacts/motion/m2-package"))
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    idx = {}
    for lane in LANES:
        p = rec / f"{lane}-index.json"
        if not p.exists():
            print(f"missing recording index for lane '{lane}': {p}", file=sys.stderr)
            return 1
        idx[lane] = {(r["viewport"], r["sequence"]): r for r in json.loads(p.read_text())["recordings"]}

    clips = sorted(set(idx["candidate"]) & set(idx["target"]))
    print(f"{len(clips)} clips x {len(LANES)} lanes")

    produced: list[Path] = []
    staged: dict[tuple, dict] = {}
    for vp, seq in clips:
        for lane in LANES:
            r = idx[lane].get((vp, seq))
            if r is None:
                continue
            src = REPO / r["dir"]
            dest = work / "frames" / lane / f"{vp}-{seq}"
            n = stage_uniform(src, r["relativeMs"], dest, FPS)
            staged[(lane, vp, seq)] = {"dir": dest, "slots": n}
            mp4 = work / "clips" / f"{vp}-{seq}-{lane}.mp4"
            encode(dest, mp4, FPS, HEIGHT)
            produced.append(mp4)
        # timestamp-aligned Target against Candidate, on one uniform 60 Hz grid
        a = staged.get(("target", vp, seq))
        b = staged.get(("candidate", vp, seq))
        if a and b:
            sbs = work / "compare" / f"{vp}-{seq}-target-vs-candidate-60hz.mp4"
            encode(a["dir"], sbs, FPS, HEIGHT, extra_in=b["dir"])
            produced.append(sbs)
        print(f"  {vp} {seq}: encoded")

    # ---- curves, from the traces rather than from the pixels ---------------
    sys.path.insert(0, str(REPO / "scripts/v5"))
    import importlib.util

    def _load(name, filename):
        spec = importlib.util.spec_from_file_location(name, REPO / "scripts/v5" / filename)
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
        return m
    MT = _load("motion_trace", "motion_trace.py")
    MC = _load("m0_motion_contract", "m0-motion-contract.py")
    R = _load("m2_replay", "m2_replay.py")

    curve_pairs = []
    for vp, seq in clips:
        t_runs = l_runs = None
        tp = traces / f"m2-target-{vp}" / "trace.json"
        lp = traces / f"m2-local-{vp}" / "trace.json"
        if not (tp.exists() and lp.exists()):
            continue
        t_runs = [r for r in json.loads(tp.read_text())["runs"] if r["sequence"] == seq]
        l_runs = [r for r in json.loads(lp.read_text())["runs"] if r["sequence"] == seq]
        if not t_runs or not l_runs:
            continue
        tr, lr = t_runs[0], l_runs[0]
        series_speed, series_dolly = [], []
        for run_, name, col in ((tr, "Target", (255, 176, 78)), (lr, "Candidate", (108, 196, 255))):
            o = MT.trajectory(run_)
            gt, gx = R.uniform(o["t"], o["scrollX"], 60.0)
            _, gy = R.uniform(o["t"], o["scrollY"], 60.0)
            vx, vy = R.velocity_series(gt, gx), R.velocity_series(gt, gy)
            series_speed.append((name, gt, [math.hypot(a, b) for a, b in zip(vx, vy)], col))
            persp = MT.frame_for(*run_["viewport"])["perspective"]
            dt_, dv = [], []
            for s in run_["frames"]:
                p = MT.camera_position(s)
                if p is not None:
                    dt_.append(s["t"])
                    dv.append(math.dist(p, (0.0, 0.0, 0.0)) / persp - 1.0)
            if dt_:
                g2, gv = R.uniform(dt_, dv, 60.0)
                series_dolly.append((name, g2, gv, col))
        p1 = work / "curves" / f"{vp}-{seq}-release-speed.png"
        plot(series_speed, f"{vp}  {seq}   scroll speed, uniform 60 Hz",
             "world units / s", p1)
        p2 = work / "curves" / f"{vp}-{seq}-dolly-envelope.png"
        plot(series_dolly, f"{vp}  {seq}   camera dolly envelope, uniform 60 Hz",
             "distance / perspective - 1", p2)
        produced += [p1, p2]
        rel = MC.release_time(lr)
        curve_pairs.append((vp, seq, rel))

    # ---- aligned frame pairs, chosen by what happens at them ---------------
    #
    # 96 uniform samples last round said little: most of them were the same
    # still frame. Six instants per clip, anchored on the release, cover the
    # moments the gate is actually about -- the last frame of the drag, the
    # release itself, the first of the fling, the fast decay, the slow decay
    # and rest.
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 15)
    except Exception:
        font = ImageFont.load_default()
    OFFSETS = [-100.0, 0.0, 50.0, 150.0, 400.0, 900.0]
    pairs = 0
    for vp, seq, rel in curve_pairs:
        a = staged.get(("target", vp, seq))
        b = staged.get(("candidate", vp, seq))
        if not (a and b) or rel is None:
            continue
        for off in OFFSETS:
            t = rel + off
            k = int(round(t / (1000.0 / FPS)))
            fa, fb = a["dir"] / f"{k:05d}.jpg", b["dir"] / f"{k:05d}.jpg"
            if not (fa.exists() and fb.exists()):
                continue
            ia, ib = Image.open(fa).convert("RGB"), Image.open(fb).convert("RGB")
            H = 560
            ia = ia.resize((int(ia.width * H / ia.height), H), Image.LANCZOS)
            ib = ib.resize((int(ib.width * H / ib.height), H), Image.LANCZOS)
            sheet = Image.new("RGB", (ia.width + ib.width + 6, H + 30), (16, 18, 24))
            sheet.paste(ia, (0, 30))
            sheet.paste(ib, (ia.width + 6, 30))
            d = ImageDraw.Draw(sheet)
            d.text((6, 7), f"TARGET   {vp} {seq}  release{off:+.0f} ms",
                   font=font, fill=(255, 176, 78))
            d.text((ia.width + 12, 7), f"CANDIDATE   release{off:+.0f} ms",
                   font=font, fill=(108, 196, 255))
            p = work / "aligned-pairs" / f"{vp}-{seq}-rel{int(off):+05d}ms.jpg"
            p.parent.mkdir(parents=True, exist_ok=True)
            sheet.save(p, quality=88)
            produced.append(p)
            pairs += 1
    print(f"  aligned frame pairs: {pairs}")

    # ---- the numbers, alongside the pixels --------------------------------
    docs = sorted(p for p in closure.iterdir() if p.is_file())
    for p in docs:
        dest = work / "numbers" / p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        produced.append(dest)

    # ---- manifest, then zip -----------------------------------------------
    def git(*a):
        try:
            return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True,
                                  text=True, check=True).stdout.strip()
        except Exception:
            return None

    files = sorted(p for p in work.rglob("*") if p.is_file() and "frames/" not in str(p))
    entries = [{"path": str(p.relative_to(work)), "bytes": p.stat().st_size,
                "sha256": sha256_file(p)} for p in files]
    manifest = {
        "package": out_zip.name,
        "capturedAtHead": git("rev-parse", "--short", "HEAD"),
        "reviewHead": "resolve with `git rev-parse HEAD`; a file cannot contain the hash "
                      "of the commit that carries it. capturedAtHead and reviewHead are "
                      "separate facts.",
        "containsTargetPixels": True,
        "whyPrivate": "the target/ lane and every side-by-side and aligned pair contain "
                      "Target pixels. Nothing in this package is committed.",
        "lanes": {
            "target": "the Target itself",
            "before": "our page built at the M1 tip d8447de",
            "candidate": "our page at capturedAtHead",
        },
        "beforeLaneIsAControl":
            "no motion behaviour changed this round -- the product code that changed was "
            "readbacks, comments and one rename. `before` and `candidate` are therefore "
            "expected to be indistinguishable, and the lane is here as the control that "
            "says so. If they differ, the claim is wrong.",
        "alignment": "every clip is resampled onto ONE uniform 60 Hz timeline by its own "
                     "browser frame timestamps before being encoded, so frame k of the "
                     "Target and frame k of the candidate are the same instant of the "
                     "same gesture. The screencast itself is variable-rate.",
        "encoding": f"H.264, CRF {CRF}, {HEIGHT}p, {FPS} fps",
        "alignedPairs": pairs,
        "fileCount": len(entries),
        "files": entries,
    }
    (work / "PACKAGE-MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    files = sorted(p for p in work.rglob("*") if p.is_file() and "frames/" not in str(p))

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, str(p.relative_to(work)))
    size = out_zip.stat().st_size
    print(f"package -> {out_zip}  {size/1e6:.1f} MB, {len(files)} files")
    if size > HARD_CAP_BYTES:
        print(f"PACKAGE OVER HARD CAP: {size/1e6:.1f} MB > {HARD_CAP_BYTES/1e6:.0f} MB",
              file=sys.stderr)
        return 1
    if size > TARGET_CAP_BYTES:
        print(f"  note: over the {TARGET_CAP_BYTES/1e6:.0f} MB target, under the hard cap")
    # No unlisted file: the manifest lists every entry in the archive.
    with zipfile.ZipFile(out_zip) as z:
        names = set(z.namelist()) - {"PACKAGE-MANIFEST.json"}
    listed = {e["path"] for e in manifest["files"]}
    unlisted = names - listed
    if unlisted:
        print(f"UNLISTED FILES IN PACKAGE: {sorted(unlisted)[:5]}", file=sys.stderr)
        return 1
    print(f"  manifest lists every one of {len(names)} archive entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
