#!/usr/bin/env python3
"""O5R -- the two overlays §十五 names, drawn so a reviewer can see the finding.

Numbers alone cannot settle a colour question. Item 4 says the candidate carries
about twice the Target's chroma on a coarse achromatic edge; item 4 ALSO says
the candidate reproduces the Target's checker chroma that the control misses by
twenty-fold. Those are opposite readings out of one instrument, and a reviewer
should be able to look at both.

Two overlays, each a strip of four lanes in the fixed order Target, current,
O5 clamped, O5R unclamped:

  grayscale false-colour -- the render above, its chroma below, on media that
    has no colour in it at all. Anything visible in the lower half is colour
    the body invented.

  checker spectral -- the same construction on hf-checker, where the Target
    DOES carry edge colour. Here the lower half is what the candidate is
    supposed to reproduce, and the control's near-black panel is the failure.

The chroma map is scaled by a FIXED constant across every panel and every
figure. A per-panel autoscale would make every lane look alike, which is the
one thing an overlay must not do.

Output: artifacts/optics-o5r/overlays/
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent.parent
HERE = REPO / "scripts/v5"
MD = REPO / "artifacts/optics-o5r/measure"
OUT = REPO / "artifacts/optics-o5r/overlays"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I = _load("o5r_instruments", "o5r_instruments.py")
G = _load("o5r_gate", "o5r-gate.py")

MAN = json.loads((MD / "measure-manifest.json").read_text())
LANES = [("target", "Target"), ("control", "current (shipped)"),
         ("o5-clamped", "O5 target-source"),
         ("o5r-unclamped", "O5R unclamped")]
# Fixed full-scale for the chroma map, in 8-bit chroma units. Chosen once, from
# the largest interior chroma any lane reaches on these assets (hf-checker, ~80)
# with headroom, and applied to every panel.
CHROMA_FULL_SCALE = 96.0
PANEL_W = 300
GUTTER = 8
LABEL_H = 18


def shot(lane, asset, vp):
    for r in MAN["records"]:
        if r.get("asset") != asset or r.get("vp") != vp:
            continue
        if r.get("state") != "rest":
            continue
        if lane == "target":
            if r.get("kind") == "target" and (r.get("repeat") or 0) == 0:
                return MD / r["file"]
        elif r.get("kind") == "lane" and r.get("lane") == lane:
            return MD / r["file"]
    return None


def heat(c: np.ndarray) -> np.ndarray:
    """Chroma -> a perceptually ordered ramp: black, blue, magenta, white.

    Deliberately not a rainbow. A rainbow map would put its own colour into a
    figure whose entire subject is invented colour.
    """
    t = np.clip(c / CHROMA_FULL_SCALE, 0.0, 1.0)
    r = np.clip(t * 2.2 - 0.35, 0, 1)
    g = np.clip(t * 2.0 - 1.05, 0, 1)
    b = np.clip(t * 2.6, 0, 1)
    return (np.stack([r, g, b], -1) * 255).astype(np.uint8)


def card_crop(path, rect):
    a = I.rgb(Image.open(path).convert("RGB"))
    x0, y0, x1, y1 = rect
    return a[y0:y1, x0:x1]


def strip(asset, vp, title, note):
    rect = G.RECTS[vp][0][0]
    panels = []
    for lane, label in LANES:
        p = shot(lane, asset, vp)
        if p is None:
            return None
        blk = card_crop(p, rect)
        h, w = blk.shape[:2]
        scale = PANEL_W / w
        ph = max(1, int(round(h * scale)))
        top = Image.fromarray(blk.astype(np.uint8)).resize(
            (PANEL_W, ph), Image.LANCZOS)
        bot = Image.fromarray(heat(I.chroma(blk))).resize(
            (PANEL_W, ph), Image.NEAREST)
        panels.append((label, top, bot,
                       float(I.chroma(blk).mean()),
                       float(np.percentile(I.chroma(blk), 99.5))))

    ph = panels[0][1].height
    W = len(panels) * PANEL_W + (len(panels) + 1) * GUTTER
    H = LABEL_H * 2 + ph * 2 + GUTTER * 4 + LABEL_H * 2 + 26
    canvas = Image.new("RGB", (W, H), (16, 16, 18))
    d = ImageDraw.Draw(canvas)
    d.text((GUTTER, 4), title, fill=(235, 235, 240))
    d.text((GUTTER, 4 + LABEL_H), note, fill=(150, 150, 158))
    y = LABEL_H * 2 + 6
    for i, (label, top, bot, cmean, c995) in enumerate(panels):
        x = GUTTER + i * (PANEL_W + GUTTER)
        d.text((x, y), label, fill=(220, 220, 226))
        canvas.paste(top, (x, y + LABEL_H))
        canvas.paste(bot, (x, y + LABEL_H + ph + GUTTER))
        d.text((x, y + LABEL_H + ph * 2 + GUTTER * 2),
               f"chroma mean {cmean:5.2f}  p99.5 {c995:6.2f}",
               fill=(190, 190, 198))
    d.text((GUTTER, H - 20),
           f"upper: render.  lower: chroma, fixed full scale "
           f"{CHROMA_FULL_SCALE:.0f} across every panel and figure.",
           fill=(140, 140, 148))
    return canvas


FIGURES = [
    ("grayscale-false-colour", "grayscale-step",
     "grayscale false colour -- media with no colour in it",
     "anything visible in the lower half is colour the body invented"),
    ("grayscale-false-colour", "bw-split",
     "grayscale false colour -- one hard achromatic edge",
     "the coarse edge item 4 fails on: candidate edge chroma is about twice "
     "the Target's"),
    ("checker-spectral", "hf-checker",
     "checker spectral structure -- media the Target DOES colour",
     "here the lower half is the thing to reproduce; the control's near-black "
     "panel is the failure"),
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for kind, asset, title, note in FIGURES:
        for vp in ("1440x900", "390x844", "844x390", "700x700"):
            if kind == "grayscale-false-colour" and vp in ("844x390", "700x700"):
                continue
            fig = strip(asset, vp, f"{title}   [{vp}]", note)
            if fig is None:
                continue
            name = f"{kind}-{asset}-{vp}.png"
            fig.save(OUT / name)
            made.append(name)
            print(f"  {name}")
    (OUT / "overlays-manifest.json").write_text(json.dumps({
        "what": "§十五 overlays. Four lanes in a fixed order, render above and "
                "chroma below, one fixed chroma full scale across every panel "
                "so the panels can be compared to each other.",
        "chromaFullScale": CHROMA_FULL_SCALE,
        "laneOrder": [l for l, _ in LANES],
        "files": made,
    }, indent=1))
    print(f"\n{len(made)} overlays -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
