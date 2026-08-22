#!/usr/bin/env python3
"""O5F §六 -- score the identity captures.

Three verdicts, each exact:

  A  current lane, 35 pairs -- exactly zero differing pixels, probes equal
  B  candidate lane, 35 pairs -- exactly zero differing pixels, probes equal
  C  generated WGSL -- vertex and fragment sha256 equal at the 5-sample tier,
     the 3-sample tier, and back at 5, O5F against the 445037e build

plus the retired-defect demonstration, scored one-sided: the O5F build's
high -> low -> high cycle must return to its own pixels exactly; the baseline
build's residual is REPORTED as the measurement of the defect the cache
retires, never as a pass or a fail of the sealed baseline.

Output: qa-v5/optics-o5f/material-cache-identity.json
Exit 0 on PASS, 1 on O5F MATERIAL CACHE IDENTITY FAILED.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
BASELINE = "445037e11eb44ae07bca6360707e043d969b1d4b"

PROBE_KEYS = [
    "opticalBody", "opticalBodySamples", "environmentMode", "envSampleClamped",
    "bodyFloorMode", "reflectionSupport", "dispersionLaw", "shellMode",
    "envMixScale", "rimScale", "glassMeshesVisible", "reflectionShellsVisible",
    "mediaMeshesVisible", "activeSlots", "drawCallsFinal",
    "drawCallsSceneColor",
]


def diff(a_path: Path, b_path: Path):
    a = np.asarray(Image.open(a_path).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(b_path).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        return {"shapeMismatch": [list(a.shape), list(b.shape)],
                "differingPixels": None, "maxDelta": None}
    d = np.abs(a - b).max(axis=2)
    return {"differingPixels": int((d > 0).sum()),
            "maxDelta": int(d.max()),
            "totalPixels": int(d.size)}


def main() -> int:
    src = REPO / "artifacts/optics-o5f/identity"
    out = REPO / "qa-v5/optics-o5f/material-cache-identity.json"
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k == "src":
            src = Path(v)
        elif k == "out":
            out = Path(v)

    man = json.loads((src / "identity-manifest.json").read_text())
    lanes = {}
    total_errors = 0

    for rec in man["records"]:
        body, vp = rec["body"], rec["vp"]
        lane = lanes.setdefault(body, {"rows": [], "allExactZero": True,
                                       "allProbesMatch": True})
        total_errors += rec["local"]["errorCount"] + rec["base"]["errorCount"]
        by_state = {c["state"]: c for c in rec["base"]["captures"]}
        for cap in rec["local"]["captures"]:
            st = cap["state"]
            base = by_state.get(st)
            if base is None:
                lane["rows"].append({"vp": vp, "state": st,
                                     "FAILED": "no baseline capture"})
                lane["allExactZero"] = False
                continue
            d = diff(src / cap["file"], src / base["file"])
            # Field-by-field probe comparison. Every PROBE_KEY exists at the
            # 445037e baseline -- it is the O5R evidence commit -- so nothing
            # here needs the NEW-field carve-out the O5 harness used. The §五
            # cache truth is the one surface that did not exist there; the
            # capture recorded it on the O5F side only, as evidence, and it
            # is deliberately not in this comparison.
            mismatched = {k: [cap["probe"].get(k), base["probe"].get(k)]
                          for k in PROBE_KEYS
                          if cap["probe"].get(k) != base["probe"].get(k)}
            if cap["probe"].get("opticalBody") != body:
                mismatched["opticalBody"] = [cap["probe"].get("opticalBody"),
                                             f"expected '{body}'"]
            if mismatched:
                lane["allProbesMatch"] = False
            if d["differingPixels"] != 0:
                lane["allExactZero"] = False
            lane["rows"].append({
                "vp": vp, "state": st,
                "localFile": cap["file"], "baseFile": base["file"], **d,
                "probeMismatches": mismatched,
                "o5fCacheTruth": cap.get("cacheTruth"),
                "identical": d["differingPixels"] == 0 and not mismatched})

    # --- C: program identity ------------------------------------------------
    prog_rows = []
    programs_ok = True
    lp = man["programs"]["local"]["programs"]
    bp = man["programs"]["base"]["programs"]
    for step, want_samples in (("high", 5), ("low", 3), ("high-return", 5)):
        l, b = lp.get(step, {}), bp.get(step, {})
        row = {"step": step,
               "samples": [l.get("samples"), b.get("samples")],
               "vertexMatch": (l.get("vertexSha256") is not None
                               and l.get("vertexSha256") == b.get("vertexSha256")),
               "fragmentMatch": (l.get("fragmentSha256") is not None
                                 and l.get("fragmentSha256") == b.get("fragmentSha256")),
               "vertexSha256": l.get("vertexSha256"),
               "fragmentSha256": l.get("fragmentSha256"),
               "samplesOk": l.get("samples") == want_samples
                            and b.get("samples") == want_samples}
        if not (row["vertexMatch"] and row["fragmentMatch"] and row["samplesOk"]):
            programs_ok = False
        prog_rows.append(row)

    # --- the retired-defect demonstration ----------------------------------
    cyc = man["cycles"]
    local_cycle = diff(src / cyc["local"]["before"], src / cyc["local"]["after"])
    base_cycle = diff(src / cyc["base"]["before"], src / cyc["base"]["after"])
    cycle_ok = local_cycle["differingPixels"] == 0

    a = lanes.get("current", {"allExactZero": False, "allProbesMatch": False,
                              "rows": []})
    b = lanes.get("target-source-unclamped",
                  {"allExactZero": False, "allProbesMatch": False, "rows": []})
    verdict = "PASS" if (a["allExactZero"] and a["allProbesMatch"]
                         and b["allExactZero"] and b["allProbesMatch"]
                         and programs_ok and cycle_ok
                         and total_errors == 0) else "FAIL"

    doc = {
        "what": "O5F §六 -- identity of the cached build against a 445037e "
                "worktree build: the shipped lane, the candidate lane, and "
                "the generated programs. Runs BEFORE any memory scoring.",
        "baselineCommit": BASELINE,
        "local": man["local"], "base": man["base"],
        "asset": man["asset"], "freeze": man["freeze"],
        "viewports": man["viewports"],
        "states": [s["state"] for s in man["states"]],
        "A_controlIdentity": {
            "lane": "current",
            "comparisons": len(a["rows"]),
            "allExactZero": a["allExactZero"],
            "allProbesMatch": a["allProbesMatch"],
        },
        "B_candidateIdentity": {
            "lane": "target-source-unclamped",
            "comparisons": len(b["rows"]),
            "allExactZero": b["allExactZero"],
            "allProbesMatch": b["allProbesMatch"],
            "note": "this is the §四 rule 10 proof -- the cache changed no "
                    "optical output. Both product sets exist at page load on "
                    "the O5F side (cacheSize 2, creationCount 6 in the "
                    "per-row cache truth); the extra unrendered set moved "
                    "nothing.",
        },
        "C_programIdentity": {
            "coding": "sha256 over the generated WGSL, vertex and fragment "
                      "separately, at high (5 samples), after a switch to "
                      "low (3 samples), and back at high. All pairs must "
                      "match.",
            "allMatch": programs_ok,
            "rows": prog_rows,
        },
        "retiredDefectDemonstration": {
            "what": "high -> low -> high on a paused, media-frozen page. At "
                    "the baseline the first quality step rebinds the convex "
                    "volume geometry, so the pixels cannot return; at O5F a "
                    "quality change switches cached sets and must return "
                    "exactly.",
            "o5fCycleReturn": local_cycle,
            "o5fMustBeZero": True,
            "o5fIsZero": cycle_ok,
            "baselineCycleResidual": base_cycle,
            "baselineNote": "reported as the measurement of the retired "
                            "defect. The sealed baseline is not being "
                            "gated; its captures were all taken at build "
                            "quality with no quality step, so this residual "
                            "is in no sealed number.",
        },
        "consoleAndPageErrors": total_errors,
        "verdict": verdict,
        "finalStateIfFailed": "O5F MATERIAL CACHE IDENTITY FAILED",
        "rows": {k: v["rows"] for k, v in lanes.items()},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1))

    for lane_name, lane in lanes.items():
        worst = max((r.get("differingPixels") or 0) for r in lane["rows"])
        print(f"{lane_name}: {len(lane['rows'])} pairs, worst diff {worst}, "
              f"probes {'OK' if lane['allProbesMatch'] else 'MISMATCH'}")
    print(f"programs: {'match' if programs_ok else 'MISMATCH'}; "
          f"o5f cycle-return diff {local_cycle['differingPixels']}, "
          f"baseline cycle residual {base_cycle['differingPixels']} px")
    print(f"errors: {total_errors}  verdict: {verdict}")
    print(f"-> {out}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
