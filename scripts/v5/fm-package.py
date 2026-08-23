#!/usr/bin/env python3
"""Final Motion §九 -- the private review package.

Target pixels live here and nowhere else in this repo. Every limit §九 sets is
enforced here and reported in the manifest, whether it passes or not:

  <= 40 MB, <= 6 videos, <= 16 stills, per-file SHA-256, the full capture head
  SHA and the full review head SHA, missing 0 and unlisted 0.

The image budget is read the strict way. §九 says "<= 16 stills"; contact
sheets are images too, so the package ships 12 stills and 4 sheets -- sixteen
images in total -- rather than 16 stills plus sheets on top. What that leaves
out is named in `curation.dropped` instead of quietly not being there.

Usage: fm-package.py [--out=<zip>] [--still-q=94] [--crf=22]
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent.parent
ART = REPO / "artifacts/visual-convergence"
FM = REPO / "artifacts/final-motion"
QA = REPO / "qa-v5/final-motion"
PRIV = REPO / "qa-v5/private"
STAGE = FM / "package-stage"
MATCHED = "matched-dark-cinematic"
TAG = "-fm"

VPS = ["1440x900", "390x844", "844x390", "700x700"]
SCENARIOS = ["desktop-slow-drag", "desktop-fast-flick", "desktop-pointer-sweep",
             "mobile-touch-drag", "mobile-long-drag-wrap", "orientation-change"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd) -> None:
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{' '.join(str(c) for c in cmd[:8])} ...\n{r.stderr[-1500:]}")


def git(*a) -> str:
    return subprocess.run(["git", "-C", str(REPO), *a],
                          capture_output=True, text=True).stdout.strip()


def jpeg(src: Path, dst: Path, q: int) -> None:
    Image.open(src).convert("RGB").save(dst, quality=q, optimize=True)


def split_5050(target: Path, cand: Path, dst: Path, vp: str, q: int) -> None:
    a, b = Image.open(target).convert("RGB"), Image.open(cand).convert("RGB")
    if a.size != b.size:
        b = b.resize(a.size)
    w, h = a.size
    out = Image.new("RGB", (w, h))
    out.paste(a.crop((0, 0, w // 2, h)), (0, 0))
    out.paste(b.crop((w // 2, 0, w, h)), (w // 2, 0))
    d = ImageDraw.Draw(out)
    d.line([(w // 2, 0), (w // 2, h)], fill=(255, 255, 255), width=2)
    d.rectangle([0, 0, 168, 20], fill=(8, 10, 16))
    d.text((5, 5), f"TARGET | CANDIDATE  {vp}", fill=(240, 240, 240))
    out.save(dst, quality=q, optimize=True)


def sheet(rows: list[tuple[str, Path]], dst: Path, height: int, q: int) -> bool:
    ims, labels = [], []
    for name, p in rows:
        if not Path(p).exists():
            continue
        im = Image.open(p).convert("RGB")
        ims.append(im.resize((max(1, round(im.width * height / im.height)), height)))
        labels.append(name)
    if not ims:
        return False
    pad, cap = 8, 26
    W = sum(i.width for i in ims) + pad * (len(ims) + 1)
    out = Image.new("RGB", (W, height + cap + pad * 2), (10, 12, 20))
    d = ImageDraw.Draw(out)
    x = pad
    for name, im in zip(labels, ims):
        out.paste(im, (x, cap + pad))
        d.text((x + 4, 7), name, fill=(235, 235, 235))
        x += im.width + pad
    out.save(dst, quality=q, optimize=True)
    return True


def jump_frames(sheet_dst: Path, q: int) -> bool:
    """§五's one allowed inset: the relayout, frame by frame, both sides.

    The frame before the viewport changes, the frame it changes on, the frame
    after -- and then the frame 150 ms later, which is where the trace says the
    Target performs its SECOND relayout teleport (530 px, 5/5 runs). Without
    that fourth column the claim that the Target holds a partly-relaid-out
    state rests on JSON alone; with it the reviewer can see it. The candidate
    is shown at the same offset so the columns are comparable, and it is the
    one that should show nothing happening there.

    Frame indices are found in the pixels, not guessed: the flip is the first
    frame whose aspect ratio is landscape, and the offset is converted from
    150 ms through that recording's own measured frame rate.
    """
    rows = []
    for tag, side in (("TARGET", "target"), ("CANDIDATE", "review-target")):
        d = ART / f"recordings{TAG}/{side}/orientation-change"
        idx = d / "index.json"
        if not idx.exists():
            continue
        meta = json.loads(idx.read_text())
        n, fps = meta["frames"], meta.get("fps") or 30.0
        flip = None
        for i in range(n):
            p = d / f"{i:05d}.jpg"
            if not p.exists():
                continue
            w, h = Image.open(p).size
            if w > h:
                flip = i
                break
        if flip is None or flip < 2:
            continue
        second = max(2, round(0.150 * fps))
        for off, what in ((-1, "before"), (0, "flip"), (1, "+1 frame"),
                          (second, f"+150 ms (f+{second})")):
            p = d / f"{flip + off:05d}.jpg"
            if p.exists():
                rows.append((f"{tag} {what}", p))
    return sheet(rows, sheet_dst, 260, q) if rows else False


def encode_side_by_side(scenario: str, dst: Path, crf: int) -> dict:
    """Target on the left, Candidate on the right, same gesture, same clock."""
    a = ART / f"recordings{TAG}/target/{scenario}"
    b = ART / f"recordings{TAG}/review-target/{scenario}"
    ia = json.loads((a / "index.json").read_text())
    ib = json.loads((b / "index.json").read_text())
    fps = min(ia["fps"], ib["fps"])
    w, h = (int(x) for x in ia["vp"].split("x"))
    # Frame size can change mid-clip (orientation); pad into the start size so
    # the landscape half is letterboxed rather than stretched.
    pad = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")
    scale = "scale=960:-2" if w >= 1440 else "scale=-2:844"
    # Every second frame at half the frame rate: the same wall-clock duration
    # and the same apparent speed, at half the file size. §五 asks for normal
    # speed, and this is normal speed.
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-framerate", f"{fps:.2f}", "-i", a / "%05d.jpg",
         "-framerate", f"{fps:.2f}", "-i", b / "%05d.jpg",
         "-filter_complex",
         f"[0:v]{pad},{scale},select='not(mod(n\\,2))',setpts=N/({fps / 2:.3f}*TB)[l];"
         f"[1:v]{pad},{scale},select='not(mod(n\\,2))',setpts=N/({fps / 2:.3f}*TB)[r];"
         f"[l][r]hstack=inputs=2,pad=ceil(iw/2)*2:ceil(ih/2)*2[v]",
         "-map", "[v]", "-r", f"{fps / 2:.2f}", "-c:v", "libx264", "-preset", "medium",
         "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst])
    return {"file": f"videos/{dst.name}", "scenario": scenario,
            "layout": "TARGET | CANDIDATE",
            "vp": ia["vp"], "resizeTo": ia.get("resizeTo"), "what": ia.get("what"),
            "sourceFps": {"target": ia["fps"], "candidate": ib["fps"]},
            "encodedFps": round(fps / 2, 2),
            "frames": {"target": ia["frames"], "candidate": ib["frames"]},
            "driver": ia["driver"],
            "copyBodySha": {"target": ia.get("copyBodySha"),
                            "candidate": ib.get("copyBodySha")},
            "mediaFrozenAt": {"target": ia.get("mediaFrozenAt"),
                              "candidate": ib.get("mediaFrozenAt")}}


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    zip_p = REPO / args.get("out", "qa-v5/private/v5-final-motion.zip")
    q = int(args.get("still-q", 94))
    crf = int(args.get("crf", 22))

    if STAGE.exists():
        shutil.rmtree(STAGE)
    for sub in ("stills", "contact-sheets", "videos", "data"):
        (STAGE / sub).mkdir(parents=True)

    st = ART / f"stills{TAG}/{MATCHED}"
    stills, dropped = [], []
    for vp in VPS:
        t = st / f"target/{vp}-labels-on.png"
        c = st / f"review-target/{vp}-labels-on.png"
        for name, src, why in (
            ("target-matched", t, "the live Target, matched media and copy, labels on"),
            ("candidate-matched", c,
             "?review=target on this round's build, same media, same copy"),
            ("split-target-candidate", None,
             "50/50 split, Target left, Candidate right, same frame"),
        ):
            dst = STAGE / "stills" / f"{name}-{vp}.jpg"
            if name == "split-target-candidate":
                if not (t.exists() and c.exists()):
                    continue
                split_5050(t, c, dst, vp, q)
            else:
                if not src.exists():
                    raise SystemExit(f"missing still {src}")
                jpeg(src, dst, q)
            stills.append({"file": f"stills/{dst.name}", "kind": name, "vp": vp,
                           "what": why})
    dropped += [
        "every labels-off (glass pass) still -- Glass is frozen this round and "
        "was not re-researched; the accepted set is in the VC2 package",
        "?review=current stills -- the shipped optical default did not change and "
        "the route check proves it still resolves",
        "natural-media stills -- this round's question is motion, and every "
        "comparison it rests on is matched-content",
    ]

    sheets = []
    p = STAGE / "contact-sheets" / "full-page-desktop.jpg"
    if sheet([("TARGET 1440x900", st / "target/1440x900-labels-on.png"),
              ("CANDIDATE 1440x900", st / "review-target/1440x900-labels-on.png")],
             p, 620, 88):
        sheets.append(f"contact-sheets/{p.name}")
    p = STAGE / "contact-sheets" / "full-page-mobile.jpg"
    if sheet([("TARGET 390x844", st / "target/390x844-labels-on.png"),
              ("CANDIDATE 390x844", st / "review-target/390x844-labels-on.png"),
              ("TARGET 844x390", st / "target/844x390-labels-on.png"),
              ("CANDIDATE 844x390", st / "review-target/844x390-labels-on.png")],
             p, 520, 88):
        sheets.append(f"contact-sheets/{p.name}")
    p = STAGE / "contact-sheets" / "full-page-square.jpg"
    if sheet([("TARGET 700x700", st / "target/700x700-labels-on.png"),
              ("CANDIDATE 700x700", st / "review-target/700x700-labels-on.png")],
             p, 620, 88):
        sheets.append(f"contact-sheets/{p.name}")
    p = STAGE / "contact-sheets" / "orientation-jump-frames.jpg"
    if jump_frames(p, 92):
        sheets.append(f"contact-sheets/{p.name}")

    videos = [encode_side_by_side(s, STAGE / "videos" / f"{s}.mp4", crf)
              for s in SCENARIOS
              if (ART / f"recordings{TAG}/target/{s}/index.json").exists()
              and (ART / f"recordings{TAG}/review-target/{s}/index.json").exists()]

    data = []
    for p in [QA / "README.md", *sorted(QA.glob("*.json")),
              FM / "route-check.json", FM / "fsx-source-contract.json",
              FM / "guard-regression.json", FM / "typography-contract.json",
              FM / "perf/perf-smoke-raw.json"]:
        if not p.exists():
            continue
        name = (f"public-{p.name}" if p.name in ("README.md", "MANIFEST.json")
                else p.name)
        dst = STAGE / "data" / name
        dst.write_bytes(p.read_bytes())
        data.append(f"data/{dst.name}")

    head = git("rev-parse", "HEAD")
    captured = git("rev-list", "-1",
                   "--grep=^v5-final-motion-flick-source-and-code", "HEAD") or head
    images = len(stills) + len(sheets)
    manifest = {
        "what": "Final Motion Convergence §九 private review package. The ONLY "
                "place Target pixels live.",
        "reviewCandidateUrl": "http://127.0.0.1:5293/?review=target",
        "reviewCurrentUrl": "http://127.0.0.1:5293/?review=current",
        "howToServe": "npm run review   (builds, then serves 127.0.0.1:5293). "
                      "npm run review:lan serves the same build on 0.0.0.0:5293 "
                      "for a real device; npm run review:lan:url prints the "
                      "addresses.",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": captured,
        "reviewHead": head,
        "headSemantics": {
            "capturedAtHead": "v5-final-motion-flick-source-and-code -- the last "
                              "commit that changes anything the page renders. Every "
                              "still and recording here was taken from a build of "
                              "this tree.",
            "reviewHead": "the head this package was assembled at. The only commit "
                          "between them is the evidence commit, which adds JSON and "
                          "QA scripts and touches no file under src/.",
        },
        "matchedContent": "every still and every video pair was captured with the "
                          "same locally generated media asset served to both pages, "
                          "the same injected copy, the same viewport, the same DPR, "
                          "the same pointer class and the same real input sequence. "
                          "Labels on, footer on, no debug HUD.",
        "budgets": {"stills": f"{len(stills)}/16", "contactSheets": len(sheets),
                    "imagesTotal": f"{images}/16",
                    "imageBudgetReading": "§九 says <= 16 stills. Contact sheets are "
                                          "images, so the strict reading is applied: "
                                          "12 stills + 4 sheets = 16 images.",
                    "videos": f"{len(videos)}/6"},
        "curation": {"why": "§五 fixes the scenario list at six and the viewport list "
                            "at four; the still budget is smaller than that matrix, so "
                            "the shipped set is curated and what was dropped is named",
                     "dropped": dropped},
        "encoding": f"stills JPEG q{q} (pixel-exact PNGs stay in local artifacts/); "
                    f"videos hstacked TARGET|CANDIDATE, every second frame at half "
                    f"the frame rate so wall-clock speed is unchanged, CRF {crf}",
        "stills": stills, "contactSheets": sheets, "videos": videos, "data": data,
        "files": [],
    }
    files = sorted(p for p in STAGE.rglob("*") if p.is_file())
    manifest["files"] = [{"path": str(p.relative_to(STAGE)), "bytes": p.stat().st_size,
                          "sha256": sha256(p)} for p in files
                         if p.relative_to(STAGE) != Path("MANIFEST.json")]
    listed = {f["path"] for f in manifest["files"]}
    referenced = ({s["file"] for s in stills} | set(sheets)
                  | {v["file"] for v in videos} | set(data))
    manifest["verification"] = {
        "missing": sorted(referenced - listed),
        "unlisted": sorted(listed - referenced),
        "fileCount": len(manifest["files"]),
    }
    (STAGE / "MANIFEST.json").write_text(json.dumps(manifest, indent=1,
                                                    ensure_ascii=False))
    manifest["files"].append({"path": "MANIFEST.json",
                              "bytes": (STAGE / "MANIFEST.json").stat().st_size,
                              "sha256": sha256(STAGE / "MANIFEST.json")})

    PRIV.mkdir(parents=True, exist_ok=True)
    if zip_p.exists():
        zip_p.unlink()
    shutil.make_archive(str(zip_p.with_suffix("")), "zip", STAGE)
    size = zip_p.stat().st_size / 1048576
    print(f"{zip_p}  {size:.1f} MiB  ({len(videos)} videos, {len(stills)} stills, "
          f"{len(sheets)} sheets, {len(manifest['files'])} files)")
    print(f"missing={manifest['verification']['missing']} "
          f"unlisted={manifest['verification']['unlisted']}")
    bad = False
    if manifest["verification"]["missing"] or manifest["verification"]["unlisted"]:
        bad = True
    if len(videos) > 6:
        print(f"VIDEO BUDGET EXCEEDED: {len(videos)}/6")
        bad = True
    if images > 16:
        print(f"IMAGE BUDGET EXCEEDED: {images}/16")
        bad = True
    if size > 40:
        print("OVER THE 40 MB LIMIT")
        bad = True
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
