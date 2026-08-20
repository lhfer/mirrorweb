#!/usr/bin/env python3
"""FSX-A evidence: public beauty frames and numbers, private Target comparisons."""
from __future__ import annotations
import json, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ART = Path("artifacts")
PUB = Path("qa-v5/fsx-a")
PRIV = Path("qa-v5/private/fsx-a")
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
    sheet.save(out_path)
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
    sheet.save(out_path)
    return True


def gif(src_dir, out_path, cap=820, ms=380):
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
    frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=ms, loop=0, optimize=True)
    return True


if __name__ == "__main__":
    PUB.mkdir(parents=True, exist_ok=True)
    PRIV.mkdir(parents=True, exist_ok=True)
    # Public: local pixels only, downsampled so the tree stays reviewable.
    for vp in VPS:
        for st in STATES:
            src = ART / f"fsx-a/beauty/{vp}/{st}.png"
            if not src.exists():
                continue
            dst = PUB / "beauty" / vp / f"{st}.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            im = Image.open(src).convert("RGB")
            # 720, matching what is committed. This used to be 900, so re-running
            # the script re-encoded 20 tracked frames and silently invalidated
            # every SHA in MANIFEST.json -- an evidence bundle that no longer
            # verified against its own manifest.
            im.thumbnail((720, 720), Image.LANCZOS)
            im.save(dst, optimize=True)
    shutil.copy2(ART / "fsx-a/beauty/beauty.json", PUB / "beauty" / "beauty.json")

    # Private: anything alongside Target pixels, plus full-resolution states.
    for vp in VPS:
        strip([(ART / f"fsx-a/beauty/{vp}/{s}.png", s) for s in STATES],
              PRIV / "states" / f"{vp}.png", scale=0.55)
        strip([(ART / f"f27/target-consensus/{vp}-f0.png", f"TARGET {vp}"),
               (ART / f"fsx-a/beauty/{vp}/4-full-beauty.png", "SOURCE EXACT full beauty")],
              PRIV / "target-vs-beauty" / f"{vp}.png")
        strip([(ART / f"fsx-a/beauty/{vp}/3-glass-media.png", "labels OFF"),
               (ART / f"fsx-a/beauty/{vp}/4-full-beauty.png", "labels ON")],
              PRIV / "labels-off-on" / f"{vp}.png", scale=0.7)
        strip([(ART / f"fsx-a/beauty/{vp}/2-media-only.png", "media only, glass OFF"),
               (ART / f"fsx-a/beauty/{vp}/3-glass-media.png", "glass + media")],
              PRIV / "media-vs-glass" / f"{vp}.png", scale=0.7)
    contact([(ART / f"fsx-a/beauty/{vp}/4-full-beauty.png", vp) for vp in VPS],
            PRIV / "contact-sourceexact-full-beauty.png")
    contact([(ART / f"f27/target-consensus/{vp}-f0.png", f"T {vp}") for vp in VPS],
            PRIV / "contact-target.png")
    for name in ["desktop", "mobile"]:
        gif(ART / f"fsx-a/recording/{name}", PRIV / f"beauty-recording-{name}.gif")
    for n in ["README.md", "route-proof.json", "quality-invariance.json",
              "detector-residual-v2.json", "MANIFEST.json"]:
        p = PUB / n
        if p.exists():
            shutil.copy2(p, PRIV / n)
    if (PUB / "beauty/attribution.json").exists():
        shutil.copy2(PUB / "beauty/attribution.json", PRIV / "attribution.json")
    for d in ["docs/v5/FSX_ACCEPTANCE.md", "docs/v5/SOURCE_EXACT_COMPOSITION.md"]:
        if Path(d).exists():
            shutil.copy2(d, PRIV / Path(d).name)
    print("assembled")
