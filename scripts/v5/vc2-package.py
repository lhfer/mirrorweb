#!/usr/bin/env python3
"""VC2 §十 -- the private review package.

Target pixels live here and nowhere else in this repo. Hard limits, all
enforced and all reported: <= 50 MB (built to <= 30 MiB, which is what the
delivery channel actually accepts), <= 8 videos, <= 24 full-page stills, a
per-file SHA-256 manifest, the full capture and review head SHAs, and a
two-direction check that nothing listed is missing and nothing present is
unlisted.

The still budget is smaller than §四's own matrix (four viewports x six kinds
= 24 plus the after-fix set), so the shipped 24 are curated and what was left
out is named in the manifest rather than silently dropped. The contact sheets
carry the overflow.

Usage: vc2-package.py [--out=<zip>] [--still-q=96] [--crf=20]
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
QA = REPO / "qa-v5/visual-convergence"
PRIV = REPO / "qa-v5/private"
STAGE = ART / "package-stage"
MATCHED = "matched-dark-cinematic"

VPS = ["1440x900", "390x844", "844x390", "700x700"]
FULL_VPS = {"1440x900", "390x844"}
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


def label(im: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 8 + 7 * len(text), 20], fill=(8, 10, 16))
    d.text((5, 5), text, fill=(240, 240, 240))
    return im


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
    d.rectangle([0, 0, 150, 20], fill=(8, 10, 16))
    d.text((5, 5), f"TARGET | CANDIDATE  {vp}", fill=(240, 240, 240))
    out.save(dst, quality=q, optimize=True)


def sheet(rows: list[tuple[str, Path]], dst: Path, height: int, q: int) -> None:
    ims, labels = [], []
    for name, p in rows:
        if not p.exists():
            continue
        im = Image.open(p).convert("RGB")
        ims.append(im.resize((max(1, round(im.width * height / im.height)), height)))
        labels.append(name)
    if not ims:
        return
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


def band_crop(src: Path, dst: Path, rows: int, q: int) -> None:
    im = Image.open(src).convert("RGB")
    im.crop((0, im.height - rows, im.width, im.height)).save(dst, quality=q, optimize=True)


def encode_side_by_side(scenario: str, dst: Path, crf: int) -> dict:
    """Target on the left, Candidate on the right, same gesture, same clock."""
    a = ART / f"recordings-after/target/{scenario}"
    b = ART / f"recordings-after/review-target/{scenario}"
    ia = json.loads((a / "index.json").read_text())
    ib = json.loads((b / "index.json").read_text())
    fps = min(ia["fps"], ib["fps"])
    w, h = (int(x) for x in ia["vp"].split("x"))
    # Frame size can change mid-clip (orientation); pad into the start size so
    # the landscape half is letterboxed rather than stretched.
    pad = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black")
    scale = "scale=960:-2" if w >= 1440 else "scale=-2:844"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-framerate", f"{fps:.2f}", "-i", a / "%05d.jpg",
         "-framerate", f"{fps:.2f}", "-i", b / "%05d.jpg",
         "-filter_complex",
         f"[0:v]{pad},{scale},select='not(mod(n\\,2))',setpts=N/({fps / 2:.3f}*TB)[l];"
         f"[1:v]{pad},{scale},select='not(mod(n\\,2))',setpts=N/({fps / 2:.3f}*TB)[r];"
         f"[l][r]hstack=inputs=2,pad=ceil(iw/2)*2:ceil(ih/2)*2[v]",
         "-map", "[v]", "-r", f"{fps / 2:.2f}", "-c:v", "libx264", "-preset", "medium",
         "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst])
    return {"file": f"videos/{dst.name}", "scenario": scenario, "layout": "TARGET | CANDIDATE",
            "vp": ia["vp"], "resizeTo": ia.get("resizeTo"), "what": ia.get("what"),
            "sourceFps": {"target": ia["fps"], "candidate": ib["fps"]},
            "encodedFps": round(fps / 2, 2),
            "frames": {"target": ia["frames"], "candidate": ib["frames"]},
            "driver": ia["driver"],
            "copyBodySha": {"target": ia.get("copyBodySha"), "candidate": ib.get("copyBodySha")}}


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    zip_p = REPO / args.get("out", "qa-v5/private/vc2-visual-convergence.zip")
    q = int(args.get("still-q", 96))
    crf = int(args.get("crf", 20))

    if STAGE.exists():
        shutil.rmtree(STAGE)
    for sub in ("stills", "contact-sheets", "videos", "data"):
        (STAGE / sub).mkdir(parents=True)

    mb = ART / f"stills-before/{MATCHED}"
    ma = ART / f"stills-after/{MATCHED}"
    nb = ART / "stills-before/natural"
    na = ART / "stills-after/natural"

    stills, dropped = [], []
    for vp in VPS:
        plan = [
            ("target-matched", mb / f"target/{vp}-labels-on.png",
             "the live Target, matched media and copy"),
            ("candidate-before-matched", mb / f"review-target/{vp}-labels-on.png",
             "?review=target BEFORE the chrome change"),
            ("candidate-after-matched", ma / f"review-target/{vp}-labels-on.png",
             "?review=target AFTER the chrome change"),
            ("split-target-candidate", None, "50/50 split, Target left, Candidate after right"),
            ("natural-candidate-after", na / f"review-target/{vp}.png",
             "?review=target with its OWN media and copy, after"),
        ]
        if vp in FULL_VPS:
            plan.insert(1, ("current-matched", mb / f"review-current/{vp}-labels-on.png",
                            "?review=current (shipped optical default), matched"))
            plan.append(("natural-target", nb / f"target/{vp}.png",
                         "the live Target with its own media and copy"))
        else:
            dropped += [f"current-matched@{vp}", f"natural-target@{vp}"]
        for name, src, why in plan:
            dst = STAGE / "stills" / f"{name}-{vp}.jpg"
            if name == "split-target-candidate":
                t, c = mb / f"target/{vp}-labels-on.png", ma / f"review-target/{vp}-labels-on.png"
                if not (t.exists() and c.exists()):
                    continue
                split_5050(t, c, dst, vp, q)
            else:
                if not src.exists():
                    raise SystemExit(f"missing still {src}")
                jpeg(src, dst, q)
            stills.append({"file": f"stills/{dst.name}", "kind": name, "vp": vp, "what": why})
    dropped += ["every labels-off (glass pass) still -- carried by the contact sheets"]
    if len(stills) > 24:
        raise SystemExit(f"still budget exceeded: {len(stills)}")

    sheets = []
    for vp in VPS:
        p = STAGE / "contact-sheets" / f"full-page-{vp}.jpg"
        sheet([("TARGET " + vp, mb / f"target/{vp}-labels-on.png"),
               ("CANDIDATE BEFORE", mb / f"review-target/{vp}-labels-on.png"),
               ("CANDIDATE AFTER", ma / f"review-target/{vp}-labels-on.png")], p, 620, 86)
        sheets.append(f"contact-sheets/{p.name}")
        # The chrome band itself, at 1:1, cropped to the Target's own scrim height.
        crops = []
        for tag, src in (("target", mb / f"target/{vp}-labels-on.png"),
                         ("before", mb / f"review-target/{vp}-labels-on.png"),
                         ("after", ma / f"review-target/{vp}-labels-on.png")):
            c = STAGE / "contact-sheets" / f"_band-{tag}-{vp}.jpg"
            band_crop(src, c, 144, 92)
            crops.append((tag.upper() + " " + vp, c))
        pb = STAGE / "contact-sheets" / f"chrome-band-{vp}.jpg"
        sheet(crops, pb, 144, 92)
        for _, c in crops:
            c.unlink()
        sheets.append(f"contact-sheets/{pb.name}")
        # labels-off glass pass, the stills the 24-budget dropped
        pg = STAGE / "contact-sheets" / f"glass-pass-labels-off-{vp}.jpg"
        sheet([("TARGET " + vp, mb / f"target/{vp}-labels-off.png"),
               ("CANDIDATE AFTER", ma / f"review-target/{vp}-labels-off.png")], pg, 620, 86)
        sheets.append(f"contact-sheets/{pg.name}")

    videos = [encode_side_by_side(s, STAGE / "videos" / f"{s}.mp4", crf) for s in SCENARIOS]
    if len(videos) > 8:
        raise SystemExit(f"video budget exceeded: {len(videos)}")

    data = []
    for p in [QA / "README.md", *sorted(QA.glob("*.json")),
              ART / "chrome-truth-before.json", ART / "chrome-truth-after.json",
              ART / "recording-band.json", ART / "recon.json", ART / "recon-after.json",
              ART / "route-check.json", ART / "frozen/source-contract.json",
              ART / "frozen/typography-contract.json", ART / "perf/perf-smoke-raw.json"]:
        if not p.exists():
            continue
        # The public tree's own README/MANIFEST travel as `public-*` so they are
        # never confused with this package's manifest at the stage root.
        name = (f"{p.parent.name}-{p.name}" if p.parent.name == "frozen"
                else f"public-{p.name}" if p.name in ("README.md", "MANIFEST.json")
                else p.name)
        dst = STAGE / "data" / name
        dst.write_bytes(p.read_bytes())
        data.append(f"data/{dst.name}")

    head = git("rev-parse", "HEAD")
    # The captures were taken from the working tree that became the product-code
    # commit. Every commit after it touches docs, evidence and instruments only,
    # so the rendered product is the same -- but the honest field is the commit
    # whose tree was actually photographed.
    captured = git("rev-list", "-1", "--grep=^v5-visual-convergence-product-code", "HEAD") or head
    manifest = {
        "what": "VC2 §十 private review package. The ONLY place Target pixels live.",
        "reviewCandidateUrl": "http://127.0.0.1:5293/?review=target",
        "reviewCurrentUrl": "http://127.0.0.1:5293/?review=current",
        "howToServe": "npm run review   (builds, then serves 127.0.0.1:5293; no remote preview "
                      "exists for this branch)",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHead": captured,
        "reviewHead": head,
        "headSemantics": {
            "capturedAtHead": "v5-visual-convergence-product-code -- the tree the after-stills "
                              "and after-recordings were photographed from. The before-stills "
                              "and the pre-fix card trajectories were captured at its parent, "
                              "v5-visual-convergence-p0-decision.",
            "reviewHead": "the head this package was assembled at; every commit between it and "
                          "capturedAtHead touches docs, evidence and instruments only -- no "
                          "src/ file changed, so the rendered product is identical",
        },
        "matchedContent": "every matched still and every video pair was captured with the same "
                          "locally generated media asset served to both pages and the same "
                          "injected copy; see data/matched-content-contract.json",
        "budgets": {"stills": f"{len(stills)}/24", "videos": f"{len(videos)}/8",
                    "contactSheets": len(sheets)},
        "curation": {"why": "§四 defines 24 matched/natural kinds BEFORE the fix and the same "
                            "again after it; the package budget is 24 stills total, so the "
                            "shipped set is curated",
                     "dropped": dropped},
        "encoding": f"stills JPEG q{q} (pixel-exact PNGs stay in local artifacts/); videos "
                    f"hstacked Target|Candidate, every second frame, CRF {crf}, wall clock "
                    f"preserved",
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
    (STAGE / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
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
    if manifest["verification"]["missing"] or manifest["verification"]["unlisted"]:
        return 1
    if size > 50:
        print("OVER THE 50 MB LIMIT")
        return 1
    if size > 30:
        print("over the 30 MiB delivery ceiling -- lower --still-q / raise --crf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
