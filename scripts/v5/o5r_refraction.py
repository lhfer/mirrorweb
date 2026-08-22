#!/usr/bin/env python3
"""§六 refraction compression, end to end.

One place that knows how to turn (a render, a card, the live matrices) into a
displacement, so the instrument tests and the gate cannot drift apart by asking
the same question two slightly different ways.

The measurement, in order:

  1. Replay the card's geometry from the LIVE matrices -- projection, dome,
     cover -- and forward-map every card fragment into source-image space.
  2. Collect the fragments that land inside each calibration disc, twice: once
     with refraction and once without. That gives a predicted REFRACTED image
     and a predicted UNREFRACTED image for each disc, including the smearing
     refraction produces near the bevel.
  3. Measure each disc's real centroid inside its own predicted footprint.
  4. displacement = measured - predicted UNREFRACTED.
     residual     = measured - predicted REFRACTED.

`displacement` is the §六 measurand, computed identically for every lane and
never derived from the lane being judged. `residual` is the replay's own
accuracy, and on the Target it is the validation §六 asks for: if the Target's
own render sits on the replayed source formula, the replay IS the Target's
refraction and can be trusted to say what the Target would do.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I = _load("o5r_ref_ins", "o5r_instruments.py")
R = _load("o5r_ref_rep", "o5r_replay.py")

# The scored landmark set: the calibration discs in the card's UPPER HALF.
# The Target draws its headline across the lower half and has no QA surface to
# switch it off, and a white glyph is not distinguishable from a white disc by
# luminance. Pre-registered here, before any O5R candidate frame.
SCORED_DISC_MAX_NY = 0.46
SOURCE_WH = (1200, 900)

# Slots whose clip index is 2 carry our FROZEN product crop (focusY 0.46,
# zoom 1.06); the Target applies its centred cover to every card. That is a
# deliberate product decision, recorded in o5-architecture.json's
# coverFitComparison, and the sealed O2 harness already excludes these slots
# from cross-page comparison for exactly this reason. Scoring them here would
# report a frozen product crop as an optical difference. On clips 0 and 1 the
# two cover laws agree exactly for a 4:3 source on a 4:3 plane -- both are
# scale (1,1), offset (0,0) -- so the excluded card is the only one where the
# question could not be asked cleanly.
EXCLUDED_CLIP_INDEX = 2

# A card is VALIDATED for scoring when the replayed source formula lands on the
# TARGET'S own render to inside this. Decided from Target pixels alone and
# applied identically to every lane. The displacement being measured is of
# order 6-20 px and the compression window floor is 1.5 px, so a replay that
# tracks the Target to 3 px is describing the same optical system; one that
# does not cannot serve as that card's reference, and §六 says the answer then
# is INSTRUMENT_UNREADABLE rather than FAIL.
REPLAY_VALIDATION_MAX_PX = 3.0


def scored_discs(media_manifest):
    geo = media_manifest["landmarkGeometry"]["discs"]
    return [{"id": i, **g} for i, g in enumerate(geo)
            if g["ny"] <= SCORED_DISC_MAX_NY]


def match_cards_to_rects(truth, rects):
    """Which live card each screen rect is.

    Matched by projected axis-aligned extent, because that is the one quantity
    both the rect deriver and the replay can compute independently -- and the
    agreement between them is itself a check that the replay's projection is
    the engine's.
    """
    out = []
    cards = [c for c in truth["cards"] if c.get("active", True)]
    lx = np.array([-.5, .5, .5, -.5])
    ly = np.array([.5, .5, -.5, -.5])
    boxes = []
    for c in cards:
        rp = R.CardReplay(truth, c)
        sx, sy = rp.local_to_screen(lx, ly)
        boxes.append((float(sx.min()), float(sy.min()),
                      float(sx.max()), float(sy.max())))
    for rect in rects:
        best, best_d = None, None
        for c, b in zip(cards, boxes):
            d = sum(abs(b[i] - rect[i]) for i in range(4))
            if best_d is None or d < best_d:
                best, best_d = (c, b), d
        out.append({"rect": rect, "card": best[0], "projectedBox": best[1],
                    "boxAgreementPx": round(best_d / 4.0, 2)})
    return out


def measure_card(img, truth, card, rect, discs):
    """Displacement and replay residual for one card in one render."""
    rp = R.CardReplay(truth, card)
    pred_ref = R.predict_disc_images(rp, discs, SOURCE_WH, refracted=True)
    pred_unref = R.predict_disc_images(rp, discs, SOURCE_WH, refracted=False)
    meas = I.measure_discs_in_windows(img, pred_ref, rect=rect)
    disp = I.displacement_from_predictions(meas["rows"], pred_unref)
    return {
        "slotIndex": card["slotIndex"], "clipIndex": card.get("clipIndex"),
        "rect": list(rect),
        "measured": meas["measured"], "expected": meas["expected"],
        "usable": meas["usable"],
        "replayResidualMeanPx": meas["meanResidualPx"],
        "replayResidualMaxPx": meas["maxResidualPx"],
        "displacementMeanPx": disp["meanMagnitudePx"],
        "perDisc": disp["perDisc"],
        "rows": meas["rows"],
    }


def measure_lane(img, truth, rects, discs, exclude_frozen_crop=True):
    """Every fully-visible card in one render."""
    pairs = match_cards_to_rects(truth, rects)
    cards = []
    for p in pairs:
        if (exclude_frozen_crop
                and p["card"].get("clipIndex") == EXCLUDED_CLIP_INDEX):
            cards.append({"slotIndex": p["card"]["slotIndex"],
                          "clipIndex": EXCLUDED_CLIP_INDEX,
                          "rect": list(p["rect"]), "usable": False,
                          "excluded": True,
                          "why": "this slot carries the frozen product crop "
                                 "the Target does not apply; the sealed O2 "
                                 "harness excludes it from cross-page "
                                 "comparison for the same reason"})
            continue
        try:
            cards.append({**measure_card(img, truth, p["card"], p["rect"], discs),
                          "boxAgreementPx": p["boxAgreementPx"]})
        except I.Unreadable as e:
            cards.append({"slotIndex": p["card"]["slotIndex"],
                          "rect": list(p["rect"]), "usable": False,
                          "why": str(e)})
    usable = [c for c in cards if c.get("usable")]
    return {
        "cards": cards,
        "usableCards": len(usable), "totalCards": len(cards),
        "displacementMeanPx": (
            round(float(np.mean([c["displacementMeanPx"] for c in usable
                                 if c["displacementMeanPx"] is not None])), 3)
            if usable else None),
        "replayResidualMeanPx": (
            round(float(np.mean([c["replayResidualMeanPx"] for c in usable
                                 if c["replayResidualMeanPx"] is not None])), 3)
            if usable else None),
        "boxAgreementMeanPx": (
            round(float(np.mean([c["boxAgreementPx"] for c in usable])), 3)
            if usable else None),
    }


def validate_replay_against_gpu(displacement_view, truth, card, rect,
                                inset=0.30, grid=64):
    """The replay against the candidate's own displacement PROGRAM.

    §六's first legitimacy condition. The GPU computes the base-ior card-UV
    displacement per fragment and writes it out; this replays the same
    expression on the CPU and compares. Sampled over the card's central region,
    away from the antialiased outline where a fragment is a blend of card and
    background and neither side is claiming to be exact.

    The comparison is reported in PIXELS of card width as well as in UV, since
    that is the unit the gate window lives in.
    """
    rp = R.CardReplay(truth, card)
    du_gpu, dv_gpu, ok = I.decode_displacement_view(displacement_view, rect)
    h, w = du_gpu.shape
    if h < 8 or w < 8:
        raise I.Unreadable("validate_replay_against_gpu: card rect too small")
    # Sample the render on a grid, then ask the replay for the same points.
    # Screen -> local is not analytic under perspective, so go the other way:
    # walk a local grid, project it, and read the render there.
    g = np.linspace(-0.5 + inset, 0.5 - inset, grid)
    lx, ly = np.meshgrid(g, g, indexing="xy")
    sx, sy = rp.local_to_screen(lx, ly)
    px = np.clip(np.round(sx - rect[0]).astype(int), 0, w - 1)
    py = np.clip(np.round(sy - rect[1]).astype(int), 0, h - 1)
    valid = ok[py, px]
    if valid.sum() < grid * grid * 0.5:
        raise I.Unreadable(
            f"validate_replay_against_gpu: only {int(valid.sum())} of "
            f"{grid * grid} samples were unsaturated")
    du_cpu, dv_cpu, _ = rp.displacement(lx, ly)
    eu = np.abs(du_cpu - du_gpu[py, px])[valid]
    ev = np.abs(dv_cpu - dv_gpu[py, px])[valid]
    quant = 1.0 / 255.0 / I.DISPLACEMENT_GAIN
    return {
        "samples": int(valid.sum()),
        "meanAbsErrorU": round(float(eu.mean()), 6),
        "meanAbsErrorV": round(float(ev.mean()), 6),
        "p99AbsErrorU": round(float(np.percentile(eu, 99)), 6),
        "p99AbsErrorV": round(float(np.percentile(ev, 99)), 6),
        "quantisationUV": round(quant, 6),
        "meanAbsErrorPxU": round(float(eu.mean()) * rp.plane_w, 3),
        "meanAbsErrorPxV": round(float(ev.mean()) * rp.plane_h, 3),
        "quantisationPxU": round(quant * rp.plane_w, 3),
        # The port agrees with the program when the disagreement is within a
        # couple of encoding steps. More than that is a defect in the port.
        "agreesWithGpu": bool(max(float(np.percentile(eu, 99)),
                                  float(np.percentile(ev, 99))) <= 3 * quant),
    }
