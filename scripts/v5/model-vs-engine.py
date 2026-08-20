#!/usr/bin/env python3
"""
Does the shipped engine project exactly the geometry the fitter solved for?

The Target comparison is done at rest. That generalises to every scroll offset
only if the engine's projection is the same closed-form geometry the fitter
scored -- no offset-dependent special cases anywhere. This compares the engine's
own reported card quads against the analytic model at every captured offset and
at a second viewport size, corner by corner.

Usage: model-vs-engine.py --dir=<capture dir> [--dir=<...>] --config=<config.ts>
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("fitlayout", HERE / "fit-layout.py")
FIT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(FIT)


def read_config(path: Path) -> dict:
    text = path.read_text()

    def num(block: str, key: str) -> float:
        section = re.search(block + r"\s*=\s*\{(.*?)\n\};", text, re.S).group(1)
        return float(re.search(rf"\b{key}:\s*(-?[\d.]+)", section).group(1))

    return {
        "cellW": num("GRID", "cellW"),
        "cellH": num("GRID", "cellH"),
        "restY0": num("GRID", "restY0"),
        "radius": num("GRID", "radius"),
        "tileW": num("TILE", "width"),
        "tileH": num("TILE", "height"),
    }


def compare(directory: Path, params: dict) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    vw = float(manifest["viewport"]["width"])
    vh = float(manifest["viewport"]["height"])
    states = []
    worst = 0.0
    for state in manifest["states"]:
        data = json.loads((directory / f"{state['id']}.json").read_text())
        p = dict(params, scrollX=state["offset"][0], scrollY=state["offset"][1])
        errs = []
        for entry in data["quads"]:
            engine = np.array([[x * vw, y * vh] for x, y in entry["quad"]])
            if engine[:, 0].max() < -600 or engine[:, 0].min() > vw + 600:
                continue
            model = FIT.card_quad(entry["i"], entry["j"], p, vw, vh)
            errs.append(float(np.abs(engine - model).max()))
        peak = max(errs) if errs else 0.0
        worst = max(worst, peak)
        states.append({
            "id": state["id"],
            "offset": state["offset"],
            "cards": len(errs),
            "maxCornerErrorPx": round(peak, 4),
            "rmsCornerErrorPx": round(float(np.sqrt(np.mean(np.square(errs)))), 4) if errs else 0.0,
        })
    return {"dir": str(directory), "viewport": [vw, vh], "states": states,
            "maxCornerErrorPx": round(worst, 4)}


if __name__ == "__main__":
    dirs = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--dir=")]
    cfg = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--config=")), "src/config.ts")
    out = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--out=")), "qa-v5/f0")
    params = read_config(Path(cfg))
    report = {"config": params, "captures": [compare(Path(d), params) for d in dirs]}
    report["maxCornerErrorPx"] = round(max(c["maxCornerErrorPx"] for c in report["captures"]), 4)
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / "model-vs-engine.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"config": params, "maxCornerErrorPx": report["maxCornerErrorPx"]}, indent=2))
    for c in report["captures"]:
        for s in c["states"]:
            print(f"  {Path(c['dir']).name}/{s['id']:<20} {int(c['viewport'][0])}x{int(c['viewport'][1])} "
                  f"cards={s['cards']:>3} max={s['maxCornerErrorPx']} rms={s['rmsCornerErrorPx']}")
