# MirrorWeb V5 — current status

Single canonical entry point. Every delivery updates this file.

Last updated: 2026-08-20 (T0 render-loop repair, T1 source-exact typography)

| | |
| --- | --- |
| Repository | `lhfer/mirrorweb` |
| Branch | `rebuild/liquid-glass-v5-source-exact` |
| Source contract | [`config/target-layout-source-v2.json`](../../config/target-layout-source-v2.json), verified by `npm run v5:target-layout-source` |

### Commit semantics

Each field names what that commit contains. `reviewHeadAtDelivery` is the branch
tip this delivery was reviewed at; a file cannot contain its own hash, so it is
stated here and no further hygiene commit is created to chase it.

| field | value |
| --- | --- |
| `sourceContractCommit` | `42ac438` `v5-fsx-source-contract` |
| `codeCommit` | `62bb251` `v5-fsx-source-exact-code` |
| `evidenceCommit` | `6d313bc` `v5-fsx-source-exact-evidence` |
| `metadataCommit` | `4c48aba` `v5-fsx-manifest-hygiene` |
| `acceptanceCommit` | `750d476` `v5-fsx-composition-accept` |
| `hardeningCommit` | `5c24a60` `v5-fsx-integration-hardening` |
| `beautyEvidenceCommit` | `6d1d5bb` `v5-fsx-beauty-baseline-evidence` |
| `evidenceReproducibilityCommit` | `4c3f7ed` `v5-fsx-evidence-reproducibility` |
| `t0FixCommit` | `52afb05` `v5-t0-render-loop-evidence-fix` |
| `typographyCodeCommit` | `847347d` `v5-t1-source-exact-typography-code` |
| `typographyEvidenceCommit` | `39ff3de` `v5-t1-source-exact-typography-evidence` |
| `sourceContractRerunCommit` | `v5-t1-source-contract-tip-rerun` — the 36-viewport engineering contract re-run at `39ff3de` so the Typography gate's Source Contract row reads a verdict out of a file instead of asserting one. Evidence only; no product code. |
| `reviewHeadAtDelivery` | the branch tip after the commits above; resolve with `git rev-parse HEAD`. A file cannot contain its own hash and no hygiene commit is created to chase one. |

### Status

| | |
| --- | --- |
| SourceExact Composition Baseline | **ACCEPTED** |
| Engineering PASS | **YES** |
| Target Visual PASS | **NOT ASSERTED** |
| Typography | **CANDIDATE — READY FOR TYPOGRAPHY PRODUCT REVIEW**, not accepted |
| Motion / Optics | **NOT STARTED**, unmodified |
| Main merge | **NOT AUTHORISED** |
| Old F0 layout baseline | Historical Accepted Baseline, superseded by SourceExact Composition |

### Preview

| | |
| --- | --- |
| Bare route | `http://127.0.0.1:5280/` — still V3, unchanged |
| Current F2.7 | `http://127.0.0.1:5280/?composition=v2` |
| Source-exact | `http://127.0.0.1:5280/?composition=sourceExact` |
| Source-exact foundation | `http://127.0.0.1:5280/?composition=sourceExact&foundation=layout&annotate=0` |
| Typography before | `http://127.0.0.1:5280/?composition=sourceExact` at `847347d^` |
| Typography candidate | `http://127.0.0.1:5280/?composition=sourceExact` at the branch tip |
| Evidence index | [`qa-v5/t1/README.md`](../../qa-v5/t1/README.md) |
| Private review package | `qa-v5/private/t1-review.zip` (git-ignored) |
| Superseded package | `qa-v5/private/fsx-a-review.zip` — captured against a frozen canvas, do not use |

## T0 — render loop repair

The FSX-A round's `tick` contained `if (!this.adaptiveQuality) return;` above
`motion.step`, `grid.update`, `applyPose`, `labels.sync` and `drawFrame`. Every
FSX-A capture ran with the sampler off, so every one was taken against a frozen
canvas. That is why media-only and glass+media came out byte identical and the
24-frame recordings were 24 copies of one image.

| | |
| --- | --- |
| Render loop proof | **PASS 22/22** — 165 frames in 1200 ms with the sampler off; it was 0 |
| Hook redraw | every named hook advances a render stamp synchronously; a paused page does not repaint on its own |
| Media-only vs glass+media | 70–84% of pixels differ, mean delta 11.6–18.1; was byte identical |
| Recordings | 24/24 unique frames desktop and mobile; offsets read back from the engine |
| Quality invariance | **PASS 57/57**, off the real mesh: bbox 656.64 x 492.48 (exactly 4:3), 5570/3242/1850 vertices, a new geometry per level, a redrawn silhouette each |

`qa-v5/fsx-a` is superseded for the media/glass comparison, the recordings and
the quality sweep. Its route proof and source contract stand.

## T1 — source-exact typography

| | |
| --- | --- |
| Typography contract | **PASS 29/29** measured Target properties, at all seven viewports |
| Container alignment | **PASS 47/47** — worst label corner error 0.011 px against the card mid-plane |
| Clipping / depth | **PASS 30/30** — Target's clip structure reproduced; 1199 sampled pixels, 0 wrong depth |
| Label ink outside card silhouettes | **0** at every viewport |
| Source contract, re-run at this tip | **PASS 36/36** — slot world 0.0, orientation 1.21e-6 deg, projected corner 0.0 px, engine vs Target DOM 0.005366 world; `npm run v5:target-layout-source` **PASS 14/14** |
| Viewport gate | **PASS 7/7 viewports, 13/13 engineering** |
| Title baseline | matches the Target to three decimals at all seven viewports |
| Build | PASS |

The defect: `TileLabelLayer` sized every label to the fixed `TILE` box while the
card is `frame.planeWidth` x `frame.planeHeight`, and every type size is a
container query against that box — so type was scaled against a card that did
not exist, by +113% at 667x375 down to −26% at 1920x1080. It was −1.4% at
1440x900, the viewport the layer was tuned at, which is why it went unseen.
See [`SOURCE_EXACT_TYPOGRAPHY.md`](SOURCE_EXACT_TYPOGRAPHY.md).

## FSX-A integration hardening

| | |
| --- | --- |
| Route proof | **PASS 6/6** — `?composition=sourceExact` reaches V4 without `optics=v4` |
| Quality invariance | **PASS 43/43** — corner delta 0 px across high/medium/low/high, contract PASS at every level |
| Adaptive quality | now fires: 2 spontaneous changes recorded by the running sampler |
| Beauty baseline | 7 viewports x 4 render states, 0 capture errors |
| Detector residual | **corrected**: all pairs 132.49 px / 280.50 px, high-confidence 14.17 px / 67.51 px, pairing confidence 0.357 |
| Build | PASS |

Three integration defects fixed, none of them in the composition:
`?composition=sourceExact` routed to V3; `AdaptiveQuality.sample()` compared its
return value with the field it had just written, so the adaptive path had never
fired; and the quality rebuild dropped the source-exact 4:3 geometry override.
See [`FSX_ACCEPTANCE.md`](FSX_ACCEPTANCE.md).

## Commit ledger

**Accepted by product**
- `62f5772` F0/F1 Foundation baseline · `b524dc5` NL-03 media focus

**Candidate, not accepted**
- `dd6d7bf` / `4ca597f` F2 · `b5cff63` F2 audit · `730beb7` F3 diagnosis
- `f56f55e` / `ba4ba32` F2.5 · this delivery's three F2.6 commits

**Superseded / withdrawn**
- F2's `cross-validation.json` — gain stored as scale, hold-out not held out.
- F2's gate revision that replaced the 3 px absolute gutter threshold with a percentage.
- F3's `radiusY = -2053.4` — a parabolic diagnostic seed.
- F2.5's portrait law `1.9468 / -0.31` — **misses the held-out scale by +5.09%**. Replaced by the cross-validated `1.87715 / +0.12204`, still selectable as `?portraitLaw=p0`.
- F2.5's rest-phase scale switch at 0.674 — **23/39 against the runtime law**. Replaced by the aspect rule.
- **F2.6's `portrait-candidate-gates.json` — INVALID.** `portraitLaw` never reached the camera, so p0 and p1 rendered byte identically and that file compared one candidate with itself. Superseded by `qa-v5/f26r/portrait-candidate-gates.json`.

## Verdicts (F2-SX source-exact)

| | |
| --- | --- |
| Engineering result | **READY FOR PREVIEW-FIRST PRODUCT REVIEW** |
| Source contract | **PASS 36/36** — slot world 0.0, orientation 1.21e-6 deg, projected corner 0.0 px, engine vs Target DOM 0.005366 world |
| `npm run v5:target-layout-source` | **PASS 14/14**; failure branch exercised against a mutated contract and exits 1 |
| Pixel gate | **8/14** viewports, **115/122** checks. F2.7 measured identically: 7/14, 112/123. |
| Runtime | **PASS 64/64** |
| F0 regression | **PASS 20/20**, baseline frame byte-identical |
| v1 / v2 / bare route | byte-identical to before; `sourceExact` is NOT the default |
| Build | PASS |
| Target visual result | Not asserted |

Every remaining pixel failure is **gutter centre** (3.5-6.5 px against 3 px).
Card size, card centre, edge yaw, row parity, centre dark band, overlap and
large void pass at every viewport. Two independent measurements show the
residual is the detector meeting a video-filled glass card: reading the Target's
own frame, the detector places card centres up to 2.67 px and widths up to
71.89 px away from the Target's OWN DOM geometry, and our frame reads closer to
that truth than the Target's own frame does at all nine viewports tested.

### Old verdicts (F2.7, on the foundation branch)

| | |
| --- | --- |
| Engineering result | **READY FOR EXPLICIT PRODUCT EXCEPTION REVIEW** — see the caveat in `qa-v5/f27/README.md` |
| Absolute Target Gate | **FAIL** — 7/14 viewports, 107/118 checks. Same measurement scores the F2.6R config 7/14 and 96/113. |
| Target phase determinism | **STABLE** — 12 viewports x 5 cold loads, no variation |
| Row-origin phase law | **36/36** viewports against live Target DOM state, no fitted constant |
| Portrait vertical hold-out | 390x844 card height **4.79% → 1.03%** (V1), 1.57% (V2 with the centre seam fixed) |
| Runtime | **PASS** 32/32 |
| F0 regression | **PASS** 20/20, baseline frame byte-identical |
| Build | PASS |
| Target visual result | Not asserted |

Contract coverage:

```json
{
  "cardCentre": "NOT_MEASURED",
  "cardSize": "NOT_MEASURED",
  "gutterPx": "FAIL",
  "edgeYaw": "FAIL",
  "rowParity": "NOT_MEASURED",
  "centreDarkBand": "FAIL",
  "overlap": "PASS",
  "largeVoid": "FAIL",
  "f0Regression": "PASS"
}
```

NOT_MEASURED comes from 1920x1080 and 667x375, where no row pair survives the
gate's conditioning. Stated, not hidden: 1920x1080's PASS means "nothing
measurable failed".

## F2.7 — the Target's layout is no longer inferred

The authorised read-only source forensics pass recovered the Target's entire
layout initialisation. See
[`TARGET_RESPONSIVE_SOURCE_FORENSICS.md`](TARGET_RESPONSIVE_SOURCE_FORENSICS.md).

- Initial scroll is **(0, 0) at every viewport**; there is no row branch to unwrap.
- The rest phase is the **parity of the Target's pool row count**, not aspect
  ratio. `restOffsetX = (rows/2) % 2 === 0 ? cellW/2 : 0`, 36/36, no free parameter.
- The responsive law is **`max(width, height)`** and is continuous at
  `width == height`. The 1.84x orientation step F2 recorded does not exist.
- The grid is a **sphere**, one radius for both axes, not a cylinder plus a
  separate `radiusY`.
- Three of the four phase mismatches the F2.7 brief named — 667x375, 780x470,
  1440x1080 — **were not mismatches**; F2.6's pixel classifier was wrong there.
- Video assignment is shuffled with `Math.random()` per load. Geometry is not.

### Frozen parameters the source disagrees with

`TILE.width` −1.35%, `TILE.height` −2.63%, `GRID.cellW` −1.87%, `GRID.radius`
−2.59% at 1440x900 and **−18.6% at 390x844**, `restY0` +6.3%, `CAMERA.y` 8 against
0. All frozen by the F2.7 brief and therefore unchanged. The 390x844 edge-yaw
failure is a direct consequence of the radius entry.

## F2.6R correction

A harness defect, not a visual one: `portraitLaw` reached `compositionScale` but
not `viewZoom` or `effectivePerspectivePx`, so with the focal mechanism the
camera used the default law. p0 and p1 rendered byte identically at 390x844.
Fixed, and proven fixed by SHA, by projected card size (278.823 px against
266.576 px) and by a scale derived from the live camera projection rather than
from config. `runtime-law-proof.json` passes 12/12.

Consequence for the record: **p0 and p1 tie at 5/6 on the gate.** F2.6 claimed
p1 was better there. p1 still ships, on the cross-validation alone. No visual
parameter changed in this round.

## Shipping parameters

```
composition   v2   verticalMode tangent   portraitLaw p1
phaseModel    rowOrigin        portraitVertical v2
radiusY -4707.6   cellH 419.95
restY0  landscape -200.99      portrait -209.975  ( = -cellH/2 )
portraitGain      1.87715 + 0.12204 * (aspect - 0.5)     [frozen]
landscapeScale    S = width / 1440                        [frozen]
portrait scaleY   1.03883, applied in the projection, landscape untouched
restOffsetX       (targetRows(viewport) / 2) % 2 === 0 ? cellW/2 : 0
tangentStrength   1.0
```

`scaleY` appears in `qa-v5/f27/portrait-vertical-models.json`; the phase law has
no constant to verify. Not shipped, default off: `?landscapeRowOrigin=centred`,
the landscape half of the `restY0` correction — 9/11 against 7/11 with no
regression, in `qa-v5/f27/gate-diagnostic-landscape-row-origin.json`.

## P0 / P1 / P2

**P0 — 390x844 fails four contract checks.** Card height 4.905% (limit 3), edge
yaw 1.231 deg (limit 0.75), viewport centre not in a horizontal gutter where the
Target has one, largest void excess 2.423% (limit 2). This is not a rounding
residual: card height is 63% over and the centre-band miss is structural.

**P1 — the aspect phase rule has a fragile boundary.** 16:9 sits at 0.5625,
about 0.01 above the 0.5525 threshold. Four sweep viewports disagree
(667x375, 700x700, 780x470, 1440x1080).

**P1 — drag feel varies with viewport**; `dragGain` maps input px to world units
while world-to-screen no longer does. Motion is frozen.

**P1 — glass rim eats the gutter on yawed cards** (11 px rendered vs 19 px).

**P2 — some Target scale fits do not converge** and are excluded by a fixed RMS
threshold, listed rather than dropped.

**P2 — cyan/magenta rim fringing; typography 9.2cqw vs 12cqw; TILE.radius 58 vs ~61.5.**

**P2 — `npm run v4:source` fails**, four checks from the baseline and three from
V5. Not re-baselined; the product owner's call.

## Next stage

F2-SX is delivered. `sourceExact` is a separate, non-default path; v1 and v2 are
untouched and the old F0 layout baseline is a **Historical Accepted Baseline,
superseded only for the source-exact path**. Not merged to main.

The open product decision is whether to adopt `sourceExact` as the composition
baseline. Adopting it retires the fitted portrait gain, the portrait vertical
scale, `radiusY`, the aspect phase threshold, the fitted `restY0` and the fixed
9x9 world grid, and makes `TILE`, `GRID.cellW` and `GRID.radius` irrelevant to
layout: the source contract replaces all of them.

Typography, Motion and Optics remain **NOT STARTED**.

### Superseded F2.7 decisions

1. Whether to accept the remaining 390x844 residual as an explicit exception. It
   is **structural**, not a rounding residual: our frozen curvature radius is
   18.6% too small there because the Target's radius follows `max(w, h)` while
   our world is fixed and scaled by width.
2. Whether to ship the landscape half of the `restY0` correction, which is
   measured, runnable and regression-free but outside F2.7's portrait-only scope.
3. Whether to unfreeze `TILE`, `GRID.cellW`, `GRID.radius` and the scale laws so
   the composition can be rebuilt on the Target's own numbers rather than fitted
   to them. Forensics makes that a transcription job rather than a fit.

Typography, Motion and Optics remain **NOT STARTED**.

## Frozen systems

Typography and TileLabelLayer visual parameters, MotionController,
InputController, MOTION, LiquidGlassMaterialV4, refraction, dispersion, blur,
reflection, environment, video focus and MediaFit, grid pool structure,
TILE.width, TILE.height, GRID.cellW, the horizontal radius, and the accepted F1
are all unchanged.
