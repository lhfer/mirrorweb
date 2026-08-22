#!/usr/bin/env python3
"""O5 sealed instruments.

Sealed BEFORE any candidate pixel exists. Nothing here may be replaced after
capture; a coding that turns out to be awkward is reported as awkward and
scored as written.

Carried forward unchanged from O4 (already sealed once, already tested, and
re-tested here): band width, band energy, the control-derived true silhouette,
gutter-outside-silhouette, the baseline-aware interior branch, the pointer
judge, and the bool-safe aggregator guards. Re-deriving them would be a silent
re-coding of measurands O4 was scored on.

New for O5, because O5 measures a body that has a real refraction system for
the first time:

  landmark_positions    where a KNOWN media boundary lands on the card
  edge_compression      that position minus the analytic flat position -- the
                        displacement refraction actually produces
  spectral_structure    whether high-frequency content survives as structure
                        rather than as blur or a flat desaturation
  white_reflection_ratio, dark_side_luma, grayscale_chroma
  sdf_alpha_truth       the candidate's own analytic silhouette, so its alpha
                        edge is judged against what it claims rather than
                        against a control-derived mask

A note on why edge compression is measured as a DISPLACEMENT and not as an
absolute position. Our clip 2 carries a frozen crop (focusY 0.46, zoom 1.06)
that the Target's centred cover does not have, so absolute landmark positions
are legitimately different on that card and comparing them would score a frozen
product decision as an optical defect. Subtracting each render's OWN analytic
flat position removes the cover law from the comparison and leaves only what
refraction did. The analytic baseline is additionally checked against a
media-only render wherever one exists (local lanes), so the subtraction is
verified, not assumed.
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


O4 = _load("o5_o4_ins", "o4_instruments.py")

# ---------------------------------------------------------------- carried over
band_width_px = O4.band_width_px
band_energy = O4.band_energy
true_silhouette = O4.true_silhouette
gutter_outside_silhouette = O4.gutter_outside_silhouette
gutter_pair_outside_silhouette = O4.gutter_pair_outside_silhouette
interior_change = O4.interior_change
glass_reflection_masks = O4.glass_reflection_masks
pointer_judge = O4.pointer_judge
AggregatorShapeError = O4.AggregatorShapeError
zero_errors = O4.zero_errors
require_number = O4.require_number
BAND_THRESHOLD = O4.BAND_THRESHOLD
BAND_INSIDE_PX = O4.BAND_INSIDE_PX
MEDIA_BLACK = O4.MEDIA_BLACK
INTERIOR_RELATIVE_BRANCH_FLOOR = O4.INTERIOR_RELATIVE_BRANCH_FLOOR

# ---------------------------------------------------------------- new codings

# Edge-band geometry, identical to the band instruments so the two are read on
# the same pixels.
EDGE_BAND_FRACTION = 0.08          # outer 8% of card width
EDGE_BAND_HEIGHT_FRACTION = 0.60   # central 60% of card height

# Landmark search: a horizontal strip across the card's vertical middle.
LANDMARK_STRIP_FRACTION = 0.16     # central 16% of card height, averaged
LANDMARK_MIN_CONTRAST = 18.0       # a step smaller than this is not a landmark
# A measured peak further than this from its expected flat position is not that
# landmark; refraction at this card size moves features by single-digit pixels,
# so a 24 px search radius is generous while still refusing an obvious mispair.
LANDMARK_MAX_PAIR_PX = 24.0
# The analytic flat baseline must agree with a real media-only render to inside
# a THIRD of the sealed compression window. Verifying it only to within the
# window itself would let a baseline error the size of the whole tolerance be
# stamped "verified".
BASELINE_RESIDUAL_MAX_PX = 0.5

# Spectral structure: tile size for local energy correlation, in card pixels.
SPECTRAL_TILE_PX = 12

# Gate floors, sealed now. Each window is max(2 * TargetRepeatability, floor);
# the floor exists so that a Target that happens to be very repeatable on one
# metric cannot produce an impossibly narrow window.
BAND_WINDOW_FLOOR_PX = 1.5         # §九.1, given by the brief
DARK_LUMA_WINDOW_FLOOR = 6.0       # 8-bit levels
WHITE_RATIO_WINDOW_FLOOR = 0.15    # dimensionless ratio
COMPRESSION_WINDOW_FLOOR_PX = 1.5  # px of landmark displacement
GRAYSCALE_CHROMA_CEILING = 6.0     # §九.4, absolute: no achromatic tint
SPECTRAL_CORRELATION_FLOOR = 0.70  # §九.6, candidate vs Target structure
HF_ENERGY_RETENTION_FLOOR = 0.60   # §九.6, candidate/Target high-freq energy


def _rgb(path_or_img):
    img = (Image.open(path_or_img) if not hasattr(path_or_img, "convert")
           else path_or_img)
    return np.asarray(img.convert("RGB"), dtype=np.float32)


def _lum(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def _chroma(a):
    return a.max(axis=-1) - a.min(axis=-1)


def edge_band(a, rect, side):
    """The outer 8% x central 60% band on one side of a card."""
    x0, y0, x1, y1 = rect
    cw, ch = x1 - x0, y1 - y0
    yb0, yb1 = y0 + int(ch * 0.2), y1 - int(ch * 0.2)
    w = max(1, int(cw * EDGE_BAND_FRACTION))
    return a[yb0:yb1, x0:x0 + w] if side == "left" else a[yb0:yb1, x1 - w:x1]


def dark_side_luma(img, rects, side="left"):
    """§九.2. Mean luminance of the dark-side edge band, per card then mean."""
    a = _rgb(img)
    vals = [float(_lum(edge_band(a, r, side)).mean()) for r in rects]
    return {"meanLuma": round(float(np.mean(vals)), 2) if vals else None,
            "perCard": [round(v, 2) for v in vals]}


def white_reflection_ratio(img, rects):
    """§九.3. Bright-side edge band over dark-side edge band, per card.

    A ratio rather than a difference because it is meant to survive an overall
    exposure change: what is being asked is how much brighter the reflection
    side is than the shadow side, not how bright either is.
    """
    a = _rgb(img)
    out = []
    for r in rects:
        d = float(_lum(edge_band(a, r, "left")).mean())
        b = float(_lum(edge_band(a, r, "right")).mean())
        out.append(b / max(d, 1.0))
    return {"meanRatio": round(float(np.mean(out)), 4) if out else None,
            "perCard": [round(v, 4) for v in out]}


# The statistic GRAYSCALE_CHROMA_CEILING binds to. Sealed explicitly, because
# "peak chroma" is ambiguous and the ambiguity is not neutral: a max-of-maxes
# is a single-pixel statistic, so one hot texel or one antialiased corner would
# fail the gate regardless of what the body does, and 8-bit rounding of a
# near-grey value already produces chroma of 1-2. The scored statistic is the
# 99.5th percentile over the card interior -- high enough to catch a real
# coloured cast or fringe, robust to a handful of outlier pixels. The raw
# maximum is still reported, as a diagnostic, never as the verdict.
GRAYSCALE_CHROMA_STATISTIC = "p995Chroma"
GRAYSCALE_CHROMA_PERCENTILE = 99.5


def grayscale_chroma(img, rects):
    """§九.4. Chroma inside the card on achromatic media.

    Scored on GRAYSCALE_CHROMA_STATISTIC against GRAYSCALE_CHROMA_CEILING.
    """
    a = _rgb(img)
    peaks, means, p995, pooled = [], [], [], []
    for (x0, y0, x1, y1) in rects:
        c = _chroma(a[y0:y1, x0:x1])
        peaks.append(float(c.max()))
        means.append(float(c.mean()))
        p995.append(float(np.percentile(c, GRAYSCALE_CHROMA_PERCENTILE)))
        pooled.append(c.ravel())
    if not peaks:
        return {"p995Chroma": None, "peakChroma": None, "meanChroma": None,
                "perCardPeak": [], "scoredStatistic": GRAYSCALE_CHROMA_STATISTIC}
    return {"p995Chroma": round(float(np.percentile(
                np.concatenate(pooled), GRAYSCALE_CHROMA_PERCENTILE)), 2),
            "perCardP995": [round(v, 2) for v in p995],
            "peakChroma": round(float(np.max(peaks)), 2),
            "meanChroma": round(float(np.mean(means)), 2),
            "perCardPeak": [round(v, 2) for v in peaks],
            "scoredStatistic": GRAYSCALE_CHROMA_STATISTIC,
            "ceiling": GRAYSCALE_CHROMA_CEILING}


# ---------------------------------------------------------- edge compression

def landmark_positions(img, rect, expected_n=None):
    """On-card x positions (in card-normalised units) of luminance steps.

    Read from a horizontal strip across the card's middle, averaged down to one
    profile, then differentiated. A step is a local extremum of |d luma / dx|
    exceeding LANDMARK_MIN_CONTRAST. Sub-pixel position is the contrast-weighted
    centroid of the gradient peak, which is what makes a 1.5px window a
    meaningful threshold at all.
    """
    a = _rgb(img)
    x0, y0, x1, y1 = rect
    cw, ch = x1 - x0, y1 - y0
    h = max(2, int(ch * LANDMARK_STRIP_FRACTION))
    yc = (y0 + y1) // 2
    strip = _lum(a[yc - h // 2:yc + h // 2, x0:x1]).mean(axis=0)
    g = np.abs(np.diff(strip))
    peaks = []
    i = 1
    while i < len(g) - 1:
        if g[i] >= LANDMARK_MIN_CONTRAST and g[i] >= g[i - 1] and g[i] >= g[i + 1]:
            lo = i
            while lo > 0 and g[lo - 1] >= LANDMARK_MIN_CONTRAST * 0.5:
                lo -= 1
            hi = i
            while hi < len(g) - 1 and g[hi + 1] >= LANDMARK_MIN_CONTRAST * 0.5:
                hi += 1
            w = g[lo:hi + 1]
            centre = float((np.arange(lo, hi + 1) * w).sum() / max(w.sum(), 1e-6))
            # g[i] = s[i+1] - s[i] straddles pixels i and i+1, whose centres
            # are at i+0.5 and i+1.5, so the gradient sample sits at i+1 in
            # continuous card coordinates. Using i+0.5 would bias every
            # landmark half a pixel inward -- a third of the 1.5 px window.
            peaks.append({"nx": round((centre + 1.0) / max(cw, 1), 6),
                          "contrast": round(float(g[lo:hi + 1].max()), 2)})
            i = hi + 1
        else:
            i += 1
    peaks.sort(key=lambda p: -p["contrast"])
    if expected_n:
        peaks = sorted(peaks[:expected_n], key=lambda p: p["nx"])
    return peaks


def flat_landmark_nx(source_nx, cover_scale_x, cover_offset_x):
    """Where a source landmark lands on the card with NO refraction.

    Inverts uv -> uv*coverScale + coverOffset. Returns None when the landmark
    is cropped away, which must be treated as "not measurable here" rather than
    silently clamped to an edge.
    """
    if cover_scale_x <= 1e-9:
        return None
    uv = (source_nx - cover_offset_x) / cover_scale_x
    return uv if -1e-6 <= uv <= 1 + 1e-6 else None


def edge_compression(img, rect, source_landmarks, cover_scale_x,
                     cover_offset_x, media_only_img=None):
    """§九.7. Landmark displacement from the analytic flat position, in px.

    Sign convention: POSITIVE means the landmark moved toward the card's
    nearest edge (outward), which is what compression toward the rim looks
    like; negative means it moved toward the centre.

    When a media-only render is supplied the analytic flat baseline is checked
    against it and the residual is reported. A large residual invalidates the
    analytic baseline for that card and the reading is marked unverified rather
    than quietly used.
    """
    x0, _, x1, _ = rect
    cw = x1 - x0
    flat = sorted(f for f in (flat_landmark_nx(s, cover_scale_x, cover_offset_x)
                              for s in source_landmarks) if f is not None)
    got = landmark_positions(img, rect, expected_n=len(flat))

    # Pair by NEAREST, not by position, and refuse to pair beyond the search
    # radius. Positional zip() is what makes this instrument dangerous: if one
    # expected landmark is missing and a rim edge is picked up instead, every
    # pair shifts by one and the mean displacement comes out large and
    # confident -- or, with two survivors of three, cancels to a perfect zero.
    # Either way the number looks measured. Anything that cannot be paired
    # cleanly and one-to-one invalidates the reading instead.
    rows, used = [], set()
    for f in flat:
        best, best_d = None, None
        for i, pk in enumerate(got):
            if i in used:
                continue
            d = abs(pk["nx"] - f) * cw
            if best_d is None or d < best_d:
                best, best_d = i, d
        if best is None or best_d > LANDMARK_MAX_PAIR_PX:
            continue
        used.add(best)
        pk = got[best]
        d_nx = pk["nx"] - f
        outward = d_nx if f >= 0.5 else -d_nx
        rows.append({"flatNx": round(f, 6), "measuredNx": pk["nx"],
                     "displacementPx": round(d_nx * cw, 3),
                     "outwardPx": round(outward * cw, 3),
                     "pairDistancePx": round(best_d, 3),
                     "contrast": pk["contrast"]})

    check = None
    if media_only_img is not None and flat:
        mo = landmark_positions(media_only_img, rect, expected_n=len(flat))
        if len(mo) == len(flat):
            check = round(float(np.mean(
                [abs(m["nx"] - f) * cw
                 for m, f in zip(sorted(mo, key=lambda q: q["nx"]), flat)])), 3)

    # The analytic baseline is only usable if it agrees with the real
    # media-only render to well INSIDE the window the displacement is scored
    # in. A baseline allowed to be wrong by more than the window can certify a
    # candidate with no refraction at all as having moved, or the reverse.
    baseline_ok = None if check is None else check < BASELINE_RESIDUAL_MAX_PX

    clean = len(rows) == len(flat) and len(flat) > 0
    return {
        "landmarks": rows,
        # A partial or mispaired set has no mean worth reporting. `None` here
        # is a refusal to answer, and the caller must treat it as one.
        "meanOutwardPx": (round(float(np.mean([r["outwardPx"] for r in rows])), 3)
                          if clean else None),
        "matched": len(rows), "expected": len(flat),
        "cleanlyPaired": clean,
        "maxPairDistancePx": (round(max(r["pairDistancePx"] for r in rows), 3)
                              if rows else None),
        "flatBaselineResidualPx": check,
        "flatBaselineVerified": baseline_ok,
        "usable": bool(clean and (baseline_ok is not False)),
    }


# ---------------------------------------------------------- spectral structure

# O4's sealed hf coding insets to the card's middle 55% before taking the
# Laplacian (qa-v5/optics-o4/gate-coding.json item 6). The inset is PART of
# that coding, not a caller's choice, so reading the whole card here would be
# a different measurand wearing the same name -- and HF_ENERGY_RETENTION_FLOOR
# is a ratio of exactly this quantity.
HF_INSET_FRACTION = 0.225


def hf_energy(img, rects):
    """Mean absolute 4-neighbour Laplacian over the card's middle 55%.

    O4's coding, inset included. The card's outer ring carries the reflection
    band and the silhouette, whose gradients dwarf the media's own texture; a
    whole-card reading would mostly measure the rim and call it high-frequency
    media structure.
    """
    a = _rgb(img)
    out = []
    for (x0, y0, x1, y1) in rects:
        cw, ch = x1 - x0, y1 - y0
        ix, iy = int(cw * HF_INSET_FRACTION), int(ch * HF_INSET_FRACTION)
        p = _lum(a[y0 + iy:y1 - iy, x0 + ix:x1 - ix])
        if p.shape[0] < 3 or p.shape[1] < 3:
            continue
        lap = (4 * p[1:-1, 1:-1] - p[:-2, 1:-1] - p[2:, 1:-1]
               - p[1:-1, :-2] - p[1:-1, 2:])
        out.append(float(np.abs(lap).mean()))
    return round(float(np.mean(out)), 4) if out else None


def _tiles(plane, tile):
    h, w = plane.shape
    th, tw = h // tile, w // tile
    if th < 2 or tw < 2:
        return None
    return plane[:th * tile, :tw * tile].reshape(th, tile, tw, tile) \
                                        .mean(axis=(1, 3))


def spectral_structure(img, rects, tile=SPECTRAL_TILE_PX):
    """§九.6. Per-tile high-frequency and chroma energy maps for one render.

    Returned as flat lists so two renders can be correlated tile by tile. A
    candidate that merely blurs the checker loses HF energy everywhere; one
    that merely desaturates loses chroma energy everywhere; one that reproduces
    the Target's refraction puts BOTH where the Target puts them, which is what
    a per-tile correlation tests and a global mean cannot.
    """
    a = _rgb(img)
    hf_maps, chroma_maps = [], []
    for (x0, y0, x1, y1) in rects:
        blk = a[y0:y1, x0:x1]
        p = _lum(blk)
        if p.shape[0] < 3 or p.shape[1] < 3:
            continue
        lap = np.zeros_like(p)
        lap[1:-1, 1:-1] = np.abs(4 * p[1:-1, 1:-1] - p[:-2, 1:-1] - p[2:, 1:-1]
                                 - p[1:-1, :-2] - p[1:-1, 2:])
        hm, cm = _tiles(lap, tile), _tiles(_chroma(blk), tile)
        if hm is None or cm is None:
            continue
        hf_maps.append(hm.ravel())
        chroma_maps.append(cm.ravel())
    if not hf_maps:
        return None
    return {"tilePx": tile,
            "hfTiles": [round(float(v), 4) for v in np.concatenate(hf_maps)],
            "chromaTiles": [round(float(v), 4) for v in np.concatenate(chroma_maps)],
            "hfMean": round(float(np.concatenate(hf_maps).mean()), 4),
            "chromaMean": round(float(np.concatenate(chroma_maps).mean()), 4)}


def correlate(a_list, b_list):
    """Pearson correlation, with the degenerate cases named rather than NaN."""
    a, b = np.asarray(a_list, float), np.asarray(b_list, float)
    n = min(len(a), len(b))
    if n < 4:
        return {"r": None, "n": n, "note": "too few tiles to correlate"}
    a, b = a[:n], b[:n]
    if a.std() < 1e-9 or b.std() < 1e-9:
        return {"r": None, "n": n, "note": "a series is constant"}
    return {"r": round(float(np.corrcoef(a, b)[0, 1]), 4), "n": n}


def edge_profile(img, rects, inside_px=BAND_INSIDE_PX, outside_px=4):
    """Mean inward luminance profile at the dark-side edge, per card."""
    a = _rgb(img)
    profs = []
    for (x0, y0, x1, y1) in rects:
        ch = y1 - y0
        seg = a[y0 + int(ch * .42):y0 + int(ch * .58),
                max(0, x0 - outside_px):x0 + inside_px]
        if seg.shape[1] == outside_px + inside_px:
            profs.append(_lum(seg).mean(axis=0))
    if not profs:
        return None
    return [round(float(v), 3) for v in np.mean(profs, axis=0)]


def false_colour_outside_features(img, rects, feature_threshold=24.0):
    """§九.6. Chroma sitting where the media has no luminance structure.

    On an achromatic checker any chroma is false; this locates it relative to
    the media's own edges so that legitimate spectral fringing AT a feature is
    distinguished from a wash of colour BETWEEN features.
    """
    a = _rgb(img)
    at_feat, away = [], []
    for (x0, y0, x1, y1) in rects:
        blk = a[y0:y1, x0:x1]
        p = _lum(blk)
        if p.shape[0] < 3 or p.shape[1] < 3:
            continue
        gx = np.zeros_like(p)
        gx[:, 1:-1] = np.abs(p[:, 2:] - p[:, :-2])
        gy = np.zeros_like(p)
        gy[1:-1, :] = np.abs(p[2:, :] - p[:-2, :])
        feat = (gx + gy) >= feature_threshold
        c = _chroma(blk)
        if feat.any():
            at_feat.append(float(c[feat].mean()))
        if (~feat).any():
            away.append(float(c[~feat].mean()))
    return {
        "chromaAtFeatures": round(float(np.mean(at_feat)), 3) if at_feat else None,
        "chromaAwayFromFeatures": round(float(np.mean(away)), 3) if away else None,
        "featureThreshold": feature_threshold,
    }


# ---------------------------------------------------------- silhouette truth

def sdf_alpha_truth(rect, corner_radius_px, shape):
    """§九.10. The candidate's OWN analytic silhouette from the contract.

    sdf = length(max(q,0)) + min(max(q.x,q.y),0) - r, with q = |p| - half + r,
    evaluated at pixel centres in card space. This is the shape the candidate
    claims to draw, so its alpha edge is judged against it rather than against
    a mask derived from the other lane.
    """
    x0, y0, x1, y1 = rect
    cw, chh = x1 - x0, y1 - y0
    hx, hy = cw / 2.0, chh / 2.0
    r = min(corner_radius_px, hx, hy)
    ys, xs = np.mgrid[0:chh, 0:cw]
    px = xs + 0.5 - hx
    py = ys + 0.5 - hy
    qx = np.abs(px) - hx + r
    qy = np.abs(py) - hy + r
    outside = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
    inside = np.minimum(np.maximum(qx, qy), 0)
    sdf = outside + inside - r
    full = np.zeros(shape[:2], dtype=np.float32)
    full[y0:y1, x0:x1] = sdf
    return full


def alpha_edge_agreement(img, rect, corner_radius_px, background_rgb=None,
                         aa_px=1.5):
    """How well a render's own coverage agrees with its analytic SDF.

    Counts pixels the SDF says are OUTSIDE (beyond the antialiasing band) that
    nonetheless differ from the background. That is light beyond the rounded
    rect -- §九.10's actual question -- and it is asked of a single render,
    with no cross-lane mask.
    """
    a = _rgb(img)
    sdf = sdf_alpha_truth(rect, corner_radius_px, a.shape)
    x0, y0, x1, y1 = rect
    box = np.zeros(a.shape[:2], bool)
    box[y0:y1, x0:x1] = True
    outside = box & (sdf > aa_px)
    if background_rgb is None:
        # Sample from OUTSIDE the card rect, never from its corner. The card's
        # corner lies outside the rounded-rect SDF but inside the rect, so a
        # card that wrongly lights its corners would have that lit corner taken
        # as the background -- and the instrument would then find nothing
        # differing from it. That is precisely the defect this function exists
        # to catch, so the sample has to come from beyond the rect.
        pad = 6
        ring = []
        h, w = a.shape[:2]
        if y0 - pad >= 0:
            ring.append(a[max(0, y0 - pad):y0, x0:x1].reshape(-1, 3))
        if y1 + pad <= h:
            ring.append(a[y1:y1 + pad, x0:x1].reshape(-1, 3))
        if x0 - pad >= 0:
            ring.append(a[y0:y1, max(0, x0 - pad):x0].reshape(-1, 3))
        if x1 + pad <= w:
            ring.append(a[y0:y1, x1:x1 + pad].reshape(-1, 3))
        if not ring:
            raise AggregatorShapeError(
                "alpha_edge_agreement: the card rect touches every frame edge, "
                "so no background can be sampled; pass background_rgb")
        background_rgb = np.concatenate(ring).mean(axis=0)
    d = np.abs(a - np.asarray(background_rgb, np.float32)).max(axis=2)
    lit = outside & (d > 2.0)
    return {"outsidePixels": int(outside.sum()),
            "litOutsidePixels": int(lit.sum()),
            "maxDeltaOutside": round(float(d[outside].max()), 2)
            if outside.any() else 0.0,
            "cornerRadiusPx": round(float(corner_radius_px), 3),
            "aaBandPx": aa_px}


# ---------------------------------------------------------- windows & verdicts

def window(target_repeatability, floor):
    """The sealed two-sided window: max(2 * repeatability, floor)."""
    return max(2.0 * float(target_repeatability), float(floor))


def enters(candidate, target, win):
    return abs(float(candidate) - float(target)) <= win


def toward(candidate, control, target):
    """Direction test: did the candidate move toward the Target from control?

    Returns None when control is already at the Target within a hair, because
    'moved toward' has no meaning there and reporting a direction would be
    inventing one.
    """
    if abs(control - target) < 1e-9:
        return None
    return abs(candidate - target) < abs(control - target)
