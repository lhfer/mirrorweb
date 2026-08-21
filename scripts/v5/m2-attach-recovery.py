#!/usr/bin/env python3
"""Attach the per-sample scroll recovery to a captured trace, as a sidecar.

The brief requires every rAF sample to carry its scroll recovery beside the
engine truth. The recovery is a deterministic function of the card matrices the
sample already holds -- it is not a second measurement -- so it is written
here, per frame, into a compact sidecar rather than inflating the trace with a
number that can be recomputed from it. `recovery.json` sits beside `trace.json`
and is keyed the same way, one array entry per frame, in frame order.

Recording it explicitly matters for one reason: it is what a reader compares
against the engine's own scroll to establish that the recovery is accurate, and
that accuracy is what licenses using the recovery on a Target that publishes
nothing at all.

Usage: m2-attach-recovery.py --trace=<trace.json> [--trace=... ]
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


MT = _load("motion_trace", "motion_trace.py")
R = _load("m2_replay", "m2_replay.py")


def main() -> int:
    paths = [Path(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--trace=")]
    if not paths:
        print("usage: m2-attach-recovery.py --trace=<trace.json> [...]", file=sys.stderr)
        return 2
    for p in paths:
        trace = json.loads(p.read_text())
        out = {"what": "per-rAF-sample scroll recovery, in world units, one entry per "
                       "frame in frame order, derived from the card matrices in "
                       "trace.json by scripts/v5/motion_trace.py:trajectory",
               "trace": p.name, "runs": []}
        for run in trace["runs"]:
            obs = MT.trajectory(run)
            entry = {"viewport": run["id"], "sequence": run["sequence"],
                     "repeat": run["repeat"],
                     "frames": len(run["frames"]),
                     "t": [round(v, 3) for v in obs["t"]],
                     "scrollX": [round(v, 4) for v in obs["scrollX"]],
                     "scrollY": [round(v, 4) for v in obs["scrollY"]],
                     "liveCards": obs.get("liveCards", [])}
            tx = R.truth_series(run, "scrollX")
            if tx is not None and tx[0] is not None:
                ty = R.truth_series(run, "scrollY")
                entry["engineScrollX"] = [round(v - tx[0], 4) for v in tx]
                entry["engineScrollY"] = [round(v - ty[0], 4) for v in ty]
                entry["worstRecoveryErrorWorldUnits"] = round(max(
                    max(abs(a - b) for a, b in zip(obs["scrollX"], entry["engineScrollX"])),
                    max(abs(a - b) for a, b in zip(obs["scrollY"], entry["engineScrollY"]))), 6)
            out["runs"].append(entry)
        dest = p.with_name("recovery.json")
        dest.write_text(json.dumps(out))
        worst = max((r.get("worstRecoveryErrorWorldUnits", 0.0) for r in out["runs"]),
                    default=None)
        print(f"recovery -> {dest}  ({len(out['runs'])} runs"
              + (f", worst vs engine truth {worst:.4f} world units)" if worst else ")"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
