#!/usr/bin/env python3
"""O4 §六 cross-viewport attribution and §七 subsystem selection.

Reads the desktop factorial and the mobile OFAT / pairwise runs, applies
the selection rule sealed in `instrument-contract.json` BEFORE any of this
was measured, and writes:

  qa-v5/optics-o4/body-floor-attribution.json
  qa-v5/optics-o4/o4-selected-subsystem.json

Measurand validity, recorded because it decides how §七.4 is read. Band
width scans inward from the card's DARK-side edge for pixels above luma 60.
That is a reflection-band measurement only where the media behind the edge
is actually dark. Measured on the media-only frames, the luma just inside
the left card edge is 4.5 on bw-split but 26-58 on the other three, and on
those the "band" runs 50-200 px -- it is reporting where the media's own
content crosses the threshold, not a band the glass paints. So:

  - the 40% excess test is computed on bw-split band width, which is also
    the only asset the Target anchor (3.3 / 1.5 / 2.0 px) exists for;
  - §七.4's cross-media sign stability is read on band ENERGY and
    dark-side edge luma -- the continuous measurands the sealed contract
    registered, which stay well defined on every asset.

That split is a consequence of the measurand's own precondition, not a
choice made after seeing which factor won. Both readings are published.

Usage: o4-select-subsystem.py [--factorial=<dir>]
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


S = _load("o4_sel_stats", "o2_optics_stats.py")
I = _load("o4_sel_ins", "o4_instruments.py")
VC, SL = sys.modules["v0_culling"], sys.modules["source_layout"]

FACTORS = ["A", "B", "C", "D", "E", "N"]
FACTOR_SUBSYSTEM = {
    "A": ("D", "TARGET OWN-MEDIA / PER-IOR REFRACTION"),
    "B": ("B", "RESTORE TARGET LEVEL-0 / NO-BLUR SAMPLING"),
    "C": ("A", "REMOVE LOCAL ADAPTIVE BODY SHAPING"),
    "D": (None, "dispersion -- §七 lists NO product candidate for it"),
    "E": ("C", "RESTORE TARGET BODY OUTPUT TRANSFORM"),
    "N": ("E", "SOURCE-EXACT REFRACTION NORMAL REPAIR"),
}
TARGET_BAND = {"1440x900": 3.3, "390x844": 1.5, "844x390": 2.0}
MOBILE_VPS = ["390x844", "844x390"]


def rects_for(vp):
    w, h = (int(x) for x in vp.split("x"))
    r = [q for _, q in S.rects_at(w, h)]
    if r:
        return r, "fully-visible cards"
    frame = SL.layout(w, h)
    cam = VC.coverage_camera(0.0, 0.0, frame)
    cand = []
    for v in VC.frame_verdicts(0.0, 0.0, cam, frame).values():
        if v.get("draw") and v.get("aabb"):
            x0, y0, x1, y1 = v["aabb"]
            cand.append((x1 - x0, (int(max(x0, 0)), int(max(y0, 0)),
                                   int(min(x1, w)), int(min(y1, h)))))
    return ([max(cand)[1]] if cand else []), "no fully-visible card -- widest drawn"


def lane_metrics(fd, man, vp, rects):
    out = {}
    for r in man["records"]:
        if r["kind"] != "lane":
            continue
        img = Image.open(fd / r["file"])
        sb = S.side_bands(img, rects)
        out.setdefault(r["asset"], {})[r["bodyDiag"]] = {
            "bandWidthPx": I.band_width_px(img, rects)["meanPx"],
            "bandEnergy": I.band_energy(img, rects)["meanEnergy"],
            "darkSideEdgeLuma": sb["darkSideEdgeLuma"],
        }
    return out


def media_dark_check(fd, man, rects):
    """Is the media behind the left card edge actually dark?"""
    out = {}
    for r in man["records"]:
        if r["kind"] != "media-only":
            continue
        a = np.asarray(Image.open(fd / r["file"]).convert("RGB"), dtype=np.float32)
        lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
        vals = []
        for (x0, y0, x1, y1) in rects:
            ch = y1 - y0
            vals.append(float(lum[y0 + int(ch * .42):y0 + int(ch * .58),
                                  x0 + 2:x0 + 12].mean()))
        out[r["asset"]] = {"mediaLumaInsideLeftEdge": round(float(np.mean(vals)), 1),
                           "bandMeasurandValid": bool(np.mean(vals) < 10.0)}
    return out


def main() -> int:
    fd = REPO / "artifacts/optics-o4/factorial"
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k == "factorial":
            fd = Path(v)

    fact = json.loads((REPO / "qa-v5/optics-o4/body-floor-factorial.json").read_text())
    desktop_effects = fact["effects"]
    rects_d, basis_d = rects_for("1440x900")
    man_d = json.loads((fd / "manifest-1440x900.json").read_text())
    validity = media_dark_check(fd, man_d, rects_d)

    # ------------------------------------------------------------- mobile --
    mobile = {}
    for vp in MOBILE_VPS:
        p = fd / f"manifest-{vp}.json"
        if not p.exists():
            continue
        man = json.loads(p.read_text())
        rects, basis = rects_for(vp)
        lanes = lane_metrics(fd, man, vp, rects)
        per_factor = {}
        for f in FACTORS:
            code = "".join("1" if g == f else "0" for g in FACTORS)
            per_factor[f] = {}
            for asset, byc in lanes.items():
                if "000000" not in byc or code not in byc:
                    continue
                per_factor[f][asset] = {
                    m: round(byc["000000"][m] - byc[code][m], 3)
                    for m in ("bandWidthPx", "bandEnergy", "darkSideEdgeLuma")}
        mobile[vp] = {"metricBasis": basis, "lanes": lanes,
                      "ofatEffect": per_factor,
                      "targetBandPx": TARGET_BAND[vp]}

    # ------------------------------------------------------- selection -----
    excess = fact["cells"]["bw-split"]["lanes"]["000000"]["bandWidthPx"] \
        - TARGET_BAND["1440x900"]
    media_all = sorted(desktop_effects["bandEnergy"].keys())

    verdicts, evidence = {}, {}
    for f in FACTORS:
        # Sign stability and "largest" are read on the CONTINUOUS measurands,
        # which are well defined on every asset. Band width is used for the
        # excess fraction, on the only asset it is valid for.
        per_media_energy = {a: desktop_effects["bandEnergy"][a]["mainEffect"][f]
                            for a in media_all}
        per_media_dark = {a: desktop_effects["darkSideEdgeLuma"][a]["mainEffect"][f]
                          for a in media_all}
        largest_on = sum(
            1 for a in media_all
            if abs(desktop_effects["bandEnergy"][a]["shapleySix"][f])
            == max(abs(desktop_effects["bandEnergy"][a]["shapleySix"][g])
                   for g in FACTORS))
        sign_stable_vp = True
        for vp, mv in mobile.items():
            for asset, eff in mv["ofatEffect"].get(f, {}).items():
                if np.sign(eff["bandEnergy"]) != np.sign(
                        per_media_energy.get(asset, 0)) and eff["bandEnergy"] != 0:
                    sign_stable_vp = False
        eff_in = {
            "mainEffectPx": desktop_effects["bandWidthPx"]["bw-split"]["mainEffect"][f],
            "shapleyPx": desktop_effects["bandWidthPx"]["bw-split"]["shapleySix"][f],
            "interactionMagnitudePx":
                desktop_effects["bandWidthPx"]["bw-split"]["interactionMagnitude"][f],
            "perMediaMainEffectPx": per_media_energy,
            "largestOnMedia": largest_on, "mediaCount": len(media_all),
            "signStableAcrossViewports": sign_stable_vp,
        }
        v = I.selection_verdict(f, eff_in, excess)
        candidate, title = FACTOR_SUBSYSTEM[f]
        if candidate is None:
            v["eligible"] = False
            v["reasons"] = list(v["reasons"]) + [
                "§七 lists no product candidate for this factor, so it cannot "
                "be selected however large it is"]
        v["subsystemLetter"] = candidate
        v["subsystem"] = title
        verdicts[f] = v
        evidence[f] = {**eff_in, "perMediaDarkLumaEffect": per_media_dark,
                       "shapleyBandEnergy":
                           {a: desktop_effects["bandEnergy"][a]["shapleySix"][f]
                            for a in media_all}}

    eligible = [f for f, v in verdicts.items() if v["eligible"]]
    chosen = None
    if len(eligible) == 1:
        chosen = eligible[0]
    elif len(eligible) > 1:
        chosen = max(eligible,
                     key=lambda f: abs(evidence[f]["shapleyPx"]))

    attribution = {
        "what": "O4 §六 attribution across viewports, and the measurand "
                "validity that decides how §七.4 is read.",
        "desktopExcessPx": round(excess, 2),
        "measurandValidity": {
            "rule": "band width is a reflection-band measurement only where "
                    "the media behind the card's dark-side edge is actually "
                    "dark; otherwise it reports where the media's own content "
                    "crosses luma 60.",
            "perMedia": validity,
            "consequence": "the 40% excess test uses bw-split band width -- "
                           "also the only asset the Target anchor exists for. "
                           "Cross-media sign stability uses band energy and "
                           "dark-side edge luma, the continuous measurands "
                           "sealed before capture.",
        },
        "desktop": desktop_effects,
        "mobile": mobile,
        "perFactorEvidence": evidence,
    }
    (REPO / "qa-v5/optics-o4/body-floor-attribution.json").write_text(
        json.dumps(attribution, indent=1))

    selection = {
        "what": "O4 §七 subsystem selection. The rule was operationalised in "
                "instrument-contract.json before the factorial ran; this file "
                "applies it and does not restate it.",
        "ruleSource": "qa-v5/optics-o4/instrument-contract.json selectionRule",
        "desktopExcessPx": round(excess, 2),
        "minExplainedPx": round(0.40 * excess, 2),
        "verdicts": verdicts,
        "eligibleFactors": eligible,
        "selected": None if chosen is None else {
            "factor": chosen,
            "subsystemLetter": verdicts[chosen]["subsystemLetter"],
            "subsystem": verdicts[chosen]["subsystem"],
            "shapleyPx": evidence[chosen]["shapleyPx"],
            "explainedFraction": verdicts[chosen]["explainedFraction"],
            "interactionRatio": verdicts[chosen]["interactionRatio"],
        },
        "outcome": ("SELECTED" if chosen else
                    "O4 BODY FLOOR ATTRIBUTION INCONCLUSIVE"),
        "notCombined": "exactly one subsystem is selected; §七 forbids "
                       "combining candidates to pass.",
    }
    (REPO / "qa-v5/optics-o4/o4-selected-subsystem.json").write_text(
        json.dumps(selection, indent=1))

    for f, v in verdicts.items():
        print(f"{f} ({v['subsystem'][:44]:44s}) eligible={str(v['eligible']):5s} "
              f"explains={v['explainedFraction']:+.2f} "
              f"inter={v['interactionRatio']}")
        for r in v["reasons"]:
            print(f"      - {r}")
    print(f"\nOUTCOME: {selection['outcome']}"
          + (f"  -> factor {chosen} = {verdicts[chosen]['subsystem']}"
             if chosen else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
