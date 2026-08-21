#!/usr/bin/env python3
"""
Assemble the motion evidence: public numbers and local pixels, private comparisons.

Target pixels never leave `qa-v5/private/`, which is git-ignored. Numbers
derived from the Target -- its measured landmarks, its repeatability, its decay
curve -- are public, because a number is what a reviewer needs to check a claim
and no Target frame is reconstructible from one.

One image cap, declared once. The T1 round learned this the hard way: two
scripts with two different caps re-encoded twenty already-committed frames and
invalidated every SHA in the manifest.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[2]
ART = REPO / "artifacts/motion"
PUB = REPO / "qa-v5/motion"
PRIV = REPO / "qa-v5/private/motion"

CAP = 720          # public frames
PRIV_CAP = 1400    # private comparisons, where a reviewer is looking closely
GIF_CAP = 620


def font(size=18):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", size)
    except OSError:
        return ImageFont.load_default()


def labelled(img, text):
    out = img.copy()
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, 14 + int(len(text) * 10.5), 28], fill=(0, 0, 0))
    d.text((7, 4), text, fill=(255, 255, 255), font=font(16))
    return out


def strip(pairs, out_path, cap=PRIV_CAP):
    imgs = [labelled(Image.open(p).convert("RGB"), t) for p, t in pairs if Path(p).exists()]
    if len(imgs) < 2:
        return False
    h = max(i.height for i in imgs)
    sheet = Image.new("RGB", (sum(i.width for i in imgs) + 8 * (len(imgs) - 1), h), (12, 14, 20))
    x = 0
    for i in imgs:
        sheet.paste(i, (x, 0)); x += i.width + 8
    sheet.thumbnail((cap, cap), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, optimize=True)
    return True


def gif(frame_dir, out_path, step=2, ms=60, cap=GIF_CAP):
    src = sorted(Path(frame_dir).glob("*.jpg"))[::step]
    if len(src) < 4:
        return False
    frames = []
    for p in src:
        im = Image.open(p).convert("RGB")
        im.thumbnail((cap, cap), Image.LANCZOS)
        frames.append(im)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out_path, save_all=True, append_images=frames[1:],
                   duration=ms, loop=0, optimize=True)
    return True


def aligned_pairs(a_dir, a_ms, b_dir, b_ms, out_dir, a_name, b_name, count=6):
    """Frames from two recordings matched on their own browser timestamps.

    Two recordings of the same gesture do not have the same frame count or the
    same phase, so pairing by index would compare different moments and call the
    difference a motion difference. Each pair is the nearest frame in time.
    """
    a_files = sorted(Path(a_dir).glob("*.jpg"))
    b_files = sorted(Path(b_dir).glob("*.jpg"))
    if not a_files or not b_files:
        return 0
    made = 0
    span = min(a_ms[-1] if a_ms else 0, b_ms[-1] if b_ms else 0)
    if span <= 0:
        return 0
    for k in range(count):
        t = span * (k + 0.5) / count
        ia = min(range(len(a_ms)), key=lambda i: abs(a_ms[i] - t))
        ib = min(range(len(b_ms)), key=lambda i: abs(b_ms[i] - t))
        if ia >= len(a_files) or ib >= len(b_files):
            continue
        ok = strip([(a_files[ia], f"{a_name} t={a_ms[ia]:.0f}ms"),
                    (b_files[ib], f"{b_name} t={b_ms[ib]:.0f}ms")],
                   out_dir / f"t{int(t):05d}ms.png")
        made += 1 if ok else 0
    return made


def decay_plot(contract_path, local_gate_dir, out_path):
    """Release-decay curves, drawn from numbers rather than from frames."""
    import math
    doc = json.loads(Path(contract_path).read_text())
    rows = [r for r in doc["runs"]
            if r["sequence"] in ("fast-flick", "reverse-flick", "touch-drag-release")
            and r.get("decayX")]
    if not rows:
        return False
    W, H, pad = 1200, 760, 70
    img = Image.new("RGB", (W, H), (12, 14, 20))
    d = ImageDraw.Draw(img)
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(f"{r['viewport']} {r['sequence']}", []).append(r["decayX"])
    keys = sorted(groups)
    names = ["timeTo50PctMs", "timeTo10PctMs", "timeToVisualStopMs"]
    colours = [(120, 200, 255), (255, 190, 120), (180, 255, 180)]
    vals = [v[n] for k in keys for v in groups[k] for n in names if v.get(n) is not None]
    top = max(vals) * 1.12 if vals else 1.0
    bar_w = (W - 2 * pad) / max(1, len(keys)) / 4
    d.text((pad, 22), "Target release decay, from the recovered scroll curve", font=font(20),
           fill=(230, 238, 255))
    d.text((pad, 48), "time to 50% / 10% of release velocity, and to visual stop (ms)",
           font=font(15), fill=(150, 165, 190))
    for gi, k in enumerate(keys):
        x0 = pad + gi * (W - 2 * pad) / len(keys)
        for ni, n in enumerate(names):
            series = [v[n] for v in groups[k] if v.get(n) is not None]
            if not series:
                continue
            m = sum(series) / len(series)
            hgt = (H - 2 * pad - 60) * (m / top)
            x = x0 + ni * bar_w + 6
            d.rectangle([x, H - pad - hgt, x + bar_w - 4, H - pad], fill=colours[ni])
            d.text((x, H - pad - hgt - 16), f"{m:.0f}", font=font(13), fill=colours[ni])
        d.text((x0 + 4, H - pad + 8), k, font=font(12), fill=(190, 205, 225))
    for ni, n in enumerate(names):
        d.rectangle([pad + ni * 260, 78, pad + ni * 260 + 16, 92], fill=colours[ni])
        d.text((pad + ni * 260 + 22, 76), n, font=font(14), fill=(210, 220, 240))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, optimize=True)
    return True


def load_index(label):
    p = ART / "recordings" / f"{label}-index.json"
    return json.loads(p.read_text()) if p.exists() else None


if __name__ == "__main__":
    PUB.mkdir(parents=True, exist_ok=True)
    PRIV.mkdir(parents=True, exist_ok=True)

    idx = {label: load_index(label) for label in ("target", "before", "candidate")}

    # Public: our own recordings, plus the decay plot drawn from numbers.
    for rec in (idx["candidate"] or {}).get("recordings", []):
        out = PUB / "recordings" / f"{rec['viewport']}-{rec['sequence']}.gif"
        gif(REPO / rec["dir"], out)
    decay_plot(PUB / "target-motion-contract.json", PUB, PUB / "release-decay.png")

    # Private: anything alongside Target pixels.
    for rec in (idx["target"] or {}).get("recordings", []):
        gif(REPO / rec["dir"], PRIV / "target" / f"{rec['viewport']}-{rec['sequence']}.gif")
    for label in ("before", "candidate"):
        for rec in (idx[label] or {}).get("recordings", []):
            gif(REPO / rec["dir"], PRIV / label / f"{rec['viewport']}-{rec['sequence']}.gif")

    made = 0
    for rec in (idx["candidate"] or {}).get("recordings", []):
        key = (rec["viewport"], rec["sequence"])
        t = next((r for r in (idx["target"] or {}).get("recordings", [])
                  if (r["viewport"], r["sequence"]) == key), None)
        b = next((r for r in (idx["before"] or {}).get("recordings", [])
                  if (r["viewport"], r["sequence"]) == key), None)
        if t:
            made += aligned_pairs(REPO / t["dir"], t["relativeMs"],
                                  REPO / rec["dir"], rec["relativeMs"],
                                  PRIV / "target-vs-candidate" / f"{key[0]}-{key[1]}",
                                  "TARGET", "CANDIDATE")
        if b:
            made += aligned_pairs(REPO / b["dir"], b["relativeMs"],
                                  REPO / rec["dir"], rec["relativeMs"],
                                  PRIV / "before-vs-candidate" / f"{key[0]}-{key[1]}",
                                  "BEFORE", "CANDIDATE")

    for n in ["README.md", "MANIFEST.json", "target-motion-contract.json",
              "input-trajectories.json", "drag-response.json", "flick-decay.json",
              "wheel-normalization.json", "pointer-orbit.json", "touch-runtime.json",
              "wrap-continuity.json", "typography-regression.json", "source-contract.json",
              "engine-vs-contract.json", "resize-continuity.json", "gate-summary.json",
              "card-label-motion.json", "highlight-path.json", "legacy-invariance.json",
              "depth-carry-forward.json",
              "release-decay.png"]:
        p = PUB / n
        if p.exists():
            shutil.copy2(p, PRIV / n)
    for doc in ["docs/v5/SOURCE_EXACT_MOTION.md", "docs/v5/CURRENT_STATUS.md"]:
        if (REPO / doc).exists():
            shutil.copy2(REPO / doc, PRIV / Path(doc).name)
    print(f"motion evidence assembled  ({made} aligned frame pairs)")
