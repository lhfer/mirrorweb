#!/usr/bin/env python3
"""Coverage overlays for the private review package.

One panel per lane x viewport x state: the strict viewport, the 64 px margin
band, every ACTIVE slot's replayed AABB coloured by verdict, the slot code at
its centre, and the lane's own DOM state as a centre dot -- so a mismatch
between what the rule says and what the page did is visible at a glance, not
buried in a JSON.

Colours:
  green   drawn AND strict-visible (the half-area interactive flag)
  amber   drawn only -- alive in the 64 px margin band
  red     culled (outline only, faded with distance from the band)
  dot     the DOM: white filled = visibility:visible, red ring = hidden
          (a red ring inside a green box IS a rule/DOM disagreement)

Usage: v0-overlays.py --target=<trace> --before=<trace> --candidate=<trace>
                      --outdir=<dir>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


VC = _load("v0_culling", "v0_culling.py")
SL = sys.modules["source_layout"]

STATES = ["rest", "pointer-corner-br", "slow-horizontal-drag", "fast-flick"]
MARGIN = 64.0
PAD = 140  # canvas padding around the margin band, world px


def pick_frame(run):
    """Rest/pointer states: the settled last frame. Gestures: the frame with
    the most labels in flight (mid-gesture, where culling is working)."""
    frames = [f for f in run["frames"] if f["w"] == run["frames"][0]["w"]]
    if run["state"] in ("rest", "pointer-centre") or run["state"].startswith("pointer-corner"):
        return frames[-1]
    best, best_v = frames[len(frames) // 2], -1
    for f in frames:
        v = sum(1 for rec in f["labels"] if rec is not None)
        if v > best_v:
            best, best_v = f, v
    return best


def replay(run, f, lane):
    frame = SL.layout(f["w"], f["h"])
    if lane == "target":
        pos = VC.parse_camera_position(f["camera"])
        if pos is None:
            return None, frame
        cam = VC.camera_from_recorded_position(pos, frame)
        sc = VC.recover_scroll(run["pool"], f["labels"], frame)
        if sc is None:
            return None, frame
        return VC.frame_verdicts(sc[0], sc[1], cam, frame), frame
    if not f.get("truth"):
        return None, frame
    cam = VC.coverage_camera(f["truth"][2], f["truth"][3], frame)
    return VC.frame_verdicts(f["truth"][0], f["truth"][1], cam, frame), frame


def draw_panel(run, lane, out_path):
    f = pick_frame(run)
    pred, frame = replay(run, f, lane)
    w, h = f["w"], f["h"]
    scale = min(1.0, 1240.0 / (w + 2 * (MARGIN + PAD)))
    ox, oy = MARGIN + PAD, MARGIN + PAD

    def pt(x, y):
        return ((x + ox) * scale, (y + oy) * scale)

    cw = int((w + 2 * (MARGIN + PAD)) * scale)
    ch = int((h + 2 * (MARGIN + PAD)) * scale) + 40
    img = Image.new("RGB", (cw, ch), (14, 15, 18))
    d = ImageDraw.Draw(img)

    # margin band, then strict viewport
    d.rectangle([pt(-MARGIN, -MARGIN), pt(w + MARGIN, h + MARGIN)],
                outline=(90, 90, 100), width=1)
    d.rectangle([pt(0, 0), pt(w, h)], outline=(230, 230, 235), width=2)

    obs = {run["pool"][i]: rec for i, rec in enumerate(f["labels"])}
    drawn = culled = 0
    if pred:
        for code, v in pred.items():
            if not v["aabb"]:
                continue
            x0, y0, x1, y1 = v["aabb"]
            # skip boxes far outside the canvas
            if x1 < -MARGIN - PAD or x0 > w + MARGIN + PAD \
                    or y1 < -MARGIN - PAD or y0 > h + MARGIN + PAD:
                continue
            if v["draw"] and v["interactive"]:
                colour, width = (70, 200, 120), 2
            elif v["draw"]:
                colour, width = (235, 190, 80), 2
            else:
                colour, width = (200, 80, 80), 1
            drawn += 1 if v["draw"] else 0
            culled += 0 if v["draw"] else 1
            d.rectangle([pt(x0, y0), pt(x1, y1)], outline=colour, width=width)
            cx, cy = pt((x0 + x1) / 2, (y0 + y1) / 2 - 12)
            d.text((cx - 8, cy), f"{code:02d}", fill=colour)
            dot = pt((x0 + x1) / 2, (y0 + y1) / 2 + 8)
            visible = obs.get(code) is not None
            if visible:
                d.ellipse([dot[0] - 4, dot[1] - 4, dot[0] + 4, dot[1] + 4],
                          fill=(255, 255, 255))
            else:
                d.ellipse([dot[0] - 4, dot[1] - 4, dot[0] + 4, dot[1] + 4],
                          outline=(255, 90, 90), width=2)
    else:
        # No replay possible (a lane state with no truth): draw the DOM alone.
        for code, rec in obs.items():
            if rec is None:
                continue
            x0, y0 = rec[3], rec[4]
            d.rectangle([pt(x0, y0), pt(x0 + rec[5], y0 + rec[6])],
                        outline=(160, 160, 170), width=1)
            cx, cy = pt(x0 + rec[5] / 2, y0 + rec[6] / 2)
            d.text((cx - 8, cy - 6), f"{code:02d}", fill=(160, 160, 170))

    n_vis = sum(1 for rec in f["labels"] if rec is not None)
    d.text((8, ch - 32),
           f"{lane}  {run['viewport']}  {run['state']}  t={f['t']:.0f}ms  "
           f"DOM visible {n_vis}/{len(run['pool'])}"
           + (f"  rule drawn {drawn}" if pred else "  (no rule replay: DOM only)"),
           fill=(220, 220, 225))
    d.text((8, ch - 18),
           "green = drawn+strict   amber = margin band   red = culled   "
           "white dot = DOM visible   red ring = DOM hidden",
           fill=(150, 150, 158))
    img.save(out_path)


def main() -> int:
    args = {}
    for a in sys.argv[1:]:
        k, v = a[2:].split("=", 1)
        args[k] = v
    outdir = Path(args["outdir"])
    outdir.mkdir(parents=True, exist_ok=True)
    count = 0
    for lane in ("target", "before", "candidate"):
        trace = json.loads(Path(args[lane]).read_text())
        for run in trace["runs"]:
            if run["state"] not in STATES:
                continue
            out = outdir / f"{lane}-{run['viewport']}-{run['state']}.png"
            draw_panel(run, lane, out)
            count += 1
    print(f"wrote {count} overlay panels to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
