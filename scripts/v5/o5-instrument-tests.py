#!/usr/bin/env python3
"""O5 instrument unit tests.

Every check has a NEGATIVE partner: a synthetic input that must make it fail.
A test suite that only ever feeds instruments correct data proves nothing --
it cannot distinguish an instrument that measures the right thing from one
that returns a plausible constant.

Run before sealing. Output: qa-v5/optics-o5/instrument-tests.json
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


I = _load("o5_test_ins", "o5_instruments.py")

RESULTS = []


def check(name, got, want, note=""):
    ok = bool(got == want) if isinstance(want, bool) else bool(got)
    RESULTS.append({"test": name, "pass": ok, "note": note})
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {note}" if note else ""))
    return ok


def card(w=240, h=180, bg=(10, 10, 10)):
    return np.full((h, w, 3), bg, np.float32)


def as_img(a):
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def framed(inner, pad=30, bg=(6, 6, 6)):
    """Put a card image inside a larger frame; returns (image, rect)."""
    h, w = inner.shape[:2]
    full = np.full((h + 2 * pad, w + 2 * pad, 3), bg, np.float32)
    full[pad:pad + h, pad:pad + w] = inner
    return as_img(full), (pad, pad, pad + w, pad + h)


# ------------------------------------------------------------ landmarks
def t_landmarks():
    a = card()
    a[:, 120:] = 200.0                       # one step at nx = 0.5
    img, rect = framed(a)
    got = I.landmark_positions(img, rect, expected_n=1)
    check("landmark: finds a single step at nx 0.5",
          len(got) == 1 and abs(got[0]["nx"] - 0.5) < 0.01, True,
          f"nx={got[0]['nx'] if got else None}")

    # NEGATIVE: a flat card has no landmark.
    img2, rect2 = framed(card())
    check("landmark NEGATIVE: flat card yields none",
          len(I.landmark_positions(img2, rect2)) == 0, True)

    # NEGATIVE: a step below the contrast floor must not register.
    a3 = card()
    a3[:, 120:] = 10.0 + I.LANDMARK_MIN_CONTRAST * 0.4
    img3, rect3 = framed(a3)
    check("landmark NEGATIVE: sub-threshold step ignored",
          len(I.landmark_positions(img3, rect3)) == 0, True)

    # Three steps, ordered left to right.
    a4 = card()
    a4[:, 60:120] = 200.0
    a4[:, 180:] = 120.0
    img4, rect4 = framed(a4)
    g4 = I.landmark_positions(img4, rect4, expected_n=3)
    check("landmark: three steps returned in x order",
          len(g4) == 3 and all(g4[i]["nx"] < g4[i + 1]["nx"] for i in range(2)),
          True, str([p["nx"] for p in g4]))

    # Sub-pixel: a ramp centred between two pixels.
    a5 = card()
    a5[:, 121:] = 200.0
    a5[:, 120] = 105.0
    img5, rect5 = framed(a5)
    g5 = I.landmark_positions(img5, rect5, expected_n=1)
    check("landmark: sub-pixel centroid lands between samples",
          bool(g5) and 0.500 < g5[0]["nx"] < 0.512, True,
          f"nx={g5[0]['nx'] if g5 else None}")


# ------------------------------------------------------------ flat position
def t_flat_position():
    check("flat: identity cover maps source nx to itself",
          abs(I.flat_landmark_nx(0.375, 1.0, 0.0) - 0.375) < 1e-9, True)
    # 16:9 into 4:3 -> scale .75 offset .125; source .375 -> uv 1/3
    check("flat: 16:9 into 4:3 puts source .375 at card 1/3",
          abs(I.flat_landmark_nx(0.375, 0.75, 0.125) - 1 / 3) < 1e-9, True)
    # NEGATIVE: a landmark cropped away must be None, not clamped.
    check("flat NEGATIVE: cropped-away landmark returns None",
          I.flat_landmark_nx(0.05, 0.75, 0.125) is None, True)
    check("flat NEGATIVE: degenerate scale returns None",
          I.flat_landmark_nx(0.5, 0.0, 0.0) is None, True)


# ------------------------------------------------------------ compression
def t_compression():
    # Media-only: step at nx 0.5. Glass: same step displaced outward by 6 px.
    mo = card()
    mo[:, 120:] = 200.0
    mo_img, rect = framed(mo)
    gl = card()
    gl[:, 126:] = 200.0
    gl_img, _ = framed(gl)
    r = I.edge_compression(gl_img, rect, [0.5], 1.0, 0.0, media_only_img=mo_img)
    check("compression: measures a 6 px displacement",
          abs(r["landmarks"][0]["displacementPx"] - 6.0) < 0.6, True,
          f"got {r['landmarks'][0]['displacementPx']}")
    check("compression: analytic flat baseline verified against media-only",
          r["flatBaselineVerified"] is True, True,
          f"residual {r['flatBaselineResidualPx']} px")

    # Sign: a landmark left of centre moving LEFT is outward (positive).
    gl2 = card()
    gl2[:, 54:] = 200.0                       # flat would be 60 -> moved left
    gl2_img, _ = framed(gl2)
    r2 = I.edge_compression(gl2_img, rect, [0.25], 1.0, 0.0)
    check("compression: outward sign is positive on the left half",
          r2["landmarks"][0]["outwardPx"] > 0, True,
          f"outward {r2['landmarks'][0]['outwardPx']}")

    # NEGATIVE: no displacement reads as zero, not as noise.
    r3 = I.edge_compression(mo_img, rect, [0.5], 1.0, 0.0)
    check("compression NEGATIVE: identical render reads ~0",
          abs(r3["landmarks"][0]["displacementPx"]) < 0.6, True,
          f"got {r3['landmarks'][0]['displacementPx']}")

    # NEGATIVE: a wrong analytic baseline must be caught, not used.
    r4 = I.edge_compression(gl_img, rect, [0.5], 0.5, 0.0, media_only_img=mo_img)
    check("compression NEGATIVE: wrong cover law flags baseline unverified",
          r4["flatBaselineVerified"] is False, True,
          f"residual {r4['flatBaselineResidualPx']} px")


def t_pairing():
    """The guards added after adversarial review found the instrument would
    return a confident number from a mispaired landmark set."""
    mo = card()
    mo[:, 60:120] = 200.0
    mo[:, 180:] = 120.0                      # three steps: .25 .5 .75
    mo_img, rect = framed(mo)
    r_ok = I.edge_compression(mo_img, rect, [0.25, 0.5, 0.75], 1.0, 0.0)
    check("pairing: three landmarks pair cleanly and read ~0",
          r_ok["cleanlyPaired"] and abs(r_ok["meanOutwardPx"]) < 0.6, True,
          f"mean {r_ok['meanOutwardPx']}, matched {r_ok['matched']}")

    # NEGATIVE: only ONE of the three steps is present. Positional pairing
    # would zip it against the first expected landmark and report a large
    # confident displacement; nearest-pairing must refuse to answer.
    one = card()
    one[:, 180:] = 120.0
    one_img, _ = framed(one)
    r_bad = I.edge_compression(one_img, rect, [0.25, 0.5, 0.75], 1.0, 0.0)
    check("pairing NEGATIVE: a missing landmark refuses to produce a mean",
          r_bad["meanOutwardPx"] is None and not r_bad["cleanlyPaired"], True,
          f"matched {r_bad['matched']}/{r_bad['expected']}")
    check("pairing NEGATIVE: an incomplete set is not usable",
          r_bad["usable"] is False, True)

    # NEGATIVE: TWO of three present -- the case that cancels to a perfect
    # zero under positional pairing, which is the most dangerous of all.
    two = card()
    two[:, 60:120] = 200.0
    two_img, _ = framed(two)
    r_two = I.edge_compression(two_img, rect, [0.25, 0.5, 0.75], 1.0, 0.0)
    check("pairing NEGATIVE: two-of-three does not cancel to a false zero",
          r_two["meanOutwardPx"] is None, True,
          f"matched {r_two['matched']}/{r_two['expected']}")

    # NEGATIVE: a baseline wrong by more than the sealed residual limit must
    # NOT be stamped verified. 1.9 px used to pass the old 2.0 threshold while
    # the scored window is only 1.5 -- so a candidate with no refraction at all
    # could be certified as having moved by more than the tolerance.
    # A SINGLE-step image, so the one expected landmark is unambiguous.
    single = card()
    single[:, 120:] = 200.0                  # one step at exactly nx 0.5
    single_img, _ = framed(single)
    off = -1.9 / 240                         # shifts the flat position by 1.9 px
    r_res = I.edge_compression(single_img, rect, [0.5], 1.0, off,
                               media_only_img=single_img)
    check("baseline NEGATIVE: a 1.9 px baseline error is NOT verified",
          r_res["flatBaselineVerified"] is False
          and 1.7 < r_res["flatBaselineResidualPx"] < 2.1, True,
          f"residual {r_res['flatBaselineResidualPx']} px, "
          f"limit {I.BASELINE_RESIDUAL_MAX_PX}")
    # ...and a baseline that is actually right IS verified, so the check is
    # not simply always-false.
    r_good = I.edge_compression(single_img, rect, [0.5], 1.0, 0.0,
                                media_only_img=single_img)
    check("baseline: a correct baseline is verified",
          r_good["flatBaselineVerified"] is True, True,
          f"residual {r_good['flatBaselineResidualPx']} px")
    check("baseline: the residual limit is well inside the scored window",
          I.BASELINE_RESIDUAL_MAX_PX < I.COMPRESSION_WINDOW_FLOOR_PX, True,
          f"{I.BASELINE_RESIDUAL_MAX_PX} < {I.COMPRESSION_WINDOW_FLOOR_PX}")


def t_hf_region():
    """hf_energy must read O4's inset region, not the whole card."""
    flat = card(240, 180, (120, 120, 120))
    ring = flat.copy()
    ring[:, :14] = 255.0                     # a bright rim, no media texture
    ring[:, -14:] = 255.0
    fimg, frect = framed(flat)
    rimg, rrect = framed(ring)
    check("hf region: a bright RIM does not register as media structure",
          abs(I.hf_energy(rimg, [rrect]) - I.hf_energy(fimg, [frect])) < 0.5,
          True,
          f"{I.hf_energy(rimg, [rrect])} vs {I.hf_energy(fimg, [frect])}")

    # NEGATIVE: real structure in the INTERIOR must register.
    inner = flat.copy()
    for x in range(60, 180, 8):
        inner[:, x:x + 4] = 255.0
    iimg, irect = framed(inner)
    check("hf region NEGATIVE: interior structure does register",
          I.hf_energy(iimg, [irect]) > 5.0, True,
          f"{I.hf_energy(iimg, [irect])}")


def t_grayscale_statistic():
    """The scored statistic must be robust to one pixel and sensitive to a cast."""
    grey = card(240, 180, (120, 120, 120))
    grey[90, 120, 0] = 255.0                 # ONE hot pixel
    gimg, grect = framed(grey)
    g = I.grayscale_chroma(gimg, [grect])
    check("grayscale: one hot pixel does not move the SCORED statistic",
          g["p995Chroma"] < I.GRAYSCALE_CHROMA_CEILING, True,
          f"p995 {g['p995Chroma']}, raw max {g['peakChroma']}")
    check("grayscale: the raw max still reports the outlier as a diagnostic",
          g["peakChroma"] > 100, True, f"{g['peakChroma']}")
    check("grayscale: the scored statistic is named in the result",
          g["scoredStatistic"] == "p995Chroma", True)

    # NEGATIVE: a real cast over the card must exceed the ceiling.
    cast = card(240, 180, (120, 120, 120))
    cast[..., 2] = 140.0
    cimg, crect = framed(cast)
    c = I.grayscale_chroma(cimg, [crect])
    check("grayscale NEGATIVE: a real cyan cast exceeds the ceiling",
          c["p995Chroma"] > I.GRAYSCALE_CHROMA_CEILING, True,
          f"p995 {c['p995Chroma']}")


# ------------------------------------------------------------ spectral
def t_spectral():
    rng = np.random.default_rng(7)
    checker = card()
    for y in range(0, 180, 8):
        for x in range(0, 240, 8):
            if ((x // 8) + (y // 8)) % 2:
                checker[y:y + 8, x:x + 8] = 255.0
    img, rect = framed(checker)
    s = I.spectral_structure(img, [rect])
    check("spectral: checker yields non-zero HF energy", s["hfMean"] > 1.0, True,
          f"hfMean {s['hfMean']}")

    blurred = checker.copy()
    for _ in range(6):
        blurred[1:-1, 1:-1] = (blurred[:-2, 1:-1] + blurred[2:, 1:-1]
                               + blurred[1:-1, :-2] + blurred[1:-1, 2:]) / 4
    bimg, brect = framed(blurred)
    sb = I.spectral_structure(bimg, [brect])
    check("spectral NEGATIVE: blur collapses HF energy",
          sb["hfMean"] < s["hfMean"] * 0.5, True,
          f"{sb['hfMean']} vs {s['hfMean']}")

    # Correlation: a render against itself is 1; against noise it is not.
    c_self = I.correlate(s["hfTiles"], s["hfTiles"])
    check("correlate: self-correlation is 1", abs(c_self["r"] - 1.0) < 1e-6, True)
    noise = list(rng.normal(size=len(s["hfTiles"])))
    c_noise = I.correlate(s["hfTiles"], noise)
    check("correlate NEGATIVE: noise does not correlate",
          abs(c_noise["r"]) < 0.5, True, f"r={c_noise['r']}")
    check("correlate NEGATIVE: constant series named, not NaN",
          I.correlate([1.0] * 40, list(range(40)))["r"] is None, True)
    check("correlate NEGATIVE: too-few tiles named, not NaN",
          I.correlate([1.0, 2.0], [1.0, 2.0])["r"] is None, True)

    # A DESATURATED render keeps HF but loses chroma -- the case a global
    # mean would miss and the reason chroma is tracked separately.
    tinted = checker.copy()
    tinted[..., 0] *= 0.75
    timg, trect = framed(tinted)
    st = I.spectral_structure(timg, [trect])
    check("spectral: chroma energy separates a tinted render from a grey one",
          st["chromaMean"] > s["chromaMean"] + 5, True,
          f"{st['chromaMean']} vs {s['chromaMean']}")


# ------------------------------------------------------------ false colour
def t_false_colour():
    checker = card()
    for y in range(0, 180, 8):
        for x in range(0, 240, 8):
            if ((x // 8) + (y // 8)) % 2:
                checker[y:y + 8, x:x + 8] = 255.0
    img, rect = framed(checker)
    f = I.false_colour_outside_features(img, [rect])
    check("false colour: achromatic checker has ~0 chroma away from features",
          f["chromaAwayFromFeatures"] < 1.0, True,
          f"{f['chromaAwayFromFeatures']}")

    washed = checker.copy()
    washed[..., 2] = np.clip(washed[..., 2] + 20, 0, 255)
    wimg, wrect = framed(washed)
    fw = I.false_colour_outside_features(wimg, [wrect])
    # +20 on B lifts chroma to 20 on the black tiles and 0 on the clipped
    # white ones, so the away-from-features mean lands near 10. The bar is
    # set well clear of the 0.0 an achromatic render gives, not near 20.
    check("false colour NEGATIVE: a blue wash is detected away from features",
          fw["chromaAwayFromFeatures"] > 5.0, True,
          f"{fw['chromaAwayFromFeatures']}")


# ------------------------------------------------------------ SDF truth
def t_sdf():
    a = card(200, 200, (0, 0, 0))
    img, rect = framed(a, pad=20)
    sdf = I.sdf_alpha_truth(rect, 40.0, (240, 240, 3))
    x0, y0, x1, y1 = rect
    check("sdf: centre is well inside (negative)",
          sdf[(y0 + y1) // 2, (x0 + x1) // 2] < -50, True)
    check("sdf: card corner is outside (positive)",
          sdf[y0 + 1, x0 + 1] > 0, True, f"{sdf[y0 + 1, x0 + 1]:.2f}")
    check("sdf: edge midpoint is near zero",
          abs(sdf[(y0 + y1) // 2, x0]) < 2.0, True,
          f"{sdf[(y0 + y1) // 2, x0]:.2f}")
    # NEGATIVE: a zero corner radius makes the corner a square corner (sdf ~0)
    sdf0 = I.sdf_alpha_truth(rect, 0.0, (240, 240, 3))
    check("sdf NEGATIVE: radius 0 puts the corner ON the outline, not outside",
          abs(sdf0[y0, x0]) < 1.5, True, f"{sdf0[y0, x0]:.2f}")

    # Alpha agreement: a card that respects its corners is clean...
    inner = card(200, 200, (0, 0, 0))
    ys, xs = np.mgrid[0:200, 0:200]
    hx = hy = 100.0
    r = 40.0
    qx = np.abs(xs + .5 - hx) - hx + r
    qy = np.abs(ys + .5 - hy) - hy + r
    d = (np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2)
         + np.minimum(np.maximum(qx, qy), 0) - r)
    inner[d < 0] = 180.0
    cimg, crect = framed(inner, pad=20, bg=(0, 0, 0))
    ag = I.alpha_edge_agreement(cimg, crect, 40.0, background_rgb=(0, 0, 0))
    check("alpha: a correctly rounded card lights no pixel outside its SDF",
          ag["litOutsidePixels"] == 0, True, f"{ag['litOutsidePixels']}")

    # ...and a SQUARE card lights its corners, which must be caught EVEN WITH
    # NO background supplied. The default sampler is what is under test here:
    # taking the background from the card's own corner would sample the very
    # lit pixels the check exists to find, and the instrument would report a
    # clean card.
    sq = card(200, 200, (180, 180, 180))
    simg, srect = framed(sq, pad=20, bg=(0, 0, 0))
    ags = I.alpha_edge_agreement(simg, srect, 40.0)
    check("alpha NEGATIVE: a square card is caught with NO background supplied",
          ags["litOutsidePixels"] > 200, True, f"{ags['litOutsidePixels']}")
    ags2 = I.alpha_edge_agreement(simg, srect, 40.0, background_rgb=(0, 0, 0))
    check("alpha: explicit and inferred backgrounds agree",
          ags["litOutsidePixels"] == ags2["litOutsidePixels"], True,
          f"{ags['litOutsidePixels']} vs {ags2['litOutsidePixels']}")
    # A card that fills its whole frame leaves nowhere to sample: that must
    # raise, not silently invent a background.
    try:
        I.alpha_edge_agreement(as_img(card(60, 60, (180, 180, 180))),
                               (0, 0, 60, 60), 12.0)
        raised = False
    except I.AggregatorShapeError:
        raised = True
    check("alpha NEGATIVE: no sampleable background raises rather than guesses",
          raised, True)


# ------------------------------------------------------------ scalars
def t_scalars():
    a = card()
    a[:, :20] = 30.0
    a[:, -20:] = 210.0
    img, rect = framed(a)
    d = I.dark_side_luma(img, [rect])
    check("dark luma: reads the dark edge band", abs(d["meanLuma"] - 30) < 2, True,
          f"{d['meanLuma']}")
    w = I.white_reflection_ratio(img, [rect])
    check("white ratio: bright over dark is ~7", abs(w["meanRatio"] - 7.0) < 0.5,
          True, f"{w['meanRatio']}")
    # NEGATIVE: swapping the sides must change the ratio, not preserve it.
    b = card()
    b[:, :20] = 210.0
    b[:, -20:] = 30.0
    img2, rect2 = framed(b)
    w2 = I.white_reflection_ratio(img2, [rect2])
    check("white ratio NEGATIVE: swapped sides invert the ratio",
          w2["meanRatio"] < 0.25, True, f"{w2['meanRatio']}")

    grey = card(bg=(120, 120, 120))
    gimg, grect = framed(grey)
    gc = I.grayscale_chroma(gimg, [grect])
    check("grayscale chroma: grey card is achromatic", gc["peakChroma"] < 0.5,
          True, f"{gc['peakChroma']}")
    tint = card(bg=(120, 120, 120))
    tint[:, 100:110, 0] = 150.0
    timg, trect = framed(tint)
    tc = I.grayscale_chroma(timg, [trect])
    check("grayscale chroma NEGATIVE: a cyan/magenta streak is caught",
          tc["peakChroma"] > 25, True, f"{tc['peakChroma']}")


# ------------------------------------------------------------ windows
def t_windows():
    check("window: floor binds when the Target is very repeatable",
          I.window(0.1, 1.5) == 1.5, True)
    check("window: 2x repeatability binds when it exceeds the floor",
          I.window(2.0, 1.5) == 4.0, True)
    check("enters: inside the window passes", I.enters(3.0, 3.3, 1.5), True)
    check("enters NEGATIVE: outside the window fails",
          I.enters(1.7, 3.3, 1.5) is False, True,
          "an UNDERSHOOT must fail a two-sided window -- the O4 lesson")
    check("toward: moving closer is True", I.toward(3.0, 9.7, 3.3) is True, True)
    check("toward NEGATIVE: overshooting past the Target is False",
          I.toward(1.0, 3.0, 3.3) is False, True)
    check("toward NEGATIVE: control already at Target yields None, not a claim",
          I.toward(5.0, 3.3, 3.3) is None, True)


# ------------------------------------------------------------ carried guards
def t_carried():
    check("carried: bools are not counted as numeric errors",
          I.zero_errors({"a": 0, "ok": True, "b": 0}) is True, True)
    check("carried NEGATIVE: a real numeric error is counted",
          I.zero_errors({"a": 0, "ok": True, "b": 3}) is False, True)
    try:
        I.require_number({"x": "nope"}, "x")
        ok = False
    except I.AggregatorShapeError:
        ok = True
    check("carried: a malformed aggregator shape fails fast", ok, True)
    try:
        I.require_number({}, "missing")
        ok2 = False
    except I.AggregatorShapeError:
        ok2 = True
    check("carried NEGATIVE: a missing key fails fast too", ok2, True)
    check("carried: interior relative-branch floor equals the absolute ceiling",
          I.INTERIOR_RELATIVE_BRANCH_FLOOR == 0.02, True)


def main() -> int:
    for fn in (t_landmarks, t_flat_position, t_compression, t_pairing,
               t_hf_region, t_grayscale_statistic, t_spectral,
               t_false_colour, t_sdf, t_scalars, t_windows, t_carried):
        print(f"\n{fn.__name__}:")
        fn()
    passed = sum(1 for r in RESULTS if r["pass"])
    out = REPO / "qa-v5/optics-o5/instrument-tests.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "what": "O5 instrument unit tests. Every check has a negative partner: "
                "a synthetic input that must make it fail. Run before sealing.",
        "passed": passed, "total": len(RESULTS),
        "pass": passed == len(RESULTS),
        "results": RESULTS,
    }, indent=1))
    print(f"\n{passed}/{len(RESULTS)} pass -> {out}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
