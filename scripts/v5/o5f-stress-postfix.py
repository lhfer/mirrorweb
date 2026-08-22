#!/usr/bin/env python3
"""O5F §十四 -- the post-correction stress gate, pre-registered.

This file is committed in `v5-o5f-portrait-source-code` BEFORE any §十四
re-capture exists, so the amended expectations below are sealed ahead of the
data exactly as §七's were.

What the §十一 correction changes about the cache's OBSERVABLE behaviour --
and nothing else:

  sample law    the unclamped lane's sample count is the DEVICE tier's,
                decided once at load, identical at every quality level.
                A coarse-pointer context therefore runs 3/3/3 and a
                fine-pointer context 5/5/5 where §七 expected 5/5/3.
  switches      the active cache key never changes on a quality step, so
                cacheSwitchCount stays 0 in every candidate context.
  uuid sets     exactly ONE distinct active-material-uuid list per candidate
                session (§七 allowed two, one per tier).
  cycle refs    in the fine-pointer cycle context the low tier binds the
                SAME set as high, so high==low reference UUIDs -- and the
                cross-tier still diagnostic flips to high==medium==low.

Everything else is §七 verbatim: the heap-slope and GC-trough formulas,
their floors, the control-relative thresholds (computed from the re-run's
OWN control sessions), resource constancy, first-frame, transition-pop.
This scorer first runs the SEALED scorer unchanged on the re-captured data
(for the record -- items 3, 4 and 10 flip by design under the new law and
that flip is itself evidence the law changed), then scores the §十四 gate:
sealed items 1, 2, 5, 6, 7, 8, 9 plus the three re-registered items below.

Every sample expectation is verified against the RECORDED context predicate
(each probe records matchMedia("(pointer: coarse)"), hardwareConcurrency,
deviceMemory), never against an assumed context.

Usage: o5f-stress-postfix.py [--cycle=...] [--sessions=...] [--out=...]
Output: artifacts/optics-o5f/stress-postfix/material-cache-stress-rerun.json
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
HERE = REPO / "scripts/v5"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o5f_stress_pf", "o5f_stress.py")

CYCLE = REPO / "artifacts/optics-o5f/stress-postfix/quality-cycle/quality-cycle.json"
SESSIONS = REPO / "artifacts/optics-o5f/stress-postfix/sessions/sessions-manifest.json"
OUT = REPO / "artifacts/optics-o5f/stress-postfix/material-cache-stress-rerun.json"
for a in sys.argv[1:]:
    k, _, v = a.lstrip("-").partition("=")
    if k == "cycle":
        CYCLE = Path(v)
    elif k == "sessions":
        SESSIONS = Path(v)
    elif k == "out":
        OUT = Path(v)


def predicate_low(p):
    """The Target's own tier predicate, applied to a RECORDED context."""
    return bool(p["pointerCoarse"] or p["hardwareConcurrency"] <= 6
                or p["deviceMemory"] <= 4)


def main() -> int:
    # ---- 1. the sealed scorer, unchanged, for the record ------------------
    sealed_out = OUT.parent / "sealed-scorer-on-postfix-data.json"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [sys.executable, str(HERE / "o5f-stress.py"),
         f"--cycle={CYCLE}", f"--sessions={SESSIONS}",
         f"--out={sealed_out}"],
        capture_output=True, text=True)
    sealed = json.loads(sealed_out.read_text())
    sealed_by_n = {c["n"]: c for c in sealed["checks"]}

    cycle = json.loads(CYCLE.read_text())
    man = json.loads(SESSIONS.read_text())
    cand = [x for x in man["records"] if x["lane"] == "candidate"]

    checks = []

    def add(n, check, ok, threshold, numbers):
        checks.append({"n": n, "check": check,
                       "status": "PASS" if ok else "FAIL",
                       "threshold": threshold, "numbers": numbers})

    # ---- unchanged items, straight off the sealed scorer ------------------
    for n in (1, 2, 5, 6, 7, 8, 9):
        c = dict(sealed_by_n[n])
        c["carriedFrom"] = "sealed §七 scorer, formulas untouched"
        checks.append(c)

    # ---- 3 (re-registered): EVERY quality transition creates nothing ------
    creation_events = []
    for x in cand:
        for q in x.get("qualitySteps", []):
            creation_events.append(q.get("creation"))
    cyc_creations = sorted({st["creation"] for st in cycle["steps"]})
    ok3 = (len(cyc_creations) == 1
           and len({c for c in creation_events if c is not None}) <= 1)
    add(3, "§十四: every quality transition creates zero material", ok3,
        "one creation count across all cycle steps and all session "
        "quality-step probes (device law: the key never changes)",
        {"cycleCreationCounts": cyc_creations,
         "sessionCreationCounts": sorted({c for c in creation_events
                                          if c is not None})})

    # ---- 4 (re-registered): one uuid list per context ---------------------
    refs = {k: v["truth"]["activeMaterialUuids"]
            for k, v in cycle["references"].items()}
    cycle_pred = cycle["steps"][0].get("contextPredicate") \
        or (cycle.get("warmup") or [{}])[0].get("contextPredicate")
    cycle_low = None if cycle_pred is None else predicate_low(cycle_pred)
    # In a fine-pointer cycle context all three tiers bind the SAME set; in
    # a coarse one likewise (the other set exists but never activates).
    refs_same = (refs.get("high") == refs.get("medium") == refs.get("low"))
    uuid_ok_steps = all(st["uuidOk"] for st in cycle["steps"])
    per_session = []
    per_ok = True
    for x in cand:
        cs = [s["cache"] for s in x["samples"] if s.get("cache")]
        lists = {tuple(c["activeMaterialUuids"]) for c in cs}
        vids = {tuple(c["videoTextureUuids"]) for c in cs}
        envs = {c["environmentUuid"] for c in cs}
        ok = len(lists) == 1 and len(vids) == 1 and len(envs) == 1
        per_ok = per_ok and ok
        per_session.append({"session": x["session"],
                            "distinctActiveUuidLists": len(lists),
                            "distinctVideoUuidLists": len(vids),
                            "distinctEnvUuids": len(envs)})
    ok4 = uuid_ok_steps and refs_same and per_ok
    add(4, "§十四: one active uuid list per context; references identical "
           "across tiers", ok4,
        "cycle reference uuids identical for high/medium/low (device law); "
        "every step returns them; exactly one distinct active list per "
        "candidate session",
        {"cycleReferencesIdentical": refs_same,
         "cycleContextLow": cycle_low,
         "perSession": per_session})

    # ---- 10 (re-registered): device-conditional sample count --------------
    rows = []
    ok10 = True
    for st in cycle["steps"]:
        p = st.get("contextPredicate")
        if p is None:
            continue
        expected = 3 if predicate_low(p) else 5
        if st["samples"] != expected:
            ok10 = False
            rows.append({"where": f"cycle step {st['step']}",
                         "level": st["level"], "samples": st["samples"],
                         "expected": expected})
    engine_agrees = True
    for st in cycle["steps"]:
        tier = st.get("deviceTier")
        p = st.get("contextPredicate")
        if tier is not None and p is not None \
                and bool(tier["low"]) != predicate_low(p):
            engine_agrees = False
            rows.append({"where": f"cycle step {st['step']}",
                         "engineLow": tier["low"],
                         "predicateLow": predicate_low(p)})
    sess_rows = []
    for x in cand:
        for s in x["samples"]:
            c, p = s.get("cache"), s.get("contextPredicate")
            if not c or not p or c.get("activeSamples") is None:
                continue
            expected = 3 if predicate_low(p) else 5
            if c["activeSamples"] != expected:
                ok10 = False
                sess_rows.append({"session": x["session"], "atMs": s["atMs"],
                                  "samples": c["activeSamples"],
                                  "expected": expected})
            dt = c.get("deviceTier")
            if dt is not None and bool(dt["low"]) != predicate_low(p):
                engine_agrees = False
                sess_rows.append({"session": x["session"], "atMs": s["atMs"],
                                  "engineLow": dt["low"],
                                  "predicateLow": predicate_low(p)})
    switch_counts = sorted({s["cache"]["cacheSwitchCount"]
                            for x in cand for s in x["samples"]
                            if s.get("cache")})
    ok_switch = switch_counts in ([0], [])
    ok10 = ok10 and engine_agrees and ok_switch
    add(10, "§十四: sample count follows the recorded device predicate at "
            "every quality; engine tier agrees; zero cache switches", ok10,
        "samples == (predicate low ? 3 : 5) at every probe; deviceTier.low "
        "== predicate; cacheSwitchCount stays 0",
        {"violations": rows + sess_rows, "engineAgrees": engine_agrees,
         "cacheSwitchCounts": switch_counts,
         "crossTierDiagnostic": cycle.get("crossTierDiagnostic")})

    checks.sort(key=lambda c: c["n"])
    passed = sum(1 for c in checks if c["status"] == "PASS")
    verdict = "PASS" if passed == len(checks) else "FAIL"
    doc = {
        "what": "§十四 -- the §七 stress gate re-run after the ONE §十一 "
                "correction, scored by this pre-registered addendum: heap "
                "and resource formulas byte-identical to §七, the three "
                "sample-law items re-registered for the device predicate.",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "amendedItems": [3, 4, 10],
        "carriedItems": [1, 2, 5, 6, 7, 8, 9],
        "sealedScorerOnSameData": {
            "file": str(sealed_out.relative_to(REPO)),
            "verdict": sealed["verdict"],
            "note": "items 3/4/10 flip by design under the device law; "
                    "that flip is evidence of the law change, recorded "
                    "here rather than hidden.",
            "exitCode": r.returncode,
        },
        "checks": checks,
        "passed": passed, "total": len(checks), "verdict": verdict,
        "finalStateIfFailed": "O5F MATERIAL CACHE FAILED",
    }
    OUT.write_text(json.dumps(doc, indent=1))
    for c in checks:
        print(f"{c['status']:>4}  {c['n']:>2}  {c['check']}")
    print(f"\n{passed}/{len(checks)}  verdict: {verdict}")
    print(f"-> {OUT}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
