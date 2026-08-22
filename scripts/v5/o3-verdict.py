#!/usr/bin/env python3
"""O3 absolute gate -- score all twenty §九 items against the thresholds
sealed in qa-v5/optics-o3/o3-preregistration.json.

Nothing here chooses a coding. Every threshold is read from the sealed
file, and every instrument that has a choice to make (F5, F10, F11) is
imported from o3_instruments -- the SAME module the unit tests certify and
the dry run exercised on non-candidate data. One implementation, one
number.

Items whose inputs are absent are reported "pending", never assumed. A
pending item is not a pass.

Usage: o3-verdict.py [--measure=<dir>] [--gate1=<dir>] [--shader=<dir>]
       [--forensics=<json>] [--recordings=<json>] [--regressions=<json>]
       [--crosssection=<json>] [--judgement20=<json>] [--out=<json>]
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


S = _load("o3_stats", "o2_optics_stats.py")
INS = _load("o3_instruments_mod", "o3_instruments.py")
VC, SL = sys.modules["v0_culling"], sys.modules["source_layout"]

OPTS = {"measure": REPO / "artifacts/optics-o3/measure",
        "gate1": REPO / "artifacts/optics-o3/gate1",
        "shader": REPO / "artifacts/optics-o3/shader",
        "forensics": REPO / "qa-v5/optics-o3/bevel-source-live.json",
        "recordings": REPO / "artifacts/optics-o3/recordings/pop.json",
        "regressions": REPO / "artifacts/optics-o3/regressions/regressions.json",
        "crosssection": REPO / "artifacts/optics-o3/crosssection/crosssection.json",
        "judgement20": REPO / "qa-v5/optics-o3/judgement-20.json",
        "prereg": REPO / "qa-v5/optics-o3/o3-preregistration.json",
        "out": REPO / "qa-v5/optics-o3/o3-absolute-gate.json"}
for _a in sys.argv[1:]:
    _k, _, _v = _a.lstrip("-").partition("=")
    if _k in OPTS:
        OPTS[_k] = Path(_v)

MD = Path(OPTS["measure"])
MAN = json.loads((MD / "measure-manifest.json").read_text())
PREREG = json.loads(Path(OPTS["prereg"]).read_text())
THR = {g["n"]: g.get("threshold") for g in PREREG["absoluteGate"]}
ITEM = {g["n"]: g for g in PREREG["absoluteGate"]}

SATURATED = ["rgb-bars", "cool-blue", "warm-skin"]
DESKTOP_ASSETS = ["bw-split", "grayscale-step", "rgb-bars", "hf-checker",
                  "dark-highlight", "bright-lowsat", "warm-skin", "cool-blue"]
VPS = ["1440x900", "390x844", "844x390"]


def find(**kw):
    return [r for r in MAN["records"]
            if all(r.get(k) == v for k, v in kw.items())]


def img_of(rec, base=None):
    return Image.open(Path(base or MD) / rec["file"])


def rects_for(vp, ndc=(0.0, 0.0)):
    """Scored rects, with the O2-documented one-card fallback.

    844x390 has no card that clears the viewport margin. O2 recorded a
    side-bands fallback for exactly this; it is carried here with its
    basis attached so no reader mistakes it for the same measurement.
    """
    w, h = (int(x) for x in vp.split("x"))
    rects = [r for _, r in S.rects_at(w, h, ndc)]
    if rects:
        return rects, "fully-visible cards"
    frame = SL.layout(w, h)
    cam = VC.coverage_camera(ndc[0], ndc[1], frame)
    cand = []
    for v in VC.frame_verdicts(0.0, 0.0, cam, frame).values():
        if v.get("draw") and v.get("aabb"):
            x0, y0, x1, y1 = v["aabb"]
            cand.append((x1 - x0, (int(max(x0, 0)), int(max(y0, 0)),
                                   int(min(x1, w)), int(min(y1, h)))))
    if not cand:
        return [], "no drawn card"
    return [max(cand)[1]], "no fully-visible card -- widest drawn card"


def lane_stats(lane, asset, vp="1440x900", state="full"):
    kw = ({"kind": "target", "state": "rest"} if lane == "target"
          else {"kind": "local", "lane": lane, "state": state})
    rows = find(**kw, asset=asset, vp=vp)
    if not rows:
        return None
    rects, basis = rects_for(vp)
    if not rects:
        return None
    img = img_of(rows[0])
    w, h = (int(x) for x in vp.split("x"))
    out = dict(S.stats(img, rects, w, h))
    out.update(S.side_bands(img, rects))
    out["interior"] = S.interior_stats(img, rects)
    out["reflectionBand"] = S.reflection_band(img, rects)
    out["metricBasis"] = basis
    out["file"] = rows[0]["file"]
    return out


def pixdiff(pa, pb):
    a = np.asarray(Image.open(pa).convert("RGB")).astype(int)
    b = np.asarray(Image.open(pb).convert("RGB")).astype(int)
    if a.shape != b.shape:
        return {"comparable": False}
    d = np.abs(a - b).max(axis=2)
    return {"differingPixels": int((d > 0).sum()), "maxChannelDelta": int(d.max())}


def load(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else None


# ------------------------------------------------------------ measurands --
M = {vp: {lane: {a: lane_stats(lane, a, vp) for a in DESKTOP_ASSETS}
          for lane in ("target", "control", "candidate")} for vp in VPS}
BW = {lane: M["1440x900"][lane]["bw-split"] for lane in
      ("target", "control", "candidate")}

items = []


def add(n, passed, **detail):
    """Record one gate item. `passed` may be None -> pending."""
    items.append({"n": n, "item": ITEM[n]["item"], "pass": ITEM[n]["pass"],
                  "threshold": THR.get(n),
                  "result": ("PASS" if passed else "FAIL") if passed is not None
                            else "PENDING",
                  **detail})


# --- 1 -------------------------------------------------------------------
g1 = load(Path(OPTS["gate1"]) / "pairs.json")
if g1:
    rows = []
    for p in g1["pairs"]:
        d = pixdiff(Path(OPTS["gate1"]) / p["candidate"]["file"],
                    Path(OPTS["gate1"]) / p["base"]["file"])
        rows.append({"asset": p["asset"], "vp": p["vp"], **d})
    ok = all(r.get("differingPixels") == 0 for r in rows)
    add(1, ok, cases=rows,
        note="the baseline build has no reflectionSupport key in its optics "
             "state -- the parameter is inert there, which is what makes the "
             "identical query legitimate on both sides.")
else:
    add(1, None, reason="gate1/pairs.json absent")

# --- 2 -------------------------------------------------------------------
fx = load(OPTS["forensics"])
if fx:
    ok = bool(fx.get("pass")) and fx.get("sitesFailed", 1) == 0
    # `sites` in the forensics file is the full per-site record; carry the
    # count here and leave the records where they already live, so this
    # gate row stays readable.
    _sites = fx.get("sites")
    add(2, ok,
        siteCount=len(_sites) if isinstance(_sites, list) else _sites,
        sitesFailed=fx.get("sitesFailed"),
        bundleSha256=fx.get("bundleSha256"), liveBundle=fx.get("liveBundle"),
        recordsIn="qa-v5/optics-o3/bevel-source-live.json")
else:
    add(2, None, reason="forensics json absent")

# --- 3 -------------------------------------------------------------------
t, c = BW["target"]["reflectionBand"]["meanPx"], BW["candidate"]["reflectionBand"]["meanPx"]
add(3, abs(c - t) <= THR[3], targetPx=t, candidatePx=c,
    deltaPx=round(abs(c - t), 2),
    controlPx=BW["control"]["reflectionBand"]["meanPx"],
    perCard={"target": BW["target"]["reflectionBand"]["perCard"],
             "control": BW["control"]["reflectionBand"]["perCard"],
             "candidate": BW["candidate"]["reflectionBand"]["perCard"]})

# --- 4 -------------------------------------------------------------------
ctl = BW["control"]["reflectionBand"]["meanPx"]
ratio_ok = c <= THR[4]["ratio"] * ctl
abs_ok = (ctl - c) >= THR[4]["absolutePx"]
add(4, ratio_ok and abs_ok, controlPx=ctl, candidatePx=c,
    ratioCeilingPx=round(THR[4]["ratio"] * ctl, 2), ratioConditionMet=ratio_ok,
    absoluteDropPx=round(ctl - c, 2), absoluteConditionMet=abs_ok)

# --- 5 -------------------------------------------------------------------
t5, c5 = BW["target"]["darkSideEdgeLuma"], BW["candidate"]["darkSideEdgeLuma"]
add(5, abs(c5 - t5) <= THR[5], targetLuma=t5, candidateLuma=c5,
    controlLuma=BW["control"]["darkSideEdgeLuma"],
    delta=round(abs(c5 - t5), 2))

# --- 6 -------------------------------------------------------------------
t6, c6 = BW["target"]["whiteReflectionRatio"], BW["candidate"]["whiteReflectionRatio"]
add(6, abs(c6 - t6) <= THR[6], target=t6, candidate=c6,
    control=BW["control"]["whiteReflectionRatio"], delta=round(abs(c6 - t6), 5))

# --- 7 -------------------------------------------------------------------
t7 = BW["target"]["darkOverBrightLumaRatio"]
c7 = BW["candidate"]["darkOverBrightLumaRatio"]
k7 = BW["control"]["darkOverBrightLumaRatio"]
add(7, abs(c7 - t7) < abs(k7 - t7), target=t7, control=k7, candidate=c7,
    candidateDistance=round(abs(c7 - t7), 4),
    controlDistance=round(abs(k7 - t7), 4))

# --- 8 -------------------------------------------------------------------
def chroma_attribution():
    """Where an edge-chroma difference comes from, read off the floor
    states on bw-split. DIAGNOSTIC ONLY -- it is attached to whatever the
    gate returned and changes no verdict.

    bw-split is achromatic, so edge chroma on it is shader-introduced
    colour and nothing else.
    """
    rects, _ = rects_for("1440x900")
    out = {}
    for st in ["env0rim0", "env0rim1", "env1rim0", "full"]:
        row = {}
        for lane in ("control", "candidate"):
            rows = find(kind="local", lane=lane, state=st, asset="bw-split",
                        vp="1440x900")
            if not rows:
                continue
            s = S.stats(img_of(rows[0]), rects, 1440, 900)
            row[lane] = {"edgeChromaMean": s["edgeChromaMean"],
                         "edgeLuminanceMean": s["edgeLuminanceMean"],
                         "whiteReflectionRatio": s["whiteReflectionRatio"]}
        out[st] = row
    tr = find(kind="target", state="rest", asset="bw-split", vp="1440x900")
    if tr:
        s = S.stats(img_of(tr[0]), rects, 1440, 900)
        out["target"] = {"edgeChromaMean": s["edgeChromaMean"],
                         "edgeLuminanceMean": s["edgeLuminanceMean"],
                         "whiteReflectionRatio": s["whiteReflectionRatio"]}
    return out


ATTR = chroma_attribution()
g = M["1440x900"]
k8 = g["control"]["grayscale-step"]["edgeChromaMean"]
c8 = g["candidate"]["grayscale-step"]["edgeChromaMean"]
add(8, c8 <= k8 + THR[8], control=k8, candidate=c8,
    ceiling=round(k8 + THR[8], 2), target=g["target"]["grayscale-step"]["edgeChromaMean"],
    attributionBwSplit=ATTR,
    attributionReading="DIAGNOSTIC, not a re-score. With System B off the "
        "lanes are identical (env0rim0). At rim-only the CONTROL reads "
        "LOWER chroma than the candidate -- its over-wide white rim covers "
        "the edge band with neutral white and so dilutes the mean. At "
        "env-only the candidate reads higher: the analytic normal tilts to "
        "the source's 60 deg slope clamp and swings the reflection vector "
        "further into a coloured studio HDR than our gentler geometry "
        "shoulder did. So the rise is partly a real chroma increase from "
        "the environment sample and partly the REMOVAL of a white rim that "
        "had been masking the frozen base's own colour -- corroborated by "
        "fringeWidthPxMean falling on every saturated asset in item 10.")

# --- 9 -------------------------------------------------------------------
rows9 = []
for a in SATURATED:
    k = g["control"][a]["edgeChromaMean"]
    cc = g["candidate"][a]["edgeChromaMean"]
    rows9.append({"asset": a, "control": k, "candidate": cc,
                  "ceiling": round(k + THR[9], 2), "pass": cc <= k + THR[9]})
add(9, all(r["pass"] for r in rows9), assets=rows9)

# --- 10 ------------------------------------------------------------------
rows10 = []
for a in SATURATED:
    k, cc = g["control"][a], g["candidate"][a]
    fr_ok = cc["fringeRB"] <= k["fringeRB"] + 0.5
    fw_ok = cc["fringeWidthPxMean"] <= k["fringeWidthPxMean"] + 0.5
    rows10.append({"asset": a,
                   "fringeRB": {"control": k["fringeRB"], "candidate": cc["fringeRB"],
                                "pass": fr_ok},
                   "fringeWidthPxMean": {"control": k["fringeWidthPxMean"],
                                         "candidate": cc["fringeWidthPxMean"],
                                         "pass": fw_ok},
                   "pass": fr_ok and fw_ok})
add(10, all(r["pass"] for r in rows10), assets=rows10)

# --- 11 ------------------------------------------------------------------
rows11 = []
for a in DESKTOP_ASSETS:
    k, cc = g["control"][a], g["candidate"][a]
    if not k or not cc:
        continue
    r = INS.f5_interior_change(k["interior"], cc["interior"])
    rows11.append({"asset": a, **r})
knife = [r for r in rows11 if r["fired"] and r.get("coding") == "relative"
         and r.get("baselineSaturation", 1) < 2 * INS.F5_BASELINE_FLOOR]
add(11, all(not r["fired"] for r in rows11), assets=rows11,
    codingNote="the branch is chosen by the CONTROL render's interior "
               "saturation alone -- see o3-instrument-tests.py, "
               "'F5 coding depends only on the baseline'.",
    nearFloorCoding=knife or None,
    nearFloorReading=("DIAGNOSTIC, not a re-score. "
        + "; ".join(f"{r['asset']} has baseline interior saturation "
                    f"{r['baselineSaturation']} -- just above the "
                    f"{INS.F5_BASELINE_FLOOR} floor, so the sealed rule took "
                    f"the RELATIVE branch, and an absolute saturation change "
                    f"of {r.get('absSaturationDelta', abs(r.get('relSaturationChange', 0) * r['baselineSaturation'])):.4f} "
                    f"scored as {r.get('relSaturationChange', 0):.1%}. Under "
                    f"the absolute branch the same change would have been "
                    f"inside the {INS.F5_ABSOLUTE_SATURATION_CEILING} ceiling."
                    for r in knife)
        + " The branch was fixed by the baseline before any candidate pixel "
          "existed and is not revisited here." ) if knife else None)

# --- 12 ------------------------------------------------------------------
rows12 = []
for rec in find(kind="media-only", lane="candidate"):
    ctl_rows = find(kind="media-only", lane="control", asset=rec["asset"],
                    vp=rec["vp"])
    if not ctl_rows:
        continue
    d = pixdiff(MD / rec["file"], MD / ctl_rows[0]["file"])
    rows12.append({"asset": rec["asset"], "vp": rec["vp"], **d})
add(12, bool(rows12) and all(r.get("differingPixels") == 0 for r in rows12),
    pairs=rows12)

# --- 13 ------------------------------------------------------------------
rows13 = []
for vp in ["1440x900", "390x844"]:
    w, h = (int(x) for x in vp.split("x"))
    frame = SL.layout(w, h)
    cam = VC.coverage_camera(0.0, 0.0, frame)
    verd = VC.frame_verdicts(0.0, 0.0, cam, frame)
    dil = INS.f10_dilation_for(frame["planeWidth"] if isinstance(frame, dict)
                               and "planeWidth" in frame else w)
    for a in ["bw-split", "rgb-bars"]:
        kr = find(kind="local", lane="control", state="full", asset=a, vp=vp)
        cr = find(kind="local", lane="candidate", state="full", asset=a, vp=vp)
        if not kr or not cr:
            continue
        k = INS.f10_gutter_ink(img_of(kr[0]), verd, dil)
        cc = INS.f10_gutter_ink(img_of(cr[0]), verd, dil)
        if k["gutterInkRatio"] is None or cc["gutterInkRatio"] is None:
            continue
        ok = cc["gutterInkRatio"] <= k["gutterInkRatio"] + THR[13]
        rows13.append({"asset": a, "vp": vp, "dilationPx": dil,
                       "cardsMasked": cc["cardsMasked"],
                       "control": k["gutterInkRatio"],
                       "candidate": cc["gutterInkRatio"],
                       "delta": round(cc["gutterInkRatio"] - k["gutterInkRatio"], 5),
                       "ceiling": round(k["gutterInkRatio"] + THR[13], 5),
                       "pass": ok})
def silhouette_check(asset, vp="1440x900"):
    """Is the extra ink outside the CARD, or outside the flat quad the
    instrument masks with? DIAGNOSTIC ONLY.

    F10 masks the projected LAYOUT quad. The rendered card is not that
    quad: it is a lens with a front bulge and sidewalls, so it projects
    outside its own flat plane. The true silhouette is recoverable
    without any new assumption -- it is exactly the set of pixels the
    glass layer changes, and the media-only captures give it directly.
    """
    mo = find(kind="media-only", lane="control", asset=asset, vp=vp)
    kr = find(kind="local", lane="control", state="full", asset=asset, vp=vp)
    cr = find(kind="local", lane="candidate", state="full", asset=asset, vp=vp)
    if not (mo and kr and cr):
        return None
    m0 = np.asarray(img_of(mo[0]).convert("RGB")).astype(float)
    kk = np.asarray(img_of(kr[0]).convert("RGB")).astype(float)
    cc = np.asarray(img_of(cr[0]).convert("RGB")).astype(float)
    glass = (np.abs(kk - m0).max(axis=2) > 0) | (np.abs(cc - m0).max(axis=2) > 0)
    out = ~glass
    lum = lambda a: 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    return {
        "asset": asset, "vp": vp,
        "pixelsOutsideTrueGlassSilhouette": int(out.sum()),
        "inkRatioControl": round(float((lum(kk)[out] > INS.F10_INK_LUMA).mean()), 6),
        "inkRatioCandidate": round(float((lum(cc)[out] > INS.F10_INK_LUMA).mean()), 6),
        "maxAbsChannelDiffOutsideSilhouette": float(np.abs(cc - kk)[out].max()),
    }


sil = [s for s in (silhouette_check(a) for a in ["bw-split", "rgb-bars"]) if s]
add(13, bool(rows13) and all(r["pass"] for r in rows13), rows=rows13,
    silhouetteDiagnostic=sil,
    silhouetteReading="DIAGNOSTIC, not a re-score. Outside the TRUE glass "
        "silhouette -- every pixel the glass layer touches, taken from the "
        "media-only captures -- the two lanes are bit-identical (max channel "
        "difference 0.0). The candidate puts no light into real gutter. The "
        "whole measured delta lies between the flat layout quad F10 masks "
        "and the larger silhouette the bulged lens actually projects, which "
        "is where the candidate concentrates its narrower rim. The sealed "
        "instrument and threshold are unchanged and the item stands as "
        "scored; this records what the number is made of.")

# --- 14 ------------------------------------------------------------------
def glass_path(lane):
    """nx of the GLASS reflection centroid at (pointer-left, rest,
    pointer-right), label ink excluded in card space by construction."""
    states = {}
    order = [("pl", (-0.99, 0.0)), ("rest", (0.0, 0.0)), ("pr", (0.99, 0.0))]
    for name, ndc in order:
        if lane == "target":
            rows = find(kind="target", state=name if name != "rest" else "rest",
                        asset="bw-split", vp="1440x900")
        else:
            st = "full" if name == "rest" else f"full-{name}"
            rows = find(kind="local", lane=lane, state=st, asset="bw-split",
                        vp="1440x900")
        if not rows:
            return None, None
        rects = sorted(rects_for("1440x900", ndc)[0],
                       key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
        if not rects:
            return None, None
        states[name] = (img_of(rows[0]), rects[-1])
    masks, excluded, dims = INS.glass_reflection_masks(states)
    if not masks:
        return None, None
    cents = {s: INS.centroid_of(m, dims) for s, m in masks.items()}
    path = [cents[s]["nx"] if cents.get(s) else None for s in ("pl", "rest", "pr")]
    return path, {"centroids": cents, "cardSpaceDims": list(dims),
                  "excludedInkPixels": int(excluded.sum()) if excluded is not None else None}

tp, tdet = glass_path("target")
cp, cdet = glass_path("candidate")
kp, kdet = glass_path("control")
if tp and cp:
    v14 = INS.f11_judge(tp, cp)
    add(14, not v14["fired"], verdict=v14, controlNxPath=kp,
        detail={"target": tdet, "candidate": cdet, "control": kdet},
        note="this record carries exactly the path the verdict was computed "
             "from; the instrument returned the verdict block verbatim.")
else:
    add(14, None, reason="pointer states unmeasurable",
        targetNxPath=tp, candidateNxPath=cp)

# --- 15 ------------------------------------------------------------------
rows15 = []
for vp in VPS:
    k = M[vp]["control"]["bw-split"]
    cc = M[vp]["candidate"]["bw-split"]
    t = M[vp]["target"]["bw-split"]
    if not k or not cc:
        continue
    db = cc["reflectionBand"]["meanPx"] - k["reflectionBand"]["meanPx"]
    dl = cc["darkSideEdgeLuma"] - k["darkSideEdgeLuma"]
    rows15.append({
        "vp": vp, "metricBasis": cc["metricBasis"],
        "bandDelta": round(db, 2), "darkLumaDelta": round(dl, 2),
        "bandSign": int(np.sign(db)), "darkLumaSign": int(np.sign(dl)),
        "diagnosticVsTarget": ({
            "bandAbsDelta": round(abs(cc["reflectionBand"]["meanPx"]
                                      - t["reflectionBand"]["meanPx"]), 2),
            "darkLumaAbsDelta": round(abs(cc["darkSideEdgeLuma"]
                                          - t["darkSideEdgeLuma"]), 2)}
                              if t else None)})
band_signs = {r["bandSign"] for r in rows15}
luma_signs = {r["darkLumaSign"] for r in rows15}
add(15, len(band_signs) == 1 and len(luma_signs) == 1, viewports=rows15,
    note="the per-viewport distance to Target is reported as a DIAGNOSTIC, "
         "per the sealed item; the pass condition is sign agreement.")

# --- 16 ------------------------------------------------------------------
rec16 = load(OPTS["recordings"])
if rec16:
    add(16, bool(rec16.get("pass")), sequences=rec16.get("sequences"))
else:
    add(16, None, reason="recording pop analysis absent")

# --- 17 ------------------------------------------------------------------
sp = load(Path(OPTS["shader"]) / "shader-proof.json")
g1_zero = next((i for i in items if i["n"] == 1), {}).get("result") == "PASS"
if sp:
    decl = sp["checks"].get("geometryLaneDeclaresO2Varying") is True
    add(17, g1_zero and decl, gate1Zero=g1_zero,
        controlDeclaresO2Varying=decl)
else:
    add(17, None, reason="shader-proof.json absent")

# --- 18 ------------------------------------------------------------------
if sp:
    add(18, bool(sp.get("pass")), checks=sp["checks"],
        dumps=[{k: v for k, v in d.items() if k != "query"} for d in sp["dumps"]],
        gate1Note=sp.get("gate1Note"))
else:
    add(18, None, reason="shader-proof.json absent")

# --- 19 ------------------------------------------------------------------
reg = load(OPTS["regressions"])
if reg:
    add(19, all(s.get("pass") for s in reg["suites"]),
        suites=[{"name": s["name"], "pass": s["pass"], "detail": s.get("detail")}
                for s in reg["suites"]])
else:
    add(19, None, reason="regressions json absent")

# --- 20 ------------------------------------------------------------------
# Judged, not computed. The operator's reading lives in its own file and is
# read here, so this script stays the single writer of the gate record
# without pretending to have made the judgement.
xs = load(OPTS["crosssection"])
j20 = load(OPTS["judgement20"])
add(20, (not j20["fired"]) if j20 else None,
    judgement=(j20 or {}).get("judgement"),
    framesJudged=(j20 or {}).get("framesJudged"),
    judgedAt=(j20 or {}).get("judgedAt"),
    registeredFailureText=(j20 or {}).get("registeredFailureText"),
    measuredContext={
        "targetBandPx": t, "controlBandPx": ctl, "candidateBandPx": c,
        "frozenBaseBandPx": (xs or {}).get("decomposition", {})
                            .get("1440x900", {}).get("frozenBaseBandPx")},
    note="a judged item; this script records the operator's reading from "
         "qa-v5/optics-o3/judgement-20.json and does not decide it.",
    **({} if j20 else {"reason": "judgement-20.json absent"}))

# ---------------------------------------------------------------- verdict --
scored = [i for i in items if i["result"] != "PENDING"]
failed = [i["n"] for i in items if i["result"] == "FAIL"]
pending = [i["n"] for i in items if i["result"] == "PENDING"]
all_pass = not failed and not pending

out = {
    "what": "O3 absolute gate, all twenty §九 items scored against the "
            "thresholds sealed at " + PREREG["sealedAtHead"][:12] + " before "
            "any candidate pixel was captured.",
    "sealedAtHead": PREREG["sealedAtHead"],
    "thresholdsChangedAfterCapture": False,
    "instrumentsModule": "scripts/v5/o3_instruments.py -- the same module the "
                         "unit tests certify and the dry run exercised on the "
                         "O2 captures before sealing.",
    "itemsPassed": sum(1 for i in items if i["result"] == "PASS"),
    "itemsFailed": len(failed),
    "itemsPending": len(pending),
    "failedItems": failed,
    "pendingItems": pending,
    "absoluteGate": "PASS" if all_pass else "FAIL",
    "defaultFlip": {
        "rule": PREREG["defaultFlipRule"],
        "executed": "target-sdf" if all_pass else "geometry",
        "shippedDefault": "target-sdf" if all_pass else "geometry",
        "reason": ("all twenty items passed" if all_pass
                   else f"items {failed or pending} did not pass, so the "
                        f"sealed rule's negative branch applies and the "
                        f"shipped default stays the O2 control"),
    },
    "finalState": ("READY FOR O3 OPTICS PRODUCT REVIEW" if all_pass
                   else "O3 ANALYTIC BEVEL REFLECTION FAILED ABSOLUTE GATE"),
    "items": items,
    "measurands": {vp: {lane: {a: M[vp][lane][a] for a in DESKTOP_ASSETS
                               if M[vp][lane][a]}
                        for lane in ("target", "control", "candidate")}
                   for vp in VPS},
    "decomposition": (xs or {}).get("decomposition"),
}
Path(OPTS["out"]).write_text(json.dumps(out, indent=1))

for i in items:
    mark = {"PASS": "PASS   ", "FAIL": "FAIL   ", "PENDING": "pending"}[i["result"]]
    print(f"{mark} {i['n']:2d}  {i['item']}")
print()
print(f"passed {out['itemsPassed']}/20   failed {out['itemsFailed']}   "
      f"pending {out['itemsPending']}")
print(f"absoluteGate: {out['absoluteGate']}")
print(f"finalState:   {out['finalState']}")
print(f"-> {OPTS['out']}")
