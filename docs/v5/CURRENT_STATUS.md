# MirrorWeb V5 — current status

Single canonical entry point. Every delivery updates this file.

Last updated: 2026-08-21 (M3 final motion source reconciliation: the magnitude MotionValue's two writers, read out of the Target's frame scheduler)

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
| `motionForensicsCommit` | `990bcce` `v5-m0-target-motion-forensics` — the motion source contract, read out of the Target's bundle and replayed against it. No product code. |
| `motionCodeCommit` | `655fda4` `v5-m1-source-exact-motion-code` — the source-exact motion model. Frozen files byte-identical to `7dc7cf1`. |
| `motionCorrectionsCommit` | `e97bc17` `v5-m1-source-exact-motion-code-corrections` — the first gate run FAILED and found four engine defects, four instrument faults and two contract errors. Not one of the four mandated commit names, and named rather than folded into one of them: it is product code, and a reviewer reading the ledger should see that the code commit was corrected before any evidence was captured against it. |
| `motionReleaseFixCommit` | `8e947b9` `v5-m1-source-exact-motion-release-and-instruments` — the release was applied out of band; three more instruments replaced. |
| `motionEvidenceCommit` | `788e6a7` `v5-m1-source-exact-motion-evidence` — captured at `8e947b9`. `d8447de` then removed the recordings from the public tree; the oversized blobs remain in this branch's history, because removing them needs a history rewrite and this branch does not permit one. |
| `m2InstrumentCommit` | `cff917b` `v5-m2-motion-instrument-and-gate-repair` — the ordering instrument, the direction-aware gate, and the Target-only baseline, sealed before the candidate was captured. No product code. |
| `m2CodeCommit` | `30dcf64` `v5-m2-motion-closure-code` — scheduling readbacks, the camera comments that contradicted the code they sat above, and the `labelCamera` → `css3dTransformCamera` rename. No motion behaviour changed. |
| `m2EvidenceCommit` | `v5-m2-motion-closure-evidence` — captured at `30dcf64`. |
| `typographyAcceptCommit` | `7dc7cf1` `v5-t1-source-exact-typography-accept` — product acceptance of T0 and T1, the typography freeze contract, and three evidence wording corrections. No product visual code. |
| `reviewHeadAtDelivery` | the branch tip after the commits above; resolve with `git rev-parse HEAD`. A file cannot contain its own hash and no hygiene commit is created to chase one. |

### Status

| | |
| --- | --- |
| SourceExact Composition Baseline | **ACCEPTED** |
| Engineering PASS | **YES** |
| Target Visual PASS | **NOT ASSERTED** |
| T0 Render Loop Repair | **ACCEPTED** |
| Typography | **ACCEPTED** — frozen, see the freeze contract below |
| Motion / Pointer / Touch | **ACCEPTED — FROZEN**, see [`MOTION_FREEZE_CONTRACT.md`](MOTION_FREEZE_CONTRACT.md). M0–M3 results below are history |
| V0 CSS3D label coverage culling | **READY FOR CSS3D CULLING PRODUCT REVIEW** — absolute gate PASS, see the V0 section |
| Optics / Media / Layout | **NOT AUTHORISED THIS ROUND**, unmodified |
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
| Hook redraw | every named hook advances a render stamp synchronously; with no QA hook called the explicit render stamp stays unchanged between two reads. The stamp counts `renderOnce()` calls, so it says the explicit draw path did not run -- not that the browser did not composite, which the stamp cannot see |
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
| Clipping / depth | **PASS 30/30** — Target's clip structure reproduced; 1199 sampled pixels, 0 wrong depth. **Scope:** `actualOverlappingCardPlaneSamples = 0`; with no two card planes observed overlapping on screen this establishes the clip structure and single-card interior ordering, not real occlusion ordering. Carried to the motion stage |
| Label ink outside card silhouettes | **0** at every viewport |
| Source contract, re-run at this tip | **PASS 36/36** — slot world 0.0, orientation 1.21e-6 deg, projected corner 0.0 px, engine vs Target DOM 0.005366 world; `npm run v5:target-layout-source` **PASS 14/14** |
| Viewport gate | **PASS 7/7 viewports, 13/13 engineering** |
| Title box bottom offset | `titleBoxBottomOffsetPct` -- card bottom to the bottom EDGE of the title box, as a percentage of card height -- matches the Target to three decimals at all seven viewports. Renamed from `titleBaseline`: the instrument reads boxes, not font metrics, so no baseline was ever measured |
| Build | PASS |

The defect: `TileLabelLayer` sized every label to the fixed `TILE` box while the
card is `frame.planeWidth` x `frame.planeHeight`, and every type size is a
container query against that box — so type was scaled against a card that did
not exist, by +113% at 667x375 down to −26% at 1920x1080. It was −1.4% at
1440x900, the viewport the layer was tuned at, which is why it went unseen.
See [`SOURCE_EXACT_TYPOGRAPHY.md`](SOURCE_EXACT_TYPOGRAPHY.md).

## M0 / M1 — source-exact motion

The Target's motion was read out of its bundle, not fitted to a recording. The
whole model, its absences and the two things that make it feel the way it does
are in [`SOURCE_EXACT_MOTION.md`](SOURCE_EXACT_MOTION.md); the contract itself
is [`config/target-motion-source-v1.json`](../../config/target-motion-source-v1.json).

What our previous model had and the Target does not: wheel handling of any
kind, a maximum velocity, a stop threshold, an exponential inertia decay, a
pointer-driven card tilt, a pointer-driven camera translation, a pointer-driven
light, and pointer capture on the drag surface. The Target's scene contains no
light object at all — its highlight moves because the camera orbits against a
fixed environment.

Our previous drag gain was 0.58 against the Target's 1.5, and the source-exact
path inverted `scrollX` at the layout boundary because the legacy model
subtracts the drag where the Target adds it. Both are gone: the model carries
the Target's own sign from the gesture onward.

### M1 result

| | |
| --- | --- |
| Motion gate | **FAIL — 806/870 landmarks.** 64 failures, in three related families plus eleven small travel rows |
| Contract vs Target | model replayed on the Target's own input: within the Target's own noise on **53/56**, raw and time-aligned |
| Recovery instrument | **exact** — 0.006–0.025 world units against our engine's own scroll over 20 runs |
| Wrap continuity | **0 visible teleports**, ours and Target, screen-space at the brief's 2 px |
| Wheel absence | **72/72**, deltaMode 0/1/2, both sides |
| Axis signs | **0 failures** |
| Card / label under motion | **PASS 34/34**, worst corner delta well inside 1 px |
| Typography regression | **PASS 4/4** — container alignment 47/47, depth 30/30, label ink 0 outside |
| Depth carry-forward | **PASS 37/37**; `actualOverlappingCardPlaneSamples = 0` → **NOT APPLICABLE — no overlapping card planes observed** |
| Source contract, re-run at this tip | **PASS 36/36**; `npm run v5:target-layout-source` **PASS 14/14** |
| v1 / v2 / bare | geometry identical to `7dc7cf1` on all six route-viewport pairs; the pixel comparison is provably incapable across origins and is reported, not gated |
| Console / page errors | **0** |
| Build | PASS |

The 64 failures are one fact three times over: the Target's scroll advances
12.7% off its local trend on a typical frame and ours advances 1.8% — two
independent rAF loops against our one. It surfaces as `frameStepJitterFraction`
(ours lower in 26/26), `maxFrameVelocityStep` (7/7) and the dolly peak, whose
magnitude source is a backward difference that jitter inflates.

### M2 result — the instrument was the largest single defect

The M1 replay decided which frame consumed an event with `event.t <= frame.t`.
Those are two different points in the frame pipeline: listener entry on
`performance.now()` against the rAF timestamp, which is when the frame STARTED.
Chrome dispatches input before the rAF block, so a median of 88% of all
recorded events were handed to the following frame — one dispatch late, always
the same direction. That is the whole of M1's "persistent final error": 0.1457
of travel on every reverse-flick row and 0.0527 on every fast-flick row,
identical across four viewports and three repeats.

M2 replaced the clock comparison with a monotone callback counter, sealed a
Target-only baseline by SHA-256 before capturing any candidate, and made the
one-sided gate direction-aware.

| | |
| --- | --- |
| Motion gate | **FAIL** — 149 failures of 2472 product-gated comparisons, 90 distinct cells across the 120 Hz and 60 Hz grids |
| Engine vs contract v2 | 180 rows, **175 exact to floating point**, 3 sub-frame race, 2 failures |
| Contract vs Target | the frozen contract on the Target's own input reproduced it in **1518/1576** |
| Dolly attribution | M1 blamed the Target's frame-step jitter. **Refuted by measurement**: feeding the magnitude spring the Target's own jittered scroll moved the peak by 0.3% while the Target stood 17.7% from the frozen law |
| Failure split | 92 dolly, 53 release velocity, 1 travel, 3 systematic sign |
| MOTION-EXC-01 | raised: the Target's raw frame-step scheduling irregularity is not reproduced |
| Baseline | sealed at `a0a5a1f6b95b685e18453d889a9a57798fd6f73e9e47d9edc9c2a087ddf29224` |

Evidence: [`qa-v5/motion-closure/`](../../qa-v5/motion-closure/). M2 recorded a
hypothesis it deliberately did not act on — that the magnitude source has two
writers that disagree by construction — because closing a residual by picking
whichever order fits is a fit and not a reading. M3 read it.

### M3 result — the magnitude has two writers and the Target's scheduler picks one

**ACCEPTED by product.** Motion behaviour baseline `4df03f2`, accepted review
tip `b99e5ce`. Motion / pointer / touch are frozen — the contract, the accepted
known deviation (release scroll retarget, +1 postRender frame), and the
standing items (two unresolved summary rows, eight `dollyPeakTimeMs` cells) are
in [`MOTION_FREEZE_CONTRACT.md`](MOTION_FREEZE_CONTRACT.md). M4 is not
authorised.

M2 recorded the two-writer hypothesis and refused to act on it. M3 read the
Target's frame scheduler and found which writer wins, so the order is a source
read rather than a fit.

| | |
| --- | --- |
| Writer order | `gestureLastWhileActive`, read from the bundle: `onPan` is scheduled with `immediate=true` into the update Set that is being iterated, so the gesture writer lands after every spring tick; `onPanEnd` is scheduled onto `postRender` from the pointerup listener, so it is first in that set, ahead of the spring's retarget |
| Dolly on the Target's own input | signed **1.0249**, median absolute **2.58%** — against **0.9514** / **17.82%** under the pre-M3 order. Both numbers are reported: the drag and flick residuals have opposite signs and the signed one cancels them |
| Dolly cells failing | **8 of 432**, from 92 of 432 under the M2 order |
| Engine vs contract | **180/180 exact to floating point**, 0 failures, worst final error 0.00e+00 against a 0.13276 gate |
| Release velocity | **132/132 exact to floating point** against the engine's own release record. 48 runs carry no release by design — 36 wheel, 12 pointer sweep |
| Landmark failures | **65** of 2570 comparisons, 2472 product-gated |
| Attribution | candidate-owned **0**; source contract 38, target input variation 18, instrument unreadable 7, unresolved **2** |
| Constants | unchanged. Drag gain 1.5, fling 0.1, both springs, 3 px threshold, 100 ms window, orbit ±0.05 rad, dolly formula, publication delay all frozen |
| MOTION-EXC-01 | still raised, unchanged, and still covers only the raw single-frame numbers |

Two results that are worth carrying forward on their own:

- **The release velocity is quantised.** framer-motion's window is a strict
  `> 100 ms` over a history fed at frame rate, so a release measures over N or
  N+1 points and nothing between. The Target's own three repeats of one scripted
  gesture land on opposite sides in **33 of its 44 cells**, spreading its own
  release velocity by a median 7.78%. No implementation can close that; the gate
  was deliberately NOT taught to forgive it.
- **The eight dolly cells that still fail are all `dollyPeakTimeMs` on slow
  drags**, with a candidate residual of **0.0 ms** on every one. Our capture's
  31-step drag ran 1106 ms against the Target's 1003 ms, and a flat dolly peak
  sitting at the release moves with it. Reported per §8 and not excepted.

Evidence: [`qa-v5/motion-final/`](../../qa-v5/motion-final/).

## V0 — source-exact CSS3D label coverage culling

**READY FOR CSS3D CULLING PRODUCT REVIEW.** The Target keeps ~16 labels alive
at 1440x900 where our page kept 81 — its only test was a JS backface
dot-product. V0 read the Target's culling out of its bundle byte by byte
(30 anchored sites, live bundle byte-identical) and implemented it in
[`SourceExactLabelCulling.ts`](../../src/ui/SourceExactLabelCulling.ts):
a dedicated dolly-free coverage camera (`Py.position.set(d,h,f)` against the
render camera's `(d,h,f+p)` in one source statement), the four projected card
corners, the NDC z skip, the 1 px² minimum area, the exact 64 px margin.
Visibility / culling only; every frozen system untouched.

| | |
| --- | --- |
| Target rule source verification | **PASS** — 20,131 Target frames replayed slot-for-slot; 0 beyond boundary; 363 wrap-seam rows, every one with the flip demonstrated under ±1e-3 perturbation |
| Candidate rule consistency | **PASS** — 20,372 frames, 0 mismatches; snapshots bit-exact to 9.1e-13 px |
| Settled slot identity vs Target | **40/40 states identical, by ILG code** (incl. resize and orientation flip) |
| Lost / intruding / stale labels | 0 / 0 / 0 — stale-rect check worst delta 0.0135 px over 2,456 drawn labels |
| Edge pop-in | candidate 171.7 px vs Target's own 171.0 px worst entry overlap — comparable, PASS |
| DOM pressure | transform writes p95/frame 120 → 36 (Target 36); sustained-input p95 100 → 17 |
| Performance | labels.sync 0.3 ms p95, frame time unchanged (GPU-bound), heap bounded, quality untouched |
| Depth | **NOT APPLICABLE on screen, measured**: 0 front-facing overlaps inside the strict viewport; 30 pairs live only in the 64 px margin band |
| Motion freeze smoke | PASS — engine vs contract 15/15 exact, release history 11/11, wrap teleports 0; card/label corner delta 34/34 |
| Regressions | source contract 36/36, layout 14/14, typography 4/4, tsc + build PASS, console/page errors 0 |

Observed in source and deliberately NOT applied: the Target drives its WebGL
glass-mesh `visible` from the same verdict. Outside V0's label mandate;
flagged for a product decision. Evidence:
[`qa-v5/culling/README.md`](../../qa-v5/culling/README.md); private package
`qa-v5/private/culling-review.zip`.

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
- M3 motion source reconciliation: `b8cbbd2` writer-order forensics · `4df03f2` writer-order code (motion behaviour baseline) · `8f906f1` evidence · `b99e5ce` hygiene (accepted review tip) · `17fcaca` acceptance record (docs)

**Candidate, not accepted**
- V0 label coverage culling: `820cd92` code · the evidence commit at this tip
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

Typography is **ACCEPTED and frozen**; Motion is authorised and in progress;
Optics remains **NOT STARTED**.

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

## Typography freeze contract

Accepted by the product owner at `34ad481` and frozen from that commit. Each
line names the artefact that holds it, so a later change is a diff and not an
argument. Changing any of these needs a new product authorisation.

| frozen | where it lives | what fixes it |
| --- | --- | --- |
| SourceExact `TileLabelLayer` plumbing | [`src/ui/TileLabelLayer.ts`](../../src/ui/TileLabelLayer.ts) | `attach(grid, mode, frame)` / `setFrame(frame)` / `applyBox()`; the frame is the single source of the label box |
| Scheme A: element = `frame.planeWidth` x `frame.planeHeight`, object scale = 1 | `applyBox()` | the Target's label element width equals the card plane width and its `matrix3d` basis columns are unit length, at all seven viewports |
| SourceExact `TYPE_Z = 0` | `TYPE_Z_SOURCE_EXACT` | radial distance from the sphere centre to each Target label = R within 1.2e-3 world units, across 36 viewports |
| `.tile-card-se` / `.se-*` typography CSS | [`src/style.css`](../../src/style.css) | 29/29 measured Target properties, at seven viewports, one instrument both sides |
| Rule / title / deck DOM order | `bindSlotCard` | the Target's rule PRECEDES the title; our earlier markup had title, rule, deck |
| Clip layer | `.se-clip` | one absolute layer at the card box, `overflow: hidden`, no clip-path, no radius |
| Footer typography | `.experiment-link`, `.cta-link`, `.cta-arrow`, `.brand-word` | the Target's own footer computed styles |

Scope carried forward rather than claimed: `actualOverlappingCardPlaneSamples`
is **0**, so the depth result establishes the clip structure and single-card
interior ordering only. Motion moves the planes; the count is re-taken there.

## Frozen systems

TileLabelLayer plumbing, the typography CSS above, LiquidGlassMaterialV4,
refraction, dispersion, blur, reflection, environment, video focus and MediaFit,
grid pool structure, TILE.width, TILE.height, GRID.cellW, the horizontal radius,
and the accepted F1 are all unchanged.

`MotionController`, `InputController`, `MOTION` and the source-exact pointer /
pose mapping are **UNFROZEN** for the authorised Motion stage. Nothing else is.
