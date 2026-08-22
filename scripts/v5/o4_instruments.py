#!/usr/bin/env python3
"""O4 instruments (§五), sealed before any candidate lane runs.

Every definition that has a choice in it lives here, so the gate, the
attribution and the unit tests all read one implementation. Where O3
carried a defect, the fix is stated with its reason.

Sealed decisions
----------------
1. BAND WIDTH is measured per card, thresholded per card, and only then
   averaged. Averaging profiles across cards first smears bands that sit at
   different depths and reads wider than any card actually is -- it read the
   Target at 9 px where the Target measures 3.3. `band_width_px` is the
   O2/O3 gate coding, re-exported here so there is one definition.

2. BAND ENERGY is a second, CONTINUOUS measurand recorded beside band
   width. Band width is thresholded and therefore lumpy: it moves in whole
   pixels and can tie. Attribution -- marginal effects, interactions,
   Shapley -- is computed on both, and the continuous one is what
   interaction dominance is read from.

3. TRUE SILHOUETTE is derived from `glass visible` XOR `media only` on the
   ALL-CURRENT CONTROL lane, per viewport and per media, and then reused
   for every lane in that cell. It is not re-derived per lane: a lane with
   the body neutralised renders close to the bare media, so its own
   silhouette degenerates and the comparison would silently change basis.
   The flat layout quad is never the gutter boundary -- the rendered card
   is a bulged lens that projects outside its own plane quad, which is
   exactly the annulus O3 item 13 misattributed.

4. LABELS OFF for every optical ROI and every pointer metric. Verified
   available on both the e913aa6 baseline and the current build, so the
   identity proof and the factorial share one basis.

5. INTERIOR uses a baseline-aware branch whose floor is derived from the
   instrument's own tolerances rather than chosen: a RELATIVE change is
   meaningful only when the baseline is at least as large as the ABSOLUTE
   change the same instrument is willing to ignore. Below that, a change
   entirely inside the absolute tolerance would score as more than 100%
   relative -- the two codings would contradict each other. So the relative
   branch requires `baseline >= F5_ABSOLUTE_SATURATION_CEILING`.

   Disclosure: under O3's sealed floor of 0.01, `hf-checker` (baseline
   0.0104) took the relative branch and fired on an absolute change of
   0.0035. That O3 verdict is unchanged and is not revisited. This floor is
   derived from the coherence requirement above, not from that outcome, and
   is sealed here before any O4 candidate pixel exists.

6. POINTER uses the O3 card-space construction: each state is cropped at
   its OWN card rect, compared on a common card-space raster, and the
   bright low-chroma pixels present in EVERY state are removed as ink. No
   post-capture percentage crop.
"""
from __future__ import annotations

import importlib.util
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


S = _load("o4_stats_base", "o2_optics_stats.py")
O3 = _load("o4_o3_instruments", "o3_instruments.py")

# ------------------------------------------------------------------ band ---

BAND_THRESHOLD = 60.0          #: luma, the O2/O3 gate threshold, unchanged
BAND_INSIDE_PX = 24            #: how far inward the profile is read
MEDIA_BLACK = 16.0             #: the deterministic media's black level


def _lum(p):
    return 0.2126 * p[..., 0] + 0.7152 * p[..., 1] + 0.0722 * p[..., 2]


def band_width_px(img, rects):
    """Per card, threshold per card, average the WIDTHS. Sealed coding."""
    return S.reflection_band(img, rects, threshold=BAND_THRESHOLD)


def band_energy(img, rects, inside_px=BAND_INSIDE_PX):
    """Continuous companion to band width.

    Integral of luma above the media black level over the first
    `inside_px` inward from each card's dark-side edge, per card, then
    averaged. Units: luma-levels x px. Unlike band width this does not
    quantise to whole pixels, so small effects and interactions remain
    visible instead of tying at a threshold crossing.
    """
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    per = []
    for (x0, y0, x1, y1) in rects:
        ch = y1 - y0
        rows = a[y0 + int(ch * 0.42):y0 + int(ch * 0.58)]
        seg = rows[:, x0:x0 + inside_px]
        if seg.shape[1] < inside_px:
            continue
        prof = _lum(seg).mean(axis=0)
        per.append(float(np.maximum(prof - MEDIA_BLACK, 0).sum()))
    if not per:
        return {"meanEnergy": None, "perCard": []}
    return {"meanEnergy": round(float(np.mean(per)), 2),
            "perCard": [round(v, 2) for v in per],
            "insidePx": inside_px, "mediaBlack": MEDIA_BLACK}


# ------------------------------------------------------------ silhouette ---

def true_silhouette(control_full_path, media_only_path):
    """Every pixel the glass layer changes, from the CONTROL lane.

    This is the rendered card, bulge and sidewall included -- not the flat
    layout quad. Returns a boolean mask.
    """
    a = np.asarray(Image.open(control_full_path).convert("RGB")).astype(int)
    b = np.asarray(Image.open(media_only_path).convert("RGB")).astype(int)
    if a.shape != b.shape:
        raise ValueError("silhouette inputs differ in shape")
    return np.abs(a - b).max(axis=2) > 0


GUTTER_INK_LUMA = 80.0


def gutter_outside_silhouette(img_path, silhouette):
    """Ink ratio strictly OUTSIDE the true rendered silhouette."""
    a = np.asarray(Image.open(img_path).convert("RGB"), dtype=np.float32)
    if a.shape[:2] != silhouette.shape:
        raise ValueError("image and silhouette differ in shape")
    out = ~silhouette
    n = int(out.sum())
    if n == 0:
        return {"gutterInkRatio": None, "gutterPixels": 0}
    return {"gutterInkRatio": round(float((_lum(a)[out] > GUTTER_INK_LUMA).sum() / n), 6),
            "gutterPixels": n}


def gutter_pair_outside_silhouette(control_path, candidate_path, silhouette):
    """Direct comparison outside the silhouette, per §五.2."""
    a = np.asarray(Image.open(control_path).convert("RGB")).astype(int)
    b = np.asarray(Image.open(candidate_path).convert("RGB")).astype(int)
    out = ~silhouette
    d = np.abs(a - b).max(axis=2)[out]
    return {
        "control": gutter_outside_silhouette(control_path, silhouette),
        "candidate": gutter_outside_silhouette(candidate_path, silhouette),
        "differingPixelsOutsideSilhouette": int((d > 0).sum()),
        "maxChannelDeltaOutsideSilhouette": int(d.max()) if d.size else 0,
    }


# -------------------------------------------------------------- interior ---

INTERIOR_RELATIVE_CEILING = 0.12
INTERIOR_ABSOLUTE_SATURATION_CEILING = 0.02
INTERIOR_ABSOLUTE_CHROMA_CEILING = 2.0
#: Derived, not chosen -- see the module docstring, decision 5.
INTERIOR_RELATIVE_BRANCH_FLOOR = INTERIOR_ABSOLUTE_SATURATION_CEILING


def interior_change(before: dict, candidate: dict) -> dict:
    """Interior-unchanged check for one asset, baseline-aware.

    The branch is chosen by the BASELINE alone, so it is fixed by the
    control render and cannot be selected after seeing the candidate.
    """
    b_sat, c_sat = before["interiorSaturationMean"], candidate["interiorSaturationMean"]
    b_lum, c_lum = before["interiorLuminanceMean"], candidate["interiorLuminanceMean"]
    d_sat = c_sat - b_sat
    d_chroma = candidate["interiorChromaMean"] - before["interiorChromaMean"]

    rel_lum = abs(c_lum - b_lum) / max(b_lum, 1e-6)
    reasons = []
    if rel_lum > INTERIOR_RELATIVE_CEILING:
        reasons.append(f"interior luminance moved {rel_lum:.1%} > "
                       f"{INTERIOR_RELATIVE_CEILING:.0%}")

    if b_sat >= INTERIOR_RELATIVE_BRANCH_FLOOR:
        coding = "relative"
        rel_sat = abs(d_sat) / b_sat
        if rel_sat > INTERIOR_RELATIVE_CEILING:
            reasons.append(f"interior saturation moved {rel_sat:.1%} > "
                           f"{INTERIOR_RELATIVE_CEILING:.0%}")
        detail = {"relSaturationChange": round(float(rel_sat), 4)}
    else:
        coding = "absolute"
        if abs(d_sat) > INTERIOR_ABSOLUTE_SATURATION_CEILING:
            reasons.append(f"interior saturation moved {abs(d_sat):.4f} > "
                           f"{INTERIOR_ABSOLUTE_SATURATION_CEILING}")
        if abs(d_chroma) > INTERIOR_ABSOLUTE_CHROMA_CEILING:
            reasons.append(f"interior chroma moved {abs(d_chroma):.3f} > "
                           f"{INTERIOR_ABSOLUTE_CHROMA_CEILING}")
        detail = {"absSaturationDelta": round(float(d_sat), 5),
                  "absChromaDelta": round(float(d_chroma), 3)}

    return {
        "coding": coding,
        "codingChosenBy": f"baseline interior saturation {b_sat:.5f} "
                          f"{'>=' if b_sat >= INTERIOR_RELATIVE_BRANCH_FLOOR else '<'} "
                          f"{INTERIOR_RELATIVE_BRANCH_FLOOR} "
                          f"(= the absolute saturation ceiling; a relative "
                          f"reading below it would contradict the absolute one)",
        "baselineSaturation": round(float(b_sat), 5),
        "relLuminanceChange": round(float(rel_lum), 4),
        **detail,
        "fired": bool(reasons), "reasons": reasons,
    }


# --------------------------------------------------------------- pointer ---

glass_reflection_masks = O3.glass_reflection_masks
centroid_of = O3.centroid_of
pointer_judge = O3.f11_judge


# ------------------------------------------------------------- aggregator --

class AggregatorShapeError(ValueError):
    """A suite record did not have the shape the aggregator requires."""


def zero_errors(v):
    """Is an error record all zero?

    `bool` is a subclass of `int` in Python, so a sibling verdict flag such
    as `"pass": true` would otherwise be counted as a non-zero error and
    fail a suite whose every real counter is zero. Booleans are excluded
    explicitly.
    """
    if v is None:
        raise AggregatorShapeError("error record is missing")
    if isinstance(v, bool):
        raise AggregatorShapeError(f"error record is a bool ({v}), not a count")
    if isinstance(v, dict):
        counts = [n for n in v.values()
                  if isinstance(n, (int, float)) and not isinstance(n, bool)]
        if not counts:
            raise AggregatorShapeError("error dict carries no numeric counts")
        return all(n == 0 for n in counts)
    if isinstance(v, (int, float)):
        return v == 0
    raise AggregatorShapeError(f"error record has unusable type {type(v).__name__}")


def require_number(d: dict, key: str):
    """Fail fast on a malformed suite record instead of coercing it."""
    if key not in d:
        raise AggregatorShapeError(f"missing key {key!r}")
    v = d[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise AggregatorShapeError(
            f"{key!r} is {type(v).__name__}, expected a number")
    return v


# ------------------------------------------------------- selection rule ----

SELECTION_MIN_EXPLAINED_FRACTION = 0.40
#: A factor is "dominated by an unmodelled interaction" when its total
#: interaction magnitude rivals its own main effect.
SELECTION_MAX_INTERACTION_RATIO = 0.50
#: "Largest stable contributor" -- it must be the largest on this fraction
#: of the scored media, and never negative on any of them.
SELECTION_STABLE_MEDIA_FRACTION = 0.75


def selection_verdict(factor: str, effects: dict, excess_px: float) -> dict:
    """Operationalisation of §七, sealed before the factorial runs.

    `effects` carries, for one factor: `mainEffectPx` (its OFAT / marginal
    reduction in band width, positive = reduces the floor),
    `shapleyPx`, `interactionMagnitudePx`, `perMediaMainEffectPx`,
    `largestOnMedia` (count of media where it is the largest contributor),
    `mediaCount`, `signStableAcrossViewports`.
    """
    reasons = []
    explained = (effects["shapleyPx"] / excess_px) if excess_px else 0.0
    if explained < SELECTION_MIN_EXPLAINED_FRACTION:
        reasons.append(
            f"explains {explained:.1%} of the {excess_px:.1f} px excess, "
            f"below the {SELECTION_MIN_EXPLAINED_FRACTION:.0%} rule")
    ratio = (effects["interactionMagnitudePx"] / abs(effects["mainEffectPx"])
             if effects["mainEffectPx"] else float("inf"))
    if ratio > SELECTION_MAX_INTERACTION_RATIO:
        reasons.append(
            f"interaction magnitude is {ratio:.2f}x its main effect, above "
            f"the {SELECTION_MAX_INTERACTION_RATIO} rule -- dominated by an "
            f"unmodelled interaction")
    frac = effects["largestOnMedia"] / max(effects["mediaCount"], 1)
    if frac < SELECTION_STABLE_MEDIA_FRACTION:
        reasons.append(
            f"largest contributor on {effects['largestOnMedia']}/"
            f"{effects['mediaCount']} media, below the "
            f"{SELECTION_STABLE_MEDIA_FRACTION:.0%} rule")
    if any(v < 0 for v in effects["perMediaMainEffectPx"].values()):
        reasons.append("main effect changes sign across media")
    if not effects.get("signStableAcrossViewports", False):
        reasons.append("main effect is not sign-stable across viewports")
    return {"factor": factor,
            "explainedFraction": round(float(explained), 4),
            "interactionRatio": round(float(ratio), 4)
                                if ratio != float("inf") else None,
            "largestOnMediaFraction": round(float(frac), 4),
            "eligible": not reasons, "reasons": reasons}
