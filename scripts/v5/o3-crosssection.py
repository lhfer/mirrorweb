#!/usr/bin/env python3
"""O3 band cross-sections -- the §十 top-band / side-band deliverable, and
the exhibit any band-width number has to be read against.

`reflection_band` reduces a profile to one number: how many consecutive
pixels inward from the card edge exceed luma 60. That number cannot say
WHERE the light comes from. These profiles can, because they are taken at
the registered floor states as well as at `full`:

  env0rim0   System B entirely off. The two lanes are identical here by
             construction -- same shader inputs, same everything. Whatever
             band survives at this state is painted by the frozen
             refraction / dispersion / adaptive-contrast composition, which
             O3 is forbidden to touch.
  env0rim1   rim only.
  env1rim0   environment reflection only.
  full       the scored state.

Profiles run from 4 px OUTSIDE the card edge to 24 px inside, so the edge
transition itself is visible rather than assumed.

Output: crosssection.json plus one PNG chart per viewport (PIL, no plotting
dependency -- the repo has none).

Usage: o3-crosssection.py [--measure=<dir>] [--out=<dir>]
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


S = _load("o3_stats", "o2_optics_stats.py")

OUTSIDE = 4
INSIDE = 24
THRESHOLD = 60.0          # the same threshold reflection_band scores on
LANE_COLOR = {"target": (40, 190, 90), "control": (225, 90, 70),
              "candidate": (90, 150, 250)}
STATE_DASH = {"full": 0, "env0rim0": 6, "env0rim1": 3, "env1rim0": 10}


def _lum(p):
    return 0.2126 * p[..., 0] + 0.7152 * p[..., 1] + 0.0722 * p[..., 2]


def side_profile(img, rects):
    """PER-CARD inward luminance from the LEFT (dark-media) card edge.

    Per card, not averaged across cards. Averaging first was the earlier
    coding here and it is wrong: the cards' bright bands sit at slightly
    different depths, so a mean profile smears them and clears the
    threshold for longer than any single card does -- it read the Target
    at 9 px where the Target measures 3.3. The gate metric
    (`reflection_band`) measures each card and means the WIDTHS, so these
    profiles are per card and the chart and the gate are one measurement
    rather than two that resemble each other.
    """
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    prof = []
    for (x0, y0, x1, y1) in rects:
        ch = y1 - y0
        rows = a[y0 + int(ch * 0.42):y0 + int(ch * 0.58)]
        seg = rows[:, max(0, x0 - OUTSIDE):x0 + INSIDE]
        if seg.shape[1] == OUTSIDE + INSIDE:
            prof.append([round(float(v), 2) for v in _lum(seg).mean(axis=0)])
    return prof or None


def top_profile(img, rects):
    """PER-CARD downward luminance from the TOP card edge -- §十's top
    band, the strip the review called a wide grey frame."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    prof = []
    for (x0, y0, x1, y1) in rects:
        cw = x1 - x0
        cols = a[:, x0 + int(cw * 0.42):x0 + int(cw * 0.58)]
        seg = cols[max(0, y0 - OUTSIDE):y0 + INSIDE]
        if seg.shape[0] == OUTSIDE + INSIDE:
            prof.append([round(float(v), 2) for v in _lum(seg).mean(axis=1)])
    return prof or None


def band_of_one(prof):
    """`reflection_band`'s coding, on a single card's profile."""
    w, started = 0, False
    for v in prof[OUTSIDE:]:
        if v > THRESHOLD:
            started, w = True, w + 1
        elif started:
            break
    return w


def band_from_profiles(profs):
    """Per-card widths, then the mean -- exactly the gate's coding."""
    if not profs:
        return None
    return round(float(np.mean([band_of_one(p) for p in profs])), 1)


def chart(rows, title, path, key):
    """One PNG: luma vs px inward. Solid = full, dashed = floor states."""
    W, H, PAD = 980, 420, 58
    im = Image.new("RGB", (W, H), (18, 18, 22))
    d = ImageDraw.Draw(im)
    x_of = lambda i: PAD + i * (W - 2 * PAD) / (OUTSIDE + INSIDE - 1)
    y_of = lambda v: H - PAD - (v / 255.0) * (H - 2 * PAD)

    for v in range(0, 256, 32):                       # luma grid
        d.line([(PAD, y_of(v)), (W - PAD, y_of(v))], fill=(44, 44, 50))
        d.text((6, y_of(v) - 6), f"{v:3d}", fill=(130, 130, 140))
    d.line([(x_of(OUTSIDE), PAD), (x_of(OUTSIDE), H - PAD)], fill=(120, 120, 130))
    d.text((x_of(OUTSIDE) - 12, H - PAD + 6), "edge", fill=(150, 150, 160))
    d.line([(PAD, y_of(THRESHOLD)), (W - PAD, y_of(THRESHOLD))], fill=(200, 170, 60))
    d.text((W - PAD - 96, y_of(THRESHOLD) - 14), "band threshold 60",
           fill=(200, 170, 60))
    for px in (5, 10, 15, 20):
        d.text((x_of(OUTSIDE + px) - 6, H - PAD + 6), str(px), fill=(110, 110, 120))

    # One line per CARD, so the spread between cards is visible instead of
    # being averaged into a band no card actually has.
    for r in rows:
        profs = r[key]
        if not profs:
            continue
        col = LANE_COLOR[r["lane"]]
        dash = STATE_DASH.get(r["state"], 0)
        for prof in profs:
            for i in range(len(prof) - 1):
                if dash and (i // max(dash // 2, 1)) % 2:
                    continue
                d.line([(x_of(i), y_of(prof[i])), (x_of(i + 1), y_of(prof[i + 1]))],
                       fill=col, width=3 if r["state"] == "full" else 2)
    d.text((PAD, 12), title, fill=(235, 235, 240))
    y = 30
    for r in rows:
        if not r[key]:
            continue
        per = [band_of_one(p) for p in r[key]]
        d.text((PAD, y),
               f"{r['lane']} / {r['state']}   band = {band_from_profiles(r[key])} px"
               f"   per card {per}",
               fill=LANE_COLOR[r["lane"]])
        y += 15
    im.save(path)


def main():
    opts = {"measure": REPO / "artifacts/optics-o3/measure",
            "out": REPO / "artifacts/optics-o3/crosssection"}
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k in opts:
            opts[k] = Path(v)
    out = Path(opts["out"])
    out.mkdir(parents=True, exist_ok=True)
    md = Path(opts["measure"])
    man = json.loads((md / "measure-manifest.json").read_text())

    results = []
    for vp in ["1440x900", "390x844", "844x390"]:
        w, h = (int(x) for x in vp.split("x"))
        rects = [rc for _, rc in S.rects_at(w, h)]
        basis = "fully-visible cards"
        if not rects:
            # The recorded 844x390 fallback: no card clears the viewport
            # margin, so the profile rides the widest drawn card instead.
            # Carried explicitly so nothing reads it as the same basis.
            basis = "no fully-visible card -- widest drawn card"
            cand = []
            VC, SL = sys.modules["v0_culling"], sys.modules["source_layout"]
            frame = SL.layout(w, h)
            cam = VC.coverage_camera(0.0, 0.0, frame)
            for code, v in VC.frame_verdicts(0.0, 0.0, cam, frame).items():
                if v["draw"] and v["aabb"]:
                    x0, y0, x1, y1 = v["aabb"]
                    cand.append((x1 - x0, (int(max(x0, 0)), int(max(y0, 0)),
                                           int(min(x1, w)), int(min(y1, h)))))
            if cand:
                rects = [max(cand)[1]]
        rows = []
        for rec in man["records"]:
            if rec.get("vp") != vp or rec.get("asset") != "bw-split":
                continue
            if rec["kind"] == "target" and rec.get("state") == "rest":
                lane, state = "target", "full"
            elif rec["kind"] == "local" and rec.get("state") in (
                    "full", "env0rim0", "env0rim1", "env1rim0"):
                lane, state = rec["lane"], rec["state"]
            else:
                continue
            img = Image.open(md / rec["file"])
            rows.append({"lane": lane, "state": state, "vp": vp,
                         "file": rec["file"], "rectBasis": basis,
                         "side": side_profile(img, rects),
                         "top": top_profile(img, rects)})
        for r in rows:
            r["sideBandPx"] = band_from_profiles(r["side"])
            r["topBandPx"] = band_from_profiles(r["top"])
        results.extend(rows)
        full = [r for r in rows if r["state"] == "full"]
        chart(full, f"side band (dark media), bw-split {vp} -- Target vs O2 "
                    f"control vs O3 candidate", out / f"side-full-{vp}.png", "side")
        chart(full, f"top band, bw-split {vp} -- Target vs O2 control vs O3 "
                    f"candidate", out / f"top-full-{vp}.png", "top")
        floors = [r for r in rows if r["lane"] != "target"]
        chart(floors, f"side band decomposition, bw-split {vp} -- solid full, "
                      f"dashed floor states", out / f"side-floors-{vp}.png", "side")

    # The decomposition claim, computed rather than asserted.
    def get(vp, lane, state, key="side"):
        for r in results:
            if r["vp"] == vp and r["lane"] == lane and r["state"] == state:
                return r[key]
        return None

    findings = {}
    for vp in ["1440x900", "390x844", "844x390"]:
        c0 = get(vp, "control", "env0rim0")
        d0 = get(vp, "candidate", "env0rim0")
        if not c0 or not d0:
            continue
        findings[vp] = {
            "lanesIdenticalWithSystemBOff": c0 == d0,
            "frozenBaseBandPx": band_from_profiles(c0),
            "controlFullBandPx": band_from_profiles(get(vp, "control", "full")),
            "candidateFullBandPx": band_from_profiles(get(vp, "candidate", "full")),
            "targetBandPx": band_from_profiles(get(vp, "target", "full")),
            "reading": "the frozen base -- refraction, dispersion, "
                       "adaptive contrast, with System B entirely off -- "
                       "already paints this band before any reflection "
                       "exists. No change to the reflection support can "
                       "take the candidate below it.",
        }

    (out / "crosssection.json").write_text(json.dumps({
        "what": "O3 band cross-sections at the registered floor states.",
        "profileRange": {"outsidePx": OUTSIDE, "insidePx": INSIDE},
        "bandThreshold": THRESHOLD,
        "asset": "bw-split",
        "decomposition": findings,
        "profiles": results,
    }, indent=1))
    for vp, f in findings.items():
        print(f"{vp}: base={f['frozenBaseBandPx']}px "
              f"control={f['controlFullBandPx']}px "
              f"candidate={f['candidateFullBandPx']}px "
              f"target={f['targetBandPx']}px "
              f"lanesIdenticalOff={f['lanesIdenticalWithSystemBOff']}")
    print(f"-> {out}")


if __name__ == "__main__":
    main()
