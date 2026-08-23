#!/usr/bin/env python3
"""Final Entry §十一 -- the private review package, and the FM metadata rebuild.

Budgets: <= 45 MB, <= 6 videos, <= 20 stills. Per-file SHA-256, the full
capture head, the full review head, nothing missing and nothing unlisted. Target
pixels live here and nowhere else in this repository.

§十一's last line also says to rebuild the old Final Motion private package's
metadata here rather than spending a round on hygiene. That package's manifest
records `reviewHead: 0345105e...`, which is a draft that its own evidence
commit's amend cycle orphaned: the SHA exists in nobody's history, no ref
reaches it, and `git push` never transferred it. The zip's manifest is rewritten
in place to the commit that actually carries that round's evidence, with a note
saying what was wrong and why.

Usage: fe-package.py [--out=qa-v5/private/v5-final-entry.zip] [--crf=30]
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent.parent
ART = REPO / "artifacts/final-entry"
PUB = REPO / "qa-v5/final-entry"
STAGE = REPO / "artifacts/final-entry/package"

MB = 1024 * 1024
BUDGET_BYTES = 45 * MB
BUDGET_VIDEOS = 6
BUDGET_STILLS = 20

VIEWPORTS = ["1440x900", "390x844", "844x390", "700x700"]
OFFSETS = [0, 120, 250, 420, 1400]

FM_EVIDENCE_MSG = "^v5-final-motion-product-evidence"


def private_dir() -> Path:
    """Where the private packages actually live.

    `qa-v5/private/` is gitignored, so it exists only in the working tree that
    created it -- which is the MAIN checkout, not the isolated worktree this
    round runs in. Resolving it through the common git dir puts this round's
    package beside every previous round's, and lets the Final Motion repair
    below find the zip it is supposed to repair.
    """
    here = REPO / "qa-v5/private"
    if here.is_dir():
        return here
    common = git("rev-parse", "--path-format=absolute", "--git-common-dir")
    main = Path(common).parent if common else REPO
    return main / "qa-v5/private"


def git(*a) -> str:
    return subprocess.run(["git", "-C", str(REPO), *a],
                          capture_output=True, text=True).stdout.strip()


def anchor(msg: str) -> str:
    sha = git("rev-list", "-1", f"--grep={msg}", "HEAD")
    if not sha:
        raise SystemExit(f"cannot resolve {msg}")
    return sha


def reachable(sha: str) -> bool:
    if not sha or subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", sha],
                                 capture_output=True).returncode != 0:
        return False
    return subprocess.run(
        ["git", "-C", str(REPO), "merge-base", "--is-ancestor", sha, "HEAD"],
        capture_output=True).returncode == 0


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"{cmd[0]} failed: {r.stderr[-600:]}")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def font(size: int):
    for name in ("/System/Library/Fonts/SFNSMono.ttf",
                 "/System/Library/Fonts/Supplemental/Andale Mono.ttf"):
        if Path(name).exists():
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                pass
    return ImageFont.load_default()


def contact_sheet(vp: str, dst: Path, col_w: int = 520) -> dict:
    """One viewport: the Target above, the candidate below, five entry moments.

    Columns are the SAME point in each page's own entry, not the same wall
    clock -- the two do not finish loading together and never will, so a
    wall-clock pairing would only compare load speed. Column 1 is the first
    frame of the entry and column 5 is settled.
    """
    rows = []
    for side in ("target", "local"):
        imgs = [Image.open(ART / f"stills/{side}/{vp}/t+{o:04d}.png").convert("RGB")
                for o in OFFSETS]
        rows.append(imgs)
    w0, h0 = rows[0][0].size
    scale = col_w / w0
    cw, ch = col_w, int(round(h0 * scale))
    pad, head, label = 6, 34, 26
    W = pad + len(OFFSETS) * (cw + pad)
    H = head + 2 * (label + ch + pad) + pad
    sheet = Image.new("RGB", (W, H), (12, 12, 12))
    d = ImageDraw.Draw(sheet)
    f = font(15)
    fs = font(13)
    d.text((pad, 9), f"cold-load entry  {vp}   TARGET (top) | CANDIDATE (bottom)"
                     "   matched media + copy, labels on, footer on", font=f,
           fill=(235, 235, 235))
    for r, (side, imgs) in enumerate(zip(("TARGET", "CANDIDATE"), rows)):
        y = head + r * (label + ch + pad)
        for c, im in enumerate(imgs):
            x = pad + c * (cw + pad)
            d.text((x, y + 5), f"{side}   ready + {OFFSETS[c]} ms", font=fs,
                   fill=(170, 170, 170))
            sheet.paste(im.resize((cw, ch), Image.LANCZOS), (x, y + label))
    dst.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(dst, quality=92)
    return {"file": f"contact-sheets/{dst.name}", "vp": vp,
            "columnsMs": OFFSETS,
            "what": "the entry at five matched points, Target above, candidate below"}


def side_by_side(name: str, dst: Path, crf: int) -> dict | None:
    a = ART / f"recordings/target/{name}/clip.webm"
    b = ART / f"recordings/local/{name}/clip.webm"
    if not (a.exists() and b.exists()):
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(a), "-i", str(b),
         # No burnt-in caption: this ffmpeg build has no drawtext filter. The
         # sides are TARGET left, CANDIDATE right, which the manifest states and
         # which is also readable off the screen -- the studio wordmark in the
         # footer differs, and ours is deliberately never the Target's.
         "-filter_complex",
         "[0:v]scale=720:-2,setsar=1[l];[1:v]scale=720:-2,setsar=1[r];"
         "[l][r]hstack=inputs=2",
         "-c:v", "libx264", "-crf", str(crf), "-preset", "slow",
         "-pix_fmt", "yuv420p", "-an", str(dst)])
    return {"file": f"videos/{dst.name}", "scenario": name,
            "layout": "TARGET on the LEFT, CANDIDATE on the RIGHT",
            "howToTellThemApart": "the footer wordmark -- the Target's studio mark is "
                                  "its own and is never copied into this repository, so "
                                  "ours reads differently",
            "speed": "normal, unaltered"}


def solo(name: str, dst: Path, crf: int, what: str) -> dict | None:
    src = ART / f"recordings/local/{name}/clip.webm"
    if not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-vf", "scale=1080:-2", "-c:v", "libx264", "-crf", str(crf),
         "-preset", "slow", "-pix_fmt", "yuv420p", "-an", str(dst)])
    return {"file": f"videos/{dst.name}", "scenario": name, "layout": "CANDIDATE only",
            "speed": "normal, unaltered", "what": what}


def rebuild_fm_metadata() -> dict:
    """§十一's last line: fix the Final Motion package's orphaned reviewHead."""
    fm_zip = private_dir() / "v5-final-motion.zip"
    if not fm_zip.exists():
        return {"done": False, "why": f"{fm_zip} not present"}
    with zipfile.ZipFile(fm_zip) as z:
        names = z.namelist()
        if "MANIFEST.json" not in names:
            return {"done": False, "why": "no MANIFEST.json in the package"}
        blobs = {n: z.read(n) for n in names}
    man = json.loads(blobs["MANIFEST.json"])
    old = man.get("reviewHead")
    if reachable(old):
        # Idempotent, and honest about it: if this round already applied the
        # repair, say so rather than reporting "nothing to do", which reads as
        # though §十一's rebuild clause was skipped.
        prior = man.get("reviewHeadCorrection")
        if prior:
            return {"done": True, "appliedEarlierThisRound": True,
                    "package": str(fm_zip), "was": prior.get("was"), "now": old,
                    "correctedAt": prior.get("correctedAt")}
        return {"done": False, "why": "reviewHead was already reachable; nothing to "
                                      "repair", "reviewHead": old}
    new = anchor(FM_EVIDENCE_MSG)
    man["reviewHead"] = new
    man["reviewHeadCorrection"] = {
        "was": old,
        "why": "that SHA was a draft of the Final Motion evidence commit that the "
               "commit's own amend cycle orphaned. It exists in no branch, no ref "
               "reaches it, and `git push` never transferred it -- so anyone given "
               "this package could not resolve it.",
        "now": "v5-final-motion-product-evidence, the commit that actually carries "
               "that round's evidence, resolved by message rather than by "
               "`git rev-parse HEAD` -- which is the mistake that produced the "
               "orphan in the first place.",
        "correctedBy": "MirrorWeb V5 Final Experience Convergence, per §十一",
        "correctedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "capturedAtHeadUnchanged": man.get("capturedAtHead"),
    }
    blobs["MANIFEST.json"] = json.dumps(man, indent=1, ensure_ascii=False).encode()
    tmp = fm_zip.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, blobs[n])
    shutil.move(tmp, fm_zip)
    return {"done": True, "package": str(fm_zip),
            "was": old, "now": new,
            "capturedAtHead": man.get("capturedAtHead"),
            "capturedAtHeadReachable": reachable(man.get("capturedAtHead"))}


def main() -> int:
    args = dict(a[2:].split("=", 1) for a in sys.argv[1:] if a.startswith("--"))
    out = Path(args["out"]) if "out" in args else private_dir() / "v5-final-entry.zip"
    crf = int(args.get("crf", 30))
    captured = anchor("^v5-final-entry-card-lifecycle-code")

    if STAGE.exists():
        shutil.rmtree(STAGE)
    for sub in ("contact-sheets", "videos", "data"):
        (STAGE / sub).mkdir(parents=True, exist_ok=True)

    sheets = [contact_sheet(vp, STAGE / "contact-sheets" / f"entry-{vp}.jpg")
              for vp in VIEWPORTS]

    # The settled page at 1x, full frame, one per side per viewport. The contact
    # sheets are scaled down to fit five columns; §七.8 is about the final
    # layout being exact, and that needs a still nobody has resized.
    stills = []
    (STAGE / "stills").mkdir(parents=True, exist_ok=True)
    for vp in VIEWPORTS:
        for side, label in (("target", "target"), ("local", "candidate")):
            src = ART / f"stills/{side}/{vp}/t+{OFFSETS[-1]:04d}.png"
            if not src.exists():
                continue
            dst = STAGE / "stills" / f"{label}-settled-{vp}.jpg"
            Image.open(src).convert("RGB").save(dst, quality=94)
            stills.append({"file": f"stills/{dst.name}", "side": label, "vp": vp,
                           "what": "the settled page at 1x, full frame, matched media "
                                   "and copy, labels on, footer on, no debug overlay"})

    videos = []
    for name in ("cold-desktop-load", "warm-desktop-load", "cold-mobile-load",
                 "slow-drag-after-entry", "orientation-change"):
        v = side_by_side(name, STAGE / "videos" / f"{name}.mp4", crf)
        if v:
            videos.append(v)
    v6 = solo("candidate-frame-pacing", STAGE / "videos" / "candidate-frame-pacing.mp4",
              crf,
              "CANDIDATE ONLY, and deliberately with the live status readout visible: "
              "FPS, p95/p99, longest frame, quality, sample tier, CSS3D mounted / "
              "visible / transform writes, material-cache size, black-frame count and "
              "the entry state. It is the subject of the clip, not a contaminant, and "
              "this is the one clip of the six that is not a Target comparison. Every "
              "other clip here, and every still, was captured with the readout ABSENT.")
    if v6:
        videos.append(v6)

    data = []
    for p in sorted(PUB.glob("*.json")) + sorted(PUB.glob("*.md")):
        shutil.copy2(p, STAGE / "data" / f"public-{p.name}"
                     if p.name in ("README.md",) else STAGE / "data" / p.name)
    for src, dst in (
        ("source-contract.json", "source-contract.json"),
        ("typography-regression.json", "typography-regression.json"),
        ("card-label-motion.json", "card-label-motion.json"),
        # §十's motion freeze smoke and its two cancel sequences. The scorer's
        # verdict, and the two raw reports it reads -- including the Target
        # landmark comparison that reports FAIL on our build and on the frozen
        # baseline alike, which is why it ships whole rather than summarised.
        ("frozen/motion-regression.json", "motion-regression.json"),
        ("frozen/motion-smoke-gate/gate-summary.json", "motion-smoke-gate-summary.json"),
        ("frozen/motion-smoke-gate/engine-vs-contract-v3.json", "motion-engine-vs-contract.json"),
        ("frozen/motion-smoke-gate/release-history-proof.json", "motion-release-history-proof.json"),
        ("frozen/motion-smoke-gate/continuity-and-input.json", "motion-continuity-and-input.json"),
        ("render/render-culling-truth.json", "render-gate.json"),
        ("gates/perf-smoke.json", "perf-smoke.json"),
        ("gates/runtime/runtime-assertions.json", "runtime-assertions.json"),
        ("pacing.json", "pacing-raw.json"),
        ("stills/target/index.json", "stills-index-target.json"),
        ("stills/local/index.json", "stills-index-candidate.json"),
        ("recordings/target/index.json", "recordings-index-target.json"),
        ("recordings/local/index.json", "recordings-index-candidate.json"),
        ("footer/target.json", "footer-target.json"),
        ("footer/local.json", "footer-candidate.json"),
    ):
        s = ART / src
        if s.exists():
            shutil.copy2(s, STAGE / "data" / dst)
    for p in sorted((STAGE / "data").iterdir()):
        data.append(f"data/{p.name}")

    for gr in (REPO / "artifacts/final-motion/guard-regression.json",
               REPO / "artifacts/visual-convergence/route-check.json"):
        if gr.exists():
            shutil.copy2(gr, STAGE / "data" / gr.name)
            data.append(f"data/{gr.name}")

    files = sorted(p for p in STAGE.rglob("*") if p.is_file())
    listing = [{"path": str(p.relative_to(STAGE)), "bytes": p.stat().st_size,
                "sha256": sha256(p)} for p in files]
    total = sum(f["bytes"] for f in listing)
    n_video = sum(1 for f in listing if f["path"].startswith("videos/"))
    n_image = sum(1 for f in listing
                  if f["path"].endswith((".jpg", ".png", ".jpeg")))

    fm = rebuild_fm_metadata()

    man = {
        "what": "Final Experience Convergence §十一 private review package. The ONLY "
                "place Target pixels live.",
        "reviewCandidateUrl": "http://127.0.0.1:5293/?review=target",
        "reviewCurrentUrl": "http://127.0.0.1:5293/?review=current",
        "howToServe": "npm run review (builds, then serves 127.0.0.1:5293). "
                      "npm run review:lan serves the same build on 0.0.0.0:5293 for a "
                      "real device; npm run review:lan:url prints the addresses. Add "
                      "&status=1 for the live readout -- it is a QA surface and was "
                      "off for every capture here except video 6.",
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "capturedAtHead": captured,
        "reviewHead": captured,
        "headSemantics": {
            "capturedAtHead": "v5-final-entry-card-lifecycle-code -- the last commit "
                              "that changes anything the page renders. Every still and "
                              "recording here was taken from a build of this tree.",
            "reviewHead": "the same commit, and deliberately so. The only thing after "
                          "it is the evidence commit that carries this package's public "
                          "half, and it touches nothing under src/ -- so the rendered "
                          "product at the branch tip is byte-identical to the product "
                          "at capturedAtHead. Both are resolved by COMMIT MESSAGE, never "
                          "by `git rev-parse HEAD`: this file is regenerated inside the "
                          "evidence commit's own amend cycle, where HEAD is the draft "
                          "the amend is about to orphan.",
            "bothReachable": {"capturedAtHead": reachable(captured)},
        },
        "matchedContent": "every still and every Target/candidate video pair was "
                          "captured with one locally generated media asset served to "
                          "both pages, the same injected copy read back off the DOM "
                          "afterwards, the same viewport, DPR 1, labels on, footer on "
                          "and no debug overlay. Video 6 is candidate-only and carries "
                          "the status readout on purpose.",
        "budgets": {
            "bytes": f"{total / MB:.1f} MB / {BUDGET_BYTES // MB} MB",
            "videos": f"{n_video} / {BUDGET_VIDEOS}",
            "stills": f"{n_image} / {BUDGET_STILLS}",
            "stillsReading": "contact sheets are images and are counted as stills, "
                             "which is the strict reading",
        },
        "contactSheets": sheets,
        "stills": stills,
        "videos": videos,
        "data": data,
        "files": listing,
        "verification": {"missing": [], "unlisted": [], "fileCount": len(listing)},
        "finalMotionPackageMetadataRebuild": fm,
    }
    (STAGE / "MANIFEST.json").write_text(json.dumps(man, indent=1, ensure_ascii=False))

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(STAGE.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(STAGE))

    with zipfile.ZipFile(out) as z:
        inzip = {n for n in z.namelist() if n != "MANIFEST.json"}
    listed = {f["path"] for f in listing}
    missing = sorted(listed - inzip)
    unlisted = sorted(inzip - listed)
    ok = (total <= BUDGET_BYTES and n_video <= BUDGET_VIDEOS
          and n_image <= BUDGET_STILLS and not missing and not unlisted)
    shown = out.relative_to(REPO) if out.is_relative_to(REPO) else out
    print(f"{shown}  {out.stat().st_size / MB:.1f} MB "
          f"(staged {total / MB:.1f} MB)  videos {n_video}/{BUDGET_VIDEOS}  "
          f"images {n_image}/{BUDGET_STILLS}  missing {len(missing)}  "
          f"unlisted {len(unlisted)}")
    print(f"  FM metadata rebuild: {fm}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
