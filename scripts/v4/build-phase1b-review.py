#!/usr/bin/env python3
"""Build the private Phase 1B human-review bundle from a clean capture manifest.

The output is deliberately restricted to qa-v4/review/, which must be ignored
and must contain no tracked files. The local manifest stores repository-relative
paths and hashes only; no private pixels are copied into public QA results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


REPO_ROOT = Path(__file__).resolve().parents[2]
REVIEW_ROOT = REPO_ROOT / "qa-v4/review"
DEFAULT_INPUT = REPO_ROOT / "qa-v4/results/optics-lab-foundation.capture.local.json"
DEFAULT_OUTPUT_DIR = REVIEW_ROOT / "phase-1b"
LOCAL_MANIFEST_NAME = "review-manifest.local.json"
CONTACT_SHEET_NAME = "phase-1b-contact-sheet.jpg"
SESSION_VIDEO_NAME = "phase-1b-session.mp4"
GENERATOR = "phase1b-review-bundle-v1"

REVIEW_CAPTURES = (
    ("v3-v4-split-checker.png", "split-checker"),
    ("v4-checker.png", "v4-checker"),
    ("v4-horizontal-lines.png", "v4-horizontal-lines"),
    ("v4-vertical-lines.png", "v4-vertical-lines"),
    ("v4-white.png", "v4-white"),
    ("v4-black.png", "v4-black"),
    ("v4-high-frequency.png", "v4-high-frequency-photo"),
    ("v4-low-frequency.png", "v4-low-frequency-flat"),
    ("v4-reflection-left.png", "phase1b-reflection-left"),
    ("v4-reflection-center.png", "phase1b-reflection-center"),
    ("v4-reflection-right.png", "phase1b-reflection-right"),
    ("v4-edge-mask.png", "edge-mask-black"),
    ("v4-refraction-offset.png", "refraction-offset-checker"),
    ("v4-dispersion.png", "dispersion-checker"),
)


class ReviewBundleError(RuntimeError):
    """Fail-closed error for a bundle that cannot be safely reviewed."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(lines: list[str]) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def repository_path(path: Path) -> str:
    resolved = path.resolve()
    if resolved == REPO_ROOT or REPO_ROOT not in resolved.parents:
        raise ReviewBundleError(f"Path escapes repository: {path}")
    return resolved.relative_to(REPO_ROOT).as_posix()


def resolve_repository_path(value: str | Path, label: str) -> Path:
    path = Path(value)
    candidate = (path if path.is_absolute() else REPO_ROOT / path).resolve()
    if candidate == REPO_ROOT or REPO_ROOT not in candidate.parents:
        raise ReviewBundleError(f"{label} must remain inside the repository")
    return candidate


def git(args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def assert_private_output(output_dir: Path) -> None:
    resolved_review_root = REVIEW_ROOT.resolve()
    if output_dir != resolved_review_root and resolved_review_root not in output_dir.parents:
        raise ReviewBundleError("Review output must remain inside qa-v4/review/")

    tracked = git(["ls-files", "--", "qa-v4/review"]).stdout.strip()
    if tracked:
        raise ReviewBundleError(f"Refusing tracked review files: {tracked.splitlines()[0]}")

    sentinel = output_dir / ".privacy-sentinel"
    ignored = git(
        ["check-ignore", "-q", "--no-index", "--", repository_path(sentinel)],
        check=False,
    )
    if ignored.returncode != 0:
        raise ReviewBundleError("qa-v4/review/ is not ignored; refusing to write private pixels")


def safe_source_file(entry: dict[str, Any]) -> Path:
    value = entry.get("file")
    if not isinstance(value, str) or not value:
        raise ReviewBundleError(f"Capture {entry.get('id')!r} has no repository-relative file")
    source = resolve_repository_path(value, f"Capture {entry.get('id')!r}")
    if not source.is_file():
        raise ReviewBundleError(f"Missing capture file: {value}")
    expected = entry.get("sha256")
    actual = sha256_file(source)
    if not isinstance(expected, str) or actual != expected:
        raise ReviewBundleError(f"Capture hash mismatch: {value}")
    return source


def validate_capture_manifest(input_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not input_path.is_file():
        raise ReviewBundleError(f"Missing capture manifest: {repository_path(input_path)}")
    manifest = json.loads(input_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "CAPTURED":
        raise ReviewBundleError(f"Capture status is {manifest.get('status')!r}, expected 'CAPTURED'")
    if manifest.get("sourceIdentityCheck", {}).get("passed") is not True:
        raise ReviewBundleError("Capture source identity did not remain clean and stable")
    if manifest.get("previewIdentity", {}).get("passed") is not True:
        raise ReviewBundleError("Capture is not bound to a verified dist preview")

    entries: dict[str, dict[str, Any]] = {}
    for entry in manifest.get("captures", []):
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise ReviewBundleError("Capture manifest contains an invalid id")
        if identifier in entries:
            raise ReviewBundleError(f"Duplicate capture id: {identifier}")
        entries[identifier] = entry
    missing = [identifier for _, identifier in REVIEW_CAPTURES if identifier not in entries]
    if missing:
        raise ReviewBundleError(f"Missing review captures: {', '.join(missing)}")
    for _, identifier in REVIEW_CAPTURES:
        entry = entries[identifier]
        if entry.get("shellMode") != "energy-controlled" or entry.get("pose") != "front":
            raise ReviewBundleError(
                f"Review capture {identifier} is not fixed to energy-controlled/front"
            )
    expected_reflection_pointers = {
        "phase1b-reflection-left": [-0.85, 0],
        "phase1b-reflection-center": [0, 0],
        "phase1b-reflection-right": [0.85, 0],
    }
    for identifier, expected_pointer in expected_reflection_pointers.items():
        if entries[identifier].get("pointer") != expected_pointer:
            raise ReviewBundleError(f"Review capture {identifier} has an unexpected pointer")
    return manifest, entries


def save_sanitized_png(source: Path, destination: Path) -> dict[str, Any]:
    with Image.open(source) as opened:
        opened.load()
        image = opened.copy() if opened.mode in {"RGB", "RGBA"} else opened.convert("RGB")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.NamedTemporaryFile(
        prefix=f".{destination.stem}-",
        suffix=".png",
        dir=destination.parent,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        image.save(temporary_path, format="PNG", optimize=False, compress_level=6)
        with Image.open(temporary_path) as verified:
            verified.load()
            if len(verified.getexif()) != 0:
                raise ReviewBundleError(f"EXIF remained in sanitized PNG: {destination.name}")
            width, height = verified.size
            mode = verified.mode
        os.replace(temporary_path, destination)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return {
        "path": repository_path(destination),
        "sha256": sha256_file(destination),
        "bytes": destination.stat().st_size,
        "width": width,
        "height": height,
        "mode": mode,
        "exifPresent": False,
    }


def review_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow before scalable default-font support.
        return ImageFont.load_default()


def build_contact_sheet(png_records: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    columns, rows = 4, 4
    tile_width, tile_height = 360, 300
    padding, label_height = 12, 38
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), (8, 10, 11))
    draw = ImageDraw.Draw(sheet)
    font = review_font(16)

    for index, record in enumerate(png_records):
        row, column = divmod(index, columns)
        left, top = column * tile_width, row * tile_height
        draw.rectangle(
            (left + 4, top + 4, left + tile_width - 5, top + tile_height - 5),
            fill=(17, 21, 22),
            outline=(56, 65, 68),
            width=1,
        )
        source = resolve_repository_path(record["path"], "Contact-sheet source")
        with Image.open(source) as opened:
            opened.load()
            thumbnail = ImageOps.contain(
                opened.convert("RGB"),
                (tile_width - padding * 2, tile_height - label_height - padding * 2),
                method=Image.Resampling.LANCZOS,
            )
        image_left = left + (tile_width - thumbnail.width) // 2
        image_top = top + padding + (tile_height - label_height - padding * 2 - thumbnail.height) // 2
        sheet.paste(thumbnail, (image_left, image_top))
        draw.text(
            (left + padding, top + tile_height - label_height + 8),
            Path(record["path"]).name,
            fill=(224, 230, 228),
            font=font,
        )

    temporary = tempfile.NamedTemporaryFile(
        prefix=".phase-1b-contact-sheet-",
        suffix=".jpg",
        dir=output.parent,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        sheet.save(
            temporary_path,
            format="JPEG",
            quality=92,
            subsampling=0,
            optimize=False,
            progressive=False,
            exif=b"",
        )
        with Image.open(temporary_path) as verified:
            verified.load()
            if len(verified.getexif()) != 0:
                raise ReviewBundleError("EXIF remained in contact sheet")
            width, height = verified.size
        os.replace(temporary_path, output)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return {
        "path": repository_path(output),
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
        "width": width,
        "height": height,
        "layout": {"columns": columns, "rows": rows, "imageCount": len(png_records)},
        "exifPresent": False,
    }


def tool_version(executable: str) -> str:
    completed = subprocess.run(
        [executable, "-version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    return completed.stdout.splitlines()[0]


def transcode_session_video(entry: dict[str, Any], output: Path) -> dict[str, Any]:
    source = safe_source_file(entry)
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise ReviewBundleError("ffmpeg and ffprobe are required for the review MP4")

    temporary = tempfile.NamedTemporaryFile(
        prefix=".phase-1b-session-",
        suffix=".mp4",
        dir=output.parent,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    temporary.close()
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-an",
        "-vf",
        "fps=30,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-map_metadata",
        "-1",
        "-movflags",
        "+faststart",
        str(temporary_path),
    ]
    try:
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if completed.returncode != 0:
            raise ReviewBundleError(f"ffmpeg failed: {completed.stderr.strip()[-400:]}")
        probe = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,pix_fmt,width,height,avg_frame_rate,duration:format=duration",
                "-of",
                "json",
                str(temporary_path),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        probe_data = json.loads(probe.stdout)
        stream = (probe_data.get("streams") or [{}])[0]
        duration = float(stream.get("duration") or probe_data.get("format", {}).get("duration") or 0)
        if stream.get("codec_name") != "h264" or stream.get("pix_fmt") != "yuv420p" or duration <= 0:
            raise ReviewBundleError("Review MP4 failed codec, pixel-format, or duration validation")
        os.replace(temporary_path, output)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    return {
        "path": repository_path(output),
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
        "sourceSha256": entry["sha256"],
        "codec": stream["codec_name"],
        "pixelFormat": stream["pix_fmt"],
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "averageFrameRate": stream.get("avg_frame_rate"),
        "durationSeconds": duration,
        "audioIncluded": False,
        "metadataCopied": False,
        "ffmpeg": tool_version(ffmpeg),
    }


def write_local_manifest(
    capture_manifest: dict[str, Any],
    input_path: Path,
    output_dir: Path,
    png_records: list[dict[str, Any]],
    contact_sheet: dict[str, Any],
    session_video: dict[str, Any],
) -> Path:
    artifact_lines = [f"{Path(record['path']).name}:{record['sha256']}" for record in png_records]
    artifact_lines.extend(
        [
            f"{CONTACT_SHEET_NAME}:{contact_sheet['sha256']}",
            f"{SESSION_VIDEO_NAME}:{session_video['sha256']}",
        ]
    )
    source_identity = capture_manifest.get("sourceIdentity", {})
    source_identity_end = capture_manifest.get("sourceIdentityEnd", {})
    result = {
        "schemaVersion": 1,
        "private": True,
        "phase": "phase-1b-frozen-visual-calibration",
        "generator": GENERATOR,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceCaptureManifest": repository_path(input_path),
        "sourceCaptureManifestSha256": sha256_file(input_path),
        "sourceIdentity": {
            "head": source_identity.get("head"),
            "headTree": source_identity.get("headTree"),
            "branch": source_identity.get("branch"),
            "dirtyRepository": source_identity.get("dirtyRepository"),
            "dirtyWithinRuntimeScope": source_identity.get("dirtyWithinRuntimeScope"),
            "runtimeSourceSetSha256": source_identity.get("runtimeSourceSetSha256"),
        },
        "sourceIdentityEnd": {
            "head": source_identity_end.get("head"),
            "headTree": source_identity_end.get("headTree"),
            "dirtyRepository": source_identity_end.get("dirtyRepository"),
            "dirtyWithinRuntimeScope": source_identity_end.get("dirtyWithinRuntimeScope"),
            "runtimeSourceSetSha256": source_identity_end.get("runtimeSourceSetSha256"),
        },
        "sourceIdentityCheck": capture_manifest.get("sourceIdentityCheck"),
        "previewIdentity": capture_manifest.get("previewIdentity"),
        "pngCount": len(png_records),
        "pngs": png_records,
        "contactSheet": contact_sheet,
        "sessionVideo": session_video,
        "bundleSha256": canonical_sha256(artifact_lines),
        "privacy": {
            "directoryIgnored": True,
            "trackedReviewFiles": False,
            "absolutePathsStored": False,
            "privatePixelsCommitted": False,
        },
    }
    serialized = json.dumps(result, indent=2, ensure_ascii=True) + "\n"
    if str(REPO_ROOT) in serialized or '"/Users/' in serialized:
        raise ReviewBundleError("Refusing to write an absolute path into the local review manifest")
    output = output_dir / LOCAL_MANIFEST_NAME
    temporary = tempfile.NamedTemporaryFile(
        prefix=".review-manifest-",
        suffix=".json",
        dir=output_dir,
        mode="w",
        encoding="utf-8",
        delete=False,
    )
    temporary_path = Path(temporary.name)
    try:
        temporary.write(serialized)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary.close()
        os.replace(temporary_path, output)
    finally:
        if not temporary.closed:
            temporary.close()
        if temporary_path.exists():
            temporary_path.unlink()
    return output


def build(input_path: Path, output_dir: Path) -> dict[str, Any]:
    assert_private_output(output_dir)
    manifest, entries = validate_capture_manifest(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    png_records = []
    for output_name, capture_id in REVIEW_CAPTURES:
        entry = entries[capture_id]
        expected_review_name = entry.get("reviewName")
        if expected_review_name not in (None, output_name):
            raise ReviewBundleError(
                f"Capture {capture_id} reviewName is {expected_review_name!r}, expected {output_name!r}"
            )
        source = safe_source_file(entry)
        record = save_sanitized_png(source, output_dir / output_name)
        record.update({
            "name": output_name,
            "sourceCaptureId": capture_id,
            "sourceCaptureSha256": entry["sha256"],
        })
        png_records.append(record)

    contact_sheet = build_contact_sheet(png_records, output_dir / CONTACT_SHEET_NAME)
    session_entry = manifest.get("sessionVideo")
    if not isinstance(session_entry, dict):
        raise ReviewBundleError("Capture manifest has no private session video")
    session_video = transcode_session_video(session_entry, output_dir / SESSION_VIDEO_NAME)
    local_manifest = write_local_manifest(
        manifest,
        input_path,
        output_dir,
        png_records,
        contact_sheet,
        session_video,
    )

    tracked_after = git(["ls-files", "--", "qa-v4/review"]).stdout.strip()
    if tracked_after:
        raise ReviewBundleError("Review generation exposed tracked private files")
    return {
        "status": "PASS",
        "outputDirectory": repository_path(output_dir),
        "manifest": repository_path(local_manifest),
        "pngCount": len(png_records),
        "contactSheet": contact_sheet["path"],
        "sessionVideo": session_video["path"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()
    try:
        input_path = resolve_repository_path(arguments.input, "Capture manifest")
        output_dir = resolve_repository_path(arguments.output_dir, "Review output")
        result = build(input_path, output_dir)
    except (ReviewBundleError, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "BLOCKED", "error": str(error)}, indent=2))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
