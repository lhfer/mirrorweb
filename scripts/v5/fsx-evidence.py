#!/usr/bin/env python3
"""Private review package for F2-SX. Target pixels stay under qa-v5/private/."""
from __future__ import annotations
import shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ART = Path("artifacts")
PRIV = Path("qa-v5/private/fsx")
GATE = ["1100x720", "1366x768", "1440x900", "1920x1080", "390x844", "844x390",
        "667x375", "700x700", "780x470", "1440x1080", "360x800", "500x900", "960x500", "960x720"]
FOCUS = ["390x844", "360x800", "700x700", "780x470", "1440x900", "1920x1080"]


def font(size=20):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", size)
    except OSError:
        return ImageFont.load_default()


def label(img, text):
    out = img.copy()
    d = ImageDraw.Draw(out)
    d.rectangle([0, 0, 14 + int(len(text) * 12), 32], fill=(0, 0, 0))
    d.text((8, 5), text, fill=(255, 255, 255), font=font())
    return out


def strip(pairs, out_path):
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
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return True


def overlay(target, local, out_path, tag):
    if not (Path(target).exists() and Path(local).exists()):
        return False
    a = Image.open(target).convert("RGB")
    b = Image.open(local).convert("RGB").resize(a.size)
    blend = Image.blend(a, b, 0.5)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    label(blend, f"OVERLAY 50/50 {tag}").save(out_path)
    return True


def gif(src_dir, out_path, cap=900, ms=420):
    src = sorted(Path(src_dir).glob("*.png"))
    if not src:
        return False
    W = max(Image.open(p).width for p in src)
    H = max(Image.open(p).height for p in src)
    frames = []
    for p in src:
        im = Image.open(p).convert("RGB")
        canvas = Image.new("RGB", (W, H), (12, 14, 20))
        canvas.paste(im, ((W - im.width) // 2, (H - im.height) // 2))
        canvas.thumbnail((cap, cap), Image.LANCZOS)
        frames.append(canvas)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(out_path, save_all=True, append_images=frames[1:], duration=ms, loop=0, optimize=True)
    return True


if __name__ == "__main__":
    PRIV.mkdir(parents=True, exist_ok=True)
    for vp in GATE:
        strip([(ART / f"f27/target-consensus/{vp}-f0.png", f"TARGET {vp}"),
               (ART / f"f27/models/v2/{vp}/01-rest.png", "CURRENT F2.7"),
               (ART / f"fsx/local/{vp}/01-rest.png", "SOURCE EXACT")],
              PRIV / "triptych" / f"{vp}.png")
    for vp in FOCUS:
        overlay(ART / f"f27/target-consensus/{vp}-f0.png",
                ART / f"fsx/local/{vp}/01-rest.png",
                PRIV / "overlay" / f"{vp}.png", vp)
    for name in ["gate.json", "source-contract.json", "runtime-assertions.json",
                 "default-proof.json", "detector-residual.json", "sphere-occlusion.json",
                 "target-layout-source.json", "f0-regression.json", "README.md"]:
        src = Path("qa-v5/fsx") / name
        if src.exists():
            shutil.copy2(src, PRIV / name)
    for d in ["docs/v5/SOURCE_EXACT_COMPOSITION.md", "docs/v5/TARGET_RESPONSIVE_SOURCE_FORENSICS.md",
              "config/target-layout-source-v2.json"]:
        shutil.copy2(d, PRIV / Path(d).name)
    print("assembled")
