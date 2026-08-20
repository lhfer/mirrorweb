#!/usr/bin/env python3
"""
Assemble the F2.7 evidence tree and the private review package.

Anything embedding Target pixels goes under qa-v5/private/, which is git-ignored.
qa-v5/f27/ carries local pixels and Target-derived NUMBERS only.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ART = Path("artifacts/f27")
PUB = Path("qa-v5/f27")
PRIV = Path("qa-v5/private/f27")

GATE = ["1100x720", "1366x768", "1440x900", "1920x1080", "390x844", "844x390",
        "667x375", "700x700", "780x470", "1440x1080", "360x800", "500x900", "960x500", "960x720"]
PHASE = ["667x375", "700x700", "780x470", "1440x1080", "900x899", "700x900"]
PORTRAIT = ["360x800", "390x700", "414x896", "430x932", "500x900", "390x844",
            "375x812", "393x852", "428x926", "700x900"]


def label(img, text):
    out = img.copy()
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 20)
    except OSError:
        font = ImageFont.load_default()
    d.rectangle([0, 0, 14 + int(len(text) * 12), 32], fill=(0, 0, 0))
    d.text((8, 5), text, fill=(255, 255, 255), font=font)
    return out


def side_by_side(pairs, out_path, scale=1.0):
    imgs = [label(Image.open(p).convert("RGB"), t) for p, t in pairs if Path(p).exists()]
    if not imgs:
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


def contact_sheet(items, out_path, cols=5, cell=300):
    tiles = []
    for p, t in items:
        if not Path(p).exists():
            continue
        im = Image.open(p).convert("RGB")
        im.thumbnail((cell, cell), Image.LANCZOS)
        pad = Image.new("RGB", (cell, cell + 26), (12, 14, 20))
        pad.paste(im, ((cell - im.width) // 2, 26 + (cell - im.height) // 2))
        d = ImageDraw.Draw(pad)
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 16)
        except OSError:
            font = ImageFont.load_default()
        d.text((6, 4), t, fill=(220, 230, 255), font=font)
        tiles.append(pad)
    if not tiles:
        return False
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 26)), (12, 14, 20))
    for n, t in enumerate(tiles):
        sheet.paste(t, ((n % cols) * cell, (n // cols) * (cell + 26)))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    return True


if __name__ == "__main__":
    PUB.mkdir(parents=True, exist_ok=True)
    PRIV.mkdir(parents=True, exist_ok=True)

    # ---- public: local pixels + numbers only -----------------------------
    for vp in GATE:
        src = ART / "models/v2" / vp
        dst = PUB / "local" / vp
        dst.mkdir(parents=True, exist_ok=True)
        for f in ["01-rest.png", "01-rest.json", "manifest.json"]:
            if (src / f).exists():
                shutil.copy2(src / f, dst / f)
    for name, src in [("gate.json", ART / "gate-v2/gate.json"),
                      ("gate-control-f26r.json", ART / "gate-control/gate.json"),
                      ("gate-diagnostic-landscape-row-origin.json", ART / "gate-diagnostic/gate.json"),
                      ("f0-regression.json", ART / "f0-gate/gate.json")]:
        if src.exists():
            shutil.copy2(src, PUB / name)

    # ---- private: anything with Target pixels ----------------------------
    for vp in GATE:
        t = ART / f"target-consensus/{vp}-f0.png"
        l = ART / f"models/v2/{vp}/01-rest.png"
        side_by_side([(t, f"TARGET {vp}"), (l, f"LOCAL v2 {vp}")], PRIV / "gate-overlays" / f"{vp}.png")
    for vp in PHASE:
        b = ART / f"control-f26r/{vp}/01-rest.png"
        a = ART / f"models/v2/{vp}/01-rest.png"
        t = ART / f"target-consensus/{vp}-f0.png"
        side_by_side([(t, f"TARGET {vp}"), (b, "BEFORE aspect rule"), (a, "AFTER row-origin")],
                     PRIV / "phase-before-after" / f"{vp}.png")
    for m in ["v0", "v1", "v2"]:
        side_by_side([(ART / "target-consensus/390x844-f0.png", "TARGET 390x844"),
                      (ART / f"models/{m}/390x844/01-rest.png", f"LOCAL {m.upper()}")],
                     PRIV / "390x844-models" / f"{m}.png")
    side_by_side([(ART / "target-consensus/390x844-f0.png", "TARGET"),
                  (ART / "models/v0/390x844/01-rest.png", "V0 control"),
                  (ART / "models/v1/390x844/01-rest.png", "V1 scaleY"),
                  (ART / "models/v2/390x844/01-rest.png", "V2 scaleY+restY0")],
                 PRIV / "390x844-models/all.png")
    contact_sheet([(ART / f"models/v2/{vp}/01-rest.png", vp) for vp in PORTRAIT],
                  PRIV / "portrait-contact-sheet.png")
    contact_sheet([(ART / f"target-consensus/{vp}-f0.png", f"T {vp}") for vp in PORTRAIT],
                  PRIV / "portrait-contact-sheet-target.png")
    print("evidence assembled")
