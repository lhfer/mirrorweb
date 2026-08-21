#!/usr/bin/env python3
"""Generate the O2 deterministic test media, locally owned.

Eight synthetic 1200x900 clips (the Target's own video dimensions, so the
cover-fit math sees identical inputs on both pages), H.264 High profile
yuv420p at CRF 12, 8 s static content -- static because both pages are
frozen at one media time and a static pattern makes ANY frozen time the
same proof. Each asset is also remuxed (-c copy, no re-encode) into a
CMAF/fMP4 HLS rendition for the Target lane: the H.264 elementary stream
inside the mp4 and inside the HLS segments is byte-identical, and the
script proves it by extracting both elementary streams and comparing
SHA-256.

Per asset the manifest records: mp4 SHA, per-segment SHAs, elementary
stream SHA (mp4 == hls asserted), dimensions, duration, and LANDMARKS --
expected RGB at named normalised positions -- for decoded-frame
verification on both pages.

Usage: o2-gen-media.py --out=<dir>
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

W, H, DUR, FPS = 1200, 900, 8, 30  # scored assets: the Target's own video size

# Each asset: (name, lavfi/geq recipe builder, landmarks)
# Landmarks are (nx, ny) -> approximate expected (r, g, b); the verifier
# allows a tolerance for chroma subsampling and codec quantisation.


def geq(r, g, b):
    return f"geq=r='{r}':g='{g}':b='{b}'"


ASSETS = [
    ("grayscale-step",
     geq("if(lt(X,600),64,192)", "if(lt(X,600),64,192)", "if(lt(X,600),64,192)"),
     {"left": (0.25, 0.5, (64, 64, 64)), "right": (0.75, 0.5, (192, 192, 192))}),
    ("bw-split",
     geq("if(lt(X,600),0,255)", "if(lt(X,600),0,255)", "if(lt(X,600),0,255)"),
     {"left": (0.25, 0.5, (0, 0, 0)), "right": (0.75, 0.5, (255, 255, 255))}),
    ("rgb-bars",
     geq("if(lt(X,300),220,if(lt(X,600),0,if(lt(X,900),0,220)))",
         "if(lt(X,300),0,if(lt(X,600),220,if(lt(X,900),0,220)))",
         "if(lt(X,300),0,if(lt(X,600),0,if(lt(X,900),220,220)))"),
     {"r": (0.125, 0.5, (220, 0, 0)), "g": (0.375, 0.5, (0, 220, 0)),
      "b": (0.625, 0.5, (0, 0, 220)), "w": (0.875, 0.5, (220, 220, 220))}),
    ("hf-checker",
     geq("if(mod(floor(X/8)+floor(Y/8),2),255,0)",
         "if(mod(floor(X/8)+floor(Y/8),2),255,0)",
         "if(mod(floor(X/8)+floor(Y/8),2),255,0)"),
     {"mean": (0.5, 0.5, (127, 127, 127))}),  # verified as a REGION mean
    ("dark-highlight",
     geq("if(lt(hypot(X-900,Y-250),50),255,16+Y*32/900)",
         "if(lt(hypot(X-900,Y-250),50),255,16+Y*32/900)",
         "if(lt(hypot(X-900,Y-250),50),255,20+Y*40/900)"),
     {"dark": (0.25, 0.75, (43, 43, 53)), "highlight": (0.75, 0.278, (255, 255, 255))}),
    ("bright-lowsat",
     geq("205+15*sin(X/200)", "200+15*sin(X/200+1)", "195+15*sin(X/200+2)"),
     {"mid": (0.5, 0.5, (207, 189, 181))}),  # sin phases at X=600
    ("warm-skin",
     geq("200+20*Y/900", "150+20*Y/900", "120+15*Y/900"),
     {"mid": (0.5, 0.5, (210, 160, 128))}),
    ("cool-blue",
     geq("40+20*Y/900", "80+20*Y/900", "140+40*Y/900"),
     {"mid": (0.5, 0.5, (50, 90, 160))}),
    # NOT a scored asset: a 16:9 control that forces the cover-fit law to do
    # real work (4:3 sources make cover degenerate scale=1/offset=0). The
    # vertical edge at source nx=0.5 must land at card nx=0.5 after the
    # symmetric crop on BOTH pages.
    # Edge deliberately OFF-centre at source nx=0.375: the 16:9 -> 4:3
    # symmetric cover crop [0.125..0.875] maps it to card nx=1/3, while an
    # uncropped (wrong) fit would leave it at 0.375 -- a ~4% of card width
    # displacement that a screenshot measurement resolves.
    ("cover-control",
     geq("if(lt(X,600),40,215)", "if(lt(X,600),40,215)", "if(lt(X,600),40,215)"),
     {"left": (0.2, 0.5, (40, 40, 40)), "right": (0.7, 0.5, (215, 215, 215))},
     (1600, 900)),
]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:6])}... failed: {r.stderr[-2000:]}")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def elementary_sha(src: Path, workdir: Path, tag: str) -> str:
    """SHA-256 of the H.264 elementary stream (annex-b) inside a container
    or a concatenated init+segments stream."""
    raw = workdir / f"{tag}.264"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(src), "-map", "0:v:0", "-c", "copy", "-f", "h264", str(raw)])
    h = sha(raw)
    raw.unlink()
    return h


def main() -> int:
    out = Path(dict(a[2:].split("=", 1) for a in sys.argv[1:])["out"])
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"what": "O2 deterministic test media, generated locally by "
                        "this script; nothing here is Target media. Static "
                        "synthetic patterns at the Target's own 1200x900.",
                "encode": {"codec": "libx264", "profile": "high",
                           "level": "4.2", "pixFmt": "yuv420p", "crf": 12,
                           "fps": FPS, "durationS": DUR},
                "assets": []}
    for entry in ASSETS:
        name, filt, landmarks = entry[0], entry[1], entry[2]
        aw, ah = entry[3] if len(entry) > 3 else (W, H)
        adir = out / name
        adir.mkdir(exist_ok=True)
        mp4 = adir / f"{name}.mp4"
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", f"color=c=black:s={aw}x{ah}:r={FPS}:d={DUR}",
             # Explicit BT.709 limited-range tagging end to end: swscale
             # defaults to BT.601 untagged, and the browser decodes
             # untagged HD as BT.709 -- that mismatch skewed landmark
             # readbacks by up to 35/255 in the first prototype.
             "-vf", filt + ",scale=out_color_matrix=bt709:out_range=tv,"
                           "format=yuv420p",
             "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.2",
             "-crf", "12", "-g", str(FPS), "-movflags", "+faststart",
             "-colorspace", "bt709", "-color_primaries", "bt709",
             "-color_trc", "bt709", "-color_range", "tv",
             "-an", str(mp4)])
        # CMAF/fMP4 HLS remux, -c copy: identical elementary stream.
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
        # Elementary-stream proof: mp4 vs concatenated init+segments.
        cat = adir / "_cat.mp4"
        with cat.open("wb") as f:
            f.write((hls / "init.mp4").read_bytes())
            for seg in sorted(hls.glob("seg*.m4s"),
                              key=lambda p: int(p.stem[3:])):
                f.write(seg.read_bytes())
        es_mp4 = elementary_sha(mp4, adir, "a")
        es_hls = elementary_sha(cat, adir, "b")
        cat.unlink()
        assert es_mp4 == es_hls, f"{name}: elementary streams differ"
        manifest["assets"].append({
            "name": name, "width": aw, "height": ah, "durationS": DUR,
            "scored": name != "cover-control",
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
    print(f"{len(ASSETS)} assets -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
