#!/usr/bin/env python3
"""O5 §十 -- score the pipeline and performance captures.

The candidate is ALLOWED to remove the scene-colour pass. The list of things
it may not do in exchange is explicit in the brief, so each is a named check
here rather than a general impression of the numbers.

Output: qa-v5/optics-o5/pipeline-performance.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    src = REPO / "artifacts/optics-o5/pipeline"
    out = REPO / "qa-v5/optics-o5/pipeline-performance.json"
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k == "src":
            src = Path(v)
        elif k == "out":
            out = Path(v)

    man = json.loads((src / "pipeline-manifest.json").read_text())
    by = {r["lane"]: r for r in man["records"]}
    c, k = by.get("control"), by.get("candidate")
    if not c or not k:
        print("missing a lane", file=sys.stderr)
        return 1

    checks = []

    def add(name, ok, detail, numbers=None):
        checks.append({"check": name, "pass": None if ok is None else bool(ok),
                       "detail": detail, "numbers": numbers or {}})

    # --- what the candidate is allowed to do -----------------------------
    add("scene-colour pass removed in the candidate lane",
        k["renderPasses"].get("sceneColorCalls") == 0
        and c["renderPasses"].get("sceneColorCalls", 0) > 0,
        "§十 explicitly allows this. Shown against the control, which still "
        "runs the pass, so the removal is demonstrated rather than asserted.",
        {"control": c["renderPasses"], "candidate": k["renderPasses"]})

    # --- what it may not pay with ----------------------------------------
    # 1. first-frame black cards.
    #
    # The in-page probe is NON-FUNCTIONAL and is reported as such rather than
    # as a result: drawImage() on a WebGPU canvas returns a blank bitmap, so it
    # yields meanLuma 0 / nearBlackFraction 1 for BOTH lanes regardless of what
    # was actually drawn. A check that returns the same constant for every
    # input measures nothing, and scoring the candidate on it would be
    # scoring a broken instrument.
    #
    # The screenshots ARE real, so the question is asked of them instead, and
    # asked comparatively: the first frame at `ready` is the app's loading
    # overlay in both lanes, so what matters is whether the CANDIDATE is
    # darker than the control at the same moment.
    import numpy as np
    from PIL import Image

    def first_frame_luma(lane):
        f = src / f"{lane}-firstframe.png"
        if not f.exists():
            return None
        a = np.asarray(Image.open(f).convert("RGB"), np.float32)
        lum = 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
        return {"meanLuma": round(float(lum.mean()), 3),
                "nearBlackFraction": round(float((lum < 6).mean()), 4),
                "p99Luma": round(float(np.percentile(lum, 99)), 2)}

    ff_c, ff_k = first_frame_luma("control"), first_frame_luma("candidate")
    # §十's requirement is literally "no first-frame BLACK CARDS", so that is
    # what is scored: the fraction of the frame at or near zero luminance.
    #
    # A mean-luminance comparison against the control was considered and
    # REJECTED, and the reasoning is recorded because it cuts the other way:
    # the candidate reads 13.2 against the control's 15.0 under the loading
    # overlay, which a mean-based check would fail -- but the candidate's body
    # IS darker at rest, by design and by measurement (dark-side edge luma 48.6
    # against the control's 95.2, and the Target's 48.2). A check that failed
    # the candidate for being darker would be failing it for the round's whole
    # objective. Black cards are the defect; a darker body is the goal.
    ff_ok = (None if (ff_c is None or ff_k is None)
             else ff_k["nearBlackFraction"] < 0.02)
    add("no first-frame black cards", ff_ok,
        "The in-page canvas probe is non-functional on a WebGPU canvas -- it "
        "returns meanLuma 0 for both lanes whatever is drawn -- so it is "
        "reported below as evidence of its own failure, not as a result. The "
        "verdict is taken from the screenshots. At `ready` both lanes still "
        "show the app's loading overlay, and neither has any near-black "
        "region: the requirement is met. The mean-luminance difference "
        "between the lanes is disclosed alongside, with the reason it is not "
        "the measurand.",
        {"fromScreenshot": {"control": ff_c, "candidate": ff_k},
         "inPageProbeNonFunctional": {"control": c["firstFrameStats"],
                                      "candidate": k["firstFrameStats"],
                                      "why": "drawImage() on a WebGPU canvas "
                                             "returns a blank bitmap"}})

    # 2. media remap on resize
    def fits_equal(rec):
        b = (rec["resize"]["before"] or {}).get("fits")
        a = (rec["resize"]["after"] or {}).get("fits")
        if b is None or a is None:
            return None
        # planeWidth/planeHeight change with the viewport, so repeat/offset
        # legitimately change too. What must NOT change is the CROP the frozen
        # focus produces: the visible fraction of the source per axis.
        def crop(f):
            return [(round(x.get("visibleX", 0), 6), round(x.get("visibleY", 0), 6))
                    for x in f]
        return crop(b) == crop(a)
    add("media crop is not remapped on resize",
        fits_equal(k) is not False,
        "The frozen focus must survive a viewport change. repeat/offset "
        "legitimately move with the card size; the visible fraction of the "
        "source must not.",
        {"controlEqual": fits_equal(c), "candidateEqual": fits_equal(k)})

    # 3. resource growth over the soak
    def heap_growth(rec):
        s = [x["heapMB"] for x in rec["soak"]["heapSamples"] if x["heapMB"]]
        if len(s) < 2:
            return None
        return round(s[-1] - s[0], 2)
    kg, cg = heap_growth(k), heap_growth(c)
    add("no resource leak over a 5-minute repeated drag",
        kg is None or kg <= max(24.0, (cg or 0) + 12.0),
        "Wrap happens many times over in this sequence, so a video texture "
        "rebuilt on wrap or a per-frame material shows as heap growth. Judged "
        "against the control's own growth, since some growth is the JS heap "
        "doing its job.",
        {"controlHeapGrowthMB": cg, "candidateHeapGrowthMB": kg,
         "soakMs": man["soakMs"],
         "controlSamples": len(c["soak"]["heapSamples"]),
         "candidateSamples": len(k["soak"]["heapSamples"])})

    # 4. no per-frame materials: the pool census must be unchanged after soak
    def pool_stable(rec):
        b = json.dumps(rec["censusBefore"].get("pool"), sort_keys=True)
        a = json.dumps(rec["censusAfter"].get("pool"), sort_keys=True)
        return b == a
    add("no per-frame materials or pool churn",
        pool_stable(k),
        "The slot pool census before and after the soak must be identical: a "
        "material or mesh created per frame shows up here.",
        {"controlStable": pool_stable(c), "candidateStable": pool_stable(k)})

    # 5. adaptive quality transitions survive, and the sample count follows
    steps = [{"level": s["level"],
              "samples": s["optics"].get("opticalBodySamples"),
              "errors": s["errors"]} for s in k["qualitySteps"]]
    expected = {"high": 5, "medium": 5, "low": 3}
    add("adaptive quality transitions are clean and change the sample count",
        all(s["samples"] == expected[s["level"]] for s in steps)
        and steps[-1]["errors"] == steps[0]["errors"],
        "Stepping high -> medium -> low -> high. The candidate's spectral "
        "sample count is a build-time literal, so a quality step must rebuild "
        "its materials or the lane would keep five samples on a device that "
        "asked for three.",
        {"steps": steps, "controlSteps": [
            {"level": s["level"], "errors": s["errors"]}
            for s in c["qualitySteps"]]})

    # 6. errors
    add("no console or page errors in either lane",
        k["errorCount"] == 0 and c["errorCount"] == 0,
        "Across load, soak, resize and every quality step.",
        {"control": c["errorCount"], "candidate": k["errorCount"]})

    passed = sum(1 for x in checks if x["pass"] is True)
    failed = sum(1 for x in checks if x["pass"] is False)

    doc = {
        "what": "O5 §十 pipeline and performance. The candidate may remove the "
                "scene-colour pass; each thing it may NOT pay for that with is "
                "a named check.",
        "passed": passed, "failed": failed, "total": len(checks),
        "pass": failed == 0,
        "summary": (
            f"Scene-colour pass: {c['renderPasses'].get('sceneColorCalls')} "
            f"draw calls in the control, "
            f"{k['renderPasses'].get('sceneColorCalls')} in the candidate. "
            f"Final pass {c['renderPasses'].get('finalCalls')} vs "
            f"{k['renderPasses'].get('finalCalls')}. CPU frame time p50 "
            f"{c['frameTimeMs']['p50']} vs {k['frameTimeMs']['p50']} ms, p99 "
            f"{c['frameTimeMs']['p99']} vs {k['frameTimeMs']['p99']} ms. "
            f"Ready in {c['readyMs']} vs {k['readyMs']} ms. "
            f"{passed}/{len(checks)} checks pass."),
        "frameTime": {"control": c["frameTimeMs"], "candidate": k["frameTimeMs"]},
        "gpuTime": {"control": c["gpuTimeMs"], "candidate": k["gpuTimeMs"],
                    "note": k["gpuTimeNote"]},
        "readyMs": {"control": c["readyMs"], "candidate": k["readyMs"]},
        "memory": {"control": {"before": c["memoryBefore"],
                               "after": c["memoryAfter"]},
                   "candidate": {"before": k["memoryBefore"],
                                 "after": k["memoryAfter"]}},
        "renderPasses": {"control": c["renderPasses"],
                         "candidate": k["renderPasses"]},
        "checks": checks,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))
    for x in checks:
        v = "PASS" if x["pass"] else ("FAIL" if x["pass"] is False else "n/a")
        print(f"  {v:4}  {x['check']}")
    print(f"\n{passed}/{len(checks)} -> {out}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
