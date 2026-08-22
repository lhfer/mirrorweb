#!/usr/bin/env python3
"""O5F §十一/§十四 -- the ONE portrait source correction, composed.

Reads the §十四 verification artifacts produced AFTER the correction commit
and writes the public record the closure tree consumes. The keys the tree
reads are exact: gates.controlIdentityAfterFix, gates.stressRerun,
postFixP0.darkSideLumaInsideWindow, postFixP0.whiteReflectionRatioInsideWindow.

Identity semantics after the correction -- pre-registered here:

  control lane        exact zero everywhere, both against the 445037e
                      baseline build and against the sealed O5R measure
                      captures. The correction must not reach it.
  o5-clamped lane     exact zero against the sealed O5R measure captures.
                      The sealed lane keeps the quality map by construction.
  candidate lane      exact zero at FINE-pointer (desktop) contexts, and
                      DIFFERENT at coarse-pointer (mobile-emulated)
                      contexts -- the correction exists to change exactly
                      those pixels. A zero diff at 390x844 would mean the
                      correction did not apply and is scored as a FAILURE.

Output: qa-v5/optics-o5f/portrait-source-code.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
QA = REPO / "qa-v5/optics-o5f"
PF = REPO / "artifacts/optics-o5f/stress-postfix"
MOBILE_VPS = {"390x844", "844x390"}


def jload(p):
    p = Path(p)
    return json.loads(p.read_text()) if p.exists() else None


def diff_png(a, b):
    if not Path(a).exists() or not Path(b).exists():
        return None
    x = np.asarray(Image.open(a).convert("RGB"), dtype=np.int16)
    y = np.asarray(Image.open(b).convert("RGB"), dtype=np.int16)
    if x.shape != y.shape:
        return {"differingPixels": None, "maxDelta": None,
                "shapeMismatch": True}
    d = np.abs(x - y).max(axis=2)
    return {"differingPixels": int((d > 0).sum()), "maxDelta": int(d.max())}


def lane_rows(man_dir, base_dir, lanes):
    """Pixel-diff every png record of `lanes` between two measure trees."""
    man = jload(Path(man_dir) / "measure-manifest.json")
    base = jload(Path(base_dir) / "measure-manifest.json")
    def key(r):
        return (r.get("kind"), r.get("lane"), r.get("asset"), r.get("vp"),
                r.get("state"), r.get("view"))
    bmap = {key(r): r for r in base["records"]
            if r.get("lane") in lanes and str(r.get("file", "")).endswith(".png")}
    rows = []
    for r in man["records"]:
        if r.get("lane") not in lanes:
            continue
        if not str(r.get("file", "")).endswith(".png"):
            continue
        b = bmap.get(key(r))
        if b is None:
            continue
        d = diff_png(Path(man_dir) / r["file"], Path(base_dir) / b["file"])
        rows.append({"lane": r["lane"], "vp": r["vp"], "asset": r.get("asset"),
                     "state": r.get("state"), "view": r.get("view"), **(d or {})})
    return rows


def main() -> int:
    tier = jload(QA / "target-mobile-tier.json")
    stress = jload(PF / "material-cache-stress-rerun.json")
    ident = jload(PF / "identity-postfix-full.json")
    attr = jload(PF / "clip-index-attribution-postfix.json")

    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()

    # ---- identity vs the 445037e baseline build --------------------------
    ctrl_ok = None
    cand_desktop_zero = None
    cand_mobile_changed = None
    ident_detail = None
    if ident:
        rows = ident.get("rows") or {}
        ctrl_rows = rows.get("current") or []
        cand_rows = rows.get("target-source-unclamped") or []
        ctrl_ok = bool(ctrl_rows) and all(
            r.get("differingPixels") == 0 for r in ctrl_rows)
        desk = [r for r in cand_rows if r.get("vp") not in MOBILE_VPS]
        mob = [r for r in cand_rows if r.get("vp") in MOBILE_VPS]
        cand_desktop_zero = bool(desk) and all(
            r.get("differingPixels") == 0 for r in desk)
        cand_mobile_changed = bool(mob) and all(
            (r.get("differingPixels") or 0) > 0 for r in mob)
        ident_detail = {
            "controlRows": len(ctrl_rows),
            "candidateDesktopRows": len(desk),
            "candidateMobileRows": len(mob),
            "candidateMobileDiffRange": (
                [min((r.get("differingPixels") or 0) for r in mob),
                 max((r.get("differingPixels") or 0) for r in mob)]
                if mob else None),
        }

    # ---- sealed-lane identity, post-fix ---------------------------------
    sealed_lane = None
    mp = REPO / "artifacts/optics-o5f/measure-postfix"
    if (mp / "measure-manifest.json").exists():
        frozen = lane_rows(mp, REPO / "artifacts/optics-o5r/measure",
                           {"control", "o5-clamped"})
        cand_vs_forensics = lane_rows(mp, REPO / "artifacts/optics-o5f/measure",
                                      {"o5r-unclamped"})
        fz_ok = bool(frozen) and all(r["differingPixels"] == 0 for r in frozen)
        cd = [r for r in cand_vs_forensics if r["vp"] not in MOBILE_VPS]
        cm = [r for r in cand_vs_forensics if r["vp"] in MOBILE_VPS]
        cd_ok = bool(cd) and all(r["differingPixels"] == 0 for r in cd)
        cm_changed = bool(cm) and any(r["differingPixels"] > 0 for r in cm)
        sealed_lane = {
            "frozenLanesExactZeroVsO5R": fz_ok,
            "frozenComparisons": len(frozen),
            "candidateDesktopExactZeroVsForensicsHead": cd_ok,
            "candidateDesktopComparisons": len(cd),
            "candidateMobileChangedByDesign": cm_changed,
            "candidateMobileComparisons": len(cm),
            "candidateMobileDiffs": sorted(
                {r["vp"]: r["differingPixels"] for r in cm}.items()),
        }

    # ---- the closure keys -------------------------------------------------
    control_identity = ("PASS" if (ctrl_ok and cand_desktop_zero
                                   and cand_mobile_changed
                                   and (sealed_lane or {})
                                   .get("frozenLanesExactZeroVsO5R")
                                   and (sealed_lane or {})
                                   .get("candidateDesktopExactZeroVsForensicsHead"))
                        else "FAIL")
    stress_verdict = (stress or {}).get("verdict") or "FAIL"

    p0 = None
    dark_in = white_in = None
    if attr:
        p0v = next((v for v in attr.get("viewports", [])
                    if v.get("vp") == "390x844"), None)
        if p0v and p0v.get("rows"):
            dark_in = all(r["insideWindow"]["darkSideLuma"]
                          for r in p0v["rows"])
            white_in = all(r["insideWindow"]["whiteReflectionRatio"]
                           for r in p0v["rows"])
            p0 = {
                "rows": len(p0v["rows"]),
                "byClip": p0v.get("byClip"),
                "perRow": [{
                    "rect": r["rect"], "rot": r["rot"],
                    "clipIndex": r["clipIndex"],
                    "candidate": r["candidate"], "target": r["target"],
                    "residual": r["residual"],
                    "insideWindow": r["insideWindow"],
                } for r in p0v["rows"]],
            }

    doc = {
        "what": "§十一 -- the ONE authorised portrait source correction, "
                "with its §十四 verification. The correction: the unclamped "
                "candidate lane's spectral sample count follows the "
                "Target's device-tier predicate (bundle byte 1968911), "
                "decided once at load, instead of the quality map.",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": head,
        "cause": {
            "kind": "WRONG RUNTIME SAMPLE-TIER MAPPING",
            "explicitlyListedIn": "§十一 allowed example",
            "proof": "qa-v5/optics-o5f/target-mobile-tier.json -- live "
                     "Target compiles 3 refract calls at 390x844 and "
                     "844x390 (coarse pointer) where our candidate ran 5; "
                     "counting convention validated on the desktop control "
                     "(predicted 5, observed 5); live bundle sha256 equals "
                     "the archived bundle.",
            "targetP0": ((tier or {}).get("conclusion") or {}).get("p0"),
        },
        "scope": {
            "lane": "target-source-unclamped only",
            "sealedClampedLane": "keeps the frozen quality map -- its "
                                 "regression identity may not move",
            "controlLane": "untouched",
            "bothSetsStillBuiltAtInit": True,
        },
        "gates": {
            "controlIdentityAfterFix": control_identity,
            "stressRerun": stress_verdict,
        },
        "identityDetail": ident_detail,
        "identitySemantics": "control exact-zero everywhere; candidate "
                             "exact-zero at fine-pointer contexts and "
                             "DIFFERENT at coarse-pointer contexts -- a "
                             "zero mobile diff would mean the correction "
                             "did not apply.",
        "sealedLaneIdentityPostFix": sealed_lane,
        "stressRerunDetail": None if not stress else {
            "checks": f"{stress['passed']}/{stress['total']}",
            "amendedItems": stress.get("amendedItems"),
            "addendum": "scripts/v5/o5f-stress-postfix.py -- committed in "
                        "the correction commit, before any re-capture",
            "sealedScorerOnSameData": stress.get("sealedScorerOnSameData"),
        },
        "postFixP0": {
            "darkSideLumaInsideWindow": dark_in,
            "whiteReflectionRatioInsideWindow": white_in,
            "detail": p0,
            "windows": "the sealed corrected gate's own: max(Target repeat "
                       "spread, floor 6.0 / 0.15) per metric",
        },
        "noOtherChange": "no Target source constant touched; no portrait "
                         "multiplier; no viewport-specific look; the "
                         "quality map itself is unedited for the lanes "
                         "that keep it.",
    }
    out = QA / "portrait-source-code.json"
    out.write_text(json.dumps(doc, indent=1))
    print(f"controlIdentityAfterFix: {control_identity}")
    print(f"stressRerun: {stress_verdict}")
    print(f"postFixP0 inside windows: dark {dark_in}  white {white_in}")
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
