#!/usr/bin/env python3
"""O3 instrument corrections (§七), written BEFORE any candidate exists.

O2 scored three checks whose registered coding fired on an instrument
degeneracy rather than on the optics, and each was adjudicated after the
pixels were in hand. That is allowed once, with both codings recorded; it
is not allowed twice. So the three measurands are re-specified here, in
one module that the O3 gate and the O3 instrument unit tests both import,
and this module is committed in the source / pre-registration commit --
before the candidate code, let alone the candidate pixels.

  F5  interior      branch on the BASELINE, not after the fact:
                    baseline > 0.01 -> relative change; baseline <= 0.01
                    -> absolute change. Fixed here forever.
  F10 gutter        mask every PROJECTED CARD POLYGON, not just the
                    fully-visible twins and not an axis-aligned box; a
                    partially-visible neighbour card is a card, never
                    gutter.
  F11 pointer path  measure the GLASS REFLECTION only. The label /
                    typography ink is excluded from the start, by
                    construction rather than by a band fraction, and the
                    published record carries the path the verdict was
                    computed from -- one coding, one number.

Nothing in this module may be edited after the O3 candidate is captured.
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------- F5 -----

#: Relative-change ceiling. Unchanged from the O2 registered value.
F5_RELATIVE_CEILING = 0.12
#: Baseline below which the relative coding is degenerate and the absolute
#: coding is used instead. A mean saturation of 0.01 is a 2.55/255 chroma
#: on an 8-bit render -- at or under the render's own quantisation floor.
F5_BASELINE_FLOOR = 0.01
#: Absolute ceilings, used when the baseline is at or under the floor.
#: Set to admit the ALREADY-ACCEPTED O2 baseline (its worst achromatic
#: interior gain was 0.0104 saturation / 0.14 of 255 chroma) with headroom,
#: NOT to admit some future O3 number: O3 must not brighten or desaturate
#: the interior at all, so any O3 value materially above the accepted O2
#: one is a real regression and this ceiling catches it.
F5_ABSOLUTE_SATURATION_CEILING = 0.02
F5_ABSOLUTE_CHROMA_CEILING = 2.0


def f5_interior_change(before: dict, candidate: dict) -> dict:
    """Interior-unchanged check for ONE asset.

    `before` / `candidate` are o2_optics_stats.interior_stats dicts. The
    coding is chosen by the BASELINE alone, so it is decided by the
    control render and cannot be selected after seeing the candidate.
    """
    b_sat = before["interiorSaturationMean"]
    b_lum = before["interiorLuminanceMean"]
    c_sat = candidate["interiorSaturationMean"]
    c_lum = candidate["interiorLuminanceMean"]
    d_sat = c_sat - b_sat
    d_chroma = candidate["interiorChromaMean"] - before["interiorChromaMean"]

    # Luminance always has a usable baseline on scored media, so it is
    # always relative.
    rel_lum = abs(c_lum - b_lum) / max(b_lum, 1e-6)
    lum_fired = rel_lum > F5_RELATIVE_CEILING

    if b_sat > F5_BASELINE_FLOOR:
        coding = "relative"
        rel_sat = abs(d_sat) / b_sat
        sat_fired = rel_sat > F5_RELATIVE_CEILING
        measure = {"relSaturationChange": round(rel_sat, 4)}
        ceiling = F5_RELATIVE_CEILING
    else:
        coding = "absolute"
        sat_fired = (abs(d_sat) > F5_ABSOLUTE_SATURATION_CEILING
                     or abs(d_chroma) > F5_ABSOLUTE_CHROMA_CEILING)
        measure = {"absSaturationDelta": round(d_sat, 4),
                   "absChromaDelta": round(d_chroma, 2)}
        ceiling = [F5_ABSOLUTE_SATURATION_CEILING, F5_ABSOLUTE_CHROMA_CEILING]

    return {
        "coding": coding,
        "codingChosenBy": f"baseline interior saturation {b_sat:.4f} "
                          f"{'>' if b_sat > F5_BASELINE_FLOOR else '<='} "
                          f"{F5_BASELINE_FLOOR}",
        "baselineSaturation": b_sat,
        "ceiling": ceiling,
        **measure,
        "relLuminanceChange": round(rel_lum, 4),
        "absLuminanceDelta": round(c_lum - b_lum, 2),
        "fired": bool(sat_fired or lum_fired),
    }


# --------------------------------------------------------------- F10 -----

#: Dilation applied to every card polygon before it is subtracted, as a
#: FRACTION OF THE INTER-CARD GAP. A fixed pixel count would mean
#: different things at different viewports; a third of the gap leaves the
#: middle third of the gap as the measured strip at every scale.
#:
#: Why a third and not zero: the polygon is the card's flat PLANE quad,
#: while the rendered card is a slab with thickness and carries a CSS3D
#: label plane that sits closer to the camera and therefore projects
#: slightly larger. Both paint a few pixels outside the plane quad. The
#: dry run on the O2 captures measured ~90% of all "gutter" ink within
#: 4-8 px of a polygon, and no gutter at all survives a 12 px dilation
#: because the cards nearly tile the frame (gap = 4.5% of the card width,
#: ~24.6 px at 1440x900). So this instrument measures a NARROW strip, and
#: its absolute value is not meaningful -- only the candidate-vs-control
#: delta is, which is how the gate reads it.
F10_GAP_FRACTION = 0.33
F10_MIN_DILATION_PX = 3
#: Luma above which a gutter pixel counts as ink.
F10_INK_LUMA = 80.0


def f10_dilation_for(plane_width, gap_ratio=0.045):
    """The pinned dilation for one viewport, in px."""
    return max(F10_MIN_DILATION_PX,
               int(round(F10_GAP_FRACTION * gap_ratio * plane_width)))


def _polygon_mask(quad, w, h, dilation):
    """Boolean mask of one projected card quad, dilated by `dilation` px.

    Even-odd fill against the quad's four edges -- the card's true
    projected footprint, not its bounding box. A rotated card on the
    sphere has a bounding box substantially larger than itself, and using
    the box would silently mask real gutter.
    """
    pts = [(float(x), float(y)) for x, y in quad]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0 = max(0, int(np.floor(min(xs))) - dilation - 1)
    x1 = min(w, int(np.ceil(max(xs))) + dilation + 1)
    y0 = max(0, int(np.floor(min(ys))) - dilation - 1)
    y1 = min(h, int(np.ceil(max(ys))) + dilation + 1)
    mask = np.zeros((h, w), bool)
    if x1 <= x0 or y1 <= y0:
        return mask
    yy, xx = np.mgrid[y0:y1, x0:x1]
    inside = np.zeros(xx.shape, bool)
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        cond = ((ay > yy) != (by > yy))
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (bx - ax) * (yy - ay) / np.where(by - ay == 0, np.nan, by - ay) + ax
        hit = cond & (xx < xint)
        inside ^= np.nan_to_num(hit, nan=False).astype(bool)
    if dilation > 0:
        # Chebyshev dilation: a pixel within `dilation` of the polygon.
        d = dilation
        grown = inside.copy()
        for dy in range(-d, d + 1):
            for dx in range(-d, d + 1):
                if dx == 0 and dy == 0:
                    continue
                grown |= np.roll(np.roll(inside, dy, axis=0), dx, axis=1)
        inside = grown
    mask[y0:y1, x0:x1] = inside
    return mask


def f10_gutter_ink(img, verdicts, dilation=F10_MIN_DILATION_PX):
    """Ink ratio in the STRICT between-card region.

    `verdicts` is the frame_verdicts dict. EVERY drawn card contributes
    its polygon, whether it is fully visible, clipped by the viewport or
    only partly on screen: a partially-visible neighbour card is a card.
    What is left is gutter, and only that is measured.
    """
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w = a.shape[:2]
    card = np.zeros((h, w), bool)
    counted = 0
    for v in verdicts.values():
        if not v.get("draw") or not v.get("quad") or not all(v["quad"]):
            continue
        card |= _polygon_mask(v["quad"], w, h, dilation)
        counted += 1
    g = a[~card]
    if len(g) == 0:
        return {"gutterInkRatio": None, "cardsMasked": counted,
                "gutterPixels": 0}
    gl = 0.2126 * g[:, 0] + 0.7152 * g[:, 1] + 0.0722 * g[:, 2]
    return {"gutterInkRatio": round(float((gl > F10_INK_LUMA).sum() / len(gl)), 5),
            "cardsMasked": counted,
            "gutterPixels": int(len(g))}


# --------------------------------------------------------------- F11 -----

F11_LUMA_MIN = 200.0
F11_CHROMA_MAX = 40.0
#: Minimum glass-reflection pixels for a state to be judged. Below this the
#: check FIRES: an empty mask is a failure to demonstrate a stable path,
#: never a pass by default.
F11_MIN_PIXELS = 50
#: Maximum adjacent jump in card widths. Unchanged from the O2 registered
#: value.
F11_MAX_ADJACENT_JUMP = 0.4
#: Below this Target path range (max - min, in card widths) the Target's
#: own reflection centroid does not track the pointer materially, so a
#: direction test on it would be measuring the reference's noise.
#:
#: The dry run on the O2 captures measured the Target's glass-only path
#: range at 0.027 card widths -- and NON-MONOTONIC. Requiring a candidate
#: to be monotonic in a direction the reference does not actually have
#: would fail the round on the instrument. So the branch is taken on the
#: TARGET's range, exactly as F5 branches on the baseline: the reference
#: decides the coding, never the candidate.
F11_FLAT_TARGET_RANGE = 0.05
#: In the flat branch the candidate may not introduce a swing the Target
#: does not have. Calibrated so the ALREADY-ACCEPTED O2 candidate passes
#: (its dry-run range was 0.044) with headroom, and so a gross swing does
#: not.
F11_FLAT_RANGE_ALLOWANCE = 0.05
F11_FLAT_RANGE_FLOOR = 0.10
#: Dilation on the static-ink exclusion, in px.
F11_INK_DILATION_PX = 2


def _qualifying(img, rect):
    x0, y0, x1, y1 = rect
    a = np.asarray(img.convert("RGB"), dtype=np.float32)[y0:y1, x0:x1]
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    chroma = a.max(axis=2) - a.min(axis=2)
    return (lum > F11_LUMA_MIN) & (chroma < F11_CHROMA_MAX)


def glass_reflection_masks(states_by_name):
    """Per-state GLASS reflection masks, label / typography excluded.

    `states_by_name` maps a state name to `(image, rect)` -- the rect of
    the SAME card AT THAT STATE. The card moves between pointer states
    (pointer parallax moves the camera, so the projected card shifts),
    and the label ink is fixed in CARD space, not screen space. Comparing
    states at one shared screen rect would misalign the ink by several
    pixels, leave the intersection near-empty, and let the label survive
    into the "glass" population -- silently reproducing the very problem
    this instrument exists to fix.

    So every state is cropped at its OWN rect and the comparison happens
    in card space, on a common raster anchored at the card's top-left
    corner. The bright low-chroma pixels present in EVERY scored state
    are ink and are removed (dilated, to absorb antialiasing and the
    sub-pixel scale difference between states). What survives is the
    population that responds to the pointer.

    Returns (masks_by_state, excluded_mask, cardSpaceDims).
    """
    quals = {s: _qualifying(img, rect) for s, (img, rect) in
             states_by_name.items()}
    if not quals:
        return {}, None, None
    h = min(q.shape[0] for q in quals.values())
    w = min(q.shape[1] for q in quals.values())
    if h <= 0 or w <= 0:
        return {}, None, None
    quals = {s: q[:h, :w] for s, q in quals.items()}
    static = None
    for q in quals.values():
        static = q.copy() if static is None else (static & q)
    d = F11_INK_DILATION_PX
    grown = static.copy()
    for dy in range(-d, d + 1):
        for dx in range(-d, d + 1):
            if dx or dy:
                grown |= np.roll(np.roll(static, dy, axis=0), dx, axis=1)
    return {s: q & ~grown for s, q in quals.items()}, grown, (h, w)


def centroid_of(mask, dims):
    """Centroid of a card-space mask, normalised to the card raster."""
    if mask is None or dims is None:
        return None
    h, w = dims
    ys, xs = np.nonzero(mask)
    if len(xs) < F11_MIN_PIXELS:
        return None
    return {"nx": round(float(xs.mean()) / max(w, 1), 4),
            "ny": round(float(ys.mean()) / max(h, 1), 4),
            "pixels": int(len(xs))}


def f11_judge(target_path, candidate_path):
    """The ONE F11 verdict.

    `*_path` are the three nx values at (pointer-left, rest, pointer-right)
    -- None where the state could not be measured. The candidate must move
    monotonically in the Target's own direction with no adjacent jump over
    F11_MAX_ADJACENT_JUMP card widths. An unmeasurable state fires.

    This function is the whole gate: the published record carries exactly
    the path fed to it and exactly the verdict it returned.
    """
    reasons = []
    if any(v is None for v in target_path):
        reasons.append("target path unmeasurable")
    if any(v is None for v in candidate_path):
        reasons.append("candidate path unmeasurable")
    if reasons:
        return {"targetNxPath": list(target_path),
                "candidateNxPath": list(candidate_path),
                "adjacentJumps": None, "targetDirection": None,
                "fired": True, "reasons": reasons}

    tdir = np.sign(target_path[2] - target_path[0])
    steps = [candidate_path[1] - candidate_path[0],
             candidate_path[2] - candidate_path[1]]
    jumps = [abs(s) for s in steps]
    cdir = np.sign(candidate_path[2] - candidate_path[0])
    t_range = max(target_path) - min(target_path)
    c_range = max(candidate_path) - min(candidate_path)

    # An over-large adjacent jump is a pop in either branch.
    if max(jumps) > F11_MAX_ADJACENT_JUMP:
        reasons.append(f"adjacent jump {max(jumps):.4f} > {F11_MAX_ADJACENT_JUMP}")

    if t_range < F11_FLAT_TARGET_RANGE:
        branch = "flat-reference"
        allowance = max(t_range + F11_FLAT_RANGE_ALLOWANCE, F11_FLAT_RANGE_FLOOR)
        if c_range > allowance:
            reasons.append(
                f"target reflection centroid is effectively stationary "
                f"(range {t_range:.4f}) but the candidate swings "
                f"{c_range:.4f} > {allowance:.4f}")
    else:
        branch = "tracking-reference"
        if cdir != tdir:
            reasons.append(
                f"candidate direction {cdir} != target direction {tdir}")
        if not all(np.sign(s) in (tdir, 0) for s in steps):
            reasons.append("candidate path not monotonic in the target direction")

    return {"targetNxPath": list(target_path),
            "candidateNxPath": list(candidate_path),
            "adjacentJumps": [round(j, 4) for j in jumps],
            "targetDirection": int(tdir),
            "targetRange": round(float(t_range), 4),
            "candidateRange": round(float(c_range), 4),
            "branch": branch,
            "branchChosenBy": f"target path range {t_range:.4f} "
                              f"{'<' if t_range < F11_FLAT_TARGET_RANGE else '>='} "
                              f"{F11_FLAT_TARGET_RANGE}",
            "fired": bool(reasons), "reasons": reasons}
