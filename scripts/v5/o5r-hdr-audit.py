#!/usr/bin/env python3
"""O5R §十 -- decode the PRODUCT HDR and audit its radiance.

This runs BEFORE the code change it authorises. §十 makes the code conditional
on what is in the asset:

    no NaN / Inf  ->  Target-source Beauty samples the source HDR unclamped
    any NaN / Inf ->  stop, report SOURCE ASSET NON-FINITE, invent no new clamp

So the decode has to be the real one. The bytes of
`public/hdri/studio_small_03_1k.hdr` are parsed here -- header, RLE, RGBE --
rather than asking three's loader what it thinks, because the loader is one of
the things being audited.

Two decodes are reported, because two different numbers matter:

  FILE     the RGBE shared-exponent value, byte * 2^(e-128) / 255. This is the
           radiance the asset encodes.
  RUNTIME  what three's HDRLoader actually puts in the texture. It defaults to
           HalfFloatType and its RGBEByteToRGBHalf does
           `Math.min(value, 65504)` before toHalfFloat -- so the runtime texture
           is finite BY CONSTRUCTION, whatever the file holds. That matters for
           the removal decision and is verified here against the vendored
           loader source rather than assumed.

Output: qa-v5/optics-o5r/hdr-radiance-audit.json
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent.parent
ASSET = REPO / "public/hdri/studio_small_03_1k.hdr"
LOADER = REPO / "node_modules/three/examples/jsm/loaders/HDRLoader.js"
OUT = REPO / "qa-v5/optics-o5r/hdr-radiance-audit.json"

# The deviation under review. Recorded so the audit reports the fraction the
# old guard was suppressing, not just the distribution in the abstract.
OLD_CEILING = 16.0
HALF_MAX = 65504.0

# Rec.709 luminance, the same weights every O5 instrument uses.
LUMA = np.array([0.2126, 0.7152, 0.0722], np.float64)


def read_header(raw: bytes):
    """Parse a Radiance header. Returns (width, height, data_offset, lines)."""
    if not raw.startswith(b"#?"):
        raise SystemExit("not a Radiance file: missing #? magic")
    i = raw.index(b"\n") + 1
    lines = [raw[: i - 1].decode("ascii", "replace")]
    fmt = None
    while True:
        j = raw.index(b"\n", i)
        line = raw[i:j].decode("ascii", "replace")
        i = j + 1
        if line == "":
            break
        lines.append(line)
        if line.startswith("FORMAT="):
            fmt = line.split("=", 1)[1]
    j = raw.index(b"\n", i)
    res = raw[i:j].decode("ascii", "replace")
    i = j + 1
    lines.append(res)
    m = re.fullmatch(r"-Y (\d+) \+X (\d+)", res)
    if not m:
        raise SystemExit(f"unsupported resolution line: {res!r}")
    if fmt != "32-bit_rle_rgbe":
        raise SystemExit(f"unsupported FORMAT: {fmt!r}")
    return int(m.group(2)), int(m.group(1)), i, lines


def read_rle(raw: bytes, off: int, w: int, h: int) -> np.ndarray:
    """Adaptive-RLE RGBE scanlines -> uint8 [h, w, 4]."""
    out = np.empty((h, w, 4), np.uint8)
    p = off
    for y in range(h):
        if p + 4 > len(raw):
            raise SystemExit(f"truncated at scanline {y}")
        r, g, b0, b1 = raw[p], raw[p + 1], raw[p + 2], raw[p + 3]
        if not (r == 2 and g == 2 and ((b0 << 8) | b1) == w and 8 <= w <= 0x7FFF):
            # Flat (non-RLE) scanline: w consecutive RGBE quadruples.
            flat = np.frombuffer(raw, np.uint8, count=w * 4, offset=p)
            out[y] = flat.reshape(w, 4)
            p += w * 4
            continue
        p += 4
        for c in range(4):
            x = 0
            while x < w:
                n = raw[p]
                p += 1
                if n > 128:                       # run
                    out[y, x:x + (n - 128), c] = raw[p]
                    x += n - 128
                    p += 1
                else:                             # literal
                    out[y, x:x + n, c] = np.frombuffer(
                        raw, np.uint8, count=n, offset=p)
                    x += n
                    p += n
            if x != w:
                raise SystemExit(f"scanline {y} channel {c} overran: {x} != {w}")
    return out


def to_float(rgbe: np.ndarray) -> np.ndarray:
    """three's RGBEByteToRGBFloat, exactly: byte * 2^(e-128) / 255."""
    e = rgbe[..., 3].astype(np.int32)
    scale = np.where(e == 0, 0.0, np.ldexp(1.0, e - 128) / 255.0)
    return rgbe[..., :3].astype(np.float64) * scale[..., None]


def loader_clamps_to_half() -> dict:
    """Verify three's half-float decode clamps, from the vendored source."""
    if not LOADER.exists():
        return {"verified": False, "why": "HDRLoader.js not present"}
    src = LOADER.read_text()
    half_default = bool(re.search(r"this\.type\s*=\s*HalfFloatType", src))
    clamp = re.findall(r"Math\.min\(\s*sourceArray\[[^\]]+\]\s*\*\s*scale,\s*"
                       r"(\d+)\s*\)", src)
    return {
        "verified": bool(half_default and len(clamp) == 3
                         and set(clamp) == {"65504"}),
        "defaultTypeIsHalfFloat": half_default,
        "clampSites": len(clamp),
        "clampValue": clamp[0] if clamp else None,
        "why": "three's RGBEByteToRGBHalf applies Math.min(v, 65504) on every "
               "colour channel before toHalfFloat, and HDRLoader defaults to "
               "HalfFloatType. The texture our shader samples is therefore "
               "finite by construction -- no NaN, no Inf -- whatever the file "
               "encodes. Read out of the vendored loader, not assumed.",
    }


def pct(a: np.ndarray, q: float) -> float:
    return round(float(np.percentile(a, q)), 6)


def main() -> int:
    raw = ASSET.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    w, h, off, header = read_header(raw)
    rgbe = read_rle(raw, off, w, h)
    rgb = to_float(rgbe)

    n_tex = w * h
    n_ch = n_tex * 3
    finite_ch = np.isfinite(rgb)
    nan_ch = np.isnan(rgb)
    inf_ch = np.isinf(rgb)
    # A texel counts as non-finite if ANY of its channels is.
    tex_nonfinite = (~finite_ch).any(axis=2)

    lum = rgb @ LUMA
    ch = rgb.reshape(-1)

    # The runtime path: half-float, clamped at 65504 by the loader itself.
    clamped = rgb > HALF_MAX

    over_old = rgb > OLD_CEILING
    lum_over_old = lum > OLD_CEILING

    doc = {
        "what": "O5R §十 -- radiance audit of the product HDR, decoded from "
                "its own bytes. §十 makes the source-environment code change "
                "conditional on this file's finiteness, so the decode is done "
                "here rather than delegated to the loader under review.",
        "asset": str(ASSET.relative_to(REPO)),
        "sha256": sha,
        "provenanceSha256Matches": sha == (
            "29267a4aa8c10de26cae758e4e3c4daadde88673798666ad657724bab7224a35"),
        "bytes": len(raw),
        "header": header,
        "width": w, "height": h,
        "texels": n_tex,
        "colourChannels": n_ch,
        "decode": "three's RGBEByteToRGBFloat: byte * 2^(exponent - 128) / 255, "
                  "with exponent 0 decoding to exactly 0. Transcribed from the "
                  "vendored loader.",
        "percentileConvention": "percentiles are over the flattened set of "
                                "COLOUR CHANNEL values (3 per texel), not over "
                                "per-texel luminance; the luminance "
                                "distribution is reported separately. The "
                                "channel convention is the binding one because "
                                "the clamp under review clamped .rgb "
                                "per-channel.",

        # ---- the four counts §十 asks for, per channel and per texel --------
        "finiteChannels": int(finite_ch.sum()),
        "nanChannels": int(nan_ch.sum()),
        "infChannels": int(inf_ch.sum()),
        "nonFiniteTexels": int(tex_nonfinite.sum()),
        "allFinite": bool(finite_ch.all()),

        "maxRadiance": round(float(rgb.max()), 4),
        "maxRadianceChannel": ["R", "G", "B"][int(
            np.unravel_index(int(rgb.argmax()), rgb.shape)[2])],
        "minRadiance": round(float(rgb.min()), 8),
        "meanRadiance": round(float(rgb.mean()), 6),
        "channelPercentiles": {
            "p50": pct(ch, 50), "p90": pct(ch, 90), "p99": pct(ch, 99),
            "p99.9": pct(ch, 99.9), "p99.99": pct(ch, 99.99),
            "p100": round(float(ch.max()), 4),
        },
        "luminance": {
            "max": round(float(lum.max()), 4),
            "mean": round(float(lum.mean()), 6),
            "p99": pct(lum, 99), "p99.9": pct(lum, 99.9),
            "p99.99": pct(lum, 99.99),
        },

        # ---- what the runtime actually stores -------------------------------
        "runtimeTexture": {
            "type": "HalfFloatType",
            "loaderClampsAt": HALF_MAX,
            "channelsAboveHalfMax": int(clamped.sum()),
            "loaderClampVerified": loader_clamps_to_half(),
            "consequence": "the sampled environment is finite whatever this "
                           "file holds, and the Target -- which loads the same "
                           "asset through the same three RGBE half-float path "
                           "-- gets exactly the same bound. Removing our own "
                           "ceiling does not expose the shader to a "
                           "non-finite sample.",
        },

        # ---- the deviation under review -------------------------------------
        "oldCeiling": {
            "value": OLD_CEILING,
            "channelsAbove": int(over_old.sum()),
            "channelFractionAbove": round(float(over_old.mean()), 6),
            "texelsWithAnyChannelAbove": int(over_old.any(axis=2).sum()),
            "luminanceFractionAbove": round(float(lum_over_old.mean()), 6),
            "maxTimesCeiling": round(float(rgb.max() / OLD_CEILING), 2),
            "binds": bool(over_old.any()),
            "note": "corroborates the O5 disclosure. The guard is not inert: "
                    "wherever a card reflects one of these texels our "
                    "highlight is dimmer than the Target's, and the brightest "
                    "texel is suppressed by more than two orders of magnitude.",
        },

        # ---- reconciliation with the O5 disclosure --------------------------
        # O5's architecture record reported the brightest texel as 3568.0 and
        # this audit reads 3581.99. The difference is not noise and is not a
        # correction of a measurement error -- it is a decode-formula
        # difference, and it resolves exactly:
        #
        #   3581.9922 * 255/256 = 3568.00004
        #
        # The older RGBELoader scale is 2^(e-128-8) = 2^(e-128)/256; the
        # HDRLoader vendored in this repo uses 2^(e-128)/255. This audit
        # transcribes the VENDORED formula, so 3581.99 is the number that
        # describes the texture our shader actually samples. Both readings
        # agree on everything the decision turns on: finite, ~1% of texels
        # above 16, brightest texel more than two hundred times the ceiling.
        "reconciliationWithO5": {
            "o5MaxRadiance": 3568.0,
            "thisMaxRadiance": round(float(rgb.max()), 4),
            "ratio": round(float(rgb.max()) / 3568.0, 8),
            "explanation": "255/256 -- the older RGBELoader scale is "
                           "2^(e-128)/256, the vendored HDRLoader uses "
                           "2^(e-128)/255. This audit follows the vendored "
                           "loader, so it describes the texture the shader "
                           "samples. Neither reading changes the decision.",
            "o5TexelFractionAboveCeiling": 0.009809,
            "thisTexelFractionAboveCeiling": round(
                float(over_old.any(axis=2).mean()), 6),
        },

        "verdict": None,
        "authorisesUnclamp": None,
    }

    if doc["allFinite"]:
        doc["verdict"] = "SOURCE ASSET FINITE"
        doc["authorisesUnclamp"] = True
        doc["verdictDetail"] = (
            f"{n_ch} colour channels decoded, 0 NaN, 0 Inf. §十's condition is "
            "met: the target-source Beauty path samples the source HDR without "
            "a ceiling. No replacement clamp is introduced.")
    else:
        doc["verdict"] = "SOURCE ASSET NON-FINITE"
        doc["authorisesUnclamp"] = False
        doc["verdictDetail"] = (
            f"{int(nan_ch.sum())} NaN and {int(inf_ch.sum())} Inf channels. "
            "§十 says stop and invent no new numerical clamp.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1))
    print(f"{w}x{h}  {n_tex} texels  sha {sha[:12]}")
    print(f"  NaN {int(nan_ch.sum())}  Inf {int(inf_ch.sum())}  "
          f"max {doc['maxRadiance']}")
    print(f"  p99 {doc['channelPercentiles']['p99']}  "
          f"p99.9 {doc['channelPercentiles']['p99.9']}  "
          f"p99.99 {doc['channelPercentiles']['p99.99']}")
    print(f"  above old ceiling {OLD_CEILING}: "
          f"{doc['oldCeiling']['channelFractionAbove'] * 100:.4f}% of channels")
    print(f"  {doc['verdict']}  -> {OUT}")
    return 0 if doc["authorisesUnclamp"] else 1


if __name__ == "__main__":
    sys.exit(main())
