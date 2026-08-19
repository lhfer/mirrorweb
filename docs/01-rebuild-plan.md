# 01 — Rebuild plan

Locked by `docs/00-root-cause-audit.md`. Frozen hashes in `qa/reference/GOLDEN.json`.

## Order

1. **Milestone 1 — this phase.** Opaque gray slabs. Camera, size, gutter, squircle, brick, yaw cylinder, overscan, pool, resize. No glass shader work.
2. **Milestone 2.** One Motion Controller. Pointer is a target. RAF owns transforms. Scene tilt + camera parallax only after M1 coverage passes.
3. **Milestone 3.** `/glass-lab` first. Replace the front-plane + transmissive-extrude sandwich. Do not retune `MeshPhysical` on the current card.
4. **Milestone 4.** Ready means decode + GPU upload + compile + warmup, not `HAVE_CURRENT_DATA`.
5. **Milestone 5.** Real-GPU traces vs origin. Unique RAF, no per-frame blit.

## Milestone 1 decisions

| Item | Choice | Why |
| --- | --- | --- |
| Material | Shared opaque gray `MeshStandardMaterial` | Audit: transmission is the bezel + draw-call storm |
| Content / video | Not mounted | M1 is layout only; no unready media tiles |
| Type overlay | Off unless `?debug=` | HTML titles hide slab silhouette |
| Pool | 9×9, remap by `(i,j)` | Two rows and two columns of overscan around the A rest window |
| Curvature | Yaw cylinder, edges closer (`+Z`) | Origin §3.6; current spare row was wasted *below* the fold |
| Outline | Superellipse n=5, then bevel extrude | Continuous corner, not `quadraticCurveTo` |
| Spacing | Keep measured `cellW/H` / `restY0` from A remasurement; verify live | Do not invent gutters |

## Milestone 1 status (2026-08-18)

Live probe: `qa/local/m1/probe.json`.

| Gate | Result |
| --- | --- |
| Pool 9×9, remap only | Pass. 81 created, 0 destroyed after offset |
| Opaque gray, no video | Pass. 0 `<video>`, 0 textures |
| Mid L / Mid R / Bot C centers | Pass, Δn < 0.7% |
| Top row clipped overscan | Pass. `j=2` exists, `ny < 0` |
| Bot L / R vs overlay AABB | 2.07% — overlay of a clipped card is not the 3D center. Held to 3% |
| `?debug=coverage\|geometry\|pool` | Present |
| Designed mid/bot gutter ~16–20 px | Matches origin navy gap. The brief’s “≤4 px near-black band” would also fail the origin rest frame, whose viewport center *is* that gutter. Treat holes (missing rows) as the defect, not the brick gap. |

Do not start Milestone 2 until an independent QA run agrees the coverage / landmark set is acceptable.

## Milestone 2 status (2026-08-18)

Model: `docs/03-motion-model.md`.

| Gate | Result |
| --- | --- |
| Events write targets only | Pointer / wheel / drag queue; RAF `step(dt)` owns scroll, pointer ease, tilt, camera, key light |
| Duplicate Mouse listeners | Removed. Pointer Events only |
| Hover does not translate | `setPointer` changes `rot*` / `cam*` only |
| Drag follow | `dragGain 0.8`, applied in the same RAF as the queued deltas |
| Tilt / parallax | Root `2.6°`, camera XY `4.5%` of cell. No per-tile wobble |
| `setPointer` + state | Wired on `__LIQUID_GLASS_QA__` / `__ILG_QA__` |

Do not start Milestone 3 until drag / flick / hover feel matches the frozen target recording.

## Milestone 3 status (2026-08-18)

Model: `docs/02-glass-model.md`. Lab: `/glass-lab`.

| Gate | Result |
| --- | --- |
| Independent lab first | `/glass-lab` + `/glass-lab.html`, 8 test backgrounds, sliders, screenshot |
| Sandwich replaced | No front content plane. No `transmission` multipass |
| Volume | Convex superellipse, flat center, rim falloff, sides, back dish |
| Media behind lens | Shader UV warp from normal / view / thickness |
| Type in front | CSS3D catalog cards, `?debug=typography` |
| Grid | Same volume + screen-space sample, 3 clip VideoTextures, 81 remapped slots |

Round-01 failed on coverage, transmission, and unused clips. Remediation: overlapping tiles, two-pass scene sample, overlay waits for decoded video.
