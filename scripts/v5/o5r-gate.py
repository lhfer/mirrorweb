#!/usr/bin/env python3
"""§十三B -- the corrected O5R product gate.

Fourteen product systems, each classified PASS / FAIL / NOT_APPLICABLE /
INSTRUMENT_UNREADABLE. An unreadable row is never converted into a pass, and
never into a failure either. A row where every lane returns the same constant
is unreadable by construction, because that is what made two of O5's eight
passes worthless.

Four lanes are read:

  target            the live site on the deterministic shared media
  control           opticalBody=current, the accepted O2 body
  o5-clamped        the SEALED O5 candidate, shown for continuity
  o5r-unclamped     the O5R candidate -- the one being scored

Windows come from Target repeatability, three runs per asset per viewport,
captured before the O5R candidate lane existed.

Output: qa-v5/optics-o5r/corrected-product-gate.json plus the per-topic files
§十五 lists.
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


S = _load("o5r_g_stats", "o2_optics_stats.py")
I5 = _load("o5r_g_o5ins", "o5_instruments.py")
I = _load("o5r_g_ins", "o5r_instruments.py")
F = _load("o5r_g_refr", "o5r_refraction.py")

MD = REPO / "artifacts/optics-o5r/measure"
OUT = REPO / "qa-v5/optics-o5r"
VIEWPORTS = ["1440x900", "390x844", "844x390", "700x700"]
LANES = ["target", "control", "o5-clamped", "o5r-unclamped"]
CANDIDATE = "o5r-unclamped"
P0 = "390x844"

GRAYSCALE_ASSETS = ["grayscale-step", "bw-split", "hf-checker"]
SATURATED_ASSETS = ["rgb-bars", "cool-blue", "warm-skin"]
TEXTURED_ASSETS = ["hf-checker", "rgb-micro", "detail-chart"]
FLAT_ASSETS = ["bw-split", "grayscale-step", "rgb-bars"]
FULLFRAME_ASSETS = ["bw-split", "grayscale-step", "hf-checker", "dark-highlight",
                    "bright-lowsat", "cool-blue", "warm-skin"]

MAN = json.loads((MD / "measure-manifest.json").read_text())
MEDIA = json.loads(
    (REPO / "artifacts/optics-o5r/media/media-manifest.json").read_text())
DISCS = F.scored_discs(MEDIA)


# ---------------------------------------------------------------- plumbing

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


RECTS = {vp: rects_for(vp) for vp in VIEWPORTS}


def find(**kw):
    return [r for r in MAN["records"]
            if all(r.get(k) == v for k, v in kw.items())]


def shot(lane, asset, vp, state="rest", repeat=None):
    if lane == "target":
        rows = find(kind="target", asset=asset, vp=vp, state=state)
        rows = [r for r in rows if r.get("repeat") == repeat]
    else:
        rows = find(kind="lane", lane=lane, asset=asset, vp=vp, state=state)
    for r in rows:
        p = MD / r["file"]
        if p.exists():
            return p
    return None


def target_repeats(asset, vp):
    rows = [r for r in find(kind="target", asset=asset, vp=vp, state="rest")
            if r.get("repeat") is not None]
    return [MD / r["file"] for r in sorted(rows, key=lambda r: r["repeat"])
            if (MD / r["file"]).exists()]


def repeatability(values):
    """Half the full range across repeats -- O5's coding, carried."""
    vs = [v for v in values if v is not None]
    if len(vs) < 2:
        return None
    return (max(vs) - min(vs)) / 2.0


def _json_default(o):
    """numpy scalars are not JSON, and silently dropping them is worse.

    Comparisons against numpy floats yield numpy bools, which the encoder
    refuses. Converting here keeps every measured value in the record rather
    than making the gate choose between crashing and omitting.
    """
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def open_img(path):
    """The carried O5 instruments take an Image, not a path."""
    return Image.open(path) if path is not None else None


ITEMS = []
TOPIC = {}


def add(n, name, status, detail, numbers=None):
    # rowCounts is not decoration. An item whose status reads PASS off one
    # readable row and three unreadable ones is a different thing from one that
    # passed everywhere, and a reader should not have to open the numbers to
    # find that out.
    rows = (numbers or {}).get("rows")
    counts = None
    if isinstance(rows, list) and rows and isinstance(rows[0], dict) \
            and "status" in rows[0]:
        counts = {}
        for r in rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
    ITEMS.append({"item": n, "name": name, "status": status,
                  "rowCounts": counts,
                  "detail": detail, "numbers": numbers or {}})


def classify(rows, key="status"):
    """A whole item's status from its per-row statuses.

    FAIL wins over UNREADABLE wins over PASS, and an item with no readable row
    at all is UNREADABLE rather than a vacuous pass.
    """
    st = [r[key] for r in rows]
    if not st:
        return I.UNREADABLE
    if any(s == "FAIL" for s in st):
        return "FAIL"
    readable = [s for s in st if s not in (I.UNREADABLE, I.NOT_APPLICABLE)]
    if not readable:
        return I.UNREADABLE if I.UNREADABLE in st else I.NOT_APPLICABLE
    return "PASS"


# ============================================== 1-3 the carried edge metrics

def edge_metric(fn, floor, item_no, name, detail, key):
    rows = []
    for vp in VIEWPORTS:
        rects = RECTS[vp][0]
        if not rects:
            rows.append({"vp": vp, "status": I.UNREADABLE,
                         "why": "no card rect for this viewport"})
            continue
        runs = [fn(p, rects) for p in target_repeats("bw-split", vp)]
        rep = repeatability(runs)
        if rep is None:
            rows.append({"vp": vp, "status": I.UNREADABLE,
                         "why": "fewer than two Target repeats"})
            continue
        win = I.window(rep, floor)
        vals = {}
        for lane in LANES:
            p = shot(lane, "bw-split", vp, repeat=0 if lane == "target" else None)
            vals[lane] = fn(p, rects) if p else None
        deg = I.degenerate_reading(f"{key} {vp}", vals)
        if deg:
            rows.append({"vp": vp, "status": I.UNREADABLE, **deg, **vals})
            continue
        t, k = vals["target"], vals[CANDIDATE]
        enters = abs(k - t) <= win
        rows.append({
            "vp": vp, "status": "PASS" if enters else "FAIL",
            **{lane: (round(v, 4) if v is not None else None)
               for lane, v in vals.items()},
            "targetRuns": [round(v, 4) for v in runs if v is not None],
            "repeatability": round(rep, 4), "window": round(win, 4),
            "candidateDelta": round(abs(k - t), 4),
            "movedTowardTarget": I5.toward(k, vals["control"], t),
        })
    st = classify(rows)
    add(item_no, name, st, detail, {"rows": rows})
    TOPIC[key] = {"what": detail, "rows": rows, "status": st}
    return rows


# ================================================= 4 grayscale / false colour

def item_grayscale():
    rows = []
    for vp in VIEWPORTS:
        rects = RECTS[vp][0]
        for asset in GRAYSCALE_ASSETS:
            if not rects or not shot("target", asset, vp, repeat=0):
                continue
            try:
                runs = [I.grayscale_v2(p, rects)
                        for p in target_repeats(asset, vp)]
            except I.Unreadable as e:
                rows.append({"vp": vp, "asset": asset, "status": I.UNREADABLE,
                             "why": str(e)})
                continue
            if len(runs) < 2:
                rows.append({"vp": vp, "asset": asset, "status": I.UNREADABLE,
                             "why": "fewer than two Target repeats"})
                continue
            t = runs[0]
            lanes = {"target": t}
            bad = None
            for lane in LANES[1:]:
                p = shot(lane, asset, vp)
                if p is None:
                    bad = f"no {lane} capture"
                    break
                lanes[lane] = I.grayscale_v2(p, rects)
            if bad:
                rows.append({"vp": vp, "asset": asset, "status": I.UNREADABLE,
                             "why": bad})
                continue

            # Windows, per statistic, from the Target's own repeats.
            wins, self_ok = {}, {}
            for stat in I.GRAYSCALE_DISTANCE_KEYS:
                rep = repeatability([r.get(stat) for r in runs])
                wins[stat] = I.window(rep or 0.0,
                                      I.CHROMA_DISTANCE_WINDOW_FLOOR)
                # §四: the instrument must make the TARGET pass its own window.
                worst = max(abs((r.get(stat) or 0) - (t.get(stat) or 0))
                            for r in runs)
                self_ok[stat] = worst <= wins[stat]
            area_rep = repeatability([r["falseColourAreaFraction"] for r in runs])
            area_win = I.window(area_rep or 0.0, I.FALSE_COLOUR_AREA_WINDOW_FLOOR)

            dist = {lane: I.grayscale_distance(v, t)
                    for lane, v in lanes.items() if lane != "target"}
            k = dist[CANDIDATE]
            within = {s: (k[s] is not None and k[s] <= wins[s])
                      for s in I.GRAYSCALE_DISTANCE_KEYS}
            area_ok = (k["falseColourAreaExcess"] is not None
                       and k["falseColourAreaExcess"] <= area_win)
            # Degeneracy: if the lanes are indistinguishable on the scored
            # statistic the row cannot discriminate.
            deg = I.degenerate_reading(
                f"grayscale p995 {asset} {vp}",
                {lane: v["p995Chroma"] for lane, v in lanes.items()})
            status = (I.UNREADABLE if deg
                      else "PASS" if (all(within.values()) and area_ok)
                      else "FAIL")
            rows.append({
                "vp": vp, "asset": asset, "status": status,
                "targetPassesItsOwnWindow": all(self_ok.values()),
                "lanes": {lane: {s: v.get(s) for s in
                                 (*I.GRAYSCALE_DISTANCE_KEYS,
                                  "falseColourAreaFraction",
                                  "falseColourBlobs",
                                  "falseColourDistanceFromFeaturesPx")}
                          for lane, v in lanes.items()},
                "distanceToTarget": dist,
                "windows": {**{s: round(w, 4) for s, w in wins.items()},
                            "falseColourAreaFraction": round(area_win, 6)},
                "within": within, "falseColourAreaWithin": area_ok,
                **({"why": deg["why"]} if deg else {}),
            })
    st = classify(rows)
    add(4, "grayscale / false colour: chroma distance to the Target, and no "
           "colour away from the Target's own features", st,
        "§四. The absolute ceiling of 6.0 is gone -- the Target reads 30 on "
        "that statistic. Every scored quantity is a DISTANCE TO THE TARGET "
        "inside a window derived from the Target's own repeats, and colour on "
        "encoded edges is separated from colour between them.",
        {"rows": rows})
    TOPIC["grayscale-v2"] = {"what": "§四 Target-relative achromatic behaviour.",
                             "rows": rows, "status": st}


# ==================================================== 5 saturated edge

def item_saturated_edge():
    rows = []
    for vp in VIEWPORTS:
        rects = RECTS[vp][0]
        for asset in SATURATED_ASSETS:
            if not rects or not shot("target", asset, vp, repeat=0):
                continue
            lanes, why = {}, None
            for lane in LANES:
                p = shot(lane, asset, vp, repeat=0 if lane == "target" else None)
                if p is None:
                    why = f"no {lane} capture"
                    break
                try:
                    lanes[lane] = I.saturated_edge_v2(p, rects, None)
                except I.Unreadable as e:
                    why = str(e)
                    break
            if why:
                rows.append({"vp": vp, "asset": asset, "status": I.UNREADABLE,
                             "why": why})
                continue
            runs = []
            for p in target_repeats(asset, vp):
                try:
                    runs.append(I.saturated_edge_v2(p, rects, None))
                except I.Unreadable:
                    pass
            t = lanes["target"]
            scored = ["chromaAtFeatures", "chromaAwayFromFeatures",
                      "broadRimColouredFraction"]
            wins, within, deg_why = {}, {}, None
            for s in scored:
                rep = repeatability([r.get(s) for r in runs]) or 0.0
                floor = (I.FALSE_COLOUR_AREA_WINDOW_FLOOR
                         if s == "broadRimColouredFraction"
                         else I.CHROMA_DISTANCE_WINDOW_FLOOR)
                wins[s] = I.window(rep, floor)
                kv, tv = lanes[CANDIDATE].get(s), t.get(s)
                within[s] = (kv is not None and tv is not None
                             and abs(kv - tv) <= wins[s])
                d = I.degenerate_reading(
                    f"{s} {asset} {vp}",
                    {lane: v.get(s) for lane, v in lanes.items()})
                if d:
                    deg_why = d["why"]
            status = (I.UNREADABLE if deg_why
                      else "PASS" if all(within.values()) else "FAIL")
            rows.append({
                "vp": vp, "asset": asset, "status": status,
                "lanes": {lane: {s: v.get(s) for s in
                                 (*scored, "fringeLocalisation",
                                  "featurePixels", "nonFeaturePixels")}
                          for lane, v in lanes.items()},
                "windows": {s: round(w, 6) for s, w in wins.items()},
                "within": within,
                **({"why": deg_why} if deg_why else {}),
            })
    st = classify(rows)
    add(5, "saturated edge: colour follows the media's own features and does "
           "not become a broad coloured rim", st,
        "§五. O5's coding returned 0.0 for every lane on every saturated asset "
        "and passed vacuously. This measures chroma AT media features and AWAY "
        "from them, and the coloured fraction of the Target's own bevel band; "
        "an asset with no feature population is UNREADABLE, not a pass.",
        {"rows": rows})
    TOPIC["saturated-edge-v2"] = {"what": "§五 feature-local saturated edge.",
                                  "rows": rows, "status": st}


# ================================================ 6 refraction compression

def item_refraction():
    rows = []
    for vp in VIEWPORTS:
        rects = RECTS[vp][0]
        truth_p = MD / f"{CANDIDATE}-bodytruth-{vp}.json"
        if not rects or not truth_p.exists():
            rows.append({"vp": vp, "status": I.UNREADABLE,
                         "why": "no card rect or no live matrices"})
            continue
        truth = json.loads(truth_p.read_text())
        lanes = {}
        for lane in LANES:
            p = shot(lane, "calib-landmarks", vp,
                     repeat=0 if lane == "target" else None)
            lanes[lane] = F.measure_lane(p, truth, rects, DISCS) if p else None
        if any(v is None for v in lanes.values()):
            rows.append({"vp": vp, "status": I.UNREADABLE,
                         "why": "a lane has no calibration capture"})
            continue

        # Card validation: decided from TARGET pixels alone, applied to every
        # lane. §六 says an unverifiable baseline is UNREADABLE, not FAIL.
        valid = {c["slotIndex"] for c in lanes["target"]["cards"]
                 if c.get("usable")
                 and (c.get("replayResidualMeanPx") or 1e9)
                 <= F.REPLAY_VALIDATION_MAX_PX}
        if not valid:
            rows.append({"vp": vp, "status": I.UNREADABLE,
                         "why": "no card's Target replay validated inside "
                                f"{F.REPLAY_VALIDATION_MAX_PX} px, so this "
                                "viewport has no verified baseline",
                         "targetCards": [
                             {"slot": c["slotIndex"],
                              "residual": c.get("replayResidualMeanPx"),
                              "usable": c.get("usable"),
                              "why": c.get("why")}
                             for c in lanes["target"]["cards"]]})
            continue

        # Per-disc VECTOR difference between lane and Target. A magnitude
        # comparison alone is a poor discriminator -- two bodies can displace a
        # landmark equally far in different directions.
        def per_disc(lane):
            out = {}
            for c in lanes[lane]["cards"]:
                if c["slotIndex"] not in valid or not c.get("usable"):
                    continue
                for d in c["perDisc"]:
                    out[(c["slotIndex"], d["id"])] = (d["dxPx"], d["dyPx"])
            return out

        tv = per_disc("target")
        results = {}
        for lane in LANES[1:]:
            lv = per_disc(lane)
            keys = sorted(set(tv) & set(lv))
            if not keys:
                results[lane] = None
                continue
            diffs = [float(np.hypot(lv[k][0] - tv[k][0], lv[k][1] - tv[k][1]))
                     for k in keys]
            results[lane] = {"discs": len(keys),
                             "meanVectorDeltaPx": round(float(np.mean(diffs)), 3),
                             "maxVectorDeltaPx": round(float(max(diffs)), 3)}
        if results[CANDIDATE] is None:
            rows.append({"vp": vp, "status": I.UNREADABLE,
                         "why": "no disc measured on both the Target and the "
                                "candidate on a validated card"})
            continue

        # Window from the Target's own repeats, on the same statistic.
        rep_runs = []
        for p in target_repeats("calib-landmarks", vp)[1:]:
            r = F.measure_lane(p, truth, rects, DISCS)
            rv = {}
            for c in r["cards"]:
                if c["slotIndex"] not in valid or not c.get("usable"):
                    continue
                for d in c["perDisc"]:
                    rv[(c["slotIndex"], d["id"])] = (d["dxPx"], d["dyPx"])
            keys = sorted(set(tv) & set(rv))
            if keys:
                rep_runs.append(float(np.mean(
                    [np.hypot(rv[k][0] - tv[k][0], rv[k][1] - tv[k][1])
                     for k in keys])))
        rep = (max(rep_runs) / 2.0) if rep_runs else 0.0
        win = I.window(rep, I.COMPRESSION_WINDOW_FLOOR_PX)
        k = results[CANDIDATE]["meanVectorDeltaPx"]
        deg = I.degenerate_reading(
            f"compression {vp}",
            {lane: (v or {}).get("meanVectorDeltaPx") for lane, v in results.items()})
        status = (I.UNREADABLE if deg else "PASS" if k <= win else "FAIL")
        rows.append({
            "vp": vp, "status": status,
            "validatedCards": sorted(valid),
            "targetReplayResidualPx": lanes["target"]["replayResidualMeanPx"],
            "displacementMeanPx": {lane: v["displacementMeanPx"]
                                   for lane, v in lanes.items()},
            "vectorDeltaToTargetPx": results,
            "targetSelfDeltaRuns": [round(v, 3) for v in rep_runs],
            "repeatability": round(rep, 3), "window": round(win, 3),
            **({"why": deg["why"]} if deg else {}),
        })
    st = classify(rows)
    add(6, "refraction compression reproduces the Target's own displacement "
           "field", st,
        "§六. No flat-card baseline anywhere. The candidate's displacement is "
        "read out of its own uv/displacement programs and its landmarks are "
        "measured inside footprints the source formula forward-maps; the "
        "Target's baseline is that same replay, validated against the "
        "Target's own render before any card is scored.",
        {"rows": rows})
    TOPIC["refraction-compression-v2"] = {
        "what": "§六 refraction compression from the real projected body.",
        "rows": rows, "status": st}


# ==================================================== 7 interior fidelity

def item_interior():
    rows = []
    for vp in VIEWPORTS:
        rects = RECTS[vp][0]
        for asset in TEXTURED_ASSETS + FLAT_ASSETS:
            if not rects or not shot("target", asset, vp, repeat=0):
                continue
            lanes, why = {}, None
            for lane in LANES:
                p = shot(lane, asset, vp, repeat=0 if lane == "target" else None)
                if p is None:
                    why = f"no {lane} capture"
                    break
                try:
                    lanes[lane] = I.interior_stats(p, rects)
                except I.Unreadable as e:
                    why = str(e)
                    break
            if why:
                rows.append({"vp": vp, "asset": asset, "status": I.UNREADABLE,
                             "why": why})
                continue
            t = lanes["target"]
            ok, na_why = I.sharpness_applicable(t["hfEnergy"])
            if not ok:
                rows.append({"vp": vp, "asset": asset,
                             "status": I.NOT_APPLICABLE, "why": na_why,
                             "targetHfEnergy": t["hfEnergy"],
                             "floor": I.HF_SIGNAL_FLOOR})
                continue
            scored = ["hfEnergy", "interiorLuma", "interiorChroma",
                      "localContrast"]
            closer, dist = {}, {}
            for s in scored:
                d = {lane: (abs(v[s] - t[s]) if v[s] is not None else None)
                     for lane, v in lanes.items() if lane != "target"}
                dist[s] = {lane: (round(v, 4) if v is not None else None)
                           for lane, v in d.items()}
                closer[s] = (d[CANDIDATE] is not None
                             and d["control"] is not None
                             and d[CANDIDATE] <= d["control"])
            corr = {lane: I.correlate(v["hfTiles"], t["hfTiles"])
                    for lane, v in lanes.items() if lane != "target"}
            chroma_corr = {lane: I.correlate(v["chromaTiles"], t["chromaTiles"])
                           for lane, v in lanes.items() if lane != "target"}
            deg = I.degenerate_reading(
                f"interior hf {asset} {vp}",
                {lane: v["hfEnergy"] for lane, v in lanes.items()})
            status = (I.UNREADABLE if deg
                      else "PASS" if all(closer.values()) else "FAIL")
            rows.append({
                "vp": vp, "asset": asset, "status": status,
                "lanes": {lane: {s: v[s] for s in scored}
                          for lane, v in lanes.items()},
                "distanceToTarget": dist, "candidateCloserThanControl": closer,
                "hfTileCorrelationToTarget": corr,
                "chromaTileCorrelationToTarget": chroma_corr,
                **({"why": deg["why"]} if deg else {}),
            })
    st = classify(rows)
    add(7, "interior fidelity: closer to the Target than the control is", st,
        "§七. The question is distance(candidate, Target) against "
        "distance(control, Target), never 'no blurrier than the control' -- on "
        "hf-checker the control is SHARPER than the Target, so the O5 coding "
        "failed the candidate for being closer. Flat assets are NOT_APPLICABLE "
        f"below a Target HF energy of {I.HF_SIGNAL_FLOOR}.",
        {"rows": rows})
    TOPIC["interior-fidelity-v2"] = {"what": "§七 Target-relative interior.",
                                     "rows": rows, "status": st}


# ==================================================== 8 own-media isolation

def item_own_media():
    rows = []
    for vp in VIEWPORTS:
        for lane in (CANDIDATE, "o5-clamped", "control"):
            rec = find(kind="lane", lane=lane, asset="bw-split", vp=vp,
                       state="rest")
            if not rec:
                continue
            st = (rec[0].get("passes") or {}).get("stats") or {}
            layers = (rec[0].get("passes") or {}).get("layers") or {}
            rows.append({"vp": vp, "lane": lane,
                         "sceneColorCalls": st.get("sceneColorCalls"),
                         "finalCalls": st.get("finalCalls"),
                         "mediaMeshesVisible": layers.get("mediaMeshesVisible"),
                         "glassMeshesVisible": layers.get("glassMeshesVisible")})
    cand = [r for r in rows if r["lane"] == CANDIDATE]
    ctrl = [r for r in rows if r["lane"] == "control"]
    structural = bool(cand) and all(r["sceneColorCalls"] == 0 for r in cand)
    contrast = bool(ctrl) and all((r["sceneColorCalls"] or 0) > 0 for r in ctrl)
    media_hidden = bool(cand) and all(
        r["mediaMeshesVisible"] in (0, None) for r in cand)
    status = "PASS" if (structural and contrast and media_hidden) else "FAIL"
    add(8, "own-media isolation: no neighbour bleed, no scene-colour "
           "cross-card contamination", status,
        "Structural, and shown against the control rather than asserted: the "
        "candidate's scene-colour pass draws 0 calls and its media plane is "
        "hidden, yet its cards show media -- so the media cannot have come "
        "from a shared target. Neighbour bleed is impossible by construction: "
        "the refracted UV is clamped BEFORE the cover transform, so a sample "
        "cannot reach outside the card's own media frame.",
        {"rows": rows, "candidateSceneColourZero": structural,
         "controlSceneColourNonZero": contrast,
         "candidateMediaPlaneHidden": media_hidden})
    TOPIC["own-media-isolation"] = {"what": "§十三 own-media isolation.",
                                    "rows": rows, "status": status}


# ========================================================== 9 silhouette

def item_silhouette():
    rows = []
    for vp in VIEWPORTS:
        rects = RECTS[vp][0]
        mask_rec = find(kind="view", lane=CANDIDATE, view="sdf-mask", vp=vp)
        if not rects or not mask_rec:
            rows.append({"vp": vp, "status": I.UNREADABLE,
                         "why": "no card rect or no sdf-mask program capture"})
            continue
        rect = rects[0]
        try:
            projected, pval = I.projected_alpha_mask(MD / mask_rec[0]["file"],
                                                     rect)
        except I.Unreadable as e:
            rows.append({"vp": vp, "status": I.UNREADABLE, "why": str(e)})
            continue
        lanes, why = {}, None
        for lane in LANES:
            p = shot(lane, "bw-split", vp, repeat=0 if lane == "target" else None)
            if p is None:
                why = f"no {lane} capture"
                break
            try:
                m, _ = I.rendered_alpha_mask(p, rect)
                lanes[lane] = {
                    **I.silhouette_compare(m, projected),
                    "cornerRadiusPx": I.measured_corner_radius_px(m),
                }
            except I.Unreadable as e:
                why = str(e)
                break
        if why:
            rows.append({"vp": vp, "status": I.UNREADABLE, "why": why})
            continue
        aa = I.edge_width_px(pval, projected)
        scored = ["litBeyondFraction", "cornerRadiusPx", "iou"]
        wins, within = {}, {}
        reps = []
        for p in target_repeats("bw-split", vp)[1:]:
            try:
                m, _ = I.rendered_alpha_mask(p, rect)
                reps.append({**I.silhouette_compare(m, projected),
                             "cornerRadiusPx": I.measured_corner_radius_px(m)})
            except I.Unreadable:
                pass
        t = lanes["target"]
        for s in scored:
            rep = repeatability([r.get(s) for r in reps] + [t.get(s)]) or 0.0
            floor = (I.SILHOUETTE_EDGE_WINDOW_FLOOR_PX if s == "cornerRadiusPx"
                     else 0.02)
            wins[s] = I.window(rep, floor)
            kv, tv = lanes[CANDIDATE].get(s), t.get(s)
            within[s] = (kv is not None and tv is not None
                         and abs(kv - tv) <= wins[s])
        deg = I.degenerate_reading(
            f"silhouette litBeyond {vp}",
            {lane: v["litBeyondFraction"] for lane, v in lanes.items()})
        status = (I.UNREADABLE if deg
                  else "PASS" if all(within.values()) else "FAIL")
        rows.append({
            "vp": vp, "status": status, "rect": list(rect),
            "projectedFrom": mask_rec[0]["file"],
            "antialiasWidthPx": aa,
            "lanes": lanes, "windows": {s: round(w, 5) for s, w in wins.items()},
            "within": within,
            **({"why": deg["why"]} if deg else {}),
        })
    st = classify(rows)
    add(9, "silhouette matches the REAL projected body", st,
        "§八. The axis-aligned rounded rect over a bounding box is gone. The "
        "reference is the sdf-mask program's own coverage -- the Target's SDF "
        "rendered through the actual PlaneGeometry projection, the actual card "
        "matrix and the actual fwidth alpha -- and every lane's rendered "
        "coverage is compared against it.",
        {"rows": rows})
    TOPIC["silhouette-v2"] = {"what": "§八 real projected silhouette.",
                              "rows": rows, "status": st}


# ========================================================= 10 pointer path

def item_pointer():
    """Carried from O5's sealed pointer coding, used exactly as O5 used it.

    Ink is removed by intersecting every captured pointer state, and each state
    is cropped at ITS OWN rect because parallax moves the card between them.
    """
    INK_STATES = [("rest", (0.0, 0.0)), ("pl", (-0.99, 0.0)),
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
            p = shot(lane, "bw-split", vp, state=name,
                     repeat=0 if (lane == "target" and name == "rest") else None)
            if p is None and lane == "target" and name == "rest":
                p = shot(lane, "bw-split", vp, state=name)
            rect = dark_half_rect(w, h, ndc)
            if p is None or rect is None:
                continue
            states[name] = (open_img(p), rect)
        if not states:
            return None
        masks, excluded, dims = I5.glass_reflection_masks(states)
        cents = {s: I5.centroid_of(m, dims) for s, m in masks.items()}
        return {
            "statesUsedForInk": sorted(states),
            "cardSpaceDims": dims,
            "excludedInkPixels": (int(excluded.sum())
                                  if excluded is not None else None),
            "glassPixelsPerState": {s: (c["pixels"] if c else 0)
                                    for s, c in cents.items()},
            "path": [cents.get(s, {}).get("nx") if cents.get(s) else None
                     for s in PATH_STATES],
        }

    rows = []
    for vp in VIEWPORTS:
        paths = {}
        for lane in LANES:
            pp = pointer_path(lane, vp)
            if pp:
                paths[lane] = pp
        if "target" not in paths or CANDIDATE not in paths:
            rows.append({"vp": vp, "status": I.UNREADABLE,
                         "why": "no usable pointer path for the Target or the "
                                "candidate at this viewport",
                         "lanesRead": sorted(paths)})
            continue
        judged = I5.pointer_judge(tuple(paths["target"]["path"]),
                                  tuple(paths[CANDIDATE]["path"]))
        ctrl = (I5.pointer_judge(tuple(paths["target"]["path"]),
                                 tuple(paths["control"]["path"]))
                if "control" in paths else {})
        deg = I.degenerate_reading(
            f"pointer path {vp}",
            {lane: (v["path"][2] if v["path"][2] is not None else None)
             for lane, v in paths.items()})
        status = (I.UNREADABLE if deg
                  else "PASS" if not judged.get("fired") else "FAIL")
        rows.append({"vp": vp, "status": status,
                     "paths": {lane: v["path"] for lane, v in paths.items()},
                     "candidateVerdict": judged, "controlVerdict": ctrl,
                     "glassPixelsPerState": {lane: v["glassPixelsPerState"]
                                             for lane, v in paths.items()},
                     **({"why": deg["why"]} if deg else {})})
    st = classify(rows)
    add(10, "pointer reflection moves in the Target's direction without a "
            "discontinuity", st,
        "Carried from O5's sealed pointer judge, unchanged and used exactly as "
        "O5 used it: labels off, ink removed by intersecting every captured "
        "pointer state, each state cropped at its own rect because parallax "
        "moves the card. Extended to all four viewports.",
        {"rows": rows})
    TOPIC["pointer-path"] = {"what": "§十三 pointer path.", "rows": rows,
                             "status": st}


# ==================================================== 11 temporal continuity

def item_temporal():
    pop = REPO / "artifacts/optics-o5r/recordings/pop.json"
    if not pop.exists():
        add(11, "no temporal pop during pointer sweep, slow drag, fast flick "
                "or touch release", I.UNREADABLE,
            "No O5R recordings on disk, so no verdict is available. Not "
            "converted into a pass.", {})
        TOPIC["temporal-continuity"] = {"status": I.UNREADABLE}
        return
    d = json.loads(pop.read_text())
    status = "PASS" if d.get("pass") else "FAIL"
    add(11, "no temporal pop during pointer sweep, slow drag, fast flick or "
            "touch release", status,
        d.get("summary", "see temporal-continuity.json"), d)
    TOPIC["temporal-continuity"] = {**d, "status": status}


# ==================================================== 12 mobile consistency

def item_mobile():
    """Same optical DIRECTION everywhere, whether or not the window is entered.

    The per-row status here is this item's own, computed on the direction rule.
    The window verdict from items 1-3 travels alongside as `windowStatus` and
    is deliberately not reused as this row's status: a row can be outside the
    Target's window at one viewport and still be moving the right way, and
    conflating the two would make the item's summary disagree with its rows.
    """
    rows = []
    for key in ("reflection-band", "dark-side-luma", "white-reflection-ratio"):
        t = TOPIC.get(key)
        if not t:
            continue
        for r in t["rows"]:
            if r.get("status") == I.UNREADABLE:
                rows.append({"metric": key, "vp": r["vp"],
                             "status": I.UNREADABLE,
                             "windowStatus": r.get("status"),
                             "why": r.get("why")})
                continue
            toward = r.get("movedTowardTarget")
            rows.append({
                "metric": key, "vp": r["vp"],
                # `None` means the control was already on the Target, so
                # "moved toward" has no meaning -- not a failure.
                "status": ("PASS" if toward is not False else "FAIL"),
                "movedTowardTarget": toward,
                "windowStatus": r.get("status"),
                "candidateDelta": r.get("candidateDelta"),
                "controlDelta": (round(abs(r["control"] - r["target"]), 4)
                                 if r.get("control") is not None
                                 and r.get("target") is not None else None),
            })
    mobile = [r for r in rows if r["vp"] in ("390x844", "844x390")]
    desktop = [r for r in rows if r["vp"] in ("1440x900", "700x700")]
    st = classify(rows) if (mobile and desktop) else I.UNREADABLE
    add(12, "portrait, landscape and square show the same optical direction",
        st,
        "Every edge metric must move TOWARD the Target at every viewport, "
        "whether or not it enters the window there. A candidate that improved "
        "desktop by moving mobile the wrong way would fail this even with two "
        "passing viewports. Scored on direction; the window verdict from items "
        "1-3 travels alongside as windowStatus and is not reused here.",
        {"rows": rows, "mobileRows": len(mobile), "desktopRows": len(desktop)})
    TOPIC["mobile-consistency"] = {"what": "§十三 mobile consistency.",
                                   "rows": rows, "status": st}


# ============================================== 13 full-frame review readiness

def item_fullframe():
    have, missing = [], []
    for vp in VIEWPORTS:
        for asset in FULLFRAME_ASSETS:
            for lane in LANES:
                p = shot(lane, asset, vp, repeat=0 if lane == "target" else None)
                (have if p else missing).append(
                    {"lane": lane, "asset": asset, "vp": vp,
                     "file": p.name if p else None})
    # The numerical proxy may contain ONLY metrics that discriminated. A row
    # that came out UNREADABLE or NOT_APPLICABLE contributes nothing.
    proxy = {}
    for key in ("reflection-band", "dark-side-luma", "white-reflection-ratio",
                "interior-fidelity-v2", "refraction-compression-v2"):
        t = TOPIC.get(key)
        if not t:
            continue
        readable = [r for r in t["rows"]
                    if r.get("status") in ("PASS", "FAIL")]
        if readable:
            proxy[key] = {"readableRows": len(readable),
                          "passed": sum(1 for r in readable
                                        if r["status"] == "PASS"),
                          "status": t["status"]}
    status = ("PASS" if not missing else I.UNREADABLE)
    add(13, "full-frame product review readiness", status,
        "EVIDENCE PREPARED, NOT A PRODUCT JUDGMENT. §九 is explicit: the agent "
        "prepares the evidence and does not approve itself. This row asserts "
        "only that the four lanes exist at every asset and viewport the brief "
        "names, and that the numerical proxy beside them contains only metrics "
        "that actually discriminated -- no all-lanes-zero sub-check is "
        "included, which is what made O5's item 14 partly vacuous.",
        {"framesPresent": len(have), "framesMissing": len(missing),
         "missing": missing[:20],
         "lanes": LANES, "assets": FULLFRAME_ASSETS, "viewports": VIEWPORTS,
         "discriminatingProxy": proxy,
         "productJudgment": "OWNED BY PRODUCT REVIEW"})
    TOPIC["full-frame-readiness"] = {"framesPresent": len(have),
                                     "framesMissing": len(missing),
                                     "status": status}


# ================================================ 14 pipeline / resources

def item_pipeline():
    p = OUT / "pipeline-performance-v2.json"
    if not p.exists():
        add(14, "pipeline and resource stability", I.UNREADABLE,
            "No §十二 performance record on disk. Not converted into a pass.",
            {})
        return
    d = json.loads(p.read_text())
    status = "PASS" if d.get("pass") else "FAIL"
    add(14, "pipeline and resource stability", status, d.get("summary", ""),
        {"passed": d.get("passed"), "total": d.get("total"),
         "checks": [{"check": c["check"], "pass": c["pass"]}
                    for c in d.get("checks", [])]})


# ---------------------------------------------------------------- assemble

def relative_to_control():
    """Derived, and deliberately not a status: which lane sits closer.

    A window verdict answers "is the candidate inside the Target's own spread".
    It does not answer "is the candidate closer to the Target than the body we
    ship today", and on this round the two questions come apart hard: item 4
    fails on hf-checker at a distance of 12 where the shipped body's distance
    is 94. Reporting only the first would let a reader infer the second.

    Nothing here changes any row's status. It is arithmetic over readings the
    sealed instruments already produced.
    """
    # Some readings the instruments carry are DIAGNOSTIC -- how many pixels a
    # mask selected, how many the silhouette covers -- and "closer to the
    # Target" on those is not a statement about optical quality. They are
    # tabulated but kept out of the headline count, because a tally that mixed
    # them would flatter or damn a lane for the size of a mask.
    diagnostic = {"featurePixels", "nonFeaturePixels", "projectedPixels",
                  "renderedPixels", "intersection", "falseColourBlobs",
                  "unlitInsideSilhouette", "litBeyondSilhouette"}
    out, closer_c, closer_k, tied = [], 0, 0, 0
    for it in ITEMS:
        for row in (it.get("numbers") or {}).get("rows", []) or []:
            if row.get("status") in (I.UNREADABLE, I.NOT_APPLICABLE):
                continue
            lanes = row.get("lanes")
            pairs = []
            if isinstance(lanes, dict) and all(
                    isinstance(v, dict) for v in lanes.values()):
                t, c, k = (lanes.get("target"), lanes.get("control"),
                           lanes.get(CANDIDATE))
                if not (t and c and k):
                    continue
                for m in sorted(set(t) & set(c) & set(k)):
                    if all(isinstance(d.get(m), (int, float))
                           and not isinstance(d.get(m), bool)
                           for d in (t, c, k)):
                        pairs.append((m, t[m], c[m], k[m]))
            elif isinstance(row.get("target"), (int, float)):
                if isinstance(row.get("control"), (int, float)) and \
                        isinstance(row.get(CANDIDATE), (int, float)):
                    pairs.append((it["name"], row["target"], row["control"],
                                  row[CANDIDATE]))
            for m, tv, cv, kv in pairs:
                dc, dk = abs(cv - tv), abs(kv - tv)
                verdict = ("candidate" if dk < dc - 1e-9
                           else "control" if dc < dk - 1e-9 else "tied")
                is_diag = m in diagnostic
                if not is_diag:
                    closer_k += verdict == "candidate"
                    closer_c += verdict == "control"
                    tied += verdict == "tied"
                out.append({"item": it["item"], "metric": m,
                            "diagnostic": is_diag,
                            "asset": row.get("asset"), "vp": row.get("vp"),
                            "target": round(float(tv), 4),
                            "control": round(float(cv), 4),
                            "candidate": round(float(kv), 4),
                            "controlDistance": round(dc, 4),
                            "candidateDistance": round(dk, 4),
                            "closerToTarget": verdict})
    return {
        "what": "for every readable scored comparison: the distance from the "
                "Target of the shipped body and of the O5R candidate. Derived "
                "arithmetic over the sealed instruments' own readings; it "
                "changes no status and is not part of the gate.",
        "comparisons": len(out),
        "qualityComparisons": closer_k + closer_c + tied,
        "diagnosticFields": sorted(diagnostic),
        "candidateCloser": closer_k, "controlCloser": closer_c, "tied": tied,
        "perItem": {
            str(n): {
                v: sum(1 for r in out if r["item"] == n and not r["diagnostic"]
                       and r["closerToTarget"] == v)
                for v in ("candidate", "control", "tied")}
            for n in sorted({r["item"] for r in out})},
        "rows": out,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    edge_metric(lambda p, r: (I5.band_width_px(open_img(p), r)["meanPx"]
                              if p else None),
                I.BAND_WINDOW_FLOOR_PX, 1,
                "reflection band width enters the Target window",
                "Carried from O5 unchanged, so the two gates stay comparable.",
                "reflection-band")
    edge_metric(lambda p, r: (I5.dark_side_luma(open_img(p), r)["meanLuma"]
                              if p else None),
                I.DARK_LUMA_WINDOW_FLOOR, 2,
                "dark-side edge luminance enters the Target window",
                "Carried from O5 unchanged.", "dark-side-luma")
    edge_metric(lambda p, r: (I5.white_reflection_ratio(open_img(p), r)["meanRatio"]
                              if p else None),
                I.WHITE_RATIO_WINDOW_FLOOR, 3,
                "white reflection ratio enters the Target window",
                "Carried from O5 unchanged.", "white-reflection-ratio")
    item_grayscale()
    item_saturated_edge()
    item_refraction()
    item_interior()
    item_own_media()
    item_silhouette()
    item_pointer()
    item_temporal()
    item_mobile()
    item_fullframe()
    item_pipeline()

    derived = relative_to_control()

    counts = {s: sum(1 for i in ITEMS if i["status"] == s)
              for s in ("PASS", "FAIL", I.NOT_APPLICABLE, I.UNREADABLE)}
    gate = "PASS" if counts["FAIL"] == 0 and counts[I.UNREADABLE] == 0 else "FAIL"
    doc = {
        "what": "§十三B -- the corrected O5R product gate. Definitions were "
                "sealed in qa-v5/optics-o5r/instrument-contract.json before "
                "the candidate lane was captured.",
        "lanes": LANES, "scoredCandidate": CANDIDATE, "viewports": VIEWPORTS,
        "rectBasis": {vp: RECTS[vp][1] for vp in VIEWPORTS},
        "classification": "PASS / FAIL / NOT_APPLICABLE / "
                          "INSTRUMENT_UNREADABLE. An UNREADABLE row is never "
                          "converted into a PASS, and never into a FAIL.",
        "counts": counts, "total": len(ITEMS), "gate": gate,
        "derivedCandidateVsControl": derived,
        "consoleAndPageErrors": sum(r.get("errorCount", 0)
                                    for r in MAN["records"]),
        "items": ITEMS,
    }
    (OUT / "corrected-product-gate.json").write_text(
        json.dumps(doc, indent=1, default=_json_default))
    for k, v in TOPIC.items():
        (OUT / f"{k}.json").write_text(
            json.dumps(v, indent=1, default=_json_default))
    for i in ITEMS:
        print(f"  {i['status']:22}  {i['item']:2d}. {i['name']}")
    print(f"\nPASS {counts['PASS']}  FAIL {counts['FAIL']}  "
          f"N/A {counts[I.NOT_APPLICABLE]}  "
          f"UNREADABLE {counts[I.UNREADABLE]}  of {len(ITEMS)}")
    print(f"gate: {gate}")
    return 0 if gate == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
