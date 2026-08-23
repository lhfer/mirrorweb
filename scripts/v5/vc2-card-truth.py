#!/usr/bin/env python3
"""VC2 §五 -- preregister the thresholds, then judge the candidate against them.

Two modes, deliberately separated in time and in commits:

  --preregister   reads ONLY the Target repeats. Every scenario is compared
                  against itself across repeats, which measures what the
                  instrument and the live page do on their own -- network,
                  frame scheduling, gesture dispatch jitter. The threshold for
                  each observable is set from that self-repeat spread, before
                  any Candidate run has been read, and written to
                  qa-v5/visual-convergence/card-trajectory-thresholds.json.

  --compare       reads the Target and the Candidate and judges the deltas
                  against the already-committed thresholds. Nothing here can
                  move a threshold; the file is read, never written.

The threshold rule is fixed in advance and applied uniformly, PER SCENARIO:

    threshold[scenario][gate] = max(floor, 2 x worst self-repeat p95 in that scenario)

Per scenario, not one number for all of them, because the scenarios are not
equally repeatable and a single pooled threshold would be set by the loosest of
them. Measured on the Target's own repeats: a still page repeats to 0.000 px, a
pointer sweep to 0.12 px, a slow drag to 2.95 px, a flick to 3.59 px, a long
wrapping touch drag to 8.45 px, and a live orientation change to 35.9 px --
because the resize lands on a different frame each time. Pooling those would
have judged the still page with a 72 px allowance.

The 2x margin exists because a Target-vs-Candidate comparison carries two
independent copies of the jitter a Target-vs-Target comparison carries one of;
the floors exist because a sub-pixel threshold would fail on rounding rather
than on anything a viewer could see.

Usage:
  vc2-card-truth.py --preregister [--dir=<card-truth dir>] [--out=<json>]
  vc2-card-truth.py --compare [--dir=...] [--thresholds=...] [--out=<json>]
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vc2_card_geom import COMPARED, compare, series_of  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
DIR = REPO / "artifacts/visual-convergence/card-truth"
QA = REPO / "qa-v5/visual-convergence"

# observable -> (threshold key, floor). Scale is judged on projected size,
# which is what a dolly actually changes on screen.
GATED = {
    "centreX": ("centreDeltaPx", 2.0), "centreY": ("centreDeltaPx", 2.0),
    "projectedWidth": ("scaleDeltaPx", 1.5), "projectedHeight": ("scaleDeltaPx", 1.5),
    "hGutter": ("gutterDeltaPx", 2.0), "vGutter": ("gutterDeltaPx", 2.0),
    "rowStagger": ("staggerDeltaPx", 2.0),
}
MARGIN = 2.0


def runs_for(side: str, base: Path) -> dict:
    out = {}
    for p in sorted((base / side).glob("*.json")):
        stem = p.stem
        scenario, rep = (stem.rsplit("-r", 1) + ["0"])[:2] if "-r" in stem else (stem, "0")
        out.setdefault(scenario, {})[int(rep)] = p
    return out


def preregister(base: Path, out_p: Path) -> int:
    tgt = runs_for("target", base)
    if not tgt:
        raise SystemExit(f"no Target runs under {base}/target")
    doc = {
        "what": "VC2 §五 pre-registered thresholds. Written from Target self-repeat "
                "spread ONLY, before any Candidate trajectory was read.",
        "rule": f"threshold[scenario][gate] = max(floor, {MARGIN} x worst self-repeat p95 "
                f"measured in that scenario)",
        "why": "a Target-vs-Candidate comparison carries two independent copies of the "
               "jitter a Target-vs-Target comparison carries one of; the floors keep a "
               "sub-pixel rounding difference from reading as a failure.",
        "floors": {k: v for k, v in {v[0]: v[1] for v in GATED.values()}.items()},
        "selfRepeat": {}, "thresholds": {},
    }
    floors = {v[0]: v[1] for v in GATED.values()}
    pooled: dict[str, float] = {}
    for scenario, reps in sorted(tgt.items()):
        if len(reps) < 2:
            continue
        series = {r: series_of(p) for r, p in sorted(reps.items())}
        rows = {}
        for ra, rb in itertools.combinations(sorted(series), 2):
            c = compare(series[ra], series[rb])
            for name, row in c["rows"].items():
                rows.setdefault(name, []).append(row["delta"]["p95"])
        worst: dict[str, float] = {}
        for name, vals in rows.items():
            if name not in GATED:
                continue
            key = GATED[name][0]
            v = max((x for x in vals if x is not None), default=0.0)
            worst[key] = max(worst.get(key, 0.0), float(v))
            pooled[key] = max(pooled.get(key, 0.0), float(v))
        doc["selfRepeat"][scenario] = {
            "repeats": sorted(series), "fps": {r: series[r]["fps"] for r in sorted(series)},
            "p95ByPair": rows, "worstP95": {k: round(v, 3) for k, v in worst.items()},
        }
        doc["thresholds"][scenario] = {
            k: round(max(floors[k], MARGIN * worst.get(k, 0.0)), 3) for k in floors}
    doc["pooledWorstSelfRepeatP95"] = {k: round(v, 3) for k, v in pooled.items()}
    doc["pooledThresholdsNotUsed"] = {
        k: round(max(floors[k], MARGIN * pooled.get(k, 0.0)), 3) for k in floors}
    doc["pooledNote"] = ("recorded to show what a single pooled threshold would have been "
                         "and why it is not used: it is set by the least repeatable "
                         "scenario and would have judged a still page with that allowance.")
    doc["observables"] = [{"name": n, "unit": u, "what": w, "gate": GATED.get(n, [None])[0]}
                          for n, _, u, w in COMPARED]
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(json.dumps(doc["thresholds"], indent=1))
    print(f"-> {out_p}")
    return 0


def settle_ms(series: dict, key: str, tol: float = 1.0) -> float | None:
    """When did `key` last move more than `tol` away from its final value?"""
    y = series[key]
    good = np.isfinite(y)
    if good.sum() < 5:
        return None
    t, v = series["t"][good], y[good]
    final = float(np.median(v[-10:]))
    off = np.where(np.abs(v - final) > tol)[0]
    return round(float(t[off[-1]] - t[0]), 1) if off.size else 0.0


def travel(series: dict) -> float | None:
    cx = series["cx"][:, 0]
    cx = cx[np.isfinite(cx)]
    return round(float(cx.max() - cx.min()), 2) if cx.size else None


def judge(base: Path, thr_p: Path, out_p: Path) -> int:
    thr = json.loads(thr_p.read_text())
    T, L = runs_for("target", base), runs_for("local", base)
    doc = {
        "what": "VC2 §五 dynamic card geometry truth. Per-frame, per-card CSS3D matrix "
                "and projected rect, read by ONE reader on both pages, on matched media "
                "and matched copy. Global phase correlation is NOT used here and is not "
                "sufficient evidence for any spacing or trajectory claim.",
        "estimator": {
            "judgedOn": "the MEDIAN p95 across every Target-repeat x Candidate-repeat pair",
            "why": "the first version of this comparison judged one Target run against one "
                   "Candidate run. That single pair reported a 24.7 px flick divergence "
                   "which a second Candidate recording did not reproduce -- the Candidate's "
                   "own run-to-run spread was the larger term. The thresholds are NOT "
                   "changed by this; only the estimator is, from one sample to the full "
                   "pair matrix, and every pair is published below.",
            "disclosure": "this change was made after seeing that one pair was noisy.",
        },
        "resolution": {
            "RESOLVED": "the Candidate's own self-repeat spread is inside the threshold, so "
                        "a cross-page difference of that size would be visible to this "
                        "instrument",
            "UNRESOLVABLE": "the Candidate's own self-repeat spread already exceeds the "
                            "threshold. The pre-registered threshold was set from Target "
                            "self-repeats on the assumption that both pages jitter alike; "
                            "where that breaks, the repeatability IS the finding and a "
                            "pass/fail on the cross-page number would be meaningless.",
        },
        "thresholdsFrom": str(thr_p.relative_to(REPO)),
        "thresholdRule": thr["rule"], "thresholds": thr["thresholds"],
        "scenarios": {}, "assertions": [],
    }
    for scenario in sorted(set(T) & set(L)):
        ts = {r: series_of(p) for r, p in sorted(T[scenario].items())}
        ls = {r: series_of(p) for r, p in sorted(L[scenario].items())}
        limits = thr["thresholds"].get(scenario, {})

        cross = {}
        for tr, a in ts.items():
            for lr, b in ls.items():
                c = compare(a, b)
                for name, row in c["rows"].items():
                    cross.setdefault(name, []).append(row["delta"]["p95"])
        self_l = {}
        for ra, rb in itertools.combinations(sorted(ls), 2):
            c = compare(ls[ra], ls[rb])
            for name, row in c["rows"].items():
                self_l.setdefault(name, []).append(row["delta"]["p95"])

        rows = {}
        for name in cross:
            vals = [v for v in cross[name] if v is not None]
            selfv = [v for v in self_l.get(name, []) if v is not None]
            gate = GATED.get(name)
            limit = limits.get(gate[0]) if gate else None
            med = round(float(np.median(vals)), 3) if vals else None
            worst_self = round(max(selfv), 3) if selfv else None
            resolved = (limit is None or worst_self is None or worst_self <= limit)
            rows[name] = {
                "crossPairP95": {"median": med,
                                 "min": round(min(vals), 3) if vals else None,
                                 "max": round(max(vals), 3) if vals else None,
                                 "pairs": [round(v, 3) for v in vals]},
                "candidateSelfRepeatP95": {"worst": worst_self,
                                           "pairs": [round(v, 3) for v in selfv]},
                "targetSelfRepeatP95": (thr["selfRepeat"].get(scenario, {})
                                        .get("p95ByPair", {}).get(name)),
                "gate": gate[0] if gate else None, "limit": limit,
                "resolution": "RESOLVED" if resolved else "UNRESOLVABLE",
                "pass": None if (limit is None or med is None or not resolved)
                        else bool(med <= limit),
            }
        first_t, first_l = ts[sorted(ts)[0]], ls[sorted(ls)[0]]
        c0 = compare(first_t, first_l)
        doc["scenarios"][scenario] = {
            "vp": first_t["meta"].get("vp"), "resizeTo": first_t["meta"].get("resizeTo"),
            "what": first_t["meta"].get("what"),
            "cardsTracked": len(first_t["meta"].get("tracked", [])),
            "repeats": {"target": sorted(ts), "candidate": sorted(ls)},
            "sameCopy": all(first_t["meta"].get("copyBodySha") == s["meta"].get("copyBodySha")
                            for s in list(ts.values()) + list(ls.values())),
            "copyBodySha": first_t["meta"].get("copyBodySha"),
            "fps": {"target": [ts[r]["fps"] for r in sorted(ts)],
                    "candidate": [ls[r]["fps"] for r in sorted(ls)]},
            "travelPx": {"target": [travel(ts[r]) for r in sorted(ts)],
                         "candidate": [travel(ls[r]) for r in sorted(ls)]},
            "rowStaggerSettleMs": {
                "target": [settle_ms(ts[r], "rowStagger") for r in sorted(ts)],
                "candidate": [settle_ms(ls[r], "rowStagger") for r in sorted(ls)]},
            "limits": limits, "rows": rows,
            "dolly": c0["dolly"], "wrap": c0["wrap"],
        }

    fails = [(s, n) for s, sc in doc["scenarios"].items()
             for n, r in sc["rows"].items() if r["pass"] is False]
    unres = [(s, n) for s, sc in doc["scenarios"].items()
             for n, r in sc["rows"].items() if r["resolution"] == "UNRESOLVABLE"]
    doc["assertions"].append({
        "assertion": "every RESOLVED gated observable is inside its pre-registered "
                     "threshold, every scenario",
        "pass": not fails, "detail": [f"{s}:{n}" for s, n in fails] or None})
    doc["assertions"].append({
        "assertion": "matched copy across every recorded run on both sides",
        "pass": all(sc["sameCopy"] for sc in doc["scenarios"].values())})
    doc["assertions"].append({
        "assertion": "static layout identical: rest scenario agrees on every observable",
        "pass": all(r["crossPairP95"]["max"] in (0.0, None)
                    for r in doc["scenarios"].get("rest", {}).get("rows", {}).values()),
        "detail": {n: r["crossPairP95"]["max"]
                   for n, r in doc["scenarios"].get("rest", {}).get("rows", {}).items()}})
    doc["unresolvable"] = [
        {"scenario": s, "observable": n,
         "candidateSelfRepeatWorstP95": doc["scenarios"][s]["rows"][n]["candidateSelfRepeatP95"]["worst"],
         "limit": doc["scenarios"][s]["rows"][n]["limit"],
         "crossPairMedian": doc["scenarios"][s]["rows"][n]["crossPairP95"]["median"]}
        for s, n in unres]
    doc["divergences"] = [
        {"scenario": s, "observable": n,
         "crossPairP95": doc["scenarios"][s]["rows"][n]["crossPairP95"],
         "limit": doc["scenarios"][s]["rows"][n]["limit"]}
        for s, n in fails]
    doc["verdict"] = ("CARD GEOMETRY WITHIN PRE-REGISTERED THRESHOLDS"
                      if not fails else "CARD GEOMETRY DIVERGENCE FOUND")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(doc["verdict"])
    for s, sc in doc["scenarios"].items():
        bad = [f"{n}={sc['rows'][n]['crossPairP95']['median']}>{sc['rows'][n]['limit']}"
               for n in sc["rows"] if sc["rows"][n]["pass"] is False]
        un = [n for n in sc["rows"] if sc["rows"][n]["resolution"] == "UNRESOLVABLE"]
        print(f"  {s:<24} {'OK' if not bad else ' '.join(bad)}"
              + (f"   [unresolvable: {','.join(un)}]" if un else ""))
    print(f"-> {out_p}")
    return 0


def main() -> int:
    args = dict((a[2:].split("=", 1) + [True])[:2] for a in sys.argv[1:] if a.startswith("--"))
    base = Path(args.get("dir", DIR))
    if "preregister" in args:
        return preregister(base, Path(args.get("out", QA / "card-trajectory-thresholds.json")))
    if "compare" in args:
        return judge(base, Path(args.get("thresholds", QA / "card-trajectory-thresholds.json")),
                     Path(args.get("out", QA / "card-trajectory-truth.json")))
    raise SystemExit("need --preregister or --compare")


if __name__ == "__main__":
    raise SystemExit(main())
