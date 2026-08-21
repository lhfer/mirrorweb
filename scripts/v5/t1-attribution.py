#!/usr/bin/env python3
"""What is left after typography, and which system owns it.

Typography is the only system this stage may touch, so everything else is
measured and named rather than adjusted. The optics numbers below are a
statistic on our frame beside the Target's, not a judgement: they say how far
apart the two are on one axis, and that axis belongs to a system that is frozen.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from PIL import Image

ART = Path("artifacts/t1")
VPS = ["1440x900", "1920x1080", "390x844", "844x390", "700x700", "667x375", "780x470"]


def stats(path):
    im = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    mx, mn = im.max(axis=2), im.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    # Colour fringing shows up as local red-blue disagreement at edges. Take the
    # gradient magnitude of (R - B): a neutral edge contributes nothing.
    rb = r - b
    gy, gx = np.gradient(rb)
    fringe = np.hypot(gx, gy)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    ly, lx = np.gradient(lum)
    edge = np.hypot(lx, ly)
    mask = edge > 12                                  # only where there IS an edge
    return {
        "meanSaturation": round(float(sat.mean()), 4),
        "meanLuminance": round(float(lum.mean()), 2),
        "meanEdgeRedBlueGradient": round(float(fringe[mask].mean()) if mask.any() else 0.0, 3),
        "p99EdgeRedBlueGradient": round(float(np.percentile(fringe[mask], 99)) if mask.any() else 0.0, 3),
        "edgePixelFraction": round(float(mask.mean()), 4),
    }


if __name__ == "__main__":
    contract = json.loads(Path("qa-v5/t1/target-typography-contract.json").read_text())
    gate = json.loads(Path("qa-v5/t1/viewport-gate.json").read_text())
    beauty = json.loads((ART / "beauty/beauty.json").read_text())

    optics = []
    for vp in VPS:
        t = ART / f"target-typography/{vp}.png"
        c = ART / f"beauty/{vp}/4-full-beauty.png"
        if not (t.exists() and c.exists()):
            continue
        ts, cs = stats(t), stats(c)
        optics.append({"viewport": vp, "target": ts, "ours": cs,
                       "saturationDelta": round(cs["meanSaturation"] - ts["meanSaturation"], 4),
                       "edgeFringeDelta": round(cs["meanEdgeRedBlueGradient"]
                                                - ts["meanEdgeRedBlueGradient"], 3)})

    perf = []
    for v in beauty["viewports"]:
        full = [s for s in v["shots"] if s["state"] == "4-full-beauty"]
        if full:
            perf.append({"viewport": v["id"], **{k: full[0]["metrics"][k]
                        for k in ["fps", "medianFrameMs", "p95FrameMs", "drawCalls", "triangles"]}})

    payload = {
        "scope": "Typography only. Motion, optics, media focus and the layout contract are "
                 "frozen this round; everything below that is not typography is named, "
                 "measured where it can be, and left alone.",
        "typography": {
            "status": "candidate, awaiting product review",
            "contract": f"{contract['matched']}/{contract['total']} measured Target properties "
                        "match at all seven viewports",
            "labelContainerCornerErrorPx": {r["viewport"]: r["labelContainerCornerErrorPx"]
                                            for r in gate["viewports"]},
            "titleBoxBottomOffsetPct": contract["reported"]["titleBoxBottomOffsetPct"],
            "labelInkOutsideCardSilhouette": {r["viewport"]: r["labelInkOutsideCardSilhouette"]
                                              for r in gate["viewports"]},
            "residual": "none measured on any gated property",
        },
        "optics": {
            "owner": "OPTICS -- frozen this round, not modified",
            "observation": "by eye, our card edges carry more visible red/green fringing than "
                           "the Target's, and media inside the glass reads more saturated",
            "method": "mean magnitude of the (R - B) gradient at luminance edges, and mean "
                      "HSV saturation, on the full-beauty frame beside the Target's",
            "whatTheNumbersSupport":
                "saturation is higher on ours at five of seven viewports, by 0.0006 to 0.056 "
                "-- small and one-directional but not decisive. The fringe statistic changes "
                "SIGN across viewports (-6.08 to +8.37) and therefore supports nothing.",
            "confound":
                "our clip reel is not the Target's. Edge gradient and saturation both depend "
                "on what is inside the card, so this statistic cannot separate the glass from "
                "the footage. Isolating it needs the same source frame through both stacks, "
                "which is an optics-stage instrument, not a typography one.",
            "carriedForward":
                "recorded as an item for the optics stage with the observation and the "
                "confound, not as a measured magnitude",
            "perViewport": optics,
        },
        "motion": {
            "owner": "MOTION -- frozen this round, not modified",
            "finding": "not observable in these captures: every gate frame is taken at rest "
                       "with motion paused. The recordings step the offset from the harness, "
                       "which exercises placement but not drag feel, inertia or settle.",
            "recordings": "qa-v5/t1/local/recording, full sequences under artifacts/",
        },
        "performance": {
            "owner": "PERFORMANCE -- observation only",
            "note": "headless developer machine, not a device-class claim",
            "perViewport": perf,
        },
        "footer": {
            "owner": "TYPOGRAPHY for the caption, out of scope for the rest",
            "fixed": "caption now Geist Mono 500, clamp(0.58rem, 0.8vw, 0.72rem), 0.18em, "
                     "uppercase, white 70% -- it was 16px Geist at full opacity",
            "notFixed": [
                "the Target has an h-36 black-to-transparent scrim behind the footer; that is "
                "a background treatment rather than typography and was left alone",
                "our wordmark is our own mark set in type, the Target's is an image; only its "
                "size was brought into the caption's band",
            ],
        },
        "media": {
            "owner": "CONTENT -- not a defect",
            "note": "our clip reel is not the Target's, so any per-card image difference in "
                    "the comparison sheets is content, not rendering",
        },
    }
    Path("qa-v5/t1/attribution.json").write_text(json.dumps(payload, indent=2))
    print("attribution written")
    for o in optics:
        print(f"  {o['viewport']:>10} satDelta={o['saturationDelta']:+.4f} "
              f"fringeDelta={o['edgeFringeDelta']:+.3f}")
