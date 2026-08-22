#!/usr/bin/env python3
"""Unit tests for the O3 instrument corrections (§七).

The point of these is NEGATIVE: an instrument that cannot fail is not an
instrument. F11 in particular must genuinely FIRE on a non-monotonic
path, on a reversed path, on an over-large jump and on an unmeasurable
state -- so each of those is asserted here against synthetic input, and
this file is committed with the pre-registration, before the candidate
code exists.

Usage: o3-instrument-tests.py [--out=<json>]
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I = _load("o3_instruments", "o3_instruments.py")

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append({"test": name, "pass": bool(ok), "detail": detail})
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    return bool(ok)


# ------------------------------------------------------------- F11 -------
# The Target direction in every case below is DECREASING (0.70 -> 0.30).
TGT = (0.70, 0.50, 0.30)

v = I.f11_judge(TGT, (0.68, 0.52, 0.34))
check("F11 monotonic same-direction path passes", not v["fired"], str(v["reasons"]))

# The exact shape O2's published record showed while reporting fired=false.
v = I.f11_judge(TGT, (0.68, 0.34, 0.52))
check("F11 NON-MONOTONIC path fires", v["fired"], str(v["reasons"]))

v = I.f11_judge(TGT, (0.34, 0.52, 0.68))
check("F11 reversed-direction path fires", v["fired"], str(v["reasons"]))

v = I.f11_judge(TGT, (0.90, 0.88, 0.20))
check("F11 over-large adjacent jump fires", v["fired"], str(v["reasons"]))

v = I.f11_judge(TGT, (0.68, None, 0.34))
check("F11 unmeasurable candidate state fires", v["fired"], str(v["reasons"]))

# ---- the FLAT-REFERENCE branch, taken on the TARGET's range alone
v = I.f11_judge((0.5, 0.5, 0.5), (0.68, 0.52, 0.34))
check("F11 stationary target + large candidate swing fires",
      v["fired"] and v["branch"] == "flat-reference", str(v["reasons"]))

FLAT = (0.5156, 0.4885, 0.5009)          # the Target's own dry-run path
v = I.f11_judge(FLAT, (0.4879, 0.4624, 0.5066))   # the accepted O2 candidate
check("F11 flat branch is chosen from the TARGET range",
      v["branch"] == "flat-reference", v["branchChosenBy"])
check("F11 the ALREADY-ACCEPTED O2 candidate passes the corrected coding",
      not v["fired"],
      f"targetRange={v['targetRange']} candidateRange={v['candidateRange']} "
      f"{v['reasons']}")

v = I.f11_judge(FLAT, (0.20, 0.50, 0.80))
check("F11 flat branch still fires on a swing the target does not have",
      v["fired"], str(v["reasons"]))

v = I.f11_judge(FLAT, (0.50, 0.95, 0.50))
check("F11 flat branch still catches a pop", v["fired"], str(v["reasons"]))

# the branch must not be selectable from the candidate
a = I.f11_judge(FLAT, (0.49, 0.50, 0.51))
b = I.f11_judge(FLAT, (0.10, 0.50, 0.90))
check("F11 branch depends only on the target path",
      a["branch"] == b["branch"] == "flat-reference")
check("F11 same branch, opposite verdicts", not a["fired"] and b["fired"])

v = I.f11_judge(TGT, (0.70, 0.70, 0.30))
check("F11 flat-then-move stays monotonic and passes",
      not v["fired"], str(v["reasons"]))

# The published path and the verdict come from the SAME call: assert the
# record echoes its input, so a record can never show one path and a
# verdict computed from another.
v = I.f11_judge(TGT, (0.68, 0.34, 0.52))
check("F11 record echoes the judged path",
      v["candidateNxPath"] == [0.68, 0.34, 0.52] and v["targetNxPath"] == list(TGT))

# ---- glass reflection mask: static ink is excluded, movers survive
def synth_states(shift_px=0, pad=40):
    """One card painted into a larger frame, optionally SHIFTED on screen
    between pointer states -- which is what pointer parallax does. The
    label ink is fixed in CARD space in every state."""
    out = {}
    for i, s in enumerate(["pl", "rest", "pr"]):
        dx = (i - 1) * shift_px
        a = np.zeros((120 + 2 * pad, 120 + 2 * pad, 3), np.uint8)
        x0, y0 = pad + dx, pad
        a[y0 + 90:y0 + 100, x0 + 20:x0 + 100] = 255        # static label ink
        a[y0 + 40:y0 + 50, x0 + 10 + i * 40:x0 + 30 + i * 40] = 255  # mover
        out[s] = (Image.fromarray(a), (x0, y0, x0 + 120, y0 + 120))
    return out


states = synth_states(shift_px=0)
masks, excluded, dims = I.glass_reflection_masks(states)
cents = {s: I.centroid_of(m, dims) for s, m in masks.items()}
check("F11 mask excludes the static ink band",
      excluded is not None and bool(excluded[90:100, 20:100].all()))
check("F11 mask keeps the moving highlight",
      all(c is not None for c in cents.values()),
      str({k: (c and c["pixels"]) for k, c in cents.items()}))
if all(c is not None for c in cents.values()):
    ny = [c["ny"] for c in cents.values()]
    check("F11 mask centroid sits in the highlight band, not the label band",
          all(0.3 < y < 0.5 for y in ny), str(ny))
    path = tuple(c["nx"] for c in cents.values())
    vv = I.f11_judge((0.2, 0.5, 0.8), path)
    check("F11 synthetic left-to-right sweep passes", not vv["fired"], str(path))

# THE PARALLAX CASE: the card shifts on screen between pointer states, as it
# really does. Card-space comparison must still remove the ink; a shared
# screen rect would not, and the ink would be scored as glass.
shifted = synth_states(shift_px=8)
m_s, exc_s, dims_s = I.glass_reflection_masks(shifted)
check("F11 card-space intersection still excludes ink when the card SHIFTS",
      exc_s is not None and bool(exc_s[90:100, 20:100].all()),
      f"excluded px={int(exc_s.sum()) if exc_s is not None else None}")
c_s = {s: I.centroid_of(m, dims_s) for s, m in m_s.items()}
check("F11 shifted-card mover survives and stays out of the label band",
      all(c is not None and 0.3 < c["ny"] < 0.5 for c in c_s.values()),
      str({k: (v and (v["nx"], v["ny"], v["pixels"])) for k, v in c_s.items()}))
# and the demonstration that a shared screen rect is NOT good enough
shared_rect = shifted["rest"][1]
naive = {s: (img, shared_rect) for s, (img, _) in shifted.items()}
_, exc_naive, _ = I.glass_reflection_masks(naive)
check("F11 shared-screen-rect comparison would have LEAKED the ink "
      "(this is why card space is used)",
      exc_naive is not None and not bool(exc_naive[90:100, 20:100].all()))

# an all-static frame leaves nothing to measure -> must fire, not pass
one = states["rest"]
flat = {s: one for s in ["pl", "rest", "pr"]}
m2, _, dims2 = I.glass_reflection_masks(flat)
c2 = [I.centroid_of(m2[s], dims2) for s in ["pl", "rest", "pr"]]
check("F11 empty glass mask fires (no pass by default)",
      I.f11_judge((0.2, 0.5, 0.8),
                  tuple(None if c is None else c["nx"] for c in c2))["fired"])

# -------------------------------------------------------------- F5 -------
r = I.f5_interior_change(
    {"interiorSaturationMean": 0.0000, "interiorLuminanceMean": 100.0,
     "interiorChromaMean": 0.0},
    {"interiorSaturationMean": 0.0104, "interiorLuminanceMean": 103.0,
     "interiorChromaMean": 0.14})
check("F5 zero baseline selects the ABSOLUTE coding", r["coding"] == "absolute")
check("F5 accepted-O2-scale absolute gain does not fire", not r["fired"], str(r))

r = I.f5_interior_change(
    {"interiorSaturationMean": 0.0000, "interiorLuminanceMean": 100.0,
     "interiorChromaMean": 0.0},
    {"interiorSaturationMean": 0.0500, "interiorLuminanceMean": 100.0,
     "interiorChromaMean": 9.0})
check("F5 large absolute interior gain FIRES on a zero baseline", r["fired"], str(r))

r = I.f5_interior_change(
    {"interiorSaturationMean": 0.4000, "interiorLuminanceMean": 100.0,
     "interiorChromaMean": 60.0},
    {"interiorSaturationMean": 0.3000, "interiorLuminanceMean": 100.0,
     "interiorChromaMean": 45.0})
check("F5 healthy baseline selects the RELATIVE coding", r["coding"] == "relative")
check("F5 25% relative desaturation FIRES", r["fired"], str(r))

r = I.f5_interior_change(
    {"interiorSaturationMean": 0.4000, "interiorLuminanceMean": 100.0,
     "interiorChromaMean": 60.0},
    {"interiorSaturationMean": 0.4000, "interiorLuminanceMean": 130.0,
     "interiorChromaMean": 60.0})
check("F5 30% interior brightening FIRES on luminance", r["fired"], str(r))

# the coding must be a function of the BASELINE alone
a = I.f5_interior_change({"interiorSaturationMean": 0.005, "interiorLuminanceMean": 50.0,
                          "interiorChromaMean": 1.0},
                         {"interiorSaturationMean": 0.9, "interiorLuminanceMean": 50.0,
                          "interiorChromaMean": 200.0})
b = I.f5_interior_change({"interiorSaturationMean": 0.005, "interiorLuminanceMean": 50.0,
                          "interiorChromaMean": 1.0},
                         {"interiorSaturationMean": 0.005, "interiorLuminanceMean": 50.0,
                          "interiorChromaMean": 1.0})
check("F5 coding depends only on the baseline", a["coding"] == b["coding"] == "absolute")
check("F5 absolute coding still fires on a huge candidate", a["fired"] and not b["fired"])

# ------------------------------------------------------------- F10 -------
# Two 40x40 cards side by side with a 20px gutter; ink painted in the gutter
# must be seen, ink on a card must not.
img = np.zeros((100, 140, 3), np.uint8)
quadA = [(10, 10), (50, 10), (50, 50), (10, 50)]
quadB = [(70, 10), (110, 10), (110, 50), (70, 50)]
verdicts = {"A": {"draw": True, "quad": quadA}, "B": {"draw": True, "quad": quadB}}

DIL = 4  # synthetic frames have a 20px gap; a third of it
clean = I.f10_gutter_ink(Image.fromarray(img), verdicts, DIL)
check("F10 clean frame has zero gutter ink", clean["gutterInkRatio"] == 0.0, str(clean))

on_card = img.copy()
on_card[15:45, 15:45] = 255
r = I.f10_gutter_ink(Image.fromarray(on_card), verdicts, DIL)
check("F10 ink INSIDE a card is not gutter", r["gutterInkRatio"] == 0.0, str(r))

in_gutter = img.copy()
in_gutter[20:40, 56:64] = 255
r = I.f10_gutter_ink(Image.fromarray(in_gutter), verdicts, DIL)
check("F10 ink BETWEEN cards is counted", r["gutterInkRatio"] > 0.0, str(r))

# a partially-visible neighbour must be masked as a card, not scored as gutter
partial = img.copy()
partial[10:50, 0:20] = 255
vpart = dict(verdicts)
vpart["C"] = {"draw": True, "quad": [(-30, 10), (20, 10), (20, 50), (-30, 50)]}
r_masked = I.f10_gutter_ink(Image.fromarray(partial), vpart, DIL)
r_unmasked = I.f10_gutter_ink(Image.fromarray(partial), verdicts, DIL)
check("F10 partially-visible neighbour card is masked, not counted as gutter",
      r_masked["gutterInkRatio"] == 0.0 and r_unmasked["gutterInkRatio"] > 0.0,
      f"masked={r_masked} unmasked={r_unmasked}")

# the polygon, not its bounding box: a rotated card leaves real gutter visible
rot = img.copy()
rot[8:12, 8:12] = 255                       # a corner OUTSIDE the diamond
diamond = [(30, 5), (55, 30), (30, 55), (5, 30)]
r = I.f10_gutter_ink(Image.fromarray(rot), {"D": {"draw": True, "quad": diamond}}, DIL)
check("F10 masks the polygon, not the bounding box", r["gutterInkRatio"] > 0.0, str(r))

check("F10 dilation law scales with the card width",
      I.f10_dilation_for(547.2) == 8 and I.f10_dilation_for(280.8) == 4
      and I.f10_dilation_for(10) >= I.F10_MIN_DILATION_PX,
      f"1440x900->{I.f10_dilation_for(547.2)} 390x844->{I.f10_dilation_for(280.8)}")

# --------------------------------------------------------------------------
failed = [r for r in RESULTS if not r["pass"]]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} instrument tests pass")
args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
if "out" in args:
    p = Path(args["out"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "what": "O3 instrument unit tests -- the corrected F5 / F10 / F11 "
                "codings must genuinely FAIL on bad input",
        "total": len(RESULTS), "failed": len(failed),
        "pass": not failed, "tests": RESULTS}, indent=1))
sys.exit(1 if failed else 0)
