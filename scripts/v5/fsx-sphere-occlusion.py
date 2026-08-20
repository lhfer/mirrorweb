#!/usr/bin/env python3
"""
Do overlapping projected cards mean a defect, or a sphere?

The screen-space overlap check was written when the grid was a cylinder, where
every card sat at a similar depth. On a sphere a lower row curves away and
passes behind the row above, so overlapping projections are expected. At one
viewport the Target's own pool is small enough that a wrapped card also lands
back on top of another at the SAME depth.

This measures both sides with one rule: the engine's projected quads, and quads
projected from the TARGET's own DOM world transforms. If the counts agree, the
overlap is the Target's behaviour and copying it is fidelity.

Usage: fsx-sphere-occlusion.py --engine=<engine.json> --dom=<dom>... --out=<json>
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(n, f):
    spec = importlib.util.spec_from_file_location(n, HERE / f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SC = _load("fsx_source_contract", "fsx-source-contract.py")
SL = _load("source_layout", "source_layout.py")
COPLANAR_WORLD = 42.0   # one card thickness; closer than this is the same plane
REAL_PENETRATION_PX = 1.0


def sep(a, b):
    best = -math.inf
    for poly in (a, b):
        for k in range(len(poly)):
            x0, y0 = poly[k]
            x1, y1 = poly[(k + 1) % len(poly)]
            nx, ny = -(y1 - y0), (x1 - x0)
            L = math.hypot(nx, ny)
            if L < 1e-9:
                continue
            nx, ny = nx / L, ny / L
            pa = [p[0] * nx + p[1] * ny for p in a]
            pb = [p[0] * nx + p[1] * ny for p in b]
            best = max(best, max(min(pb) - max(pa), min(pa) - max(pb)))
    return best


def classify(quads, w, h):
    on = [q for q in quads
          if max(p[0] for p in q["poly"]) > -40 and min(p[0] for p in q["poly"]) < w + 40
          and max(p[1] for p in q["poly"]) > -40 and min(p[1] for p in q["poly"]) < h + 40]
    pairs = coll = 0
    worst = math.inf
    worst_coll = 0.0
    for i in range(len(on)):
        for j in range(i + 1, len(on)):
            s = sep(on[i]["poly"], on[j]["poly"])
            worst = min(worst, s)
            if s > 0:
                continue
            pairs += 1
            if abs(on[i]["z"] - on[j]["z"]) <= COPLANAR_WORLD and s < -REAL_PENETRATION_PX:
                coll += 1
                worst_coll = min(worst_coll, s)
    return {"onScreen": len(on), "overlappingPairs": pairs, "occlusions": pairs - coll,
            "sameDepthCollisions": coll,
            "minSeparationPx": round(worst, 2) if on else None,
            "worstCollisionPx": round(worst_coll, 2)}


def target_quads(load):
    w, h = load["viewport"]
    f = SL.layout(w, h)
    R, persp = f["sphereRadius"], f["perspective"]
    out = []
    for c in SC.dom_cards(load):
        wx, wy, wz = SC.dom_world(c)
        n = (wx / R, wy / R, (wz + R) / R)
        ln = math.sqrt(sum(v * v for v in n)) or 1.0
        n = tuple(v / ln for v in n)
        q = SC.quat_from_unit_vectors((0.0, 0.0, 1.0), n)
        rx, ry = SC.rotate(q, (1.0, 0.0, 0.0)), SC.rotate(q, (0.0, 1.0, 0.0))
        hw, hh = c["cssW"] / 2, c["cssH"] / 2
        poly = []
        for sx, sy in ((-1, 1), (1, 1), (1, -1), (-1, -1)):
            p = [(wx, wy, wz)[k] + rx[k] * sx * hw + ry[k] * sy * hh for k in range(3)]
            pr = SC.project(p, persp, w, h)
            if pr is None:
                poly = []
                break
            poly.append(pr)
        if poly:
            out.append({"poly": poly, "z": wz})
    return out


def engine_quads(entry):
    return [{"poly": [tuple(p) for p in s["cornersPx"]], "z": s["world"][2]} for s in entry["slots"]]


if __name__ == "__main__":
    args = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if "=" in a and not a.startswith("--dom=")}
    doms = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--dom=")]
    by_id = {}
    for f in doms:
        for load in json.loads(Path(f).read_text())["loads"]:
            by_id.setdefault(load["id"], load)
    engine = json.loads(Path(args["--engine"]).read_text())
    eng_by_id = {e["id"]: e for e in engine["viewports"]}

    rows = []
    for vid, load in sorted(by_id.items()):
        w, h = load["viewport"]
        t = classify(target_quads(load), w, h)
        e = classify(engine_quads(eng_by_id[vid]), w, h) if vid in eng_by_id else None
        rows.append({"id": vid, "target": t, "engine": e,
                     "agrees": bool(e and e["overlappingPairs"] == t["overlappingPairs"]
                                    and e["sameDepthCollisions"] == t["sameDepthCollisions"])})
    measured = [r for r in rows if r["engine"]]
    payload = {
        "question": "Is an overlapping projected card pair a defect, or the sphere?",
        "rule": {"coplanarWorldUnits": COPLANAR_WORLD, "realPenetrationPx": REAL_PENETRATION_PX,
                 "note": "Two cards whose depths differ by more than one card thickness are "
                         "occluding, which is what a sphere does. Closer than that and they "
                         "share a plane, which would be a fault."},
        "viewportsCompared": len(measured),
        "engineMatchesTargetEverywhere": all(r["agrees"] for r in measured),
        "viewportsWithAnyOverlap": [r["id"] for r in measured if r["target"]["overlappingPairs"]],
        "viewportsWithSameDepthCollision": [r["id"] for r in measured if r["target"]["sameDepthCollisions"]],
        "viewports": rows,
    }
    Path(args["--out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["--out"]).write_text(json.dumps(payload, indent=2))
    print(f"engine matches Target at every viewport: {payload['engineMatchesTargetEverywhere']} "
          f"({len(measured)} compared)")
    for r in measured:
        if r["target"]["overlappingPairs"] or (r["engine"] and r["engine"]["overlappingPairs"]):
            print(f"  {r['id']:>10} target pairs={r['target']['overlappingPairs']:2d} "
                  f"coll={r['target']['sameDepthCollisions']} | engine pairs={r['engine']['overlappingPairs']:2d} "
                  f"coll={r['engine']['sameDepthCollisions']} | agrees={r['agrees']}")
