# MirrorWeb V4 architecture boundary

## Phase 0 scope

This phase changes documentation, calibration, QA tooling, tests, and private-reference plumbing only. It does not modify `src/**`, HTML entry points, Vite routes, the V3 shader, geometry, typography, motion, grid recycling, or runtime quality behavior.

The existing implementation remains the unflagged V3 baseline. Phase 0 declared the V4 boundary without changing runtime code.

## Phase 1 isolated optics boundary

`/glass-lab-v4` is now implemented as a single-lens test bench. Its `?optics=v3|v4`, V3, V4, Split, and Difference selectors are confined to the lab. The production root, main grid, CSS3D typography, motion controller, and adaptive quality implementation remain byte-identical to the accepted V3 baseline.

```text
Procedural pattern or local-session video
                ↓
registered background media plane
                ↓
linear RGBA16F Scene Color Target + mip chain
                ↓
V4 Snell/projected lens refraction body
                +
MeshPhysical reflection shell
  ↙ procedural strip environment   ↘ pointer Directional Key Light
                ↓
linear V4 comparison target
                ↓
ACES tone map and output conversion
```

The V4 material factory has no `mediaMap` argument. Direct media sampling exists only in the isolated V3 control. Five geometry attributes partition center face, shoulder, lens rim, and sidewall. Blur and dispersion scale with the outer lens zone; adaptive neutral lift/shadow responds to local luminance and contrast instead of applying a fixed blue or black body.

The lab emits nine diagnostic views and captures V3, V4, Split, Difference, a pure-black Edge Mask, line patterns, flat bright/dark patterns, synthetic high/low-frequency content, and a seven-point pointer path. Raw pixels and WebM stay ignored. The committed result contains hashes, aggregate metrics, and sanitized SVG plots only.

## Reference classes and evidence pipeline

```text
Frozen target video ── extract clean frames + ROI masks ── Frozen Visual Golden
Live target URL ────── controlled 4-profile capture ─────── Controlled Live Reference
e977134 worktree ───── same browser/input matrix ───────── Controlled Local Baseline
                                  ↓
                     layered reference status
                                  ↓
              Phase 1 development gate / final gate
```

The private lock is the frozen input identity. A version-controlled aggregate identity digest anchors its asset and input-script section without publishing private paths. Sanitized manifests expose only permitted hashes and normalized measurements. Runtime verification re-hashes the private target video, all selected frames/crops/overlays/masks, controlled screenshots/videos, DOM/telemetry, and raw manifests; sanitized JSON alone cannot open the Phase 1 gate. Generated private files are ignored by Git.

If `ILG_GOLDEN_DIR` points inside the repository, the entire directory must be ignored and contain no tracked files. Asset paths must remain inside that directory; the deterministic input path is fixed to the calibrated repository file and cannot use `..` or an absolute path.

The capture matrix is paired across target and local:

- 1440×900 DPR 1
- 1440×900 DPR 2
- 390×844 browser DPR 3, recording the target's effective canvas DPR clamp
- 844×390 browser DPR 3, recording the target's effective canvas DPR clamp

Each profile has separate identity, interaction, and performance passes so screenshot/DOM work cannot contaminate performance sampling. `rafIntervalMs` is a browser cadence metric, not GPU execution time.

Capture IDs are immutable. Failed attempts remain as separate sanitized manifests with ignored raw evidence; a retry must use a new ID.

Exit codes remain contractual for the strict Golden verifier:

- `0`: `READY`
- `2`: `BLOCKED` because required evidence is absent, unverifiable, dirty, or mismatched
- `1`: tool or source-contract failure

The verifier never falls back to the old `qa/reference/GOLDEN.json`, historical artifacts, or a QA state string. The live target is a distinct controlled reference and can never overwrite Frozen Visual Golden.

## V3 snapshot

The exact source paths and SHA-256 fingerprints in `config/calibration.v4.json` bind the term “V3” to the implementation that was audited in Phase 0. This avoids changing `getState().glass` merely to satisfy a test.

Known current flow:

```text
Media Plane → sRGB/default Scene Render Target
           ↘ direct mediaMap sample
             V3 MeshBasicNodeMaterial hybrid → final output
```

Known current update flow:

```text
origin cell changes → all 81 logical coordinates reconsidered
                    → changed slots remap material/content
                    → CSS3D card innerHTML is rebuilt
```

## Gate separation

The Phase 1 development gate requires source consistency, a commit-bound controlled local baseline, readable/hash-locked Frozen Visual Golden, at least one clean optical ROI, a working V3 runtime, and an isolated V4 lab route.

Final quantitative acceptance additionally requires complete controlled live evidence, strict Motion fitting, controlled performance evidence, and closure of all P0/P1/P2 findings. A final `BLOCKED` does not automatically prevent the isolated optics lab from starting.

## Phase isolation

- Phase 1: `/glass-lab-v4` foundation is implemented and structurally measured; Frozen Visual crop fitting and visual review remain before any main integration.
- Phase 2: typography only, preserving CSS3D and the V3 route.
- Phase 3: deterministic motion fitting only.
- Phase 4: 2D ring buffer, DOM reuse, video-frame updates, and real adaptive quality.
- Phase 5: integration only after the preceding gates pass.

Each phase receives one scoped commit. Failed evidence remains preserved.
