#!/usr/bin/env python3
"""O2 shared-media harness -- verification half.

Consumes harness-raw.json + the lane screenshots, adds the cover-fit
verification (law recomputation for both pages + a rendered-edge
measurement on the screenshots against the python layout twin's card
rects), and writes the public shared-media-harness.json with a pass/fail
per asset and overall.

Cover verification is two-layered:
  law     the Target's source-read cover function and our MediaFit cover
          law are both recomputed here from the asset dimensions; the
          local page's getMediaFits readback must equal our law exactly.
  render  for the three edge assets the dark->light edge is located in a
          measured card on BOTH screenshots; under the SAME crop it must
          land at the same normalised card x (0.5 for 4:3 assets, 1/3 for
          the 16:9 cover-control) on both pages.

Local card selection excludes slots with slotIndex % 3 == 2: clip index 2
carries a frozen product focus/zoom (0.5, 0.46, 1.06) that the Target has
no equivalent of; those cards are verified against their OWN declared law
(the getMediaFits comparison covers it) and excluded from cross-page
rendered-edge comparison. Recorded, not hidden.

Usage: o2-harness-verify.py --raw=<harness-raw.json> --out=<json>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


VC = _load("v0_culling", "v0_culling.py")
SL = sys.modules["source_layout"]

EDGE_ASSETS = {"grayscale-step": 0.5, "bw-split": 0.5, "cover-control": 0.375}
CLIP_FOCUS = [  # frozen product config, src/content/VideoClips.ts
    {"focusX": 0.5, "focusY": 0.5, "zoom": 1.0},
    {"focusX": 0.5, "focusY": 0.5, "zoom": 1.0},
    {"focusX": 0.5, "focusY": 0.46, "zoom": 1.06},
]


def target_cover(aw, ah):
    """The Target's source-read cover law (bundle offset 1978497)."""
    a, t = aw / ah, 4 / 3
    if a > t:
        sx = t / a
        return {"scaleX": round(sx, 6), "scaleY": 1.0,
                "offsetX": round((1 - sx) / 2, 6), "offsetY": 0.0}
    sy = a / t
    return {"scaleX": 1.0, "scaleY": round(sy, 6),
            "offsetX": 0.0, "offsetY": round((1 - sy) / 2, 6)}


def local_cover(aw, ah, cw, ch, focus):
    """Our MediaFit cover law (src/content/MediaFit.ts)."""
    sa, ca = aw / ah, cw / ch
    rx, ry = 1.0, 1.0
    if sa > ca:
        rx = ca / sa
    else:
        ry = sa / ca
    z = max(1.0, focus["zoom"])
    rx, ry = rx / z, ry / z
    return {"repeatX": rx, "repeatY": ry,
            "offsetX": focus["focusX"] * (1 - rx),
            "offsetY": (1 - focus["focusY"]) * (1 - ry)}


def expected_edge_nx(src_nx, cover_scale_x, cover_offset_x):
    """Where a source-normalised x lands in card space under the crop."""
    return (src_nx - cover_offset_x) / cover_scale_x


def card_rects_with_codes(w, h):
    frame = SL.layout(w, h)
    cam = VC.coverage_camera(0.0, 0.0, frame)
    pred = VC.frame_verdicts(0.0, 0.0, cam, frame)
    rects = []
    for code, v in pred.items():
        if not v["draw"] or not v["aabb"] or not all(v["quad"]):
            continue
        x0, y0, x1, y1 = v["aabb"]
        if x0 < 2 or y0 < 2 or x1 > w - 2 or y1 > h - 2:
            continue
        rects.append((code, (int(x0), int(y0), int(x1), int(y1))))
    return rects


def measure_edge(img, rect):
    """Edge x inside the card's central band, normalised to card width."""
    x0, y0, x1, y1 = rect
    cw, ch = x1 - x0, y1 - y0
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    band = a[y0 + int(ch * 0.40):y0 + int(ch * 0.60),
             x0 + int(cw * 0.08):x1 - int(cw * 0.08)]
    luma = (0.2126 * band[..., 0] + 0.7152 * band[..., 1]
            + 0.0722 * band[..., 2]).mean(axis=0)
    grad = np.abs(np.diff(luma))
    if grad.max() < 8:
        return None
    edge_px = int(np.argmax(grad)) + int(cw * 0.08)
    return round(edge_px / cw, 4)


def main() -> int:
    args = {a[2:].split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:]}
    raw = json.loads(Path(args["raw"]).read_text())
    raw_dir = Path(args["raw"]).parent
    media_manifest = json.loads(
        (REPO / "artifacts/optics-o2/media/media-manifest.json").read_text())
    by_name = {a["name"]: a for a in media_manifest["assets"]}

    assets_out = []
    all_pass = True
    for rec in raw["records"]:
        entry = by_name[rec["asset"]]
        w, h = map(int, rec["viewport"].split("x"))
        aw, ah = entry["width"], entry["height"]
        t_cover = target_cover(aw, ah)

        # local law vs readback (all three clips, incl. clip 2's own law)
        frame = rec["local"]["frame"]
        fit_rows = []
        fits_ok = True
        for i, fit in enumerate(rec["local"]["mediaFits"] or []):
            law = local_cover(aw, ah, frame["planeWidth"], frame["planeHeight"],
                              CLIP_FOCUS[i])
            ok = all(abs(fit[k] - law[k]) < 1e-6
                     for k in ("repeatX", "repeatY", "offsetX", "offsetY"))
            fits_ok = fits_ok and ok
            fit_rows.append({"clip": i, "law": {k: round(law[k], 6) for k in law},
                             "readback": {k: round(fit[k], 6)
                                          for k in ("repeatX", "repeatY",
                                                    "offsetX", "offsetY")},
                             "sourceDims": f"{fit['sourceWidth']}x{fit['sourceHeight']}",
                             "match": ok})
        source_dims_ok = all(r["sourceDims"] == f"{aw}x{ah}" for r in fit_rows)

        # rendered-edge measurement on both screenshots
        render = None
        if rec["asset"] in EDGE_ASSETS and not rec["mobile"]:
            src_nx = EDGE_ASSETS[rec["asset"]]
            rects = card_rects_with_codes(w, h)
            t_img = Image.open(raw_dir / rec["target"]["screenshot"])
            l_img = Image.open(raw_dir / rec["local"]["screenshot"])
            # target: largest card; local: largest card whose clip != 2
            t_code, t_rect = max(rects, key=lambda cv: (cv[1][2] - cv[1][0])
                                 * (cv[1][3] - cv[1][1]))
            l_candidates = [cv for cv in rects if (cv[0] - 1) % 3 != 2]
            l_code, l_rect = max(l_candidates, key=lambda cv: (cv[1][2] - cv[1][0])
                                 * (cv[1][3] - cv[1][1]))
            exp_t = expected_edge_nx(src_nx, t_cover["scaleX"], t_cover["offsetX"])
            l_law = local_cover(aw, ah, frame["planeWidth"], frame["planeHeight"],
                                CLIP_FOCUS[(l_code - 1) % 3])
            exp_l = expected_edge_nx(src_nx, l_law["repeatX"], l_law["offsetX"])
            got_t = measure_edge(t_img, t_rect)
            got_l = measure_edge(l_img, l_rect)
            tol = 0.045
            render = {
                "sourceEdgeNx": src_nx,
                "target": {"card": t_code, "expectedNx": round(exp_t, 4),
                           "measuredNx": got_t,
                           "pass": got_t is not None and abs(got_t - exp_t) <= tol},
                "local": {"card": l_code, "clip": (l_code - 1) % 3,
                          "expectedNx": round(exp_l, 4), "measuredNx": got_l,
                          "pass": got_l is not None and abs(got_l - exp_l) <= tol},
                "toleranceNx": tol,
                "note": "measured through the glass at card centre band, where "
                        "the dome refraction is near zero on both pages",
            }

        checks = {
            "targetAllVideosOurRendition": (
                rec["target"]["allDims"] == [f"{aw}x{ah}"]
                and all(abs(d - entry["durationS"]) < 0.5
                        for d in rec["target"]["allDurations"])),
            "targetFrozen": rec["target"]["allFrozenAt"],
            "localFrozen": bool(rec["local"]["freezeReport"]["frozen"]),
            "targetLandmarks": rec["target"]["landmarkVerdict"]["pass"],
            "localLandmarks": rec["local"]["landmarkVerdict"]["pass"],
            "decodedFrameHashesEqual": rec["decodedFrameHashesEqual"],
            "localFitLawMatchesReadback": fits_ok,
            "localSourceDimsAreAsset": source_dims_ok,
            "renderedEdge": (render is None
                             or (render["target"]["pass"] and render["local"]["pass"])),
        }
        ok = all(checks.values())
        all_pass = all_pass and ok
        assets_out.append({
            "asset": rec["asset"], "viewport": rec["viewport"],
            "mobileEmulation": rec["mobile"],
            "sha256": entry["mp4"]["sha256"],
            "elementaryStreamSha256": entry["elementaryStreamSha256"],
            "elementaryStreamIdenticalMp4VsHls":
                entry["elementaryStreamIdenticalMp4VsHls"],
            "dimensions": f"{aw}x{ah}", "durationS": entry["durationS"],
            "frozenMediaTime": rec["frozenMediaTime"],
            "targetRequestUrlIntercepted": rec["target"]["interceptedUrlSample"],
            "targetRequestsIntercepted": rec["target"]["requestsIntercepted"],
            "targetResponseSha": rec["target"]["servedFiles"],
            "localResponseSha": rec["local"]["servedSha256"],
            "targetCoverScaleOffset": t_cover,
            "localCoverScaleOffset": fit_rows,
            "renderedEdgeVerification": render,
            "decodedFrameProof": {
                "target": rec["target"]["landmarkVerdict"],
                "local": rec["local"]["landmarkVerdict"],
                "fullFrameHashEqual": rec["decodedFrameHashesEqual"],
                "targetHash": rec["target"]["decoded"].get("frameHashFnv1a"),
                "localHash": rec["local"]["decoded"].get("frameHashFnv1a"),
            },
            "checks": checks, "pass": ok,
        })

    doc = {
        "what": "O2 deterministic shared-media harness: Target and Local "
                "consume IDENTICAL locally generated bytes via Playwright "
                "routing; both pages frozen at the same media time; cover "
                "law, decoded frames and served SHAs verified per asset.",
        "design": {
            "sameAssetAllCards": "every clip URL on both pages is fulfilled "
                "with the SAME asset per scenario -- this neutralises the "
                "Target's per-load shuffle AND our slot%3 mapping, so every "
                "card on both pages shows the same pattern",
            "sameBytes": "the Target receives a CMAF/HLS remux (-c copy) of "
                "the exact mp4 the local page receives; the H.264 elementary "
                "streams are byte-identical (asserted at generation, SHAs "
                "recorded); transport containers necessarily differ because "
                "each page keeps its own frozen media pipeline",
            "targetFreeze": "the Target's 19 detached video elements are "
                "captured via a document.createElement hook and paused+seeked "
                "directly; it has no QA API",
            "clip2Exclusion": "local slots with slotIndex%3==2 carry the "
                "frozen product focus/zoom (0.5,0.46,1.06); they are verified "
                "against their own declared law and excluded from cross-page "
                "rendered-edge comparison",
        },
        "freezeTimeS": raw["freeze"],
        "assets": assets_out,
        "pass": all_pass,
    }
    Path(args["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["out"]).write_text(json.dumps(doc, indent=1) + "\n")
    for a in assets_out:
        bad = [k for k, v in a["checks"].items() if not v]
        print(f"{a['asset']} {a['viewport']}: {'PASS' if a['pass'] else 'FAIL ' + ','.join(bad)}")
    print("HARNESS:", "PASS" if all_pass else "FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
