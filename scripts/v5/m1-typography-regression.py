#!/usr/bin/env python3
"""The accepted T1 typography gates, re-run at the motion tip.

Typography is frozen this stage. "Frozen" is a claim about a diff, and a diff
cannot see a regression that comes from somewhere else -- the motion work moved
the camera the label layer projects through, which is exactly the kind of change
a file-level freeze does not cover. So the gates are re-run rather than inferred.

It also carries the T1 depth result forward. T1 recorded
`actualOverlappingCardPlaneSamples = 0`: no two card planes were ever seen
overlapping, so the depth row established the clip structure and single-card
interior ordering, not real occlusion ordering. Motion moves the planes, so the
count is re-taken at the four extremes of the pointer orbit and three scroll
offsets. If it is still zero the row says so in those words and claims nothing
more.

Usage: m1-typography-regression.py --alignment=<json> --ink=<json> --depth=<json>
                                   --out=<json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def load(p):
    q = Path(p)
    return json.loads(q.read_text()) if q.exists() else None


if __name__ == "__main__":
    args = {a.split("=", 1)[0][2:]: a.split("=", 1)[1]
            for a in sys.argv[1:] if a.startswith("--") and "=" in a}
    align = load(args["alignment"])
    ink = load(args["ink"])
    depth = load(args["depth"])

    report = {
        "what": "the accepted T1 typography gates, re-run at the motion tip",
        "why": "typography is frozen by diff this stage, and a diff cannot see a regression "
               "that arrives from another file -- the motion work moved the camera the label "
               "layer projects through",
        "rows": [], "assertions": []}

    def A(name, ok, detail=None):
        report["assertions"].append({"assertion": name, "pass": bool(ok), "detail": detail})

    for name, doc, src in (("container alignment", align, args["alignment"]),
                           ("label ink", ink, args["ink"]),
                           ("depth / clipping (pointer-swept)", depth, args["depth"])):
        if doc is None:
            report["rows"].append({"gate": name, "source": src, "verdict": "MISSING"})
            A(f"{name}: re-run at this tip", False, f"{src} was not produced")
            continue
        row = {"gate": name, "source": src, "verdict": doc.get("verdict"),
               "passed": doc.get("passed"), "total": doc.get("total")}
        report["rows"].append(row)
        A(f"{name}: PASS at this tip", doc.get("verdict") == "PASS", row)

    # ---- depth carry-forward ---------------------------------------------
    if depth is not None:
        overlapped = depth.get("actualOverlappingCardPlaneSamples")
        swept = depth.get("pointerSweep")
        moved = [{"viewport": v["id"], "cameraSpread": v.get("pointerSweepMovedCameraBy")}
                 for v in depth.get("viewports", [])]
        report["depthCarryForward"] = {
            "pointerPositionsSwept": swept,
            "scrollOffsetsSwept": [[0, 0], [313, 197], [-640, 480]],
            "cameraActuallyMovedPerViewport": moved,
            "depthSamplesWithAnotherCardPlaneOverThem": overlapped,
            "status": ("NOT APPLICABLE — no overlapping card planes observed"
                       if overlapped == 0 else
                       f"{overlapped} samples had another card plane over them; the occlusion "
                       "case was exercised and is judged by the depth gate's own row"),
            "whatThisDoesNotClaim":
                ("Real occlusion ordering is still unproven. The sampled hits are single-card "
                 "interiors, and a single-card interior sample cannot exercise "
                 "rear-text-over-front-card. This is stated rather than converted into a PASS."
                 if overlapped == 0 else "n/a — the occlusion case was exercised"),
        }
        # The sweep has to prove it moved the camera, or the count above is a
        # count taken four times at the same place.
        spreads = [m["cameraSpread"] for m in moved if m["cameraSpread"]]
        A("the pointer sweep moved the camera at every viewport",
          len(spreads) == len(moved) and all(min(s) > 1 for s in spreads),
          moved)

    report["passed"] = sum(1 for a in report["assertions"] if a["pass"])
    report["total"] = len(report["assertions"])
    report["verdict"] = "PASS" if report["passed"] == report["total"] else "FAIL"
    out = Path(args["out"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"typography regression {report['verdict']}  {report['passed']}/{report['total']}")
    for a in report["assertions"]:
        if not a["pass"]:
            print(f"  FAIL {a['assertion']}  {json.dumps(a['detail'])[:200]}")
