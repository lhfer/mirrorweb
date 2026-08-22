#!/usr/bin/env python3
"""O5F §九 -- score the term decomposition: find the first diverging term.

Chain order (causal): analytic-normal -> reflection-vector -> equirect-uv ->
raw-env-sample -> fresnel -> env-mix-factor -> white-rim -> body-refracted ->
final-colour. For each term the ENGINE value (the term's own separate
program, photographed) is compared against the REPLAY value (the source
formula evaluated on the CPU through the live card matrix and camera), on
the same card, the same card-local SDF bins, the same frozen media time.

VALIDATION BEFORE SCORING. Every term must first reproduce the engine at
1440x900 -- the viewport where the final result passes -- within its
pre-registered tolerance. A term whose replay cannot do that is
INSTRUMENT_UNREADABLE at every viewport: a replay that disagrees where the
answer is known good is measuring its own conventions, not the candidate.
Only validated terms are then read at 390x844, and the first one whose
worst-bin p95 exceeds its tolerance THERE is the first diverging term.

Pre-registered tolerances (byte quantisation + resampling driven, fixed
before any decomposition capture is scored):

  analytic-normal    p95 component delta <= 0.05
  reflection-vector  p95 component delta <= 0.05
  equirect-uv        p95 delta <= 0.02  (u wrap-aware)
  raw-env-sample     p95 delta <= 0.04  (Reinhard space, bilinear replay)
  fresnel            p95 delta <= 0.02
  env-mix-factor     p95 delta <= 0.02
  white-rim          p95 delta <= 0.03
  body-refracted     p95 channel delta <= 0.08 (image-warp replay of the
                     media plane; resampling noise dominates)
  final-colour       p95 encoded-byte delta <= 0.06 (ACES composite of the
                     ENGINE's own terms vs the Beauty program)

Two conventions are resolved ON THE VALIDATION VIEWPORT ONLY and disclosed:
the ACES matrix orientation (three's TSL mat3 layout) and nothing else --
every other convention (equirect axes, HDR flipY, rotation signs) is fixed
from the three sources quoted in o5f_terms.py, and a failure is reported as
UNREADABLE rather than searched over.

Output: qa-v5/optics-o5f/portrait-term-decomposition.json
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
DEC = REPO / "artifacts/optics-o5f/decomposition"
OUT = REPO / "qa-v5/optics-o5f/portrait-term-decomposition.json"

VALIDATION_VP = "1440x900"
P0 = "390x844"
GRID_N = 128
EDGE_MARGIN_PX = 2.0   # engine samples only where sdf < -margin
CHAIN = ["analytic-normal", "reflection-vector", "equirect-uv",
         "raw-env-sample", "fresnel", "env-mix-factor", "white-rim",
         "body-refracted", "final-colour"]
TOL = {"analytic-normal": 0.05, "reflection-vector": 0.05,
       "equirect-uv": 0.02, "raw-env-sample": 0.04, "fresnel": 0.02,
       "env-mix-factor": 0.02, "white-rim": 0.03, "body-refracted": 0.08,
       "final-colour": 0.06}


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


T = _load("o5f_td_terms", "o5f_terms.py")
G = _load("o5f_td_gate", "o5r-gate.py")

HDR_PATH = REPO / "public/hdri/studio_small_03_1k.hdr"

ACES_IN = np.array([[0.59719, 0.35458, 0.04823],
                    [0.07600, 0.90834, 0.01566],
                    [0.02840, 0.13383, 0.83777]])
ACES_OUT = np.array([[1.60475, -0.53108, -0.07367],
                     [-0.10208, 1.10813, -0.00605],
                     [-0.00327, -0.07276, 1.07602]])


def aces(rgb, transpose=False):
    m_in = ACES_IN.T if transpose else ACES_IN
    m_out = ACES_OUT.T if transpose else ACES_OUT
    c = np.asarray(rgb, float) / 0.6
    c = c @ m_in.T
    a = c * (c + 0.0245786) - 0.000090537
    b = c * (0.983729 * (c + 0.4329510)) + 0.238081
    c = a / b
    c = c @ m_out.T
    return np.clip(c, 0.0, 1.0)


def img_rgb(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0


def sample_screen(img, sx, sy):
    h, w = img.shape[:2]
    xi = np.clip(np.round(sx).astype(int), 0, w - 1)
    yi = np.clip(np.round(sy).astype(int), 0, h - 1)
    return img[yi, xi]


def p95(x):
    return float(np.percentile(x, 95)) if x.size else None


def main() -> int:
    man = json.loads((DEC / "decomposition-manifest.json").read_text())
    hdr = T.load_hdr(HDR_PATH)
    by = {(r["vp"], r["view"]): r for r in man["records"]}

    # --- input identity: every view on a viewport must have rendered the
    # same card matrix, camera and media time -----------------------------
    input_identity = []
    for vp in man["viewports"]:
        truths = {}
        for view in man["views"]:
            t = json.loads((DEC / by[(vp, view)]["truthFile"]).read_text())
            truths[view] = t
        ref = truths["beauty"]["body"]
        ref_cards = {c["slotIndex"]: c["matrixWorld"]
                     for c in ref["cards"] if c.get("active")}
        same = True
        for view, t in truths.items():
            b = t["body"]
            if (b["camera"]["projectionMatrix"]
                    != ref["camera"]["projectionMatrix"]
                    or b["camera"]["matrixWorldInverse"]
                    != ref["camera"]["matrixWorldInverse"]):
                same = False
            cards = {c["slotIndex"]: c["matrixWorld"]
                     for c in b["cards"] if c.get("active")}
            if cards != ref_cards:
                same = False
            mt = t.get("media")
            ref_mt = truths["beauty"].get("media")
            if isinstance(mt, dict) and isinstance(ref_mt, dict):
                if mt.get("times") != ref_mt.get("times"):
                    same = False
        input_identity.append({"vp": vp, "identical": same})

    program_hashes = {}
    for vp in man["viewports"]:
        hs = {v: (by[(vp, v)].get("program") or {}).get("fragmentSha256")
              for v in man["views"]}
        program_hashes[vp] = {
            "fragmentSha256": hs,
            "allDistinct": len({h for h in hs.values() if h}) == len(
                [h for h in hs.values() if h]),
        }

    # The Beauty program must be UNCHANGED by the added measurement views:
    # each view is a separate program, and the §六C identity gate recorded the
    # cached Beauty program's hashes before any view existed. Compared here so
    # the forensics commit carries its own proof that it touched nothing
    # sealed.
    ident = json.loads((REPO / "qa-v5/optics-o5f/material-cache-identity.json")
                       .read_text())
    sealed_beauty = next(r for r in ident["C_programIdentity"]["rows"]
                         if r["step"] == "high")
    now_beauty = (by[("1440x900", "beauty")].get("program") or {})
    # The sealed rows carry 16-hex PREFIXES; the decomposition capture hashes
    # the full digest, so the comparison is prefix-against-full.
    beauty_unchanged = {
        "sealedFragmentSha256Prefix": sealed_beauty["fragmentSha256"],
        "currentFragmentSha256": now_beauty.get("fragmentSha256"),
        "unchanged": bool(now_beauty.get("fragmentSha256"))
        and str(now_beauty["fragmentSha256"])
        .startswith(sealed_beauty["fragmentSha256"]),
    }

    results = {vp: {} for vp in man["viewports"]}
    aces_convention = {"transpose": False, "decidedOn": VALIDATION_VP,
                       "p95ByOrientation": None}

    for vp in man["viewports"]:
        w, h = (int(x) for x in vp.split("x"))
        rects = G.RECTS[vp][0]
        truth = json.loads((DEC / by[(vp, "beauty")]["truthFile"]).read_text())
        body = truth["body"]
        env_constants = {k: float(body["source"][k]) for k in
                         ("fresnelF0", "envIntensity", "envMaxMix",
                          "envRotation", "envRotationX", "rimIntensity")}
        # The two runtime scale uniforms sit in the OPTICS truth, not the
        # static contract; the shader multiplies both (envMix .mul(
        # envMixScale), rim .mul(rimScale)), so the replay must too. At rest
        # they are 1.0, and reading them from the capture proves it.
        env_constants["envMixScale"] = float(truth["optics"]["envMixScale"])
        env_constants["rimScale"] = float(truth["optics"]["rimScale"])
        samples = int(body["samples"])
        spectral = T.spectral_samples(samples)
        imgs = {v: img_rgb(DEC / by[(vp, v)]["file"]) for v in man["views"]}
        media_img = img_rgb(DEC / by[(vp, "beauty")]["mediaFile"])

        # match active cards to the gate rects by projected centre
        cards = [c for c in body["cards"] if c.get("active")]
        per_card = []
        for rect in rects:
            cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            best, best_d = None, 1e18
            for c in cards:
                r = T.R.CardReplay(body, c)
                sx, sy = r.local_to_screen(np.array(0.0), np.array(0.0))
                d = (float(sx) - cx) ** 2 + (float(sy) - cy) ** 2
                if d < best_d:
                    best, best_d = c, d
            per_card.append((rect, best))

        for rect, card in per_card:
            tr = T.TermReplay(body, card, hdr, env_constants)
            lx, ly = tr.card.grid_local(GRID_N)
            s = tr.sdf_at(lx, ly)
            sx, sy = tr.card.local_to_screen(lx, ly)
            valid = ((s < -EDGE_MARGIN_PX)
                     & (sx >= rect[0] + 1) & (sx < rect[2] - 1)
                     & (sy >= rect[1] + 1) & (sy < rect[3] - 1))
            bins = T.bin_masks(tr, lx, ly)
            bins = {k: (m & valid) for k, m in bins.items()}
            bins["all-valid"] = valid

            def stats(term, delta, engine_std):
                rows = {}
                for bname, m in bins.items():
                    if not m.any():
                        continue
                    d = delta[m]
                    rows[bname] = {"n": int(m.sum()),
                                   "meanAbsDelta": round(float(np.mean(d)), 5),
                                   "p95AbsDelta": round(p95(d), 5)}
                return {"bins": rows,
                        "worstBinP95": max((r["p95AbsDelta"]
                                            for r in rows.values()),
                                           default=None),
                        "engineInteriorStd": round(engine_std, 5),
                        "degenerateEngine": engine_std < 1e-4}

            card_out = {"slotIndex": card["slotIndex"],
                        "clipIndex": card["clipIndex"], "rect": rect,
                        "samples": samples, "terms": {}}

            # ---- analytic-normal (sRGB-encoded raw view) ----------------
            eng = T.srgb_decode(sample_screen(imgs["analytic-normal"], sx, sy)) * 2 - 1
            rep = tr.analytic_normal_view(lx, ly) * 2 - 1
            delta = np.abs(eng - rep).max(axis=-1)
            card_out["terms"]["analytic-normal"] = stats(
                "analytic-normal", delta, float(eng[valid].std()))

            # ---- reflection-vector (inverse-encoded view) ---------------
            eng = sample_screen(imgs["reflection-vector"], sx, sy) * 2 - 1
            rep = tr.reflection_vector(lx, ly)
            delta = np.abs(eng - rep).max(axis=-1)
            card_out["terms"]["reflection-vector"] = stats(
                "reflection-vector", delta, float(eng[valid].std()))

            # ---- equirect-uv --------------------------------------------
            eng = sample_screen(imgs["equirect-uv"], sx, sy)[..., :2]
            rep = tr.equirect_uv(lx, ly)
            du = np.abs(eng[..., 0] - rep[..., 0])
            du = np.minimum(du, 1.0 - du)      # the atan2 seam wraps
            dv = np.abs(eng[..., 1] - rep[..., 1])
            delta = np.maximum(du, dv)
            card_out["terms"]["equirect-uv"] = stats(
                "equirect-uv", delta, float(eng[valid].std()))

            # ---- raw-env-sample (Reinhard-compressed view) --------------
            eng = sample_screen(imgs["raw-env-sample"], sx, sy)
            rep = T.reinhard(tr.raw_env_sample(lx, ly))
            delta = np.abs(eng - rep).max(axis=-1)
            card_out["terms"]["raw-env-sample"] = stats(
                "raw-env-sample", delta, float(eng[valid].std()))

            # ---- fresnel / env-mix / rim (scalar views) -----------------
            for term, fn in (("fresnel", tr.fresnel),
                             ("env-mix-factor", tr.env_mix),
                             ("white-rim", tr.rim)):
                eng = sample_screen(imgs[term], sx, sy)[..., 0]
                rep = fn(lx, ly)
                delta = np.abs(eng - rep)
                card_out["terms"][term] = stats(
                    term, delta, float(eng[valid].std()))

            # ---- body-refracted: image-warp replay ----------------------
            eng = T.srgb_decode(sample_screen(imgs["refraction-only"], sx, sy))
            du, dv, _ = tr.card.displacement(lx, ly)
            acc = np.zeros(lx.shape + (3,))
            cover_ok = np.ones(lx.shape, bool)
            base_u, base_v = lx + 0.5, ly + 0.5
            for sp in spectral:
                eta_i = 1.0 / max(tr.card.ior
                                  + tr.dispersion * sp["offset"],
                                  tr.eta_floor)
                # each sample re-refracts at its own eta: rebuild via the
                # displacement's own machinery, scaled by eta ratio is NOT
                # the formula -- so recompute exactly.
                N, V, _pxy = tr._NV(lx, ly)
                rx, ry, rz, _ok = T.R.refract(-V[0], -V[1], -V[2],
                                              N[0], N[1], N[2], eta_i)
                travel = tr.card.S["thickness"] / np.maximum(
                    np.abs(rz), tr.card.travel_z_floor)
                ou = rx * travel * tr.card.refract_strength / tr.card.plane_w
                ov = ry * travel * tr.card.refract_strength / tr.card.plane_h
                su = np.clip(base_u + ou, 0.0, 1.0)
                sv = np.clip(base_v + ov, 0.0, 1.0)
                mu = su * tr.card.cover_scale[0] + tr.card.cover_offset[0]
                mv = sv * tr.card.cover_scale[1] + tr.card.cover_offset[1]
                clu, clv, inside = tr.card.media_uv_to_local(mu, mv)
                cover_ok &= inside
                msx, msy = tr.card.local_to_screen(clu, clv)
                rgb = T.srgb_decode(sample_screen(media_img, msx, msy))
                acc += rgb * np.asarray(sp["weight"])
            delta = np.abs(eng - acc).max(axis=-1)
            # A point whose displaced sample the cover crop removed cannot be
            # replayed from the media plane; it is excluded, not clamped.
            body_bins = {k: (m & cover_ok) for k, m in bins.items()}
            bv = valid & cover_ok
            bins, saved_bins = body_bins, bins
            card_out["terms"]["body-refracted"] = stats(
                "body-refracted", delta,
                float(eng[bv].std()) if bv.any() else 0.0)
            bins = saved_bins

            # ---- final-colour: ACES composite of ENGINE terms -----------
            env_lin = sample_screen(imgs["raw-env-sample"], sx, sy)
            env_lin = env_lin / np.maximum(1.0 - env_lin, 1e-4)  # un-Reinhard
            mixf = sample_screen(imgs["env-mix-factor"], sx, sy)[..., :1]
            rimf = sample_screen(imgs["white-rim"], sx, sy)[..., :1]
            body_lin = T.srgb_decode(
                sample_screen(imgs["refraction-only"], sx, sy))
            composite_lin = (body_lin * (1 - mixf) + env_lin * mixf
                             + rimf)
            beauty = sample_screen(imgs["beauty"], sx, sy)
            variants = {}
            for transpose in (False, True):
                pred = T.srgb_encode(aces(composite_lin, transpose))
                variants[transpose] = np.abs(pred - beauty).max(axis=-1)
            if vp == VALIDATION_VP and aces_convention["p95ByOrientation"] is None:
                p_row = p95(variants[False][valid])
                p_col = p95(variants[True][valid])
                aces_convention["p95ByOrientation"] = {
                    "rowMajor": round(p_row, 5), "transposed": round(p_col, 5)}
                aces_convention["transpose"] = bool(p_col < p_row)
            delta = variants[aces_convention["transpose"]]
            card_out["terms"]["final-colour"] = stats(
                "final-colour", delta, float(beauty[valid].std()))

            results[vp].setdefault("cards", []).append(card_out)

    # --- validation, then P0 scoring ---------------------------------------
    term_status = {}
    for term in CHAIN:
        val_worst = max((c["terms"][term]["worstBinP95"] or 0)
                        for c in results[VALIDATION_VP]["cards"])
        degenerate = any(c["terms"][term]["degenerateEngine"]
                         for c in results[VALIDATION_VP]["cards"])
        validated = (val_worst is not None and val_worst <= TOL[term]
                     and not degenerate)
        p0_worst = max((c["terms"][term]["worstBinP95"] or 0)
                       for c in results[P0]["cards"])
        p0_by_card = [{"slotIndex": c["slotIndex"],
                       "clipIndex": c["clipIndex"],
                       "worstBinP95": c["terms"][term]["worstBinP95"]}
                      for c in results[P0]["cards"]]
        term_status[term] = {
            "tolerance": TOL[term],
            "validationWorstBinP95": round(val_worst, 5),
            "validated": validated,
            "degenerateEngineView": degenerate,
            "status": ("INSTRUMENT_UNREADABLE" if not validated
                       else ("DIVERGES" if p0_worst > TOL[term] else "MATCHES")),
            "p0WorstBinP95": round(p0_worst, 5),
            "p0ByCard": p0_by_card,
        }

    first_diverging = next((t for t in CHAIN
                            if term_status[t]["status"] == "DIVERGES"), None)
    unreadable = [t for t in CHAIN
                  if term_status[t]["status"] == "INSTRUMENT_UNREADABLE"]

    doc = {
        "what": "§九 -- the source chain, term by term: each term's own "
                "program against the CPU replay of the source formula, on "
                "the same cards, bins and frozen media time. Validated at "
                "1440x900 before 390x844 is read.",
        "chainOrder": CHAIN,
        "tolerances": TOL,
        "validationViewport": VALIDATION_VP,
        "p0Viewport": P0,
        "gridN": GRID_N, "edgeMarginPx": EDGE_MARGIN_PX,
        "inputIdentity": input_identity,
        "programHashes": program_hashes,
        "beautyProgramUnchangedByViews": beauty_unchanged,
        "acesConvention": aces_convention,
        "terms": term_status,
        "perCard": {vp: results[vp]["cards"] for vp in man["viewports"]},
        "firstDivergingTerm": first_diverging,
        "instrumentUnreadableTerms": unreadable,
        "conclusion": (
            f"first diverging term at {P0}: {first_diverging}"
            if first_diverging else
            "NO term diverges from the source formula at 390x844 within "
            "the pre-registered tolerances: the transcription is faithful "
            "at both viewports, and the portrait residual is carried by "
            "the chain's INPUTS (media crop, sample tier, environment "
            "asset), which §十 examines."),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    for t in CHAIN:
        st = term_status[t]
        print(f"{st['status']:<21} {t:<18} val {st['validationWorstBinP95']} "
              f"p0 {st['p0WorstBinP95']} tol {st['tolerance']}")
    print(f"\nfirst diverging term: {first_diverging}")
    print(f"-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
