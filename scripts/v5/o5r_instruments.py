#!/usr/bin/env python3
"""O5R corrected instruments.

Sealed BEFORE any scored O5R capture. What "corrected" means here is narrow and
specific: four O5 items could not read the candidate, and two O5 PASS rows
carried no signal. Each repair below fixes the identified fault and nothing
else. The O5 codings themselves are NOT edited -- `o5_instruments.py` is
untouched, so §十三A's re-run of the original gate reads exactly what it read.

The faults, and the repair each one gets:

  item 4  an ABSOLUTE chroma ceiling of 6.0 that the Target fails at 30.0.
          Repaired by measuring the candidate's chroma DISTANCE TO THE TARGET
          and by separating colour that sits on the media's own encoded edges
          (which the Target carries too) from colour that sits away from them
          (which nothing justifies).                              -> §四

  item 5  every lane returned 0.0 on every saturated asset, and the sealed
          comparison was vacuously true. Repaired by measuring chroma where the
          MEDIA has features and where it does not, inside the rim band, with
          an explicit UNREADABLE state when neither population exists. -> §五

  item 7  an analytic FLAT-card baseline for a domed plane under perspective.
          Repaired by reading the displacement out of the render itself
          through three QA-only programs, and by replaying the source formula
          for the Target rather than assuming a flat mapping.       -> §六

  item 9  "no blurrier than the control", where the control is SHARPER than
          the Target. Repaired by asking for proximity to the Target, and by
          declaring assets whose Target HF energy is below a pre-registered
          floor NOT APPLICABLE instead of letting noise decide.     -> §七

  item 10 an axis-aligned rounded rect over a screen-space bounding box whose
          corners sit 109 px from the real projected quad. Repaired by using
          the real projected body -- the sdf-mask program for the candidate,
          the same projection replayed for the Target.              -> §八

Two rules apply to everything in this file.

  DEGENERACY IS NOT A PASS. If every lane produces the same constant -- zero or
  otherwise -- the instrument returns UNREADABLE. That is what made O5 items 5
  and 14 report a pass they had not earned.

  UNREADABLE IS NOT A FAIL EITHER. An instrument that cannot answer says so.
  Converting either way is the failure mode this file exists to remove.
"""
from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

# --------------------------------------------------------------- constants
# Every number below is pre-registered here, before any scored O5R capture.

# §四 / §五. A pixel is "at a media feature" when the local luminance gradient
# reaches this. Carried unchanged from O5's false_colour_outside_features, so
# the two rounds mean the same thing by "feature".
FEATURE_GRADIENT_THRESHOLD = 24.0

# §四. A pixel counts as FALSE COLOUR on an achromatic asset when its chroma
# exceeds this AND it is away from a media feature. Set above the 8-bit
# rounding of a near-grey value (1-2) and above 4:2:0 ringing on a flat field,
# and below the Target's own p99.5 of 30, so the statistic is about a cast or a
# wash rather than about encode noise.
FALSE_COLOUR_CHROMA = 12.0

# §四. A false-colour blob smaller than this (as a fraction of card area) is
# noise, not a cast. 0.0002 of a 300x225 card is about 13 px.
FALSE_COLOUR_MIN_BLOB_FRACTION = 0.0002

# §五. The inside-rim band, as a fraction of card width. The Target's own
# bevelWidth ratio: the band where its refraction and reflection actually live,
# so "a broad coloured rim" is asked about exactly the region a rim occupies.
RIM_BAND_FRACTION = 0.192

# §五. Chroma above this inside the rim band, away from any media feature, is
# a broad coloured rim rather than a fringe.
BROAD_RIM_CHROMA = 18.0

# §七. Below this Target interior HF energy an asset has no interior structure
# to measure and is NOT_APPLICABLE for sharpness. O5's own numbers bracket it
# cleanly: bw-split 4.80, rgb-bars 5.68, hf-checker 149.55.
HF_SIGNAL_FLOOR = 20.0

# §七. Tile size for per-tile correlation, in card pixels. Same as O5's.
TILE_PX = 12

# §六. A landmark centroid further than this from its predicted unrefracted
# position is not that landmark. Refraction moves a feature by single-digit
# pixels at these card sizes; the discs are 26-44 px in a 1200 px source.
LANDMARK_MAX_PAIR_PX = 28.0
# A blob outside this area window is not one of the calibration discs. The
# discs are 26-44 px radius in a 1200 px source, and the source maps onto the
# whole card width, so on any of the O5R viewports a disc covers between about
# 0.2% and 0.6% of the card. The window is deliberately wide either side of
# that: its job is to reject the reflection band, the white rim and the
# Target's own glyphs, not to select on size.
LANDMARK_MIN_AREA_FRACTION = 0.0008
LANDMARK_MAX_AREA_FRACTION = 0.02
# Fewer matched landmarks than this and the card cannot be scored.
LANDMARK_MIN_MATCHES = 4
# The scored landmark region, in card-normalised coordinates. Upper half only:
# the Target draws its headline across the lower half and cannot be asked to
# stop, and a white glyph is not distinguishable from a white disc.
LANDMARK_REGION = (0.0, 0.0, 1.0, 0.5)
# Relative luminance threshold for disc detection, between ground and disc.
LANDMARK_LEVEL_FRACTION = 0.55

# §六. The displacement view's encoding, mirrored from V5_DISPLACEMENT_GAIN.
DISPLACEMENT_GAIN = 2.0

# §八. Antialias band half-width, in px, outside which a pixel is unambiguously
# outside the silhouette.
SILHOUETTE_AA_PX = 1.5
# A pixel differing from the background by more than this is "lit".
SILHOUETTE_LIT_DELTA = 2.0

# §十二. Final-third heap slope below this is flat. A real per-wrap leak in
# this app shows as tens of MB over fifteen minutes; browser JS heap noise on
# an idle-ish page is well under a megabyte a minute.
HEAP_SLOPE_FLOOR_MB_PER_MIN = 0.35

# Window floors, carried from O5 so the two gates' shared rows stay comparable.
BAND_WINDOW_FLOOR_PX = 1.5
DARK_LUMA_WINDOW_FLOOR = 6.0
WHITE_RATIO_WINDOW_FLOOR = 0.15
# §四/§五/§七/§八 windows are Target-relative and get their own floors.
CHROMA_DISTANCE_WINDOW_FLOOR = 3.0        # 8-bit chroma levels
FALSE_COLOUR_AREA_WINDOW_FLOOR = 0.004    # fraction of card area
COMPRESSION_WINDOW_FLOOR_PX = 1.5
HF_DISTANCE_WINDOW_FLOOR = 4.0            # Laplacian energy units
SILHOUETTE_EDGE_WINDOW_FLOOR_PX = 1.0


class Unreadable(Exception):
    """Raised by an instrument that cannot answer. Never caught into a PASS."""


UNREADABLE = "INSTRUMENT_UNREADABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"


# --------------------------------------------------------------- primitives

def rgb(path_or_img) -> np.ndarray:
    img = (Image.open(path_or_img) if not hasattr(path_or_img, "convert")
           else path_or_img)
    return np.asarray(img.convert("RGB"), dtype=np.float32)


def lum(a: np.ndarray) -> np.ndarray:
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def chroma(a: np.ndarray) -> np.ndarray:
    return a.max(axis=-1) - a.min(axis=-1)


def feature_mask(block: np.ndarray,
                 threshold: float = FEATURE_GRADIENT_THRESHOLD) -> np.ndarray:
    """Where the render's own luminance has structure.

    Central differences on both axes, the same coding O5 used. This reads the
    RENDER, not the source media, on purpose: a feature that refraction moved
    is still a feature, and asking "is there colour where there is no edge"
    only means anything about the picture in front of you.
    """
    p = lum(block)
    gx = np.zeros_like(p)
    gx[:, 1:-1] = np.abs(p[:, 2:] - p[:, :-2])
    gy = np.zeros_like(p)
    gy[1:-1, :] = np.abs(p[2:, :] - p[:-2, :])
    return (gx + gy) >= threshold


def feature_mask_chromatic(block: np.ndarray,
                           threshold: float = FEATURE_GRADIENT_THRESHOLD
                           ) -> np.ndarray:
    """Where the render has structure of ANY kind -- luminance or colour.

    §五 asks for a "media gradient mask" on SATURATED media, and there the
    luminance-only mask of §四 is the wrong tool: a red bar beside a blue one
    differs by 140 levels in two channels and by only twenty in luminance, so a
    luminance-gradient mask reports no features at all and the instrument would
    answer "no colour at features" about media that is nothing but colour at
    features. §四 keeps the luminance-only mask on purpose -- there, letting
    colour define its own excuse would make the false-colour test circular.

    The gradient is taken PER CHANNEL and maximised, not on a chroma scalar:
    max-minus-min is a saturation measure, so a red-to-blue boundary -- the
    canonical saturated edge -- has a chroma gradient of exactly zero.
    """
    d = np.zeros(block.shape[:2], np.float32)
    for ch in range(3):
        p = block[..., ch]
        gx = np.zeros_like(d)
        gx[:, 1:-1] = np.abs(p[:, 2:] - p[:, :-2])
        gy = np.zeros_like(d)
        gy[1:-1, :] = np.abs(p[2:, :] - p[:-2, :])
        d = np.maximum(d, gx + gy)
    return d >= threshold


def card_blocks(img, rects):
    a = rgb(img)
    return [a[y0:y1, x0:x1] for (x0, y0, x1, y1) in rects if
            y1 > y0 and x1 > x0]


def rim_distance(shape, corner_radius_px, rim_band_px):
    """Distance INSIDE the rounded-rect silhouette, in px, per pixel.

    Uses the same SDF the Target's own alpha and rim use, evaluated in card
    space. Returned as `-sdf`, so a pixel `d` px inside the outline has
    value `d`. `rim_band_px` names the band this is asked about.
    """
    h, w = shape
    hx, hy = w / 2.0, h / 2.0
    r = min(corner_radius_px, hx, hy)
    ys, xs = np.mgrid[0:h, 0:w]
    qx = np.abs(xs + 0.5 - hx) - hx + r
    qy = np.abs(ys + 0.5 - hy) - hy + r
    outside = np.sqrt(np.maximum(qx, 0.0) ** 2 + np.maximum(qy, 0.0) ** 2)
    sdf = outside + np.minimum(np.maximum(qx, qy), 0.0) - r
    inside = -sdf
    return inside, (inside >= 0) & (inside <= rim_band_px)


def all_same(values, tol=1e-9) -> bool:
    """The degeneracy test §三 requires: every lane the same constant."""
    vs = [v for v in values if v is not None]
    if len(vs) < 2:
        return True
    return max(vs) - min(vs) <= tol


def degenerate_reading(name, lanes: dict, tol=1e-9):
    """UNREADABLE when every lane agrees exactly, or when any lane is missing.

    §三: "No instrument may return PASS when all compared lanes produce the
    same zero or constant value." This is the single place that rule lives, so
    every scored row can be routed through it and no row can forget.
    """
    missing = [k for k, v in lanes.items() if v is None]
    if missing:
        return {"status": UNREADABLE,
                "why": f"{name}: no reading from {', '.join(sorted(missing))}"}
    if all_same(list(lanes.values()), tol):
        return {"status": UNREADABLE,
                "why": f"{name}: every lane returned the same value "
                       f"({list(lanes.values())[0]}); the metric cannot "
                       f"discriminate here and a comparison against it would "
                       f"be vacuously true"}
    return None


def window(target_repeatability, floor):
    """The sealed two-sided window, carried from O5: max(2 * repeat, floor)."""
    return max(2.0 * float(target_repeatability), float(floor))


# ------------------------------------------------------- §四 grayscale v2

def grayscale_v2(img, rects, corner_radius_px=None):
    """Achromatic behaviour of one render, as a distribution plus a map.

    Nothing here is a verdict. §四's law is that the candidate is scored
    against the TARGET, not against an ideal zero-chroma image, so this returns
    the quantities and `grayscale_distance` does the comparing.

    The seven things §四 asks for map onto these fields:

      1-3  meanChroma / p95Chroma / p995Chroma   (distances taken later)
      4    chromaAtGradients
      5    chromaAwayFromGradients
      6    falseColourAreaFraction  (connected components, small blobs dropped)
      7    falseColourDistanceFromFeaturesPx
    """
    blocks = card_blocks(img, rects)
    if not blocks:
        raise Unreadable("grayscale_v2: no card rects")
    pooled, at_feat, away_feat = [], [], []
    fc_area, fc_dist, fc_blobs = [], [], []
    for blk in blocks:
        if blk.shape[0] < 3 or blk.shape[1] < 3:
            continue
        c = chroma(blk)
        pooled.append(c.ravel())
        feat = feature_mask(blk)
        if feat.any():
            at_feat.append(float(c[feat].mean()))
        if (~feat).any():
            away_feat.append(float(c[~feat].mean()))

        # False colour: coloured AND away from any luminance feature. Colour
        # that sits ON an encoded edge is allowed by §四 when the Target
        # carries it, and the Target does -- 4:2:0 subsampling puts chroma on
        # every sharp step. Colour BETWEEN features has no such excuse.
        false_px = (c > FALSE_COLOUR_CHROMA) & (~feat)
        labels, n = ndimage.label(false_px)
        area = blk.shape[0] * blk.shape[1]
        keep = np.zeros_like(false_px)
        blobs = 0
        if n:
            sizes = ndimage.sum_labels(false_px, labels, range(1, n + 1))
            for i, s in enumerate(sizes, start=1):
                if s / area >= FALSE_COLOUR_MIN_BLOB_FRACTION:
                    keep |= labels == i
                    blobs += 1
        fc_area.append(float(keep.sum()) / area)
        fc_blobs.append(blobs)
        if keep.any() and feat.any():
            # How far the false colour sits from the nearest real feature. A
            # fringe hugs an edge; a cast floats.
            dist = ndimage.distance_transform_edt(~feat)
            fc_dist.append(float(dist[keep].mean()))
        elif keep.any():
            fc_dist.append(None)

    if not pooled:
        raise Unreadable("grayscale_v2: every card rect was degenerate in size")
    allc = np.concatenate(pooled)
    dists = [d for d in fc_dist if d is not None]
    return {
        "meanChroma": round(float(allc.mean()), 4),
        "p95Chroma": round(float(np.percentile(allc, 95)), 3),
        "p995Chroma": round(float(np.percentile(allc, 99.5)), 3),
        "maxChroma": round(float(allc.max()), 2),
        "chromaAtGradients": (round(float(np.mean(at_feat)), 4)
                              if at_feat else None),
        "chromaAwayFromGradients": (round(float(np.mean(away_feat)), 4)
                                    if away_feat else None),
        "falseColourAreaFraction": round(float(np.mean(fc_area)), 6),
        "falseColourBlobs": int(np.sum(fc_blobs)),
        "falseColourDistanceFromFeaturesPx": (round(float(np.mean(dists)), 3)
                                              if dists else None),
        "cards": len(blocks),
        "thresholds": {"featureGradient": FEATURE_GRADIENT_THRESHOLD,
                       "falseColourChroma": FALSE_COLOUR_CHROMA,
                       "minBlobFraction": FALSE_COLOUR_MIN_BLOB_FRACTION},
    }


GRAYSCALE_DISTANCE_KEYS = ("meanChroma", "p95Chroma", "p995Chroma",
                           "chromaAtGradients", "chromaAwayFromGradients")


def grayscale_distance(lane, target):
    """|lane - target| on each distributional statistic, plus the area terms."""
    out = {}
    for k in GRAYSCALE_DISTANCE_KEYS:
        a, b = lane.get(k), target.get(k)
        out[k] = None if (a is None or b is None) else round(abs(a - b), 4)
    la, ta = lane.get("falseColourAreaFraction"), target.get("falseColourAreaFraction")
    out["falseColourAreaFraction"] = (None if la is None or ta is None
                                      else round(la - ta, 6))
    out["falseColourAreaExcess"] = (None if la is None or ta is None
                                    else round(max(0.0, la - ta), 6))
    return out


# --------------------------------------------------- §五 saturated edge v2

def saturated_edge_v2(img, rects, corner_radius_px):
    """Feature-local colour behaviour on saturated media.

    O5's item 5 asked a question whose answer was 0.0 for every lane on every
    asset, which is not a measurement. This asks instead:

      - is there chroma where the MEDIA has texture?      (expected: yes)
      - is there chroma where it does not?                (expected: little)
      - how localised is it?                              (a ratio)
      - is there a BROAD coloured band inside the rim?    (the actual defect)

    The rim band is the Target's own bevelWidth fraction of the card, so
    "broad coloured rim" is asked of exactly the region a rim occupies.

    UNREADABLE when either population is empty -- an asset with no features, or
    a card with no non-feature area, cannot answer this and must say so rather
    than return a zero.
    """
    a = rgb(img)
    at_feat, away_feat, rim_broad, rim_frac, fringe_local = [], [], [], [], []
    n_feat_px, n_away_px = 0, 0
    for (x0, y0, x1, y1) in rects:
        blk = a[y0:y1, x0:x1]
        if blk.shape[0] < 8 or blk.shape[1] < 8:
            continue
        c = chroma(blk)
        feat = feature_mask_chromatic(blk)
        n_feat_px += int(feat.sum())
        n_away_px += int((~feat).sum())
        if feat.any():
            at_feat.append(float(c[feat].mean()))
        if (~feat).any():
            away_feat.append(float(c[~feat].mean()))
        cw = x1 - x0
        r = (corner_radius_px if corner_radius_px is not None
             else 0.163 * cw)
        _, band = rim_distance(blk.shape[:2], r, RIM_BAND_FRACTION * cw)
        if band.any():
            broad = band & (~feat) & (c > BROAD_RIM_CHROMA)
            rim_broad.append(float(broad.sum()))
            rim_frac.append(float(broad.sum()) / float(band.sum()))
    if not at_feat or not away_feat:
        raise Unreadable(
            "saturated_edge_v2: this asset has no feature population "
            f"({n_feat_px} feature px, {n_away_px} non-feature px); the "
            "feature-local question cannot be asked of it")
    at = float(np.mean(at_feat))
    away = float(np.mean(away_feat))
    # Localisation: how much more colour sits on features than off them. A
    # spectral fringe raises this; a broad wash of colour drives it toward 1.
    fringe_local = at / max(away, 1e-3)
    return {
        "featureMask": "per-channel gradient, maximised over R/G/B",
        "chromaAtFeatures": round(at, 4),
        "chromaAwayFromFeatures": round(away, 4),
        "fringeLocalisation": round(fringe_local, 4),
        "broadRimColouredFraction": (round(float(np.mean(rim_frac)), 6)
                                     if rim_frac else None),
        "rimBandFraction": RIM_BAND_FRACTION,
        "featurePixels": n_feat_px, "nonFeaturePixels": n_away_px,
        "thresholds": {"featureGradient": FEATURE_GRADIENT_THRESHOLD,
                       "broadRimChroma": BROAD_RIM_CHROMA},
    }


# ------------------------------------------- §六 refraction compression v2

def decode_displacement_view(img, rect, gain=DISPLACEMENT_GAIN):
    """Card-UV displacement per pixel, out of the refraction-displacement view.

    The program writes `srgbToLinear(0.5 + d * gain)` so the renderer's own
    linear->sRGB output transform returns the encoded number unchanged. The
    byte IS the encoding; no transfer function is applied here, and applying
    one would be the O5 normal-decode mistake in reverse.

    Pixels at 0 or 255 in either axis are saturated and are excluded rather
    than believed -- outside the card the framebuffer holds background, and a
    background pixel decodes to a large fake displacement.
    """
    a = rgb(img)
    x0, y0, x1, y1 = rect
    blk = a[y0:y1, x0:x1]
    sat = ((blk[..., 0] <= 0) | (blk[..., 0] >= 255)
           | (blk[..., 1] <= 0) | (blk[..., 1] >= 255))
    du = (blk[..., 0] / 255.0 - 0.5) / gain
    dv = (blk[..., 1] / 255.0 - 0.5) / gain
    return du, dv, ~sat


def decode_uv_view(img, rect):
    """Card-media UV per pixel, out of a uv-* view. Same encoding argument."""
    a = rgb(img)
    x0, y0, x1, y1 = rect
    blk = a[y0:y1, x0:x1]
    return blk[..., 0] / 255.0, blk[..., 1] / 255.0


def disc_blobs(img, rect, region=None, area_range=None):
    """Every bright blob inside a card, with its centroid and area.

    Thresholds between the card's OWN 2nd and 98th luminance percentiles rather
    than at a fixed level, so a body that darkens the whole card does not lose
    its landmarks and a body that brightens it does not gain spurious ones.
    Centroids are luminance-weighted, which is what gives sub-pixel position on
    a disc that refraction has smeared.

    `region` restricts the search to a fraction of the card as
    (x0, y0, x1, y1) in card-normalised units. The scored landmark set lives in
    the card's upper half because the TARGET draws its own headline type across
    the lower half and has no QA surface to switch it off -- a white glyph is
    not distinguishable from a white disc by luminance alone, and pretending
    otherwise would put the label layer into an optical measurement.
    """
    a = rgb(img)
    x0, y0, x1, y1 = rect
    blk = a[y0:y1, x0:x1]
    if blk.shape[0] < 16 or blk.shape[1] < 16:
        raise Unreadable("disc_blobs: card rect too small")
    p = lum(blk)
    p_lo, p_hi = float(np.percentile(p, 2)), float(np.percentile(p, 98))
    if p_hi - p_lo < 12.0:
        raise Unreadable(
            f"disc_blobs: card has no usable contrast (p2 {p_lo:.1f}, "
            f"p98 {p_hi:.1f}); the calibration discs are not resolvable here")
    thresh = p_lo + (p_hi - p_lo) * LANDMARK_LEVEL_FRACTION
    mask = p >= thresh
    if region is not None:
        keep = np.zeros_like(mask)
        h, w = mask.shape
        rx0, ry0, rx1, ry1 = region
        keep[int(ry0 * h):int(ry1 * h), int(rx0 * w):int(rx1 * w)] = True
        mask = mask & keep
    labels, n = ndimage.label(mask)
    area = blk.shape[0] * blk.shape[1]
    lo = (area_range[0] if area_range else LANDMARK_MIN_AREA_FRACTION * area)
    hi = (area_range[1] if area_range else LANDMARK_MAX_AREA_FRACTION * area)
    ys, xs = np.mgrid[0:blk.shape[0], 0:blk.shape[1]]
    out = []
    for i in range(1, n + 1):
        sel = labels == i
        px = int(sel.sum())
        if px < lo or px > hi:
            continue
        # UNWEIGHTED centroid of the thresholded blob. A luminance-weighted
        # one would pull toward whichever side of the disc the body happens to
        # brighten, and the prediction it is compared against is the uniform
        # centroid of the disc's fragment set -- the two have to mean the same
        # thing. Sub-pixel precision comes from averaging hundreds of pixels,
        # not from the weights.
        out.append({"x": float(xs[sel].mean()) + 0.5,
                    "y": float(ys[sel].mean()) + 0.5,
                    "areaPx": px,
                    "areaFraction": round(px / area, 6)})
    return out


def disc_centroids(img, rect, ground_level=None, disc_level=None,
                   region=None, area_range=None):
    """Backwards-compatible name: every detectable blob, unguided.

    Kept because the unit tests exercise the unguided path -- an instrument
    whose only entry point needs a prediction cannot be tested against a
    fixture that has no prediction.
    """
    return disc_blobs(img, rect, region=region, area_range=area_range)


def match_predicted_discs(blobs, predicted, max_px=None):
    """Pair each PREDICTED landmark with the nearest acceptable blob.

    Prediction-guided rather than detect-then-sort: the render contains bright
    things that are not landmarks -- the reflection band, the white rim, the
    Target's own type -- and a global sort would rank them alongside the discs.
    Searching a bounded neighbourhood of a position the replay computed from
    GEOMETRY (never from the pixels being judged) keeps the instrument looking
    only where a landmark can be.

    A prediction with no acceptable blob in range is left unmatched, and an
    unmatched prediction invalidates the mean rather than being dropped.
    """
    max_px = LANDMARK_MAX_PAIR_PX if max_px is None else max_px
    rows, used = [], set()
    for q in predicted:
        best, best_d = None, None
        for i, b in enumerate(blobs):
            if i in used:
                continue
            d = float(np.hypot(b["x"] - q["x"], b["y"] - q["y"]))
            if d <= max_px and (best_d is None or d < best_d):
                best, best_d = i, d
        if best is None:
            rows.append({"id": q.get("id"), "matched": False,
                         "predicted": [round(q["x"], 3), round(q["y"], 3)]})
            continue
        used.add(best)
        b = blobs[best]
        rows.append({"id": q.get("id"), "matched": True,
                     "predicted": [round(q["x"], 3), round(q["y"], 3)],
                     "measured": [round(b["x"], 3), round(b["y"], 3)],
                     "dxPx": round(b["x"] - q["x"], 3),
                     "dyPx": round(b["y"] - q["y"], 3),
                     "distancePx": round(best_d, 3),
                     "areaPx": b["areaPx"]})
    matched = [r for r in rows if r["matched"]]
    return {"rows": rows, "matched": len(matched), "expected": len(predicted),
            "usable": len(matched) >= LANDMARK_MIN_MATCHES,
            "meanDistancePx": (round(float(np.mean(
                [r["distancePx"] for r in matched])), 3) if matched else None)}


def pair_centroids(measured, predicted, max_px=LANDMARK_MAX_PAIR_PX):
    """Nearest one-to-one pairing with a hard radius, O5's discipline.

    Positional pairing is what makes a landmark instrument dangerous: one
    missing landmark shifts every pair and the mean comes out large and
    confident, or cancels to a perfect zero. Anything that cannot be paired
    cleanly invalidates the reading.
    """
    rows, used = [], set()
    for j, q in enumerate(predicted):
        best, best_d = None, None
        for i, m in enumerate(measured):
            if i in used:
                continue
            d = float(np.hypot(m["x"] - q["x"], m["y"] - q["y"]))
            if best_d is None or d < best_d:
                best, best_d = i, d
        if best is None or best_d > max_px:
            continue
        used.add(best)
        m = measured[best]
        rows.append({"index": j,
                     "predicted": [round(q["x"], 3), round(q["y"], 3)],
                     "measured": [round(m["x"], 3), round(m["y"], 3)],
                     "dxPx": round(m["x"] - q["x"], 3),
                     "dyPx": round(m["y"] - q["y"], 3),
                     "distancePx": round(best_d, 3),
                     "areaFraction": m["areaFraction"]})
    clean = len(rows) == len(predicted) and len(predicted) > 0
    return {"pairs": rows, "matched": len(rows), "expected": len(predicted),
            "cleanlyPaired": clean,
            "meanDisplacementPx": (
                round(float(np.mean([r["distancePx"] for r in rows])), 3)
                if clean else None),
            "meanDxPx": (round(float(np.mean([r["dxPx"] for r in rows])), 3)
                         if clean else None),
            "meanDyPx": (round(float(np.mean([r["dyPx"] for r in rows])), 3)
                         if clean else None)}


# ---------------------------------------------------- §七 interior fidelity

def interior_stats(img, rects, inset_fraction=0.225, tile=TILE_PX):
    """Interior luminance, chroma, HF energy, local contrast and tile maps.

    The inset is O4's sealed one, carried so the HF number means the same thing
    across three rounds: the card's outer ring carries the reflection band and
    the silhouette, whose gradients dwarf the media's own texture.
    """
    a = rgb(img)
    lumas, chromas, hfs, contrasts = [], [], [], []
    hf_tiles, chroma_tiles = [], []
    for (x0, y0, x1, y1) in rects:
        cw, ch = x1 - x0, y1 - y0
        ix, iy = int(cw * inset_fraction), int(ch * inset_fraction)
        blk = a[y0 + iy:y1 - iy, x0 + ix:x1 - ix]
        if blk.shape[0] < 5 or blk.shape[1] < 5:
            continue
        p = lum(blk)
        lap = np.abs(4 * p[1:-1, 1:-1] - p[:-2, 1:-1] - p[2:, 1:-1]
                     - p[1:-1, :-2] - p[1:-1, 2:])
        lumas.append(float(p.mean()))
        chromas.append(float(chroma(blk).mean()))
        hfs.append(float(lap.mean()))
        contrasts.append(float(p.std()))
        full = np.zeros_like(p)
        full[1:-1, 1:-1] = lap
        ht, ct = _tiles(full, tile), _tiles(chroma(blk), tile)
        if ht is not None and ct is not None:
            hf_tiles.append(ht.ravel())
            chroma_tiles.append(ct.ravel())
    if not lumas:
        raise Unreadable("interior_stats: no usable card interior")
    return {
        "interiorLuma": round(float(np.mean(lumas)), 3),
        "interiorChroma": round(float(np.mean(chromas)), 3),
        "hfEnergy": round(float(np.mean(hfs)), 4),
        "localContrast": round(float(np.mean(contrasts)), 4),
        "hfTiles": ([round(float(v), 4) for v in np.concatenate(hf_tiles)]
                    if hf_tiles else []),
        "chromaTiles": ([round(float(v), 4) for v in np.concatenate(chroma_tiles)]
                        if chroma_tiles else []),
        "cards": len(lumas), "insetFraction": inset_fraction, "tilePx": tile,
    }


def _tiles(plane, tile):
    h, w = plane.shape
    th, tw = h // tile, w // tile
    if th < 2 or tw < 2:
        return None
    return plane[:th * tile, :tw * tile].reshape(th, tile, tw, tile) \
                                        .mean(axis=(1, 3))


def correlate(a_list, b_list):
    a, b = np.asarray(a_list, float), np.asarray(b_list, float)
    n = min(len(a), len(b))
    if n < 4:
        return {"r": None, "n": n, "note": "too few tiles to correlate"}
    a, b = a[:n], b[:n]
    if a.std() < 1e-9 or b.std() < 1e-9:
        return {"r": None, "n": n, "note": "a series is constant"}
    return {"r": round(float(np.corrcoef(a, b)[0, 1]), 4), "n": n}


def sharpness_applicable(target_hf):
    """§七: flat assets are NOT_APPLICABLE, they are not passes or failures."""
    if target_hf is None:
        return False, "no Target reading"
    if target_hf < HF_SIGNAL_FLOOR:
        return False, (f"Target interior HF energy {target_hf} is below the "
                       f"pre-registered signal floor {HF_SIGNAL_FLOOR}; this "
                       f"asset has no interior structure to measure and a "
                       f"difference here would be noise")
    return True, None


# ------------------------------------------------------- §八 silhouette v2

def rendered_alpha_mask(img, rect, background_rgb=None, pad=6,
                        delta=SILHOUETTE_LIT_DELTA):
    """Where a render actually put light, inside a card's screen rect.

    The background is sampled from a ring OUTSIDE the rect, never from a
    corner: the corner lies outside the rounded-rect silhouette but inside the
    rect, so a card that wrongly lights its corners would otherwise have that
    lit corner taken as the background and the defect would vanish.
    """
    a = rgb(img)
    x0, y0, x1, y1 = rect
    h, w = a.shape[:2]
    if background_rgb is None:
        ring = []
        if y0 - pad >= 0:
            ring.append(a[max(0, y0 - pad):y0, x0:x1].reshape(-1, 3))
        if y1 + pad <= h:
            ring.append(a[y1:y1 + pad, x0:x1].reshape(-1, 3))
        if x0 - pad >= 0:
            ring.append(a[y0:y1, max(0, x0 - pad):x0].reshape(-1, 3))
        if x1 + pad <= w:
            ring.append(a[y0:y1, x1:x1 + pad].reshape(-1, 3))
        if not ring:
            raise Unreadable(
                "rendered_alpha_mask: the card rect touches every frame edge, "
                "so no background can be sampled")
        background_rgb = np.concatenate(ring).mean(axis=0)
    blk = a[y0:y1, x0:x1]
    d = np.abs(blk - np.asarray(background_rgb, np.float32)).max(axis=2)
    return d > delta, d


def projected_alpha_mask(sdf_mask_img, rect, level=0.5):
    """The candidate's OWN projected silhouette, out of the sdf-mask program.

    This is the repair §八 asks for. The sdf-mask view renders
    smoothstep(0, -1, sdf) through the REAL PlaneGeometry projection and the
    REAL card matrix, so its coverage is the projected rounded rect including
    the dome and the perspective -- not an axis-aligned rectangle fitted to a
    bounding box whose corners can sit 109 px from the actual quad.
    """
    a = rgb(sdf_mask_img)
    x0, y0, x1, y1 = rect
    v = lum(a[y0:y1, x0:x1]) / 255.0
    return v >= level, v


def silhouette_compare(rendered, projected):
    """Agreement between where light is and where the silhouette says it is."""
    if rendered.shape != projected.shape:
        raise Unreadable("silhouette_compare: mask shapes differ")
    inter = int((rendered & projected).sum())
    union = int((rendered | projected).sum())
    outside = int((rendered & ~projected).sum())
    missing = int((~rendered & projected).sum())
    return {
        "renderedPixels": int(rendered.sum()),
        "projectedPixels": int(projected.sum()),
        "intersection": inter,
        "iou": round(inter / union, 6) if union else None,
        "litBeyondSilhouette": outside,
        "litBeyondFraction": (round(outside / int(projected.sum()), 6)
                              if projected.any() else None),
        "unlitInsideSilhouette": missing,
    }


def edge_width_px(value_map, mask, axis=1):
    """Antialias width of a coverage edge, in px, from a soft coverage map.

    Measured as the mean number of pixels per scanline whose coverage sits
    strictly between 0.05 and 0.95 on a transition. A hard edge gives ~1; a
    wide feathered edge gives more. Rows with no transition are skipped rather
    than counted as zero.
    """
    soft = (value_map > 0.05) & (value_map < 0.95)
    counts = []
    for i in range(soft.shape[0] if axis == 1 else soft.shape[1]):
        line = soft[i] if axis == 1 else soft[:, i]
        m = mask[i] if axis == 1 else mask[:, i]
        if not m.any():
            continue
        n = int(line.sum())
        if n == 0:
            continue
        counts.append(n / 2.0)   # two edges per scanline through a card
    if not counts:
        return None
    return round(float(np.mean(counts)), 3)


def measured_corner_radius_px(mask):
    """Corner radius implied by a coverage mask, in px.

    Taken from the top-left corner: the distance along the diagonal from the
    rect corner to the first covered pixel. For a rounded rect the corner arc
    is centred at (r, r), so the diagonal point (t, t) is covered exactly when
    sqrt(2) * (r - t) <= r, i.e. from t = r * (1 - 1/sqrt(2)) onward. Hence
    r = t / (1 - 1/sqrt(2)). Robust enough to distinguish a square card (r = 0)
    from a rounded one, which is the negative control §八 requires.
    """
    if not mask.any():
        return None
    h, w = mask.shape
    n = min(h, w) // 2
    for k in range(n):
        if mask[k, k]:
            return round(k / (1.0 - 1.0 / np.sqrt(2)), 3)
    return None


# The predicted footprint is dilated by this many pixels before the measured
# centroid is taken inside it. Enough to absorb the antialiasing and the
# replay's own sub-pixel error; far short of the distance to any other disc.
DISC_WINDOW_MARGIN_PX = 10.0
# The measured bright area inside a window must be within this factor of the
# PREDICTED SCREEN AREA of the disc's image, or the window did not catch the
# disc: too large means it also caught a glyph, the rim or a neighbour; too
# small means part of the image is missing -- occluded by the Target's own type
# or cut off by the frame -- and the centroid of what remains is not the
# centroid of the disc.
DISC_AREA_RATIO_RANGE = (0.6, 1.6)


def measure_discs_in_windows(img, predictions, rect=None, level_fraction=None):
    """Measured centroid of each predicted disc image, inside its own window.

    Prediction-guided and footprint-based. The threshold is taken from the
    CARD, not from the window, so a window that happens to sit on a dark part
    of the body does not get its own private definition of bright.

    Returns one row per prediction. A row that could not be measured says so
    and carries no centroid -- there is no fallback that guesses.
    """
    a = rgb(img)
    p_full = lum(a)
    if rect is not None:
        x0, y0, x1, y1 = rect
        card = p_full[y0:y1, x0:x1]
    else:
        card = p_full
    p_lo, p_hi = float(np.percentile(card, 2)), float(np.percentile(card, 98))
    if p_hi - p_lo < 12.0:
        raise Unreadable(
            f"measure_discs_in_windows: card has no usable contrast "
            f"(p2 {p_lo:.1f}, p98 {p_hi:.1f})")
    frac = LANDMARK_LEVEL_FRACTION if level_fraction is None else level_fraction
    thresh = p_lo + (p_hi - p_lo) * frac

    # Windows must not overlap, or two discs would share pixels and both
    # centroids would be pulled toward the shared region.
    boxes = []
    for q in predictions:
        if q.get("x") is None or not q.get("bbox"):
            boxes.append(None)
            continue
        bx0, by0, bx1, by1 = q["bbox"]
        boxes.append((bx0 - DISC_WINDOW_MARGIN_PX, by0 - DISC_WINDOW_MARGIN_PX,
                      bx1 + DISC_WINDOW_MARGIN_PX, by1 + DISC_WINDOW_MARGIN_PX))
    rows = []
    H, W = p_full.shape
    for i, (q, box) in enumerate(zip(predictions, boxes)):
        row = {"id": q.get("id"), "measured": False}
        if box is None:
            row["why"] = "no prediction (the disc is outside this card's crop)"
            rows.append(row)
            continue
        overlap = [j for j, other in enumerate(boxes)
                   if other is not None and j != i
                   and not (other[2] < box[0] or other[0] > box[2]
                            or other[3] < box[1] or other[1] > box[3])]
        if overlap:
            row["why"] = f"window overlaps disc(s) {overlap}"
            rows.append(row)
            continue
        wx0, wy0 = int(max(0, np.floor(box[0]))), int(max(0, np.floor(box[1])))
        wx1, wy1 = int(min(W, np.ceil(box[2]) + 1)), int(min(H, np.ceil(box[3]) + 1))
        if wx1 - wx0 < 3 or wy1 - wy0 < 3:
            row["why"] = "window clipped to nothing by the frame edge"
            rows.append(row)
            continue
        win = p_full[wy0:wy1, wx0:wx1]
        sel = win >= thresh
        k = int(sel.sum())
        lo, hi = DISC_AREA_RATIO_RANGE
        pred_px = q.get("predictedAreaPx", q["fragments"])
        if k < 8 or k < lo * pred_px or k > hi * pred_px:
            row["why"] = (f"measured area {k} px is outside "
                          f"[{lo}, {hi}] x the predicted {pred_px:.0f} px")
            row["areaPx"] = k
            row["predictedAreaPx"] = round(pred_px, 1)
            rows.append(row)
            continue
        ys, xs = np.mgrid[wy0:wy1, wx0:wx1]
        mx, my = float(xs[sel].mean()) + 0.5, float(ys[sel].mean()) + 0.5
        row.update({
            "measured": True,
            "x": round(mx, 3), "y": round(my, 3),
            "predicted": [round(q["x"], 3), round(q["y"], 3)],
            "residualPx": round(float(np.hypot(mx - q["x"], my - q["y"])), 3),
            "areaPx": k, "predictedAreaPx": round(pred_px, 1),
            "areaRatio": round(k / max(pred_px, 1.0), 3),
        })
        rows.append(row)
    ok = [r for r in rows if r["measured"]]
    return {
        "rows": rows, "measured": len(ok), "expected": len(predictions),
        "usable": len(ok) >= LANDMARK_MIN_MATCHES,
        "meanResidualPx": (round(float(np.mean([r["residualPx"] for r in ok])), 3)
                           if ok else None),
        "maxResidualPx": (round(float(max(r["residualPx"] for r in ok)), 3)
                          if ok else None),
        "thresholdLuma": round(thresh, 2),
    }


def displacement_from_predictions(measured_rows, unrefracted):
    """Per-disc displacement: measured position minus the UNREFRACTED one.

    The unrefracted prediction is pure geometry -- projection and cover, no
    refraction at all -- so this is "how far refraction moved this landmark",
    measured identically for every lane and never derived from the lane being
    judged.
    """
    by_id = {u["id"]: u for u in unrefracted}
    rows, mags = [], []
    for r in measured_rows:
        if not r.get("measured"):
            continue
        u = by_id.get(r["id"])
        if not u or u.get("x") is None:
            continue
        dx, dy = r["x"] - u["x"], r["y"] - u["y"]
        mag = float(np.hypot(dx, dy))
        mags.append(mag)
        rows.append({"id": r["id"], "dxPx": round(dx, 3), "dyPx": round(dy, 3),
                     "magnitudePx": round(mag, 3)})
    return {"perDisc": rows,
            "meanMagnitudePx": (round(float(np.mean(mags)), 3) if mags else None),
            "discs": len(rows)}
