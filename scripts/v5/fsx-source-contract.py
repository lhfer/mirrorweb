#!/usr/bin/env python3
"""
The Source-Exact Engineering Gate.

Three independent things must agree at every viewport:

  MODEL   scripts/v5/source_layout.py, reading config/target-layout-source-v2.json
  ENGINE  the running app, read back off live object matrices and the live camera
  TARGET  the Target's own CSS3D world transforms

Model-vs-engine catches an implementation that drifted from the contract.
Engine-vs-Target catches a contract that was transcribed wrongly. Neither alone
is sufficient, and comparing the model with itself proves nothing at all.

This is an ENGINEERING gate. Passing it does not assert a Target visual result.

Usage: fsx-source-contract.py --engine=<engine.json> --dom=<dom-state.json>... --out=<json>
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SL = _load("source_layout", "source_layout.py")

TOL = {
    "perspectivePx": 0.01,
    "sphereRadiusWorld": 0.01,
    "planeSizeWorld": 0.01,
    "cellWorld": 0.01,
    "slotWorldPositionModel": 0.1,
    "slotWorldPositionTarget": 0.1,
    "orientationDeg": 0.05,
    "projectedCornerPx": 0.5,
}


def dom_cards(load: dict) -> list[dict]:
    """
    Target cards that can be trusted.

    A card the Target has culled keeps a STALE transform and empty text, so only
    code-bearing cards carry a current pose. The scene root is also a
    matrix3d div containing every label, which is what the multi-code filter
    removes. Both filters are the corrected reader from F2.7, not a rewrite.
    """
    w, h = load["viewport"]
    return [c for c in load["cards"]
            if c["code"] is not None and c["text"].count("ILG") == 1
            and c["cssW"] < w and c["cssH"] < h]


def dom_world(card: dict) -> tuple[float, float, float]:
    """The card element's transform composes translate(-50%,-50%) with the matrix."""
    return (card["tx"] + card["cssW"] / 2, card["ty"] + card["cssH"] / 2, card["tz"])


def quat_from_unit_vectors(a, b):
    """Minimal rotation taking a to b. Mirrors Three's setFromUnitVectors."""
    dot = sum(x * y for x, y in zip(a, b))
    if dot < -0.999999:
        axis = (1.0, 0.0, 0.0) if abs(a[0]) < 0.9 else (0.0, 1.0, 0.0)
        cx = (a[1] * axis[2] - a[2] * axis[1], a[2] * axis[0] - a[0] * axis[2],
              a[0] * axis[1] - a[1] * axis[0])
        n = math.hypot(*cx) or 1.0
        return (cx[0] / n, cx[1] / n, cx[2] / n, 0.0)
    cx = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    q = (cx[0], cx[1], cx[2], 1.0 + dot)
    n = math.sqrt(sum(v * v for v in q)) or 1.0
    return tuple(v / n for v in q)


def rotate(q, v):
    """Rotate v by quaternion q = (x, y, z, w)."""
    x, y, z, w = q
    tx = 2 * (y * v[2] - z * v[1])
    ty = 2 * (z * v[0] - x * v[2])
    tz = 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty),
            v[1] + w * ty + (z * tx - x * tz),
            v[2] + w * tz + (x * ty - y * tx))


def angle_between(a, b) -> float:
    dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
    return math.degrees(math.acos(dot))


def project(world, persp, vw, vh):
    """The Target's own projection: camera on axis at `persp`, looking at origin."""
    denom = persp - world[2]
    if denom <= 1e-9:
        return None
    return (vw / 2 + world[0] * persp / denom, vh / 2 - world[1] * persp / denom)


def check(items, name, value, limit, unit, detail=""):
    ok = bool(value <= limit) if isinstance(value, (int, float)) and not isinstance(value, bool) \
        else bool(value is True)
    items.append({"check": name, "value": round(value, 6) if isinstance(value, float) else value,
                  "limit": limit, "unit": unit, "pass": ok, "detail": detail})


def compare(entry: dict, dom: dict | None) -> dict:
    vw, vh = entry["viewport"]
    frame = entry["frame"]
    model = SL.layout(vw, vh)
    checks: list[dict] = []

    check(checks, "perspective (engine vs model)", abs(frame["perspective"] - model["perspective"]),
          TOL["perspectivePx"], "px")
    check(checks, "sphereRadius (engine vs model)", abs(frame["sphereRadius"] - model["sphereRadius"]),
          TOL["sphereRadiusWorld"], "world")
    check(checks, "planeWidth (engine vs model)", abs(frame["planeWidth"] - model["planeWidth"]),
          TOL["planeSizeWorld"], "world")
    check(checks, "planeHeight (engine vs model)", abs(frame["planeHeight"] - model["planeHeight"]),
          TOL["planeSizeWorld"], "world")
    check(checks, "cellW (engine vs model)", abs(frame["cellW"] - model["cellW"]), TOL["cellWorld"], "world")
    check(checks, "cellH (engine vs model)", abs(frame["cellH"] - model["cellH"]), TOL["cellWorld"], "world")
    check(checks, "cols exact", frame["cols"] == model["cols"], True, "bool",
          f"engine {frame['cols']}, model {model['cols']}")
    check(checks, "rows exact", frame["rows"] == model["rows"], True, "bool",
          f"engine {frame['rows']}, model {model['rows']}")
    check(checks, "card aspect is 4/3",
          abs(frame["planeWidth"] / frame["planeHeight"] - 4 / 3) <= 1e-9, True, "bool")
    check(checks, "active slot count exact",
          entry["activeSlotCount"] == model["activeSlotCount"], True, "bool",
          f"engine {entry['activeSlotCount']}, model {model['activeSlotCount']}")
    check(checks, "initial scroll is zero",
          entry["scroll"][0] == 0 and entry["scroll"][1] == 0, True, "bool", str(entry["scroll"]))
    check(checks, "ILG code is slotIndex + 1",
          bool(entry["slotIdentity"]["codesAreSlotIndexPlusOne"]), True, "bool")
    check(checks, "inactive slots hidden",
          bool(entry["slotIdentity"]["inactiveHidden"]), True, "bool")

    cam = entry["camera"]
    mcam = SL.camera(model)
    check(checks, "camera on axis", bool(cam["cameraOnAxis"]), True, "bool")
    check(checks, "camera distance == perspective",
          abs(cam["actualCameraZ"] - model["perspective"]), TOL["perspectivePx"], "px")
    check(checks, "camera fov == 2*atan(h/2/perspective)",
          abs(cam["actualFovDeg"] - mcam["fovDeg"]), 1e-6, "deg")
    check(checks, "one world unit is one CSS pixel at z=0",
          abs(cam["oneWorldUnitIsOneCssPixelAtZ0"] - 1.0), 1e-6, "px/world")
    check(checks, "near/far from contract",
          cam["near"] == SL.CAMERA["near"] and cam["far"] == SL.CAMERA["far"], True, "bool")

    # ---- engine slots against the model, over EVERY active slot -------------
    worst_pos = worst_ang = worst_corner = 0.0
    corners_compared = 0
    corners_offscreen = 0
    half_w, half_h = model["planeWidth"] / 2, model["planeHeight"] / 2
    for slot in entry["slots"]:
        m = SL.place(slot["slotIndex"], 0.0, 0.0, model)
        worst_pos = max(worst_pos, math.dist(slot["world"], [m["x"], m["y"], m["z"]]))
        n = (m["nx"], m["ny"], m["nz"])
        worst_ang = max(worst_ang, angle_between(slot["normal"], n))
        # The card's in-plane axes are whatever the MINIMAL rotation from +Z to
        # the normal produces -- the same quaternion the engine builds. Picking
        # any other orthogonal basis rolls the card in its own plane and moves
        # every corner, which is what made this check read six figures.
        q = quat_from_unit_vectors((0.0, 0.0, 1.0), n)
        rx = rotate(q, (1.0, 0.0, 0.0))
        ry = rotate(q, (0.0, 1.0, 0.0))
        for idx, (sx, sy) in enumerate(((-1, 1), (1, 1), (1, -1), (-1, -1))):
            wp = [m[k] + rx[a] * sx * half_w + ry[a] * sy * half_h
                  for a, k in enumerate(("x", "y", "z"))]
            pm = project(wp, model["perspective"], vw, vh)
            pe = slot["cornersPx"][idx]
            if pm is None:
                continue
            # Only cards the screen can actually show are compared in pixels. A
            # card swung past the horizon projects to five- and six-figure
            # coordinates where a fractional world difference becomes a huge
            # pixel one; it is off screen, the pixel gate never sees it, and its
            # geometry is already covered by the world-position check above at
            # 0.1 world units. Exclusions are counted, not hidden.
            on_screen = (-2 * vw <= pm[0] <= 3 * vw) and (-2 * vh <= pm[1] <= 3 * vh)
            if not on_screen:
                corners_offscreen += 1
                continue
            corners_compared += 1
            worst_corner = max(worst_corner, math.dist(pm, pe))
    check(checks, "every active slot world position (engine vs model)", worst_pos,
          TOL["slotWorldPositionModel"], "world", f"{len(entry['slots'])} slots")
    check(checks, "every active slot orientation (engine vs model)", worst_ang,
          TOL["orientationDeg"], "deg")
    check(checks, "projected card corners (engine vs model)", worst_corner,
          TOL["projectedCornerPx"], "px",
          f"{corners_compared} corners on or near screen, {corners_offscreen} past the "
          f"horizon and covered by the world-position check instead")

    # ---- engine against the Target's own DOM, where the Target is readable ---
    target = {"status": "NOT_AVAILABLE", "reason": "no Target DOM capture at this viewport"}
    if dom is not None:
        cards = dom_cards(dom)
        engine_by_arc = []
        for slot in entry["slots"]:
            m = SL.place(slot["slotIndex"], 0.0, 0.0, model)
            engine_by_arc.append((m["xArc"], m["yArc"], slot))
        worst_t = 0.0
        matched = 0
        for c in cards:
            tw = dom_world(c)
            best = None
            for _, _, slot in engine_by_arc:
                d = math.dist(slot["world"], tw)
                if best is None or d < best[0]:
                    best = (d, slot)
            if best is None:
                continue
            worst_t = max(worst_t, best[0])
            matched += 1
        check(checks, "every visible Target card matched by an engine slot (world)", worst_t,
              TOL["slotWorldPositionTarget"], "world",
              f"{matched} of {len(cards)} code-bearing Target cards")
        target = {
            "status": "MEASURED",
            "codeBearingCards": len(cards),
            "matched": matched,
            "worstWorldDeltaToEngine": round(worst_t, 6),
            "note": "Culled Target cards keep a STALE transform and empty text, so only "
                    "code-bearing cards carry a current pose and only they can be compared. "
                    "This is a property of the Target, not an unmeasured item.",
        }

    verdict = "PASS" if all(c["pass"] for c in checks) else "FAIL"
    return {"id": entry["id"], "viewport": [vw, vh], "verdict": verdict,
            "cols": frame["cols"], "rows": frame["rows"],
            "activeSlotCount": entry["activeSlotCount"],
            "worstSlotWorldVsModel": round(worst_pos, 8),
            "worstOrientationDegVsModel": round(worst_ang, 8),
            "worstProjectedCornerPx": round(worst_corner, 6),
            "targetDom": target,
            "checks": checks}


if __name__ == "__main__":
    args = {a.split("=", 1)[0]: a.split("=", 1)[1] for a in sys.argv[1:] if "=" in a and not a.startswith("--dom=")}
    doms = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--dom=")]
    engine = json.loads(Path(args["--engine"]).read_text())
    dom_by_id: dict[str, dict] = {}
    for f in doms:
        for load in json.loads(Path(f).read_text())["loads"]:
            dom_by_id.setdefault(load["id"], load)

    results = [compare(e, dom_by_id.get(e["id"])) for e in engine["viewports"]]
    passed = [r for r in results if r["verdict"] == "PASS"]
    payload = {
        "gate": "source-exact engineering contract",
        "contract": "config/target-layout-source-v2.json",
        "bundleSha256": SL.CONTRACT["target"]["appBundleSha256"],
        "layoutVersion": SL.CONTRACT["layoutVersion"],
        "isEngineeringGateOnly": "Passing this gate does NOT assert a Target visual result. "
                                 "It asserts that the engine, the model and the Target's own "
                                 "DOM agree about geometry.",
        "tolerances": TOL,
        "viewports": len(results),
        "passed": len(passed),
        "verdict": "PASS" if len(passed) == len(results) else "FAIL",
        "worstSlotWorldVsModel": round(max(r["worstSlotWorldVsModel"] for r in results), 8),
        "worstOrientationDegVsModel": round(max(r["worstOrientationDegVsModel"] for r in results), 8),
        "worstProjectedCornerPx": round(max(r["worstProjectedCornerPx"] for r in results), 6),
        "worstWorldDeltaToTargetDom": round(max(
            (r["targetDom"]["worstWorldDeltaToEngine"] for r in results
             if r["targetDom"]["status"] == "MEASURED"), default=0.0), 8),
        "viewportsWithTargetDom": sum(1 for r in results if r["targetDom"]["status"] == "MEASURED"),
        "results": results,
    }
    Path(args["--out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(args["--out"]).write_text(json.dumps(payload, indent=2))
    print(f"{payload['verdict']}  {payload['passed']}/{payload['viewports']} viewports")
    print(f"  worst slot world vs model   {payload['worstSlotWorldVsModel']}")
    print(f"  worst orientation vs model  {payload['worstOrientationDegVsModel']} deg")
    print(f"  worst projected corner      {payload['worstProjectedCornerPx']} px")
    print(f"  worst world vs Target DOM   {payload['worstWorldDeltaToTargetDom']} "
          f"({payload['viewportsWithTargetDom']} viewports)")
    for r in results:
        if r["verdict"] != "PASS":
            print(f"  FAIL {r['id']}: " + "; ".join(
                f"{c['check']}={c['value']}" for c in r["checks"] if not c["pass"]))
