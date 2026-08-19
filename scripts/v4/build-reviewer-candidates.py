#!/usr/bin/env python3
"""Extract alternative Target Frame candidates for Reviewer Mode step 1.

Frozen Visual extraction selects exactly one frame per category. A human
reviewer must be able to say "this frame is unusable, show me a cleaner one",
so this script decodes a few neighbouring frames of the same source video and
writes them, plus card-centred thumbnails, into the private review bundle.

Everything is written under qa-v4/review/, which must stay ignored: these are
Target pixels and never become public QA output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_ROOT = REPO_ROOT / "qa-v4/review"
OUTPUT_DIR = REVIEW_ROOT / "phase-1b/candidates"
MANIFEST_NAME = "candidates.local.json"
FROZEN_ROOT = REPO_ROOT / "qa-v4/reference/frozen-visual"
PRIVATE_MANIFEST = FROZEN_ROOT / "manifest.private.json"
SANITIZED_MANIFEST = FROZEN_ROOT / "frozen-visual.sanitized.json"
DEFAULT_VIDEO = REPO_ROOT / ".private/ilg-golden-v4/target.mp4"
SOURCE_VIDEO_SHA256 = "b6e79250c75e0357e489de87b63ffd4a5097a573eb7baced35e5de8b050c2435"
GENERATOR = "phase1b-reviewer-candidates-v1"

# Role-facing categories only. pointer-before / pointer-after are not review roles.
ROLE_CATEGORIES = (
    "bright-front",
    "dark-front",
    "high-texture",
    "low-texture",
    "left-tilt",
    "right-tilt",
)
NEIGHBOUR_OFFSETS = (-8, -4, 4, 8)
THUMBNAIL_BOX = (520, 340)
THUMBNAIL_PADDING = 0.22


class CandidateError(RuntimeError):
    """Fail-closed error for a candidate bundle that cannot be trusted."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_path(path: Path) -> str:
    resolved = path.resolve()
    if resolved == REPO_ROOT or REPO_ROOT not in resolved.parents:
        raise CandidateError(f"Path escapes repository: {path}")
    return resolved.relative_to(REPO_ROOT).as_posix()


def git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def assert_private_output() -> None:
    tracked = git(["ls-files", "--", "qa-v4/review"]).stdout.strip()
    if tracked:
        raise CandidateError(f"Refusing tracked review files: {tracked.splitlines()[0]}")
    sentinel = OUTPUT_DIR / ".privacy-sentinel"
    ignored = git(["check-ignore", "-q", "--no-index", "--", repository_path(sentinel)], check=False)
    if ignored.returncode != 0:
        raise CandidateError("qa-v4/review/ is not ignored; refusing to write Target pixels")


def extract_frame(video: Path, frame_index: int, destination: Path) -> None:
    """Same decode contract as scripts/v4/extract-frozen-visual.py."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    expression = f"select=eq(n\\,{frame_index})"
    temporary = tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}-", suffix=".png", dir=destination.parent, delete=False
    )
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-i", str(video),
                "-vf", expression, "-fps_mode", "vfr", "-frames:v", "1", "-y",
                str(temporary_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not temporary_path.is_file() or temporary_path.stat().st_size == 0:
            raise CandidateError(result.stderr.strip() or f"Could not extract source frame {frame_index}")
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def write_thumbnail(source: Path, destination: Path, quad: list[list[float]]) -> dict[str, Any]:
    """Card-centred crop so the strip is about the card, not the whole desktop."""
    with Image.open(source) as opened:
        opened.load()
        image = opened.convert("RGB")
    width, height = image.size
    xs = [point[0] for point in quad]
    ys = [point[1] for point in quad]
    box_width = max(xs) - min(xs)
    box_height = max(ys) - min(ys)
    pad_x = box_width * THUMBNAIL_PADDING
    pad_y = box_height * THUMBNAIL_PADDING
    left = max(0, int(min(xs) - pad_x))
    top = max(0, int(min(ys) - pad_y))
    right = min(width, int(max(xs) + pad_x))
    bottom = min(height, int(max(ys) + pad_y))
    if right - left < 16 or bottom - top < 16:
        raise CandidateError(f"Candidate crop for {source.name} is degenerate")
    crop = image.crop((left, top, right, bottom))
    crop.thumbnail(THUMBNAIL_BOX, Image.Resampling.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}-", suffix=".jpg", dir=destination.parent, delete=False
    )
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        crop.save(temporary_path, format="JPEG", quality=88, optimize=True, exif=b"")
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return {
        "path": repository_path(destination),
        "sha256": sha256_file(destination),
        "bytes": destination.stat().st_size,
        "width": crop.width,
        "height": crop.height,
        "cropBox": [left, top, right, bottom],
    }


def load_frozen_geometry() -> tuple[dict[str, dict[str, Any]], int]:
    if not PRIVATE_MANIFEST.is_file():
        raise CandidateError("Frozen private manifest is missing; run the frozen extraction first")
    private = json.loads(PRIVATE_MANIFEST.read_text(encoding="utf-8"))
    sanitized = json.loads(SANITIZED_MANIFEST.read_text(encoding="utf-8"))
    if private.get("sourceSha256") != SOURCE_VIDEO_SHA256:
        raise CandidateError("Frozen manifest is bound to a different source video")
    frame_count = int(sanitized.get("source", {}).get("frameCount") or 0)
    if frame_count <= 0:
        raise CandidateError("Frozen manifest has no frame count")
    categories: dict[str, dict[str, Any]] = {}
    for entry in private.get("categories", []):
        categories[entry["id"]] = entry
    missing = [name for name in ROLE_CATEGORIES if name not in categories]
    if missing:
        raise CandidateError(f"Frozen manifest is missing categories: {', '.join(missing)}")
    return categories, frame_count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", default=str(DEFAULT_VIDEO), help="Private Golden target video")
    parser.add_argument("--force", action="store_true", help="Re-decode candidates that already exist")
    arguments = parser.parse_args()

    assert_private_output()
    video = Path(arguments.video)
    if not video.is_file():
        raise CandidateError(f"Private Golden video is unavailable: {arguments.video}")
    if sha256_file(video) != SOURCE_VIDEO_SHA256:
        raise CandidateError("Private Golden video identity does not match the frozen source")

    categories, frame_count = load_frozen_geometry()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result_categories: dict[str, list[dict[str, Any]]] = {}

    for category_id in ROLE_CATEGORIES:
        entry = categories[category_id]
        selected_index = int(entry["sourceFrameIndex"])
        quad = entry["pixelGeometry"]["quad"]
        frozen_frame = FROZEN_ROOT / "frames" / f"{category_id}.png"
        if not frozen_frame.is_file():
            raise CandidateError(f"Frozen frame is missing for {category_id}")
        directory = OUTPUT_DIR / category_id
        directory.mkdir(parents=True, exist_ok=True)
        candidates: list[dict[str, Any]] = []

        indices = [selected_index] + [
            selected_index + offset
            for offset in NEIGHBOUR_OFFSETS
            if 0 <= selected_index + offset < frame_count
        ]
        for index in indices:
            primary = index == selected_index
            if primary:
                frame_path = frozen_frame
            else:
                frame_path = directory / f"frame-{index}.png"
                if arguments.force or not frame_path.is_file():
                    extract_frame(video, index, frame_path)
            with Image.open(frame_path) as opened:
                width, height = opened.size
            thumbnail_path = directory / f"frame-{index}.thumb.jpg"
            if arguments.force or not thumbnail_path.is_file():
                thumbnail = write_thumbnail(frame_path, thumbnail_path, quad)
            else:
                with Image.open(thumbnail_path) as opened:
                    thumbnail_size = opened.size
                thumbnail = {
                    "path": repository_path(thumbnail_path),
                    "sha256": sha256_file(thumbnail_path),
                    "bytes": thumbnail_path.stat().st_size,
                    "width": thumbnail_size[0],
                    "height": thumbnail_size[1],
                }
            candidates.append({
                "id": f"f{index}",
                "frameIndex": index,
                "primary": primary,
                "offsetFromSelected": index - selected_index,
                "path": repository_path(frame_path),
                "sha256": sha256_file(frame_path),
                "bytes": frame_path.stat().st_size,
                "width": width,
                "height": height,
                "thumbnail": thumbnail,
            })
        if len(candidates) < 3:
            raise CandidateError(f"{category_id} produced fewer than three candidate frames")
        result_categories[category_id] = candidates
        print(f"{category_id}: {len(candidates)} candidates ({', '.join(str(c['frameIndex']) for c in candidates)})")

    manifest = {
        "schemaVersion": 1,
        "private": True,
        "generator": GENERATOR,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "sourceVideoSha256": SOURCE_VIDEO_SHA256,
        "frameCount": frame_count,
        "neighbourOffsets": list(NEIGHBOUR_OFFSETS),
        "categories": result_categories,
    }
    manifest_path = OUTPUT_DIR / MANIFEST_NAME
    manifest_path.write_text(f"{json.dumps(manifest, indent=2)}\n", encoding="utf-8")
    print(f"Candidate manifest: {repository_path(manifest_path)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CandidateError as error:
        print(f"FAILED: {error}")
        raise SystemExit(1) from error
