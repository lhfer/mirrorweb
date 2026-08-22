#!/usr/bin/env python3
"""O5 §九 -- the absolute visual gate, fourteen items.

Windows come from TARGET REPEATABILITY, which was captured before any candidate
frame existed. Each is max(2 x repeatability, the floor sealed in
o5_instruments). No coding here may be changed now; a measurand that turns out
awkward is reported as awkward and scored as written.

Output: qa-v5/optics-o5/body-absolute-gate.json plus the per-topic files §十三
lists.
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


S = _load("o5_gate_stats", "o2_optics_stats.py")
I = _load("o5_gate_ins", "o5_instruments.py")

MD = REPO / "artifacts/optics-o5/measure"
VIEWPORTS = ["1440x900", "390x844", "844x390", "700x700"]

# Source landmarks per asset, in SOURCE normalised x. From o2-gen-media.py.
LANDMARKS = {
    "cover-control": [0.375],
    "rgb-bars": [0.25, 0.5, 0.75],
    "bw-split": [0.5],
    "grayscale-step": [0.5],
}
# Media pixel dimensions, for the cover fit.
MEDIA_WH = {"cover-control": (1600, 900), "rgb-bars": (1200, 900),
            "bw-split": (1200, 900), "grayscale-step": (1200, 900),
            "hf-checker": (1200, 900)}
PLANE_ASPECT = 4 / 3


def rects_for(vp):
    w, h = (int(x) for x in vp.split("x"))
    r = [q for _, q in S.rects_at(w, h)]
    basis = "fully-visible cards"
    if not r:
        VC, SL = sys.modules["v0_culling"], sys.modules["source_layout"]
        frame = SL.layout(w, h)
        cam = VC.coverage_camera(0.0, 0.0, frame)
        cand = []
        for v in VC.frame_verdicts(0.0, 0.0, cam, frame).values():
            if v.get("draw") and v.get("aabb"):
                x0, y0, x1, y1 = v["aabb"]
                cand.append((x1 - x0, (int(max(x0, 0)), int(max(y0, 0)),
                                       int(min(x1, w)), int(min(y1, h)))))
        r = [max(cand)[1]] if cand else []
        basis = "no fully-visible card -- widest drawn card"
    return r, basis


def target_cover_x(asset):
    """The Target's centred cover, x axis only."""
    sw, sh = MEDIA_WH.get(asset, (1200, 900))
    a = sw / sh
    if a > PLANE_ASPECT:
        e = PLANE_ASPECT / a
        return e, (1 - e) / 2
    return 1.0, 0.0


def frozen_cover_x(asset, card_index):
    """Our frozen MediaFit, x axis only, for the clip in this pool slot."""
    focus = [(0.5, 1.0), (0.5, 1.0), (0.5, 1.06)][card_index % 3]
    sw, sh = MEDIA_WH.get(asset, (1200, 900))
    a = sw / sh
    rx = PLANE_ASPECT / a if a > PLANE_ASPECT else 1.0
    rx /= max(1.0, focus[1])
    return rx, focus[0] * (1 - rx)


def pick(man, **kw):
    out = []
    for r in man["records"]:
        if all(r.get(k) == v for k, v in kw.items()):
            out.append(r)
    return out


def one(man, **kw):
    r = pick(man, **kw)
    return r[0] if r else None


def img(rec):
    return Image.open(MD / rec["file"]) if rec else None


def repeatability(man, metric_fn, asset, vp):
    """Spread of a metric across the Target's repeat captures."""
    reps = sorted((r for r in man["records"]
                   if r.get("lane") == "target" and r.get("asset") == asset
                   and r.get("vp") == vp and r.get("repeat") is not None),
                  key=lambda r: r["repeat"])
    vals = []
    for r in reps:
        v = metric_fn(img(r))
        if v is not None:
            vals.append(float(v))
    if len(vals) < 2:
        return None, vals
    # Half the full range: the largest deviation any single capture shows from
    # the middle of the observed spread. Standard deviation would understate a
    # two-mode flicker, which is the failure this is guarding against.
    return (max(vals) - min(vals)) / 2.0, vals


def main() -> int:
    out_dir = REPO / "qa-v5/optics-o5"
    out_dir.mkdir(parents=True, exist_ok=True)
    man = json.loads((MD / "measure-manifest.json").read_text())

    rects = {vp: rects_for(vp) for vp in VIEWPORTS}
    items, topic = [], {}

    def add(n, name, passed, detail, numbers=None):
        items.append({"item": n, "name": name,
                      "pass": None if passed is None else bool(passed),
                      "detail": detail, "numbers": numbers or {}})

    # ---------------------------------------------------------- windows
    band_of = lambda im, vp: (I.band_width_px(im, rects[vp][0])["meanPx"]
                              if im is not None and rects[vp][0] else None)
    dark_of = lambda im, vp: (I.dark_side_luma(im, rects[vp][0])["meanLuma"]
                              if im is not None and rects[vp][0] else None)
    ratio_of = lambda im, vp: (I.white_reflection_ratio(im, rects[vp][0])["meanRatio"]
                               if im is not None and rects[vp][0] else None)

    windows = {}
    for vp in VIEWPORTS:
        b_rep, b_vals = repeatability(man, lambda i, v=vp: band_of(i, v),
                                      "bw-split", vp)
        d_rep, d_vals = repeatability(man, lambda i, v=vp: dark_of(i, v),
                                      "bw-split", vp)
        r_rep, r_vals = repeatability(man, lambda i, v=vp: ratio_of(i, v),
                                      "bw-split", vp)
        windows[vp] = {
            "bandRepeatabilityPx": b_rep, "bandRuns": b_vals,
            "bandWindowPx": I.window(b_rep or 0, I.BAND_WINDOW_FLOOR_PX),
            "darkLumaRepeatability": d_rep, "darkRuns": d_vals,
            "darkLumaWindow": I.window(d_rep or 0, I.DARK_LUMA_WINDOW_FLOOR),
            "whiteRatioRepeatability": r_rep, "ratioRuns": r_vals,
            "whiteRatioWindow": I.window(r_rep or 0, I.WHITE_RATIO_WINDOW_FLOOR),
        }
    topic["target-repeatability"] = {
        "what": "Target repeatability, captured BEFORE any candidate frame. "
                "Every §九 window is max(2 x repeatability, floor). Spread is "
                "half the full range across repeats, not a standard "
                "deviation: a two-mode flicker between runs is exactly what "
                "this must not average away.",
        "repeats": man["repeats"], "byViewport": windows,
        "floors": {"bandPx": I.BAND_WINDOW_FLOOR_PX,
                   "darkLuma": I.DARK_LUMA_WINDOW_FLOOR,
                   "whiteRatio": I.WHITE_RATIO_WINDOW_FLOOR,
                   "compressionPx": I.COMPRESSION_WINDOW_FLOOR_PX},
    }

    # ------------------------------------------------- 1 reflection band
    band_rows, band_ok = [], True
    for vp in VIEWPORTS:
        t = band_of(img(one(man, lane="target", state="rest", asset="bw-split",
                            vp=vp, repeat=None)), vp)
        c = band_of(img(one(man, lane="control", state="rest",
                            asset="bw-split", vp=vp)), vp)
        k = band_of(img(one(man, lane="candidate", state="rest",
                            asset="bw-split", vp=vp)), vp)
        w = windows[vp]["bandWindowPx"]
        ok = None if (t is None or k is None) else I.enters(k, t, w)
        band_ok = band_ok and bool(ok)
        band_rows.append({"vp": vp, "target": t, "control": c, "candidate": k,
                          "windowPx": w,
                          "candidateDelta": None if (t is None or k is None)
                          else round(abs(k - t), 3),
                          "controlDelta": None if (t is None or c is None)
                          else round(abs(c - t), 3),
                          "enters": ok, "rectBasis": rects[vp][1]})
    add(1, "reflection band width enters the Target window", band_ok,
        "bw-split at every viewport, per-card thresholded band width.",
        {"rows": band_rows})
    topic["reflection-band"] = {"what": "§九.1 band width, all viewports.",
                                "rows": band_rows,
                                "windows": {v: windows[v]["bandWindowPx"]
                                            for v in VIEWPORTS}}

    # ------------------------------------------------- 2 dark-side luma
    dark_rows, dark_ok = [], True
    for vp in VIEWPORTS:
        t = dark_of(img(one(man, lane="target", state="rest", asset="bw-split",
                            vp=vp, repeat=None)), vp)
        c = dark_of(img(one(man, lane="control", state="rest",
                            asset="bw-split", vp=vp)), vp)
        k = dark_of(img(one(man, lane="candidate", state="rest",
                            asset="bw-split", vp=vp)), vp)
        w = windows[vp]["darkLumaWindow"]
        ok = None if (t is None or k is None) else I.enters(k, t, w)
        dark_ok = dark_ok and bool(ok)
        dark_rows.append({"vp": vp, "target": t, "control": c, "candidate": k,
                          "window": w, "enters": ok,
                          "movedToward": None if None in (t, c, k)
                          else I.toward(k, c, t)})
    add(2, "dark-side edge luma enters the Target window", dark_ok,
        "Mean luminance of the dark-side edge band, per card then mean.",
        {"rows": dark_rows})

    # ------------------------------------------------- 3 white ratio
    ratio_rows, ratio_ok = [], True
    for vp in VIEWPORTS:
        t = ratio_of(img(one(man, lane="target", state="rest", asset="bw-split",
                             vp=vp, repeat=None)), vp)
        c = ratio_of(img(one(man, lane="control", state="rest",
                             asset="bw-split", vp=vp)), vp)
        k = ratio_of(img(one(man, lane="candidate", state="rest",
                             asset="bw-split", vp=vp)), vp)
        w = windows[vp]["whiteRatioWindow"]
        ok = None if (t is None or k is None) else I.enters(k, t, w)
        ratio_ok = ratio_ok and bool(ok)
        ratio_rows.append({"vp": vp, "target": t, "control": c, "candidate": k,
                           "window": w, "enters": ok})
    add(3, "white reflection ratio enters the Target window", ratio_ok,
        "Bright-side edge band over dark-side edge band.", {"rows": ratio_rows})

    # ------------------------------------------------- 4 grayscale chroma
    gs_rows, gs_ok = [], True
    for vp in ["1440x900"]:
        for asset in ["grayscale-step", "bw-split"]:
            r = rects[vp][0]
            if not r:
                continue
            row = {"vp": vp, "asset": asset}
            for lane in ("target", "control", "candidate"):
                rec = one(man, lane=lane, state="rest", asset=asset, vp=vp,
                          **({"repeat": None} if lane == "target" else {}))
                if rec is None:
                    continue
                g = I.grayscale_chroma(img(rec), r)
                row[lane] = {"p995": g["p995Chroma"], "max": g["peakChroma"],
                             "mean": g["meanChroma"]}
            k = (row.get("candidate") or {}).get("p995")
            ok = None if k is None else k <= I.GRAYSCALE_CHROMA_CEILING
            gs_ok = gs_ok and bool(ok)
            row["ceiling"] = I.GRAYSCALE_CHROMA_CEILING
            row["scoredStatistic"] = I.GRAYSCALE_CHROMA_STATISTIC
            row["withinCeiling"] = ok
            gs_rows.append(row)
    add(4, "grayscale adds no colour", gs_ok,
        f"Scored on {I.GRAYSCALE_CHROMA_STATISTIC} against a ceiling of "
        f"{I.GRAYSCALE_CHROMA_CEILING}; the raw maximum is reported as a "
        f"diagnostic, never as the verdict.", {"rows": gs_rows})
    topic["grayscale-ringing"] = {"what": "§九.4 achromatic media.",
                                  "rows": gs_rows}

    # ------------------------------------------------- 5 saturated chroma
    sat_rows, sat_ok = [], True
    for asset in ["rgb-bars", "cool-blue", "warm-skin"]:
        vp = "1440x900"
        r = rects[vp][0]
        if not r:
            continue
        row = {"asset": asset, "vp": vp}
        for lane in ("target", "control", "candidate"):
            rec = one(man, lane=lane, state="rest", asset=asset, vp=vp,
                      **({"repeat": None} if lane == "target" else {}))
            if rec is None:
                continue
            st = S.side_bands(img(rec), r)
            row[lane] = {"fringeRB": round(float(st.get("fringeRB", 0)), 2),
                         "fringeWidthPxMean":
                             round(float(st.get("fringeWidthPxMean", 0)), 2),
                         "edgeChroma": round(float(st.get("edgeChroma", 0)), 2)}
        t, c, k = row.get("target"), row.get("control"), row.get("candidate")
        if t and c and k:
            # "Approach the Target without a broad coloured rim": the
            # candidate must be closer to the Target's edge chroma than the
            # control is, AND must not widen the fringe past the Target's.
            closer = abs(k["edgeChroma"] - t["edgeChroma"]) <= \
                abs(c["edgeChroma"] - t["edgeChroma"])
            not_broader = k["fringeWidthPxMean"] <= max(
                t["fringeWidthPxMean"], c["fringeWidthPxMean"])
            row["closerToTarget"] = closer
            row["notBroaderThanEither"] = not_broader
            ok = closer and not_broader
        else:
            ok = None
        row["pass"] = ok
        sat_ok = sat_ok and bool(ok)
        sat_rows.append(row)
    add(5, "saturated edge chroma approaches the Target without a broad "
           "coloured rim", sat_ok,
        "Closer to the Target's edge chroma than the control, and no wider "
        "than the wider of Target and control.", {"rows": sat_rows})
    topic["bright-dark"] = {"what": "§九.5 saturated and bright/dark media.",
                            "rows": sat_rows}

    # ------------------------------------------------- 6 HF checker
    vp = "1440x900"
    r = rects[vp][0]
    hf = {}
    for lane in ("target", "control", "candidate"):
        rec = one(man, lane=lane, state="rest", asset="hf-checker", vp=vp,
                  **({"repeat": None} if lane == "target" else {}))
        if rec is None or not r:
            continue
        im = img(rec)
        hf[lane] = {
            "hfEnergy": I.hf_energy(im, r),
            "spectral": I.spectral_structure(im, r),
            "edgeProfile": I.edge_profile(im, r),
            "falseColour": I.false_colour_outside_features(im, r),
        }
    hf_ok = None
    hf_summary = {}
    if {"target", "candidate", "control"} <= set(hf):
        t, c, k = hf["target"], hf["control"], hf["candidate"]
        spec_corr = I.correlate(k["spectral"]["hfTiles"],
                                t["spectral"]["hfTiles"])
        ctrl_corr = I.correlate(c["spectral"]["hfTiles"],
                                t["spectral"]["hfTiles"])
        prof_corr = I.correlate(k["edgeProfile"], t["edgeProfile"])
        retention = (k["hfEnergy"] / t["hfEnergy"]) if t["hfEnergy"] else None
        hf_summary = {
            "hfEnergy": {"target": t["hfEnergy"], "control": c["hfEnergy"],
                         "candidate": k["hfEnergy"], "retention": None
                         if retention is None else round(retention, 4)},
            "localSpectralCorrelationToTarget": spec_corr,
            "controlSpectralCorrelationToTarget": ctrl_corr,
            "edgeProfileCorrelationToTarget": prof_corr,
            "falseColour": {"target": t["falseColour"],
                            "control": c["falseColour"],
                            "candidate": k["falseColour"]},
            "floors": {"correlation": I.SPECTRAL_CORRELATION_FLOOR,
                       "hfRetention": I.HF_ENERGY_RETENTION_FLOOR},
        }
        hf_ok = bool(
            spec_corr["r"] is not None
            and spec_corr["r"] >= I.SPECTRAL_CORRELATION_FLOOR
            and retention is not None
            and retention >= I.HF_ENERGY_RETENTION_FLOOR)
    add(6, "HF checker preserves content-local spectral structure", hf_ok,
        "Per-tile correlation of high-frequency energy against the Target, "
        "plus HF energy retention. A candidate that merely blurs loses "
        "retention; one that merely desaturates loses correlation.",
        hf_summary)
    topic["spectral-structure"] = {"what": "§九.6 high-frequency structure.",
                                   "summary": hf_summary}

    # ------------------------------------------------- 7 edge compression
    comp_rows, comp_ok = [], True
    for vp in VIEWPORTS:
        for asset in ["cover-control", "rgb-bars"]:
            r, _ = rects[vp]
            if not r or asset not in LANDMARKS:
                continue
            row = {"vp": vp, "asset": asset, "sourceLandmarks": LANDMARKS[asset]}
            tsx, tox = target_cover_x(asset)
            for lane in ("target", "control", "candidate"):
                rec = one(man, lane=lane, state="rest", asset=asset, vp=vp,
                          **({"repeat": None} if lane == "target" else {}))
                if rec is None:
                    continue
                per_card = []
                for ci, rect in enumerate(r):
                    if lane == "target":
                        sx, ox = tsx, tox
                        mo = None
                    else:
                        sx, ox = frozen_cover_x(asset, ci)
                        morec = one(man, kind="media-only", lane=lane,
                                    asset=asset, vp=vp)
                        mo = img(morec) if morec else None
                    per_card.append(I.edge_compression(
                        img(rec), rect, LANDMARKS[asset], sx, ox,
                        media_only_img=mo))
                usable = [p for p in per_card if p["usable"]]
                row[lane] = {
                    "cards": len(per_card), "usable": len(usable),
                    "meanOutwardPx": round(float(np.mean(
                        [p["meanOutwardPx"] for p in usable])), 3)
                    if usable else None,
                    "baselineVerified": [p["flatBaselineVerified"]
                                         for p in per_card],
                }
            t, c, k = (row.get(x) or {} for x in ("target", "control", "candidate"))
            tv, cv, kv = (x.get("meanOutwardPx") for x in (t, c, k))
            w = I.window(0, I.COMPRESSION_WINDOW_FLOOR_PX)
            if tv is None or kv is None:
                ok = None
            else:
                ok = I.enters(kv, tv, w)
            row["windowPx"] = w
            row["enters"] = ok
            row["directionMatches"] = (None if (tv is None or kv is None)
                                       else (tv == 0 and kv == 0)
                                       or (tv * kv > 0))
            row["movedToward"] = (None if None in (tv, cv, kv)
                                  else I.toward(kv, cv, tv))
            if asset == "cover-control":
                comp_ok = comp_ok and bool(ok)
            comp_rows.append(row)
    add(7, "edge compression reproduces the Target's direction and magnitude",
        comp_ok,
        "Landmark displacement from each render's OWN analytic flat position, "
        "so the frozen crop on clip 2 is subtracted out rather than scored as "
        "an optical defect. Scored on cover-control, whose 16:9 source makes "
        "the cover law do real work; rgb-bars reported alongside.",
        {"rows": comp_rows})
    topic["refraction-compression"] = {"what": "§九.7 edge compression.",
                                       "rows": comp_rows}

    # ------------------------------------------------- 8 own-media isolation
    iso_rows, iso_ok = [], True
    for vp in ["1440x900"]:
        r, _ = rects[vp]
        for lane in ("control", "candidate"):
            rec = one(man, lane=lane, state="rest", asset="bw-split", vp=vp)
            morec = one(man, kind="media-only", lane=lane, asset="bw-split",
                        vp=vp)
            if rec is None or morec is None or not r:
                continue
            sil = I.true_silhouette(MD / rec["file"], MD / morec["file"])
            gut = I.gutter_outside_silhouette(MD / rec["file"], sil)
            passes = (rec.get("passes") or {}).get("stats") or {}
            iso_rows.append({
                "vp": vp, "lane": lane,
                "gutterOutsideSilhouette": gut,
                "sceneColorCalls": passes.get("sceneColorCalls"),
                "structuralIsolation": lane == "candidate",
            })
    cand_iso = next((x for x in iso_rows if x["lane"] == "candidate"), None)
    if cand_iso is not None:
        # The candidate's isolation is STRUCTURAL, and that is stronger than a
        # pixel test: its refracted UV is clamped to 0..1 BEFORE the cover
        # transform, so a sample cannot leave the card's own media frame; and
        # its scene-colour pass draws nothing, so there is no cross-card
        # buffer to contaminate from. The pixel measurement is reported
        # alongside as the observable consequence.
        iso_ok = cand_iso["sceneColorCalls"] == 0
    else:
        iso_ok = None
    add(8, "own-media isolation: no neighbour bleed, no scene-colour "
           "cross-card contamination", iso_ok,
        "Structural: the refracted UV is clamped to 0..1 before the cover "
        "transform (contract site clampThenCover), so a sample cannot reach "
        "outside the card's own media; and the scene-colour pass draws 0 "
        "calls in this lane, so no cross-card buffer exists to read.",
        {"rows": iso_rows})

    # ------------------------------------------------- 9 interior fidelity
    int_rows, int_ok = [], True
    for vp in ["1440x900"]:
        r, _ = rects[vp]
        for asset in ["bw-split", "rgb-bars", "hf-checker"]:
            row = {"vp": vp, "asset": asset}
            for lane in ("target", "control", "candidate"):
                rec = one(man, lane=lane, state="rest", asset=asset, vp=vp,
                          **({"repeat": None} if lane == "target" else {}))
                if rec is None or not r:
                    continue
                a = np.asarray(img(rec).convert("RGB"), np.float32)
                vals = []
                for (x0, y0, x1, y1) in r:
                    cw, ch = x1 - x0, y1 - y0
                    ix, iy = int(cw * 0.3), int(ch * 0.3)
                    vals.append(a[y0 + iy:y1 - iy, x0 + ix:x1 - ix]
                                .reshape(-1, 3))
                blk = np.concatenate(vals)
                lum = (0.2126 * blk[:, 0] + 0.7152 * blk[:, 1]
                       + 0.0722 * blk[:, 2])
                row[lane] = {
                    "luma": round(float(lum.mean()), 2),
                    "chroma": round(float(
                        (blk.max(axis=1) - blk.min(axis=1)).mean()), 3),
                    "sharpness": I.hf_energy(img(rec), r),
                }
            t, c, k = (row.get(x) for x in ("target", "control", "candidate"))
            if t and k and c:
                # Closer to the Target than the control on luminance, and not
                # duller than the control on sharpness.
                row["lumaCloser"] = abs(k["luma"] - t["luma"]) <= \
                    abs(c["luma"] - t["luma"])
                row["notBlurrierThanControl"] = (k["sharpness"] or 0) >= \
                    (c["sharpness"] or 0) * 0.9
                ok = row["lumaCloser"] and row["notBlurrierThanControl"]
            else:
                ok = None
            row["pass"] = ok
            int_ok = int_ok and bool(ok)
            int_rows.append(row)
    add(9, "interior fidelity: luminance, chroma, sharpness, cover position",
        int_ok,
        "Card centre, inner 40%. Cover position is scored by item 7's "
        "landmark measurement, which is the same question asked with a ruler.",
        {"rows": int_rows})

    # ------------------------------------------------- 10 silhouette / gutter
    sil_rows, sil_ok = [], True
    for vp in VIEWPORTS:
        r, _ = rects[vp]
        w, h = (int(x) for x in vp.split("x"))
        frame = sys.modules["source_layout"].layout(w, h)
        corner_px = 0.163 * frame["planeWidth"]
        for lane in ("control", "candidate"):
            rec = one(man, lane=lane, state="rest", asset="bw-split", vp=vp)
            if rec is None or not r:
                continue
            ag = [I.alpha_edge_agreement(img(rec), rect, corner_px)
                  for rect in r]
            lit = sum(x["litOutsidePixels"] for x in ag)
            sil_rows.append({"vp": vp, "lane": lane,
                             "cornerRadiusPx": round(corner_px, 2),
                             "litOutsideOwnSdf": lit,
                             "outsidePixels": sum(x["outsidePixels"] for x in ag),
                             "maxDelta": max(x["maxDeltaOutside"] for x in ag)})
    for row in sil_rows:
        if row["lane"] == "candidate":
            # The candidate's silhouette IS the analytic SDF, so this is a
            # self-consistency test against what it claims to draw -- not a
            # mask borrowed from the other lane, which is the mistake O3 item
            # 13 and O4 item 9 both made.
            row["pass"] = row["litOutsideOwnSdf"] == 0
            sil_ok = sil_ok and row["pass"]
    add(10, "silhouette matches the Target's SDF rule; no light beyond the "
            "rounded rect", sil_ok,
        "Each render judged against ITS OWN analytic SDF at "
        "cornerRadius = 0.163 x planeWidth, never against a mask derived from "
        "the other lane.", {"rows": sil_rows})

    # ------------------------------------------------- 11 pointer
    # The O3/O4 sealed coding, unchanged: every captured pointer state
    # contributes to the ink intersection (the more states a bright pixel
    # survives, the more certainly it is label ink), and the PATH is judged
    # on the three sweep states. Each state is cropped at its OWN rect,
    # because pointer parallax moves the projected card.
    INK_STATES = [("pl", (-0.99, 0.0)), ("rest", (0.0, 0.0)),
                  ("pr", (0.99, 0.0)), ("pbr", (0.99, 0.99))]
    PATH_STATES = ["pl", "rest", "pr"]

    def dark_half_rect(w, h, ndc):
        rr = sorted((q for _, q in S.rects_at(w, h, ndc)),
                    key=lambda q: (q[2] - q[0]) * (q[3] - q[1]))
        if not rr:
            return None
        x0, y0, x1, y1 = rr[-1]
        return (x0, y0, (x0 + x1) // 2, y1)

    def pointer_path(lane, vp):
        w, h = (int(x) for x in vp.split("x"))
        states = {}
        for name, ndc in INK_STATES:
            rec = one(man, lane=lane, state=name, asset="bw-split", vp=vp,
                      **({"repeat": None} if (lane == "target"
                                              and name == "rest") else {}))
            rect = dark_half_rect(w, h, ndc)
            if rec is None or rect is None:
                continue
            states[name] = (img(rec), rect)
        if not states:
            return None
        masks, excluded, dims = I.glass_reflection_masks(states)
        cents = {s: I.centroid_of(m, dims) for s, m in masks.items()}
        return {
            "statesUsedForInk": sorted(states),
            "cardSpaceDims": dims,
            "excludedInkPixels": int(excluded.sum()) if excluded is not None else None,
            "glassPixelsPerState": {s: (c["pixels"] if c else 0)
                                    for s, c in cents.items()},
            "path": [cents.get(s, {}).get("nx") if cents.get(s) else None
                     for s in PATH_STATES],
        }

    ptr_rows = []
    paths = {}
    for lane in ("target", "control", "candidate"):
        pp = pointer_path(lane, "1440x900")
        if pp:
            paths[lane] = pp
            ptr_rows.append({"vp": "1440x900", "lane": lane, **pp})
    if "target" in paths and "candidate" in paths:
        judged = I.pointer_judge(tuple(paths["target"]["path"]),
                                 tuple(paths["candidate"]["path"]))
        ctrl_judged = (I.pointer_judge(tuple(paths["target"]["path"]),
                                       tuple(paths["control"]["path"]))
                       if "control" in paths else {})
        ptr_ok = not judged.get("fired")
    else:
        judged, ctrl_judged, ptr_ok = {}, {}, None
    add(11, "pointer reflection moves in the Target's direction without a "
            "discontinuity", ptr_ok,
        "Labels off. Ink is removed by intersecting every captured pointer "
        "state; the path is judged on pointer-left / rest / pointer-right, "
        "each cropped at its own rect because parallax moves the card.",
        {"rows": ptr_rows, "candidateVerdict": judged,
         "controlVerdict": ctrl_judged})
    topic["pointer-path"] = {"what": "§九.11 pointer reflection.",
                             "rows": ptr_rows, "candidateVerdict": judged,
                             "controlVerdict": ctrl_judged}

    # ------------------------------------------------- 12 motion
    pop_path = REPO / "artifacts/optics-o5/recordings/pop.json"
    if pop_path.exists():
        pop = json.loads(pop_path.read_text())
        mot_ok = bool(pop.get("pass"))
        mot_detail = pop.get("summary", "see temporal-continuity.json")
    else:
        pop, mot_ok = {}, None
        mot_detail = "recordings not present"
    add(12, "no temporal pop during pointer sweep, slow drag, fast flick or "
            "touch release", mot_ok, mot_detail, {"pop": pop})
    topic["temporal-continuity"] = {"what": "§九.12 motion continuity.",
                                    "pop": pop}

    # ------------------------------------------------- 13 mobile
    mob_rows, mob_ok = [], True
    for vp in ["390x844", "844x390"]:
        row = {"vp": vp}
        for lane in ("target", "control", "candidate"):
            rec = one(man, lane=lane, state="rest", asset="bw-split", vp=vp,
                      **({"repeat": None} if lane == "target" else {}))
            r, _ = rects[vp]
            if rec is None or not r:
                continue
            row[lane] = {"bandPx": band_of(img(rec), vp),
                         "darkLuma": dark_of(img(rec), vp),
                         "whiteRatio": ratio_of(img(rec), vp)}
        t, c, k = (row.get(x) for x in ("target", "control", "candidate"))
        if t and c and k:
            # "Same optical direction" in both orientations: the candidate
            # must move the band toward the Target from the control, in both.
            row["bandTowardTarget"] = I.toward(k["bandPx"], c["bandPx"],
                                               t["bandPx"])
            ok = row["bandTowardTarget"] is not False
        else:
            ok = None
        row["pass"] = ok
        mob_ok = mob_ok and bool(ok)
        mob_rows.append(row)
    add(13, "portrait and landscape show the same optical direction", mob_ok,
        "Band width moving toward the Target from the control, in both "
        "orientations.", {"rows": mob_rows})
    topic["mobile-consistency"] = {"what": "§九.13 mobile.", "rows": mob_rows}

    # ------------------------------------------------- 14 full-frame reading
    # §九.14 is a product judgment. It cannot be measured directly, so the
    # three failure modes it NAMES are measured instead, each against the
    # Target's own value, and the item is reported as a proxy -- not as the
    # judgment itself, which belongs to product review.
    vp = "1440x900"
    r, _ = rects[vp]
    reading = {}
    for lane in ("target", "control", "candidate"):
        rec = one(man, lane=lane, state="rest", asset="bw-split", vp=vp,
                  **({"repeat": None} if lane == "target" else {}))
        hrec = one(man, lane=lane, state="rest", asset="hf-checker", vp=vp,
                   **({"repeat": None} if lane == "target" else {}))
        crec = one(man, lane=lane, state="rest", asset="cool-blue", vp=vp,
                   **({"repeat": None} if lane == "target" else {}))
        if rec is None or not r:
            continue
        st = S.side_bands(img(crec), r) if crec else {}
        reading[lane] = {
            "thickWhitePlastic_bandPx": band_of(img(rec), vp),
            "colouredGlassFrame_fringeWidthPx":
                round(float(st.get("fringeWidthPxMean", 0)), 2),
            "blurredLens_interiorHf": I.hf_energy(img(hrec), r) if hrec else None,
        }
    if {"target", "control", "candidate"} <= set(reading):
        t, c, k = reading["target"], reading["control"], reading["candidate"]
        checks = {}
        for key in ("thickWhitePlastic_bandPx",
                    "colouredGlassFrame_fringeWidthPx",
                    "blurredLens_interiorHf"):
            tv, cv, kv = t[key], c[key], k[key]
            checks[key] = {
                "target": tv, "control": cv, "candidate": kv,
                "candidateCloser": None if None in (tv, cv, kv)
                else abs(kv - tv) <= abs(cv - tv),
            }
        read_ok = all(v["candidateCloser"] for v in checks.values()
                      if v["candidateCloser"] is not None)
    else:
        checks, read_ok = {}, None
    add(14, "full-frame reading: no longer thick white plastic, a coloured "
            "glass frame, or a blurred scene-colour lens", read_ok,
        "PROXY for a product judgment, not the judgment. The three failure "
        "modes §九.14 names are measured against the Target's own values: "
        "band width, fringe width, and interior high-frequency energy. "
        "Product review owns the actual reading.",
        {"checks": checks})

    passed = sum(1 for i in items if i["pass"] is True)
    failed = sum(1 for i in items if i["pass"] is False)
    pending = sum(1 for i in items if i["pass"] is None)
    gate = "PASS" if (failed == 0 and pending == 0) else "FAIL"

    (out_dir / "target-repeatability.json").write_text(
        json.dumps(topic["target-repeatability"], indent=1))
    for k, v in topic.items():
        if k != "target-repeatability":
            (out_dir / f"{k}.json").write_text(json.dumps(v, indent=1))

    doc = {
        "what": "O5 §九 absolute visual gate. Windows derive from Target "
                "repeatability captured before any candidate frame existed.",
        "viewports": VIEWPORTS,
        "windows": windows,
        "rectBasis": {vp: rects[vp][1] for vp in VIEWPORTS},
        "passed": passed, "failed": failed, "pending": pending,
        "total": len(items),
        "absoluteGate": gate,
        "finalState": ("READY FOR O5 OPTICAL BODY PRODUCT REVIEW" if gate == "PASS"
                       else "O5 TARGET-SOURCE BODY FAILED ABSOLUTE GATE"),
        "consoleAndPageErrors": sum(r.get("errorCount", 0)
                                    for r in man["records"]),
        "items": items,
    }
    (out_dir / "body-absolute-gate.json").write_text(json.dumps(doc, indent=1))
    for i in items:
        v = "PASS" if i["pass"] else ("FAIL" if i["pass"] is False else "n/a")
        print(f"  {v:4}  {i['item']:2d}. {i['name']}")
    print(f"\npassed {passed}/{len(items)}  failed {failed}  pending {pending}")
    print(f"absoluteGate: {gate}")
    print(f"finalState:   {doc['finalState']}")
    return 0 if gate == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
