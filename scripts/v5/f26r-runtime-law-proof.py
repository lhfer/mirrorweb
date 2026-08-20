#!/usr/bin/env python3
"""
Proof that each portrait candidate actually RENDERS its own law.

F2.6 compared three candidates whose JSON differed and whose pixels did not.
`portraitLaw` reached `compositionScale` but not `viewZoom` or
`effectivePerspectivePx`, and the shipping mechanism is focal -- so the reported
scale followed the requested law while the camera used the default one. p0 and
p1 came out byte identical.

This checks the things that cannot be faked by a config read:

  * the PNG hashes differ between candidates
  * the projected card size differs
  * the scale derived from the LIVE camera projection matches each law's own
    analytic scale, not some other candidate's
  * requested / renderer / grid all report the same law

Usage: f26r-runtime-law-proof.py --dir=<capture root> --out=<json>
"""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path

REF_W = 1440.0
LAWS = {
    "p0": {"gainBase": 1.9468, "gainSlope": -0.31},
    "p1": {"gainBase": 1.87715, "gainSlope": 0.12204},
    "p2": {"gainBase": 1.87715, "gainSlope": 0.12204},
}
VPS = ["390x844", "360x800", "500x900", "1440x900"]


def analytic_scale(w, h, law):
    g = LAWS[law]
    if w < h:
        return (g["gainBase"] + g["gainSlope"] * (w / h - 0.5)) * w / REF_W
    return w / REF_W


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


if __name__ == "__main__":
    args = dict(a.split("=", 1) for a in sys.argv[1:])
    root = Path(args.get("--dir", "qa-v5/f26r/portrait-candidates"))
    out = Path(args.get("--out", "qa-v5/f26r/runtime-law-proof.json"))
    rows, checks = [], []
    per_vp_sha, per_vp_w = {}, {}
    for law in ("p0", "p1", "p2"):
        for vp in VPS:
            png = root / law / "local" / vp / "01-rest.png"
            js = png.with_suffix(".json")
            if not png.exists():
                rows.append({"law": law, "viewport": vp, "status": "MISSING"}); continue
            d = json.loads(js.read_text())
            st, v4 = d["state"], d.get("v4state", {})
            w, h = (int(x) for x in vp.split("x"))
            q = next((c for c in d["quads"] if c["i"] == 0 and c["j"] == 0), None)
            card_w = ((max(p[0] for p in q["quad"]) - min(p[0] for p in q["quad"])) * w) if q else None
            card_h = ((max(p[1] for p in q["quad"]) - min(p[1] for p in q["quad"])) * h) if q else None
            derived = v4.get("scaleDerivedFromActualCameraProjection")
            expect = analytic_scale(w, h, law)
            rows.append({
                "law": law, "viewport": vp, "png": str(png), "sha256": sha(png),
                "requestedPortraitLaw": v4.get("requestedPortraitLaw"),
                "rendererPortraitLaw": v4.get("rendererPortraitLaw"),
                "gridPortraitLaw": v4.get("gridPortraitLaw"),
                "effectiveFov": v4.get("effectiveFov"),
                "effectivePerspectivePx": v4.get("effectivePerspectivePx"),
                "reportedCompositionScale": v4.get("reportedCompositionScale"),
                "scaleDerivedFromActualCameraProjection": derived,
                "analyticScaleForThisLaw": round(expect, 8),
                "derivedMinusAnalytic": None if derived is None else round(derived - expect, 9),
                "cardProjectedWidthPx": None if card_w is None else round(card_w, 4),
                "cardProjectedHeightPx": None if card_h is None else round(card_h, 4),
                "runtimeTruthAssertions": v4.get("runtimeTruthAssertions"),
            })
            per_vp_sha.setdefault(vp, {})[law] = rows[-1]["sha256"]
            per_vp_w.setdefault(vp, {})[law] = card_w

    def add(name, ok, detail):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    for vp in VPS:
        s = per_vp_sha.get(vp, {})
        w, h = (int(x) for x in vp.split("x"))
        if "p0" not in s or "p1" not in s:
            continue
        if w < h:
            add(f"{vp} (portrait): p0 and p1 PNGs differ", s["p0"] != s["p1"],
                f"p0 {s['p0'][:16]}  p1 {s['p1'][:16]}")
        else:
            # Landscape does not use the portrait gain at all, and p0 and p1
            # share their vertical parameters, so identical output here is the
            # correct result -- and a useful control: it shows the difference
            # seen in portrait comes from the law and not from capture noise.
            add(f"{vp} (landscape control): p0 and p1 PNGs identical", s["p0"] == s["p1"],
                f"both {s['p0'][:16]} -- landscape ignores the portrait gain")
    pw = per_vp_w.get("390x844", {})
    if "p0" in pw and "p1" in pw:
        add("390x844: p0 and p1 projected card size differs",
            abs(pw["p0"] - pw["p1"]) > 0.5,
            f"p0 {pw['p0']:.3f} px, p1 {pw['p1']:.3f} px, delta {pw['p0']-pw['p1']:.3f}")
    for law in ("p0", "p1", "p2"):
        # 3.2e-5 is structural: the analytic scale is focal / perspectivePx,
        # which assumes an unpitched camera, while the live projection measures
        # along the real view axis, which CAMERA.y = 8 makes 1000.032 long.
        bad = [r for r in rows if r.get("law") == law and r.get("derivedMinusAnalytic") is not None
               and abs(r["derivedMinusAnalytic"]) > 1e-4]
        add(f"{law}: live camera scale matches its own law at every viewport", not bad,
            "max |derived - analytic| = " + str(max((abs(r["derivedMinusAnalytic"]) for r in rows
                if r.get("law") == law and r.get("derivedMinusAnalytic") is not None), default=None)))
    p1s = {r["viewport"]: r["scaleDerivedFromActualCameraProjection"] for r in rows if r.get("law") == "p1"}
    p2s = {r["viewport"]: r["scaleDerivedFromActualCameraProjection"] for r in rows if r.get("law") == "p2"}
    add("p2 camera scale equals p1's", all(abs(p1s[v] - p2s[v]) < 1e-9 for v in p1s if v in p2s),
        "p2 shares p1's scale law and differs only in vertical geometry")
    p1w = {r["viewport"]: r["cardProjectedHeightPx"] for r in rows if r.get("law") == "p1"}
    p2w = {r["viewport"]: r["cardProjectedHeightPx"] for r in rows if r.get("law") == "p2"}
    add("p2 vertical geometry differs from p1",
        any(abs(p1w[v] - p2w[v]) > 0.05 for v in p1w if v in p2w),
        "; ".join(f"{v}: {p1w[v]:.3f} vs {p2w[v]:.3f}" for v in p1w if v in p2w))
    add("portrait law propagated on every capture",
        all((r.get("runtimeTruthAssertions") or {}).get("portraitLawPropagated") for r in rows if "law" in r),
        "requested == renderer == grid")
    add("reported scale matches live camera projection on every capture (1e-4, camera pitch)",
        all((r.get("runtimeTruthAssertions") or {}).get("reportedScaleMatchesCameraProjection")
            for r in rows if "law" in r),
        "config-reported scale is the scale the camera actually uses")

    payload = {
        "defectBeingProvenFixed":
            "portraitLaw reached compositionScale but not viewZoom or "
            "effectivePerspectivePx; with the focal mechanism the camera used the "
            "default law, so p0 and p1 rendered byte identically while their JSON "
            "differed.",
        "cameraPitchTolerance": {
            "absolute": 1e-4,
            "why": "the analytic scale is focal/perspectivePx and assumes an unpitched "
                   "camera; the live projection measures along the real view axis, which "
                   "CAMERA.y = 8 makes 1000.032 long. A fixed 3.2e-5 relative difference.",
        },
        "verdict": "PASS" if all(c["pass"] for c in checks) else "FAIL",
        "checks": checks, "captures": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"runtime law proof: {payload['verdict']}")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['check']}  {c['detail']}")
