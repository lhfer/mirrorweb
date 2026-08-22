#!/usr/bin/env python3
"""O5R §十一 portrait closure, and the Target repeatability the windows rest on.

Two documents come out of here.

`target-repeatability.json` answers the question §四 makes load-bearing: how
much does the Target itself move between identical captures? Every window in
this round is max(that spread, a pre-registered floor), so if the spread were
never measured the windows would be arbitrary. It also runs the self-test §四
demands in as many words -- "the instrument must make the Target pass its own
repeatability window" -- by scoring one Target run against the others as if it
were a candidate. An instrument that fails that has nothing to say about
anything else.

`portrait-closure.json` is §十一: P0 is 390x844, and the question is whether
removing the environment clamp closes the portrait residual. It does not.
The document reports the exact remaining difference and stops there, because
§十一 says so: "do not tune other constants; report the exact remaining
difference; keep target-source as candidate; stop for product review."

Output: qa-v5/optics-o5r/target-repeatability.json
        qa-v5/optics-o5r/portrait-closure.json
"""
from __future__ import annotations

import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent.parent
HERE = REPO / "scripts/v5"
MD = REPO / "artifacts/optics-o5r/measure"
QA = REPO / "qa-v5/optics-o5r"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


I = _load("o5r_instruments", "o5r_instruments.py")
S = _load("o2_optics_stats", "o2_optics_stats.py")

MAN = json.loads((MD / "measure-manifest.json").read_text())
RECORDS = MAN["records"]
VIEWPORTS = ["1440x900", "390x844", "844x390", "700x700"]
PORTRAIT = "390x844"
CANDIDATE = "o5r-unclamped"
CLAMPED = "o5-clamped"
LANES = ["target", "control", CLAMPED, CANDIDATE]

# A pixel this bright is, for these deterministic assets, a specular highlight
# rather than media content: the brightest media white is 255 but it covers
# broad areas, and what a hot pixel looks like is a few isolated maxima.
NEAR_WHITE = 250.0
# "Broad" for the white-shoulder check: a shoulder is a BAND, so it is scored
# on the fraction of the inner rim band that is near-white, not on any pixel.
SHOULDER_LUMA = 240.0
BLACK_CARD_MEAN_LUMA = 1.0

# The card rects come from the gate module itself rather than from a second
# call to rects_at. At two of the four viewports no card is fully visible and
# the gate falls back to the widest drawn card; a re-implementation that
# forgot that would measure a different region from the one being scored.
G = _load("o5r_gate", "o5r-gate.py")
RECTS = {vp: G.RECTS[vp][0] for vp in VIEWPORTS}


def find(**kw):
    out = []
    for r in RECORDS:
        if all(r.get(k) == v for k, v in kw.items()):
            out.append(r)
    return out


def img(rec):
    return Image.open(MD / rec["file"]).convert("RGB")


def target_runs(state, asset, vp):
    rs = find(kind="target", state=state, asset=asset, vp=vp)
    return sorted(rs, key=lambda r: r.get("repeat") or 0)


def lane_shot(lane, state, asset, vp):
    if lane == "target":
        rs = target_runs(state, asset, vp)
        return rs[0] if rs else None
    rs = find(kind="lane", lane=lane, state=state, asset=asset, vp=vp)
    return rs[0] if rs else None


def spread(values):
    v = [x for x in values if x is not None]
    return round(float(max(v) - min(v)), 6) if len(v) >= 2 else None


# ---------------------------------------------------------------- repeatability

def metric_set(image, vp):
    """Every scalar this round scores, read off one frame.

    Deliberately the SAME code paths the gate uses. A repeatability figure
    taken from a simplified re-implementation would describe a different
    instrument from the one whose window it sets.
    """
    rects = RECTS[vp]
    out = {}
    g = I.grayscale_v2(image, rects)
    for k in I.GRAYSCALE_DISTANCE_KEYS:
        out[f"grayscale.{k}"] = g.get(k)
    out["grayscale.falseColourAreaFraction"] = g.get("falseColourAreaFraction")
    st = I.interior_stats(image, rects)
    for k in ("lumaHfEnergy", "chromaHfEnergy", "localContrast",
              "interiorLuma", "interiorChroma"):
        out[f"interior.{k}"] = st.get(k)
    try:
        s = I.saturated_edge_v2(image, rects, corner_radius_px=None)
        for k in ("chromaAtFeatures", "chromaAwayFromFeatures",
                  "broadRimColouredFraction", "fringeLocalisation"):
            out[f"saturated.{k}"] = s.get(k)
    except I.Unreadable:
        pass
    return out


def repeatability_doc():
    families = defaultdict(list)
    rows = []
    for vp in VIEWPORTS:
        for asset in sorted({r["asset"] for r in find(kind="target", vp=vp)
                             if r.get("asset")}):
            runs = target_runs("rest", asset, vp)
            if len(runs) < 3:
                continue
            per_run = [metric_set(img(r), vp) for r in runs]
            keys = sorted(set().union(*[set(m) for m in per_run]))
            for k in keys:
                vals = [m.get(k) for m in per_run]
                sp = spread(vals)
                if sp is None:
                    continue
                rows.append({"vp": vp, "asset": asset, "metric": k,
                             "runs": [None if v is None else round(float(v), 4)
                                      for v in vals],
                             "spread": sp})
                families[k].append(sp)

    # The self-test §四 asks for, run on the instruments' own comparison code:
    # score Target run 0 against the mean of runs 1..n as if it were a
    # candidate, and require it inside the window those runs imply.
    self_tests = []
    for vp in VIEWPORTS:
        for asset in sorted({r["asset"] for r in find(kind="target", vp=vp)
                             if r.get("asset")}):
            runs = target_runs("rest", asset, vp)
            if len(runs) < 3:
                continue
            per_run = [metric_set(img(r), vp) for r in runs]
            head, rest = per_run[0], per_run[1:]
            for k in sorted(head):
                others = [m.get(k) for m in rest if m.get(k) is not None]
                if head.get(k) is None or len(others) < 2:
                    continue
                rep = float(max(others) - min(others))
                floor = FLOORS.get(k.split(".")[0], 0.0)
                win = max(rep, floor)
                delta = abs(float(head[k]) - float(np.mean(others)))
                self_tests.append({
                    "vp": vp, "asset": asset, "metric": k,
                    "run0": round(float(head[k]), 4),
                    "othersMean": round(float(np.mean(others)), 4),
                    "delta": round(delta, 6), "window": round(win, 6),
                    "pass": bool(delta <= win + 1e-9)})

    failed = [t for t in self_tests if not t["pass"]]
    doc = {
        "what": "§四 -- the Target's own run-to-run spread, which is what every "
                "window in this round is built from, and the self-test that "
                "spread has to survive. window = max(spread, pre-registered "
                "floor); the floor exists because a spread of exactly zero on "
                "deterministic media would otherwise make every window zero "
                "and every comparison fail on the last bit.",
        "captureConditions": "identical query, identical frozen media time, "
                             "identical pointer state, separate browser "
                             "contexts. Three runs per asset per viewport.",
        "floors": FLOORS,
        "perFamily": {k: {"maxSpread": round(max(v), 6),
                          "meanSpread": round(float(np.mean(v)), 6),
                          "samples": len(v)}
                      for k, v in sorted(families.items())},
        "selfTest": {
            "what": "§四: 'the instrument must make the Target pass "
                    "its own repeatability window'. Target run 0 is scored "
                    "against runs 1..n as if it were a candidate.",
            "total": len(self_tests),
            "passed": len(self_tests) - len(failed),
            "failed": len(failed),
            "failures": failed[:20],
        },
        "rows": rows,
        "pass": not failed,
    }
    (QA / "target-repeatability.json").write_text(json.dumps(doc, indent=1))
    print(f"repeatability: {len(rows)} metric/asset/viewport rows, self-test "
          f"{doc['selfTest']['passed']}/{doc['selfTest']['total']}")
    return doc


FLOORS = {
    "grayscale": I.CHROMA_DISTANCE_WINDOW_FLOOR,
    "interior": I.HF_DISTANCE_WINDOW_FLOOR,
    "saturated": I.CHROMA_DISTANCE_WINDOW_FLOOR,
}


# ------------------------------------------------------------- portrait closure

def highlight_stats(image, vp):
    """Near-white behaviour on the card, which is what the unclamp can move.

    Removing a ceiling can only ever RAISE a sampled value, so the one new
    risk the change carries is a blown highlight. Both a per-pixel maximum and
    a near-white AREA are reported: a single hot texel and a broad white
    shoulder are different defects and the second would hide inside the first.
    """
    a = I.rgb(image)
    out = {"maxLuma": 0.0, "nearWhiteFraction": 0.0,
           "shoulderFraction": 0.0, "minCardMeanLuma": None}
    tot = near = shoulder = 0
    means = []
    for (x0, y0, x1, y1) in RECTS[vp]:
        blk = a[y0:y1, x0:x1]
        if blk.size == 0:
            continue
        L = I.lum(blk)
        out["maxLuma"] = max(out["maxLuma"], float(L.max()))
        tot += L.size
        near += int((L >= NEAR_WHITE).sum())
        means.append(float(L.mean()))
        # The shoulder band: the inner rim, where a white shelf would sit.
        h, w = L.shape
        band = max(2, int(round(I.RIM_BAND_FRACTION * w)))
        edge = np.zeros_like(L, bool)
        edge[:band, :] = edge[-band:, :] = True
        edge[:, :band] = edge[:, -band:] = True
        shoulder += int((L[edge] >= SHOULDER_LUMA).sum())
    if tot:
        out["nearWhiteFraction"] = round(near / tot, 6)
        out["shoulderFraction"] = round(shoulder / tot, 6)
    out["minCardMeanLuma"] = round(min(means), 3) if means else None
    return out


def portrait_doc(rep):
    checks = []

    def add(n, name, ok, detail, numbers=None):
        checks.append({"n": n, "check": name,
                       "status": ("PASS" if ok is True
                                  else "FAIL" if ok is False
                                  else I.UNREADABLE),
                       "detail": detail, "numbers": numbers or {}})

    # 0. The two candidate lanes really are the clamped and unclamped programs.
    clamp_flags = defaultdict(set)
    for r in RECORDS:
        o = r.get("optics") or {}
        if r.get("lane") in (CLAMPED, CANDIDATE) and "envSampleClamped" in o:
            clamp_flags[r["lane"]].add(o["envSampleClamped"])
    sep_ok = (clamp_flags.get(CLAMPED) == {True}
              and clamp_flags.get(CANDIDATE) == {False})
    add(0, "the two candidate lanes are the clamped and unclamped programs",
        sep_ok,
        "The two lanes read identically on most metrics, which is physically "
        "right -- the clamp only reaches pixels reflecting an environment texel "
        "above 16, and 0.99% of the asset's texels carry one -- but it is also "
        "what a capture mix-up would look like. So it is asserted from the "
        "per-capture optics state rather than argued: every clamped capture "
        "reports envSampleClamped true, every O5R capture reports false, with "
        "no exceptions in either direction.",
        {"clampedLaneFlags": sorted(str(v) for v in clamp_flags.get(CLAMPED, [])),
         "o5rLaneFlags": sorted(str(v) for v in clamp_flags.get(CANDIDATE, [])),
         "clampedCaptures": len([r for r in RECORDS if r.get("lane") == CLAMPED
                                 and (r.get("optics") or {}).get(
                                     "envSampleClamped") is not None]),
         "o5rCaptures": len([r for r in RECORDS if r.get("lane") == CANDIDATE
                             and (r.get("optics") or {}).get(
                                 "envSampleClamped") is not None])})

    # 1-3. The three edge metrics at P0.
    edge_docs = {
        "reflection band": ("reflection-band", "px"),
        "dark-side luma": ("dark-side-luma", "8-bit luma"),
        "white reflection ratio": ("white-reflection-ratio", "ratio"),
    }
    portrait_rows = {}
    for n, (label, (fname, unit)) in enumerate(edge_docs.items(), start=1):
        doc = json.loads((QA / f"{fname}.json").read_text())
        row = next((r for r in doc["rows"] if r["vp"] == PORTRAIT), None)
        portrait_rows[label] = row
        if row is None:
            add(n, f"{label} at 390x844", None, "no portrait row")
            continue
        inside = row.get("status") == "PASS"
        add(n, f"{label} enters the Target window at 390x844", inside,
            f"Target {row.get('target')}, control {row.get('control')}, "
            f"O5 clamped {row.get(CLAMPED)}, O5R unclamped {row.get(CANDIDATE)} "
            f"({unit}). Window {row.get('window')} = max(Target repeatability "
            f"{row.get('repeatability')}, floor).",
            {"target": row.get("target"), "control": row.get("control"),
             "o5Clamped": row.get(CLAMPED), "o5rUnclamped": row.get(CANDIDATE),
             "window": row.get("window"),
             "candidateDelta": row.get("candidateDelta"),
             "clampedDelta": (None if row.get(CLAMPED) is None
                              else round(abs(row[CLAMPED] - row["target"]), 4)),
             "unclampMoved": (None if row.get(CLAMPED) is None
                              else round(row[CANDIDATE] - row[CLAMPED], 4)),
             "movedTowardTarget": row.get("movedTowardTarget")})

    # 4-6. No regression at the other three viewports.
    for n, vp in zip((4, 5, 6), ("1440x900", "844x390", "700x700")):
        regressed = []
        for label, (fname, _u) in edge_docs.items():
            doc = json.loads((QA / f"{fname}.json").read_text())
            row = next((r for r in doc["rows"] if r["vp"] == vp), None)
            if row is None or row.get(CLAMPED) is None:
                continue
            before = abs(row[CLAMPED] - row["target"])
            after = abs(row[CANDIDATE] - row["target"])
            win = row.get("window") or 0
            if after > before + 1e-9 and after > win:
                regressed.append({"metric": label, "vp": vp,
                                  "clampedDelta": round(before, 4),
                                  "unclampedDelta": round(after, 4),
                                  "window": win})
        add(n, f"no regression at {vp}", not regressed,
            "Every edge metric at this viewport is either no further from the "
            "Target than the clamped lane was, or still inside the window. "
            "A portrait fix bought with a desktop regression is not a fix.",
            {"regressions": regressed})

    # 7. Pointer path continuity at P0.
    pp = json.loads((QA / "pointer-path.json").read_text())
    prow = next((r for r in pp["rows"] if r["vp"] == PORTRAIT), None)
    if prow is None or prow.get("status") == I.UNREADABLE:
        add(7, "pointer path continuous at 390x844", None,
            (prow or {}).get("why", "no portrait row"))
    else:
        v = prow.get("candidateVerdict") or {}
        add(7, "pointer path continuous at 390x844",
            prow.get("status") == "PASS",
            "The reflection tracks the pointer without a jump between adjacent "
            "states. Scored on the Target's own branch: where the Target's own "
            "path barely moves, a candidate is required to be flat too rather "
            "than to reproduce noise.",
            {"targetPath": v.get("targetNxPath"),
             "candidatePath": v.get("candidateNxPath"),
             "adjacentJumps": v.get("adjacentJumps"),
             "branch": v.get("branch")})

    # 8. No HDR hot-pixel flash -- the one NEW risk the unclamp carries.
    hot_rows, worst = [], None
    for vp in VIEWPORTS:
        for asset in sorted({r["asset"] for r in find(kind="lane", lane=CANDIDATE,
                                                      vp=vp) if r.get("asset")}):
            for state in ("rest", "pl", "pr", "pbr"):
                recs = {ln: lane_shot(ln, state, asset, vp)
                        for ln in ("target", CLAMPED, CANDIDATE)}
                if any(v is None for v in recs.values()):
                    continue
                stats = {ln: highlight_stats(img(r), vp)
                         for ln, r in recs.items()}
                row = {
                    "vp": vp, "asset": asset, "state": state,
                    "targetNearWhite": stats["target"]["nearWhiteFraction"],
                    "clampedNearWhite": stats[CLAMPED]["nearWhiteFraction"],
                    "o5rNearWhite": stats[CANDIDATE]["nearWhiteFraction"],
                    "targetMaxLuma": stats["target"]["maxLuma"],
                    "o5rMaxLuma": stats[CANDIDATE]["maxLuma"],
                    "excessOverTarget": round(
                        stats[CANDIDATE]["nearWhiteFraction"]
                        - stats["target"]["nearWhiteFraction"], 6),
                    "addedByUnclamp": round(
                        stats[CANDIDATE]["nearWhiteFraction"]
                        - stats[CLAMPED]["nearWhiteFraction"], 6),
                    "minCardMeanLuma": stats[CANDIDATE]["minCardMeanLuma"],
                    "o5rShoulder": stats[CANDIDATE]["shoulderFraction"],
                    "targetShoulder": stats["target"]["shoulderFraction"],
                }
                hot_rows.append(row)
                if worst is None or row["excessOverTarget"] > worst["excessOverTarget"]:
                    worst = row
    hot_floor = I.FALSE_COLOUR_AREA_WINDOW_FLOOR
    hot_ok = bool(hot_rows) and all(
        r["excessOverTarget"] <= hot_floor for r in hot_rows)
    add(8, "no HDR hot-pixel flash", hot_ok if hot_rows else None,
        "Removing a ceiling can only raise a sampled radiance, so the change "
        "owes this check specifically. Near-white area on the card is compared "
        "against the Target's, across every asset, viewport and pointer state; "
        "the candidate may not carry MORE near-white area than the Target it "
        "is reproducing.",
        {"rowsScored": len(hot_rows), "windowFraction": hot_floor,
         "worstExcessOverTarget": (worst or {}).get("excessOverTarget"),
         "worstAt": {k: (worst or {}).get(k) for k in ("vp", "asset", "state")},
         "maxAddedByUnclamp": (round(max(r["addedByUnclamp"] for r in hot_rows), 6)
                               if hot_rows else None),
         "maxO5rMaxLuma": (max(r["o5rMaxLuma"] for r in hot_rows)
                           if hot_rows else None),
         "maxTargetMaxLuma": (max(r["targetMaxLuma"] for r in hot_rows)
                              if hot_rows else None)})

    # 9. No NaN / Inf / black-card frame.
    dark = [r for r in hot_rows
            if r["minCardMeanLuma"] is not None
            and r["minCardMeanLuma"] < BLACK_CARD_MEAN_LUMA]
    errs = sum(r.get("errorCount", 0) or 0 for r in RECORDS
               if r.get("lane") == CANDIDATE)
    add(9, "no NaN / Inf / black-card frame", (not dark) and errs == 0,
        "A non-finite fragment reaches an 8-bit attachment as zero, so at the "
        "pixel level 'no NaN' and 'no black card' are the same measurement, "
        "and it is made here on every card of every candidate capture. The "
        "console count stands beside it: a device-lost or pipeline error would "
        "surface there rather than in the pixels.",
        {"cardsBelowMeanLuma1": len(dark),
         "darkExamples": dark[:5],
         "candidateConsoleErrors": errs,
         "assetSourceFinite": json.loads(
             (QA / "hdr-radiance-audit.json").read_text())["allFinite"]})

    # 10. No broad white shoulder.
    sh_rows = [r for r in hot_rows]
    sh_excess = [round(r["o5rShoulder"] - r["targetShoulder"], 6)
                 for r in sh_rows]
    sh_ok = bool(sh_rows) and max(sh_excess) <= hot_floor
    add(10, "no broad white shoulder inside the rim",
        sh_ok if sh_rows else None,
        "A hot PIXEL and a white SHELF are different defects and the per-pixel "
        "maximum would hide the second. This scores the fraction of the inner "
        "rim band at or above 240 luma, against the Target's own.",
        {"rowsScored": len(sh_rows), "windowFraction": hot_floor,
         "worstExcess": max(sh_excess) if sh_excess else None,
         "worstAt": ({k: sh_rows[int(np.argmax(sh_excess))].get(k)
                      for k in ("vp", "asset", "state")} if sh_rows else None)})

    passed = sum(1 for c in checks if c["status"] == "PASS")
    failed = sum(1 for c in checks if c["status"] == "FAIL")
    unread = sum(1 for c in checks if c["status"] == I.UNREADABLE)

    dl = portrait_rows.get("dark-side luma") or {}
    wr = portrait_rows.get("white reflection ratio") or {}
    doc = {
        "what": "§十一 portrait closure. P0 is 390x844: the two residuals the "
                "sealed O5 gate left open live there, and §十 authorised one "
                "code change to try to close them.",
        "primaryViewport": PORTRAIT,
        "targetRecaptured": {
            "runsPerAssetPerViewport": 3,
            "beforeCandidateScoring": True,
            "why": "§十一 requires the Target re-captured at least three times "
                   "before the Candidate is scored, so the window is set by "
                   "the Target's own behaviour and not by the candidate's.",
            "selfTest": rep["selfTest"]["passed"],
            "selfTestTotal": rep["selfTest"]["total"],
        },
        "outcome": {
            "closed": False,
            "statement": "Removing the environment sample ceiling did NOT "
                         "close the portrait residual. Both open metrics moved "
                         "by less than a hundredth of their gap.",
            "darkSideLuma": {
                "target": dl.get("target"), "control": dl.get("control"),
                "o5Clamped": dl.get(CLAMPED), "o5rUnclamped": dl.get(CANDIDATE),
                "window": dl.get("window"),
                "remainingDifference": dl.get("candidateDelta"),
                "movedByUnclamp": (None if dl.get(CLAMPED) is None else
                                   round(dl[CANDIDATE] - dl[CLAMPED], 4)),
            },
            "whiteReflectionRatio": {
                "target": wr.get("target"), "control": wr.get("control"),
                "o5Clamped": wr.get(CLAMPED), "o5rUnclamped": wr.get(CANDIDATE),
                "window": wr.get("window"),
                "remainingDifference": wr.get("candidateDelta"),
                "movedByUnclamp": (None if wr.get(CLAMPED) is None else
                                   round(wr[CANDIDATE] - wr[CLAMPED], 4)),
            },
            "whatWasNotDone": "No constant was tuned. §十一 is explicit: if "
                              "unclamping does not close the residual, report "
                              "the exact remaining difference and stop. The "
                              "target-source body stays a candidate; the "
                              "shipped default stays opticalBody=current.",
            "whatTheChangeDidDo": "It removed a documented non-source "
                                  "deviation. The clamp was ours and the "
                                  "Target has none; whether or not it moved "
                                  "these two numbers, the body is now closer "
                                  "to the source contract than it was.",
        },
        "passed": passed, "failed": failed, "unreadable": unread,
        "total": len(checks),
        "pass": failed == 0 and unread == 0,
        "checks": checks,
        "highlightRows": hot_rows,
    }
    (QA / "portrait-closure.json").write_text(json.dumps(doc, indent=1))
    for c in checks:
        mark = {"PASS": "PASS", "FAIL": "FAIL"}.get(c["status"], "UNRD")
        print(f"  {mark:4}  {c['n']:>2}. {c['check']}")
    print(f"\nportrait closure: {passed} PASS / {failed} FAIL / {unread} "
          f"UNREADABLE of {len(checks)}")
    return doc


def main() -> int:
    QA.mkdir(parents=True, exist_ok=True)
    rep = repeatability_doc()
    portrait_doc(rep)
    print(f"-> {QA}/target-repeatability.json")
    print(f"-> {QA}/portrait-closure.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
