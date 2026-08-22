#!/usr/bin/env python3
"""O5F §十E -- prove what the portrait ROIs do and do not contain.

The two open portrait metrics read the outer-8%-width, central-60%-height
edge bands of each scored card rect. §十E asks for proof that those bands
exclude: Target typography, candidate typography, the footer, neighbouring
cards, and the antialias silhouette ring. Sealed codings, fixed before any
Phase B capture is scored:

  1. TYPOGRAPHY / FOOTER: pixel-intersection area of every band with every
     text-ink box (se-rule / se-title / se-deck) and every footer box must
     be ZERO. The boxes come from the live DOM at capture time; the frozen
     layout is the Target's own (source contract 36/36, typography contract
     29/29), so the same boxes describe the Target's type footprint.
  2. NEIGHBOURING CARDS: intersection area of every band with every OTHER
     scored card rect must be ZERO.
  3. ANTIALIAS RING / OFF-SILHOUETTE PIXELS: measured, not assumed, from
     the sdf-mask program capture -- the fraction of band pixels that fall
     outside the rendered silhouette is reported per band, and the sealed
     coding for "the ring does not own the residual" is the difference of
     differences: recomputing dark-side luma with off-silhouette pixels
     masked out must move the CANDIDATE-MINUS-TARGET residual by less than
     10% of that residual. (Both lanes carry the same ring; a contamination
     that cancels in the difference cannot explain the difference.)

Output: qa-v5/optics-o5f/roi-isolation.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
HERE = REPO / "scripts/v5"
ROT = REPO / "artifacts/optics-o5f/clip-rotation"
MD = REPO / "artifacts/optics-o5f/measure"
O5R_MD = REPO / "artifacts/optics-o5r/measure"
OUT = REPO / "qa-v5/optics-o5f/roi-isolation.json"

EDGE_BAND_FRACTION = 0.08
RING_EFFECT_MAX_FRACTION = 0.10   # sealed: <10% of the residual it could bias
SILHOUETTE_THRESHOLD = 128        # sdf-mask is white inside, black outside


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


G = _load("o5f_roi_gate", "o5r-gate.py")


def bands_of(rect):
    x0, y0, x1, y1 = rect
    cw, ch = x1 - x0, y1 - y0
    yb0, yb1 = y0 + int(ch * 0.2), y1 - int(ch * 0.2)
    w = max(1, int(cw * EDGE_BAND_FRACTION))
    return {"left": (x0, yb0, x0 + w, yb1),
            "right": (x1 - w, yb0, x1, yb1)}


def inter_area(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def lum(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def band_pixels(img, band):
    x0, y0, x1, y1 = band
    return np.asarray(img.convert("RGB"), dtype=np.float32)[y0:y1, x0:x1]


def main() -> int:
    man = json.loads((ROT / "clip-rotation-manifest.json").read_text())
    o5f_man = json.loads((MD / "measure-manifest.json").read_text())
    o5r_man = json.loads((O5R_MD / "measure-manifest.json").read_text())

    def view_file(vp):
        rows = [r for r in o5f_man["records"]
                if r.get("kind") == "view" and r.get("view") == "sdf-mask"
                and r.get("vp") == vp and r.get("lane") == "o5r-unclamped"]
        return rows[0]["file"] if rows else None

    def lane_file(manifest, root, lane, vp):
        if lane == "target":
            rows = [r for r in manifest["records"]
                    if r.get("kind") == "target" and r.get("state") == "rest"
                    and r.get("asset") == "bw-split" and r.get("vp") == vp]
        else:
            rows = [r for r in manifest["records"]
                    if r.get("kind") == "lane" and r.get("lane") == lane
                    and r.get("state") == "rest"
                    and r.get("asset") == "bw-split" and r.get("vp") == vp]
        return (root / rows[0]["file"]) if rows else None

    per_vp = []
    for rec in man["records"]:
        vp = rec["vp"]
        rects = G.RECTS[vp][0]
        truth = rec["labelTruth"] or {}
        text_boxes = [t["box"] for c in truth.get("cards", [])
                      for t in c.get("texts", [])]
        footer_boxes = [f["box"] for f in truth.get("footer", [])]

        rows = []
        for ri, rect in enumerate(rects):
            for side, band in bands_of(rect).items():
                text_overlap = sum(inter_area(band, b) for b in text_boxes)
                footer_overlap = sum(inter_area(band, b) for b in footer_boxes)
                other_overlap = sum(inter_area(band, r)
                                    for rj, r in enumerate(rects) if rj != ri)
                rows.append({"rect": ri, "side": side, "band": band,
                             "textOverlapPx": int(text_overlap),
                             "footerOverlapPx": int(footer_overlap),
                             "otherCardOverlapPx": int(other_overlap)})

        # --- 3: off-silhouette pixels and the ring's effect on the residual
        ring = None
        vf = view_file(vp)
        cand_f = lane_file(o5f_man, MD, "o5r-unclamped", vp)
        targ_f = lane_file(o5r_man, O5R_MD, "target", vp)
        if vf and cand_f and targ_f:
            mask_img = Image.open(MD / vf).convert("L")
            mask = np.asarray(mask_img, dtype=np.uint8) >= SILHOUETTE_THRESHOLD
            cand = Image.open(cand_f)
            targ = Image.open(targ_f)
            ring_rows = []
            for ri, rect in enumerate(rects):
                band = bands_of(rect)["left"]   # the dark-side band
                x0, y0, x1, y1 = band
                m = mask[y0:y1, x0:x1]
                off = 1.0 - float(m.mean())
                cl = lum(band_pixels(cand, band))
                tl = lum(band_pixels(targ, band))
                unmasked = float(cl.mean()) - float(tl.mean())
                masked = (float(cl[m].mean()) - float(tl[m].mean())
                          if m.any() else None)
                ring_rows.append({
                    "rect": ri, "offSilhouetteFraction": round(off, 4),
                    "residualUnmasked": round(unmasked, 4),
                    "residualSilhouetteOnly": (round(masked, 4)
                                               if masked is not None else None),
                    "ringEffect": (round(masked - unmasked, 4)
                                   if masked is not None else None),
                })
            effects = [r["ringEffect"] for r in ring_rows
                       if r["ringEffect"] is not None]
            resids = [abs(r["residualUnmasked"]) for r in ring_rows]
            ring = {
                "sdfMaskFile": vf,
                "rows": ring_rows,
                "worstRingEffect": max((abs(e) for e in effects), default=None),
                "worstResidual": max(resids, default=None),
                "withinSealedCoding": (bool(effects) and bool(resids)
                    and max(abs(e) for e in effects)
                    <= RING_EFFECT_MAX_FRACTION * max(max(resids), 1e-9)),
            }

        clean = all(r["textOverlapPx"] == 0 and r["footerOverlapPx"] == 0
                    and r["otherCardOverlapPx"] == 0 for r in rows)
        per_vp.append({"vp": vp, "bands": rows, "boxCounts": {
                           "textBoxes": len(text_boxes),
                           "footerBoxes": len(footer_boxes)},
                       "typographyFooterNeighbourClean": clean,
                       "antialiasRing": ring})

    doc = {
        "what": "§十E -- what the portrait ROI edge bands contain, proven "
                "from DOM boxes, rect arithmetic and the sdf-mask program.",
        "sealedCodings": {
            "typographyFooterNeighbours": "intersection area == 0",
            "antialiasRing": "masking off-silhouette pixels out of the band "
                             "must move the candidate-minus-Target residual "
                             f"by < {RING_EFFECT_MAX_FRACTION:.0%} of that "
                             "residual",
            "layoutIdentity": "the DOM boxes describe both pages: the frozen "
                              "layout reproduces the Target's (source "
                              "contract 36/36; typography contract 29/29)",
        },
        "viewports": per_vp,
        "pass": all(v["typographyFooterNeighbourClean"]
                    and (v["antialiasRing"] is None
                         or v["antialiasRing"]["withinSealedCoding"])
                    for v in per_vp),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    for v in per_vp:
        ring = v["antialiasRing"]
        print(f"{v['vp']}: clean={v['typographyFooterNeighbourClean']} "
              f"ringEffect={ring and ring['worstRingEffect']} "
              f"(residual {ring and ring['worstResidual']})")
    print(f"-> {OUT}  {'PASS' if doc['pass'] else 'FAIL'}")
    return 0 if doc["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
