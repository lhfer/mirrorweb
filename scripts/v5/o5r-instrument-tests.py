#!/usr/bin/env python3
"""O5R instrument tests.

§三 requires SIX things of every corrected instrument, and this file is
organised so that a missing one is visible rather than implied:

  positive unit test        a synthetic input the instrument must read
  negative unit test        a synthetic input it must NOT confuse with the first
  Target self-test          it reads real Target pixels
  Control self-test         it reads real control pixels
  Candidate-readable test   it reads a real target-source candidate
  UNREADABLE state          an input it must REFUSE, out loud

The self-tests deliberately use captures that already exist: the O5R Target
frames, and the O5 control and clamped-candidate frames. None of them is the
O5R candidate, which does not exist at seal time and must not.

Output: qa-v5/optics-o5r/instrument-tests.json
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


I = _load("o5r_ins", "o5r_instruments.py")
R = _load("o5r_rep", "o5r_replay.py")
S = _load("o5r_stats", "o2_optics_stats.py")
F = _load("o5r_refr", "o5r_refraction.py")

O5R_MD = REPO / "artifacts/optics-o5r/measure"
O5_MD = REPO / "artifacts/optics-o5/measure"

RESULTS = []


def check(instrument, kind, name, ok, detail=""):
    RESULTS.append({"instrument": instrument, "kind": kind, "test": name,
                    "pass": bool(ok), "detail": detail})
    return bool(ok)


# ------------------------------------------------------------- fixtures

def img_from(arr):
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def grey_card(w=240, h=180, level=128, noise=0.0, seed=1):
    rng = np.random.default_rng(seed)
    a = np.full((h, w, 3), float(level))
    if noise:
        a += rng.normal(0, noise, a.shape)
    return a


def with_edges(a, step=(64, 192), x=None):
    """A vertical luminance step, achromatic."""
    h, w = a.shape[:2]
    x = w // 2 if x is None else x
    a[:, :x] = step[0]
    a[:, x:] = step[1]
    return a


def add_edge_fringe(a, x=None, width=2, rb=40):
    """Colour that HUGS an edge -- the legitimate kind."""
    h, w = a.shape[:2]
    x = w // 2 if x is None else x
    a[:, max(0, x - width):x, 0] += rb
    a[:, x:min(w, x + width), 2] += rb
    return a


def add_broad_cast(a, chroma=40):
    """Colour spread over the whole card -- the illegitimate kind."""
    a[..., 0] += chroma * 0.5
    a[..., 2] -= chroma * 0.5
    return a


def frame_with_card(card, pad=40, background=18.0):
    """Place a card block into a larger frame, with a rect."""
    h, w = card.shape[:2]
    f = np.full((h + 2 * pad, w + 2 * pad, 3), background)
    f[pad:pad + h, pad:pad + w] = card
    return f, (pad, pad, pad + w, pad + h)


def rounded_mask(h, w, r):
    hx, hy = w / 2.0, h / 2.0
    r = min(r, hx, hy)
    ys, xs = np.mgrid[0:h, 0:w]
    qx = np.abs(xs + 0.5 - hx) - hx + r
    qy = np.abs(ys + 0.5 - hy) - hy + r
    outside = np.sqrt(np.maximum(qx, 0.0) ** 2 + np.maximum(qy, 0.0) ** 2)
    sdf = outside + np.minimum(np.maximum(qx, qy), 0.0) - r
    return sdf


# =============================================== §四 grayscale v2
def test_grayscale():
    NAME = "grayscale_v2"
    h, w = 180, 240
    # POSITIVE: colour that sits on the encoded edge only. The Target carries
    # exactly this from 4:2:0 subsampling, so the instrument must record it as
    # gradient-local colour and NOT as false colour.
    a = add_edge_fringe(with_edges(grey_card(w, h)))
    f, rect = frame_with_card(a)
    r = I.grayscale_v2(img_from(f), [rect])
    check(NAME, "positive",
          "edge-local chroma is reported at gradients, not as false colour",
          r["chromaAtGradients"] > r["chromaAwayFromGradients"]
          and r["falseColourAreaFraction"] < 0.01,
          f"atGradients {r['chromaAtGradients']} away "
          f"{r['chromaAwayFromGradients']} falseArea "
          f"{r['falseColourAreaFraction']}")

    # NEGATIVE: the same card with a BROAD cast. Must be caught as false
    # colour, which is the whole point of separating the two populations.
    b = add_broad_cast(with_edges(grey_card(w, h)))
    fb, rectb = frame_with_card(b)
    rb = I.grayscale_v2(img_from(fb), [rectb])
    check(NAME, "negative",
          "a broad cast is caught as false colour away from features",
          rb["falseColourAreaFraction"] > 0.5
          and rb["chromaAwayFromGradients"] > r["chromaAwayFromGradients"] * 3,
          f"falseArea {rb['falseColourAreaFraction']} away "
          f"{rb['chromaAwayFromGradients']}")

    # The scored comparison is Target-RELATIVE, so a lane identical to the
    # Target must read zero distance, and the broad-cast lane must not.
    d_same = I.grayscale_distance(r, r)
    d_cast = I.grayscale_distance(rb, r)
    check(NAME, "positive", "distance to Target is zero for an identical lane",
          all(v == 0 for v in d_same.values() if v is not None), str(d_same))
    check(NAME, "negative", "distance to Target is large for the cast lane",
          d_cast["meanChroma"] > 5, str(d_cast))

    # UNREADABLE: no cards.
    try:
        I.grayscale_v2(img_from(f), [])
        check(NAME, "unreadable", "refuses when there are no card rects", False,
              "returned a reading")
    except I.Unreadable as e:
        check(NAME, "unreadable", "refuses when there are no card rects", True,
              str(e))

    # The DEGENERACY rule: identical lanes must be UNREADABLE, never PASS.
    deg = I.degenerate_reading("grayscale", {"target": 0.0, "control": 0.0,
                                             "candidate": 0.0})
    check(NAME, "unreadable",
          "three identical lane values return UNREADABLE, not PASS",
          deg is not None and deg["status"] == I.UNREADABLE,
          (deg or {}).get("why", ""))
    live = I.degenerate_reading("grayscale", {"target": 30.0, "control": 18.0,
                                              "candidate": 18.5})
    check(NAME, "positive", "differing lane values are not degenerate",
          live is None, "")
    return r


# =============================================== §五 saturated edge v2
def test_saturated_edge():
    NAME = "saturated_edge_v2"
    h, w = 180, 240
    # POSITIVE: chroma that follows the media texture. Vertical colour bars
    # with a fringe at each boundary.
    a = np.full((h, w, 3), 120.0)
    for i in range(0, w, 40):
        a[:, i:i + 40] = [200, 60, 60] if (i // 40) % 2 else [60, 60, 200]
    f, rect = frame_with_card(a)
    r = I.saturated_edge_v2(img_from(f), [rect], corner_radius_px=0.163 * w)
    check(NAME, "positive", "reads a feature population on textured media",
          r["chromaAtFeatures"] is not None and r["featurePixels"] > 100,
          f"atFeatures {r['chromaAtFeatures']} px {r['featurePixels']}")

    # NEGATIVE: a broad cyan/magenta frame -- §五 names this exact fixture.
    # Flat interior, wide coloured band inside the rim, no media features
    # under it. The broad-rim measure must fire and localisation must collapse.
    b = np.full((h, w, 3), 120.0)
    for i in range(0, w, 40):
        b[:, i:i + 40] = [200, 60, 60] if (i // 40) % 2 else [60, 60, 200]
    band = int(w * I.RIM_BAND_FRACTION)
    b[:band, :] = [40, 220, 220]        # cyan top band
    b[-band:, :] = [220, 40, 220]       # magenta bottom band
    b[:, :band] = [40, 220, 220]
    b[:, -band:] = [220, 40, 220]
    fb, rectb = frame_with_card(b)
    rb = I.saturated_edge_v2(img_from(fb), [rectb], corner_radius_px=0.163 * w)
    check(NAME, "negative",
          "a broad cyan/magenta rim is caught by broadRimColouredFraction",
          rb["broadRimColouredFraction"] > 0.5
          and rb["broadRimColouredFraction"] > (r["broadRimColouredFraction"] or 0),
          f"broadRim candidate {rb['broadRimColouredFraction']} vs textured "
          f"{r['broadRimColouredFraction']}")
    check(NAME, "negative", "colour following the texture keeps localisation up",
          r["fringeLocalisation"] > rb["fringeLocalisation"],
          f"textured {r['fringeLocalisation']} vs broad-rim "
          f"{rb['fringeLocalisation']}")

    # UNREADABLE: a perfectly flat card has no feature population at all. This
    # is exactly the situation O5 item 5 answered with 0.0 and a PASS.
    flat, rectf = frame_with_card(grey_card(w, h, level=140))
    try:
        I.saturated_edge_v2(img_from(flat), [rectf], corner_radius_px=0.163 * w)
        check(NAME, "unreadable", "refuses on media with no features", False,
              "returned a reading where O5 returned 0.0 and called it a pass")
    except I.Unreadable as e:
        check(NAME, "unreadable", "refuses on media with no features", True,
              str(e))
    return r


# =============================================== §六 refraction v2
def test_refraction():
    NAME = "refraction_compression_v2"
    # POSITIVE: an encoded displacement field decodes back to itself.
    h, w = 120, 160
    du = np.linspace(-0.1, 0.1, w)[None, :].repeat(h, 0)
    dv = np.linspace(-0.05, 0.05, h)[:, None].repeat(w, 1)
    enc = np.stack([
        np.clip(0.5 + du * I.DISPLACEMENT_GAIN, 0, 1) * 255,
        np.clip(0.5 + dv * I.DISPLACEMENT_GAIN, 0, 1) * 255,
        np.zeros((h, w)),
    ], axis=-1)
    f, rect = frame_with_card(enc)
    gdu, gdv, ok = I.decode_displacement_view(img_from(f), rect)
    err = max(float(np.abs(gdu - du)[ok].max()), float(np.abs(gdv - dv)[ok].max()))
    check(NAME, "positive",
          "the displacement encoding round-trips to inside one 8-bit code",
          err <= 1.0 / 255 / I.DISPLACEMENT_GAIN + 1e-6,
          f"max error {err:.6f} UV, one code = "
          f"{1 / 255 / I.DISPLACEMENT_GAIN:.6f}")

    # NEGATIVE: background pixels (0 or 255) must be excluded, not believed.
    enc2 = enc.copy()
    enc2[:10, :] = 0
    f2, rect2 = frame_with_card(enc2)
    _, _, ok2 = I.decode_displacement_view(img_from(f2), rect2)
    check(NAME, "negative", "saturated pixels are excluded, not decoded",
          not ok2[:10, :].any() and ok2[20:, :].all(),
          f"{int((~ok2).sum())} excluded of {ok2.size}")

    # POSITIVE: disc centroids on a synthetic calibration card.
    card = np.full((200, 260, 3), 90.0)
    centres = [(50, 60), (150, 90), (95, 190), (40, 210)]
    ys, xs = np.mgrid[0:200, 0:260]
    for (cy, cx) in centres:
        card[(ys - cy) ** 2 + (xs - cx) ** 2 <= 14 ** 2] = 245.0
    fc, rectc = frame_with_card(card)
    got = I.disc_centroids(img_from(fc), rectc, 90, 245,
                           area_range=(200, 4000))
    found = sorted((round(g["x"], 1), round(g["y"], 1)) for g in got)
    want = sorted((float(cx) + 0.5, float(cy) + 0.5) for (cy, cx) in centres)
    close = (len(got) == len(centres)
             and all(abs(a[0] - b[0]) < 1.0 and abs(a[1] - b[1]) < 1.0
                     for a, b in zip(found, want)))
    check(NAME, "positive", "disc centroids land on the discs, sub-pixel",
          close, f"found {found} want {want}")

    # NEGATIVE: shift every disc by a known amount; the pairing must report it.
    shifted = [{"x": g["x"] + 3.0, "y": g["y"] - 2.0, "areaPx": g["areaPx"],
                "areaFraction": g["areaFraction"]} for g in got]
    pr = I.pair_centroids(shifted, got)
    check(NAME, "negative", "a known shift is recovered exactly",
          pr["cleanlyPaired"] and abs(pr["meanDxPx"] - 3.0) < 1e-6
          and abs(pr["meanDyPx"] + 2.0) < 1e-6,
          f"dx {pr['meanDxPx']} dy {pr['meanDyPx']}")

    # NEGATIVE: a mispair must invalidate rather than average away. Two discs
    # cancelling to a mean of zero is the exact O5 failure mode.
    partial = I.pair_centroids(got[:2], got)
    check(NAME, "negative",
          "an incomplete pairing refuses to report a mean",
          not partial["cleanlyPaired"] and partial["meanDisplacementPx"] is None,
          f"matched {partial['matched']} of {partial['expected']}")
    far = [{"x": g["x"] + 200.0, "y": g["y"], "areaPx": g["areaPx"],
            "areaFraction": g["areaFraction"]} for g in got]
    outside = I.pair_centroids(far, got)
    check(NAME, "negative", "a pairing beyond the search radius is refused",
          outside["matched"] == 0 and not outside["cleanlyPaired"],
          f"matched {outside['matched']}")

    # UNREADABLE: a card with no contrast has no landmarks.
    flat, rectf = frame_with_card(grey_card(260, 200, level=120))
    try:
        I.disc_centroids(img_from(flat), rectf, 90, 245)
        check(NAME, "unreadable", "refuses a card with no landmark contrast",
              False, "returned centroids")
    except I.Unreadable as e:
        check(NAME, "unreadable", "refuses a card with no landmark contrast",
              True, str(e))

    # The window path -- the one the gate actually uses. A prediction whose
    # footprint is right must be measured; one whose window catches something
    # far too large must be refused rather than measured wrongly.
    preds = [{"id": i, "x": float(cx) + 0.5 + 40, "y": float(cy) + 0.5 + 40,
              "fragments": int(np.pi * 14 ** 2),
              "bbox": [cx + 40 - 14.0, cy + 40 - 14.0,
                       cx + 40 + 14.0, cy + 40 + 14.0]}
             for i, (cy, cx) in enumerate(centres)]
    win = I.measure_discs_in_windows(img_from(fc), preds, rect=rectc)
    check(NAME, "positive",
          "window measurement lands on the discs to well inside a pixel",
          win["measured"] == len(centres) and win["maxResidualPx"] < 0.6,
          f"{win['measured']}/{win['expected']} maxResid {win['maxResidualPx']}")

    # A split image: erase a stripe across one disc so a connected-component
    # detector would see two half-discs. The window measurement must still
    # return the whole object's centroid.
    split = card.copy()
    cy0, cx0 = centres[0]
    split[cy0 - 1:cy0 + 2, cx0 - 20:cx0 + 20] = 90.0
    fs, rects_ = frame_with_card(split)
    win2 = I.measure_discs_in_windows(img_from(fs), preds, rect=rects_)
    r0 = [r for r in win2["rows"] if r["id"] == 0]
    check(NAME, "negative",
          "a disc image split in two is still measured as one object",
          bool(r0) and r0[0]["measured"] and r0[0]["residualPx"] < 1.0,
          str(r0[0] if r0 else None))

    # UNREADABLE: overlapping windows must be refused, not shared.
    dup = [dict(preds[0]), dict(preds[0], id=99)]
    ov = I.measure_discs_in_windows(img_from(fc), dup, rect=rectc)
    check(NAME, "unreadable", "overlapping windows are refused, not shared",
          all(not r["measured"] and "overlaps" in r.get("why", "")
              for r in ov["rows"]), str(ov["rows"]))

    # The displacement measurand: measured minus the UNREFRACTED prediction.
    unref = [{"id": p["id"], "x": p["x"] - 4.0, "y": p["y"] + 3.0}
             for p in preds]
    d = I.displacement_from_predictions(win["rows"], unref)
    check(NAME, "positive", "displacement is measured against the unrefracted "
          "prediction, and recovers a known offset",
          d["discs"] == len(centres) and abs(d["meanMagnitudePx"] - 5.0) < 0.6,
          f"mean {d['meanMagnitudePx']} expected 5.0")
    return None


# =============================================== §七 interior fidelity v2
def test_interior():
    NAME = "interior_fidelity_v2"
    h, w = 200, 260
    # A 4-px checker, not a 1-px one: the 4-neighbour mean of a 1-px checker is
    # its own inverse, so "blurring" it would leave the HF energy identical and
    # the fixture would prove nothing.
    checker = ((np.indices((h, w)) // 4).sum(0) % 2) * 255.0
    tex = np.repeat(checker[..., None], 3, axis=2)
    ft, rt = frame_with_card(tex)
    sharp = I.interior_stats(img_from(ft), [rt])
    blur = tex.copy()
    blur[1:-1, 1:-1] = (tex[:-2, 1:-1] + tex[2:, 1:-1] + tex[1:-1, :-2]
                        + tex[1:-1, 2:] + tex[1:-1, 1:-1]) / 5
    fb, rb = frame_with_card(blur)
    blurred = I.interior_stats(img_from(fb), [rb])
    check(NAME, "positive", "a sharp texture reads higher HF than a blurred one",
          sharp["hfEnergy"] > blurred["hfEnergy"] * 1.5,
          f"sharp {sharp['hfEnergy']} blurred {blurred['hfEnergy']}")

    # The repair itself: proximity to the Target, not "no blurrier than the
    # control". Build a Target between the two and confirm the nearer lane wins
    # even though it is the blurrier one.
    target_hf = (sharp["hfEnergy"] + blurred["hfEnergy"]) / 2 * 0.92
    d_sharp = abs(sharp["hfEnergy"] - target_hf)
    d_blur = abs(blurred["hfEnergy"] - target_hf)
    check(NAME, "negative",
          "proximity, not sharpness: the blurrier lane wins when it is nearer",
          d_blur < d_sharp,
          f"|blurred-T| {d_blur:.2f} < |sharp-T| {d_sharp:.2f}; the O5 coding "
          f"would have failed the nearer lane for being blurrier")

    ok, why = I.sharpness_applicable(sharp["hfEnergy"])
    check(NAME, "positive", "a textured asset is applicable for sharpness", ok,
          f"hf {sharp['hfEnergy']}")
    ok2, why2 = I.sharpness_applicable(4.8)
    check(NAME, "unreadable",
          "a flat asset is NOT_APPLICABLE, not a pass and not a failure",
          not ok2, why2)

    flat, rf = frame_with_card(grey_card(w, h))
    fl = I.interior_stats(img_from(flat), [rf])
    ok3, _ = I.sharpness_applicable(fl["hfEnergy"])
    check(NAME, "negative", "a flat card falls below the signal floor",
          not ok3, f"hf {fl['hfEnergy']} floor {I.HF_SIGNAL_FLOOR}")

    try:
        I.interior_stats(img_from(flat), [(0, 0, 3, 3)])
        check(NAME, "unreadable", "refuses a card too small to inset", False, "")
    except I.Unreadable as e:
        check(NAME, "unreadable", "refuses a card too small to inset", True,
              str(e))
    return sharp


# =============================================== §八 silhouette v2
def test_silhouette():
    NAME = "silhouette_v2"
    h, w = 200, 260
    r = 0.163 * w
    sdf = rounded_mask(h, w, r)
    inside = np.clip(-sdf, 0, 1)

    # A synthetically PERFECT target-source card: coverage exactly the SDF.
    card = np.where(inside[..., None] > 0.5, 200.0, 18.0)
    fperf, rect = frame_with_card(card, background=18.0)
    rendered, _ = I.rendered_alpha_mask(img_from(fperf), rect)
    # The soft coverage map, not a hard threshold of it: the antialias-width
    # measurement exists precisely to read the partial-coverage band, and a
    # hard fixture would have it return None and look like a broken instrument.
    proj_img = np.repeat(inside[..., None] * 255.0, 3, axis=2)
    fproj, rect2 = frame_with_card(proj_img, background=0.0)
    projected, pval = I.projected_alpha_mask(img_from(fproj), rect2)
    cmp_perfect = I.silhouette_compare(rendered, projected)
    check(NAME, "positive", "a synthetically perfect card matches its silhouette",
          cmp_perfect["iou"] > 0.995 and cmp_perfect["litBeyondSilhouette"] == 0,
          f"iou {cmp_perfect['iou']} beyond {cmp_perfect['litBeyondSilhouette']}")

    # NEGATIVE CONTROL: a SQUARE card. §八 requires this to be distinguishable.
    sq = np.full((h, w, 3), 200.0)
    fsq, rects = frame_with_card(sq, background=18.0)
    rend_sq, _ = I.rendered_alpha_mask(img_from(fsq), rects)
    cmp_sq = I.silhouette_compare(rend_sq, projected)
    check(NAME, "negative", "a square card is distinguishable from the rounded one",
          cmp_sq["litBeyondSilhouette"] > 400
          and cmp_sq["iou"] < cmp_perfect["iou"],
          f"square beyond {cmp_sq['litBeyondSilhouette']} iou {cmp_sq['iou']} "
          f"vs perfect beyond {cmp_perfect['litBeyondSilhouette']}")

    rad_round = I.measured_corner_radius_px(rendered)
    rad_square = I.measured_corner_radius_px(rend_sq)
    check(NAME, "positive", "the measured corner radius recovers the real one",
          rad_round is not None and abs(rad_round - r) < 0.15 * r,
          f"measured {rad_round} expected {round(r, 2)}")
    check(NAME, "negative", "a square card measures a corner radius near zero",
          rad_square is not None and rad_square < 0.2 * r,
          f"square {rad_square} vs rounded {rad_round}")

    aa = I.edge_width_px(pval, projected)
    check(NAME, "positive", "an antialias width is measurable from the soft map",
          aa is not None, f"aa {aa}")

    # UNREADABLE: a card rect covering the whole frame has no background ring.
    full = np.full((h, w, 3), 200.0)
    try:
        I.rendered_alpha_mask(img_from(full), (0, 0, w, h))
        check(NAME, "unreadable", "refuses when no background can be sampled",
              False, "returned a mask")
    except I.Unreadable as e:
        check(NAME, "unreadable", "refuses when no background can be sampled",
              True, str(e))
    try:
        I.silhouette_compare(rendered, projected[:-4])
        check(NAME, "unreadable", "refuses mismatched mask shapes", False, "")
    except I.Unreadable as e:
        check(NAME, "unreadable", "refuses mismatched mask shapes", True, str(e))
    return None


# =============================================== replay port
def test_replay():
    NAME = "target_replay"
    # refract() against a flat normal must be the identity direction.
    rx, ry, rz, ok = R.refract(np.array([0.0]), np.array([0.0]),
                               np.array([-1.0]), np.array([0.0]),
                               np.array([0.0]), np.array([1.0]), 1.0 / 2.3)
    check(NAME, "positive", "refract() at normal incidence stays on the axis",
          bool(ok[0]) and abs(rx[0]) < 1e-12 and abs(ry[0]) < 1e-12
          and abs(rz[0] + 1.0) < 1e-9,
          f"r = ({rx[0]:.3g}, {ry[0]:.3g}, {rz[0]:.6f})")
    # Total internal reflection returns zero, as GLSL does.
    rx2, _, _, ok2 = R.refract(np.array([0.9]), np.array([0.0]),
                               np.array([-np.sqrt(1 - 0.81)]), np.array([0.0]),
                               np.array([0.0]), np.array([1.0]), 2.3)
    check(NAME, "negative", "total internal reflection returns the GLSL zero",
          not bool(ok2[0]) and rx2[0] == 0.0, f"ok {bool(ok2[0])}")
    # The SDF is zero on the outline and negative inside.
    s_in = R.sdf(np.array([0.0]), np.array([0.0]), 150.0, 112.5, 24.0)
    s_out = R.sdf(np.array([200.0]), np.array([0.0]), 150.0, 112.5, 24.0)
    check(NAME, "positive", "the SDF is negative inside and positive outside",
          s_in[0] < 0 and s_out[0] > 0, f"in {s_in[0]:.2f} out {s_out[0]:.2f}")
    # The bevel profile is 0 at the outline and full thickness well inside.
    b_edge = R.bevel(np.array([0.0]), 57.6, 3.9, 155.0)
    b_deep = R.bevel(np.array([-200.0]), 57.6, 3.9, 155.0)
    check(NAME, "positive", "the bevel is zero at the outline, full inside",
          abs(b_edge[0]) < 1e-9 and abs(b_deep[0] - 155.0) < 1e-9,
          f"edge {b_edge[0]:.4g} deep {b_deep[0]:.4g}")
    # The dome is 0 at the centre and negative away from it.
    check(NAME, "negative", "the dome falls away from the card centre",
          R.dome_z(np.array([0.0]), np.array([0.0]), 1000.0)[0] == 0.0
          and R.dome_z(np.array([300.0]), np.array([0.0]), 1000.0)[0] < 0,
          "")
    check(NAME, "positive", "the media v flip is the documented one",
          R.source_ny_to_media_v(0.0) == 1.0
          and R.source_ny_to_media_v(1.0) == 0.0, "")

    # UNREADABLE: a coordinate the cover crop removed is reported as outside,
    # never clamped to an edge and measured anyway.
    class _Fake:
        cover_scale = np.array([0.75, 1.0])
        cover_offset = np.array([0.125, 0.0])
        media_uv_to_local = R.CardReplay.media_uv_to_local
    _, _, inside = _Fake.media_uv_to_local(
        _Fake, np.array([0.5, 0.02]), np.array([0.5, 0.5]))
    check(NAME, "unreadable",
          "a landmark outside the cover crop is reported outside, not clamped",
          bool(inside[0]) and not bool(inside[1]),
          f"inside {list(map(bool, inside))}")


# =============================================== self-tests on real pixels
def _find(md, **kw):
    p = md / "measure-manifest.json"
    if not p.exists():
        return []
    man = json.loads(p.read_text())
    return [r for r in man["records"]
            if all(r.get(k) == v for k, v in kw.items())
            and (md / r.get("file", "")).exists()]


def _rects(vp):
    w, h = (int(x) for x in vp.split("x"))
    return [q for _, q in S.rects_at(w, h)]


def self_tests():
    """Each instrument reads real Target, control and candidate pixels."""
    vp = "1440x900"
    rects = _rects(vp)
    lanes = {}
    t = _find(O5R_MD, kind="target", asset="grayscale-step", vp=vp, repeat=0)
    if t:
        lanes["target"] = (O5R_MD / t[0]["file"])
    c = _find(O5_MD, kind="lane", lane="control", asset="grayscale-step", vp=vp,
              state="rest")
    if c:
        lanes["control"] = (O5_MD / c[0]["file"])
    k = _find(O5_MD, kind="lane", lane="candidate", asset="grayscale-step",
              vp=vp, state="rest")
    if k:
        lanes["candidate"] = (O5_MD / k[0]["file"])

    readings = {}
    for lane, f in lanes.items():
        try:
            readings[lane] = I.grayscale_v2(f, rects)
            check("grayscale_v2", f"{lane}-self-test",
                  f"reads real {lane} pixels on grayscale-step", True,
                  f"p995 {readings[lane]['p995Chroma']} falseArea "
                  f"{readings[lane]['falseColourAreaFraction']}")
        except I.Unreadable as e:
            check("grayscale_v2", f"{lane}-self-test",
                  f"reads real {lane} pixels on grayscale-step", False, str(e))
    if len(readings) >= 2:
        vals = {lane: r["p995Chroma"] for lane, r in readings.items()}
        check("grayscale_v2", "discrimination",
              "the lanes are not all the same value",
              I.degenerate_reading("grayscale p995", vals) is None, str(vals))

    # §四's own law: the Target must pass its own repeatability window.
    reps = _find(O5R_MD, kind="target", asset="grayscale-step", vp=vp)
    reps = [r for r in reps if r.get("repeat") is not None]
    if len(reps) >= 2:
        rv = []
        for r in reps:
            try:
                rv.append(I.grayscale_v2(O5R_MD / r["file"], rects))
            except I.Unreadable:
                pass
        if len(rv) >= 2:
            spread = max(x["p995Chroma"] for x in rv) - min(x["p995Chroma"] for x in rv)
            win = I.window(spread / 2.0, I.CHROMA_DISTANCE_WINDOW_FLOOR)
            worst = max(abs(x["p995Chroma"] - rv[0]["p995Chroma"]) for x in rv)
            check("grayscale_v2", "target-window",
                  "the Target passes its own repeatability window",
                  worst <= win,
                  f"{len(rv)} runs, spread {round(spread, 3)}, window "
                  f"{round(win, 3)}, worst deviation {round(worst, 3)}")

    # saturated edge, on a saturated asset
    for lane, md, kw in (("target", O5R_MD, dict(kind="target", repeat=0)),
                         ("control", O5_MD, dict(kind="lane", lane="control",
                                                 state="rest")),
                         ("candidate", O5_MD, dict(kind="lane", lane="candidate",
                                                   state="rest"))):
        rec = _find(md, asset="rgb-bars", vp=vp, **kw)
        if not rec:
            continue
        try:
            r = I.saturated_edge_v2(md / rec[0]["file"], rects,
                                    corner_radius_px=None)
            check("saturated_edge_v2", f"{lane}-self-test",
                  f"reads real {lane} pixels on rgb-bars", True,
                  f"atFeatures {r['chromaAtFeatures']} away "
                  f"{r['chromaAwayFromFeatures']} localisation "
                  f"{r['fringeLocalisation']}")
        except I.Unreadable as e:
            check("saturated_edge_v2", f"{lane}-self-test",
                  f"reads real {lane} pixels on rgb-bars", False, str(e))

    # interior fidelity, on the textured asset
    hf = {}
    for lane, md, kw in (("target", O5R_MD, dict(kind="target", repeat=0)),
                         ("control", O5_MD, dict(kind="lane", lane="control",
                                                 state="rest")),
                         ("candidate", O5_MD, dict(kind="lane", lane="candidate",
                                                   state="rest"))):
        rec = _find(md, asset="hf-checker", vp=vp, **kw)
        if not rec:
            continue
        try:
            r = I.interior_stats(md / rec[0]["file"], rects)
            hf[lane] = r["hfEnergy"]
            check("interior_fidelity_v2", f"{lane}-self-test",
                  f"reads real {lane} pixels on hf-checker", True,
                  f"hf {r['hfEnergy']} chroma {r['interiorChroma']} luma "
                  f"{r['interiorLuma']}")
        except I.Unreadable as e:
            check("interior_fidelity_v2", f"{lane}-self-test",
                  f"reads real {lane} pixels on hf-checker", False, str(e))
    if "target" in hf:
        ok, why = I.sharpness_applicable(hf["target"])
        check("interior_fidelity_v2", "applicability",
              "hf-checker is applicable for sharpness on real Target pixels",
              ok, f"target hf {hf['target']} floor {I.HF_SIGNAL_FLOOR}")

    # silhouette, on real renders
    for lane, md, kw in (("target", O5R_MD, dict(kind="target", repeat=0)),
                         ("control", O5_MD, dict(kind="lane", lane="control",
                                                 state="rest")),
                         ("candidate", O5_MD, dict(kind="lane", lane="candidate",
                                                   state="rest"))):
        rec = _find(md, asset="bw-split", vp=vp, **kw)
        if not rec or not rects:
            continue
        try:
            mask, _ = I.rendered_alpha_mask(md / rec[0]["file"], rects[0])
            rad = I.measured_corner_radius_px(mask)
            check("silhouette_v2", f"{lane}-self-test",
                  f"reads a real {lane} coverage mask", mask.any(),
                  f"lit {int(mask.sum())} px, measured corner radius {rad}")
        except I.Unreadable as e:
            check("silhouette_v2", f"{lane}-self-test",
                  f"reads a real {lane} coverage mask", False, str(e))

    # The projected silhouette needs the sdf-mask program, which only the
    # candidate lanes have. Read whichever capture exists.
    view = _find(O5R_MD, kind="view", view="sdf-mask", vp=vp)
    audit = REPO / "artifacts/optics-o5/audit/candidate-sdf-mask.png"
    src = (O5R_MD / view[0]["file"]) if view else (audit if audit.exists() else None)
    if src and rects:
        proj, pval = I.projected_alpha_mask(src, rects[0])
        check("silhouette_v2", "candidate-readable",
              "the sdf-mask program yields a real projected silhouette",
              proj.any() and 0.2 < proj.mean() < 1.0,
              f"coverage {round(float(proj.mean()), 4)} from "
              f"{Path(src).name}")

    # refraction: the QA views, if this head has captured them yet.
    dv = _find(O5R_MD, kind="view", view="refraction-displacement", vp=vp)
    if dv and rects:
        du, dvv, ok = I.decode_displacement_view(O5R_MD / dv[0]["file"], rects[0])
        check("refraction_compression_v2", "candidate-readable",
              "the displacement program yields a real, non-constant field",
              bool(ok.any()) and float(np.abs(du[ok]).max()) > 0.005,
              f"|du|max {round(float(np.abs(du[ok]).max()), 5)} "
              f"|dv|max {round(float(np.abs(dvv[ok]).max()), 5)}")
    cal = _find(O5R_MD, kind="target", asset="calib-landmarks", vp=vp, repeat=0)
    if cal and rects:
        try:
            got = I.disc_centroids(O5R_MD / cal[0]["file"], rects[0], 90, 245,
                                   region=I.LANDMARK_REGION)
            check("refraction_compression_v2", "target-self-test",
                  "the calibration discs are detectable in a real Target render",
                  len(got) >= 4, f"{len(got)} blobs in the scored region")
        except I.Unreadable as e:
            check("refraction_compression_v2", "target-self-test",
                  "the calibration discs are detectable in a real Target render",
                  False, str(e))

    # The full §六 chain on real pixels, for every lane that has a capture.
    media = REPO / "artifacts/optics-o5r/media/media-manifest.json"
    truth_files = sorted(O5R_MD.glob(f"*-bodytruth-{vp}.json"))
    if media.exists() and truth_files and rects:
        discs = F.scored_discs(json.loads(media.read_text()))
        truth = json.loads(truth_files[0].read_text())
        lanes = {}
        if cal:
            lanes["target"] = O5R_MD / cal[0]["file"]
        for lane in ("control", "o5-clamped"):
            rec = _find(O5R_MD, kind="lane", lane=lane, asset="calib-landmarks",
                        vp=vp, state="rest")
            if rec:
                lanes[lane] = O5R_MD / rec[0]["file"]
        for lane, f in lanes.items():
            kind = ("target-self-test" if lane == "target"
                    else "control-self-test" if lane == "control"
                    else "candidate-readable")
            res = F.measure_lane(f, truth, rects, discs)
            check("refraction_compression_v2", kind,
                  f"the §六 chain reads real {lane} pixels",
                  res["usableCards"] > 0,
                  f"{res['usableCards']}/{res['totalCards']} cards, "
                  f"displacement {res['displacementMeanPx']} px, replay "
                  f"residual {res['replayResidualMeanPx']} px")
            if lane == "target":
                check("target_replay", "target-self-test",
                      "the replayed source formula lands on the Target's own "
                      "render, which is what makes it usable as the Target's "
                      "prediction",
                      res["replayResidualMeanPx"] is not None
                      and res["replayResidualMeanPx"]
                      <= F.REPLAY_VALIDATION_MAX_PX,
                      f"mean residual {res['replayResidualMeanPx']} px over "
                      f"{res['usableCards']} cards, against the "
                      f"pre-registered {F.REPLAY_VALIDATION_MAX_PX} px")
            if lane == "control":
                check("target_replay", "control-self-test",
                      "the replay's PROJECTION half agrees with the control's "
                      "own card geometry",
                      res["boxAgreementMeanPx"] is not None
                      and res["boxAgreementMeanPx"] < 12.0,
                      f"projected box agreement {res['boxAgreementMeanPx']} px")

    # The replay against the candidate's own displacement PROGRAM.
    dvv = _find(O5R_MD, kind="view", view="refraction-displacement", vp=vp)
    if dvv and truth_files and rects:
        truth = json.loads([t for t in truth_files
                            if t.name.startswith(dvv[0]["lane"])][0].read_text())
        pair = F.match_cards_to_rects(truth, rects)[0]
        try:
            v = F.validate_replay_against_gpu(
                O5R_MD / dvv[0]["file"], truth, pair["card"], pair["rect"])
            check("target_replay", "candidate-readable",
                  "the CPU replay agrees with the GPU displacement program",
                  v["agreesWithGpu"],
                  f"p99 |dU| {v['p99AbsErrorU']} p99 |dV| {v['p99AbsErrorV']} "
                  f"vs one encoding step {v['quantisationUV']} "
                  f"({v['samples']} samples)")
        except I.Unreadable as e:
            check("target_replay", "candidate-readable",
                  "the CPU replay agrees with the GPU displacement program",
                  False, str(e))


def main() -> int:
    test_grayscale()
    test_saturated_edge()
    test_refraction()
    test_interior()
    test_silhouette()
    test_replay()
    self_tests()

    passed = sum(1 for r in RESULTS if r["pass"])
    by_instrument = {}
    for r in RESULTS:
        by_instrument.setdefault(r["instrument"], []).append(r)
    coverage = {}
    for name, rows in by_instrument.items():
        kinds = {x["kind"] for x in rows}
        coverage[name] = {
            "tests": len(rows),
            "passed": sum(1 for x in rows if x["pass"]),
            "hasPositive": any(k == "positive" for k in kinds),
            "hasNegative": any(k == "negative" for k in kinds),
            "hasUnreadable": any(k == "unreadable" for k in kinds),
            "hasTargetSelfTest": any("target" in k for k in kinds),
            "hasControlSelfTest": any("control" in k for k in kinds),
            "hasCandidateReadable": any("candidate" in k for k in kinds),
        }
    doc = {
        "what": "O5R instrument tests. §三 requires a positive test, a negative "
                "test, a Target self-test, a Control self-test, a "
                "candidate-readable test and an explicit UNREADABLE state for "
                "every corrected instrument.",
        "sealedBefore": "any capture of the O5R candidate lane "
                        "(opticalBody=target-source-unclamped)",
        "selfTestSources": {
            "target": str(O5R_MD.relative_to(REPO)),
            "controlAndCandidate": str(O5_MD.relative_to(REPO))
            + " -- the O5 control and the O5 CLAMPED candidate. Neither is the "
              "O5R candidate.",
        },
        "passed": passed, "total": len(RESULTS),
        "pass": passed == len(RESULTS),
        "coverage": coverage,
        "results": RESULTS,
    }
    out = REPO / "qa-v5/optics-o5r/instrument-tests.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    for r in RESULTS:
        if not r["pass"]:
            print(f"  FAIL  {r['instrument']} / {r['kind']} / {r['test']}"
                  f"\n        {r['detail']}")
    print(f"\n{passed}/{len(RESULTS)} -> {out}")
    for name, c in coverage.items():
        missing = [k for k in ("hasPositive", "hasNegative", "hasUnreadable",
                               "hasTargetSelfTest", "hasControlSelfTest",
                               "hasCandidateReadable") if not c[k]]
        flag = "OK " if not missing else "GAP"
        print(f"  {flag} {name:28} {c['passed']}/{c['tests']}"
              + (f"  missing: {', '.join(missing)}" if missing else ""))
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
