#!/usr/bin/env python3
"""Generate the three O5R calibration assets, locally owned.

The O2 shared-media set is reused unchanged for everything it already covers.
Three things it does not carry are added here, because two of the repaired
instruments cannot be built without them:

  calib-landmarks  §六 asks for "several uniquely identifiable landmarks, not
                   one symmetric edge". Ten bright discs on a mid-grey ground,
                   at irregular positions and in four different radii, so each
                   one is identified by BOTH where it is and how big it is --
                   and so the layout has no mirror symmetry in either axis to
                   pair a landmark with its own reflection.

  rgb-micro        §七's "rgb micro-pattern". Six horizontal bands of vertical
                   R/G/B stripes at pitches 8, 12, 16, 24, 32, 48 px, so the
                   chroma high-frequency measurement has a range of spatial
                   frequencies rather than one, and does not depend on the
                   card happening to be a particular size on screen.

  detail-chart     §七's "deterministic texture-detail chart". Five bands of
                   vertical black/white bars at pitches 4, 6, 8, 12, 16 px and
                   one band of HORIZONTAL bars at pitch 8, which makes the
                   chart anisotropy-sensitive: refraction that smears one axis
                   more than the other shows as a difference between the last
                   band and the pitch-8 vertical band.

Encode, container and HLS remux are the O2 recipe verbatim -- 1200x900 (the
Target's own video size, so the cover-fit math sees identical inputs), BT.709
limited range tagged end to end, CRF 12, static content, and the elementary
stream inside the mp4 asserted byte-identical to the one inside the HLS
segments. Nothing here is Target media.

Landmark positions are chosen inside nx in [0.18, 0.82] and ny in [0.08, 0.92]
so that they survive clip 2's frozen product crop as well as the degenerate
cover the other two clips get: the plane is 4:3 and so is the source, so clips
0 and 1 show the whole frame while clip 2 shows [0.146..0.854] x [0.031..0.974].

Usage: o5r-gen-media.py --out=<dir>
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

W, H, DUR, FPS = 1200, 900, 8, 30
GROUND, DISC = 90, 245          # calib-landmarks levels
LO, HI = 25, 230                # rgb-micro off/on levels

# (nx, ny, radiusPx). Irregular on purpose: no pair maps onto another under
# x -> 1-x or y -> 1-y, so a landmark can never be confused with a mirror of
# itself, and the radius gives every disc a second identifying feature that
# survives refraction.
DISCS = [
    (0.230, 0.140, 44),
    (0.520, 0.100, 30),
    (0.780, 0.190, 38),
    (0.195, 0.455, 26),
    (0.430, 0.545, 44),
    (0.700, 0.400, 30),
    (0.815, 0.640, 26),
    (0.245, 0.775, 38),
    (0.545, 0.905, 26),
    (0.760, 0.845, 44),
]

RGB_PITCHES = [8, 12, 16, 24, 32, 48]
DETAIL_BANDS = [("v", 4), ("v", 6), ("v", 8), ("v", 12), ("v", 16), ("h", 8)]


def discs_expr() -> str:
    """Nested ffmpeg geq: DISC inside any circle, GROUND elsewhere."""
    e = str(GROUND)
    for nx, ny, r in DISCS:
        cx, cy = round(nx * W), round(ny * H)
        e = f"if(lt(hypot(X-{cx},Y-{cy}),{r}),{DISC},{e})"
    return e


def bands_expr(bands, body) -> str:
    """Nested geq over equal-height horizontal bands; body(i) per band."""
    n = len(bands)
    bh = H // n
    e = body(n - 1)
    for i in range(n - 2, -1, -1):
        e = f"if(lt(Y,{(i + 1) * bh}),{body(i)},{e})"
    return e


def rgb_micro_expr(channel: int) -> str:
    def body(i):
        p = RGB_PITCHES[i]
        return f"if(eq(mod(floor(X/{p}),3),{channel}),{HI},{LO})"
    return bands_expr(RGB_PITCHES, body)


def detail_expr() -> str:
    def body(i):
        axis, p = DETAIL_BANDS[i]
        v = "X" if axis == "v" else "Y"
        return f"if(mod(floor({v}/{p}),2),255,0)"
    return bands_expr(DETAIL_BANDS, body)


def geq(r, g, b):
    return f"geq=r='{r}':g='{g}':b='{b}'"


def landmarks_calib():
    lm = {}
    for i, (nx, ny, _) in enumerate(DISCS):
        lm[f"disc{i}"] = (nx, ny, (DISC, DISC, DISC))
    # A ground sample far from every disc, to prove the background level too.
    lm["ground"] = (0.500, 0.290, (GROUND, GROUND, GROUND))
    return lm


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:])
    out = Path(args["out"])
    out.mkdir(parents=True, exist_ok=True)

    d = discs_expr()
    assets = [
        ("calib-landmarks", geq(d, d, d), landmarks_calib(),
         "ten bright discs on a mid-grey ground, four radii, no mirror "
         "symmetry in either axis"),
        ("rgb-micro",
         geq(rgb_micro_expr(0), rgb_micro_expr(1), rgb_micro_expr(2)),
         # Landmarks sit in the coarsest band (pitch 48, Y in [750,900)), the
         # only place where a 16x16 region mean is over ONE stripe rather than
         # an average of several -- so the check reads a colour, not a blur.
         {"microR": (0.500, 0.9167, (HI, LO, LO)),
          "microG": (0.540, 0.9167, (LO, HI, LO)),
          "microB": (0.580, 0.9167, (LO, LO, HI))},
         "six bands of vertical R/G/B stripes at pitches "
         + "/".join(map(str, RGB_PITCHES)) + " px"),
        ("detail-chart", geq(detail_expr(), detail_expr(), detail_expr()),
         # Coarsest vertical band is pitch 16 at Y in [600,750); the last band
         # is horizontal pitch 8. Landmarks are taken in the pitch-16 band,
         # on bar centres so that a 16x16 region lands inside exactly one bar:
         # bar 39 spans X 624..639 (white), bar 38 spans X 608..623 (black).
         {"detailWhite": (0.526667, 0.7222, (255, 255, 255)),
          "detailBlack": (0.513333, 0.7222, (0, 0, 0))},
         "five vertical bar bands at pitches 4/6/8/12/16 px plus one "
         "horizontal band at pitch 8, so the chart is anisotropy-sensitive"),
    ]

    manifest = {
        "what": "O5R calibration media, generated locally by this script. "
                "Nothing here is Target media. Same 1200x900, same encode and "
                "same HLS remux discipline as the O2 shared-media harness, so "
                "these assets travel through the identical routing.",
        "encode": {"codec": "libx264", "profile": "high", "level": "4.2",
                   "pixFmt": "yuv420p", "crf": 12, "fps": FPS,
                   "durationS": DUR,
                   "colour": "bt709 primaries/trc/matrix, limited range, "
                             "tagged end to end"},
        "landmarkGeometry": {
            "discs": [{"nx": nx, "ny": ny, "radiusPx": r,
                       "sourceX": round(nx * W), "sourceY": round(ny * H)}
                      for nx, ny, r in DISCS],
            "level": {"ground": GROUND, "disc": DISC},
            "insideClip2Crop": all(0.18 <= nx <= 0.82 and 0.08 <= ny <= 0.92
                                   for nx, ny, _ in DISCS),
            "why": "positions are irregular and the radii vary, so a landmark "
                   "is identified by position AND area and no disc is the "
                   "mirror of another. All ten sit inside clip 2's frozen "
                   "product crop as well as the full-frame cover the other "
                   "clips get.",
        },
        "assets": [],
    }

    for name, filt, landmarks, desc in assets:
        adir = out / name
        adir.mkdir(exist_ok=True)
        mp4 = adir / f"{name}.mp4"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}:d={DUR}",
             "-vf", filt + ",scale=out_color_matrix=bt709:out_range=tv,"
                           "format=yuv420p",
             "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.2",
             "-crf", "12", "-g", str(FPS), "-movflags", "+faststart",
             "-colorspace", "bt709", "-color_primaries", "bt709",
             "-color_trc", "bt709", "-color_range", "tv",
             "-an", str(mp4)])
        hls = adir / "hls"
        if hls.exists():
            shutil.rmtree(hls)
        hls.mkdir()
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-i", str(mp4), "-c", "copy", "-f", "hls",
             "-hls_time", "4", "-hls_playlist_type", "vod",
             "-hls_segment_type", "fmp4",
             "-hls_fmp4_init_filename", "init.mp4",
             "-hls_segment_filename", str(hls / "seg%d.m4s"),
             str(hls / "media.m3u8")])
        cat = adir / "_cat.mp4"
        with cat.open("wb") as f:
            f.write((hls / "init.mp4").read_bytes())
            for seg in sorted(hls.glob("seg*.m4s"),
                              key=lambda p: int(p.stem[3:])):
                f.write(seg.read_bytes())
        es_mp4 = elementary_sha(mp4, adir, "a")
        es_hls = elementary_sha(cat, adir, "b")
        cat.unlink()
        if es_mp4 != es_hls:
            raise SystemExit(f"{name}: elementary streams differ")
        manifest["assets"].append({
            "name": name, "width": W, "height": H, "durationS": DUR,
            "scored": True, "description": desc,
            "mp4": {"file": str(mp4.relative_to(out)), "sha256": sha(mp4),
                    "bytes": mp4.stat().st_size},
            "hls": {"playlist": str((hls / "media.m3u8").relative_to(out)),
                    "playlistSha256": sha(hls / "media.m3u8"),
                    "init": {"sha256": sha(hls / "init.mp4")},
                    "segments": [{"file": p.name, "sha256": sha(p)}
                                 for p in sorted(hls.glob("seg*.m4s"),
                                                 key=lambda p: int(p.stem[3:]))]},
            "elementaryStreamSha256": es_mp4,
            "elementaryStreamIdenticalMp4VsHls": True,
            "landmarks": {k: {"nx": v[0], "ny": v[1], "rgb": v[2]}
                          for k, v in landmarks.items()},
        })
        print(f"{name}: mp4 {mp4.stat().st_size} B, es {es_mp4[:12]}")

    (out / "media-manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{len(assets)} assets -> {out}")
    return 0


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:6])}... failed: {r.stderr[-2000:]}")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def elementary_sha(src: Path, workdir: Path, tag: str) -> str:
    raw = workdir / f"{tag}.264"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(src), "-map", "0:v:0", "-c", "copy", "-f", "h264", str(raw)])
    h = sha(raw)
    raw.unlink()
    return h


if __name__ == "__main__":
    sys.exit(main())
