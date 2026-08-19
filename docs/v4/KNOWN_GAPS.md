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
| V4-P1-001 | LAB STRUCTURAL PASS / FINAL BLOCKED | Deterministic patterns pass the first optics-lab gate, but no frame-aligned Frozen Visual crop fit has been accepted. | Continue inside Phase 1 only; do not integrate V4 into the main page or claim visual equivalence. |
| V4-P1-002 | LAB RAF CAPTURED / FINAL BLOCKED | The V4 lab reports rAF P50/P95/P99, not WebGPU timestamp-query execution cost. | Treat the values as scheduling evidence only; controlled GPU performance remains unresolved. |
| V4-P1-003 | PRIVATE REVIEW AVAILABLE | V3/V4 crops, Debug views, and the session video are retained as ignored evidence; the commit contains hashes and sanitized SVG plots. | A clean checkout can validate source contracts but needs the private capture directory to re-inspect pixels. |

## Implementation gaps and lab-only resolutions

| ID | Phase | Current evidence | Required direction |
| --- | --- | --- | --- |
| V4-GAP-OPTICS-01 | 1 | LAB RESOLVED: V4 normal path accepts only Scene Color; V3 direct media remains isolated to the control. | Keep this invariant during Frozen Visual fitting and later integration. |
| V4-GAP-OPTICS-02 | 1 | LAB RESOLVED / VISUAL CONDITIONAL: adaptive neutral volume and a physical shell replace the fixed V3 body; captured highlight travel passes. | Fit highlight shape and intensity to Frozen crops without reintroducing a fixed rim. |
| V4-GAP-OPTICS-03 | 1 | LAB RESOLVED: V4 uses linear half-float Scene Color with 1.0/0.75/0.55 presets. | Validate tone mapping and quality switching again at integration time. |
| V4-GAP-GEOMETRY-01 | 1 | LAB RESOLVED: all five optical attributes and the continuous superellipse profile are present. | Frozen crop comparison still decides whether the measured zone widths match the target. |
| V4-GAP-TYPE-01 | 2 | Title scale, padding, vertical placement, `.tile-id`, and wrapping do not match the target. | Apply the frozen CSS3D typography contract and edge-crop QA. |
| V4-GAP-MOTION-01 | 3 | Release velocity uses the latest accumulated RAF window; speed below 70 px/s hard-stops. | Fit a controlled replay and use 80–120 ms weighted regression plus stable low-speed settling. |
| V4-GAP-MOTION-02 | 3 | Wheel `deltaMode` is not normalized. | Compare pixel and line deltas under the same deterministic script. |
| V4-GAP-GRID-01 | 4 | A wrap can remap the full 9×9 pool. | Recycle only the entering row or column with a 2D ring buffer. |
| V4-GAP-DOM-01 | 4 | CSS3D content is rebound with `innerHTML`. | Pre-create nodes and update `textContent` only for recycled visible slots. |
| V4-GAP-VIDEO-01 | 4 | Every RAF calls `VideoTexture.update()`. | Gate uploads with `requestVideoFrameCallback`. |
| V4-GAP-QUALITY-01 | 4 | Hysteresis is 2.5 seconds and runtime adaptation changes geometry only. | Use at least 3 seconds and change RT scale, DPR, samples, geometry, dispersion, and DOM overscan. |
| V4-GAP-ROUTING-01 | 1 | LAB RESOLVED / MAIN DEFERRED: `/glass-lab-v4?optics=v3|v4` and Split/Difference exist; the production root remains V3. | Add main-page routing only after the full Phase 1 visual gate permits integration. |

## Baseline verdict

The V3 source is preserved and buildable. The V4 lab foundation passes its deterministic structural checks, but this is not a Frozen Visual pass. Further Phase 1 optics work is authorized; main integration and Phases 2–4 remain gated.
