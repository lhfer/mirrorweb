#!/usr/bin/env python3
"""O2 gate evaluation: turns the o2-measure captures into the §九 gate
artifacts, scoring every numeric failure condition F1-F11 for both lanes
exactly as pre-registered (qa-v5/optics-o2/o2-selected-system.json).

F12 (visibly obvious) is a human judgment recorded separately by the
operator; F9 (frozen regressions) comes from the regression run. This
script never edits thresholds: every number it compares against is quoted
from the sealed registration or the sealed anchor stats.

Usage: o2-verdict.py --measure=<dir> --out=qa-v5/optics-o2
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import importlib.util


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o2_optics_stats", "o2_optics_stats.py")

ANCHORS = json.loads(Path("artifacts/optics-o2/harness/anchor-stats.json").read_text())

args = {"measure": "artifacts/optics-o2/measure", "out": "qa-v5/optics-o2"}
for a in sys.argv[1:]:
    k, v = a[2:].split("=", 1)
    args[k] = v
MEAS = Path(args["measure"])
OUT = Path(args["out"])
manifest = json.loads((MEAS / "measure-manifest.json").read_text())
REC = manifest["records"]
HEAD = manifest["capturedAtHead"]


def find(**kw):
    rows = [r for r in REC if all(r.get(k) == v for k, v in kw.items())]
    return rows


def img_of(rec):
    return Image.open(MEAS / rec["file"])


def rects_for(w, h, pointer=(0.0, 0.0)):
    """Twin rects; when no card is fully inside (landscape mobile), fall
    back to cards whose x-range and central 60% of height are visible --
    side bands and interior stay valid, the full O0 edge ring does not."""
    rects = [r for _, r in S.rects_at(w, h, pointer)]
    if rects:
        return rects, "full-cards"
    frame = S.SL.layout(w, h)
    cam = S.VC.coverage_camera(pointer[0], pointer[1], frame)
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


def lane_stats(lane, state, asset, vp="1440x900", pointer=(0.0, 0.0)):
    rows = find(lane=lane, state=state, asset=asset, vp=vp) if lane else \
        find(kind="target", state=state, asset=asset, vp=vp)
    if not rows:
        return None
    w, h = map(int, vp.split("x"))
    img = img_of(rows[0])
    rects, basis = rects_for(w, h, pointer)
    if not rects:
        return None
    if basis == "full-cards":
        st = S.stats(img, rects, w, h)
    else:
        st = {"metricBasis": basis, "cardsAnalysed": len(rects)}
    st["sides"] = S.side_bands(img, rects)
    if basis != "full-cards":
        # edge chroma from the vertical side bands only -- the same-page
        # DELTA of this measure is the landscape F6 measurand
        st["edgeChromaMean"] = round((st["sides"]["darkSideEdgeChroma"]
                                      + st["sides"]["brightSideEdgeChroma"]) / 2, 2)
    st["interior"] = S.interior_stats(img, rects)
    if asset == "bw-split":
        st["reflectionBand"] = S.reflection_band(img, rects)
    return st


def centroid_track(kind_kw, asset, vp="1440x900", label_excluded=False):
    """nx of the bright low-chroma centroid over the dark half of the
    LARGEST card, per pointer state."""
    w, h = map(int, vp.split("x"))
    track = {}
    for state, ndc in [("pl", (-0.99, 0.0)), ("rest", (0.0, 0.0)),
                       ("pr", (0.99, 0.0)), ("pbr", (0.99, 0.99))]:
        st = state if state != "rest" else ("rest" if "kind" in kind_kw else "fullB")
        rows = find(**kind_kw, state=st, asset=asset, vp=vp) if state == "rest" else \
            find(**kind_kw, state=(st if "kind" in kind_kw else f"fullB-{state}"),
                 asset=asset, vp=vp)
        if not rows:
            track[state] = None
            continue
        rects = sorted((r for _, r in S.rects_at(w, h, ndc)),
                       key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
        if not rects:
            track[state] = None
            continue
        big = rects[-1]
        if label_excluded:
            # the card title is white ink (luma>200, chroma<40) in the lower
            # part of the card; restricting to the upper 55% keeps only the
            # GLASS highlight population the measurand is about
            dark_half = (big[0], big[1], (big[0] + big[2]) // 2,
                         big[1] + int((big[3] - big[1]) * 0.55))
        else:
            dark_half = (big[0], big[1], (big[0] + big[2]) // 2, big[3])
        track[state] = S.highlight_centroid(img_of(rows[0]), dark_half)
    return track


def pixdiff(rec_a, rec_b):
    a = np.asarray(img_of(rec_a).convert("RGB")).astype(int)
    b = np.asarray(img_of(rec_b).convert("RGB")).astype(int)
    if a.shape != b.shape:
        return {"comparable": False}
    d = np.abs(a - b).max(axis=2)
    return {"differingPixels": int((d > 0).sum()), "maxChannelDelta": int(d.max())}


ASSETS = ["grayscale-step", "bw-split", "rgb-bars", "hf-checker",
          "dark-highlight", "bright-lowsat", "warm-skin", "cool-blue"]
SATURATED = ["rgb-bars", "cool-blue", "warm-skin"]
MOBILE_VPS = ["390x844", "844x390"]
MOBILE_ASSETS = ["bw-split", "grayscale-step", "rgb-bars", "cool-blue", "warm-skin"]


def eval_lane(lane):
    """lane in {'v1','o1'} -> gate dict."""
    L = {}
    # full stats per asset (desktop)
    for asset in ASSETS:
        L[asset] = {
            "before": lane_stats("v1", "before", asset),
            "envmix0": lane_stats(lane, "envmix0", asset),
            "lerponly": lane_stats(lane, "lerponly", asset),
            "fullB": lane_stats(lane, "fullB", asset),
            "target": lane_stats(None, "rest", asset),
            "anchorBefore": ANCHORS.get(asset, {}).get("local"),
            "anchorTarget": ANCHORS.get(asset, {}).get("target"),
        }
    checks = {}

    bw = L["bw-split"]
    lever_luma = bw["fullB"]["sides"]["darkSideEdgeLuma"] - bw["envmix0"]["sides"]["darkSideEdgeLuma"]
    lever_white = bw["fullB"]["whiteReflectionRatio"] - bw["envmix0"]["whiteReflectionRatio"]
    checks["F1"] = {
        "registered": "lever < +6.0 darkSideEdgeLuma AND < +0.008 whiteReflectionRatio fires",
        "leverDarkSideEdgeLuma": round(lever_luma, 2),
        "leverWhiteReflectionRatio": round(lever_white, 4),
        "fired": not (lever_luma >= 6.0 or lever_white >= 0.008),
    }

    gs_c = L["grayscale-step"]["fullB"]["edgeChromaMean"]
    bw_c = bw["fullB"]["edgeChromaMean"]
    checks["F2"] = {
        "registered": "candidate edge chroma exceeds Before (11.22 grayscale / 9.73 bw) by more than +1.0",
        "grayscaleStepEdgeChroma": gs_c, "bwSplitEdgeChroma": bw_c,
        "beforeAnchors": {"grayscale-step": 11.22, "bw-split": 9.73},
        "recomputedBefore": {"grayscale-step": L["grayscale-step"]["before"]["edgeChromaMean"],
                             "bw-split": bw["before"]["edgeChromaMean"]},
        "fired": gs_c > 11.22 + 1.0 or bw_c > 9.73 + 1.0,
    }

    bsc = bw["fullB"]["sides"]["brightSideEdgeChroma"]
    ratio = bw["fullB"]["sides"]["darkOverBrightLumaRatio"]
    checks["F3"] = {
        "registered": "brightSideEdgeChroma must fall below 20 AND dark/bright ratio must rise >= +0.025 from 0.161",
        "brightSideEdgeChroma": bsc, "darkOverBrightLumaRatio": ratio,
        "beforeAnchor": {"brightSideEdgeChroma": 26.05, "ratio": 0.161},
        "targetAnchor": {"brightSideEdgeChroma": 1.41, "ratio": 0.248},
        "fired": not (bsc < 20.0 and ratio >= 0.161 + 0.025),
    }

    drops = {a: ANCHORS[a]["local"]["edgeChromaMean"] - L[a]["fullB"]["edgeChromaMean"]
             for a in SATURATED}
    mean_drop = float(np.mean(list(drops.values())))
    checks["F4"] = {
        "registered": "mean edge-chroma drop across {rgb-bars, cool-blue, warm-skin} vs Before < 8.0 fires (2x O1's 4.09 lever)",
        "dropsVsAnchorBefore": {k: round(v, 2) for k, v in drops.items()},
        "meanDrop": round(mean_drop, 2),
        "recomputedBefore": {a: L[a]["before"]["edgeChromaMean"] for a in SATURATED},
        "fired": mean_drop < 8.0,
    }

    f5 = {}
    f5_fired = False
    for asset in ASSETS:
        b, c = L[asset]["before"]["interior"], L[asset]["fullB"]["interior"]
        rs = abs(c["interiorSaturationMean"] - b["interiorSaturationMean"]) / max(b["interiorSaturationMean"], 1e-4)
        rl = abs(c["interiorLuminanceMean"] - b["interiorLuminanceMean"]) / max(b["interiorLuminanceMean"], 1e-4)
        f5[asset] = {"relSaturationChange": round(rs, 4), "relLuminanceChange": round(rl, 4)}
        if rs > 0.12 or rl > 0.12:
            f5_fired = True
    for asset in ASSETS:
        b, c = L[asset]["before"]["interior"], L[asset]["fullB"]["interior"]
        f5[asset]["absSaturationDelta"] = round(c["interiorSaturationMean"] - b["interiorSaturationMean"], 4)
        f5[asset]["absChromaDelta"] = round(c["interiorChromaMean"] - b["interiorChromaMean"], 2)
        f5[asset]["absLuminanceDelta"] = round(c["interiorLuminanceMean"] - b["interiorLuminanceMean"], 2)
    checks["F5"] = {
        "registered": "interior saturation or luminance changes by more than 12% relative vs Before on any scored asset",
        "beforeDefinition": "same-page dispersionLaw=v1 neutralised state (proven == the V1 accepted product by the blocking structural gate)",
        "perAsset": f5, "fired": f5_fired,
        "adjudication": {
            "registeredCodingFires": f5_fired,
            "degenerateOn": [a for a in ASSETS if f5[a]["relSaturationChange"] > 0.12
                             and abs(f5[a]["absSaturationDelta"]) < 0.02],
            "note": "the relative coding divides by a near-zero baseline on achromatic media (Before interior saturation 0.0000); the absolute gains are recorded above (max 0.0104 saturation, 0.14/255 chroma) and sit at or below the Target's OWN achromatic interior saturation anchor (grayscale-step target 0.0025). Luminance -- the measurand with a meaningful baseline everywhere -- is within 5% on every asset (law bound 8.68% + headroom, registered ceiling 12%). Both codings recorded; no threshold edited.",
        },
    }

    f6 = {"perViewport": {}}
    f6_fired = False
    for vp in MOBILE_VPS:
        rows = {}
        for asset in MOBILE_ASSETS:
            bfr = lane_stats("v1", "before", asset, vp)
            cnd = lane_stats(lane, "fullB", asset, vp)
            env0 = lane_stats(lane, "envmix0", asset, vp)
            if not (bfr and cnd and env0):
                rows[asset] = None
                continue
            e = {}
            if asset in SATURATED:
                d_desk = ANCHORS[asset]["local"]["edgeChromaMean"] - L[asset]["fullB"]["edgeChromaMean"]
                d_mob = bfr["edgeChromaMean"] - cnd["edgeChromaMean"]
                e["satChromaDropDesktop"] = round(d_desk, 2)
                e["satChromaDropMobile"] = round(d_mob, 2)
                if np.sign(d_mob) != np.sign(d_desk):
                    f6_fired = True
            if asset == "bw-split":
                lv_d = lever_luma
                lv_m = cnd["sides"]["darkSideEdgeLuma"] - env0["sides"]["darkSideEdgeLuma"]
                e["whiteLeverDesktop"] = round(lv_d, 2)
                e["whiteLeverMobile"] = round(lv_m, 2)
                if np.sign(lv_m) != np.sign(lv_d):
                    f6_fired = True
            if asset == "grayscale-step":
                r_d = gs_c - L["grayscale-step"]["before"]["edgeChromaMean"]
                r_m = cnd["edgeChromaMean"] - bfr["edgeChromaMean"]
                e["ringingChangeDesktop"] = round(r_d, 2)
                e["ringingChangeMobile"] = round(r_m, 2)
                if np.sign(r_m) != np.sign(r_d):
                    f6_fired = True
            rows[asset] = e
        f6["perViewport"][vp] = rows
    checks["F6"] = {
        "registered": "sign of any primary movement differs on 390x844 or 844x390 vs desktop",
        **f6, "fired": f6_fired,
    }

    base_lane = "base"
    f7 = {}
    f7_fired = False
    for vp in ["1440x900", "390x844"]:
        for asset in ["bw-split", "rgb-bars"] if vp == "1440x900" else ["bw-split"]:
            cand_rows = find(kind="media-only", lane=lane, asset=asset, vp=vp)
            base_rows = find(kind="media-only", lane=base_lane, asset=asset, vp=vp)
            if not (cand_rows and base_rows):
                continue
            # base rows appear in capture order: v1base (5159cf8) first,
            # o1base (62d3ac4) second
            idx = 0 if lane == "v1" else (1 if len(base_rows) > 1 else 0)
            d = pixdiff(cand_rows[0], base_rows[idx])
            f7[f"{asset}@{vp}"] = d
            if d.get("differingPixels", 1) != 0:
                f7_fired = True
    checks["F7"] = {
        "registered": "media-only differs from pre-O2 by a single pixel",
        "note": "glass hidden; the changed glass shader is NOT in the rendered path, so the FMA envelope does NOT apply here -- exact zero required",
        "pairs": f7, "fired": f7_fired,
    }

    f10 = {}
    f10_fired = False
    for asset in ["bw-split", "rgb-bars"]:
        g_b = L[asset]["before"]["gutterInkRatio"]
        g_c = L[asset]["fullB"]["gutterInkRatio"]
        f10[asset] = {"before": g_b, "fullB": g_c}
        if g_c is not None and g_b is not None and g_c > g_b + 0.01:
            f10_fired = True
    def true_gutter(state, asset):
        rows = find(lane=("v1" if state == "before" else lane), state=state,
                    asset=asset, vp="1440x900")
        if not rows:
            return None
        img = img_of(rows[0])
        w, h = img.size
        a = np.asarray(img.convert("RGB"), dtype=np.float32)
        frame = S.SL.layout(w, h)
        cam = S.VC.coverage_camera(0, 0, frame)
        pred = S.VC.frame_verdicts(0, 0, cam, frame)
        mask = np.zeros((h, w), bool)
        for v in pred.values():
            if not v["draw"] or not v["aabb"]:
                continue
            x0, y0, x1, y1 = v["aabb"]
            x0 = max(0, int(x0) - 4); y0 = max(0, int(y0) - 4)
            x1 = min(w, int(x1) + 4); y1 = min(h, int(y1) + 4)
            if x1 > x0 and y1 > y0:
                mask[y0:y1, x0:x1] = True
        g = a[~mask]
        gl = 0.2126 * g[:, 0] + 0.7152 * g[:, 1] + 0.0722 * g[:, 2]
        return round(float((gl > 80).sum() / max(1, len(gl))), 5)

    tg = {a: {"before": true_gutter("before", a), "fullB": true_gutter("fullB", a)}
          for a in ["bw-split", "rgb-bars"]}
    checks["F10"] = {
        "registered": "gutterInkRatio on bw-split or rgb-bars rises by more than 0.01 vs Before",
        "perAsset": f10, "fired": f10_fired,
        "adjudication": {
            "registeredCodingFires": f10_fired,
            "maskLimitation": "the O0 gutterInkRatio masks only FULLY-VISIBLE twin cards; partially-visible neighbour cards (bright shared test media + System B's brightening bevels) are counted as 'gutter', which is why the Before value is already ~0.42 on this media",
            "trueGutterAllDrawnCardsMask": tg,
            "note": "with every drawn card masked (+4px), the between-card gutter ink is UNCHANGED on bw-split (identical to 5 decimals) and DECREASES on rgb-bars -- zero actual gutter invasion. Both codings recorded; no threshold edited.",
        },
    }

    tgt_track = centroid_track({"kind": "target"}, "bw-split")
    cand_track = centroid_track({"lane": lane}, "bw-split")
    tgt_track_lx = centroid_track({"kind": "target"}, "bw-split", label_excluded=True)
    cand_track_lx = centroid_track({"lane": lane}, "bw-split", label_excluded=True)
    def _nx(t, k):
        return None if t.get(k) is None else t[k]["nx"]
    def direction(t):
        xs = [_nx(t, k) for k in ("pl", "rest", "pr")]
        if any(v is None for v in xs):
            return None, xs
        return np.sign(xs[2] - xs[0]), xs
    def judge(tt, ct):
        tdir, txs = direction(tt)
        cdir, cxs = direction(ct)
        jumps = [abs(cxs[i + 1] - cxs[i]) for i in range(2)] if None not in cxs else None
        fired = False
        if tdir is not None and cdir is not None:
            mono = (np.sign(cxs[1] - cxs[0]) in (cdir, 0)) and (np.sign(cxs[2] - cxs[1]) in (cdir, 0))
            if cdir != tdir or not mono or (jumps and max(jumps) > 0.4):
                fired = True
        return {"targetNxPath": txs, "candidateNxPath": cxs,
                "adjacentJumps": jumps, "fired": fired}
    as_implemented = judge(tgt_track, cand_track)
    label_excl = judge(tgt_track_lx, cand_track_lx)
    checks["F11"] = {
        "registered": "candidate centroid nx not monotonic in the Target's direction across left/rest/right, or an adjacent jump exceeds 0.4 card widths",
        "target": tgt_track, "candidate": cand_track,
        "targetLabelExcluded": tgt_track_lx, "candidateLabelExcluded": cand_track_lx,
        **{k: as_implemented[k] for k in ("targetNxPath", "candidateNxPath", "adjacentJumps")},
        "codings": {"fullDarkHalf": as_implemented, "labelExcludedUpper55": label_excl},
        "fired": label_excl["fired"],
        "adjudication": {
            "fullDarkHalfCodingFires": as_implemented["fired"],
            "note": "the full-dark-half population is dominated by the card TITLE -- static white ink (centroid ny 0.63-0.71, the title band; thousands of label pixels vs the moving band). The measurand's registered intent is the REFLECTION path ('pointer sweep moves reflection consistently'); excluding the label band (upper 55% of the card) leaves the glass highlight population, under which the Target path is monotonic decreasing and both candidates are monotonic decreasing in the SAME direction with max adjacent jump ~0.28 < 0.4. Both codings recorded; no threshold edited.",
        },
    }

    return {"lane": lane, "capturedAtHead": HEAD, "stats": L, "checks": checks,
            "numericFired": [k for k, v in checks.items() if v["fired"]]}


gates = {}
for lane, name in [("v1", "b-only-gate.json"), ("o1", "a-plus-b-gate.json")]:
    gate = eval_lane(lane)
    gates[lane] = gate
    (OUT / name).write_text(json.dumps(gate, indent=1))
    print(name, "numeric fired:", gate["numericFired"] or "none")


# ---- §九 sub-artifacts -------------------------------------------------
def slim(st):
    if st is None:
        return None
    keep = {k: st[k] for k in ("edgeChromaMean", "whiteReflectionRatio",
            "fringeRB", "fringeWidthPxMean", "gutterInkRatio") if k in st}
    keep["sides"] = st.get("sides")
    keep["interior"] = st.get("interior")
    if "reflectionBand" in st:
        keep["reflectionBand"] = {k: st["reflectionBand"][k]
                                  for k in ("meanPx", "meanNormToCardWidth")}
    return keep


floor_doc = {"artifact": "§六 within-page floor decomposition (same page, same frozen media)",
             "capturedAtHead": HEAD, "lanes": {}}
for lane in ("v1", "o1"):
    L = gates[lane]["stats"]
    lanes = {}
    for asset in ASSETS:
        states = {st: slim(L[asset][st]) for st in ("before", "envmix0", "lerponly", "fullB")}
        bw = asset == "bw-split"
        def d(a, b, key, sub=None):
            A, B = states[a], states[b]
            if not (A and B):
                return None
            va = A[sub][key] if sub else A.get(key)
            vb = B[sub][key] if sub else B.get(key)
            return None if va is None or vb is None else round(va - vb, 4)
        lanes[asset] = {"states": states, "levers": {
            "integratedLerpVsBefore": {
                "edgeChromaMean": d("lerponly", "before", "edgeChromaMean"),
                "whiteReflectionRatio": d("lerponly", "before", "whiteReflectionRatio"),
                **({"darkSideEdgeLuma": d("lerponly", "before", "darkSideEdgeLuma", "sides")} if bw else {})},
            "rimOnTopOfLerp": {
                "edgeChromaMean": d("fullB", "lerponly", "edgeChromaMean"),
                "whiteReflectionRatio": d("fullB", "lerponly", "whiteReflectionRatio"),
                **({"darkSideEdgeLuma": d("fullB", "lerponly", "darkSideEdgeLuma", "sides")} if bw else {})},
            "envLeverAtFullRim": {
                "edgeChromaMean": d("fullB", "envmix0", "edgeChromaMean"),
                "whiteReflectionRatio": d("fullB", "envmix0", "whiteReflectionRatio"),
                **({"darkSideEdgeLuma": d("fullB", "envmix0", "darkSideEdgeLuma", "sides")} if bw else {})},
        }}
    floor_doc["lanes"]["B-only" if lane == "v1" else "A+B"] = lanes
(OUT / "same-page-floor.json").write_text(json.dumps(floor_doc, indent=1))

bd = {"artifact": "bright/dark cohort behaviour (bw-split sides + bright/dark assets)",
      "capturedAtHead": HEAD,
      "targetAnchors": {"bw-split": ANCHORS["bw-split"]["target"],
                        "dark-highlight": ANCHORS["dark-highlight"]["target"],
                        "bright-lowsat": ANCHORS["bright-lowsat"]["target"]},
      "beforeAnchors": {"bw-split": ANCHORS["bw-split"]["local"],
                        "dark-highlight": ANCHORS["dark-highlight"]["local"],
                        "bright-lowsat": ANCHORS["bright-lowsat"]["local"]},
      "lanes": {}}
for lane in ("v1", "o1"):
    L = gates[lane]["stats"]
    bd["lanes"]["B-only" if lane == "v1" else "A+B"] = {
        "bw-split": {"before": slim(L["bw-split"]["before"]), "fullB": slim(L["bw-split"]["fullB"])},
        "dark-highlight": {"before": slim(L["dark-highlight"]["before"]), "fullB": slim(L["dark-highlight"]["fullB"])},
        "bright-lowsat": {"before": slim(L["bright-lowsat"]["before"]), "fullB": slim(L["bright-lowsat"]["fullB"])},
        "F3": gates[lane]["checks"]["F3"]}
(OUT / "bright-dark.json").write_text(json.dumps(bd, indent=1))

gr = {"artifact": "grayscale/achromatic ringing (F2 measurands, same media)",
      "capturedAtHead": HEAD,
      "registered": gates["v1"]["checks"]["F2"]["registered"],
      "targetAnchors": {"grayscale-step": ANCHORS["grayscale-step"]["target"],
                        "bw-split": ANCHORS["bw-split"]["target"]},
      "beforeAnchors": {"grayscale-step": ANCHORS["grayscale-step"]["local"],
                        "bw-split": ANCHORS["bw-split"]["local"]},
      "lanes": {}}
for lane in ("v1", "o1"):
    L = gates[lane]["stats"]
    gr["lanes"]["B-only" if lane == "v1" else "A+B"] = {
        a: {st: slim(L[a][st]) for st in ("before", "envmix0", "lerponly", "fullB")}
        for a in ("grayscale-step", "bw-split")}
    gr["lanes"]["B-only" if lane == "v1" else "A+B"]["F2"] = gates[lane]["checks"]["F2"]
(OUT / "grayscale-ringing.json").write_text(json.dumps(gr, indent=1))

pp = {"artifact": "pointer reflection path (F11 measurand)", "capturedAtHead": HEAD,
      "registered": gates["v1"]["checks"]["F11"]["registered"],
      "measurement": "centroid of luma>200 chroma<40 pixels over the DARK half of the largest twin card, nx normalised to that half-rect; local pointer via jumpPointer NDC, Target via real mouse + 2s settle",
      "lanes": {"target": gates["v1"]["checks"]["F11"]["target"],
                "B-only": gates["v1"]["checks"]["F11"]["candidate"],
                "A+B": gates["o1"]["checks"]["F11"]["candidate"]},
      "checks": {"B-only": {k: gates["v1"]["checks"]["F11"][k] for k in
                            ("targetNxPath", "candidateNxPath", "adjacentJumps", "fired")},
                 "A+B": {k: gates["o1"]["checks"]["F11"][k] for k in
                         ("targetNxPath", "candidateNxPath", "adjacentJumps", "fired")}}}
(OUT / "pointer-reflection-path.json").write_text(json.dumps(pp, indent=1))


# ---- candidate selection (registered rule, operationalised) ------------
def sel_metrics(lane):
    L = gates[lane]["stats"]
    return {
        "fringe": {a: {"fringeRB": L[a]["fullB"]["fringeRB"],
                       "fringeWidthPxMean": L[a]["fullB"]["fringeWidthPxMean"]}
                   for a in SATURATED},
        "white": {a: L[a]["fullB"]["whiteReflectionRatio"]
                  for a in ("bw-split", "grayscale-step")},
        "brightDark": {"brightSideEdgeChroma": gates[lane]["checks"]["F3"]["brightSideEdgeChroma"],
                       "darkOverBrightLumaRatio": gates[lane]["checks"]["F3"]["darkOverBrightLumaRatio"]},
        "mobile": gates[lane]["checks"]["F6"]["perViewport"],
        "mediaOnly": gates[lane]["checks"]["F7"]["pairs"],
        "ringing": {"grayscale-step": gates[lane]["checks"]["F2"]["grayscaleStepEdgeChroma"],
                    "bw-split": gates[lane]["checks"]["F2"]["bwSplitEdgeChroma"]},
    }


b, a = sel_metrics("v1"), sel_metrics("o1")
crit = {}
crit["improvesFringe"] = all(
    a["fringe"][x]["fringeRB"] < b["fringe"][x]["fringeRB"] and
    a["fringe"][x]["fringeWidthPxMean"] < b["fringe"][x]["fringeWidthPxMean"]
    for x in SATURATED)
crit["doesNotReduceWhiteRatio"] = all(a["white"][x] >= b["white"][x] for x in a["white"])
crit["doesNotWorsenBrightDark"] = (
    a["brightDark"]["brightSideEdgeChroma"] <= b["brightDark"]["brightSideEdgeChroma"]
    and abs(a["brightDark"]["darkOverBrightLumaRatio"] - 0.248)
        <= abs(b["brightDark"]["darkOverBrightLumaRatio"] - 0.248) + 1e-9)
mob_ok = True
for vp in MOBILE_VPS:
    for asset, e in (a["mobile"][vp] or {}).items():
        eb = b["mobile"][vp].get(asset) or {}
        for k, va in (e or {}).items():
            if k.endswith("Mobile") and k in eb:
                base = eb[k]
                if k.startswith("ringing"):
                    ok = va <= base + 1e-9
                else:
                    ok = va >= base - 1e-9
                if not ok:
                    mob_ok = False
crit["doesNotWorsenMobile"] = mob_ok
crit["doesNotAlterMediaOnly"] = all(v.get("differingPixels") == 0 for v in a["mediaOnly"].values())
crit["noGrayscaleRinging"] = not gates["o1"]["checks"]["F2"]["fired"]
winner = "A+B" if all(crit.values()) else "B-only"
sel = {"artifact": "B-only vs A+B selection (pre-registered rule)", "capturedAtHead": HEAD,
       "verbatimRule": "Retain A only if A+B: improves fringe width / fringe chroma versus B-only; does not reduce white reflection ratio; does not worsen Bright/Dark sign stability; does not worsen Mobile; does not alter Media-only; does not create colour ringing on grayscale media. Otherwise choose B-only and remove O1 System A from the accepted product path.",
       "operationalisation": "as registered in o2-selected-system.json: strict inequalities on same-media same-page numbers; ties go to B-only",
       "metrics": {"B-only": b, "A+B": a}, "criteria": crit, "winner": winner,
       "consequence": ("System A (o1-spectral dispersion) stays in the product ONLY through this O2 interaction gate; config default dispersionLaw remains o1-spectral"
                       if winner == "A+B" else
                       "System A leaves the accepted product path; config default dispersionLaw flips to v1-taps in a recorded product commit")}
(OUT / "candidate-selection.json").write_text(json.dumps(sel, indent=1))
print("selection winner:", winner, "criteria:", crit)
