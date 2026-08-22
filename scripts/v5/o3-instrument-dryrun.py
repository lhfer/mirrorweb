#!/usr/bin/env python3
"""Dry-run the corrected O3 instruments on the EXISTING O2 captures.

A corrected instrument that has only ever been run on synthetic input is
not validated. These are real frames -- Target and both O2 lanes, the
same deterministic media -- and none of them is an O3 candidate, so
nothing here can tune anything. What it answers before sealing:

  * does the Target's dark half retain enough MOVING bright pixels for
    the glass-only F11 to be measurable at all (if not, gate 14 would
    fire on the instrument rather than on the optics);
  * do the polygon-masked F10 numbers sit sanely against the AABB-masked
    numbers O2 recorded;
  * does the F5 baseline branch pick the coding the O2 record implies.

Usage: o3-instrument-dryrun.py --measure=<dir> --out=<json>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_load("v0_culling", "v0_culling.py")
_load("source_layout", "source_layout.py")
S = _load("o2_optics_stats", "o2_optics_stats.py")
I = _load("o3_instruments", "o3_instruments.py")

#: PINNED: the ink intersection uses EVERY captured pointer state (the
#: more states a bright pixel survives, the more certainly it is ink);
#: the path is judged on the three sweep states.
INK_STATES = [("pl", (-0.99, 0.0)), ("rest", (0.0, 0.0)),
              ("pr", (0.99, 0.0)), ("pbr", (0.99, 0.99))]
PATH_STATES = ["pl", "rest", "pr"]


def dark_half_rect(w, h, ndc):
    rects = sorted((r for _, r in S.rects_at(w, h, ndc)),
                   key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))
    if not rects:
        return None
    x0, y0, x1, y1 = rects[-1]
    return (x0, y0, (x0 + x1) // 2, y1)


def f11_for(measure: Path, files_by_state: dict, vp="1440x900") -> dict:
    w, h = map(int, vp.split("x"))
    states = {}
    for name, ndc in INK_STATES:
        f = files_by_state.get(name)
        rect = dark_half_rect(w, h, ndc)
        if f is None or rect is None or not (measure / f).exists():
            continue
        states[name] = (Image.open(measure / f), rect)
    masks, excluded, dims = I.glass_reflection_masks(states)
    cents = {s: I.centroid_of(m, dims) for s, m in masks.items()}
    return {
        "statesUsedForInk": sorted(states),
        "cardSpaceDims": dims,
        "excludedInkPixels": int(excluded.sum()) if excluded is not None else None,
        "glassPixelsPerState": {s: (c["pixels"] if c else 0)
                                for s, c in cents.items()},
        "centroids": cents,
        "path": [cents.get(s, {}).get("nx") if cents.get(s) else None
                 for s in PATH_STATES],
    }


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:])
    measure = Path(args["measure"])
    man = json.loads((measure / "measure-manifest.json").read_text())
    recs = man["records"]

    def files(pred):
        return {r["state"]: r["file"] for r in recs if pred(r)}

    # ---- F11: Target, and both O2 lanes at their fullB state
    tgt_files = files(lambda r: r["kind"] == "target"
                      and r["asset"] == "bw-split" and r["vp"] == "1440x900")
    out_f11 = {"target": f11_for(measure, tgt_files)}
    for lane, tag in [("b-only", "v1"), ("a-plus-b", "o1")]:
        lf = {}
        for r in recs:
            if r["kind"] != "local" or r.get("lane") != tag: continue
            if r["asset"] != "bw-split" or r["vp"] != "1440x900": continue
            st = r["state"]
            if st == "fullB":
                lf["rest"] = r["file"]
            elif st.startswith("fullB-"):
                lf[st.split("-", 1)[1]] = r["file"]
        out_f11[lane] = f11_for(measure, lf)

    tpath = out_f11["target"]["path"]
    verdicts = {}
    for lane in ("b-only", "a-plus-b"):
        verdicts[lane] = I.f11_judge(tuple(tpath),
                                     tuple(out_f11[lane]["path"]))

    # ---- F10: polygon mask vs the AABB numbers O2 recorded
    out_f10 = {}
    for asset in ("bw-split", "rgb-bars"):
        row = {}
        for label, tag, state in [("before", "v1", "before"),
                                  ("b-only", "v1", "fullB"),
                                  ("a-plus-b", "o1", "fullB")]:
            hit = [r for r in recs if r["kind"] == "local"
                   and r.get("lane") == tag and r["state"] == state
                   and r["asset"] == asset and r["vp"] == "1440x900"]
            if not hit:
                continue
            img = Image.open(measure / hit[0]["file"])
            w, h = img.size
            frame = S.SL.layout(w, h)
            cam = S.VC.coverage_camera(0, 0, frame)
            pred = S.VC.frame_verdicts(0, 0, cam, frame)
            dil = I.f10_dilation_for(frame["planeWidth"])
            row[label] = dict(I.f10_gutter_ink(img, pred, dil), dilationPx=dil)
        out_f10[asset] = row

    # ---- F5: does the baseline branch pick the coding the O2 record implies
    out_f5 = {}
    for asset in ("bw-split", "grayscale-step", "rgb-bars", "cool-blue"):
        def interior(tag, state):
            hit = [r for r in recs if r["kind"] == "local"
                   and r.get("lane") == tag and r["state"] == state
                   and r["asset"] == asset and r["vp"] == "1440x900"]
            if not hit:
                return None
            img = Image.open(measure / hit[0]["file"])
            w, h = img.size
            return S.interior_stats(img, [r for _, r in S.rects_at(w, h)])
        b, c = interior("v1", "before"), interior("o1", "fullB")
        if b and c:
            out_f5[asset] = I.f5_interior_change(b, c)

    doc = {
        "what": "O3 corrected-instrument dry run on the EXISTING O2 captures. "
                "Validation only -- no O3 candidate exists and nothing here "
                "can tune anything.",
        "measureDir": str(measure),
        "capturedAtHead": man.get("capturedAtHead"),
        "inkIntersectionStates": [s for s, _ in INK_STATES],
        "pathStates": PATH_STATES,
        "F11": out_f11,
        "F11Verdicts": verdicts,
        "F11Measurable": all(
            all(v > 0 for v in out_f11[l]["glassPixelsPerState"].values())
            for l in out_f11),
        "F10PolygonMask": out_f10,
        "F5BaselineBranch": {k: {"coding": v["coding"], "fired": v["fired"]}
                             for k, v in out_f5.items()},
        "F5Detail": out_f5,
    }
    Path(args["out"]).write_text(json.dumps(doc, indent=1))
    print("F11 measurable:", doc["F11Measurable"])
    for lane, v in out_f11.items():
        print(f"  {lane:10s} ink={v['excludedInkPixels']} "
              f"glass={v['glassPixelsPerState']} path={v['path']}")
    for lane, v in verdicts.items():
        print(f"  verdict {lane}: fired={v['fired']} {v['reasons']}")
    for asset, row in out_f10.items():
        print(f"F10 {asset}: " + ", ".join(
            f"{k}={x['gutterInkRatio']}({x['cardsMasked']} cards)"
            for k, x in row.items()))
    for asset, v in out_f5.items():
        print(f"F5 {asset}: {v['coding']} fired={v['fired']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
