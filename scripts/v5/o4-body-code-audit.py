#!/usr/bin/env python3
"""O4A — analysis side of the compiled Body-path audit (§三).

Answers, from the generated program and from runtime probes only:

  Does the TSL shared-normal codegen issue O2 root-caused also affect the
  current Beauty refraction path?

Static half: locate every site where the geometry normal is UNPACKED
(`normalViewGeometry = normalize(v_normalViewGeometry)`) and every site
where it is merely ALIASED (`normalView = normalViewGeometry`), and place
each inside the debug-select branch it belongs to. `normalViewGeometry` is
a module-scope `var<private>`, which WGSL zero-initialises, so an alias in
a branch with no unpack reads the zero vector.

Runtime half: two debug views read `normalView` in DIFFERENT branches of
the same program, in the same frame, over the same geometry.

  normals  renders the normal itself
  fresnel  renders pow(1 - saturate(dot(normalView, V)), 5)

A normal that varies across the card cannot produce a spatially constant
fresnel. If the normals view varies and the fresnel view does not, the two
branches are demonstrably reading different values — which is what a single
unpack site predicts.

`optical-zones` and `thickness` read unshared vertex attributes and are the
control: they show the harness, geometry and capture are sound.

Nothing is fixed here. §三 forbids it.

Usage: o4-body-code-audit.py [--captures=<dir>] [--out=<json>]
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


S = _load("o4_stats", "o2_optics_stats.py")

#: A decoded normal is valid when its length is 1 within 8-bit quantisation
#: plus tone-transfer slack. NaN cannot survive a PNG readback as NaN, so it
#: is detected here as an invalid length, not counted directly -- stated
#: rather than glossed.
NORMAL_LEN_TOL = 0.12
#: Spatially constant to within this 0-255 range over the card interior.
FLAT_RANGE = 2.0

BRANCH_RE = re.compile(r"(?:object\.)?nodeUniform0\s*==\s*([0-9.]+)")
DEBUG_NAME = {0: "beauty", 1: "edge-mask", 2: "optical-zones", 3: "normals",
              4: "thickness", 5: "refraction-offset", 6: "reflection",
              7: "fresnel", 8: "dispersion", 9: "adaptivity",
              10: "rim-mask", 11: "analytic-normal"}


def branch_map(lines):
    """Debug-branch context for every line, by a FORWARD parse.

    The chain is a nest of `if (nodeUniform0 == N) { ... } else { ... }`.
    A backward walk gets this wrong: arriving at `} else {` from below it
    cannot tell that everything above belongs to the taken side, so it
    attributes the else body to the very test the else excludes. A forward
    parse over a brace stack cannot make that mistake.

    A line belongs to debug code N when its innermost enclosing frame is
    that test's THEN side. A line that sits in the else side of every test
    in the chain is the beauty path.
    """
    out = [None] * len(lines)
    stack = []                       # frames: {code, side, depth}
    depth = 0
    for i, line in enumerate(lines):
        opens, closes = line.count("{"), line.count("}")
        is_else = re.search(r"\}\s*else\s*\{", line) is not None
        if is_else and stack and stack[-1]["depth"] == depth - closes:
            stack[-1]["side"] = "else"
            out[i] = dict(stack[-1])
            depth += opens - closes
            continue
        depth_before = depth - closes
        while stack and stack[-1]["depth"] > depth_before:
            stack.pop()
        m = BRANCH_RE.search(line)
        inner = next((f for f in reversed(stack) if f["side"] == "then"), None)
        if inner is not None:
            code = inner["code"]
            out[i] = {"branch": DEBUG_NAME.get(code, f"debugCode {code}"),
                      "debugCode": code, "side": "taken"}
        else:
            out[i] = {"branch": "beauty (else side of every debug test)",
                      "debugCode": 0, "side": "fallthrough"}
        if m and opens > closes:
            stack.append({"code": int(float(m.group(1))), "side": "then",
                          "depth": depth_before})
        depth += opens - closes
    return out


def analyse_program(path: Path) -> dict:
    text = path.read_text()
    lines = text.split("\n")
    bmap = branch_map(lines)
    unpacks, aliases = [], []
    for i, line in enumerate(lines):
        ctx = bmap[i] or {"branch": "unknown", "debugCode": None, "side": None}
        ctx = {k: v for k, v in ctx.items() if k != "depth"}
        if re.search(r"normalViewGeometry\s*=\s*normalize\(", line):
            unpacks.append({"line": i + 1, **ctx})
        elif re.search(r"normalView\s*=\s*normalViewGeometry\s*;", line):
            aliases.append({"line": i + 1, **ctx})
    consumers = {
        "refract": [i + 1 for i, l in enumerate(lines)
                    if "refract(" in l and "normalView" in l],
        "projectedNormalOffset": [i + 1 for i, l in enumerate(lines)
                                  if "normalView.x" in l],
        "facingDot": [i + 1 for i, l in enumerate(lines)
                      if "dot( normalView" in l or "dot(normalView" in l],
    }
    unpacked_branches = {u["branch"] for u in unpacks}
    starved = [a for a in aliases if a["branch"] not in unpacked_branches]
    return {
        "file": path.name,
        "privateDeclaration": bool(re.search(
            r"var<private>\s+normalViewGeometry", text)),
        "zeroInitialisedByLanguage":
            "WGSL zero-initialises module-scope var<private>",
        "unpackSites": unpacks,
        "aliasSites": aliases,
        "aliasSitesInBranchesWithNoUnpack": starved,
        "consumerLines": consumers,
        "beautyBranchAliases": [a for a in aliases
                                if a["debugCode"] == 0],
    }


def card_mask_stats(img: Image.Image, rects, label):
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    px = []
    for (x0, y0, x1, y1) in rects:
        cw, ch = x1 - x0, y1 - y0
        px.append(a[y0 + int(ch * .12):y1 - int(ch * .12),
                    x0 + int(cw * .12):x1 - int(cw * .12)].reshape(-1, 3))
    p = np.concatenate(px)
    return {
        "view": label,
        "pixels": int(len(p)),
        "meanRGB": [round(float(v), 2) for v in p.mean(axis=0)],
        "minRGB": [round(float(v), 2) for v in p.min(axis=0)],
        "maxRGB": [round(float(v), 2) for v in p.max(axis=0)],
        "rangeRGB": [round(float(v), 2) for v in (p.max(axis=0) - p.min(axis=0))],
        "stdRGB": [round(float(v), 3) for v in p.std(axis=0)],
        "spatiallyConstant": bool((p.max(axis=0) - p.min(axis=0)).max() <= FLAT_RANGE),
    }


def transect(img: Image.Image, rect, samples=(("centre", 0.5), ("shoulder", 0.10),
                                              ("rim", 0.015))):
    """Value at fractional inset from the card's LEFT edge, mid height."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    x0, y0, x1, y1 = rect
    cw, ch = x1 - x0, y1 - y0
    y = slice(y0 + int(ch * 0.45), y0 + int(ch * 0.55))
    out = {}
    for name, frac in samples:
        x = int(x0 + cw * frac)
        out[name] = [round(float(v), 2) for v in a[y, x - 1:x + 2].mean(axis=(0, 1))]
    return out


def normal_validity(img: Image.Image, rects):
    """Decode n = 2c - 1 and check |n| ~ 1."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    px = []
    for (x0, y0, x1, y1) in rects:
        cw, ch = x1 - x0, y1 - y0
        px.append(a[y0 + int(ch * .12):y1 - int(ch * .12),
                    x0 + int(cw * .12):x1 - int(cw * .12)].reshape(-1, 3))
    n = np.concatenate(px) * 2.0 - 1.0
    ln = np.linalg.norm(n, axis=1)
    finite = np.isfinite(ln)
    valid = finite & (np.abs(ln - 1.0) <= NORMAL_LEN_TOL)
    return {
        "pixels": int(len(ln)),
        "nonFinitePixels": int((~finite).sum()),
        "unitLengthPixels": int(valid.sum()),
        "unitLengthFraction": round(float(valid.mean()), 4),
        "meanLength": round(float(ln[finite].mean()), 4),
        "lengthRange": [round(float(ln[finite].min()), 4),
                        round(float(ln[finite].max()), 4)],
        "note": "the readback is 8-bit PNG, so a NaN cannot arrive as NaN. It "
                "is detected here as an invalid decoded length, not counted "
                "directly. Stated rather than implied.",
        "unitLengthFractionIsNotAValidityVerdict":
            "the body material is toneMapped, so the debug output passes "
            "through ACES before readback and n = 2c - 1 does not invert it. "
            "The meaningful readings here are that NO pixel is non-finite and "
            "that the length range is tight and centred near 1 -- consistent "
            "with a unit normal through a monotone transfer. The low "
            "unit-length fraction is the transfer, not a bad normal, and the "
            "audit does not rest on it: it rests on the single unpack site "
            "and on the normals-vs-fresnel discriminator.",
    }


def main() -> int:
    opts = {"captures": REPO / "artifacts/optics-o4/audit",
            "out": REPO / "qa-v5/optics-o4/body-code-audit.json"}
    for a in sys.argv[1:]:
        k, _, v = a.lstrip("-").partition("=")
        if k in opts:
            opts[k] = Path(v)
    cap = Path(opts["captures"])
    man = json.loads((cap / "audit-captures.json").read_text())
    rects = [r for _, r in S.rects_at(1440, 900)]
    biggest = max(rects, key=lambda r: (r[2] - r[0]) * (r[3] - r[1]))

    programs, probes = {}, {}
    for q in ["high", "medium", "low"]:
        p = cap / f"program-{q}.txt"
        if p.exists():
            programs[q] = analyse_program(p)
        rows, tr = {}, {}
        for rec in man["records"]:
            if rec.get("quality") != q or "view" not in rec:
                continue
            img = Image.open(cap / rec["file"])
            rows[rec["view"]] = card_mask_stats(img, rects, rec["view"])
            tr[rec["view"]] = transect(img, biggest)
            if rec["view"] == "normals":
                rows[rec["view"]]["normalValidity"] = normal_validity(img, rects)
        probes[q] = {"views": rows, "transectFromLeftEdge": tr}

    # ---------------------------------------------------------------- verdict
    prog = programs.get("high", {})
    single_unpack = len(prog.get("unpackSites", [])) == 1
    unpack_branch = (prog["unpackSites"][0]["branch"]
                     if prog.get("unpackSites") else None)
    beauty_starved = bool(prog.get("beautyBranchAliases")) and all(
        a in prog.get("aliasSitesInBranchesWithNoUnpack", [])
        for a in prog.get("beautyBranchAliases", []))

    hi = probes.get("high", {}).get("views", {})
    normals_varies = not hi.get("normals", {}).get("spatiallyConstant", True)
    fresnel_flat = hi.get("fresnel", {}).get("spatiallyConstant", False)
    controls_vary = (not hi.get("optical-zones", {}).get("spatiallyConstant", True)
                     and not hi.get("thickness", {}).get("spatiallyConstant", True))
    offset_flat = hi.get("refraction-offset", {}).get("spatiallyConstant", False)

    measurable = bool(programs) and bool(hi) and controls_vary
    affected = bool(single_unpack and beauty_starved and normals_varies
                    and fresnel_flat)

    doc = {
        "what": "O4A — compiled Body-path audit. Read from the generated "
                "program and from runtime probes; no TypeScript comment is "
                "evidence here, and nothing was fixed.",
        "question": "Does the TSL shared-normal codegen issue discovered in "
                    "O2 also affect the current Beauty refraction path?",
        "answer": ("YES. The geometry normal is unpacked exactly once, inside "
                   "the `normals` debug branch. Every other branch -- the "
                   "shipped Beauty path included -- aliases a "
                   "zero-initialised var<private>, so the Beauty refraction, "
                   "the projected-normal offset and the facing term all "
                   "consume a ZERO normal."
                   if affected else
                   "NO -- see the sites and probes below."),
        "auditMeasurable": measurable,
        "verdict": "AFFECTED" if affected else ("UNAFFECTED" if measurable
                                                else "NOT MEASURABLE"),
        "staticEvidence": {
            "unpackSiteCount": len(prog.get("unpackSites", [])),
            "unpackBranch": unpack_branch,
            "aliasSiteCount": len(prog.get("aliasSites", [])),
            "aliasSitesInBranchesWithNoUnpack":
                len(prog.get("aliasSitesInBranchesWithNoUnpack", [])),
            "beautyBranchAliasLines":
                [a["line"] for a in prog.get("beautyBranchAliases", [])],
            "perQuality": programs,
        },
        "runtimeEvidence": {
            "discriminator":
                "`normals` and `fresnel` read normalView in DIFFERENT branches "
                "of one program, same frame, same geometry. A normal that "
                "varies across the card cannot yield a spatially constant "
                "fresnel; if it does, the branches are reading different "
                "values.",
            "normalsViewVaries": normals_varies,
            "fresnelViewSpatiallyConstant": fresnel_flat,
            "refractionOffsetViewSpatiallyConstant": offset_flat,
            "controlViewsVary": controls_vary,
            "controlNote":
                "optical-zones and thickness read unshared vertex attributes. "
                "They vary correctly, which places the fault in the shared "
                "normal emission rather than in the geometry, the harness or "
                "the capture.",
            "perQuality": probes,
        },
        "consequencesInTheShippedBeautyPath": [
            "refract(-V, N, 1/ior) with N = 0 returns eta * incident -- a "
            "scaled view ray with NO dependence on the surface, so the "
            "refraction displacement carries perspective only.",
            "projectedNormalOffset = vec2(N.x, -N.y) * ... = exactly zero. "
            "This term was described in OpticsConfigV4 as 'the only term that "
            "tracks the surface normal directly'.",
            "facing = saturate(dot(N, V)) = 0, so fresnel = pow(1, 5) = 1 -- "
            "saturated everywhere, which is what the flat fresnel view shows.",
        ],
        "explainsGate005":
            "GATE-005 recorded that the refraction-offset debug view moves at "
            "most 2 of 255 levels while the same change moved 34.9% of beauty "
            "pixels, and treated that view as unsound. The audit gives the "
            "mechanism: projectedNormalOffset is identically zero, so that "
            "view was reporting a real zero rather than failing to report. "
            "The anomaly is explained, not merely reproduced."
            if affected else None,
        "notFixedHere": "§三 forbids repair during the audit. The finding is "
                        "carried into the O4 attribution and makes §七.E "
                        "eligible for consideration -- it does not select it.",
    }
    Path(opts["out"]).parent.mkdir(parents=True, exist_ok=True)
    Path(opts["out"]).write_text(json.dumps(doc, indent=1))

    print(f"unpack sites: {doc['staticEvidence']['unpackSiteCount']} "
          f"(branch: {unpack_branch})")
    print(f"alias sites: {doc['staticEvidence']['aliasSiteCount']}, "
          f"in branches with no unpack: "
          f"{doc['staticEvidence']['aliasSitesInBranchesWithNoUnpack']}")
    for q, pr in probes.items():
        v = pr["views"]
        print(f"  {q}: normals range {v.get('normals', {}).get('rangeRGB')} "
              f"| fresnel range {v.get('fresnel', {}).get('rangeRGB')} "
              f"| zones range {v.get('optical-zones', {}).get('rangeRGB')}")
    print(f"VERDICT: {doc['verdict']}")
    print(f"-> {opts['out']}")
    return 0 if measurable else 1


if __name__ == "__main__":
    sys.exit(main())
