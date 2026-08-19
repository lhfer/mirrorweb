# V4 Optics Lab Foundation

Status: **PASS — Phase 1 deterministic structural gate only**

Final Quantitative Acceptance: **BLOCKED**

Canonical result: `qa-v4/results/optics-lab-foundation.json`

Canonical result regenerated from clean commit-bound evidence: `2026-08-19T13:25:12.239282+00:00`

This result authorizes continued work inside Phase 1. It does not authorize main-page integration, Phase 2 Typography, a visual-match claim, a performance-match claim, or final acceptance.

## Scope and architecture boundary

The foundation is isolated at `/glass-lab-v4`. The production entry point and its default V3 implementation remain unchanged.

- The Lab renders one controlled optical specimen and supports V3, V4, Split, and Difference views.
- V4's normal path is `background scene -> linear half-float Scene Color Target -> V4 refraction body -> final tone mapping/output conversion`.
- V4 does not accept or mix a direct media texture in its normal material path. The captured runtime contract records `normalPathDirectMedia: false`.
- The V4 target was captured at High quality, scale `1.0`, `1114 x 900`, linear color, half float.
- At this historical foundation commit, V4 geometry exposed `aEdgeDistance`, `aShoulder`, `aSidewall`, `aThickness`, and `aCurvature`; Phase 1B later added independent `aLensRim` without rewriting this evidence.
- Refraction and reflection are separate layers. Reflection uses a programmatic strip-light environment and a pointer-driven key light; it does not hotlink target-site lighting assets.
- Debug views cover Beauty, Edge Mask, Normals, Thickness, Refraction Offset, Reflection, Fresnel, Dispersion, and Adaptivity.
- The Lab exposes controlled QA state and setters for mode, pattern, debug view, and normalized pointer input.
- Deterministic test patterns are generated locally. Private reference media is neither loaded by the normal V4 path nor committed.

The runtime contract passed with `v3Preserved: true`. Main-page Motion, Typography, Grid, layout, and the stable V3 material are outside this foundation's authorized change surface.

## Captured environment

| Field | Captured value |
| --- | --- |
| Capture time | `2026-08-19T13:15:59.172Z` |
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
| Served resource count | `50` |
| Served resource manifest SHA-256 | `596a09ede0f0dcb7fcc9255f60ab80d8e107042203bd566de84ed2bac426b768` |

Captured source identity is branch `rebuild/liquid-glass-v4`, HEAD `3f57807cd6927935bd854a8a5ae7dbb1e551f4dd`, with runtime source-set SHA-256 `e50dd5f0d82689125056865d2e043e6072ddceff775d8c326eab765c67e503b3`. `dirtyWithinRuntimeScope = false`. This supersedes the pre-commit `d7f4e319` evidence binding without changing the accepted foundation architecture.

## Structural metrics

All nine checks below passed the thresholds recorded in the canonical JSON. Passing means that the first-round structural property is measurable in this deterministic Lab capture; it does not mean the value has been fitted to the Frozen Visual Golden.

| Check | Measured value | Gate | Result |
| --- | ---: | ---: | :---: |
| Center/Rim sharpness ratio | `1.475648` | `>= 1.0` | PASS |
| Rim width / short card side | `0.107903` (`71 px`) | `0.015–0.25` | PASS |
| Horizontal line continuity | coverage `0.997096`; score `0.928263`; outer displacement `2.315516 px` | coverage `>= 0.8`; score `>= 0.7`; displacement `>= 1.5 px` | PASS |
| Vertical line continuity | coverage `0.975731`; score `0.827141`; outer displacement `2.463565 px` | coverage `>= 0.8`; score `>= 0.7`; displacement `>= 1.5 px` | PASS |
| Four-corner continuity | `0.999654` | `>= 0.4` | PASS |
| Pointer highlight path | 7/7 valid; travel `0.694293`; max/median jump `1.771056`; X correlation `0.911380` | travel `>= 0.03`; jump ratio `<= 3.5` | PASS |
| Dispersion energy in outer zone | `0.999999797` | `>= 0.9` | PASS |
| Dark-background discernibility | `0.177112` | `>= 0.015` | PASS |
| Light-background discernibility | `0.016907` | `>= 0.015` | PASS |

Additional diagnostics, not separate acceptance gates:

- Difference view: mean absolute luma `0.294794`, P95 `0.964706`, non-trivial pixel ratio `0.499303`.
- Browser rAF interval: 1,741 samples; P50 `8.30 ms`, P95 `9.20 ms`, P99 `9.30 ms`, maximum `83.00 ms`.
- The rAF numbers describe browser scheduling intervals. They are not CPU render cost and are not WebGPU timestamp-query measurements.

Sanitized plots are committed without private pixels:

- `qa-v4/results/optics-lab-foundation-artifacts/displacement-plot.svg`, SHA-256 `403a61588957bb88f35c10f8a9ee38fc9e6d675dbd6137ae4301922cc0273423`
- `qa-v4/results/optics-lab-foundation-artifacts/highlight-path.svg`, SHA-256 `b724b43ddad92670091ff61531bc0d7ac5a91741a84346a135c38ec16add4329`

## Private evidence identity

The following identities were read from the retained clean `3f57807` rerun manifest. No absolute filesystem path or private pixel/video payload is recorded here.

| Private evidence | SHA-256 |
| --- | --- |
| Complete screenshot set | `8e45f6053260124ad158bda7e81c93266777bb9b85aa5fd6a0d4da0580367722` |
| Input capture manifest | `4ad727a12ffe63f16541ef7d3ebf85bfe14f46fbdb5700f0ca282fe58285642e` |
| Measurement evidence set | `108cb070d54dcc27882d96a297d2b351158f10ce195f98eb2bd558bc50be00f3` |
| Full Lab session video | `26993e2a4b8c4fd5b75fa2c6ec2206697900d1e8935c397ac5326e291eab31b0` |
| Split-view UI preview | `e60446d8c7b729c4324de15421ff653f4ac85f6ec28bf6a19439d755c00e882b` |
| V3/V4 split checker | `5d702b761abc9cd95d4f6a21687f03c90c6537647da1383415850b9ec0317049` |
| V3 control checker | `b4d7760a36bb6af1d84b9e3febc84f01ac9dbcd1d376ba89fffdc538f74c589f` |
| V4 checker | `55d0d4a3f6b23988684bb656d910b799fe9c2c9793254dab5a62847dc881ad72` |
| Difference checker | `3d3117cc391a31e17bcbf46c9ed24fd1bf4131e7c28e1fe211a5be27ce1fcfe9` |
| Edge mask | `1dfb066e109c34352055a3e8cd8ead56d4b094976fd5180e5d18d6e1ba367b43` |
| Horizontal lines | `8046a8b2a42454ea259a61f52a3bf726faed0b4ad1d3c42a8d51a2138c429e54` |
| Vertical lines | `bd39bac930812812df7e4a847bd25f481d79266875f8341b96c76e6f80e0833c` |
| Dispersion debug | `cf8ca6c896b36d0201c03099b18964972c490349fc2726028619159fed14aa08` |

The seven pointer/reflection frames are individually hash-locked in the canonical result. Their ordered set produced highlight travel `0.694293` with a max/median jump ratio of `1.771056`.

## Retained prior attempts

Attempts 01–08 remain retained locally as capture and metric manifests. They were not deleted or rewritten after the clean commit-bound rerun replaced their public evidence binding.

| Attempt | Capture time | Screenshot-set SHA-256 | Outcome / reason superseded |
| --- | --- | --- | --- |
| 01 | `2026-08-19T09:53:31.113Z` | `89ad3f0c63edbb512ab3887f1309b45c01d2b84503989d4a28787d477651bdbc` | Invalid checker-contaminated Mask and zero-displacement false-positive; dark-background failure |
| 02 | `2026-08-19T09:56:30.608Z` | `0a41f5bb81f6df2b1a3702a9b4089d805db22f55d03ed9ce0d9eecffc20ce08d` | Invalid checker-contaminated Mask and zero-displacement false-positive; dark-background failure |
| 03 | `2026-08-19T10:10:06.103Z` | `37c4479d39c04347c5ef8485965bd04ef9f88c2ff1af9cf8231e534594e11301` | Horizontal displacement, vertical displacement, light-background discernibility |
| 04 | `2026-08-19T10:13:50.918Z` | `8ff4a585510e5b9f6f9e2d9d933ab13ac21e4e6ca120045fff76643604056ff4` | Horizontal displacement, vertical displacement, light-background discernibility |
| 05 | `2026-08-19T10:15:23.606Z` | `22f9da39adc7a36b9dc38bba548a766e5fdc1978f811acfa0d67577ca636b141` | Light-background discernibility |
| 06 | `2026-08-19T10:16:33.400Z` | `ff661c5d573605863071d60cc31ca2f6d8952b83a6740274db58d8ffc3d4e5c5` | Structural PASS, superseded after review corrected the fallback-adapter gate |
| 07 | `2026-08-19T10:34:40.343Z` | `f113ef756dac9f6887db077452c915c8e0ab3b2b511402ad1f989baf2b244753` | Structural PASS, superseded after final diff-check normalized two runtime-file EOFs |

Attempts 01–02 were explicitly invalidated after review showed that the checker background inflated the silhouette to 88.1% of the canvas and the old continuity metric could pass with zero displacement. They are retained as audit evidence, not counted as valid optics measurements. Attempt 06 passed the optics checks but was superseded because the hardware gate read the fallback flag from the wrong adapter object; Attempt 07 was superseded only to bind the final normalized runtime bytes; attempt 08 was still pre-commit. None of these attempts contributes to the canonical clean `3f57807` PASS, and they must not be removed merely because a later run passed.

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
- The canonical foundation capture is now bound to clean commit `3f57807`; later Phase 1B evidence uses a separate runtime source-set and cannot overwrite this baseline.

## Gate decision

`v4-02-optics-lab-foundation` is permitted to continue only within Phase 1: refine the isolated V4 optical model, extend deterministic and natural-media Lab evidence, and compare it with the Frozen Visual Golden ROIs.

The following remain prohibited at this gate:

- Integrating V4 into the main page or changing the default V3 route.
- Changing main-page Typography, Motion, Grid behavior, or layout.
- Starting Phase 2.
- Deleting V3 or removing failed evidence.
- Claiming Frozen Visual Golden parity, strict Motion parity, target performance parity, or final completion.

Final Quantitative Acceptance remains **BLOCKED** until the formal Frozen/Live/Local reference requirements and all later phase gates are satisfied.
