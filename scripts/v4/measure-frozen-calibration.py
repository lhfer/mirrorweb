#!/usr/bin/env python3
"""Measure Phase 1B card-normalized Frozen Visual calibration evidence.

Private pixels are read only from hash-bound inputs and any pixel overlays are
written only to the requested review directory.  The public aggregate contains
hashes, scalar/profile metrics, explicit evidence states, and caveats.  It never
contains image payloads, private paths, or a whole-card SSIM score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from jsonschema import Draft202012Validator

from lib.roi_metrics import (
    MeasurementUnavailable,
    aggregate_pose_width_distributions,
    background_response,
    card_transform,
    compute_optical_zone_metrics,
    content_bending_width,
    corner_refraction_signature,
    decode_optical_zone_palette,
    dispersion_width,
    draw_private_edge_overlay,
    highlight_mask_metrics,
    highlight_metrics,
    highlight_path,
    infer_card_quad_from_silhouette,
    load_mask,
    load_rgb,
    normalized_profiles,
    relative_point,
    relative_scalar,
    relative_vector,
    sharpness_ratio,
    shell_composite_delta_metrics,
    sidewall_content_compression,
    summarize_profiles,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FROZEN_MANIFEST = REPO_ROOT / "qa-v4/reference/frozen-visual/frozen-visual.sanitized.json"
DEFAULT_FROZEN_ROOT = REPO_ROOT / "qa-v4/reference/frozen-visual"
DEFAULT_PRIORS = REPO_ROOT / "qa-v4/reference/frozen-visual/calibration-priors.sanitized.json"
DEFAULT_ANNOTATIONS = REPO_ROOT / "qa-v4/reference/frozen-visual/annotations.private.json"
DEFAULT_REVIEW_DIR = REPO_ROOT / "qa-v4/review/phase-1b"
DEFAULT_OUTPUT = REPO_ROOT / "qa-v4/results/frozen-visual-calibration.json"
GENERATOR = "phase1b-frozen-calibration-v1"
SHA256_PATTERN_LENGTH = 64

FROZEN_CATEGORY_IDS = (
    "bright-front",
    "dark-front",
    "high-texture",
    "low-texture",
    "left-tilt",
    "right-tilt",
    "pointer-before",
    "pointer-after",
)
MASK_NAMES = (
    "card-silhouette",
    "center-face",
    "optical-shoulder",
    "lens-rim",
    "sidewall",
    "highlight",
    "typography",
    "gutter",
)
ROLE_SPECS: dict[str, dict[str, str]] = {
    "bright": {"targetCategory": "bright-front", "localCaptureId": "v4-white"},
    "dark": {"targetCategory": "dark-front", "localCaptureId": "v4-black"},
    "highTexture": {"targetCategory": "high-texture", "localCaptureId": "v4-high-frequency-photo"},
    "lowTexture": {"targetCategory": "low-texture", "localCaptureId": "v4-low-frequency-flat"},
    # The Frozen set has only six non-pointer roles. Front intentionally reuses
    # high-texture rather than misrepresenting a clipped pointer frame.
    "front": {"targetCategory": "high-texture", "localCaptureId": "v4-checker"},
    "leftTilt": {"targetCategory": "left-tilt", "localPose": "left"},
    "rightTilt": {"targetCategory": "right-tilt", "localPose": "right"},
}
RELATIVE_METRIC_IDS = (
    "rimWidthRelativeError",
    "shoulderWidthRelativeError",
    "highlightWidthRelativeError",
    "highlightPositionRelativeError",
    "centerRimSharpnessRatioError",
    "dispersionWidthRelativeError",
    "brightDarkBackgroundResponseDifference",
    "cornerRefractionSignature",
    "sidewallContentCompression",
    "targetLocalEdgeRoiOverlay",
)


@dataclass
class EvidenceEntry:
    raw: dict[str, Any]
    path: Path

    @property
    def identifier(self) -> str:
        return str(self.raw.get("id") or self.raw.get("role") or self.path.name)


@dataclass
class LocalContext:
    manifest: dict[str, Any]
    entries: list[EvidenceEntry]
    edge_entry: EvidenceEntry
    transform: Any
    rectified_edge: np.ndarray
    silhouette: np.ndarray
    optical_zones: dict[str, Any]
    profiles: dict[str, Any]


@dataclass
class PoseContext:
    pose: str
    zone_entry: EvidenceEntry
    transform: Any
    rectified_zones: np.ndarray
    silhouette: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a fail-closed Phase 1B Frozen Visual calibration aggregate")
    parser.add_argument("--local-capture", type=Path, required=True, help="Private Phase 1B local capture manifest")
    parser.add_argument("--frozen-manifest", type=Path, default=DEFAULT_FROZEN_MANIFEST)
    parser.add_argument("--frozen-private-root", type=Path, default=DEFAULT_FROZEN_ROOT)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    parser.add_argument("--priors", type=Path, default=DEFAULT_PRIORS)
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MeasurementUnavailable(f"JSON root must be an object: {path.name}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def require_private_review_directory(path: Path) -> None:
    review_root = (REPO_ROOT / "qa-v4/review").resolve()
    try:
        relative = path.resolve().relative_to(review_root)
    except ValueError as error:
        raise MeasurementUnavailable("Private pixel overlays must remain inside qa-v4/review") from error
    sentinel = review_root / relative / ".privacy-sentinel"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", str(sentinel)],
        cwd=REPO_ROOT,
        check=False,
    )
    if ignored.returncode != 0:
        raise MeasurementUnavailable("Private pixel overlay directory is not ignored by Git")
    tracked = subprocess.run(
        ["git", "ls-files", "--", str((Path("qa-v4/review") / relative).as_posix())],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if tracked.returncode != 0 or tracked.stdout.strip():
        raise MeasurementUnavailable("Private pixel overlay directory contains tracked files")


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == SHA256_PATTERN_LENGTH and all(character in "0123456789abcdef" for character in value)


def require_hash(path: Path, expected: Any, label: str) -> None:
    if not valid_sha256(expected):
        raise MeasurementUnavailable(f"{label} has no valid SHA-256")
    if not path.is_file():
        raise MeasurementUnavailable(f"{label} is missing")
    actual = sha256_file(path)
    if actual != expected:
        raise MeasurementUnavailable(f"{label} hash mismatch")


def repository_or_manifest_file(value: str, manifest_path: Path) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    repository_candidate = (REPO_ROOT / candidate).resolve()
    if repository_candidate.is_file():
        return repository_candidate
    return (manifest_path.parent / candidate).resolve()


def verify_frozen(
    sanitized_path: Path,
    private_root: Path,
) -> tuple[dict[str, Any], dict[str, dict[str, Path]], dict[str, Any]]:
    if not sanitized_path.is_file():
        raise MeasurementUnavailable("Frozen sanitized manifest is missing")
    sanitized = read_json(sanitized_path)
    if sanitized.get("referenceClass") != "frozen-visual":
        raise MeasurementUnavailable("Frozen manifest has the wrong reference class")
    categories = sanitized.get("categories")
    if not isinstance(categories, list):
        raise MeasurementUnavailable("Frozen manifest categories are missing")
    by_id = {item.get("id"): item for item in categories if isinstance(item, dict)}
    if set(by_id) != set(FROZEN_CATEGORY_IDS):
        raise MeasurementUnavailable("Frozen manifest does not contain the exact eight-category set")
    if sanitized.get("summary", {}).get("opticalZoneWidthsMeasured") is not False:
        raise MeasurementUnavailable("Frozen v1 manifest must remain explicit that optical zone widths are unmeasured")

    private_manifest_path = private_root / "manifest.private.json"
    if not private_manifest_path.is_file():
        raise MeasurementUnavailable("Frozen private manifest is missing")
    private = read_json(private_manifest_path)
    if private.get("private") is not True:
        raise MeasurementUnavailable("Frozen private manifest is not marked private")
    if private.get("sourceSha256") != sanitized.get("source", {}).get("videoSha256"):
        raise MeasurementUnavailable("Frozen source identity differs between private and sanitized manifests")
    if private.get("sanitizedManifestSha256") != canonical_sha256(sanitized):
        raise MeasurementUnavailable("Frozen private manifest is not bound to the sanitized manifest")
    private_categories = {
        item.get("id"): item for item in private.get("categories", []) if isinstance(item, dict)
    }
    if set(private_categories) != set(FROZEN_CATEGORY_IDS):
        raise MeasurementUnavailable("Frozen private manifest category set differs from sanitized evidence")

    files: dict[str, dict[str, Path]] = {}
    artifact_identity: list[dict[str, Any]] = []
    for category_id in FROZEN_CATEGORY_IDS:
        category = by_id[category_id]
        private_category = private_categories[category_id]
        category_files = {
            "frame": private_root / "frames" / f"{category_id}.png",
            "crop": private_root / "crops" / f"{category_id}.png",
            "overlay": private_root / "overlays" / f"{category_id}.png",
        }
        require_hash(category_files["frame"], category.get("frameSha256"), f"Frozen {category_id} frame")
        require_hash(category_files["crop"], category.get("cropSha256"), f"Frozen {category_id} crop")
        require_hash(category_files["overlay"], category.get("overlaySha256"), f"Frozen {category_id} overlay")
        private_hashes = private_category.get("hashes", {})
        if (
            private_hashes.get("frame") != category.get("frameSha256")
            or private_hashes.get("crop") != category.get("cropSha256")
            or private_hashes.get("overlay") != category.get("overlaySha256")
        ):
            raise MeasurementUnavailable(f"Frozen {category_id} private hashes differ from sanitized evidence")
        for mask_name in MASK_NAMES:
            mask_file = private_root / "masks" / category_id / f"{mask_name}.png"
            expected = category.get("masks", {}).get(mask_name, {}).get("sha256")
            require_hash(mask_file, expected, f"Frozen {category_id} {mask_name} mask")
            if private_hashes.get("masks", {}).get(mask_name) != expected:
                raise MeasurementUnavailable(f"Frozen {category_id} {mask_name} private hash differs")
            category_files[mask_name] = mask_file
        files[category_id] = category_files
        artifact_identity.append({
            "id": category_id,
            "frameSha256": category["frameSha256"],
            "cropSha256": category["cropSha256"],
            "overlaySha256": category["overlaySha256"],
            "maskSha256": {name: category["masks"][name]["sha256"] for name in MASK_NAMES},
        })
    if canonical_sha256(artifact_identity) != sanitized.get("summary", {}).get("artifactSetSha256"):
        raise MeasurementUnavailable("Frozen artifact-set identity cannot be recomputed")
    return sanitized, files, private


def flatten_local_entries(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for key in ("captures", "pointerPath", "abCaptures", "poseCaptures"):
        value = manifest.get(key, [])
        if isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict))
    variants = manifest.get("variants")
    if isinstance(variants, dict):
        for variant_id, variant in variants.items():
            if not isinstance(variant, dict):
                continue
            for key in ("captures", "pointerPath"):
                for item in variant.get(key, []) if isinstance(variant.get(key), list) else []:
                    if isinstance(item, dict):
                        entries.append({**item, "shellVariant": item.get("shellVariant", variant_id)})
    return entries


def sanitized_runtime_files(identity: Mapping[str, Any]) -> list[dict[str, str]]:
    raw_files = identity.get("files")
    if not isinstance(raw_files, list) or not raw_files:
        raise MeasurementUnavailable("Phase 1B local capture has no runtime source file identity")
    files: list[dict[str, str]] = []
    for raw in raw_files:
        if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
            raise MeasurementUnavailable("Runtime source identity contains a malformed file entry")
        value = raw["path"].replace("\\", "/")
        candidate = Path(value)
        if candidate.is_absolute() or value.startswith("/") or ".." in candidate.parts or value in ("", "."):
            raise MeasurementUnavailable("Runtime source identity contains a non-repository-relative path")
        digest = raw.get("sha256")
        if not valid_sha256(digest):
            raise MeasurementUnavailable(f"Runtime source identity has an invalid hash for {value}")
        files.append({"path": value, "sha256": digest})
    if len({entry["path"] for entry in files}) != len(files):
        raise MeasurementUnavailable("Runtime source identity contains duplicate paths")
    expected = hashlib.sha256(
        "\n".join(f"{entry['path']}:{entry['sha256']}" for entry in files).encode("utf-8")
    ).hexdigest()
    if expected != identity.get("runtimeSourceSetSha256"):
        raise MeasurementUnavailable("Runtime source file list does not reproduce runtimeSourceSetSha256")
    return files


def verify_capture_attestation(manifest: Mapping[str, Any], identity: Mapping[str, Any]) -> None:
    check = manifest.get("sourceIdentityCheck")
    if not isinstance(check, dict) or check.get("passed") is not True:
        raise MeasurementUnavailable("Phase 1B local capture did not preserve a clean source identity")
    ending_identity = manifest.get("sourceIdentityEnd")
    if (
        not isinstance(ending_identity, dict)
        or ending_identity.get("head") != identity.get("head")
        or ending_identity.get("runtimeSourceSetSha256") != identity.get("runtimeSourceSetSha256")
        or ending_identity.get("dirtyRepository") is not False
        or ending_identity.get("dirtyWithinRuntimeScope") is not False
    ):
        raise MeasurementUnavailable("Phase 1B capture end identity is missing, dirty, or drifted")
    preview = manifest.get("previewIdentity")
    if not isinstance(preview, dict) or preview.get("passed") is not True or preview.get("violations") != []:
        raise MeasurementUnavailable("Phase 1B capture is not bound to a clean dist preview")
    dist = manifest.get("distIdentity")
    if (
        not isinstance(dist, dict)
        or not valid_sha256(dist.get("treeSha256"))
        or not isinstance(dist.get("fileCount"), int)
        or dist.get("fileCount", 0) <= 0
    ):
        raise MeasurementUnavailable("Phase 1B capture lacks a valid dist tree identity")
    runtime_contract = manifest.get("runtimeContract")
    if not isinstance(runtime_contract, dict) or runtime_contract.get("passed") is not True:
        raise MeasurementUnavailable("Phase 1B runtime optics contract did not pass")
    graphics = manifest.get("environment", {}).get("graphics", {})
    adapter = graphics.get("adapter", {}) if isinstance(graphics, dict) else {}
    if (
        not isinstance(graphics, dict)
        or not isinstance(adapter, dict)
        or graphics.get("webgpuAvailable") is not True
        or graphics.get("softwareRendererDetected") is not False
        or adapter.get("isFallbackAdapter") is not False
    ):
        raise MeasurementUnavailable("Phase 1B capture lacks a non-fallback hardware WebGPU adapter")
    if manifest.get("pageErrorCount") != 0:
        raise MeasurementUnavailable("Phase 1B capture contains page errors")
    served = manifest.get("servedResourceIdentity")
    served_resources = served.get("resources") if isinstance(served, dict) else None
    if (
        not isinstance(served, dict)
        or not isinstance(served_resources, list)
        or not valid_sha256(served.get("manifestSha256"))
        or not isinstance(served.get("resourceCount"), int)
        or served.get("resourceCount", 0) <= 0
        or served.get("resourceCount") != len(served_resources)
    ):
        raise MeasurementUnavailable("Phase 1B capture lacks a valid served-resource identity")
    if not valid_sha256(manifest.get("screenshotSetSha256")):
        raise MeasurementUnavailable("Phase 1B capture lacks a screenshot-set identity")
    if not valid_sha256(manifest.get("sessionVideo", {}).get("sha256")):
        raise MeasurementUnavailable("Phase 1B capture lacks a session-video identity")
    capture_script = manifest.get("captureScript")
    expected_capture_script = REPO_ROOT / "scripts/v4/capture-optics-lab.mjs"
    if (
        not isinstance(capture_script, dict)
        or capture_script.get("path") != "scripts/v4/capture-optics-lab.mjs"
        or capture_script.get("sha256") != sha256_file(expected_capture_script)
        or capture_script.get("version") != "optics-lab-capture-phase1b-v2"
    ):
        raise MeasurementUnavailable("Phase 1B capture script identity is missing or stale")


def verify_local_capture(path: Path) -> tuple[dict[str, Any], list[EvidenceEntry]]:
    if not path.is_file():
        raise MeasurementUnavailable("Phase 1B local capture manifest is missing")
    manifest = read_json(path)
    if manifest.get("status") != "CAPTURED":
        raise MeasurementUnavailable("Phase 1B local capture status is not CAPTURED")
    identity = manifest.get("sourceIdentity")
    if not isinstance(identity, dict) or not valid_sha256(identity.get("runtimeSourceSetSha256")):
        raise MeasurementUnavailable("Phase 1B local capture lacks runtime source identity")
    if identity.get("dirtyRepository") is not False or identity.get("dirtyWithinRuntimeScope") is not False:
        raise MeasurementUnavailable("Phase 1B local capture is not clean")
    if not isinstance(identity.get("head"), str) or len(identity["head"]) != 40:
        raise MeasurementUnavailable("Phase 1B local capture is not bound to a full Git HEAD")
    sanitized_runtime_files(identity)
    verify_capture_attestation(manifest, identity)
    raw_entries = flatten_local_entries(manifest)
    if not raw_entries:
        raise MeasurementUnavailable("Phase 1B local capture contains no pixel evidence")
    entries = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_entries:
        if not isinstance(raw.get("file"), str):
            raise MeasurementUnavailable("Local evidence entry has no file")
        file = repository_or_manifest_file(raw["file"], path)
        require_hash(file, raw.get("sha256"), f"Local capture {raw.get('id', file.name)}")
        key = (str(raw.get("id")), str(raw.get("sha256")))
        if key in seen:
            continue
        state = raw.get("state")
        if not isinstance(state, dict):
            raise MeasurementUnavailable(f"Local capture {raw.get('id')} has no runtime state")
        for field in ("pattern", "mode", "debug", "shellMode", "pose"):
            declared = raw.get(field)
            if declared is not None and state.get(field) != declared:
                raise MeasurementUnavailable(
                    f"Local capture {raw.get('id')} state differs from declared {field}"
                )
        seen.add(key)
        entries.append(EvidenceEntry(raw, file))
    return manifest, entries


def load_annotations(path: Path, frozen: Mapping[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not path.is_file():
        return None, {
            "status": "MISSING",
            "approvedCategoryCount": 0,
            "reason": "private-human-reviewed-annotations-missing",
        }
    annotations = read_json(path)
    annotation_schema = read_json(REPO_ROOT / "qa-v4/reference/frozen-visual/annotations.schema.json")
    schema_errors = sorted(
        Draft202012Validator(annotation_schema).iter_errors(annotations),
        key=lambda error: list(error.path),
    )
    if schema_errors:
        first = schema_errors[0]
        location = ".".join(map(str, first.path)) or "<root>"
        raise MeasurementUnavailable(f"Frozen annotations schema failed at {location}: {first.message}")
    if annotations.get("referenceClass") != "frozen-visual-human-calibration":
        raise MeasurementUnavailable("Frozen annotations have the wrong reference class")
    if annotations.get("private") is not True:
        raise MeasurementUnavailable("Frozen annotations are not marked private")
    if annotations.get("reviewStatus") not in ("PENDING", "APPROVED", "REJECTED"):
        raise MeasurementUnavailable("Frozen annotations have an invalid review status")
    if annotations.get("sourceVideoSha256") != frozen.get("source", {}).get("videoSha256"):
        raise MeasurementUnavailable("Frozen annotations are bound to a different source video")
    frozen_categories = {item["id"]: item for item in frozen["categories"]}
    annotated = annotations.get("categories", {})
    if not isinstance(annotated, dict):
        raise MeasurementUnavailable("Frozen annotation categories are malformed")
    quad_approved = 0
    feature_approved = 0
    highlight_approved = 0
    for category_id, value in annotated.items():
        if category_id not in frozen_categories or not isinstance(value, dict):
            raise MeasurementUnavailable("Frozen annotations contain an unknown category")
        if value.get("sourceFrameSha256") != frozen_categories[category_id]["frameSha256"]:
            raise MeasurementUnavailable(f"Frozen annotation frame hash differs for {category_id}")
        if (
            annotations.get("reviewStatus") == "APPROVED"
            and value.get("reviewStatus") == "APPROVED"
            and value.get("quadReviewStatus") == "APPROVED"
        ):
            quad_approved += 1
            if value.get("approvals", {}).get("naturalFeatureSignature") is True:
                feature_approved += 1
            if value.get("approvals", {}).get("existingHighlightMask") is True:
                highlight_approved += 1
    return annotations, {
        "status": "APPROVED" if feature_approved == len(FROZEN_CATEGORY_IDS) else "PARTIAL",
        "approvedCategoryCount": feature_approved,
        "quadApprovedCategoryCount": quad_approved,
        "featureSignatureApprovedCategoryCount": feature_approved,
        "highlightMaskApprovedCategoryCount": highlight_approved,
        "requiredCategoryCount": len(FROZEN_CATEGORY_IDS),
        "annotationSetSha256": canonical_sha256(annotations),
    }


def load_priors(path: Path) -> dict[str, Any]:
    priors = read_json(path)
    rim = priors.get("targetStrongLensRim")
    if not isinstance(rim, dict) or rim.get("evidenceClass") != "provisional-user-measurement":
        raise MeasurementUnavailable("Strong Lens Rim prior is missing its provisional evidence class")
    if (
        rim.get("status") != "CONDITIONAL"
        or rim.get("mayClaimPixelTruth") is not False
        or rim.get("maximumResultStatus") != "CONDITIONAL"
    ):
        raise MeasurementUnavailable("Strong Lens Rim prior does not preserve the conditional acceptance ceiling")
    minimum, maximum, center = rim.get("min"), rim.get("max"), rim.get("center")
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (minimum, maximum, center)):
        raise MeasurementUnavailable("Strong Lens Rim prior values are invalid")
    if not minimum <= center <= maximum:
        raise MeasurementUnavailable("Strong Lens Rim prior center is outside its range")
    return priors


def entry_by_id(entries: Sequence[EvidenceEntry], identifier: str) -> EvidenceEntry | None:
    return next((entry for entry in entries if entry.raw.get("id") == identifier), None)


def entry_by_predicate(entries: Sequence[EvidenceEntry], predicate: Any) -> EvidenceEntry | None:
    return next((entry for entry in entries if predicate(entry.raw)), None)


def _normalized_shell_mode(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower().replace("_", "-")
    aliases = {
        "a": "additive",
        "current": "additive",
        "additive-shell": "additive",
        "b": "energy-controlled",
        "energy": "energy-controlled",
        "premultiplied": "energy-controlled",
        "fresnel-premultiplied": "energy-controlled",
    }
    return aliases.get(normalized, normalized)


def variant_name(raw: Mapping[str, Any]) -> str | None:
    experiment = raw.get("experimentVariant")
    experiment_mode = _normalized_shell_mode(experiment.get("shellMode")) if isinstance(experiment, dict) else None
    direct_mode = _normalized_shell_mode(raw.get("shellMode"))
    legacy_mode = _normalized_shell_mode(raw.get("shellVariant") or raw.get("variant") or raw.get("composition"))
    observed = [value for value in (experiment_mode, direct_mode, legacy_mode) if value is not None]
    if len(set(observed)) > 1:
        return None
    return observed[0] if observed else None


def experiment_view(raw: Mapping[str, Any]) -> str | None:
    experiment = raw.get("experimentVariant")
    value = experiment.get("view") if isinstance(experiment, dict) else None
    if not isinstance(value, str):
        value = raw.get("debug")
    return value.strip().lower() if isinstance(value, str) else None


def entry_quad(raw: Mapping[str, Any], image_shape: Sequence[int]) -> Any | None:
    if isinstance(raw.get("cardQuad"), list):
        return card_transform(raw["cardQuad"], source_shape=image_shape, normalized=False)
    if isinstance(raw.get("cardQuadNormalized"), list):
        return card_transform(raw["cardQuadNormalized"], source_shape=image_shape, normalized=True)
    geometry = raw.get("cardGeometry")
    if isinstance(geometry, dict):
        if isinstance(geometry.get("quad"), list):
            return card_transform(geometry["quad"], source_shape=image_shape, normalized=False)
        if isinstance(geometry.get("quadNormalized"), list):
            return card_transform(geometry["quadNormalized"], source_shape=image_shape, normalized=True)
    return None


def build_local_context(manifest: dict[str, Any], entries: list[EvidenceEntry]) -> LocalContext:
    edge = entry_by_id(entries, "phase1b-optical-zones-front")
    if edge is None:
        raise MeasurementUnavailable("Local Phase 1B capture requires phase1b-optical-zones-front")
    if (
        edge.raw.get("role") != "phase1b-optical-zones"
        or edge.raw.get("debug") != "optical-zones"
        or edge.raw.get("pose") != "front"
    ):
        raise MeasurementUnavailable("phase1b-optical-zones-front violates the categorical front-pose contract")
    edge_rgb = load_rgb(edge.path)
    mapping = entry_quad(edge.raw, edge_rgb.shape)
    if mapping is None:
        source_decoded = decode_optical_zone_palette(
            edge_rgb,
            required_zones=("centerFace", "opticalShoulder", "strongLensRim"),
        )
        quad = infer_card_quad_from_silhouette(source_decoded["silhouette"])
        mapping = card_transform(quad, source_shape=edge_rgb.shape)
    rectified = mapping.rectify(edge_rgb)
    decoded = decode_optical_zone_palette(
        rectified,
        required_zones=("centerFace", "opticalShoulder", "strongLensRim"),
    )
    silhouette = decoded["silhouette"]
    zones = compute_optical_zone_metrics(
        rectified,
        silhouette,
        required_zones=("centerFace", "opticalShoulder", "strongLensRim"),
    )
    profiles = normalized_profiles(rectified, silhouette)
    return LocalContext(manifest, entries, edge, mapping, rectified, silhouette, zones, profiles)


def pose_context(context: LocalContext, pose: str) -> PoseContext:
    if pose == "front":
        return PoseContext(
            pose="front",
            zone_entry=context.edge_entry,
            transform=context.transform,
            rectified_zones=context.rectified_edge,
            silhouette=context.silhouette,
        )
    zone_entry = entry_by_id(context.entries, f"phase1b-optical-zones-{pose}")
    if zone_entry is None:
        raise MeasurementUnavailable(f"phase1b-optical-zones-{pose} is required for pose rectification")
    if (
        zone_entry.raw.get("role") != "phase1b-optical-zones"
        or zone_entry.raw.get("debug") != "optical-zones"
        or zone_entry.raw.get("pose") != pose
    ):
        raise MeasurementUnavailable(f"phase1b-optical-zones-{pose} violates the pose evidence contract")
    zone_rgb = load_rgb(zone_entry.path)
    mapping = entry_quad(zone_entry.raw, zone_rgb.shape)
    if mapping is None:
        source_decoded = decode_optical_zone_palette(zone_rgb)
        quad = infer_card_quad_from_silhouette(source_decoded["silhouette"])
        mapping = card_transform(quad, source_shape=zone_rgb.shape)
    rectified = mapping.rectify(zone_rgb)
    decoded = decode_optical_zone_palette(rectified)
    return PoseContext(pose, zone_entry, mapping, rectified, decoded["silhouette"])


def rectify_entry(entry: EvidenceEntry, context: LocalContext, *, mapping: Any | None = None) -> np.ndarray:
    rgb = load_rgb(entry.path)
    selected = mapping or entry_quad(entry.raw, rgb.shape) or context.transform
    return selected.rectify(rgb)


def blocked(reason: str, *, evidence: Any = None) -> dict[str, Any]:
    return {"status": "BLOCKED", "value": None, "reason": reason, "evidence": evidence}


def conditional(value: Any, reason: str, *, evidence: Any = None) -> dict[str, Any]:
    return {"status": "CONDITIONAL", "value": value, "reason": reason, "evidence": evidence}


def measured(value: Any, *, evidence: Any = None) -> dict[str, Any]:
    return {"status": "MEASURED", "value": value, "evidence": evidence}


def annotation_category(annotations: Mapping[str, Any] | None, category_id: str) -> Mapping[str, Any] | None:
    if not annotations:
        return None
    if annotations.get("reviewStatus") != "APPROVED":
        return None
    value = annotations.get("categories", {}).get(category_id)
    if not isinstance(value, dict):
        return None
    if value.get("reviewStatus") != "APPROVED" or value.get("quadReviewStatus") != "APPROVED":
        return None
    return value


def annotation_metric(annotations: Mapping[str, Any] | None, category_id: str, name: str) -> Any:
    category = feature_annotation_category(annotations, category_id)
    if category is None:
        return None
    return category.get("metrics", {}).get(name)


def feature_annotation_category(
    annotations: Mapping[str, Any] | None,
    category_id: str,
) -> Mapping[str, Any] | None:
    category = annotation_category(annotations, category_id)
    if category is None:
        return None
    if category.get("approvals", {}).get("naturalFeatureSignature") is not True:
        return None
    return category


def target_card(
    frozen: Mapping[str, Any],
    files: Mapping[str, Mapping[str, Path]],
    category_id: str,
) -> tuple[np.ndarray, np.ndarray, Any, dict[str, Any]]:
    category = next(item for item in frozen["categories"] if item["id"] == category_id)
    rgb = load_rgb(files[category_id]["frame"])
    mapping = card_transform(category["geometry"]["quadNormalized"], source_shape=rgb.shape, normalized=True)
    rectified = mapping.rectify(rgb)
    source_mask = load_mask(files[category_id]["card-silhouette"])
    silhouette = mapping.rectify(source_mask.astype(np.float32), order=0) >= 0.5
    if silhouette.mean() < 0.35:
        raise MeasurementUnavailable(f"Frozen {category_id} rectified silhouette is implausible")
    return rectified, silhouette, mapping, category


def role_entry(
    role: str,
    context: LocalContext,
    annotations: Mapping[str, Any] | None,
) -> EvidenceEntry | None:
    override = annotations.get("roleMap", {}).get(role) if annotations else None
    if isinstance(override, dict) and isinstance(override.get("localCaptureId"), str):
        return entry_by_id(context.entries, override["localCaptureId"])
    specification = ROLE_SPECS[role]
    if "localCaptureId" in specification:
        return entry_by_id(context.entries, specification["localCaptureId"])
    pose = specification["localPose"]
    return entry_by_predicate(
        context.entries,
        lambda raw: str(raw.get("pose", raw.get("cardPose", ""))).lower() == pose
        and raw.get("debug", "beauty") == "beauty",
    )


def role_mapping(
    frozen: Mapping[str, Any],
    files: Mapping[str, Mapping[str, Path]],
    context: LocalContext,
    annotations: Mapping[str, Any] | None,
    review_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    roles: dict[str, Any] = {}
    artifacts: dict[str, Any] = {}
    for role, specification in ROLE_SPECS.items():
        target_id = specification["targetCategory"]
        target_rgb, target_silhouette, _, target_category = target_card(frozen, files, target_id)
        typography = load_mask(files[target_id]["typography"])
        highlight = load_mask(files[target_id]["highlight"])
        target_image = load_rgb(files[target_id]["frame"])
        target_mapping = card_transform(
            target_category["geometry"]["quadNormalized"],
            source_shape=target_image.shape,
            normalized=True,
        )
        exclusions = [
            target_mapping.rectify(typography.astype(np.float32), order=0) >= 0.5,
            target_mapping.rectify(highlight.astype(np.float32), order=0) >= 0.5,
        ]
        target_profiles = normalized_profiles(target_rgb, target_silhouette, exclusions=exclusions)
        target_overlay = review_dir / f"edge-roi-target-{role}.png"
        target_annotation = annotation_category(annotations, target_id)
        target_boundaries = None
        if target_annotation:
            target_boundaries = {
                name: target_annotation.get("metrics", {}).get(name)
                for name in ("sidewallScreenWidthRatio", "strongLensRimWidthRatio", "opticalShoulderWidthRatio")
            }
        draw_private_edge_overlay(
            target_rgb,
            target_silhouette,
            target_overlay,
            title=f"Frozen target · {role} · {target_id}",
            zone_boundaries=target_boundaries,
        )
        artifacts[f"target-{role}"] = {
            "sha256": sha256_file(target_overlay),
            "privatePixelArtifact": True,
        }

        local = role_entry(role, context, annotations)
        local_value: dict[str, Any]
        if local is None:
            local_value = blocked(
                "required-local-role-capture-missing",
                evidence={"requiredPose": specification.get("localPose"), "requiredCaptureId": specification.get("localCaptureId")},
            )
        else:
            try:
                local_pose = specification.get("localPose", "front")
                pose_evidence = pose_context(context, local_pose)
                local_rgb = rectify_entry(local, context, mapping=pose_evidence.transform)
                local_profiles = normalized_profiles(local_rgb, pose_evidence.silhouette)
                local_overlay = review_dir / f"edge-roi-local-{role}.png"
                draw_private_edge_overlay(
                    local_rgb,
                    pose_evidence.silhouette,
                    local_overlay,
                    title=f"Local V4 · {role} · {local.identifier}",
                    zone_boundaries={
                        "sidewallScreenWidthRatio": context.optical_zones.get("sidewallScreenWidthRatio"),
                        "strongLensRimWidthRatio": context.optical_zones.get("strongLensRimWidthRatio"),
                        "opticalShoulderWidthRatio": context.optical_zones.get("opticalShoulderWidthRatio"),
                    },
                )
                artifacts[f"local-{role}"] = {
                    "sha256": sha256_file(local_overlay),
                    "privatePixelArtifact": True,
                }
                local_value = measured({
                    "captureId": local.identifier,
                    "captureSha256": local.raw["sha256"],
                    "pose": local_pose,
                    "poseOpticalZonesCaptureId": pose_evidence.zone_entry.identifier,
                    "poseOpticalZonesSha256": pose_evidence.zone_entry.raw["sha256"],
                    "profileSummary": summarize_profiles(local_profiles),
                })
            except MeasurementUnavailable as error:
                local_value = blocked(str(error), evidence={"captureId": local.identifier, "captureSha256": local.raw["sha256"]})

        target_reviewed = annotation_category(annotations, target_id) is not None
        roles[role] = {
            "targetCategory": target_id,
            "targetFrameSha256": target_category["frameSha256"],
            "frameReuse": [name for name, value in ROLE_SPECS.items() if value["targetCategory"] == target_id],
            "targetReviewStatus": "APPROVED" if target_reviewed else "PENDING",
            "targetProfileSummary": summarize_profiles(target_profiles),
            "local": local_value,
        }
    return roles, artifacts


def safe_metric(callable_value: Any, reason: str) -> dict[str, Any]:
    try:
        return measured(callable_value())
    except (MeasurementUnavailable, ValueError) as error:
        return blocked(f"{reason}: {error}")


def local_metrics(context: LocalContext) -> dict[str, Any]:
    zone_metrics = dict(context.optical_zones)
    zone_metrics["widthDistributions"] = dict(context.optical_zones["widthDistributions"])
    sidewall_by_pose: dict[str, Any] = {}
    sidewall_distributions = []
    for pose in ("left", "right"):
        try:
            evidence = pose_context(context, pose)
            metrics = compute_optical_zone_metrics(evidence.rectified_zones, evidence.silhouette)
            distribution = metrics["widthDistributions"]["sidewall"]
            sidewall_by_pose[pose] = {
                "status": "MEASURED",
                "captureId": evidence.zone_entry.identifier,
                "captureSha256": evidence.zone_entry.raw["sha256"],
                "distribution": distribution,
            }
            sidewall_distributions.append(distribution)
        except (MeasurementUnavailable, ValueError) as error:
            sidewall_by_pose[pose] = {"status": "BLOCKED", "reason": str(error)}
    zone_metrics["sidewallByPose"] = sidewall_by_pose
    if len(sidewall_distributions) == 2:
        aggregate = aggregate_pose_width_distributions({
            pose: sidewall_by_pose[pose]["distribution"] for pose in ("left", "right")
        })
        zone_metrics["sidewallScreenWidthRatio"] = aggregate["p50"]
        zone_metrics["widthDistributions"]["sidewall"] = aggregate
        optical_zone_result = measured(zone_metrics)
    else:
        optical_zone_result = blocked(
            "left-and-right optical-zone poses are required for sidewall screen width",
            evidence=sidewall_by_pose,
        )
    values: dict[str, Any] = {"opticalZones": optical_zone_result}

    horizontal = entry_by_id(context.entries, "v4-horizontal-lines")
    vertical = entry_by_id(context.entries, "v4-vertical-lines")
    if horizontal and vertical:
        rectified_horizontal = rectify_entry(horizontal, context)
        rectified_vertical = rectify_entry(vertical, context)
        bending = safe_metric(
            lambda: content_bending_width(rectified_horizontal, rectified_vertical, context.silhouette),
            "content-bending-unavailable",
        )
        values["contentBending"] = bending
        if bending["status"] == "MEASURED":
            zone_metrics["contentBendingWidthRatio"] = bending["value"]["widthRatio"]
    else:
        values["contentBending"] = blocked("horizontal-or-vertical-line-capture-missing")

    compression_by_pose: dict[str, Any] = {}
    compression_values = []
    for pose in ("left", "right"):
        horizontal_pose = entry_by_id(context.entries, f"phase1b-sidewall-{pose}-horizontal-lines")
        vertical_pose = entry_by_id(context.entries, f"phase1b-sidewall-{pose}-vertical-lines")
        if horizontal_pose is None or vertical_pose is None:
            compression_by_pose[pose] = blocked("matched tilted line captures are missing")
            continue
        try:
            evidence = pose_context(context, pose)
            metric = sidewall_content_compression(
                rectify_entry(horizontal_pose, context, mapping=evidence.transform),
                rectify_entry(vertical_pose, context, mapping=evidence.transform),
                evidence.silhouette,
            )
            compression_by_pose[pose] = measured(metric)
            compression_values.append(metric["compressionRatio"])
        except (MeasurementUnavailable, ValueError) as error:
            compression_by_pose[pose] = blocked(f"tilted-sidewall-compression-unavailable: {error}")
    if len(compression_values) == 2:
        values["sidewallContentCompression"] = measured({
            "method": "median of matched left/right tilted deterministic-line compression",
            "compressionRatio": float(np.median(compression_values)),
            "byPose": compression_by_pose,
        })
    else:
        values["sidewallContentCompression"] = blocked(
            "matched left/right tilted line compression is required",
            evidence=compression_by_pose,
        )

    pointer_entries = [
        entry for entry in context.entries
        if entry.raw.get("role") == "phase1b-reflection-pointer"
        and entry.raw.get("debug") == "reflection"
        and isinstance(entry.raw.get("pointer"), list)
    ]
    pointer_entries.sort(key=lambda entry: (float(entry.raw["pointer"][0]), float(entry.raw["pointer"][1])))
    if pointer_entries:
        center_entry = min(
            pointer_entries,
            key=lambda entry: float(np.linalg.norm(np.asarray(entry.raw.get("pointer", [99, 99]), dtype=float))),
        )
        highlight = safe_metric(lambda: highlight_metrics(rectify_entry(center_entry, context), context.silhouette), "highlight-unavailable")
        values["highlight"] = highlight
        if highlight["status"] == "MEASURED":
            zone_metrics["highlightWidthRatio"] = highlight["value"]["widthRatio"]
        values["highlightPath"] = safe_metric(
            lambda: highlight_path(
                [(entry.raw["pointer"], rectify_entry(entry, context)) for entry in pointer_entries],
                context.silhouette,
            ),
            "highlight-path-unavailable",
        )
    else:
        values["highlight"] = blocked("pointer-reflection-captures-missing")
        values["highlightPath"] = blocked("pointer-reflection-captures-missing")

    # Checker has uniform spatial frequency across center and rim; the
    # procedural photo is useful for qualitative adaptivity but has a spatially
    # varying source spectrum and would bias this ratio by content placement.
    high = entry_by_id(context.entries, "v4-checker") or entry_by_id(context.entries, "v4-high-frequency-photo")
    rim_width = context.optical_zones.get("strongLensRimWidthRatio")
    shoulder_width = context.optical_zones.get("opticalShoulderWidthRatio")
    if high and rim_width is not None:
        values["sharpness"] = safe_metric(
            lambda: sharpness_ratio(
                rectify_entry(high, context),
                context.silhouette,
                rim_width_ratio=rim_width,
                shoulder_width_ratio=shoulder_width,
            ),
            "sharpness-unavailable",
        )
    else:
        values["sharpness"] = blocked("high-frequency-capture-or-measured-rim-width-missing")

    dispersion = entry_by_id(context.entries, "dispersion-checker")
    values["dispersion"] = safe_metric(
        lambda: dispersion_width(rectify_entry(dispersion, context), context.silhouette),
        "dispersion-unavailable",
    ) if dispersion else blocked("dispersion-capture-missing")

    white = entry_by_id(context.entries, "v4-white")
    black = entry_by_id(context.entries, "v4-black")
    values["backgroundResponse"] = {}
    if white:
        values["backgroundResponse"]["bright"] = safe_metric(
            lambda: background_response(rectify_entry(white, context), context.silhouette, "white"),
            "white-background-response-unavailable",
        )
    else:
        values["backgroundResponse"]["bright"] = blocked("white-capture-missing")
    if black:
        values["backgroundResponse"]["dark"] = safe_metric(
            lambda: background_response(rectify_entry(black, context), context.silhouette, "black"),
            "black-background-response-unavailable",
        )
    else:
        values["backgroundResponse"]["dark"] = blocked("black-capture-missing")
    bright_value = values["backgroundResponse"]["bright"]
    dark_value = values["backgroundResponse"]["dark"]
    if bright_value["status"] == "MEASURED" and dark_value["status"] == "MEASURED":
        values["backgroundResponseDifference"] = measured(abs(
            bright_value["value"]["discernibility"] - dark_value["value"]["discernibility"],
        ))
    else:
        values["backgroundResponseDifference"] = blocked("paired-flat-background-response-unavailable")

    checker = entry_by_id(context.entries, "v4-checker")
    values["cornerSignature"] = safe_metric(
        lambda: corner_refraction_signature(rectify_entry(checker, context), context.silhouette),
        "corner-signature-unavailable",
    ) if checker else blocked("checker-capture-missing")
    return values


def target_highlight_metric(
    annotations: Mapping[str, Any] | None,
    frozen: Mapping[str, Any],
    files: Mapping[str, Mapping[str, Path]],
    category_id: str,
) -> dict[str, Any] | None:
    category_annotation = annotation_category(annotations, category_id)
    if category_annotation is None or category_annotation.get("approvals", {}).get("existingHighlightMask") is not True:
        return None
    target_rgb, silhouette, mapping, _ = target_card(frozen, files, category_id)
    del target_rgb
    mask = mapping.rectify(load_mask(files[category_id]["highlight"]).astype(np.float32), order=0)
    return highlight_mask_metrics(mask, silhouette)


def target_relative_metrics(
    local: Mapping[str, Any],
    annotations: Mapping[str, Any] | None,
    priors: Mapping[str, Any],
    frozen: Mapping[str, Any],
    files: Mapping[str, Mapping[str, Path]],
    overlay_artifacts: Mapping[str, Any],
) -> dict[str, Any]:
    result = {identifier: blocked("target-truth-unavailable") for identifier in RELATIVE_METRIC_IDS}
    optical = local["opticalZones"]
    local_zones = optical["value"] if optical["status"] == "MEASURED" else {}

    prior = priors["targetStrongLensRim"]
    local_rim = local_zones.get("strongLensRimWidthRatio")
    if local_rim is not None:
        error = relative_scalar(local_rim, float(prior["center"]))
        error.update({
            "local": local_rim,
            "targetCenter": prior["center"],
            "targetRange": [prior["min"], prior["max"]],
            "initialLocalGate": prior["initialLocalGate"],
            "withinTargetRange": prior["min"] <= local_rim <= prior["max"],
            "withinInitialLocalGate": prior["initialLocalGate"][0] <= local_rim <= prior["initialLocalGate"][1],
        })
        result["rimWidthRelativeError"] = conditional(
            error,
            "provisional-user-measurement-cannot-claim-automatic-pixel-truth",
            evidence={"priorSetSha256": canonical_sha256(priors)},
        )

    shoulder_target = annotation_metric(annotations, "high-texture", "opticalShoulderWidthRatio")
    local_shoulder = local_zones.get("opticalShoulderWidthRatio")
    if shoulder_target is not None and local_shoulder is not None:
        result["shoulderWidthRelativeError"] = measured({
            "local": local_shoulder,
            "target": shoulder_target,
            **relative_scalar(local_shoulder, shoulder_target),
        })

    target_highlight = target_highlight_metric(annotations, frozen, files, "bright-front")
    local_highlight = local.get("highlight", {})
    if target_highlight and local_highlight.get("status") == "MEASURED":
        value = local_highlight["value"]
        result["highlightWidthRelativeError"] = measured({
            "local": value.get("widthRatio"),
            "target": target_highlight.get("widthRatio"),
            **relative_scalar(value.get("widthRatio"), target_highlight.get("widthRatio")),
        })
        result["highlightPositionRelativeError"] = measured({
            "local": value.get("centroidNormalized"),
            "target": target_highlight.get("centroidNormalized"),
            **relative_point(value.get("centroidNormalized"), target_highlight.get("centroidNormalized")),
        })

    target_sharpness = annotation_metric(annotations, "high-texture", "centerRimSharpnessRatio")
    local_sharpness = local.get("sharpness", {})
    if target_sharpness is not None and local_sharpness.get("status") == "MEASURED":
        local_ratio = local_sharpness["value"].get("centerRimSharpnessRatio")
        result["centerRimSharpnessRatioError"] = measured({
            "local": local_ratio,
            "target": target_sharpness,
            "logRatioError": abs(math.log(max(local_ratio, 1e-9) / max(float(target_sharpness), 1e-9))),
            **relative_scalar(local_ratio, target_sharpness),
        })

    target_dispersion = annotation_metric(annotations, "high-texture", "dispersionWidthRatio")
    local_dispersion = local.get("dispersion", {})
    if target_dispersion is not None and local_dispersion.get("status") == "MEASURED":
        local_width = local_dispersion["value"].get("widthRatio")
        result["dispersionWidthRelativeError"] = measured({
            "local": local_width,
            "target": target_dispersion,
            **relative_scalar(local_width, target_dispersion),
        })

    paired_target = annotations.get("crossCategoryMetrics", {}).get("brightDarkBackgroundResponseDifference") if annotations else None
    local_background = local.get("backgroundResponseDifference", {})
    paired_approved = bool(annotations and annotations.get("approvals", {}).get("brightDarkPairedUse") is True)
    if paired_approved and paired_target is not None and local_background.get("status") == "MEASURED":
        result["brightDarkBackgroundResponseDifference"] = measured({
            "local": local_background["value"],
            "target": paired_target,
            **relative_scalar(local_background["value"], paired_target),
        })
    elif not paired_approved:
        result["brightDarkBackgroundResponseDifference"] = blocked(
            "Frozen bright/dark frames use different cards, media, and geometry; paired material response is not approved",
        )

    target_corner = annotation_metric(annotations, "high-texture", "cornerRefractionSignature")
    local_corner = local.get("cornerSignature", {})
    if isinstance(target_corner, list) and local_corner.get("status") == "MEASURED":
        local_vector = local_corner["value"].get("vector")
        result["cornerRefractionSignature"] = measured({
            "local": local_vector,
            "target": target_corner,
            **relative_vector(local_vector, target_corner),
        })

    left_target = annotation_metric(annotations, "left-tilt", "sidewallContentCompression")
    right_target = annotation_metric(annotations, "right-tilt", "sidewallContentCompression")
    local_compression = local.get("sidewallContentCompression", {})
    local_pose_values = local_compression.get("value", {}).get("byPose", {}) \
        if local_compression.get("status") == "MEASURED" else {}
    pose_pairs = {}
    for pose, target_value in (("left", left_target), ("right", right_target)):
        local_pose = local_pose_values.get(pose, {})
        if isinstance(target_value, (int, float)) and local_pose.get("status") == "MEASURED":
            local_value = local_pose["value"].get("compressionRatio")
            pose_pairs[pose] = {
                "local": local_value,
                "target": target_value,
                **relative_scalar(local_value, target_value),
            }
    if len(pose_pairs) == 2:
        target_value = float(np.median([left_target, right_target]))
        local_value = float(np.median([pose_pairs["left"]["local"], pose_pairs["right"]["local"]]))
        result["sidewallContentCompression"] = measured({
            "local": local_value,
            "target": target_value,
            "byPose": pose_pairs,
            "targetPoseCount": 2,
            **relative_scalar(local_value, target_value),
        })

    required_overlay_ids = [f"target-{role}" for role in ROLE_SPECS] + [f"local-{role}" for role in ROLE_SPECS]
    missing = [identifier for identifier in required_overlay_ids if identifier not in overlay_artifacts]
    approved_count = sum(
        1 for category_id in FROZEN_CATEGORY_IDS if annotation_category(annotations, category_id) is not None
    )
    if missing:
        result["targetLocalEdgeRoiOverlay"] = blocked("one-or-more-target/local-role-overlays-are-unavailable", evidence={"missing": missing})
    elif approved_count < len(FROZEN_CATEGORY_IDS):
        result["targetLocalEdgeRoiOverlay"] = conditional(
            {"artifactHashes": {identifier: overlay_artifacts[identifier]["sha256"] for identifier in required_overlay_ids}},
            "edge overlays are reviewable observations but the Frozen category set is not fully human-approved",
        )
    else:
        result["targetLocalEdgeRoiOverlay"] = measured({
            "artifactHashes": {identifier: overlay_artifacts[identifier]["sha256"] for identifier in required_overlay_ids},
        })
    return result


def variant_entries(entries: Sequence[EvidenceEntry], name: str) -> list[EvidenceEntry]:
    return [entry for entry in entries if variant_name(entry.raw) == name]


def select_ab_pointer_entries(entries: Sequence[EvidenceEntry], name: str) -> list[EvidenceEntry]:
    """Select only same-view A/B pointer evidence and order it by pointer.x."""

    selected = [
        entry for entry in entries
        if variant_name(entry.raw) == name
        and entry.raw.get("role") == "phase1b-reflection-shell-ab-pointer"
        and experiment_view(entry.raw) == "reflection"
        and isinstance(entry.raw.get("experimentVariant"), dict)
        and entry.raw["experimentVariant"].get("family") == "reflection-shell-ab-pointer"
        and isinstance(entry.raw.get("pointer"), list)
        and len(entry.raw["pointer"]) == 2
    ]
    selected.sort(key=lambda entry: (float(entry.raw["pointer"][0]), float(entry.raw["pointer"][1])))
    return selected


def variant_metric(context: LocalContext, name: str) -> dict[str, Any]:
    entries = variant_entries(context.entries, name)
    if not entries:
        return blocked(f"{name}-variant-captures-missing")
    backgrounds = [
        entry for entry in entries
        if entry.raw.get("role") == "phase1b-reflection-shell-ab"
        and experiment_view(entry.raw) == "beauty"
        and isinstance(entry.raw.get("experimentVariant"), dict)
        and entry.raw["experimentVariant"].get("family") == "reflection-shell-ab-background"
    ]
    white = entry_by_predicate(backgrounds, lambda raw: raw.get("pattern") == "white")
    black = entry_by_predicate(backgrounds, lambda raw: raw.get("pattern") == "black")
    color = entry_by_predicate(backgrounds, lambda raw: raw.get("pattern") == "low-frequency-flat-color")
    off_backgrounds = [
        entry for entry in variant_entries(context.entries, "off")
        if entry.raw.get("role") == "phase1b-reflection-shell-ab"
        and experiment_view(entry.raw) == "beauty"
    ]
    off_white = entry_by_predicate(off_backgrounds, lambda raw: raw.get("pattern") == "white")
    off_color = entry_by_predicate(off_backgrounds, lambda raw: raw.get("pattern") == "low-frequency-flat-color")
    pointers = select_ab_pointer_entries(context.entries, name)
    if any(entry is None for entry in (white, black, color, off_white, off_color)) or len(pointers) < 3:
        return blocked(
            f"{name}-variant-requires-matched-white-color-shell-off-and-three-reflection-pointer-captures",
            evidence={
                "white": white is not None,
                "black": black is not None,
                "color": color is not None,
                "offWhite": off_white is not None,
                "offColor": off_color is not None,
                "pointerCount": len(pointers),
                "pointerRole": "phase1b-reflection-shell-ab-pointer",
                "pointerView": "reflection",
            },
        )
    try:
        bright = background_response(rectify_entry(white, context), context.silhouette, "white")
        dark = background_response(rectify_entry(black, context), context.silhouette, "black")
        color_delta = shell_composite_delta_metrics(
            rectify_entry(color, context),
            rectify_entry(off_color, context),
            context.silhouette,
        )
        white_delta = shell_composite_delta_metrics(
            rectify_entry(white, context),
            rectify_entry(off_white, context),
            context.silhouette,
        )
        path = highlight_path(
            [(entry.raw["pointer"], rectify_entry(entry, context)) for entry in pointers],
            context.silhouette,
        )
    except MeasurementUnavailable as error:
        return blocked(f"{name}-variant-metric-unavailable: {error}")
    return measured({
        "shellMode": name,
        "pointerView": "reflection-lighting-invariant",
        "energyView": "beauty-minus-matched-shell-off",
        "pointerExperimentFamily": "reflection-shell-ab-pointer",
        "highlightClippedPixelRatio": max(
            color_delta["highlightClippedPixelRatio"],
            white_delta["highlightClippedPixelRatio"],
        ),
        "rimMeanLuma": {"bright": bright["rimMeanLuma"], "dark": dark["rimMeanLuma"]},
        "brightBackgroundDiscernibility": bright["discernibility"],
        "darkBackgroundHaloWidth": dark["haloWidthRatio"],
        "reflectionEnergy": color_delta["reflectionEnergy"],
        "highlightWidth": color_delta["highlightWidthRatio"],
        "highlightPath": path,
        "shellContribution": {
            "color": color_delta,
            "white": white_delta,
        },
        "neutralPerimeter": {
            "meanChroma": float(np.mean([bright["neutralPerimeterChroma"], dark["neutralPerimeterChroma"]])),
            "whiteOutlineLumaBias": white_delta["rimMeanLumaDelta"],
            "whiteOutlinePixelRatio": white_delta["whiteOutlinePixelRatio"],
        },
        "evidenceHashes": {
            "background": [white.raw["sha256"], black.raw["sha256"], color.raw["sha256"]],
            "shellOff": [off_white.raw["sha256"], off_color.raw["sha256"]],
            "pointerPath": [entry.raw["sha256"] for entry in pointers],
        },
    })


def ab_metrics(context: LocalContext) -> dict[str, Any]:
    additive = variant_metric(context, "additive")
    controlled = variant_metric(context, "energy-controlled")
    comparison: dict[str, Any]
    if additive["status"] != "MEASURED" or controlled["status"] != "MEASURED":
        comparison = blocked("complete-additive-and-energy-controlled-capture-sets-are-required")
    else:
        left, right = additive["value"], controlled["value"]
        deltas = {
            "highlightClippedPixelRatio": right["highlightClippedPixelRatio"] - left["highlightClippedPixelRatio"],
            "brightBackgroundDiscernibility": right["brightBackgroundDiscernibility"] - left["brightBackgroundDiscernibility"],
            "darkBackgroundHaloWidth": None if right["darkBackgroundHaloWidth"] is None or left["darkBackgroundHaloWidth"] is None
                else right["darkBackgroundHaloWidth"] - left["darkBackgroundHaloWidth"],
            "reflectionEnergy": right["reflectionEnergy"] - left["reflectionEnergy"],
            "highlightWidth": None if right["highlightWidth"] is None or left["highlightWidth"] is None
                else right["highlightWidth"] - left["highlightWidth"],
            "neutralPerimeterChroma": right["neutralPerimeter"]["meanChroma"] - left["neutralPerimeter"]["meanChroma"],
            "whiteOutlineLumaBias": right["neutralPerimeter"]["whiteOutlineLumaBias"] - left["neutralPerimeter"]["whiteOutlineLumaBias"],
        }
        additive_white_outline = left["neutralPerimeter"]["whiteOutlineLumaBias"]
        controlled_white_outline = right["neutralPerimeter"]["whiteOutlineLumaBias"]
        preferred = "energy-controlled" if (
            right["highlightClippedPixelRatio"] <= left["highlightClippedPixelRatio"]
            and controlled_white_outline <= additive_white_outline
            and right["highlightPath"]["validSampleCount"] == right["highlightPath"]["requestedSampleCount"]
        ) else "manual-review-required"
        comparison = conditional(
            {"energyControlledMinusAdditive": deltas, "preferredVariant": preferred},
            "A/B metrics are local controlled evidence and do not establish final Frozen target match",
        )
    return {"additive": additive, "energyControlled": controlled, "comparison": comparison}


def result_status(relative: Mapping[str, Any], annotations_status: Mapping[str, Any]) -> str:
    statuses = [value.get("status") for value in relative.values()]
    if annotations_status.get("approvedCategoryCount", 0) < len(FROZEN_CATEGORY_IDS):
        return "CONDITIONAL" if "CONDITIONAL" in statuses else "BLOCKED"
    if any(status == "BLOCKED" for status in statuses):
        return "BLOCKED"
    return "CONDITIONAL"


def build_result(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    frozen_path = args.frozen_manifest.resolve()
    frozen_root = args.frozen_private_root.resolve()
    local_path = args.local_capture.resolve()
    annotations_path = args.annotations.resolve()
    priors_path = args.priors.resolve()
    review_dir = args.review_dir.resolve()
    require_private_review_directory(review_dir)

    frozen, frozen_files, private = verify_frozen(frozen_path, frozen_root)
    local_manifest, entries = verify_local_capture(local_path)
    annotations, annotation_status = load_annotations(annotations_path, frozen)
    priors = load_priors(priors_path)
    context = build_local_context(local_manifest, entries)
    roles, artifacts = role_mapping(frozen, frozen_files, context, annotations, review_dir)
    local = local_metrics(context)
    relative = target_relative_metrics(local, annotations, priors, frozen, frozen_files, artifacts)
    ab = ab_metrics(context)
    status = result_status(relative, annotation_status)
    runtime_files = sanitized_runtime_files(local_manifest["sourceIdentity"])

    fallback_sources = sorted({
        category.get("metrics", {}).get("zoneWidthSource") for category in frozen["categories"]
    })
    result = {
        "$schema": "frozen-visual-calibration.schema.json",
        "schemaVersion": 1,
        "phase": "phase-1b-frozen-visual-calibration",
        "generator": GENERATOR,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "sourceIdentity": {
            "frozenVideoSha256": frozen["source"]["videoSha256"],
            "frozenSanitizedManifestSha256": sha256_file(frozen_path),
            "frozenCanonicalManifestSha256": canonical_sha256(frozen),
            "frozenArtifactSetSha256": frozen["summary"]["artifactSetSha256"],
            "frozenPrivateManifestSha256": sha256_file(frozen_root / "manifest.private.json"),
            "localCaptureManifestSha256": sha256_file(local_path),
            "localHead": local_manifest["sourceIdentity"]["head"],
            "localRuntimeSourceSetSha256": local_manifest["sourceIdentity"]["runtimeSourceSetSha256"],
            "localDirtyRepository": local_manifest["sourceIdentity"].get("dirtyRepository"),
            "localDirtyWithinRuntimeScope": local_manifest["sourceIdentity"]["dirtyWithinRuntimeScope"],
            "files": runtime_files,
            "calibrationPriorSha256": sha256_file(priors_path),
            "annotationSetSha256": annotation_status.get("annotationSetSha256"),
        },
        "captureAttestation": {
            "status": "PASS",
            "sourceIdentityCheckPassed": local_manifest["sourceIdentityCheck"]["passed"],
            "sourceIdentityStartDigest": local_manifest["sourceIdentityCheck"]["startDigest"],
            "sourceIdentityEndDigest": local_manifest["sourceIdentityCheck"]["endDigest"],
            "previewPassed": local_manifest["previewIdentity"]["passed"],
            "previewOriginPublished": False,
            "distTreeSha256": local_manifest["distIdentity"]["treeSha256"],
            "distFileCount": local_manifest["distIdentity"]["fileCount"],
            "servedResourceManifestSha256": local_manifest["servedResourceIdentity"]["manifestSha256"],
            "servedResourceCount": local_manifest["servedResourceIdentity"]["resourceCount"],
            "runtimeContractPassed": local_manifest["runtimeContract"]["passed"],
            "hardwareWebGpu": True,
            "adapter": {
                "vendor": local_manifest["environment"]["graphics"]["adapter"].get("vendor"),
                "architecture": local_manifest["environment"]["graphics"]["adapter"].get("architecture"),
                "isFallbackAdapter": local_manifest["environment"]["graphics"]["adapter"].get("isFallbackAdapter"),
            },
            "pageErrorCount": local_manifest["pageErrorCount"],
            "captureScriptSha256": local_manifest["captureScript"]["sha256"],
            "captureScriptVersion": local_manifest["captureScript"]["version"],
            "screenshotSetSha256": local_manifest["screenshotSetSha256"],
            "sessionVideoSha256": local_manifest["sessionVideo"]["sha256"],
            "captureCount": len(entries),
        },
        "evidenceIntegrity": {
            "status": "PASS",
            "frozenArtifactCategoryCount": len(frozen_files),
            "frozenArtifactHashCount": len(frozen_files) * (3 + len(MASK_NAMES)),
            "localCaptureHashCount": len(entries),
            "privatePixelsCommittedByThisReport": False,
        },
        "targetTruth": {
            **annotation_status,
            "fallbackZoneSourcesObserved": fallback_sources,
            "fallbackZonesAcceptedAsTargetTruth": False,
            "provisionalStrongLensRim": priors["targetStrongLensRim"],
            "finalTargetTruthStatus": "BLOCKED" if annotation_status.get("approvedCategoryCount", 0) < len(FROZEN_CATEGORY_IDS) else "REVIEWED",
        },
        "roleMapping": roles,
        "opticalZoneMetrics": {
            "local": local["opticalZones"],
            "target": {
                role: {
                    "targetCategory": specification["targetCategory"],
                    "reviewStatus": "APPROVED"
                        if feature_annotation_category(annotations, specification["targetCategory"]) else "BLOCKED",
                    "metrics": feature_annotation_category(annotations, specification["targetCategory"]).get("metrics")
                        if feature_annotation_category(annotations, specification["targetCategory"]) else None,
                }
                for role, specification in ROLE_SPECS.items()
            },
        },
        "normalizedEdgeProfiles": {
            "coordinateSpace": "canonical-card-768x448-short-side-normalized",
            "regions": list(context.profiles["regions"]),
            "localSummary": summarize_profiles(context.profiles),
            "wholeCardSsimComputed": False,
        },
        "localMetrics": local,
        "targetRelativeMetrics": relative,
        "reflectionShellAB": ab,
        "privateReviewArtifacts": {
            "artifactCount": len(artifacts),
            "artifacts": artifacts,
            "pathsPublished": False,
            "pixelsPublished": False,
        },
        "finalTargetMatch": "BLOCKED",
        "caveats": {
            "frozenConfiguredZonesAreNotTargetTruth": True,
            "naturalTargetHasNoUnrefractedMediaSource": True,
            "featureDisplacementPolicy": "absolute displacement is local deterministic-line evidence; Frozen natural-media comparison uses reviewed signatures only",
            "brightDarkTargetPairControlled": bool(annotations and annotations.get("approvals", {}).get("brightDarkPairedUse") is True),
            "pointerTargetStateKnown": False,
            "tiltRequiresRealLabPose": True,
            "wholeCardSsimForbidden": True,
            "scope": "Phase 1B Lab calibration only; no Typography, Motion, Grid, main-page integration, Phase 2, or final target PASS is implied.",
        },
    }
    runtime = {
        "output": str(args.output.resolve()),
        "reviewDirectory": str(review_dir),
        "status": status,
        "finalTargetMatch": "BLOCKED",
        "privateArtifactCount": len(artifacts),
    }
    del private
    return result, runtime


def blocked_result(reason: str, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "$schema": "frozen-visual-calibration.schema.json",
        "schemaVersion": 1,
        "phase": "phase-1b-frozen-visual-calibration",
        "generator": GENERATOR,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED",
        "sourceIdentity": {"status": "UNAVAILABLE", "files": []},
        "measurementRun": {"executed": False, "reason": reason},
        "captureAttestation": {"status": "BLOCKED"},
        "evidenceIntegrity": {"status": "BLOCKED"},
        "opticalZoneMetrics": {},
        "targetRelativeMetrics": {identifier: blocked(reason) for identifier in RELATIVE_METRIC_IDS},
        "reflectionShellAB": {
            "additive": blocked(reason),
            "energyControlled": blocked(reason),
            "comparison": blocked(reason),
        },
        "privateReviewArtifacts": {"artifactCount": 0, "artifacts": {}, "pathsPublished": False, "pixelsPublished": False},
        "finalTargetMatch": "BLOCKED",
        "caveats": {
            "wholeCardSsimForbidden": True,
            "scope": "No optical or target-match conclusion may be inferred from this blocked result.",
        },
    }


def public_failure_reason(error: Exception, args: argparse.Namespace) -> str:
    reason = str(error)
    replacements = {
        args.local_capture.resolve(): "<local-capture>",
        args.frozen_manifest.resolve(): "<frozen-manifest>",
        args.frozen_private_root.resolve(): "<frozen-private-root>",
        args.annotations.resolve(): "<private-annotations>",
        args.priors.resolve(): "<calibration-priors>",
        args.review_dir.resolve(): "<private-review-dir>",
        args.output.resolve(): "<public-output>",
        REPO_ROOT.resolve(): "<repository>",
    }
    for path, replacement in sorted(replacements.items(), key=lambda item: len(str(item[0])), reverse=True):
        reason = reason.replace(str(path), replacement)
    return reason


def main() -> int:
    args = parse_args()
    try:
        result, runtime = build_result(args)
        write_json(args.output.resolve(), result)
        print(json.dumps(runtime, ensure_ascii=False, indent=2))
        return 0
    except (
        MeasurementUnavailable,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        json.JSONDecodeError,
    ) as error:
        result = blocked_result(public_failure_reason(error, args), args)
        write_json(args.output.resolve(), result)
        print(json.dumps({
            "status": "BLOCKED",
            "reason": str(error),
            "output": str(args.output.resolve()),
            "reviewDirectory": str(args.review_dir.resolve()),
        }, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
