# MirrorWeb V4 controlled reference

This document describes the reproducible evidence workflow. It does not contain private media, absolute paths, raw DOM, or full network URL lists.

## Reference classes

| Class | Authority | Status rule |
| --- | --- | --- |
| Frozen Visual Golden | Optical structure, rim/shoulder shape, refraction style, highlight form, dispersion zone, typography depth relation, qualitative rhythm | `PASS` or `CONDITIONAL` only when the private video is readable, its SHA matches, all derived assets re-hash, and at least one clean seed ROI exists |
| Controlled Live Reference | Current-device layout, trusted Pointer/Touch/Wheel input, motion trajectory, viewport response, relative RAF cadence | `PASS` only when all four target cells pass the same matrix |
| Controlled Local Baseline | Commit-bound V3 baseline under the same matrix | `PASS` only when all four local cells pass and both the source worktree and served page attest to `e977134` and its tree |

The live target never supersedes Frozen Visual Golden. Their card arrangement, media state, cursor state, and capture time differ, so no frame-aligned full-image diff is valid.

## Formal matrix

| Profile | CSS viewport | Browser DPR | Required canvas DPR |
| --- | ---: | ---: | ---: |
| `desktop-1440x900-dpr1` | 1440×900 | 1 | 1 |
| `desktop-1440x900-dpr2` | 1440×900 | 2 | 2 |
| `mobile-390x844-dpr3-clamp1_5` | 390×844 | 3 | 1.5 |
| `mobile-844x390-dpr3-clamp1_5` | 844×390 | 3 | 1.5 |

Every target/local cell has separate identity, interaction, and performance passes. Identity records the full public URL, capture time, complete Chrome version, macOS version, GPU adapter/backend, CSS viewport, browser DPR, canvas buffer/effective DPR, refresh estimate, DOM hash, screenshot hash, network URL/size manifest hashes, and available HTTP validators.

The interaction pass records Rest 5s, five Pointer positions, two 800ms drags, a 150ms Flick with release checkpoints, calibrated trusted pixel Wheel, explicitly non-strict synthetic line Wheel, calibrated trusted Touch Flick, Resize, and trusted Blur/Focus. Timed inputs are fail-closed at ±12%; at least eight card corner points must remain trackable.

The performance pass reports browser `requestAnimationFrame` intervals. P50/P95/P99 values are relative cadence evidence only; they are not GPU execution time and do not make final performance acceptance pass.

## Reproduction

The local server requires an explicit clean worktree:

```bash
ILG_LOCAL_SOURCE_DIR=/path/to/e977134-worktree \
ILG_LOCAL_PORT=5281 \
npm run v4:serve:controlled-local
```

In another shell:

```bash
ILG_LOCAL_SOURCE_DIR=/path/to/e977134-worktree \
ILG_LOCAL_URL=http://127.0.0.1:5281 \
npm run v4:capture:controlled -- --capture-id=<new-unique-id>
```

Capture IDs are immutable. Reusing an existing ID is rejected so failed evidence cannot be overwritten.

Frozen extraction uses the sole private-root protocol:

```bash
ILG_GOLDEN_DIR=/path/to/private-golden npm run v4:extract:frozen
```

The required Python package versions are recorded in `qa-v4/reference/python-requirements.lock.txt`; the generated sanitized manifest also records the exact Python, FFmpeg, NumPy, SciPy, scikit-image, and Pillow versions used.

## Gate semantics

`npm run v4:references` recomputes private video, frame, crop, overlay, mask, raw DOM, telemetry, video, and manifest hashes. A committed sanitized summary cannot pass without its ignored private evidence on the current machine.

Phase 1 may start when source consistency, the commit-bound local baseline, the readable/hash-locked Frozen source, one clean seed ROI, V3 WebGPU smoke, and the isolated V4 route contract all pass. Final quantitative acceptance remains `BLOCKED` until strict optics comparison, Motion fitting, controlled performance acceptance, and the later implementation gaps are closed.

## Accepted Phase 0 capture

- Capture: `20260819-e977134-controlled-r5` — `PASS`, 8/8 cells.
- Time: 2026-08-19 09:06:44–09:16:48 UTC.
- Browser: Chrome `151.0.7922.138`, CDP `1.3`.
- Host: macOS `27.0` build `26A5378n`, arm64.
- GPU: Apple M5 Max, `metal-3`, inferred Metal backend, no fallback adapter observed.
- Local identity: commit `e9771340f849d232f30f87aa70ddac2062d0e332`, tree `6347bfc2b0343cf58f664693bd945f35cf57e01f`, tracked tree clean.
- Matrix SHA-256: `14b4f4b4fa5f569690d60c7e042f88f26f8668f4229400a121450ffbf269b6e9`.
- Input file SHA-256: `fb54e598cd6e5f47e448a931f1afa28be3e232dd87fa5fcb6d6a25eddbdb3df3`.
- Capture harness SHA-256: `7977d75eb2e484afd21b0db31e0f99facdfc68cac05d353320b32722177fbf2a` (`controlled-reference-v6`).

Controlled RAF interval summary in milliseconds:

| Profile | Site | Idle P50/P95/P99 | Interaction P50/P95/P99 |
| --- | --- | --- | --- |
| Desktop DPR1 | Target | 8.3 / 10.1 / 10.3 | 8.3 / 10.0 / 10.3 |
| Desktop DPR1 | Local | 8.3 / 10.1 / 10.3 | 8.3 / 9.9 / 10.3 |
| Desktop DPR2 | Target | 8.3 / 9.9 / 10.3 | 8.3 / 9.9 / 10.3 |
| Desktop DPR2 | Local | 8.3 / 9.9 / 10.3 | 8.3 / 10.0 / 10.3 |
| Mobile portrait | Target | 8.3 / 9.9 / 10.3 | 8.3 / 9.8 / 10.3 |
| Mobile portrait | Local | 8.3 / 10.1 / 10.4 | 8.3 / 9.9 / 10.3 |
| Mobile landscape | Target | 8.3 / 10.0 / 10.3 | 8.3 / 9.8 / 10.3 |
| Mobile landscape | Local | 8.3 / 9.9 / 10.3 | 8.3 / 9.8 / 10.3 |

These near-vsync values are useful for same-device cadence comparison only. They do not prove equal GPU cost or final performance acceptance.
