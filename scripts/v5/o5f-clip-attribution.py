#!/usr/bin/env python3
"""O5F §十A -- per-clip attribution of the portrait residual.

Sealed coding, fixed before the rotation captures are scored:

  * the metrics are the SEALED instruments -- dark_side_luma and
    white_reflection_ratio from o5_instruments.py, per single-card rect;
  * the reference scale is the SEALED windows -- max(Target repeatability,
    floor 6.0 / 0.15), exactly the corrected gate's;
  * the Target reference per rect is the mean over its three sealed repeat
    captures (repeatability 0.0 on this deterministic media);
  * a rect row is scored only if the rotation left the rect where the rest
    capture had it (every corner within 2 px) -- a drifted rect would
    compare different pixels, and it is reported as skipped, not guessed;
  * ISOLATED TO CLIP 2 means: at the P0 viewport, every clip-0 and clip-1
    row sits INSIDE the sealed window and every clip-2 row sits OUTSIDE it,
    for the metric in question. Partial patterns are reported as the
    numbers they are, with isolated=false.

Under the deterministic media routes all three clips play identical
content, and clips 0 and 1 carry centred cover -- the Target's own formula
-- while clip 2 carries the frozen product crop (focusY 0.46, zoom 1.06).
A per-clip difference can therefore only be the crop.

Output: qa-v5/optics-o5f/clip-index-attribution.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
HERE = REPO / "scripts/v5"
ROT = REPO / "artifacts/optics-o5f/clip-rotation"
O5R_MD = REPO / "artifacts/optics-o5r/measure"
OUT = REPO / "qa-v5/optics-o5f/clip-index-attribution.json"

RECT_DRIFT_TOLERANCE_PX = 2


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I5 = _load("o5f_att_ins", "o5_instruments.py")
G = _load("o5f_att_gate", "o5r-gate.py")


def iou(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union else 0.0


def card_metrics(img_path, rect):
    img = Image.open(img_path)
    dark = I5.dark_side_luma(img, [rect])["meanLuma"]
    white = I5.white_reflection_ratio(img, [rect])["meanRatio"]
    return {"darkSideLuma": dark, "whiteReflectionRatio": white}


def occupant(shot, rect):
    """Which slot/clip the engine says occupies `rect` in this capture."""
    clips = {c["slotIndex"]: c["clipIndex"]
             for c in shot["engine"]["cards"]}
    best, best_iou = None, 0.0
    for r in shot["engine"]["rects"]:
        v = iou(rect, r["rectPx"])
        if v > best_iou:
            best, best_iou = r, v
    if best is None or best_iou < 0.5:
        return None
    drift = max(abs(best["rectPx"][i] - rect[i]) for i in range(4))
    return {"slotIndex": best["slotIndex"],
            "clipIndex": clips.get(best["slotIndex"]),
            "iou": round(best_iou, 4), "cornerDriftPx": round(drift, 2)}


def main() -> int:
    man = json.loads((ROT / "clip-rotation-manifest.json").read_text())
    o5r_man = json.loads((O5R_MD / "measure-manifest.json").read_text())

    def target_files(vp):
        return [r["file"] for r in o5r_man["records"]
                if r.get("kind") == "target" and r.get("state") == "rest"
                and r.get("asset") == man["asset"] and r.get("vp") == vp]

    windows = {"darkSideLuma": I5.DARK_LUMA_WINDOW_FLOOR,
               "whiteReflectionRatio": I5.WHITE_RATIO_WINDOW_FLOOR}
    per_vp = []
    for rec in man["records"]:
        vp = rec["vp"]
        rects = G.RECTS[vp][0]
        tfiles = target_files(vp)
        rows, skipped = [], []
        for ri, rect in enumerate(rects):
            tvals = [card_metrics(O5R_MD / f, rect) for f in tfiles]
            target = {k: round(sum(v[k] for v in tvals) / len(tvals), 4)
                      for k in windows} if tvals else None
            t_spread = {k: round(max(v[k] for v in tvals)
                                 - min(v[k] for v in tvals), 4)
                        for k in windows} if tvals else None
            for shot in rec["shots"]:
                occ = occupant(shot, rect)
                if occ is None or occ["cornerDriftPx"] > RECT_DRIFT_TOLERANCE_PX:
                    skipped.append({"rect": ri, "rot": shot["rot"],
                                    "occupant": occ})
                    continue
                cand = card_metrics(ROT / shot["file"], rect)
                row = {"rect": ri, "rectPx": rect, "rot": shot["rot"],
                       "offsetX": shot["offsetX"], **occ,
                       "candidate": cand, "target": target,
                       "targetSpread": t_spread}
                if target:
                    row["residual"] = {
                        k: round(cand[k] - target[k], 4) for k in windows}
                    row["insideWindow"] = {
                        k: abs(row["residual"][k])
                           <= max(windows[k],
                                  (t_spread or {}).get(k, 0.0))
                        for k in windows}
                rows.append(row)

        by_clip = {}
        for row in rows:
            by_clip.setdefault(row["clipIndex"], []).append(row)
        clip_summary = {}
        for clip, rws in sorted(by_clip.items(), key=str):
            clip_summary[str(clip)] = {
                "rows": len(rws),
                "meanResidual": {
                    k: round(sum(r["residual"][k] for r in rws) / len(rws), 4)
                    for k in windows},
                "allInsideWindow": {
                    k: all(r["insideWindow"][k] for r in rws)
                    for k in windows},
            }

        def isolated(metric):
            c01 = [r for r in rows if r["clipIndex"] in (0, 1)]
            c2 = [r for r in rows if r["clipIndex"] == 2]
            if not c01 or not c2:
                return None
            return (all(r["insideWindow"][metric] for r in c01)
                    and all(not r["insideWindow"][metric] for r in c2))

        per_vp.append({
            "vp": vp, "cellW": rec["cellW"],
            "targetReferenceFiles": tfiles,
            "rows": rows, "skippedRows": skipped,
            "byClip": clip_summary,
            "isolatedToClip2": {k: isolated(k) for k in windows},
        })

    p0 = next((v for v in per_vp if v["vp"] == "390x844"), None)
    doc = {
        "what": "§十A -- the portrait residual measured per clip/material "
                "index, using the sealed instruments and windows. Clips 0 "
                "and 1 are centred cover (the Target's own formula); clip 2 "
                "is the frozen product crop. Same content on every clip "
                "under the deterministic routes.",
        "sealedCoding": {
            "metrics": "o5_instruments.dark_side_luma / "
                       "white_reflection_ratio, per single-card rect",
            "window": "max(Target repeat spread, floor 6.0 / 0.15) -- the "
                      "corrected gate's own",
            "rectDriftTolerancePx": RECT_DRIFT_TOLERANCE_PX,
            "isolated": "every clip-0/1 row inside the window AND every "
                        "clip-2 row outside it, at the metric in question",
        },
        "notApplicable": {"844x390": "no fully-visible card at rest; the "
                                     "sealed gate itself scored a widest-"
                                     "drawn-card basis there"},
        "viewports": per_vp,
        "p0Conclusion": None if p0 is None else {
            "vp": "390x844",
            "byClip": p0["byClip"],
            "isolatedToClip2": p0["isolatedToClip2"],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    for v in per_vp:
        print(f"{v['vp']}: {len(v['rows'])} rows, skipped "
              f"{len(v['skippedRows'])}, isolatedToClip2 "
              f"{v['isolatedToClip2']}")
        for clip, s in v["byClip"].items():
            print(f"   clip {clip}: {s['rows']} rows, meanResidual "
                  f"{s['meanResidual']}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
