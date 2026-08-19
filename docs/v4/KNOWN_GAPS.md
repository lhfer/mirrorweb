# MirrorWeb V4 known gaps

This list separates evidence blockers from expected V3 implementation failures. A successful build does not close either category.

## Final-acceptance blockers and development implications

| ID | Status | Gap | Consequence |
| --- | --- | --- | --- |
| V4-P0-001 | FINAL BLOCKED | Frozen recordings do not carry Browser/GPU/CSS Viewport/DPR provenance. | They remain valid visual Golden input, but not performance or strict Motion evidence. |
| V4-P0-002 | LOCAL RESOLVED / FINAL CONDITIONAL | The legacy-current recording remains unbound, but a new local baseline is bound to `e977134` plus its Git tree and served-page attestation. | Use the controlled local baseline; whole-image diff against the differently composed frozen target remains invalid. |
| V4-P0-003 | CONDITIONAL | Clean frames and eight-layer masks are generated from the unannotated target video; seven of eight initial masks retain review flags. | The one clean seed ROI permits the isolated optics lab. Review flags remain visible and cannot count as final quantitative acceptance. |
| V4-P0-004 | CONDITIONAL | The frozen target recording contains a cursor and no deterministic replay marker. | Mask the cursor for frozen visual ROIs; use controlled live capture for causal Pointer measurements. |
| V4-P0-005 | CONTROLLED RAF CAPTURED / FINAL BLOCKED | Controlled P50/P95/P99 RAF intervals are available for target/local comparison, but GPU execution time is not measured. | Never infer page FPS from the 30 fps frozen video or label RAF cadence as GPU frame time. |

## Expected V3 baseline failures

| ID | Phase | Current evidence | Required direction |
| --- | --- | --- | --- |
| V4-GAP-OPTICS-01 | 1 | Normal path mixes direct `mediaMap` with the scene target. | Scene Color Target becomes the normal-path body and rim source. |
| V4-GAP-OPTICS-02 | 1 | Fixed dark body tint and `normal.y` highlight remain in the material. | Content-adaptive optical body plus view/reflection/key-light response. |
| V4-GAP-OPTICS-03 | 1 | Scene target is sRGB/default type, not linear half-float HDR. | Linear HDR optical mixing with quality-dependent target scale. |
| V4-GAP-GEOMETRY-01 | 1 | Geometry exposes only `position`, `uv`, and packed `uv1`. | Add measured edge, shoulder, sidewall, thickness, and curvature attributes with C1 continuity. |
| V4-GAP-TYPE-01 | 2 | Title scale, padding, vertical placement, `.tile-id`, and wrapping do not match the target. | Apply the frozen CSS3D typography contract and edge-crop QA. |
| V4-GAP-MOTION-01 | 3 | Release velocity uses the latest accumulated RAF window; speed below 70 px/s hard-stops. | Fit a controlled replay and use 80–120 ms weighted regression plus stable low-speed settling. |
| V4-GAP-MOTION-02 | 3 | Wheel `deltaMode` is not normalized. | Compare pixel and line deltas under the same deterministic script. |
| V4-GAP-GRID-01 | 4 | A wrap can remap the full 9×9 pool. | Recycle only the entering row or column with a 2D ring buffer. |
| V4-GAP-DOM-01 | 4 | CSS3D content is rebound with `innerHTML`. | Pre-create nodes and update `textContent` only for recycled visible slots. |
| V4-GAP-VIDEO-01 | 4 | Every RAF calls `VideoTexture.update()`. | Gate uploads with `requestVideoFrameCallback`. |
| V4-GAP-QUALITY-01 | 4 | Hysteresis is 2.5 seconds and runtime adaptation changes geometry only. | Use at least 3 seconds and change RT scale, DPR, samples, geometry, dispersion, and DOM overscan. |
| V4-GAP-ROUTING-01 | 1 | `?optics=v3`, `?optics=v4`, and `/glass-lab-v4` do not exist. | Add isolation without deleting or overwriting V3. |

## Baseline verdict

The V3 source is preserved and buildable, but it is not a V4 visual pass. Phase 1 is authorized by the controlled-reference development gate, not by final quantitative acceptance.
