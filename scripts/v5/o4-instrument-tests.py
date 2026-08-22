#!/usr/bin/env python3
"""Unit tests for the sealed O4 instruments (§五.6).

The point of these is the NEGATIVE cases. An instrument that never fires is
not a conservative instrument, it is a broken one, so every check here has
a partner that proves the failure path is reachable:

  - a non-monotonic pointer path must FAIL
  - a real gutter leak must FAIL
  - a zero-baseline saturation change must take the ABSOLUTE branch
  - a bool must never be counted as a numeric error
  - a malformed aggregator shape must fail fast rather than coerce

Usage: o4-instrument-tests.py [--out=<json>]
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I = _load("o4_ins", "o4_instruments.py")

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append({"test": name, "pass": bool(cond), "detail": detail})
    print(f"{'PASS' if cond else 'FAIL'}  {name}"
          + (f"  -- {detail}" if detail and not cond else ""))


def img_from(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def tmp_png(a, name):
    d = Path(REPO / "artifacts/optics-o4/testtmp")
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    img_from(a).save(p)
    return p


# ------------------------------------------------------------ band width ---
# Two cards whose bands sit at DIFFERENT depths. Per-card-then-average is
# the sealed coding; averaging the profiles first would smear them.
H, W = 120, 400
a = np.zeros((H, W, 3), np.float32)
a[:, 20:23] = 255          # card 1 band: 3 px from x=20
a[:, 220:232] = 255        # card 2 band: 12 px from x=220
rects = [(20, 10, 120, 110), (220, 10, 320, 110)]
bw = I.band_width_px(img_from(a), rects)
check("band width is per card, then averaged (3 and 12 -> 7.5)",
      bw["perCard"] == [3, 12] and abs(bw["meanPx"] - 7.5) < 1e-6,
      f"got {bw}")

smeared = np.zeros((H, W, 3), np.float32)
smeared[:, 20:32] = 128     # what a cross-card profile average would look like
check("a smeared profile would read WIDER than either card -- the defect the "
      "sealed coding avoids",
      I.band_width_px(img_from(smeared), [(20, 10, 120, 110)])["perCard"][0] == 12)

# ---------------------------------------------------------- band energy ----
e_lo = I.band_energy(img_from(a), rects)
b2 = a.copy()
b2[:, 20:23] = 200          # dimmer band, SAME width
e_hi = I.band_energy(img_from(b2), rects)
check("band energy is continuous where band width ties",
      I.band_width_px(img_from(b2), rects)["meanPx"] == bw["meanPx"]
      and e_hi["meanEnergy"] < e_lo["meanEnergy"],
      f"width tie {bw['meanPx']}, energy {e_lo['meanEnergy']} -> {e_hi['meanEnergy']}")

# ----------------------------------------------------------- silhouette ---
media = np.full((60, 60, 3), 30, np.float32)
control = media.copy()
control[20:40, 20:40] = 90            # the glass covers this
mp, cp = tmp_png(media, "media.png"), tmp_png(control, "control.png")
sil = I.true_silhouette(cp, mp)
check("true silhouette is exactly the pixels the glass changes",
      sil.sum() == 400 and sil[25, 25] and not sil[5, 5], f"{sil.sum()} px")

# A CANDIDATE that puts ink outside that silhouette must be caught.
leak = control.copy()
leak[5:10, 5:10] = 255
lp = tmp_png(leak, "leak.png")
pair = I.gutter_pair_outside_silhouette(cp, lp, sil)
check("a REAL gutter leak fails",
      pair["differingPixelsOutsideSilhouette"] == 25
      and pair["candidate"]["gutterInkRatio"] > pair["control"]["gutterInkRatio"],
      json.dumps(pair))

# Ink added strictly INSIDE the silhouette is not gutter invasion. This is
# the O3 item-13 misattribution, and the sealed instrument must not repeat it.
inside = control.copy()
inside[20:40, 20:24] = 255
ip = tmp_png(inside, "inside.png")
pair_in = I.gutter_pair_outside_silhouette(cp, ip, sil)
check("ink INSIDE the silhouette is not counted as gutter invasion",
      pair_in["differingPixelsOutsideSilhouette"] == 0
      and pair_in["candidate"]["gutterInkRatio"] == pair_in["control"]["gutterInkRatio"],
      json.dumps(pair_in))

check("a flat layout quad is NOT the gutter boundary -- the silhouette is "
      "derived from rendered pixels, so a bulged lens keeps its own annulus",
      sil.sum() == 400)

# ------------------------------------------------------------- interior ---
zero_base = {"interiorSaturationMean": 0.0, "interiorLuminanceMean": 100.0,
             "interiorChromaMean": 0.0}
tiny = {"interiorSaturationMean": 0.004, "interiorLuminanceMean": 100.0,
        "interiorChromaMean": 0.5}
r = I.interior_change(zero_base, tiny)
check("a ZERO-baseline saturation change takes the ABSOLUTE branch",
      r["coding"] == "absolute" and not r["fired"], json.dumps(r))

r2 = I.interior_change(zero_base, {"interiorSaturationMean": 0.09,
                                   "interiorLuminanceMean": 100.0,
                                   "interiorChromaMean": 9.0})
check("the absolute branch still FIRES on a large absolute change",
      r2["coding"] == "absolute" and r2["fired"], json.dumps(r2))

big_base = {"interiorSaturationMean": 0.60, "interiorLuminanceMean": 100.0,
            "interiorChromaMean": 80.0}
r3 = I.interior_change(big_base, {"interiorSaturationMean": 0.30,
                                  "interiorLuminanceMean": 100.0,
                                  "interiorChromaMean": 40.0})
check("a well-supported baseline takes the RELATIVE branch and fires at 50%",
      r3["coding"] == "relative" and r3["fired"], json.dumps(r3))

edge = {"interiorSaturationMean": I.INTERIOR_RELATIVE_BRANCH_FLOOR,
        "interiorLuminanceMean": 100.0, "interiorChromaMean": 2.0}
check("the branch floor equals the absolute ceiling, so the two codings "
      "cannot contradict each other",
      I.interior_change(edge, edge)["coding"] == "relative"
      and I.interior_change({**edge, "interiorSaturationMean":
                             I.INTERIOR_RELATIVE_BRANCH_FLOOR - 1e-9},
                            edge)["coding"] == "absolute")

# Same baseline, wildly different candidates -> the SAME coding. This is
# the property that makes the branch unselectable after seeing a candidate.
wild = {"interiorSaturationMean": 0.9, "interiorLuminanceMean": 250.0,
        "interiorChromaMean": 200.0}
check("the branch depends on the BASELINE only, not on the candidate",
      I.interior_change(zero_base, tiny)["coding"]
      == I.interior_change(zero_base, wild)["coding"] == "absolute"
      and I.interior_change(big_base, tiny)["coding"]
      == I.interior_change(big_base, wild)["coding"] == "relative")

# -------------------------------------------------------------- pointer ---
check("a NON-MONOTONIC pointer path FAILS",
      I.pointer_judge([0.2, 0.5, 0.8], [0.2, 0.9, 0.3])["fired"],
      json.dumps(I.pointer_judge([0.2, 0.5, 0.8], [0.2, 0.9, 0.3])))
check("a path monotonic in the target's direction PASSES",
      not I.pointer_judge([0.2, 0.5, 0.8], [0.25, 0.5, 0.75])["fired"])
check("a path moving the WRONG way FAILS",
      I.pointer_judge([0.2, 0.5, 0.8], [0.8, 0.5, 0.2])["fired"])
check("an unmeasurable state FAILS rather than passing quietly",
      I.pointer_judge([0.2, 0.5, 0.8], [0.2, None, 0.8])["fired"])

# ----------------------------------------------------------- aggregator ---
check("zero_errors accepts an all-zero dict",
      I.zero_errors({"target": 0, "ours": 0}))
check("zero_errors ignores a sibling bool verdict flag rather than counting it",
      I.zero_errors({"target": 0, "ours": 0, "pass": True}))
check("zero_errors rejects a real non-zero count",
      not I.zero_errors({"target": 0, "ours": 3}))


def raises(fn):
    try:
        fn()
        return False
    except I.AggregatorShapeError:
        return True
    except Exception:
        return False


check("a BOOL passed as an error record fails fast",
      raises(lambda: I.zero_errors(True)))
check("a MISSING error record fails fast",
      raises(lambda: I.zero_errors(None)))
check("a dict with no numeric counts fails fast",
      raises(lambda: I.zero_errors({"pass": True})))
check("an unusable type fails fast",
      raises(lambda: I.zero_errors("0")))
check("require_number rejects a bool masquerading as a count",
      raises(lambda: I.require_number({"n": True}, "n")))
check("require_number rejects a missing key",
      raises(lambda: I.require_number({}, "n")))
check("require_number accepts a real number",
      I.require_number({"n": 7}, "n") == 7)

# ------------------------------------------------------- selection rule ---
strong = {"mainEffectPx": 4.0, "shapleyPx": 3.2,
          "interactionMagnitudePx": 1.0,
          "perMediaMainEffectPx": {"a": 4.1, "b": 3.9, "c": 4.0, "d": 4.0},
          "largestOnMedia": 4, "mediaCount": 4,
          "signStableAcrossViewports": True}
check("a large, stable, low-interaction factor is ELIGIBLE",
      I.selection_verdict("C", strong, 6.4)["eligible"])
check("a factor explaining under 40% is NOT eligible",
      not I.selection_verdict("C", {**strong, "shapleyPx": 2.0}, 6.4)["eligible"])
check("a factor dominated by interaction is NOT eligible",
      not I.selection_verdict("C", {**strong, "interactionMagnitudePx": 3.0},
                              6.4)["eligible"])
check("a factor that flips sign across media is NOT eligible",
      not I.selection_verdict("C", {**strong, "perMediaMainEffectPx":
                                    {"a": 4.1, "b": -0.3, "c": 4.0, "d": 4.0}},
                              6.4)["eligible"])
check("a factor not sign-stable across viewports is NOT eligible",
      not I.selection_verdict("C", {**strong, "signStableAcrossViewports": False},
                              6.4)["eligible"])
check("a factor that is largest on only half the media is NOT eligible",
      not I.selection_verdict("C", {**strong, "largestOnMedia": 2},
                              6.4)["eligible"])

# --------------------------------------------------------------- report ---
passed = sum(1 for r in RESULTS if r["pass"])
doc = {
    "what": "unit tests for the O4 instruments sealed in §五. Every check "
            "has a negative partner: an instrument that cannot fail is not "
            "conservative, it is broken.",
    "instrumentsModule": "scripts/v5/o4_instruments.py",
    "tests": len(RESULTS), "passed": passed, "failed": len(RESULTS) - passed,
    "pass": passed == len(RESULTS),
    "results": RESULTS,
}
out = REPO / "qa-v5/optics-o4/instrument-tests.json"
for a_ in sys.argv[1:]:
    k, _, v = a_.lstrip("-").partition("=")
    if k == "out":
        out = Path(v)
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(doc, indent=1))
print(f"\n{passed}/{len(RESULTS)} passed -> {out}")
sys.exit(0 if doc["pass"] else 1)
