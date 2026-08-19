#!/usr/bin/env python3
"""Round 1 contact sheets for human preview review.

Two sheets:

  v3-v4-split      every fixed review state, V3 on the left of the seam and V4
                   on the right, at identical offset, pointer and clip time.
  target-current   the Frozen target card crops next to the current V4 cards.

The second sheet is a LOOK reference for a human decision, not a measurement:
formal pixel truth stays BLOCKED and human optical-zone annotation is skipped,
so no number on this sheet may be read as a match score.

Both sheets contain Target-adjacent pixels and stay under qa-v4/review/.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUND_DIR = REPO_ROOT / "qa-v4/review/round-1"
STATES_DIR = ROUND_DIR / "states"
FROZEN_CROPS = REPO_ROOT / "qa-v4/reference/frozen-visual/crops"
INK = (232, 236, 230)
MUTED = (140, 152, 149)
PANEL = (16, 20, 21)
BACKGROUND = (8, 10, 11)
ACCENT = (201, 243, 91)


class SheetError(RuntimeError):
    """Fail-closed error for a contact sheet that cannot be trusted."""


def font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def repository_path(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def assert_private_output() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "--", "qa-v4/review"],
        cwd=REPO_ROOT, text=True, capture_output=True, check=True,
    ).stdout.strip()
    if tracked:
        raise SheetError(f"Refusing tracked review files: {tracked.splitlines()[0]}")
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", "qa-v4/review/round-1/.sentinel"],
        cwd=REPO_ROOT, check=False,
    )
    if ignored.returncode != 0:
        raise SheetError("qa-v4/review/ is not ignored; refusing to write preview pixels")


def split_tile(v3_path: Path, v4_path: Path, size: tuple[int, int]) -> Image.Image:
    """One state, V3 left of the seam and V4 right of it."""
    with Image.open(v3_path) as left_source, Image.open(v4_path) as right_source:
        left = left_source.convert("RGB").resize(size, Image.Resampling.LANCZOS)
        right = right_source.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    tile = Image.new("RGB", size, BACKGROUND)
    half = size[0] // 2
    tile.paste(left.crop((0, 0, half, size[1])), (0, 0))
    tile.paste(right.crop((half, 0, size[0], size[1])), (half, 0))
    draw = ImageDraw.Draw(tile)
    draw.line((half, 0, half, size[1]), fill=ACCENT, width=2)
    return tile


def build_split_sheet(states: list[str], output: Path) -> dict[str, Any]:
    columns, rows = 3, 5
    tile_w, tile_h = 452, 283
    label_h = 26
    pad = 10
    sheet = Image.new(
        "RGB",
        (columns * (tile_w + pad) + pad, rows * (tile_h + label_h + pad) + pad + 34),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, 10), "ROUND 1 · V3 (left)  |  V4 (right) · identical state, offset, pointer and clip time",
              fill=INK, font=font(15))
    used: list[str] = []
    for index, state in enumerate(states):
        v3_path = STATES_DIR / "v3" / f"{state}.png"
        v4_path = STATES_DIR / "v4" / f"{state}.png"
        if not v3_path.is_file() or not v4_path.is_file():
            continue
        row, column = divmod(index, columns)
        x = pad + column * (tile_w + pad)
        y = 34 + pad + row * (tile_h + label_h + pad)
        sheet.paste(split_tile(v3_path, v4_path, (tile_w, tile_h)), (x, y))
        draw.rectangle((x, y + tile_h, x + tile_w, y + tile_h + label_h), fill=PANEL)
        draw.text((x + 8, y + tile_h + 7), state.replace("-", " ").upper(), fill=MUTED, font=font(12))
        used.append(state)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="JPEG", quality=92, subsampling=0, exif=b"")
    return {"path": repository_path(output), "states": used, "size": list(sheet.size)}


def contain(image: Image.Image, box: tuple[int, int]) -> Image.Image:
    copy = image.convert("RGB").copy()
    copy.thumbnail(box, Image.Resampling.LANCZOS)
    return copy


def build_target_current_sheet(pairs: list[tuple[str, Path, Path]], output: Path) -> dict[str, Any]:
    tile_w, tile_h = 430, 300
    label_h = 24
    pad = 12
    header = 58
    sheet = Image.new(
        "RGB",
        (len(pairs) * (tile_w + pad) + pad, header + 2 * (tile_h + label_h + pad) + pad),
        BACKGROUND,
    )
    draw = ImageDraw.Draw(sheet)
    draw.text((pad, 10), "ROUND 1 · TARGET (top) vs CURRENT V4 (bottom)", fill=INK, font=font(16))
    draw.text((pad, 32),
              "Look reference for a human decision. Formal pixel truth is BLOCKED; this is not a match score.",
              fill=MUTED, font=font(12))
    used: list[str] = []
    for index, (label, target_path, current_path) in enumerate(pairs):
        if not target_path.is_file() or not current_path.is_file():
            continue
        x = pad + index * (tile_w + pad)
        for row, source in enumerate((target_path, current_path)):
            y = header + row * (tile_h + label_h + pad)
            with Image.open(source) as opened:
                opened.load()
                thumbnail = contain(opened, (tile_w, tile_h))
            draw.rectangle((x, y, x + tile_w, y + tile_h), fill=PANEL)
            sheet.paste(
                thumbnail,
                (x + (tile_w - thumbnail.width) // 2, y + (tile_h - thumbnail.height) // 2),
            )
            caption = f"TARGET · {label}" if row == 0 else f"CURRENT V4 · {label}"
            draw.text((x + 8, y + tile_h + 6), caption, fill=MUTED, font=font(12))
        used.append(label)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="JPEG", quality=92, subsampling=0, exif=b"")
    return {"path": repository_path(output), "pairs": used, "size": list(sheet.size)}


def crop_center_card(source: Path, destination: Path, quad: list[list[float]] | None) -> Path:
    """Crops exactly the centred card, using its projected quad when available."""
    with Image.open(source) as opened:
        opened.load()
        image = opened.convert("RGB")
    width, height = image.size
    if quad:
        xs = [point[0] * width for point in quad]
        ys = [point[1] * height for point in quad]
        margin_x = (max(xs) - min(xs)) * 0.06
        margin_y = (max(ys) - min(ys)) * 0.06
        box = (
            max(0, int(min(xs) - margin_x)),
            max(0, int(min(ys) - margin_y)),
            min(width, int(max(xs) + margin_x)),
            min(height, int(max(ys) + margin_y)),
        )
    else:
        half_w, half_h = int(width * 0.2), int(height * 0.265)
        cx, cy = width // 2, height // 2
        box = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
    crop = image.crop(box)
    destination.parent.mkdir(parents=True, exist_ok=True)
    crop.save(destination, format="PNG")
    return destination


def main() -> int:
    assert_private_output()
    manifest_path = ROUND_DIR / "capture-manifest.local.json"
    if not manifest_path.is_file():
        raise SheetError("Run scripts/v4/capture-round1-preview.mjs first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    states = [entry["id"] for entry in manifest["states"]]

    split = build_split_sheet(states, ROUND_DIR / "contact-v3-v4-split.jpg")

    current_dir = ROUND_DIR / "current-cards"
    quads = {entry["id"]: entry.get("centreQuad") for entry in manifest["states"]}
    pairs: list[tuple[str, Path, Path]] = []
    for label, category, state in (
        ("bright", "bright-front", "07-bright-card"),
        ("dark", "dark-front", "08-dark-card"),
        ("high texture", "high-texture", "09-high-texture-card"),
        ("low texture", "low-texture", "10-low-texture-card"),
    ):
        target = FROZEN_CROPS / f"{category}.png"
        state_frame = STATES_DIR / "v4" / f"{state}.png"
        if not state_frame.is_file():
            continue
        current = crop_center_card(state_frame, current_dir / f"{state}.png", quads.get(state))
        pairs.append((label, target, current))
    target_current = build_target_current_sheet(pairs, ROUND_DIR / "contact-target-current.jpg")

    result = {
        "schemaVersion": 1,
        "private": True,
        "generator": "round1-contact-sheets-v1",
        "formalPixelTruth": "BLOCKED",
        "humanAnnotation": "SKIPPED_BY_PRODUCT_OWNER",
        "splitSheet": split,
        "targetCurrentSheet": target_current,
    }
    (ROUND_DIR / "contact-sheets.local.json").write_text(f"{json.dumps(result, indent=2)}\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SheetError as error:
        print(f"FAILED: {error}")
        raise SystemExit(1) from error
