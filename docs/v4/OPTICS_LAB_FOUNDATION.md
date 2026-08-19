# V4 Optics Lab Foundation

Status: **PASS — Phase 1 deterministic structural gate only**

Final Quantitative Acceptance: **BLOCKED**

Canonical result: `qa-v4/results/optics-lab-foundation.json`

Canonical result generated: `2026-08-19T10:42:00.303730+00:00`

This result authorizes continued work inside Phase 1. It does not authorize main-page integration, Phase 2 Typography, a visual-match claim, a performance-match claim, or final acceptance.

## Scope and architecture boundary

The foundation is isolated at `/glass-lab-v4`. The production entry point and its default V3 implementation remain unchanged.

- The Lab renders one controlled optical specimen and supports V3, V4, Split, and Difference views.
- V4's normal path is `background scene -> linear half-float Scene Color Target -> V4 refraction body -> final tone mapping/output conversion`.
- V4 does not accept or mix a direct media texture in its normal material path. The captured runtime contract records `normalPathDirectMedia: false`.
- The V4 target was captured at High quality, scale `1.0`, `1114 x 900`, linear color, half float.
- V4 geometry exposes the optical attributes `aEdgeDistance`, `aShoulder`, `aSidewall`, `aThickness`, and `aCurvature`; it is separate from the preserved V3 geometry.
- Refraction and reflection are separate layers. Reflection uses a programmatic strip-light environment and a pointer-driven key light; it does not hotlink target-site lighting assets.
- Debug views cover Beauty, Edge Mask, Normals, Thickness, Refraction Offset, Reflection, Fresnel, Dispersion, and Adaptivity.
- The Lab exposes controlled QA state and setters for mode, pattern, debug view, and normalized pointer input.
- Deterministic test patterns are generated locally. Private reference media is neither loaded by the normal V4 path nor committed.

The runtime contract passed with `v3Preserved: true`. Main-page Motion, Typography, Grid, layout, and the stable V3 material are outside this foundation's authorized change surface.

## Captured environment

| Field | Captured value |
| --- | --- |
| Capture time | `2026-08-19T10:41:52.004Z` |
| Browser | Chrome `151.0.7922.138`, headed |
| Browser UA platform token | macOS `10_15_7` |
| Viewport | `1440 x 900`, DPR `1` |
| Canvas CSS bounds | `1114 x 900` |
| Canvas buffer | `1114 x 900` |
| WebGPU adapter | vendor `apple`, architecture `metal-3`, non-fallback |
| Renderer | ANGLE Metal Renderer, Apple M5 Max |
| Driver / OS build reported by renderer | Apple `27.0`, build `26A5378n` |
| Software renderer detected | No |
| Observed canvas contexts | `2d`, `webgpu` |
| Served resource count | `51` |
| Served resource manifest SHA-256 | `af3a1fc067a01fd5346969a9d605106a658f28d57fa6e883119ed444e8acee6f` |

Captured source identity was branch `rebuild/liquid-glass-v4`, HEAD `d7f4e31995716ab1982d20e3789391da482fede8`, with runtime source-set SHA-256 `e50dd5f0d82689125056865d2e043e6072ddceff775d8c326eab765c67e503b3`. The runtime scope was dirty because this capture was produced before the Phase 1 commit; the source-set hash, served-resource hash, screenshot-set hash, and subsequent commit identity must be considered together.

## Structural metrics

All nine checks below passed the thresholds recorded in the canonical JSON. Passing means that the first-round structural property is measurable in this deterministic Lab capture; it does not mean the value has been fitted to the Frozen Visual Golden.

| Check | Measured value | Gate | Result |
| --- | ---: | ---: | :---: |
| Center/Rim sharpness ratio | `1.476148` | `>= 1.0` | PASS |
| Rim width / short card side | `0.107903` (`71 px`) | `0.015–0.25` | PASS |
| Horizontal line continuity | coverage `0.997096`; score `0.928263`; outer displacement `2.315516 px` | coverage `>= 0.8`; score `>= 0.7`; displacement `>= 1.5 px` | PASS |
| Vertical line continuity | coverage `0.975439`; score `0.835657`; outer displacement `2.463565 px` | coverage `>= 0.8`; score `>= 0.7`; displacement `>= 1.5 px` | PASS |
| Four-corner continuity | `0.999654` | `>= 0.4` | PASS |
| Pointer highlight path | 7/7 valid; travel `0.693954`; max/median jump `1.788349`; X correlation `0.912938` | travel `>= 0.03`; jump ratio `<= 3.5` | PASS |
| Dispersion energy in outer zone | `0.999999797` | `>= 0.9` | PASS |
| Dark-background discernibility | `0.177112` | `>= 0.015` | PASS |
| Light-background discernibility | `0.016907` | `>= 0.015` | PASS |

Additional diagnostics, not separate acceptance gates:

- Difference view: mean absolute luma `0.293820`, P95 `0.964706`, non-trivial pixel ratio `0.499895`.
- Browser rAF interval: 1,739 samples; P50 `8.30 ms`, P95 `9.00 ms`, P99 `9.30 ms`, maximum `76.00 ms`.
- The rAF numbers describe browser scheduling intervals. They are not CPU render cost and are not WebGPU timestamp-query measurements.

Sanitized plots are committed without private pixels:

- `qa-v4/results/optics-lab-foundation-artifacts/displacement-plot.svg`, SHA-256 `0d42810a601d9e0a97720758022e02eaa7dee395326503c40abc5eed35a5eb96`
- `qa-v4/results/optics-lab-foundation-artifacts/highlight-path.svg`, SHA-256 `937535eda26ee3ac895b155521670c874865408927d353cc3ae99a872af6cab4`

## Private evidence identity

The following identities were read from the retained attempt-08 local manifest. No absolute filesystem path or private pixel/video payload is recorded here.

| Private evidence | SHA-256 |
| --- | --- |
| Complete screenshot set | `c59e75e33eaa5065786b62b840d4706973ee7410e430ca41a596a3e93ea597d7` |
| Input capture manifest | `278af3fdf21e5d2f634f9d13ece2017869774db448a1a5f22556093f70e609e0` |
| Measurement evidence set | `bd09bfeef4b6a24a79ff918927e02bd2720be18fb7b1c4323dabd07920b60c0c` |
| Full Lab session video | `64d83840682a9098d87d800a6718bac2b8b73ff5c42642a934137355228d8b7b` |
| Split-view UI preview | `c5197c44792374d768ba7f766da4ea1c2d3c158936d134add239221033bb3033` |
| V3/V4 split checker | `eeb77c830638b2d0bd664786737e104ef5bb56a1bc0d7fe7f7dadf6f8a721055` |
| V3 control checker | `17fc378151c0d9601661e1412ba79a17b202221a414f973f6979ce5a460c3669` |
| V4 checker | `14833adead27ab0ee60fb0e620afee755d5721bf19c68bba0d34f5214223cd3f` |
| Difference checker | `2a992cdf0a46db8ce2aac20983eaac2842691a9b718cb6f747258020f1e69065` |
| Edge mask | `d5a730e5c5c713a1047d9c46e0042aa33f804067ebedb3e2bfe1369c3fbfe3bd` |
| Horizontal lines | `bf07d857d71507afd94b3077577bf99f53294527e6eff07b3dd469053c4f746a` |
| Vertical lines | `d922e0b4776698a8e372243e8cae9a7a1c894200a61ed8b5326d6287daf5d09f` |
| Dispersion debug | `6c6ca6074e885f0172e138b1003c3300f03f7d5c159f3484f0f38d942be4a804` |

The seven pointer/reflection frames are individually hash-locked in the canonical result. Their ordered set produced highlight travel `0.693954` with a max/median jump ratio of `1.788349`.

## Retained prior attempts

Attempts 01–07 remain retained locally as capture and metric manifests. They were not deleted or rewritten after attempt-08 passed.

| Attempt | Capture time | Screenshot-set SHA-256 | Outcome / reason superseded |
| --- | --- | --- | --- |
| 01 | `2026-08-19T09:53:31.113Z` | `89ad3f0c63edbb512ab3887f1309b45c01d2b84503989d4a28787d477651bdbc` | Invalid checker-contaminated Mask and zero-displacement false-positive; dark-background failure |
| 02 | `2026-08-19T09:56:30.608Z` | `0a41f5bb81f6df2b1a3702a9b4089d805db22f55d03ed9ce0d9eecffc20ce08d` | Invalid checker-contaminated Mask and zero-displacement false-positive; dark-background failure |
| 03 | `2026-08-19T10:10:06.103Z` | `37c4479d39c04347c5ef8485965bd04ef9f88c2ff1af9cf8231e534594e11301` | Horizontal displacement, vertical displacement, light-background discernibility |
| 04 | `2026-08-19T10:13:50.918Z` | `8ff4a585510e5b9f6f9e2d9d933ab13ac21e4e6ca120045fff76643604056ff4` | Horizontal displacement, vertical displacement, light-background discernibility |
| 05 | `2026-08-19T10:15:23.606Z` | `22f9da39adc7a36b9dc38bba548a766e5fdc1978f811acfa0d67577ca636b141` | Light-background discernibility |
| 06 | `2026-08-19T10:16:33.400Z` | `ff661c5d573605863071d60cc31ca2f6d8952b83a6740274db58d8ffc3d4e5c5` | Structural PASS, superseded after review corrected the fallback-adapter gate |
| 07 | `2026-08-19T10:34:40.343Z` | `f113ef756dac9f6887db077452c915c8e0ab3b2b511402ad1f989baf2b244753` | Structural PASS, superseded after final diff-check normalized two runtime-file EOFs |

Attempts 01–02 were explicitly invalidated after review showed that the checker background inflated the silhouette to 88.1% of the canvas and the old continuity metric could pass with zero displacement. They are retained as audit evidence, not counted as valid optics measurements. Attempt 06 passed the optics checks but was superseded because the hardware gate read the fallback flag from the wrong adapter object; Attempt 07 was superseded only to bind the final normalized runtime bytes. None of the earlier runs contributes to the attempt-08 PASS, and they must not be removed merely because a later run passed.

## Known differences and unresolved work

- The deterministic pattern set validates optical structure. It is not a pixel comparison against Frozen Visual Golden frames.
- The “high-frequency photo” Lab source is procedurally generated; no natural photographic texture or licensed video was included in the measured gate.
- PNG measurements are display-encoded readbacks. Linear HDR sampling is established separately by the runtime contract, not inferred from those PNG values.
- The light-background discernibility result (`0.016907`) has a small margin above the `0.015` foundation threshold and needs further robustness work.
- The measured line displacement proves continuous bending is present; it does not prove that lens width or displacement magnitude matches the target reference.
- Highlight movement was measured in the isolated Reflection debug view over a black deterministic background, not over the full target media distribution.
- Only the listed desktop `1440 x 900`, DPR `1` Lab environment is represented by this foundation measurement. It is not a multi-profile performance result.
- P50/P95/P99 are rAF intervals, not GPU execution time, and cannot support a target-site performance-equivalence claim.
- Typography, Motion, the two-dimensional grid ring buffer, video upload scheduling, and adaptive production quality remain outside this round.
- The capture source was pre-commit and dirty within the explicitly measured runtime scope. The final Phase 1 commit must re-run source identity and consistency checks.

## Gate decision

`v4-02-optics-lab-foundation` is permitted to continue only within Phase 1: refine the isolated V4 optical model, extend deterministic and natural-media Lab evidence, and compare it with the Frozen Visual Golden ROIs.

The following remain prohibited at this gate:

- Integrating V4 into the main page or changing the default V3 route.
- Changing main-page Typography, Motion, Grid behavior, or layout.
- Starting Phase 2.
- Deleting V3 or removing failed evidence.
- Claiming Frozen Visual Golden parity, strict Motion parity, target performance parity, or final completion.

Final Quantitative Acceptance remains **BLOCKED** until the formal Frozen/Live/Local reference requirements and all later phase gates are satisfied.
