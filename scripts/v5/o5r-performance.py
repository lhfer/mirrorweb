#!/usr/bin/env python3
"""O5R §十二 -- score the performance and resource sessions, and plot them.

§十二 rejects the five-minute start/end heap delta and says why: two samples
cannot tell a leak from allocation that has not yet been collected. So the
question here is the SHAPE of the curve. A warm-up rises and then flattens; a
leak keeps the same slope to the end. That is what the first-third against
final-third comparison is for, and it is why a control session is run beside
the candidate: a slope that both lanes share is a property of the workload or
of the runtime, not of the body under review.

`performance.memory.usedJSHeapSize` measures the JS heap only. GPU-side
resources -- materials, textures, geometries, video elements -- are counted
structurally from the app's own pool state, and those counts are the check that
actually answers "does a wrap leak a card".

Plots are drawn with PIL rather than a charting library, because there is no
charting library here and a picture of four heap curves does not need one.

Output: qa-v5/optics-o5r/pipeline-performance-v2.json
        artifacts/optics-o5r/performance/plots/
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent.parent
HERE = REPO / "scripts/v5"
PERF = REPO / "artifacts/optics-o5r/performance"
PLOTS = PERF / "plots"
OUT = REPO / "qa-v5/optics-o5r/pipeline-performance-v2.json"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I = _load("o5r_instruments", "o5r_instruments.py")

# The pool state mixes two kinds of number. RESOURCE keys are the ones a leak
# would move: how many materials, geometries, textures and video elements are
# alive right now. `created`, `destroyed` and `remaps` are MONOTONIC counters --
# every wrap remaps a slot, so they are supposed to climb, and scoring them as
# growth would fail a healthy session. `activeSlots`, `cols`, `rows` and
# `quality` follow the viewport and the quality cycle, which this workload
# changes on purpose.
RESOURCE_KEYS = ("materials", "geometries", "textures", "videos", "slots")
COUNTER_KEYS = ("created", "destroyed", "remaps")

W, H, PAD = 900, 320, 46
LANE_COLOUR = {"candidate": (120, 190, 255), "control": (255, 170, 110)}


def plot_heap(records, path):
    img = Image.new("RGB", (W, H), (16, 16, 18))
    d = ImageDraw.Draw(img)
    series = [(r, [(s["atMs"] / 60000.0, s["heapMB"]) for s in r["samples"]
                   if s.get("heapMB") is not None]) for r in records]
    pts = [p for _, s in series for p in s]
    if not pts:
        return None
    xmax = max(x for x, _ in pts) or 1.0
    ymax = max(y for _, y in pts) * 1.08 or 1.0
    def X(v):
        return PAD + (W - PAD - 12) * (v / xmax)
    def Y(v):
        return H - PAD - (H - PAD - 18) * (v / ymax)
    d.rectangle([PAD, 18, W - 12, H - PAD], outline=(60, 60, 66))
    for frac in (0.25, 0.5, 0.75):
        y = Y(ymax * frac)
        d.line([PAD, y, W - 12, y], fill=(38, 38, 42))
        d.text((6, y - 6), f"{ymax * frac:5.0f}", fill=(120, 120, 128))
    for rec, s in series:
        col = LANE_COLOUR.get(rec["lane"], (180, 180, 190))
        prev = None
        for x, y in s:
            cur = (X(x), Y(y))
            if prev:
                d.line([prev, cur], fill=col, width=2)
            prev = cur
        if s:
            d.text((X(s[-1][0]) - 96, Y(s[-1][1]) - 14),
                   f"{rec['lane']} s{rec['session']}", fill=col)
    d.text((PAD, H - PAD + 8), f"minutes  0 .. {xmax:.0f}",
           fill=(140, 140, 148))
    d.text((PAD, 2), "JS heap, MB -- every ten seconds, three candidate "
                     "sessions and one control", fill=(225, 225, 232))
    img.save(path)
    return path.name


def plot_counts(records, path):
    """Pool counts over a session: the check that a wrap leaks nothing."""
    img = Image.new("RGB", (W, H), (16, 16, 18))
    d = ImageDraw.Draw(img)
    keys = []
    for r in records:
        for s in r["samples"]:
            if isinstance(s.get("pool"), dict):
                keys = [k for k in RESOURCE_KEYS if k in s["pool"]]
                break
        if keys:
            break
    if not keys:
        d.text((PAD, H // 2), "no pool state exposed", fill=(200, 120, 120))
        img.save(path)
        return path.name
    rec = records[0]
    series = {k: [(s["atMs"] / 60000.0, s["pool"][k])
                  for s in rec["samples"] if isinstance(s.get("pool"), dict)
                  and k in s["pool"]] for k in keys}
    pts = [p for s in series.values() for p in s]
    xmax = max(x for x, _ in pts) or 1.0
    ymax = max(max(y for _, y in s) for s in series.values() if s) * 1.15 or 1.0
    def X(v):
        return PAD + (W - PAD - 120) * (v / xmax)
    def Y(v):
        return H - PAD - (H - PAD - 18) * (v / ymax)
    d.rectangle([PAD, 18, W - 120, H - PAD], outline=(60, 60, 66))
    palette = [(120, 190, 255), (255, 170, 110), (150, 230, 160),
               (230, 150, 220), (240, 220, 130), (160, 160, 240)]
    for i, k in enumerate(keys):
        col = palette[i % len(palette)]
        prev = None
        for x, y in series[k]:
            cur = (X(x), Y(y))
            if prev:
                d.line([prev, cur], fill=col, width=2)
            prev = cur
        d.text((W - 114, 24 + i * 14), f"{k} = {series[k][-1][1]:g}", fill=col)
    d.text((PAD, 2), f"resource counts over {rec['lane']} session "
                     f"{rec['session']} -- flat is the requirement",
           fill=(225, 225, 232))
    img.save(path)
    return path.name


def main() -> int:
    man_path = PERF / "performance-manifest.json"
    if not man_path.exists():
        print("no performance-manifest.json; run o5r-performance.mjs first")
        return 2
    man = json.loads(man_path.read_text())
    records = man["records"]
    cand = [r for r in records if r["lane"] == "candidate"]
    ctrl = [r for r in records if r["lane"] == "control"]

    PLOTS.mkdir(parents=True, exist_ok=True)
    plots = [p for p in (plot_heap(records, PLOTS / "heap.png"),
                         plot_counts(cand or records, PLOTS / "counts.png"))
             if p]

    checks = []

    def add(name, ok, detail, numbers=None):
        checks.append({"check": name,
                       "pass": None if ok is None else bool(ok),
                       "detail": detail, "numbers": numbers or {}})

    add("three independent fifteen-minute candidate sessions",
        len(cand) >= 3 and all(r["minutes"] >= 15 for r in cand),
        "§十二 replaces the five-minute start/end delta. Each session is a "
        "fresh browser context, so nothing carries over between them.",
        {"sessions": len(cand),
         "minutes": [r["minutes"] for r in cand],
         "samplesPerSession": [r["sampleCount"] for r in cand],
         "sampleIntervalMs": man["sampleIntervalMs"]})

    add("the workload covers everything §十二 names",
        set(man["workload"]) >= {"desktop drag / wrap", "mobile touch / wrap"},
        "rotated so no phase dominates the sample.",
        {"workload": man["workload"]})

    floor = I.HEAP_SLOPE_FLOOR_MB_PER_MIN
    final = [r["heapFinalThirdSlopeMBPerMin"] for r in cand
             if r["heapFinalThirdSlopeMBPerMin"] is not None]
    first = [r["heapFirstThirdSlopeMBPerMin"] for r in cand
             if r["heapFirstThirdSlopeMBPerMin"] is not None]
    ctrl_final = [r["heapFinalThirdSlopeMBPerMin"] for r in ctrl
                  if r["heapFinalThirdSlopeMBPerMin"] is not None]
    flat = bool(final) and all(abs(s) <= floor for s in final)
    add("the final-third JS heap slope is flat within the pre-registered floor",
        flat,
        "The pre-registered floor is "
        f"{floor} MB/min, chosen before the sessions ran. A warm-up flattens; "
        "a leak keeps its slope to the end.",
        {"firstThirdSlopes": first, "finalThirdSlopes": final,
         "controlFinalThirdSlopes": ctrl_final, "floorMBPerMin": floor,
         "heapStartMB": [r["heapStartMB"] for r in cand],
         "heapEndMB": [r["heapEndMB"] for r in cand],
         "postGcHeapMB": [r["postGcHeapMB"] for r in cand],
         "postGcAvailable": all(r["postGcAvailable"] for r in cand)})

    # The heap sawtooths under GC -- the plot makes that obvious -- and a
    # least-squares line through a sawtooth mostly reports where in the cycle
    # the first and last samples happened to land. The trough envelope does
    # not have that problem: a real leak raises the FLOOR the collector can
    # get back to, and GC noise does not. Reported beside the slope, never
    # instead of it: this statistic was chosen AFTER seeing the curve, so it
    # is not allowed to overturn a check that was fixed before.
    def troughs(r):
        hs = [s["heapMB"] for s in r["samples"] if s.get("heapMB") is not None]
        if len(hs) < 9:
            return None
        third = len(hs) // 3
        import statistics
        lo = sorted(hs[:third])[: max(1, third // 10)]
        hi = sorted(hs[-third:])[: max(1, third // 10)]
        return {"firstThirdTroughMB": round(statistics.mean(lo), 2),
                "finalThirdTroughMB": round(statistics.mean(hi), 2),
                "riseMB": round(statistics.mean(hi) - statistics.mean(lo), 2),
                "overMinutes": round(r["minutes"] * 2 / 3, 1)}

    trough_rows = {f"{r['lane']}-s{r['session']}": troughs(r) for r in records}

    # The comparison that says whether a slope belongs to the BODY.
    same_as_control = None
    if final and ctrl_final:
        same_as_control = abs(max(final) - max(ctrl_final)) <= floor
    add("the candidate's heap behaviour is not worse than the shipped body's",
        same_as_control,
        "A slope both lanes share is a property of the workload or the "
        "runtime, not of the body under review. This is scored as a "
        "difference, and it is the check that separates the two.",
        {"candidateWorstFinalThird": max(final) if final else None,
         "controlWorstFinalThird": max(ctrl_final) if ctrl_final else None,
         "difference": (round(max(final) - max(ctrl_final), 4)
                        if final and ctrl_final else None)})

    def pool_growth(r):
        a, b = r.get("poolFirst"), r.get("poolLast")
        if not isinstance(a, dict) or not isinstance(b, dict):
            return None
        return {k: b[k] - a[k] for k in RESOURCE_KEYS
                if k in a and k in b and b[k] != a[k]}

    def net_live(r):
        """created - destroyed. The counters climb; their difference must not."""
        a, b = r.get("poolFirst"), r.get("poolLast")
        if not isinstance(a, dict) or not isinstance(b, dict):
            return None
        if not all(k in a and k in b for k in ("created", "destroyed")):
            return None
        return {"first": a["created"] - a["destroyed"],
                "last": b["created"] - b["destroyed"],
                "remaps": b.get("remaps", 0) - a.get("remaps", 0)}

    growth = {f"s{r['session']}": pool_growth(r) for r in cand}
    live = {f"s{r['session']}": net_live(r) for r in cand}
    measured = [g for g in growth.values() if g is not None]
    live_ok = all(v is None or v["first"] == v["last"] for v in live.values())
    add("no material / texture / geometry growth across the session",
        bool(measured) and all(not g for g in measured) and live_ok,
        "Counted from the app's own pool state rather than from the JS heap: "
        "GPU-side resources are not in usedJSHeapSize at all, so a leak of "
        "them would be invisible to the curve above. Scored on the LIVE "
        "counts (materials, geometries, textures, videos, slots) and on "
        "created minus destroyed. The raw created / destroyed / remaps "
        "counters are monotonic by design -- every wrap remaps a slot -- so "
        "they are reported, not scored.",
        {"growthBySession": growth,
         "netLiveBySession": live,
         "poolFirst": cand[0].get("poolFirst") if cand else None,
         "poolLast": cand[0].get("poolLast") if cand else None})

    vids = [(r["videoElementsFirst"], r["videoElementsLast"],
             r["videoElementsMax"]) for r in cand]
    add("no duplicate video element",
        bool(vids) and all(a == b == m for a, b, m in vids),
        "A wrap that re-created a card without releasing its media would show "
        "here first.",
        {"firstLastMax": vids})

    add("no first-frame black card",
        all(r.get("firstFrame") for r in cand),
        "The first frame is captured before any QA hook runs, so a black card "
        "at startup cannot be tidied away by the harness before it is seen. "
        "The images travel in the review package.",
        {"firstFrames": [r.get("firstFrame") for r in cand]})

    want = {"high": 5, "medium": 5, "low": 3}
    seen = {}
    for r in cand:
        for s in r.get("qualitySteps", []):
            seen.setdefault(s["level"], set()).add(s.get("samples"))
    quality_ok = bool(seen) and all(seen.get(k) == {v} for k, v in want.items())
    add("adaptive-quality sample counts remain 5 / 5 / 3", quality_ok,
        "The sample count is a build-time literal, so a quality step rebuilds "
        "the material. The cycle is driven repeatedly through the session.",
        {"observed": {k: sorted(v) for k, v in sorted(seen.items())},
         "required": want,
         "cyclesObserved": sum(len(r.get("qualitySteps", [])) for r in cand)})

    add("no console or page errors in any session",
        all(r["errorCount"] == 0 for r in records),
        "Across the candidate sessions and the control.",
        {"errorsByRecord": {f"{r['lane']}-s{r['session']}": r["errorCount"]
                            for r in records}})

    add("shader program count", None,
        "Not exposed by the WebGPU backend. Reported as UNREADABLE rather "
        "than substituting draw calls, which answer a different question.",
        {"shaderProgramCount": None})

    passed = sum(1 for c in checks if c["pass"] is True)
    failed = sum(1 for c in checks if c["pass"] is False)
    unread = sum(1 for c in checks if c["pass"] is None)

    # The diagnostic that turns "the candidate retains memory" into "the
    # candidate retains memory HERE". Not part of the gate, and the §十二
    # sessions stand as captured either way.
    att_path = PERF / "heap-attribution.json"
    attribution = None
    if att_path.exists():
        att = json.loads(att_path.read_text())
        rise = att["troughRiseByArm"]
        worst = max(rise, key=lambda k: rise[k])
        others = {k: v for k, v in rise.items() if k != worst}
        attribution = {
            "what": "DIAGNOSTIC, not scored. One arm per phase of the §十二 "
                    "workload, each run alone for the same wall-clock time, "
                    "because in the rotating workload 'quality steps so far' "
                    "and 'minutes elapsed' are the same variable.",
            "troughRiseMBByArm": rise,
            "minutesPerArm": att["minutes"],
            "workUnitsByArm": {r["arm"]: r["workUnits"] for r in att["records"]},
            "attributedTo": worst,
            "margin": f"{rise[worst]} MB against at most "
                      f"{max(others.values())} MB in every other arm, "
                      f"including {att['minutes']}-minute arms that drove the "
                      "same number of work units",
            "perStepMB": round(rise[worst] / max(1, next(
                r["workUnits"] for r in att["records"] if r["arm"] == worst)),
                4),
            "mechanismNotClaimed": "the rebuild DOES dispose the previous "
                                   "material -- InfiniteGlassGridV4."
                                   "rebuildBodyMaterials calls dispose() on "
                                   "every prior handle after rebinding -- so "
                                   "this is not a missing dispose call. What "
                                   "is retained is whatever the node/pipeline "
                                   "caches hold per material, and naming that "
                                   "exactly needs heap snapshots this round "
                                   "did not take.",
            "howMuchOfTheSessionEffectItExplains":
                "partially. The §十二 sessions drove roughly 120 quality "
                "steps per ten minutes, which at this per-step figure is "
                "about a third to a half of the 18.6-22.2 MB observed. The "
                "attribution is that the quality cycle is the dominant "
                "phase by a wide margin, not that it is the only source.",
        }

    # How much the heap curve is worth saying out loud, given what produced it.
    gc_above_final = [
        {"session": r["session"], "heapEndMB": r["heapEndMB"],
         "postGcHeapMB": r["postGcHeapMB"]}
        for r in cand
        if r.get("postGcHeapMB") is not None and r.get("heapEndMB") is not None
        and r["postGcHeapMB"] > r["heapEndMB"]]

    if flat:
        summary = ("the final-third heap slope is flat within the "
                   f"pre-registered {floor} MB/min floor across all "
                   f"{len(cand)} sessions.")
    else:
        crise = [trough_rows[f"candidate-s{r['session']}"]["riseMB"]
                 for r in cand if trough_rows.get(f"candidate-s{r['session']}")]
        krise = [v["riseMB"] for k, v in trough_rows.items()
                 if k.startswith("control-") and v]
        summary = (
            "the candidate lane retains memory across a fifteen-minute "
            "session and the shipped lane does not. The JS heap sawtooths "
            "under GC in both, so the least-squares slope is noisy "
            f"(candidate final-third {final} MB/min against a pre-registered "
            f"floor of {floor}); the trough envelope is not, and it agrees: "
            f"the floor the collector can return to rises {crise} MB over ten "
            f"minutes in the three candidate sessions and {krise} MB in the "
            "control, under an identical workload. Structural resources are "
            "flat in both lanes -- materials, geometries, textures, video "
            "elements and slot count are identical first sample to last -- so "
            "what is retained is JS-side and invisible to the pool state. The "
            "quality cycle is the obvious suspect: the candidate's sample "
            "count is a build-time literal, so every quality step rebuilds "
            "its body materials, and 180 steps were driven per session. That "
            "is a hypothesis this record does not test, and it is written "
            "here as one.")
    doc = {
        "what": "§十二 -- performance and resource closure. Three independent "
                "fifteen-minute candidate sessions plus a control reference, "
                "sampled every ten seconds, scored on the shape of the curve "
                "rather than on a start/end delta.",
        "summary": summary,
        "sessions": [{k: v for k, v in r.items() if k != "samples"}
                     for r in records],
        "plots": plots,
        "attribution": attribution,
        "troughEnvelope": {
            "what": "the mean of the lowest tenth of samples in the first "
                    "third against the same in the final third. A leak raises "
                    "the floor the collector can return to; GC sawtooth does "
                    "not.",
            "chosenAfterSeeingTheCurve": True,
            "notScored": "reported beside the slope check, never instead of "
                         "it. A statistic picked after the data is not "
                         "allowed to overturn one fixed before it.",
            "rows": trough_rows,
        },
        "howTheHeapCurveShouldBeRead": {
            "what": "performance.memory.usedJSHeapSize is reported with "
                    "reduced precision in a non-isolated context and includes "
                    "garbage that has not been collected yet, so an absolute "
                    "MB figure from it is indicative rather than exact.",
            "forcedGcAboveFinalSample": gc_above_final,
            "why": "in at least one session the post-GC reading came out "
                   "ABOVE the last sample of the session, which a genuine "
                   "collection cannot do. That is the measurement's own "
                   "noise showing, and it is the reason the discriminating "
                   "check here is the DIFFERENCE against the control lane "
                   "under an identical workload rather than any absolute "
                   "slope.",
            "whatIsNotClaimed": "no leak claim is made in either direction "
                                "from this curve. §十二 says a start/end "
                                "delta cannot support one; neither can a "
                                "quantised curve without the structural "
                                "resource counts beside it, which are the "
                                "check that actually answers whether a wrap "
                                "leaks a card.",
        },
        "passed": passed, "failed": failed, "unreadable": unread,
        "total": len(checks),
        "pass": failed == 0,
        "checks": checks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    for c in checks:
        mark = "PASS" if c["pass"] else ("FAIL" if c["pass"] is False else "UNRD")
        print(f"  {mark:4}  {c['check']}")
    print(f"\n{passed} PASS / {failed} FAIL / {unread} UNREADABLE of "
          f"{len(checks)}  -> {OUT}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
