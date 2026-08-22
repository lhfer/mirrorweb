#!/usr/bin/env python3
"""O4 §十二 cross-sections and the true-silhouette / gutter overlay.

Two deliverables the package requires:

  side-band cross-sections   per-card inward luminance profiles for both
                             lanes in BOTH states, so a reader can see the
                             body floor and the shipped band as curves
                             rather than as two numbers.
  silhouette overlay         item 9's primary exhibit: the true rendered
                             silhouette boundary with every differing pixel
                             marked, which is what shows they hug it.

Profiles are per card and thresholded per card -- the sealed coding -- so
the widths printed on the charts are the same numbers the gate scored.

Usage: o4-crosssection.py [--gate=<dir>] [--out=<dir>]
"""
from __future__ import annotations

import importlib.util
import json
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


S = _load("o4_xs_stats", "o2_optics_stats.py")
I = _load("o4_xs_ins", "o4_instruments.py")

OUTSIDE, INSIDE, THRESHOLD = 4, 24, 60.0
COLOR = {("control", "sysBOff"): (225, 90, 70),
         ("candidate", "sysBOff"): (90, 150, 250),
         ("control", "sysBOn"): (250, 170, 90),
         ("candidate", "sysBOn"): (120, 220, 200)}


def _lum(p):
    return 0.2126 * p[..., 0] + 0.7152 * p[..., 1] + 0.0722 * p[..., 2]


def side_profiles(img, rects):
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    out = []
    for (x0, y0, x1, y1) in rects:
        ch = y1 - y0
        seg = a[y0 + int(ch * .42):y0 + int(ch * .58),
                max(0, x0 - OUTSIDE):x0 + INSIDE]
        if seg.shape[1] == OUTSIDE + INSIDE:
            out.append([round(float(v), 2) for v in _lum(seg).mean(axis=0)])
    return out


def band_of_one(prof):
    w, started = 0, False
    for v in prof[OUTSIDE:]:
        if v > THRESHOLD:
            started, w = True, w + 1
        elif started:
            break
    return w


def chart(rows, title, path):
    W, H, PAD = 980, 430, 58
    im = Image.new("RGB", (W, H), (18, 18, 22))
    d = ImageDraw.Draw(im)
    x_of = lambda i: PAD + i * (W - 2 * PAD) / (OUTSIDE + INSIDE - 1)
    y_of = lambda v: H - PAD - (v / 255.0) * (H - 2 * PAD)
    for v in range(0, 256, 32):
        d.line([(PAD, y_of(v)), (W - PAD, y_of(v))], fill=(44, 44, 50))
        d.text((6, y_of(v) - 6), f"{v:3d}", fill=(130, 130, 140))
    d.line([(x_of(OUTSIDE), PAD), (x_of(OUTSIDE), H - PAD)], fill=(120, 120, 130))
    d.text((x_of(OUTSIDE) - 12, H - PAD + 6), "edge", fill=(150, 150, 160))
    d.line([(PAD, y_of(THRESHOLD)), (W - PAD, y_of(THRESHOLD))], fill=(200, 170, 60))
    d.text((W - PAD - 100, y_of(THRESHOLD) - 14), "band threshold 60",
           fill=(200, 170, 60))
    for px in (5, 10, 15, 20):
        d.text((x_of(OUTSIDE + px) - 6, H - PAD + 6), str(px), fill=(110, 110, 120))
    for r in rows:
        col = COLOR[(r["lane"], r["state"])]
        for prof in r["profiles"]:
            for i in range(len(prof) - 1):
                d.line([(x_of(i), y_of(prof[i])), (x_of(i + 1), y_of(prof[i + 1]))],
                       fill=col, width=3 if r["state"] == "sysBOff" else 2)
    d.text((PAD, 12), title, fill=(235, 235, 240))
    y = 30
    for r in rows:
        per = [band_of_one(p) for p in r["profiles"]]
        d.text((PAD, y), f"{r['lane']} / {r['state']}   band = "
                         f"{round(float(np.mean(per)), 1)} px   per card {per}",
               fill=COLOR[(r["lane"], r["state"])])
        y += 15
    im.save(path)


def overlay(gate_dir, out, control_f, candidate_f, mediaonly_f, label):
    """Item 9's exhibit: the true silhouette boundary and every differing
    pixel, so a reader can see that the diffs hug the boundary."""
    sil = I.true_silhouette(gate_dir / control_f, gate_dir / mediaonly_f)
    a = np.asarray(Image.open(gate_dir / control_f).convert("RGB")).astype(int)
    b = np.asarray(Image.open(gate_dir / candidate_f).convert("RGB")).astype(int)
    diff = (np.abs(a - b).max(axis=2) > 0) & (~sil)
    grown = sil.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            grown |= np.roll(np.roll(sil, dy, axis=0), dx, axis=1)
    boundary = grown & ~sil

    base = (np.asarray(Image.open(gate_dir / control_f).convert("RGB"))
            .astype(np.float32) * 0.35)
    base[boundary] = np.array([60, 200, 120], np.float32)     # silhouette edge
    base[diff] = np.array([255, 60, 60], np.float32)          # differing px
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(im)
    d.text((14, 12), f"{label}: true silhouette boundary (green) and every "
                     f"pixel where the two lanes differ outside it (red)",
           fill=(255, 255, 255))
    d.text((14, 28), f"differing outside silhouette = {int(diff.sum())}, "
                     f"of which within 1 px of the boundary = "
                     f"{int((diff & grown).sum())}, beyond = "
                     f"{int((diff & ~grown).sum())}", fill=(255, 220, 220))
    im.save(out)
    return {"asset": label, "differingOutside": int(diff.sum()),
            "within1px": int((diff & grown).sum()),
            "beyond1px": int((diff & ~grown).sum())}


def main() -> int:
    gd = REPO / "artifacts/optics-o4/gate"
    out = REPO / "artifacts/optics-o4/crosssection"
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k == "gate":
            gd = Path(v)
        elif k == "out":
            out = Path(v)
    out.mkdir(parents=True, exist_ok=True)
    man = json.loads((gd / "gate-manifest.json").read_text())

    results, overlays = [], []
    for vp in ["1440x900", "390x844", "844x390"]:
        w, h = (int(x) for x in vp.split("x"))
        rects = [q for _, q in S.rects_at(w, h)]
        basis = "fully-visible cards"
        if not rects:
            VC, SL = sys.modules["v0_culling"], sys.modules["source_layout"]
            frame = SL.layout(w, h)
            cam = VC.coverage_camera(0.0, 0.0, frame)
            cand = []
            for v in VC.frame_verdicts(0.0, 0.0, cam, frame).values():
                if v.get("draw") and v.get("aabb"):
                    x0, y0, x1, y1 = v["aabb"]
                    cand.append((x1 - x0, (int(max(x0, 0)), int(max(y0, 0)),
                                           int(min(x1, w)), int(min(y1, h)))))
            rects = [max(cand)[1]] if cand else []
            basis = "no fully-visible card -- widest drawn card"
        rows = []
        for rec in man["records"]:
            if (rec["kind"] != "lane" or rec.get("vp") != vp
                    or rec.get("asset") != "bw-split"
                    or rec["lane"] not in ("control", "candidate")):
                continue
            profs = side_profiles(Image.open(gd / rec["file"]), rects)
            rows.append({"lane": rec["lane"], "state": rec["state"], "vp": vp,
                         "file": rec["file"], "rectBasis": basis,
                         "profiles": profs,
                         "bandPx": round(float(np.mean(
                             [band_of_one(p) for p in profs])), 1) if profs else None})
        if rows:
            chart([r for r in rows if r["state"] == "sysBOff"],
                  f"body floor, System B OFF -- bw-split {vp}",
                  out / f"side-bodyfloor-{vp}.png")
            chart(rows, f"body floor and shipped band -- bw-split {vp} "
                        f"(thick = System B OFF, thin = shipped)",
                  out / f"side-both-{vp}.png")
        results.extend(rows)

    for asset in ["bw-split", "rgb-bars"]:
        try:
            overlays.append(overlay(
                gd, out / f"silhouette-overlay-{asset}.png",
                f"control-sysBOn-{asset}-1440x900.png",
                f"candidate-sysBOn-{asset}-1440x900.png",
                f"control-mediaonly-{asset}-1440x900.png", asset))
        except FileNotFoundError:
            pass

    (out / "crosssection.json").write_text(json.dumps({
        "what": "O4 side-band cross-sections for both lanes in both states, "
                "and the true-silhouette / gutter overlay that is item 9's "
                "exhibit.",
        "profileRange": {"outsidePx": OUTSIDE, "insidePx": INSIDE},
        "bandThreshold": THRESHOLD,
        "coding": "per card, thresholded per card, widths averaged -- the "
                  "sealed coding, so the widths on the charts are the numbers "
                  "the gate scored.",
        "asset": "bw-split", "profiles": results,
        "silhouetteOverlays": overlays,
    }, indent=1))
    for r in results:
        if r["vp"] == "1440x900":
            print(f"  {r['lane']:10s} {r['state']:8s} band={r['bandPx']}")
    for o in overlays:
        print(f"  overlay {o['asset']}: {o['differingOutside']} outside, "
              f"{o['within1px']} within 1px, {o['beyond1px']} beyond")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
