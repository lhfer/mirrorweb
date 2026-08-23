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


def judge(base: Path, thr_p: Path, out_p: Path) -> int:
    thr = json.loads(thr_p.read_text())
    T, L = runs_for("target", base), runs_for("local", base)
    doc = {
        "what": "VC2 §五 dynamic card geometry truth. Per-frame, per-card CSS3D matrix "
                "and projected rect, read by ONE reader on both pages, on matched media "
                "and matched copy. Global phase correlation is NOT used here and is not "
                "sufficient evidence for any spacing or trajectory claim.",
        "thresholdsFrom": str(thr_p.relative_to(REPO)),
        "thresholdRule": thr["rule"], "thresholds": thr["thresholds"],
        "scenarios": {}, "assertions": [],
    }
    for scenario in sorted(set(T) & set(L)):
        a, b = series_of(T[scenario][0]), series_of(L[scenario][0])
        c = compare(a, b)
        limits = thr["thresholds"].get(scenario, {})
        rows = {}
        for name, row in c["rows"].items():
            gate = GATED.get(name)
            limit = limits.get(gate[0]) if gate else None
            p95 = row["delta"]["p95"]
            rows[name] = {**row, "gate": gate[0] if gate else None, "limit": limit,
                          "pass": None if limit is None or p95 is None else bool(p95 <= limit)}
        doc["scenarios"][scenario] = {
            "vp": a["meta"].get("vp"), "resizeTo": a["meta"].get("resizeTo"),
            "what": a["meta"].get("what"),
            "cardsTracked": len(a["meta"].get("tracked", [])),
            "copyBodySha": {"target": a["meta"].get("copyBodySha"),
                            "candidate": b["meta"].get("copyBodySha")},
            "sameCopy": a["meta"].get("copyBodySha") == b["meta"].get("copyBodySha"),
            "gridFrames": c["gridFrames"], "gridSpanMs": c["gridSpanMs"], "fps": c["fps"],
            "limits": limits,
            "rows": rows, "dolly": c["dolly"], "wrap": c["wrap"],
        }
    fails = [(s, n) for s, sc in doc["scenarios"].items()
             for n, r in sc["rows"].items() if r["pass"] is False]
    doc["assertions"].append({
        "assertion": "every gated observable within its pre-registered threshold, every scenario",
        "pass": not fails, "detail": [f"{s}:{n}" for s, n in fails] or None})
    doc["assertions"].append({
        "assertion": "matched copy on both sides in every compared scenario",
        "pass": all(sc["sameCopy"] for sc in doc["scenarios"].values())})
    doc["assertions"].append({
        "assertion": "dolly excursion agrees to within 0.01 of projected-size ratio",
        "pass": all(sc["dolly"]["excursionDelta"] <= 0.01 for sc in doc["scenarios"].values()),
        "detail": {s: sc["dolly"]["excursionDelta"] for s, sc in doc["scenarios"].items()}})
    doc["verdict"] = ("CARD GEOMETRY WITHIN PRE-REGISTERED THRESHOLDS"
                      if not fails else "CARD GEOMETRY DIVERGENCE FOUND")
    doc["divergences"] = [
        {"scenario": s, "observable": n,
         "targetAtRest": doc["scenarios"][s]["rows"][n]["aAtRest"],
         "candidateAtRest": doc["scenarios"][s]["rows"][n]["bAtRest"],
         "delta": doc["scenarios"][s]["rows"][n]["delta"],
         "limit": doc["scenarios"][s]["rows"][n]["limit"]}
        for s, n in fails]
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    print(doc["verdict"])
    for s, sc in doc["scenarios"].items():
        bad = [f"{n}={sc['rows'][n]['delta']['p95']}>{sc['rows'][n]['limit']}"
               for n in sc["rows"] if sc["rows"][n]["pass"] is False]
        print(f"  {s:<24} {'OK' if not bad else ' '.join(bad)}")
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
