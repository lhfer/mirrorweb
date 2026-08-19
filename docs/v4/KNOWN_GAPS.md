# MirrorWeb V4 known gaps

This list separates evidence blockers from expected V3 implementation failures. A successful build does not close either category.

## Phase 0 evidence blockers

| ID | Status | Gap | Consequence |
| --- | --- | --- | --- |
| V4-P0-001 | BLOCKED | The supplied recordings do not carry a verified source commit, Browser, GPU, CSS Viewport, or DPR provenance. | Golden preflight cannot be `READY`. |
| V4-P0-002 | BLOCKED | The target and current recordings differ in encoded dimensions, duration, content, and uncontrolled input. | No frame-aligned diff or motion fitting is valid. |
| V4-P0-003 | BLOCKED | The only supplied target screenshot contains red annotation strokes. | It is ROI guidance only; full-frame pixel metrics need a clean source or mask. |
| V4-P0-004 | BLOCKED | The target recording contains a cursor and no deterministic replay marker. | Highlight and difference metrics need a cursor mask or controlled recapture. |
| V4-P0-005 | NOT MEASURED | P50/P95/P99 render frame time is not encoded in a 30 fps screen recording. | Performance remains unverified; 30 fps must not be reported as page FPS. |

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

The V3 source is preserved and buildable, but it is not a V4 visual pass. Phase 1 is not authorized while the Phase 0 Golden preflight remains blocked.
