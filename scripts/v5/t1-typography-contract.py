#!/usr/bin/env python3
"""Build the Target typography contract, and check ours against it.

Both sides are read by the SAME instrument (`t1-target-typography.mjs`), one
pointed at the Target and one at our page, at the same seven viewports. A
contract compared with a differently-written reader would be comparing two
readers as much as two pages.

Every value here is measured. Nothing is declared, and where the Target could
not be read the property is recorded as NOT FOUND rather than filled in.
"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

VPS = ["1440x900", "1920x1080", "390x844", "844x390", "700x700", "667x375", "780x470"]


def card_of(vp):
    """The first fully-formed card at this viewport."""
    for c in vp["cards"]:
        if any(ch.get("className") and "p-[" in ch["className"] for ch in c["children"]):
            return c
        if any(ch.get("className") and "se-content" in str(ch["className"]) for ch in c["children"]):
            return c
    return vp["cards"][0] if vp["cards"] else None


def pick(card, pred):
    for ch in card["children"]:
        if pred(ch):
            return ch
    return None


def has(cls):
    return lambda ch: bool(ch.get("className")) and cls in str(ch["className"])


SELECTORS = {
    # name: (target predicate, local predicate)
    "content":   (has("p-["),                 has("se-content")),
    "clip":      (has("overflow-hidden"),     has("se-clip")),
    "meta":      (has("font-mono"),           has("se-meta")),
    "metaLeft":  (has("gap-[2.8cqw]"),        has("se-meta-left")),
    "metaRight": (has("gap-[1.2cqw]"),        has("se-meta-right")),
    "dim":       (has("opacity-75"),          has("se-dim")),
    "dot":       (has("rounded-full"),        has("se-dot")),
    "rule":      (has("bg-white/55"),         has("se-rule")),
    "title":     (lambda ch: ch["tag"] == "h2", lambda ch: ch["tag"] == "h2"),
    "deckRow":   (has("mt-[3.5cqw]"),         has("se-deck-row")),
    "deck":      (lambda ch: ch["tag"] == "p", lambda ch: ch["tag"] == "p"),
}

# property -> (element, extractor(el, cardWidth), unit, tolerance)
PROPS = [
    ("cardPaddingCqw",       "content",   lambda e, w: e["padding"][0] / w * 100, "cqw",   0.02),
    ("cardTransformStyle",   "self",      lambda e, w: e["transformStyle"],       "",      None),
    ("cardBackfaceVisibility", "self",    lambda e, w: e["backfaceVisibility"],   "",      None),
    ("clipOverflow",         "clip",      lambda e, w: e["overflow"],             "",      None),
    ("metaFontSizeCqw",      "meta",      lambda e, w: e["fontSizePx"] / w * 100, "cqw",   0.005),
    ("metaLineHeight",       "meta",      lambda e, w: e["lineHeightPx"] / e["fontSizePx"], "x", 0.005),
    ("metaLetterSpacingEm",  "meta",      lambda e, w: e["letterSpacingPx"] / e["fontSizePx"], "em", 0.002),
    ("metaFontWeight",       "meta",      lambda e, w: int(e["fontWeight"]),      "",      0),
    ("metaTextTransform",    "meta",      lambda e, w: e["textTransform"],        "",      None),
    ("metaFontIsMono",       "meta",      lambda e, w: "Mono" in e["fontFamily"], "",      None),
    ("metaLeftGapCqw",       "metaLeft",  lambda e, w: float(e["gap"][:-2]) / w * 100, "cqw", 0.02),
    ("metaRightGapCqw",      "metaRight", lambda e, w: float(e["gap"][:-2]) / w * 100, "cqw", 0.02),
    ("metaRightOpacity",     "metaRight", lambda e, w: float(e["opacity"]),       "",      0.005),
    ("categoryOpacity",      "dim",       lambda e, w: float(e["opacity"]),       "",      0.005),
    ("dotSizeCqw",           "dot",       lambda e, w: e["widthPx"] / w * 100,    "cqw",   0.03),
    ("ruleHeightCqw",        "rule",      lambda e, w: e["heightPx"] / w * 100,   "cqw",   0.03),
    ("ruleMarginBottomCqw",  "rule",      lambda e, w: e["margin"][2] / w * 100,  "cqw",   0.02),
    ("titleFontSizeCqw",     "title",     lambda e, w: e["fontSizePx"] / w * 100, "cqw",   0.005),
    ("titleLineHeight",      "title",     lambda e, w: e["lineHeightPx"] / e["fontSizePx"], "x", 0.005),
    ("titleLetterSpacingEm", "title",     lambda e, w: e["letterSpacingPx"] / e["fontSizePx"], "em", 0.002),
    ("titleFontWeight",      "title",     lambda e, w: int(e["fontWeight"]),      "",      0),
    ("titleMaxWidthPct",     "title",     lambda e, w: e["maxWidth"],             "",      None),
    ("titleTextWrap",        "title",     lambda e, w: e["textWrap"],             "",      None),
    ("deckRowMarginTopCqw",  "deckRow",   lambda e, w: e["margin"][0] / w * 100,  "cqw",   0.02),
    ("deckFontSizeCqw",      "deck",      lambda e, w: e["fontSizePx"] / w * 100, "cqw",   0.005),
    ("deckLineHeight",       "deck",      lambda e, w: e["lineHeightPx"] / e["fontSizePx"], "x", 0.005),
    ("deckLetterSpacingEm",  "deck",      lambda e, w: e["letterSpacingPx"] / e["fontSizePx"], "em", 0.002),
    ("deckFontWeight",       "deck",      lambda e, w: int(e["fontWeight"]),      "",      0),
    ("deckMaxWidthCqw",      "deck",      lambda e, w: float(e["maxWidth"][:-2]) / w * 100
                                             if str(e["maxWidth"]).endswith("px") else e["maxWidth"], "cqw", 0.03),
]


def measure(doc, side):
    out = {}
    for vp in doc["viewports"]:
        card = card_of(vp)
        if card is None:
            continue
        w = card["container"]["widthPx"]
        els = {"self": {"transformStyle": card["transformStyle"],
                        "backfaceVisibility": card["backfaceVisibility"]}}
        for name, (tpred, lpred) in SELECTORS.items():
            els[name] = pick(card, lpred if side == "local" else tpred)
        row = {"cardBox": [w, card["container"]["heightPx"]],
               "objectScale": card["objectScale"],
               "containerType": card["container"].get("containerType"),
               "backfaceVisibility": card["backfaceVisibility"],
               "transformStyle": card["transformStyle"],
               "domOrderInBottomBlock": [e["tag"] + ":" + (str(e.get("className"))[:26] if e.get("className") else "-")
                                         for e in card["children"]
                                         if e["depth"] == 3 and e["tag"] in ("div", "h2")]}
        for prop, el, fn, unit, tol in PROPS:
            e = els.get(el)
            try:
                row[prop] = fn(e, w) if e else None
            except Exception:
                row[prop] = None
        title = els.get("title")
        H = card["container"]["heightPx"]
        if title and title.get("localBox"):
            b = title["localBox"]
            row["titleLocalBox"] = b
            row["titleBaselineFromBottomPct"] = round((H - (b[1] + b[3])) / H * 100, 3)
            row["titleLineCount"] = title.get("lineCount")
        out[vp["id"]] = row
    return out


def agree(a, b, tol):
    if a is None or b is None:
        return a == b
    if isinstance(a, str) or isinstance(b, str) or isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if tol is None:
        return a == b
    return abs(a - b) <= tol


def reported_block(T, L):
    """Measured on both sides, reported rather than gated.

    These depend on the card's TEXT -- our catalogue is not the Target's -- so
    an equality check here would be comparing two sets of words, not two type
    systems. The layout law that produces them is gated above.
    """
    return {
        "note": "text-dependent; reported for the visual gate, not asserted",
        "titleBaselineFromCardBottomPct": {
            v: {"target": T[v].get("titleBaselineFromBottomPct"),
                "ours": L[v].get("titleBaselineFromBottomPct")} for v in VPS if v in T and v in L},
        "titleLineCount": {
            v: {"target": T[v].get("titleLineCount"), "ours": L[v].get("titleLineCount")}
            for v in VPS if v in T and v in L},
        "titleLocalBox": {
            v: {"target": T[v].get("titleLocalBox"), "ours": L[v].get("titleLocalBox")}
            for v in VPS if v in T and v in L},
    }


FOOTER_PROPS = ["fontFamily", "fontSizePx", "fontWeight", "letterSpacingPx", "lineHeightPx",
                "textTransform", "color", "opacity"]


def footer_block(tdoc, ldoc):
    """The Target's footer type, and ours, element by element.

    Reported rather than gated: our footer carries our own wordmark and our own
    links, so a property-for-property equality check would be measuring a
    difference in content, not in typography.
    """
    def label_of(doc):
        for vp in doc["viewports"]:
            if vp["id"] != "1440x900":
                continue
            for ch in vp.get("footerTree", []):
                if ch["text"].upper().startswith("AN EXPERIMENT BY") and ch["tag"] in ("span", "a"):
                    if "Mono" in ch["fontFamily"] or ch["tag"] == "span":
                        return ch
        return None
    t, l = label_of(tdoc), label_of(ldoc)
    return {
        "note": "the 'AN EXPERIMENT BY' caption is the one footer element whose type is "
                "comparable; the wordmark is an image on the Target and type on ours.",
        "targetCaption": {k: t[k] for k in FOOTER_PROPS} if t else "NOT FOUND",
        "ourCaption": {k: l[k] for k in FOOTER_PROPS} if l else "NOT FOUND",
        "targetTree": [{"cls": c["className"], "text": c["text"][:40], "size": c["fontSizePx"],
                        "weight": c["fontWeight"], "ls": c["letterSpacingPx"],
                        "mono": "Mono" in c["fontFamily"]}
                       for c in (tdoc["viewports"][0].get("footerTree") or [])],
        "ourTree": [{"cls": c["className"], "text": c["text"][:40], "size": c["fontSizePx"],
                     "weight": c["fontWeight"], "ls": c["letterSpacingPx"],
                     "mono": "Mono" in c["fontFamily"]}
                    for c in (ldoc["viewports"][0].get("footerTree") or [])],
    }


if __name__ == "__main__":
    tdoc = json.loads(Path(sys.argv[1]).read_text())
    ldoc = json.loads(Path(sys.argv[2]).read_text())
    out = Path(sys.argv[3])
    T, L = measure(tdoc, "target"), measure(ldoc, "local")

    props = []
    for prop, el, fn, unit, tol in PROPS:
        tvals = [T[v][prop] for v in VPS if v in T]
        lvals = [L[v][prop] for v in VPS if v in L]
        numeric = all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in tvals if x is not None)
        const = (len(set(map(str, tvals))) == 1) if not numeric else (
            max(tvals) - min(tvals) <= (tol or 0) if all(v is not None for v in tvals) else False)
        matches = [agree(T[v][prop], L[v][prop], tol) for v in VPS if v in T and v in L]
        worst = None
        if numeric and all(isinstance(x, (int, float)) for x in lvals if x is not None):
            deltas = [abs(T[v][prop] - L[v][prop]) for v in VPS
                      if v in T and v in L and T[v][prop] is not None and L[v][prop] is not None]
            worst = round(max(deltas), 6) if deltas else None
        props.append({
            "property": prop, "element": el, "unit": unit,
            "targetValue": (round(sum(tvals) / len(tvals), 4) if numeric and None not in tvals
                            else tvals[0]),
            "targetPerViewport": {v: (round(T[v][prop], 5) if isinstance(T[v][prop], float) else T[v][prop])
                                  for v in VPS if v in T},
            "constantAcrossViewports": bool(const),
            "ourValue": (round(sum(lvals) / len(lvals), 4) if numeric and None not in lvals else
                         (lvals[0] if lvals else None)),
            "worstAbsDelta": worst, "tolerance": tol,
            "matchesAtEveryViewport": all(matches) and len(matches) == len(VPS),
            "status": "MATCH" if (all(matches) and len(matches) == len(VPS)) else
                      ("NOT FOUND IN TARGET" if all(v is None for v in tvals) else "DIFFERS"),
        })

    payload = {
        "instrument": "scripts/v5/t1-target-typography.mjs, one reader for both sides",
        "target": {"url": tdoc["target"], "capturedAtUtc": tdoc["capturedAt"]},
        "local": {"url": ldoc["target"], "capturedAtUtc": ldoc["capturedAt"]},
        "viewports": VPS,
        "container": {
            "law": "label element width = layout frame planeWidth, height = planeHeight, "
                   "CSS3D object scale = 1",
            "evidence": "at all seven viewports the Target's label element computed width "
                        "equals the card plane width and its matrix3d basis columns are unit "
                        "length, so its object scale is 1. Scheme A, not scheme B.",
            "targetBoxes": {v: T[v]["cardBox"] for v in VPS if v in T},
            "ourBoxes": {v: L[v]["cardBox"] for v in VPS if v in L},
            "boxesAgree": all(
                abs(T[v]["cardBox"][0] - L[v]["cardBox"][0]) < 1e-3
                and abs(T[v]["cardBox"][1] - L[v]["cardBox"][1]) < 1e-3
                for v in VPS if v in T and v in L),
            "targetObjectScale": {v: [round(x, 6) for x in T[v]["objectScale"]] for v in VPS if v in T},
            "ourObjectScale": {v: [round(x, 6) for x in L[v]["objectScale"]] for v in VPS if v in L},
            "containerType": {"target": T[VPS[0]]["containerType"], "ours": L[VPS[0]]["containerType"]},
            "backfaceVisibility": {"target": T[VPS[0]]["backfaceVisibility"],
                                   "ours": L[VPS[0]]["backfaceVisibility"]},
            "transformStyle": {"target": T[VPS[0]]["transformStyle"], "ours": L[VPS[0]]["transformStyle"]},
        },
        "domOrder": {"target": T[VPS[0]]["domOrderInBottomBlock"],
                     "ours": L[VPS[0]]["domOrderInBottomBlock"],
                     "note": "the Target's rule precedes the title; our previous markup had "
                             "title, rule, deck"},
        "footer": footer_block(tdoc, ldoc),
        "reported": reported_block(T, L),
        "properties": props,
        "notFound": [p["property"] for p in props if p["status"] == "NOT FOUND IN TARGET"],
        "matched": sum(1 for p in props if p["status"] == "MATCH"),
        "total": len(props),
    }
    payload["verdict"] = "PASS" if payload["matched"] == payload["total"] else "FAIL"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))
    print(f"typography contract {payload['verdict']}  {payload['matched']}/{payload['total']}")
    for p in props:
        if p["status"] != "MATCH":
            print(f"  {p['status']:<20} {p['property']:<24} target={p['targetValue']} ours={p['ourValue']} worst={p['worstAbsDelta']}")
