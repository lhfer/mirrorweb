#!/usr/bin/env python3
"""VC2 §九 -- summarise the bounded smoke into the public record.

The raw series stay in the private package; what is published here is the
shape of them plus the one thing a series cannot answer on its own: whether
any card went black. That is read off the stills the smoke took, by measuring
the mean luma inside each card's own projected rect -- a card that failed to
get its media would read near zero there while the page around it did not.

Usage: vc2-perf-summary.py [--raw=<json>] [--out=<json>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
ART = REPO / "artifacts/visual-convergence/perf"


def heap_trend(h: list[float]) -> dict:
    """Slope over the run and the floor the collector returns to, per third."""
    if len(h) < 6:
        return {"slopeMBPerMin": 0.0, "floorFirstThird": None, "floorLastThird": None}
    y = np.array(h, dtype=float)
    x = np.arange(y.size) * 5.0 / 60.0          # samples are 5 s apart
    slope = float(np.polyfit(x, y, 1)[0])
    k = y.size // 3
    return {"slopeMBPerMin": round(slope, 3),
            "floorFirstThird": round(float(y[:k].min()), 2),
            "floorLastThird": round(float(y[-k:].min()), 2)}


def rect_lumas(png: Path, rects: list) -> list[float]:
    a = np.asarray(Image.open(png).convert("RGB"), dtype=np.float64)
    y = 0.2126 * a[:, :, 0] + 0.7152 * a[:, :, 1] + 0.0722 * a[:, :, 2]
    out = []
    for r in rects:
        x0, y0, w, h = (int(round(v)) for v in r)
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(y.shape[1], x0 + max(w, 1)), min(y.shape[0], y0 + max(h, 1))
        if x1 <= x0 or y1 <= y0:
            continue
        out.append(round(float(y[y0:y1, x0:x1].mean()), 2))
    return out


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    raw_p = REPO / args.get("raw", "artifacts/visual-convergence/perf/perf-smoke-raw.json")
    raw = json.loads(raw_p.read_text())
    out_p = REPO / args.get("out", "qa-v5/visual-convergence/perf-smoke.json")
    # The stills the smoke took sit next to its raw series, wherever that is.
    # Pinning this to one round's directory made the black-card check silently
    # find nothing when the smoke was run into a different one.
    global ART
    ART = raw_p.parent

    doc = {"what": "VC2 §九 bounded candidate smoke -- ten minutes, real input, "
                   "High/Medium/Low exercised, and one phase under a 4x CPU throttle.",
           "url": raw["url"], "startedAt": raw["startedAt"],
           "realDeviceCaveat": raw["cpuThrottleNote"],
           "gestureCoverage": {
               "desktop": "drag, hard flick, long wrap-length drag; High/Medium/Low "
                          "each pinned for 9 s with adaptive off, adaptive back on "
                          "in between",
               "mobile": "touch drag, long wrap drag, reverse drag, plus a "
                         "portrait->landscape->portrait rotation every other cycle "
                         "with a drag taken in landscape. The rotation was added "
                         "this round because the one product change is on the "
                         "resize path, and it belongs under load and under the CPU "
                         "throttle rather than only in a clean trace.",
               "samplerNote": "the 5 s sampler runs through the rotations; a sample "
                              "that lands mid-resize is dropped by its own try/catch. "
                              "Sample counts per phase are reported below -- if the "
                              "mobile phase is short of the desktop phase, that is "
                              "why.",
           },
           "phases": []}
    for ph in raw["phases"]:
        s = ph["summary"]
        lumas = []
        for st in ph["stills"]:
            p = ART / st["file"]
            if p.exists() and st.get("rects"):
                lumas.append({"still": st["file"], "cardRects": len(st["rects"]),
                              "minRectLuma": min(rect_lumas(p, st["rects"]), default=None)})
        doc["phases"].append({
            "name": ph["name"], "vp": ph["vp"], "minutes": ph["minutes"],
            "cpuThrottlingRate": ph["cpuThrottlingRate"],
            "samples": s["samples"],
            "heapMB": {**s["heapMB"], **heap_trend([x["heapMB"] for x in ph["samples"]
                                                     if x["heapMB"]])},
            "fpsMean": s["fpsMean"], "frameP95ms": s["frameP95ms"],
            "qualityLevelsSeen": s["qualityLevelsSeen"],
            "qualitySeries": s["qualitySeries"],
            "materialCache": {"first": s["cacheFirst"], "last": s["cacheLast"],
                              "constant": s["cacheFirst"] == s["cacheLast"]},
            "videoAdvancing": s["videoAdvancing"],
            "blackCards": lumas,
            "errors": ph["errors"],
        })
    doc["assertions"] = [
        {"assertion": "no card rect went black in any sampled still",
         "pass": all(l["minRectLuma"] is None or l["minRectLuma"] > 8
                     for p in doc["phases"] for l in p["blackCards"]),
         "detail": {p["name"]: [l["minRectLuma"] for l in p["blackCards"]]
                    for p in doc["phases"]}},
        {"assertion": "the material cache neither grew nor churned across either phase",
         "pass": all(p["materialCache"]["constant"] for p in doc["phases"]),
         "detail": {p["name"]: p["materialCache"] for p in doc["phases"]}},
        # The heap sawtooths between roughly 14 and 48 MB on both phases. On a
        # sawtooth, both first-vs-last and a least-squares slope mostly measure
        # WHERE in the cycle the samples landed -- the desktop phase reads
        # +1.09 MB/min and the mobile phase +1.85 MB/min while the floor the
        # collector returns to barely moves. The floor is the retention signal, so
        # the floor is the gate; the slope is published beside it rather than
        # dropped, and the residual it points at is named in `heapResidual`.
        {"assertion": "no heap retention: the GC floor rises by at most 6 MB across "
                      "either phase",
         "pass": all(p["heapMB"]["floorLastThird"] <= p["heapMB"]["floorFirstThird"] + 6
                     for p in doc["phases"]),
         "detail": {p["name"]: p["heapMB"] for p in doc["phases"]}},
        {"assertion": "all three quality levels were actually exercised on the desktop phase",
         "pass": len(doc["phases"][0]["qualityLevelsSeen"]) >= 3,
         "detail": doc["phases"][0]["qualityLevelsSeen"]},
        {"assertion": "media kept advancing on both phases",
         "pass": all(p["videoAdvancing"] for p in doc["phases"])},
        {"assertion": "zero console or page errors",
         "pass": not any(p["errors"] for p in doc["phases"]),
         "detail": {p["name"]: p["errors"][:3] for p in doc["phases"]}},
    ]
    doc["heapResidual"] = {
        "what": "what the floor test allows and does not claim to be zero",
        "floorRiseMB": {p["name"]: round(p["heapMB"]["floorLastThird"]
                                         - p["heapMB"]["floorFirstThird"], 2)
                        for p in doc["phases"]},
        "note": "a five-minute window is short for a retention estimate. The mobile "
                "floor rise is the number to re-measure if a longer run is ever asked "
                "for; it is not asserted to be zero here.",
    }
    doc["verdict"] = "SMOKE CLEAN" if all(a["pass"] for a in doc["assertions"]) else "SMOKE FLAGGED"
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    for a in doc["assertions"]:
        print(f"  {'PASS' if a['pass'] else 'FLAG'}  {a['assertion']}")
    print(f"{doc['verdict']}\n-> {out_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
