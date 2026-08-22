#!/usr/bin/env python3
"""O4 §九 absolute gate.

Every threshold is read from `qa-v5/optics-o4/gate-coding.json`, sealed at
66684dd before any gate pixel existed, and every instrument with a choice
in it comes from `o4_instruments.py`, sealed earlier still. Nothing here
chooses a coding.

Items whose inputs are missing report PENDING, never PASS.

Usage: o4-gate.py [--gate=<dir>] [--recordings=<json>] [--regressions=<json>]
       [--out=<json>]
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


S = _load("o4_gate_stats", "o2_optics_stats.py")
I = _load("o4_gate_ins", "o4_instruments.py")
VC, SL = sys.modules["v0_culling"], sys.modules["source_layout"]

OPTS = {"gate": REPO / "artifacts/optics-o4/gate",
        "coding": REPO / "qa-v5/optics-o4/gate-coding.json",
        "recordings": REPO / "artifacts/optics-o4/recordings/pop.json",
        "regressions": REPO / "artifacts/optics-o4/regressions/regressions.json",
        "out": REPO / "qa-v5/optics-o4/body-floor-gate.json"}
for _a in sys.argv[1:]:
    _k, _, _v = _a.lstrip("-").partition("=")
    if _k in OPTS:
        OPTS[_k] = Path(_v)

GD = Path(OPTS["gate"])
MAN = json.loads((GD / "gate-manifest.json").read_text())
CODING = json.loads(Path(OPTS["coding"]).read_text())
VPS = ["1440x900", "390x844", "844x390"]
SATURATED = ["rgb-bars", "cool-blue", "warm-skin"]
DESKTOP = ["bw-split", "grayscale-step", "rgb-bars", "hf-checker",
           "cool-blue", "warm-skin", "dark-highlight", "bright-lowsat"]


def find(**kw):
    return [r for r in MAN["records"]
            if all(r.get(k) == v for k, v in kw.items())]


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


def stats_of(lane, state, asset, vp):
    rows = find(kind="lane", lane=lane, state=state, asset=asset, vp=vp)
    if not rows:
        return None
    rects, basis = rects_for(vp)
    if not rects:
        return None
    img = Image.open(GD / rows[0]["file"])
    w, h = (int(x) for x in vp.split("x"))
    out = dict(S.stats(img, rects, w, h))
    out.update(S.side_bands(img, rects))
    out.update(S.interior_stats(img, rects))
    out["bandWidthPx"] = I.band_width_px(img, rects)["meanPx"]
    out["bandEnergy"] = I.band_energy(img, rects)["meanEnergy"]
    out["metricBasis"] = basis
    out["file"] = rows[0]["file"]
    return out


def hf_energy(path, rects):
    """Mean |4-neighbour Laplacian| of luma over the card interior."""
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    vals = []
    for (x0, y0, x1, y1) in rects:
        cw, ch = x1 - x0, y1 - y0
        p = lum[y0 + int(ch * .225):y1 - int(ch * .225),
                x0 + int(cw * .225):x1 - int(cw * .225)]
        lap = (4 * p[1:-1, 1:-1] - p[:-2, 1:-1] - p[2:, 1:-1]
               - p[1:-1, :-2] - p[1:-1, 2:])
        vals.append(float(np.abs(lap).mean()))
    return round(float(np.mean(vals)), 4)


def pixdiff(pa, pb):
    a = np.asarray(Image.open(pa).convert("RGB")).astype(int)
    b = np.asarray(Image.open(pb).convert("RGB")).astype(int)
    if a.shape != b.shape:
        return {"comparable": False}
    d = np.abs(a - b).max(axis=2)
    return {"differingPixels": int((d > 0).sum()), "maxChannelDelta": int(d.max())}


def load(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


items = []


def add(n, title, passed, **detail):
    items.append({"n": n, "item": title,
                  "result": ("PASS" if passed else "FAIL")
                            if passed is not None else "PENDING", **detail})


PG = CODING["primaryGate"]

# --- 1 / 2 / 3 : the primary gate, System B OFF ---------------------------
floor_rows = []
for vp in VPS:
    anch = PG["anchors"][vp]
    c = stats_of("control", "sysBOff", "bw-split", vp)
    k = stats_of("candidate", "sysBOff", "bw-split", vp)
    if not c or not k:
        continue
    red = (c["bandWidthPx"] - k["bandWidthPx"]) / max(c["bandWidthPx"], 1e-9)
    dist = abs(k["bandWidthPx"] - anch["targetBandPx"])
    ctl_dist = abs(c["bandWidthPx"] - anch["targetBandPx"])
    floor_rows.append({
        "vp": vp, "metricBasis": k["metricBasis"],
        "targetBandPx": anch["targetBandPx"],
        "controlBandPx": c["bandWidthPx"], "candidateBandPx": k["bandWidthPx"],
        "reductionFraction": round(float(red), 4),
        "item1Pass": bool(red >= PG["item1"]["threshold"]),
        "distanceToTargetPx": round(float(dist), 2),
        "controlDistanceToTargetPx": round(float(ctl_dist), 2),
        "item2Pass": bool(dist <= PG["item2"]["thresholdPx"]),
        "item2Side": ("under Target" if k["bandWidthPx"] < anch["targetBandPx"]
                      else "over Target"),
        "controlDarkLuma": c["darkSideEdgeLuma"],
        "candidateDarkLuma": k["darkSideEdgeLuma"],
        "targetDarkLumaFullRender": PG["item3"]["targetDarkSideEdgeLuma"],
        "item3Pass": bool(abs(k["darkSideEdgeLuma"] - PG["item3"]["targetDarkSideEdgeLuma"])
                          < abs(c["darkSideEdgeLuma"] - PG["item3"]["targetDarkSideEdgeLuma"])),
        "controlBandEnergy": c["bandEnergy"],
        "candidateBandEnergy": k["bandEnergy"],
    })
# The primary gate is scored at System B OFF, as §九 specifies. But the
# product ships with System B ON, and the same two measurands there say
# something the System-B-OFF numbers cannot: how much of the SHIPPED band
# is body at all. Recorded as a diagnostic beside the scored items, never
# in place of them.
shipped_rows = []
for vp in VPS:
    c = stats_of("control", "sysBOn", "bw-split", vp)
    k = stats_of("candidate", "sysBOn", "bw-split", vp)
    off_c = stats_of("control", "sysBOff", "bw-split", vp)
    off_k = stats_of("candidate", "sysBOff", "bw-split", vp)
    if not (c and k and off_c and off_k):
        continue
    shipped_rows.append({
        "vp": vp, "targetBandPx": PG["anchors"][vp]["targetBandPx"],
        "controlShippedBandPx": c["bandWidthPx"],
        "candidateShippedBandPx": k["bandWidthPx"],
        "controlBodyFloorPx": off_c["bandWidthPx"],
        "candidateBodyFloorPx": off_k["bandWidthPx"],
        "systemBAddsToControlPx": round(c["bandWidthPx"] - off_c["bandWidthPx"], 2),
        "systemBAddsToCandidatePx": round(k["bandWidthPx"] - off_k["bandWidthPx"], 2),
        "controlShippedDarkLuma": c["darkSideEdgeLuma"],
        "candidateShippedDarkLuma": k["darkSideEdgeLuma"],
    })
SHIPPED_DIAG = {
    "what": "DIAGNOSTIC, not a scored item. The same measurands in the "
            "SHIPPED state (System B ON, shell off).",
    "rows": shipped_rows,
    "reading": "removing the local adaptive body shaping takes the body "
               "floor below the Target's whole band, but the shipped band "
               "barely moves, because with the body dark the O2 reflection "
               "support paints the band on its own. O3 showed the support "
               "field is not the binding constraint given this body; O4 "
               "shows the body is not the binding constraint given this "
               "support. Both are constraints, and neither round was "
               "permitted to change the other.",
}

add(1, "body floor reduced by >= 40%",
    bool(floor_rows) and all(r["item1Pass"] for r in floor_rows),
    threshold=PG["item1"]["threshold"], viewports=floor_rows,
    shippedStateDiagnostic=SHIPPED_DIAG)
add(2, "candidate enters the Target window (two-sided)",
    bool(floor_rows) and all(r["item2Pass"] for r in floor_rows),
    thresholdPx=PG["item2"]["thresholdPx"],
    note=PG["item2"]["note"],
    reading="the candidate UNDERSHOOTS at every viewport: removing the "
            "adaptive shaping leaves LESS light at the dark-side edge than "
            "the Target has. The comparison §九 mandates is asymmetric and "
            "that is recorded, not argued around -- our System-B-OFF floor "
            "against the Target's full render, which includes the Target's "
            "own rim and environment. See shippedStateDiagnostic on item 1.",
    viewports=[{k: v for k, v in r.items()
                if k in ("vp", "targetBandPx", "candidateBandPx",
                         "distanceToTargetPx", "item2Pass", "item2Side")}
               for r in floor_rows])
add(3, "dark-side body luma moves toward the Target",
    bool(floor_rows) and all(r["item3Pass"] for r in floor_rows),
    basisNote=PG["item3"]["targetLumaBasisNote"],
    reading="the candidate moves AWAY from 48.1 because it removes light "
            "the Target replaces with its own reflection. In the shipped "
            "state the same measurand moves TOWARD the Target on every "
            "viewport (95.1 -> 82.9 desktop); that is the diagnostic on "
            "item 1, and it does not change this item's scored result.",
    viewports=[{k: v for k, v in r.items()
                if k in ("vp", "controlDarkLuma", "candidateDarkLuma",
                         "targetDarkLumaFullRender", "item3Pass")}
               for r in floor_rows])

# --- shipped-state product items ------------------------------------------
SHIPPED = "sysBOn"
c4 = stats_of("control", SHIPPED, "grayscale-step", "1440x900")
k4 = stats_of("candidate", SHIPPED, "grayscale-step", "1440x900")
t4 = CODING["item4"]["threshold"]
add(4, CODING["item4"]["title"],
    bool(c4 and k4) and k4["edgeChromaMean"] <= c4["edgeChromaMean"] + t4
    and k4["interiorChromaMean"] <= c4["interiorChromaMean"] + t4,
    threshold=t4, scoredInState=SHIPPED,
    edgeChroma={"control": c4 and c4["edgeChromaMean"],
                "candidate": k4 and k4["edgeChromaMean"]},
    interiorChroma={"control": c4 and c4["interiorChromaMean"],
                    "candidate": k4 and k4["interiorChromaMean"]})

rows5 = []
for a in SATURATED:
    c, k = stats_of("control", SHIPPED, a, "1440x900"), stats_of("candidate", SHIPPED, a, "1440x900")
    if not c or not k:
        continue
    t = CODING["item5"]["threshold"]
    rows5.append({"asset": a,
                  "fringeRB": {"control": c["fringeRB"], "candidate": k["fringeRB"],
                               "pass": k["fringeRB"] <= c["fringeRB"] + t},
                  "fringeWidthPxMean": {"control": c["fringeWidthPxMean"],
                                        "candidate": k["fringeWidthPxMean"],
                                        "pass": k["fringeWidthPxMean"]
                                                <= c["fringeWidthPxMean"] + t}})
    rows5[-1]["pass"] = (rows5[-1]["fringeRB"]["pass"]
                         and rows5[-1]["fringeWidthPxMean"]["pass"])
add(5, CODING["item5"]["title"],
    bool(rows5) and all(r["pass"] for r in rows5),
    threshold=CODING["item5"]["threshold"], scoredInState=SHIPPED, assets=rows5)

rects_d, _ = rects_for("1440x900")
hf_rows = {}
for lane in ("control", "candidate"):
    rr = find(kind="lane", lane=lane, state=SHIPPED, asset="hf-checker", vp="1440x900")
    if rr:
        hf_rows[lane] = hf_energy(GD / rr[0]["file"], rects_d)
mo_hf = find(kind="media-only", lane="control", asset="hf-checker", vp="1440x900")
add(6, CODING["item6"]["title"],
    len(hf_rows) == 2 and hf_rows["candidate"]
    >= CODING["item6"]["threshold"] * hf_rows["control"],
    threshold=CODING["item6"]["threshold"], scoredInState=SHIPPED,
    hfEnergy={**hf_rows,
              "mediaOnlyReference": (hf_energy(GD / mo_hf[0]["file"], rects_d)
                                     if mo_hf else None)},
    ratio=(round(hf_rows["candidate"] / hf_rows["control"], 4)
           if len(hf_rows) == 2 and hf_rows["control"] else None),
    reading="the two lanes are bit-identical in the card INTERIOR, which is "
            "why the ratio is exactly 1.0. That is by design rather than by "
            "accident: every adaptive term is gated on blurZone and "
            "curvature, both of which are zero on the clear centre face, so "
            "the subsystem the candidate removes never acted there. The "
            "media-only reference is null because media-only frames were "
            "captured for bw-split and rgb-bars only.")

rows7 = []
for a in DESKTOP:
    c, k = stats_of("control", SHIPPED, a, "1440x900"), stats_of("candidate", SHIPPED, a, "1440x900")
    if not c or not k:
        continue
    rows7.append({"asset": a, **I.interior_change(c, k)})
add(7, CODING["item7"]["title"],
    bool(rows7) and all(not r["fired"] for r in rows7),
    scoredInState=SHIPPED, assets=rows7)

rows8 = []
for rec in find(kind="media-only", lane="candidate"):
    ctl = find(kind="media-only", lane="control", asset=rec["asset"], vp=rec["vp"])
    if ctl:
        rows8.append({"asset": rec["asset"], "vp": rec["vp"],
                      **pixdiff(GD / rec["file"], GD / ctl[0]["file"])})
add(8, CODING["item8"]["title"],
    bool(rows8) and all(r.get("differingPixels") == 0 for r in rows8),
    pairs=rows8)

rows9 = []
for asset in ["bw-split", "rgb-bars"]:
    mo = find(kind="media-only", lane="control", asset=asset, vp="1440x900")
    c = find(kind="lane", lane="control", state=SHIPPED, asset=asset, vp="1440x900")
    k = find(kind="lane", lane="candidate", state=SHIPPED, asset=asset, vp="1440x900")
    if not (mo and c and k):
        continue
    sil = I.true_silhouette(GD / c[0]["file"], GD / mo[0]["file"])
    pair = I.gutter_pair_outside_silhouette(GD / c[0]["file"], GD / k[0]["file"], sil)
    # Where are the differing pixels? A silhouette derived from the CONTROL
    # lane has a one-pixel antialiased boundary: a pixel the control lifts
    # by one level and the candidate does not falls just outside it while
    # still being glass. Measuring the distance separates that from a real
    # leak into the gutter.
    a_ = np.asarray(Image.open(GD / c[0]["file"]).convert("RGB")).astype(int)
    b_ = np.asarray(Image.open(GD / k[0]["file"]).convert("RGB")).astype(int)
    dmask = (np.abs(a_ - b_).max(axis=2) > 0) & (~sil)
    grown = sil.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(sil, dy, axis=0), dx, axis=1)
    rows9.append({"asset": asset, "silhouettePixels": int(sil.sum()), **pair,
                  "differingWithin1pxOfSilhouette": int((dmask & grown).sum()),
                  "differingBeyond1pxOfSilhouette": int((dmask & ~grown).sum())})
add(9, CODING["item9"]["title"],
    bool(rows9) and all(r["differingPixelsOutsideSilhouette"] == 0 for r in rows9),
    scoredInState=SHIPPED, why=CODING["item9"]["why"], rows=rows9,
    reading="every differing pixel lies within ONE pixel of the true "
            "silhouette, at a maximum of 2 and 5 levels. They are the "
            "antialiased boundary of a silhouette derived from the control "
            "lane, not light in the gutter -- beyond 1 px the two lanes are "
            "identical. The sealed threshold is exactly zero and the item "
            "stands as scored; this records what the number is made of.")

rec10 = load(OPTS["recordings"])
add(10, CODING["item10"]["title"],
    bool(rec10.get("pass")) if rec10 else None,
    sequences=rec10.get("sequences") if rec10 else None,
    reason=None if rec10 else "recording pop analysis absent")

rows11 = []
for rec in find(kind="lane", lane="baseline-e913aa6", state="sysBOff"):
    ours = find(kind="lane", lane="control", state="sysBOff",
                asset=rec["asset"], vp=rec["vp"])
    if ours:
        rows11.append({"asset": rec["asset"], "vp": rec["vp"],
                       **pixdiff(GD / ours[0]["file"], GD / rec["file"])})
add(11, CODING["item11"]["title"],
    bool(rows11) and all(r.get("differingPixels") == 0 for r in rows11),
    cases=rows11)

reg = load(OPTS["regressions"])
add(12, CODING["item12"]["title"],
    all(s.get("pass") for s in reg["suites"]) if reg else None,
    suites=[{"name": s["name"], "pass": s["pass"]} for s in reg["suites"]]
    if reg else None,
    reason=None if reg else "regressions json absent")

errs = sum(r.get("errorCount", 0) for r in find(kind="errors"))
failed = [i["n"] for i in items if i["result"] == "FAIL"]
pending = [i["n"] for i in items if i["result"] == "PENDING"]
ok = not failed and not pending

doc = {
    "what": "O4 §九 absolute gate. Thresholds from gate-coding.json, sealed "
            "at " + CODING["sealedAtHead"][:12] + " before any gate pixel "
            "existed; instruments from o4_instruments.py, sealed earlier.",
    "codingSealedAtHead": CODING["sealedAtHead"],
    "thresholdsChangedAfterCapture": False,
    "scoringStates": {
        "itemsOneToThree": "System B OFF -- §九's primary gate state",
        "itemsFourToNine": "System B ON (shell off) -- the SHIPPED state, "
                           "because these are product-quality statements "
                           "about what a user sees. Both states were captured "
                           "and both are in the manifest.",
    },
    "consoleAndPageErrors": errs,
    "itemsPassed": sum(1 for i in items if i["result"] == "PASS"),
    "itemsFailed": len(failed), "itemsPending": len(pending),
    "failedItems": failed, "pendingItems": pending,
    "absoluteGate": "PASS" if ok else "FAIL",
    "shippedDefault": "current",
    "defaultFlip": "not executed -- this brief registers no automatic flip "
                   "and its final states do not include one; the product "
                   "review owns that decision and reads this file.",
    "finalState": ("READY FOR O4 BODY FLOOR PRODUCT REVIEW" if ok
                   else "O4 SELECTED BODY CANDIDATE FAILED ABSOLUTE GATE"),
    "items": items,
}
Path(OPTS["out"]).write_text(json.dumps(doc, indent=1))
for i in items:
    print(f"{i['result']:7s} {i['n']:2d}  {i['item']}")
print(f"\npassed {doc['itemsPassed']}/12  failed {doc['itemsFailed']}  "
      f"pending {doc['itemsPending']}")
print(f"absoluteGate: {doc['absoluteGate']}")
print(f"finalState:   {doc['finalState']}")
print(f"-> {OPTS['out']}")
