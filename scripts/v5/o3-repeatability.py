#!/usr/bin/env python3
"""O3 §八: turn the Target repeatability captures into the O3 thresholds.

The Target does not render the same numbers twice -- decode order, mount
timing and compositor state all move it. A threshold tighter than that
motion measures noise, and a threshold set after seeing the candidate
measures nothing at all. So the floors are derived here, from the Target
against itself, and sealed in the pre-registration commit.

  spread(metric)  = max - min across the independent repeats
  bandWidth       = max(2 * spread, 1.5 px)
  darkLuma        = max(2 * spread, 10 luma levels)
  whiteRatio      = max(2 * spread, 0.02)

The band-width and dark-luma spreads come from bw-split, the only asset
with a black side to measure a band against. The white-ratio spread is
the WORST of the six media, so one lucky asset cannot tighten the floor.

Usage: o3-repeatability.py --dir=<capture dir> --out=<json>
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_load("v0_culling", "v0_culling.py")
_load("source_layout", "source_layout.py")
S = _load("o2_optics_stats", "o2_optics_stats.py")

#: §八 floors -- the value a threshold may never go below, whatever the
#: Target's own spread turns out to be.
FLOOR = {"bandWidth": 1.5, "darkLuma": 10.0, "whiteRatio": 0.02}
SPREAD_MULTIPLIER = 2.0


def rects_for(w, h):
    """Twin rects, with the O2-documented landscape fallback.

    At 844x390 no card is fully inside the viewport, so the full O0 edge
    ring is not a valid population. The same fallback O2 recorded is used
    -- cards whose x-range and central 60% of height are visible -- and
    the basis is carried on every row so a reader can see which metrics
    the numbers came from.
    """
    rects = [r for _, r in S.rects_at(w, h)]
    if rects:
        return rects, "full-cards"
    frame = S.SL.layout(w, h)
    cam = S.VC.coverage_camera(0.0, 0.0, frame)
    pred = S.VC.frame_verdicts(0.0, 0.0, cam, frame)
    out = []
    for v in pred.values():
        if not v["draw"] or not v["aabb"]:
            continue
        x0, y0, x1, y1 = v["aabb"]
        ch = y1 - y0
        if x0 >= 2 and x1 <= w - 2 and y0 + 0.2 * ch >= 0 and y1 - 0.2 * ch <= h:
            out.append((int(x0), int(y0), int(x1), int(y1)))
    return out, "side-bands-basis"


def measure(path: Path, vp: str, asset: str) -> dict:
    w, h = map(int, vp.split("x"))
    img = Image.open(path)
    rects, basis = rects_for(w, h)
    if not rects:
        return {"metricBasis": "none"}
    out = {"metricBasis": basis, "cardsAnalysed": len(rects)}
    if basis == "full-cards":
        # the full edge ring is only a valid population when the whole card
        # is on screen
        st = S.stats(img, rects, w, h)
        out["whiteReflectionRatio"] = st["whiteReflectionRatio"]
        out["edgeChromaMean"] = st["edgeChromaMean"]
        out["edgeLuminanceMean"] = st["edgeLuminanceMean"]
    if asset == "bw-split":
        sides = S.side_bands(img, rects)
        band = S.reflection_band(img, rects)
        out["darkSideEdgeLuma"] = sides["darkSideEdgeLuma"]
        out["brightSideEdgeLuma"] = sides["brightSideEdgeLuma"]
        out["darkOverBrightLumaRatio"] = sides["darkOverBrightLumaRatio"]
        out["reflectionBandPx"] = band["meanPx"]
    return out


def spread(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if len(vals) < 2:
        return None
    return round(max(vals) - min(vals), 5)


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:])
    d = Path(args["dir"])
    out = Path(args["out"])
    man = json.loads((d / "repeatability-manifest.json").read_text())

    per = {}
    shas = {}
    for rec in man["records"]:
        key = f"{rec['asset']}@{rec['vp']}"
        per.setdefault(key, {})[rec["run"]] = measure(
            d / rec["file"], rec["vp"], rec["asset"])
        shas.setdefault(key, {})[rec["run"]] = hashlib.sha256(
            (d / rec["file"]).read_bytes()).hexdigest()

    identical = {k: len(set(v.values())) == 1 for k, v in shas.items()}

    series = {}
    for key, runs in sorted(per.items()):
        ordered = [runs[r] for r in sorted(runs)]
        metrics = sorted({k for m in ordered for k in m})
        series[key] = {
            "runs": sorted(runs),
            "perRun": {m: [r.get(m) for r in ordered] for m in metrics},
            "spread": {m: spread([r.get(m) for r in ordered]) for m in metrics},
            "mean": {m: (round(sum(v for v in (r.get(m) for r in ordered)
                                   if isinstance(v, (int, float)))
                               / max(1, sum(1 for r in ordered
                                            if isinstance(r.get(m), (int, float)))), 4)
                         if any(isinstance(r.get(m), (int, float)) for r in ordered)
                         else None)
                     for m in metrics},
        }

    bw = series.get("bw-split@1440x900", {}).get("spread", {})
    band_spread = bw.get("reflectionBandPx")
    luma_spread = bw.get("darkSideEdgeLuma")
    white_spreads = {k: v["spread"].get("whiteReflectionRatio")
                     for k, v in series.items() if k.endswith("@1440x900")}
    worst_white = max((v for v in white_spreads.values() if v is not None),
                      default=None)

    def threshold(name, sp):
        if sp is None:
            return {"spread": None, "twoSpread": None,
                    "threshold": FLOOR[name],
                    "bound": "floor (spread unmeasurable)"}
        two = round(SPREAD_MULTIPLIER * sp, 5)
        thr = max(two, FLOOR[name])
        return {"spread": sp, "twoSpread": two, "floor": FLOOR[name],
                "threshold": round(thr, 5),
                "bound": "2x spread" if two > FLOOR[name] else "floor"}

    thresholds = {
        "bandWidthThreshold": threshold("bandWidth", band_spread),
        "darkLumaThreshold": threshold("darkLuma", luma_spread),
        "whiteRatioThreshold": threshold("whiteRatio", worst_white),
    }
    # mobile band-width spreads, recorded so the §九.15 direction check has
    # a per-viewport noise floor rather than borrowing the desktop one
    for vp in ("390x844", "844x390"):
        s = series.get(f"bw-split@{vp}", {}).get("spread", {})
        thresholds[f"bandWidthThreshold@{vp}"] = threshold(
            "bandWidth", s.get("reflectionBandPx"))
        thresholds[f"darkLumaThreshold@{vp}"] = threshold(
            "darkLuma", s.get("darkSideEdgeLuma"))

    doc = {
        "what": "O3 §八 Target repeatability baseline: how far the Target "
                "moves against itself under the deterministic shared-media "
                "harness, and the thresholds derived from it.",
        "capturedBeforeCandidateCode": True,
        "target": man["target"],
        "repeats": man["repeats"],
        "freeze": man["freeze"],
        "spreadDefinition": "max - min across the independent repeats, per "
                            "metric per media per viewport. Each repeat is a "
                            "separate page load in a fresh browser context.",
        "thresholdLaw": {
            "bandWidthThreshold": "max(2 x Target spread of the bw-split "
                                  "reflection band width, 1.5 px)",
            "darkLumaThreshold": "max(2 x Target spread of the bw-split "
                                 "dark-side edge luma, 10 luma levels)",
            "whiteRatioThreshold": "max(2 x the WORST Target spread of "
                                   "whiteReflectionRatio across the six "
                                   "scored media, 0.02)",
            "note": "no threshold may be recomputed, loosened or tightened "
                    "after an O3 candidate is captured.",
        },
        "byteIdenticalAcrossRepeats": identical,
        "repeatabilityFinding":
            ("Every scored capture is BYTE-IDENTICAL across the three "
             "independent page loads, so the measured spread is exactly 0 on "
             "every metric and all three thresholds bind at their §八 floors. "
             "That is a property of the deterministic shared-media harness, "
             "not of the Target: routed frozen renditions plus a "
             "condition-driven mount wait remove the decode-order and "
             "mount-timing variance the raw Target page has. The floors "
             "therefore carry the whole tolerance, which is the conservative "
             "direction -- a 0-spread threshold would have been 0 px."
             if all(identical.values()) else
             "Some repeats differ byte-wise; see byteIdenticalAcrossRepeats "
             "and the per-metric spreads."),
        "whiteRatioSpreadPerAsset": white_spreads,
        "thresholds": thresholds,
        "series": series,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    for k, v in thresholds.items():
        print(f"{k:32s} spread={v['spread']} -> {v['threshold']} ({v['bound']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
