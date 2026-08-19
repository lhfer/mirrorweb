#!/usr/bin/env python3
"""Validate the committed sanitized V4 reference manifests."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(schema_path: Path, instance_path: Path) -> dict[str, object]:
    schema = load(schema_path)
    instance = load(instance_path)
    errors = sorted(Draft202012Validator(schema).iter_errors(instance), key=lambda error: list(error.path))
    if errors:
        rendered = [f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors]
        raise SystemExit(json.dumps({"status": "FAILED", "manifest": str(instance_path.relative_to(ROOT)), "errors": rendered}, indent=2))
    return {"manifest": str(instance_path.relative_to(ROOT)), "status": "PASSED"}


def main() -> None:
    calibration = load(ROOT / "config/calibration.v4.json")
    frozen_path = ROOT / calibration["referenceClasses"]["frozenVisual"]["sanitizedManifest"]
    controlled_path = ROOT / calibration["referenceClasses"]["controlledCapture"]["sanitizedManifest"]
    results = [
        validate(ROOT / "qa-v4/reference/roi-mask.schema.json", frozen_path),
        validate(ROOT / "qa-v4/reference/controlled-reference.schema.json", controlled_path),
    ]
    print(json.dumps({"status": "PASSED", "results": results}, indent=2))


if __name__ == "__main__":
    main()
