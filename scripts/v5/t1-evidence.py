#!/usr/bin/env python3
"""T1 evidence: local pixels public, anything alongside Target pixels private.

Frames are capped once, at 720 px, on the way in. The FSX-A bundle capped at 900
in the script and 720 in the tree, so re-running re-encoded committed frames and
invalidated their hashes; one cap in one place is what stops that.
"""
from __future__ import annotations
import json, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ART = Path("artifacts/t1")
PUB = Path("qa-v5/t1")
PRIV = Path("qa-v5/private/t1")
# 560 for the full-frame states, 720 for the sparse analysis frames. The public
# tree is meant to be reviewable in a browser, not to be the archive: the
# full-resolution frames stay under artifacts/, which is git-ignored.
CAP = 560
CAP_SPARSE = 720
VPS = ["1440x900", "1920x1080", "390x844", "844x390", "700x700", "667x375", "780x470"]
STATES = ["1-foundation", "2-media-only", "3-glass-media", "4-full-beauty"]


def font(sz=20):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", sz)
    except OSError:
        return ImageFont.load_default()


def label(img, text):
    out = img.copy()
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, 14 + int(len(text) * 12), 32], fill=(0, 0, 0))
    d.text((8, 5), text, fill=(255, 255, 255), font=font())
    return out


def shrink(src, dst, cap=CAP):
    if not Path(src).exists():
        return False
    im = Image.open(src).convert("RGB")
    im.thumbnail((cap, cap), Image.LANCZOS)
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    im.save(dst, optimize=True)
    return True


def strip(pairs, out_path, scale=1.0):
    imgs = [label(Image.open(p).convert("RGB"), t) for p, t in pairs if Path(p).exists()]
    if len(imgs) < 2:
        return False
    h = max(i.height for i in imgs)
    w = sum(i.width for i in imgs) + 8 * (len(imgs) - 1)
    sheet = Image.new("RGB", (w, h), (12, 14, 20))
    x = 0
    for i in imgs:
        sheet.paste(i, (x, 0))
        x += i.width + 8
    if scale != 1.0:
        sheet = sheet.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, optimize=True)
    return True


def fifty_fifty(left, right, out_path, left_tag, right_tag):
    """Left half of one frame beside the right half of the other, at the seam."""
    if not (Path(left).exists() and Path(right).exists()):
        return False
    a = Image.open(left).convert("RGB")
    b = Image.open(right).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size, Image.LANCZOS)
    out = a.copy()
    out.paste(b.crop((a.width // 2, 0, a.width, a.height)), (a.width // 2, 0))
    d = ImageDraw.Draw(out)
    d.line([(a.width // 2, 0), (a.width // 2, a.height)], fill=(255, 0, 255), width=2)
    d.rectangle([0, 0, 14 + len(left_tag) * 12, 30], fill=(0, 0, 0))
    d.text((8, 4), left_tag, fill=(255, 255, 255), font=font(18))
    d.rectangle([a.width // 2 + 4, 0, a.width // 2 + 18 + len(right_tag) * 12, 30], fill=(0, 0, 0))
    d.text((a.width // 2 + 12, 4), right_tag, fill=(255, 255, 255), font=font(18))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(out_path, optimize=True)
    return True


def contact(items, out_path, cols=4, cell=360):
    tiles = []
    for p, t in items:
        if not Path(p).exists():
            continue
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell, cell), Image.LANCZOS)
        pad = Image.new("RGB", (cell, cell + 28), (12, 14, 20))
        pad.paste(im, ((cell - im.width) // 2, 28 + (cell - im.height) // 2))
        ImageDraw.Draw(pad).text((6, 5), t, fill=(220, 230, 255), font=font(16))
        tiles.append(pad)
    if not tiles:
        return False
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 28)), (12, 14, 20))
    for n, t in enumerate(tiles):
        sheet.paste(t, ((n % cols) * cell, (n // cols) * (cell + 28)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, optimize=True)
    return True


def gif(src_dir, out_path, cap=820, ms=340):
    src = sorted(Path(src_dir).glob("*.png"))
    if not src:
        return False
    W = max(Image.open(p).width for p in src)
    H = max(Image.open(p).height for p in src)
    frames = []
    for p in src:
        im = Image.open(p).convert("RGB")
        c = Image.new("RGB", (W, H), (12, 14, 20))
        c.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
        c.thumbnail((cap, cap), Image.LANCZOS)
        frames.append(c)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=ms, loop=0,
                   optimize=True)
    return True


if __name__ == "__main__":
    PUB.mkdir(parents=True, exist_ok=True)
    PRIV.mkdir(parents=True, exist_ok=True)

    # ---- public: our own pixels only -------------------------------------
    for vp in VPS:
        for st in STATES:
            shrink(ART / f"beauty/{vp}/{st}.png", PUB / f"local/beauty/{vp}/{st}.png")
        shrink(ART / f"beauty/{vp}/diff-media-vs-glass.png",
               PUB / f"local/beauty/{vp}/diff-media-vs-glass.png")
        shrink(ART / f"depth-clipping/{vp}-labels-only.png", PUB / f"local/labels-only/{vp}.png",
               CAP_SPARSE)
        shrink(ART / f"depth-clipping/{vp}-mask-and-bounds.png",
               PUB / f"local/mask-and-bounds/{vp}.png", CAP_SPARSE)
        # Before / after, both ours.
        strip([(ART / f"beauty-before/{vp}/4-full-beauty.png", "BEFORE  fixed TILE box"),
               (ART / f"beauty/{vp}/4-full-beauty.png", "CANDIDATE  card-plane box")],
              PUB / f"local/before-vs-candidate/{vp}.png", scale=0.42)
    for lvl in ["0-high-base", "1-medium", "2-low", "3-high"]:
        for vp in ["1440x900", "390x844", "700x700"]:
            shrink(ART / f"quality/{vp}-{lvl}.png", PUB / f"local/quality/{vp}-{lvl}.png", 480)
    for p in sorted((ART / "session").glob("*.png")):
        shrink(p, PUB / "session" / p.name, 480)
    if (ART / "session/session.json").exists():
        shutil.copy2(ART / "session/session.json", PUB / "session/session.json")
    for name in ["desktop", "mobile"]:
        frames = sorted((ART / f"recording/{name}").glob("*.png"))
        for tag, p in ([("first", frames[0]), ("middle", frames[len(frames) // 2]),
                        ("last", frames[-1])] if frames else []):
            shrink(p, PUB / f"local/recording/{name}-{tag}.png", 480)
    beauty = json.loads((ART / "beauty/beauty.json").read_text())
    (PUB / "beauty.json").write_text(json.dumps(beauty, indent=2))

    # ---- private: anything next to Target pixels --------------------------
    for vp in VPS:
        t = ART / f"target-typography/{vp}.png"
        cand = ART / f"beauty/{vp}/4-full-beauty.png"
        before = ART / f"beauty-before/{vp}/4-full-beauty.png"
        strip([(t, f"TARGET {vp}"), (before, "BEFORE"), (cand, "TYPOGRAPHY CANDIDATE")],
              PRIV / "target-before-candidate" / f"{vp}.png", scale=0.62)
        fifty_fifty(t, cand, PRIV / "fifty-fifty" / f"{vp}.png", "TARGET", "CANDIDATE")
        strip([(t, f"TARGET {vp}"), (cand, "CANDIDATE")],
              PRIV / "target-vs-candidate" / f"{vp}.png", scale=0.72)
    contact([(ART / f"beauty/{vp}/4-full-beauty.png", vp) for vp in VPS],
            PRIV / "contact-candidate.png")
    contact([(ART / f"target-typography/{vp}.png", f"T {vp}") for vp in VPS],
            PRIV / "contact-target.png")
    contact([(ART / f"beauty-before/{vp}/4-full-beauty.png", f"before {vp}") for vp in VPS],
            PRIV / "contact-before.png")
    for name in ["desktop", "mobile"]:
        gif(ART / f"recording/{name}", PRIV / f"beauty-recording-{name}.gif")
    for n in ["README.md", "MANIFEST.json", "target-typography-contract.json",
              "container-alignment.json", "depth-clipping.json", "label-ink.json",
              "quality-invariance.json", "render-loop-proof.json", "route-proof.json",
              "recording.json", "viewport-gate.json", "attribution.json"]:
        p = PUB / n
        if p.exists():
            shutil.copy2(p, PRIV / n)
    for d in ["docs/v5/SOURCE_EXACT_TYPOGRAPHY.md", "docs/v5/CURRENT_STATUS.md"]:
        if Path(d).exists():
            shutil.copy2(d, PRIV / Path(d).name)
    print("t1 evidence assembled")
