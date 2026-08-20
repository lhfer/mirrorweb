#!/usr/bin/env python3
"""
Does the fitter's model project what the engine actually renders?

Verified corner by corner, at both rest phases (0 and half a cell), both
vertical modes, and all six gated viewports. Two things are checked separately
so a failure points at one of them:

  law      the engine's own compositionScale and restOffset against the model's
  geometry the projected quads, with the engine's scale and phase substituted in
           so only placeTile + the camera are under test

Usage: f26-model-vs-engine.py --dir=<capture root> --out=<json>
"""
from __future__ import annotations
import importlib.util, json, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("f25", HERE / "f25-joint-fit.py")
F = importlib.util.module_from_spec(spec); spec.loader.exec_module(F)

VPS = ["1100x720", "1366x768", "1440x900", "1920x1080", "390x844", "844x390"]
# Portrait-law dimension. F2.6 verified depth/tangent x zero/half-cell x six
# viewports, but every capture ran the same portrait law -- which is precisely
# the axis the propagation defect lived on, so it could not have been caught.
PORTRAIT_VPS = ["390x844", "360x800", "500x900"]


def model_quads(vw, vh, params, mode, scale, phase_x, tile):
    """
    Model quads with the engine's own scale, phase and TILE forced in.

    The fitter carries the SILHOUETTE tile size, because that is what a pixel
    detector reads off a rendered card. getCardQuads returns the slab. Comparing
    the two without substituting is a 0.18% mismatch by construction -- it shows
    up as a clean 0.07%-of-viewport error at every corner, which is exactly what
    it was before this substitution.
    """
    orig_tile = (F.TILE_W, F.TILE_H)
    F.TILE_W, F.TILE_H = tile
    orig_scale, orig_phase = F.scale_of, F.rest_phase_x
    F.scale_of = lambda w, h, b, s: scale
    F.rest_phase_x = lambda w, h, b, s: phase_x
    try:
        return F.quads(vw, vh, params, mode)
    finally:
        F.scale_of, F.rest_phase_x = orig_scale, orig_phase
        F.TILE_W, F.TILE_H = orig_tile


if __name__ == "__main__":
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    root = Path(args["--dir"])
    out = Path(args.get("--out", "qa-v5/f26/model-vs-engine.json"))
    cfg = json.loads(Path(args.get("--params", "qa-v5/f26/params.json")).read_text())
    rows, worst_geom, worst_law = [], 0.0, 0.0
    combos = [(m, vp, None) for m in ("depth", "tangent") for vp in VPS]
    combos += [("tangent", vp, law) for law in ("p0", "p1", "p2") for vp in PORTRAIT_VPS]
    for mode, vp, law in combos:
        if True:
            p = dict(cfg[mode])
            if law:
                p = dict(p, **{k: v for k, v in cfg["laws"][law].items()})
            f = (root / mode / vp / "01-rest.json" if law is None
                 else Path(args["--laws-dir"]) / law / "local" / vp / "01-rest.json")
            if not f.exists():
                rows.append({"mode": mode, "viewport": vp, "portraitLaw": law,
                             "status": "MISSING_CAPTURE"})
                continue
            data = json.loads(f.read_text())
            st, v4 = data["state"], data.get("v4state", {})
            vw, vh = (int(x) for x in vp.split("x"))
            eng_scale = st.get("compositionScale")
            eng_phase = (v4.get("restOffset") or {}).get("x", 0.0)
            law_scale = F.scale_of(vw, vh, p["gainBase"], p["gainSlope"])
            law_phase = F.rest_phase_x(vw, vh, p["gainBase"], p["gainSlope"])
            d_scale = abs(law_scale - eng_scale)
            d_phase = abs(law_phase - eng_phase)
            worst_law = max(worst_law, d_scale / max(eng_scale, 1e-9) * 100, d_phase)

            tile = (st["tile"]["width"], st["tile"]["height"])
            mq = {(c["i"], c["j"]): c["q"] for c in
                  model_quads(vw, vh, p, mode, eng_scale, eng_phase, tile)}
            errs = []
            for c in data["quads"]:
                key = (c["i"], c["j"])
                if key not in mq:
                    continue
                eng = np.array([[x * vw, y * vh] for x, y in c["quad"]])
                errs.append(float(np.abs(eng - mq[key]).max()))
            peak = max(errs) if errs else None
            if peak is not None:
                worst_geom = max(worst_geom, peak)
            rows.append({
                "mode": mode, "viewport": vp, "portraitLaw": law,
                "restPhase": "half-cell" if eng_phase > 1 else "zero",
                "engineCompositionScale": eng_scale, "modelCompositionScale": round(law_scale, 6),
                "scaleErrorPct": round(d_scale / max(eng_scale, 1e-9) * 100, 6),
                "engineRestOffsetX": round(eng_phase, 4), "modelRestOffsetX": round(law_phase, 4),
                "restOffsetErrorPx": round(d_phase, 6),
                "cardsCompared": len(errs),
                "maxCornerErrorPx": round(peak, 6) if peak is not None else None,
                "rmsCornerErrorPx": round(float(np.sqrt(np.mean(np.square(errs)))), 6) if errs else None,
            })
    payload = {
        "note": "Law and geometry are checked separately. Geometry substitutes the engine's "
                "own scale and phase, so a non-zero geometry error is placeTile or the "
                "camera, never the responsive law.",
        "floatingPointTolerancePx": 0.05,
        "worstGeometryCornerErrorPx": round(worst_geom, 6),
        "worstLawError": round(worst_law, 6),
        "geometryExact": bool(worst_geom <= 0.05),
        "lawExact": bool(worst_law <= 0.05),
        "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"geometry worst {worst_geom:.6f} px   law worst {worst_law:.6f}")
    for r in rows:
        if "maxCornerErrorPx" in r:
            print(f"  {r['mode']:<8} {str(r.get('portraitLaw') or '-'):<3} {r['viewport']:<10} "
                  f"phase={r['restPhase']:<9} "
                  f"cards={r['cardsCompared']:>3} maxCorner={r['maxCornerErrorPx']} "
                  f"scaleErr={r['scaleErrorPct']}%")
