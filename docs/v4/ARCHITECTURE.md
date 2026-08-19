# MirrorWeb V4 architecture boundary

## Phase 0 scope

This phase changes documentation, calibration, QA tooling, tests, and private-reference plumbing only. It does not modify `src/**`, HTML entry points, Vite routes, the V3 shader, geometry, typography, motion, grid recycling, or runtime quality behavior.

The existing implementation remains the unflagged V3 baseline. `?optics=v3`, `?optics=v4`, and `/glass-lab-v4` are declared routes but are intentionally marked `not-implemented` until the optics-lab phase.

## Evidence pipeline

```text
private media under ILG_GOLDEN_DIR
        ↓ create once, refuse overwrite
manifest.lock.json
        ↓ recompute hashes + ffprobe + provenance + input hash
qa-v4/results/golden-manifest.local.json
        ↓ combine with source-contract audit and known-gap probes
qa-v4/results/phase-0-baseline.local.json
```

The private lock is the frozen input identity. A version-controlled aggregate identity digest anchors its asset and input-script section without publishing private paths or per-file hashes. Runtime manifests add the tested commit, tree, branch, dirty state, timestamps, and verification result. Generated private files are ignored by Git.

If `ILG_GOLDEN_DIR` points inside the repository, the entire directory must be ignored and contain no tracked files. Asset paths must remain inside that directory; the deterministic input path is fixed to the calibrated repository file and cannot use `..` or an absolute path.

Exit codes are contractual:

- `0`: `READY`
- `2`: `BLOCKED` because required evidence is absent, unverifiable, dirty, or mismatched
- `1`: tool or source-contract failure

The verifier never falls back to the old `qa/reference/GOLDEN.json`, historical artifacts, the live target, or a QA state string.

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

## Planned phase isolation

- Phase 1: add V4 feature routing and `/glass-lab-v4`; implement and measure optics only.
- Phase 2: typography only, preserving CSS3D and the V3 route.
- Phase 3: deterministic motion fitting only.
- Phase 4: 2D ring buffer, DOM reuse, video-frame updates, and real adaptive quality.
- Phase 5: integration only after the preceding gates pass.

Each phase receives one scoped commit. Failed evidence remains preserved.
