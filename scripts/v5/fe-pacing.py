#!/usr/bin/env python3
"""Final Entry §八 -- frame pacing through the entry, both sides.

§八 is explicit that an average FPS is not an answer, so nothing here reports
one. What it reports is the distribution: p50, p95, p99, the longest frame, and
how many frames crossed 8.3 / 16.7 / 25 ms -- over three windows that mean
different things and should not be pooled.

  preReady   navigation to ready. Behind an opaque overlay on both pages, so a
             long frame here costs a viewer nothing; it is reported because the
             compile lands in it and a compile that moved would show up here
             first.
  intro      ready to settle. This is the window §八 is about. Every frame here
             is on screen and moving.
  postIntro  the second after settle. The idle baseline the intro is measured
             against.

The recorder's own per-frame cost is subtracted where a corrected number is
given, and both are printed: it samples every drawn card's bounding box, which
is real work, is paid identically on both pages, and is large enough relative
to a 8.3 ms frame that hiding it would be dishonest.

Usage: fe-pacing.py --target=<dir> --local=<dir> [--out=<json>]
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fe_entry_geom as G  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent


def pct(values, q):
    if not values:
        return None
    v = sorted(values)
    k = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
    return round(v[k], 2)


def window_stats(frames, lo, hi, corrected=False):
    dts, costs = [], []
    for i in range(lo + 1, hi + 1):
        dt = frames[i]["t"] - frames[i - 1]["t"]
        c = frames[i].get("costMs") or 0.0
        dts.append(max(0.0, dt - c) if corrected else dt)
        costs.append(c)
    if not dts:
        return None
    return {
        "frames": len(dts),
        "p50": pct(dts, 0.50), "p95": pct(dts, 0.95), "p99": pct(dts, 0.99),
        "longestMs": round(max(dts), 2),
        "over8_3": sum(1 for d in dts if d > 8.3),
        "over16_7": sum(1 for d in dts if d > 16.7),
        "over25": sum(1 for d in dts if d > 25),
        "recorderCostP50Ms": round(statistics.median(costs), 3) if costs else None,
    }


def run_windows(path: Path):
    doc = json.loads(path.read_text())
    F = doc["trace"]["frames"]
    vp = doc["trace"].get("viewport")
    for f in F:
        f["viewportHint"] = vp
    ri = G.ready_index(F)
    fd = G.first_draw_index(F)
    if ri is None or fd is None:
        return None
    codes = G.tracked_codes(F, fd, len(F) - 1)
    si = G.settle_index(F, ri, codes)
    if si is None:
        return None
    post = min(len(F) - 1, si + 120)
    return {
        "cond": doc["cond"], "rep": doc["rep"], "viewport": doc["viewport"],
        "preReady": window_stats(F, 0, ri),
        "intro": window_stats(F, ri, si),
        "introCorrected": window_stats(F, ri, si, corrected=True),
        "postIntro": window_stats(F, si, post),
    }


def fold(rows, window, key):
    vals = [r[window][key] for r in rows if r and r.get(window) and r[window][key] is not None]
    if not vals:
        return None
    v = sorted(vals)
    return {"n": len(v), "min": v[0], "median": v[len(v) // 2], "max": v[-1]}


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    out = {}
    for side in ("target", "local"):
        d = Path(args.get(side if side == "target" else "local",
                          f"artifacts/final-entry/load/{side}"))
        if not d.is_absolute():
            d = REPO / d
        rows = [r for r in (run_windows(p) for p in sorted(d.glob("*-[0-9][0-9].json"))) if r]
        by = {}
        for r in rows:
            by.setdefault(r["cond"], []).append(r)
        out[side] = {"runs": rows, "byCondition": {
            c: {w: {k: fold(rs, w, k) for k in
                    ("p50", "p95", "p99", "longestMs", "over8_3", "over16_7", "over25")}
                for w in ("preReady", "intro", "introCorrected", "postIntro")}
            for c, rs in by.items()}}

    doc = {
        "what": "§八 frame pacing across the cold-load entry, matched windows, both pages",
        "noAverageFps": "Deliberately absent. §八 forbids an average-FPS pass and "
                        "nothing here computes one.",
        "windows": {
            "preReady": "navigation start to ready; behind an opaque overlay on both pages",
            "intro": "ready to settle; every frame is on screen and moving",
            "introCorrected": "the same window with the recorder's own measured "
                              "per-frame cost subtracted",
            "postIntro": "one second after settle -- the idle baseline",
        },
        "sides": out,
    }
    p = Path(args.get("out", REPO / "artifacts/final-entry/pacing.json"))
    if not p.is_absolute():
        p = REPO / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1))
    for cond in sorted(out["target"]["byCondition"]):
        t = out["target"]["byCondition"][cond]["intro"]
        l = out["local"]["byCondition"].get(cond, {}).get("intro")
        if not l:
            continue
        print(f"{cond}")
        for k in ("p50", "p95", "p99", "longestMs", "over16_7", "over25"):
            tv, lv = t[k], l[k]
            print(f"   intro {k:10} T {tv['median'] if tv else None:>8}"
                  f"   C {lv['median'] if lv else None:>8}")
    print(f"-> {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
