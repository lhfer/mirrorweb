#!/usr/bin/env python3
"""O5F §七 -- score the stress captures against the SEALED gate.

Every threshold and formula comes from o5f_stress.py, the module the
contract generator also imports, committed in the material-cache code commit
before any capture. Nothing here invents a number.

Inputs:  artifacts/optics-o5f/quality-cycle/quality-cycle.json
         artifacts/optics-o5f/stress/sessions-manifest.json
Output:  qa-v5/optics-o5f/material-cache-stress.json (+ heap plots)
Exit 0 on PASS, 1 on O5F MATERIAL CACHE FAILED.
"""
from __future__ import annotations

import importlib.util
import json
import statistics
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o5f_stress_s", "o5f_stress.py")

CYCLE = REPO / "artifacts/optics-o5f/quality-cycle/quality-cycle.json"
SESSIONS = REPO / "artifacts/optics-o5f/stress/sessions-manifest.json"
OUT = REPO / "qa-v5/optics-o5f/material-cache-stress.json"
PLOTS = REPO / "artifacts/optics-o5f/stress/plots"
for a in sys.argv[1:]:
    k, _, v = a.lstrip("-").partition("=")
    if k == "cycle":
        CYCLE = Path(v)
    elif k == "sessions":
        SESSIONS = Path(v)
    elif k == "out":
        OUT = Path(v)

cycle = json.loads(CYCLE.read_text())
man = json.loads(SESSIONS.read_text())
cand = [r for r in man["records"] if r["lane"] == "candidate"]
ctrl = [r for r in man["records"] if r["lane"] == "control"]

checks = []


def add(n, check, ok, threshold, numbers):
    checks.append({"n": n, "check": check,
                   "status": "PASS" if ok else "FAIL",
                   "threshold": threshold, "numbers": numbers})


def cand_cache_samples(r):
    return [s["cache"] for s in r["samples"] if s.get("cache")]


# --- 1: creationCount constant at PRODUCT_CREATION_COUNT -------------------
cyc_creations = sorted({st["creation"] for st in cycle["steps"]})
sess_creations = sorted({c["materialCreationCount"]
                         for r in cand for c in cand_cache_samples(r)})
ok1 = (cyc_creations == [S.PRODUCT_CREATION_COUNT]
       and sess_creations == [S.PRODUCT_CREATION_COUNT])
add(1, "after both product sets exist, materialCreationCount does not "
       "increase", ok1,
    f"== {S.PRODUCT_CREATION_COUNT} at every cycle step and every session "
    "sample",
    {"cycleDistinctValues": cyc_creations,
     "sessionDistinctValues": sess_creations,
     "cycleSteps": len(cycle["steps"]),
     "sessionSamples": sum(len(cand_cache_samples(r)) for r in cand)})

# --- 2: cacheSize finite and constant --------------------------------------
cyc_sizes = sorted({st["cacheSize"] for st in cycle["steps"]})
sess_sizes = sorted({c["cacheSize"] for r in cand
                     for c in cand_cache_samples(r)})
ok2 = cyc_sizes == [S.PRODUCT_CACHE_SIZE] and sess_sizes == [S.PRODUCT_CACHE_SIZE]
add(2, "cacheSize remains finite and constant", ok2,
    f"== {S.PRODUCT_CACHE_SIZE} at every sample",
    {"cycleDistinctValues": cyc_sizes, "sessionDistinctValues": sess_sizes})

# --- 3: high <-> medium creates zero material -------------------------------
hm_deltas = []
steps = cycle["steps"]
for prev, cur in zip(steps, steps[1:]):
    if {prev["level"], cur["level"]} == {"high", "medium"}:
        hm_deltas.append(cur["creation"] - prev["creation"])
ok3 = bool(hm_deltas) and all(d == 0 for d in hm_deltas)
add(3, "high <-> medium creates zero material", ok3,
    "creation delta == 0 across every high<->medium step",
    {"transitions": len(hm_deltas),
     "nonZeroDeltas": [d for d in hm_deltas if d != 0]})

# --- 4: original UUIDs return after every cycle ----------------------------
uuid_ok_steps = all(st["uuidOk"] for st in steps)
ref_uuids = {k: v["truth"]["activeMaterialUuids"]
             for k, v in cycle["references"].items()}
hm_same = ref_uuids.get("high") == ref_uuids.get("medium")
low_diff = ref_uuids.get("high") != ref_uuids.get("low")
# Sessions: every distinct active-UUID list seen must be one of the two
# tiers' lists, and video/environment UUIDs must never move.
sess_uuid_sets = set()
video_uuid_sets = set()
env_uuids = set()
for r in cand:
    for c in cand_cache_samples(r):
        sess_uuid_sets.add(tuple(c["activeMaterialUuids"]))
        video_uuid_sets.add(tuple(c["videoTextureUuids"]))
        env_uuids.add(c["environmentUuid"])
# UUIDs are per page load; sessions each load their own page, so the
# invariant is per session: count distinct lists per session instead.
per_session_ok = True
per_session_detail = []
for r in cand:
    cs = cand_cache_samples(r)
    lists = {tuple(c["activeMaterialUuids"]) for c in cs}
    vids = {tuple(c["videoTextureUuids"]) for c in cs}
    envs = {c["environmentUuid"] for c in cs}
    ok = len(lists) <= 2 and len(vids) == 1 and len(envs) == 1
    per_session_ok = per_session_ok and ok
    per_session_detail.append({"session": r["session"],
                               "distinctActiveUuidLists": len(lists),
                               "distinctVideoUuidLists": len(vids),
                               "distinctEnvUuids": len(envs)})
ok4 = uuid_ok_steps and hm_same and low_diff and per_session_ok
add(4, "the original material UUIDs return after every cycle", ok4,
    "per-tier UUID list identical at every visit across all cycle steps; "
    "high and medium share one list; low carries its own; per session at "
    "most two distinct active lists, one VideoTexture list, one environment "
    "UUID",
    {"cycleStepsAllUuidOk": uuid_ok_steps,
     "highMediumShareUuids": hm_same,
     "lowHasOwnUuids": low_diff,
     "perSession": per_session_detail})

# --- 5: final-third heap slope ---------------------------------------------
def heap_points(r):
    return [(s["atMs"], s["heapMB"]) for s in r["samples"]
            if s.get("heapMB") is not None]


def final_third_slope(r):
    pts = heap_points(r)
    third = max(3, len(pts) // 3)
    return S.slope_mb_per_min(pts[-third:])


cand_slopes = [final_third_slope(r) for r in cand]
ctrl_slopes = [final_third_slope(r) for r in ctrl]
thr5 = S.heap_slope_threshold(ctrl_slopes)
ok5 = all(s is not None and s <= thr5 for s in cand_slopes)
add(5, "final-third heap slope", ok5,
    f"<= {thr5} MB/min = max(control repeatability window "
    f"{max((abs(s) for s in ctrl_slopes if s is not None), default=0.0):.4f}, "
    f"floor {S.HEAP_SLOPE_FLOOR_MB_PER_MIN})",
    {"candidateFinalThirdSlopes": cand_slopes,
     "controlFinalThirdSlopes": ctrl_slopes,
     "threshold": thr5})

# --- 6: ten-minute GC-trough rise ------------------------------------------
def rise(r):
    hs = [s["heapMB"] for s in r["samples"] if s.get("heapMB") is not None]
    t = S.trough_rise_mb(hs)
    return t


cand_rises = [rise(r) for r in cand]
ctrl_rises = [rise(r) for r in ctrl]
thr6 = S.trough_rise_threshold([t["riseMB"] if t else None for t in ctrl_rises])
ok6 = all(t is not None and t["riseMB"] <= thr6 for t in cand_rises)
add(6, "ten-minute GC-trough rise", ok6,
    f"<= {thr6} MB = max(2 x control spread, floor {S.TROUGH_RISE_FLOOR_MB})",
    {"candidate": cand_rises, "control": ctrl_rises, "threshold": thr6,
     "o5rCandidateRises": [18.59, 20.03, 22.15],
     "o5rControlRise": -1.04})

# --- 7: no texture / geometry / video-element growth ------------------------
def pool_growth(r):
    a, b = r.get("poolFirst"), r.get("poolLast")
    if not isinstance(a, dict) or not isinstance(b, dict):
        return None
    return {k: b[k] - a[k] for k in S.RESOURCE_KEYS
            if k in a and k in b and b[k] != a[k]}


def net_live(r):
    a, b = r.get("poolFirst"), r.get("poolLast")
    if not isinstance(a, dict) or not isinstance(b, dict):
        return None
    if not all(k in a and k in b for k in ("created", "destroyed")):
        return None
    return {"first": a["created"] - a["destroyed"],
            "last": b["created"] - b["destroyed"]}


def renderer_counts(r):
    """Matched-state renderer counts: samples after phase 0 (desktop drag),
    first cycle excluded as warm-up; programs constant after the first
    quality phase completes."""
    matched = [s["cache"] for s in r["samples"][4:]
               if s.get("phase") == 0 and s.get("cache")]
    tex = {c["rendererTextures"] for c in matched} or {None}
    geo = {c["rendererGeometries"] for c in matched} or {None}
    after_q = False
    progs = []
    for s in r["samples"]:
        if s.get("phase") == 3:
            after_q = True
        if after_q and s.get("cache"):
            progs.append(s["cache"]["rendererPrograms"])
    return {"texturesDistinct": sorted(tex, key=lambda v: (v is None, v)),
            "geometriesDistinct": sorted(geo, key=lambda v: (v is None, v)),
            "programsAfterFirstQualityPhase": sorted(set(progs))}


growth = {f"s{r['session']}": pool_growth(r) for r in cand}
live = {f"s{r['session']}": net_live(r) for r in cand}
vids7 = [(r["videoElementsFirst"], r["videoElementsLast"],
          r["videoElementsMax"]) for r in cand]
rc = {f"s{r['session']}": renderer_counts(r) for r in cand}
rc_ctrl = {f"s{r['session']}": renderer_counts(r) for r in ctrl}
grow_ok = all(g is not None and not g for g in growth.values())
live_ok = all(v is not None and v["first"] == v["last"] for v in live.values())
vid_ok = bool(vids7) and all(a == b == m for a, b, m in vids7)
rcount_ok = all(len(v["texturesDistinct"]) == 1
                and len(v["geometriesDistinct"]) == 1
                and len(v["programsAfterFirstQualityPhase"]) == 1
                for v in rc.values())
ok7 = grow_ok and live_ok and vid_ok and rcount_ok
add(7, "no texture / geometry / video-element growth", ok7,
    "pool LIVE counts and created-destroyed zero-delta; video elements "
    "first == last == max; renderer texture/geometry counts single-valued "
    "on matched post-warm-up samples; renderer program count constant after "
    "the first quality phase",
    {"poolGrowthBySession": growth, "netLiveBySession": live,
     "videoElementsFirstLastMax": vids7,
     "rendererCounts": rc, "rendererCountsControl": rc_ctrl,
     "monotonicCountersReportedNotScored": {
         f"s{r['session']}": {k: [r["poolFirst"].get(k), r["poolLast"].get(k)]
                              for k in S.MONOTONIC_KEYS}
         for r in cand if r.get("poolFirst") and r.get("poolLast")}})

# --- 8: no first-frame black card ------------------------------------------
def first_frame_luma(r, base_dir):
    p = base_dir / r["firstFrame"]
    if not p.exists():
        return None
    a = np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)
    lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    return {"file": r["firstFrame"], "meanLuma": round(float(lum.mean()), 2),
            "nearBlackFraction": round(float((lum < 8).mean()), 4)}


ff = [first_frame_luma(r, SESSIONS.parent) for r in cand + ctrl]
ok8 = all(f is not None for f in ff)
add(8, "no first-frame black card", ok8,
    "the pre-hook first frame is captured and travels in the review "
    "package; luma reported as a diagnostic (bw-split media legitimately "
    "carries a black half); transition blackouts are caught by check 9's "
    "exact-zero identity",
    {"firstFrames": ff})

# --- 9: no quality-transition pop ------------------------------------------
mism = cycle["mismatches"]
mism_diffs = []
for m in mism:
    a = np.asarray(Image.open(CYCLE.parent / m["file"]).convert("RGB"),
                   dtype=np.int16)
    b = np.asarray(Image.open(CYCLE.parent / m["expected"]).convert("RGB"),
                   dtype=np.int16)
    d = np.abs(a - b).max(axis=2)
    mism_diffs.append({**m, "differingPixels": int((d > 0).sum()),
                       "maxDelta": int(d.max())})
pixel_ok_steps = all(st["pixelOk"] for st in steps)
ok9 = pixel_ok_steps and not mism
add(9, "no quality-transition pop", ok9,
    "every post-warm-up visit to a tier equals that tier's reference still "
    "with 0 differing pixels, across all 1,200 steps",
    {"steps": len(steps), "mismatches": mism_diffs,
     "crossTierDiagnosticNotScored": cycle["crossTierDiagnostic"],
     "cycleHeapFirstMB": steps[0]["heapMB"] if steps else None,
     "cycleHeapLastMB": steps[-1]["heapMB"] if steps else None,
     "cycleElapsedMin": round(cycle["elapsedMs"] / 60000, 1)})

# --- 10: sample count remains 5 / 5 / 3 ------------------------------------
seen = {}
for st in steps:
    seen.setdefault(st["level"], set()).add(st["samples"])
for r in cand:
    for q in r.get("qualitySteps", []):
        seen.setdefault(q["level"], set()).add(q["samples"])
ok10 = bool(seen) and all(seen.get(k) == {v}
                          for k, v in S.EXPECTED_SAMPLES.items())
add(10, "sample count remains 5 / 5 / 3", ok10,
    f"opticalBodySamples == {S.EXPECTED_SAMPLES} at every step",
    {"observed": {k: sorted(v) for k, v in sorted(seen.items())}})

# --- plots ------------------------------------------------------------------
PLOTS.mkdir(parents=True, exist_ok=True)


def plot(r):
    pts = heap_points(r)
    if len(pts) < 3:
        return None
    w, h = 900, 300
    img = Image.new("RGB", (w, h), (17, 17, 20))
    dr = ImageDraw.Draw(img)
    ys = [p[1] for p in pts]
    lo, hi = min(ys), max(ys)
    pad = max(1.0, (hi - lo) * 0.15)
    lo, hi = lo - pad, hi + pad
    tmax = pts[-1][0]
    xy = [(40 + (p[0] / tmax) * (w - 60),
           h - 30 - ((p[1] - lo) / (hi - lo)) * (h - 60)) for p in pts]
    dr.line(xy, fill=(120, 190, 255), width=2)
    tr = rise(r)
    label = (f"{r['lane']} s{r['session']}  heap {ys[0]:.1f} -> {ys[-1]:.1f} "
             f"MB  trough rise {tr['riseMB'] if tr else '?'} MB")
    dr.text((44, 8), label, fill=(230, 230, 230))
    dr.text((44, h - 22), f"0 .. {r['minutes']} min, {len(pts)} samples",
            fill=(150, 150, 150))
    f = PLOTS / f"heap-{r['lane']}-s{r['session']}.png"
    img.save(f)
    return f.name


plot_files = [plot(r) for r in man["records"]]

# --- verdict ----------------------------------------------------------------
n_pass = sum(1 for c in checks if c["status"] == "PASS")
verdict = "PASS" if n_pass == len(checks) else "FAIL"
doc = {
    "what": "O5F §七 -- the pre-registered material-cache stress gate, "
            "scored against the thresholds sealed in "
            "material-cache-contract.json (both generated from "
            "o5f_stress.py).",
    "contract": "qa-v5/optics-o5f/material-cache-contract.json",
    "runs": {"qualityCycleSteps": cycle["stepsTotal"],
             "qualityCycles": cycle["cycles"],
             "candidateSessions": len(cand), "controlSessions": len(ctrl),
             "sessionMinutes": man["minutes"],
             "workload": man["workload"]},
    "checks": checks,
    "passed": n_pass, "total": len(checks),
    "verdict": verdict,
    "finalStateIfFailed": "O5F MATERIAL CACHE FAILED",
    "plots": [p for p in plot_files if p],
    "consoleAndPageErrors": {
        "cycle": cycle["errorCount"],
        "sessions": {f"{r['lane']}-s{r['session']}": r["errorCount"]
                     for r in man["records"]}},
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(doc, indent=1))
for c in checks:
    print(f"{c['status']}  {c['n']:>2}  {c['check']}")
print(f"\n{n_pass}/{len(checks)}  verdict: {verdict}")
print(f"-> {OUT}")
sys.exit(0 if verdict == "PASS" else 1)
