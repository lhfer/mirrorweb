# O5 — Source-Exact Card Optical Body

**Final state: O5 TARGET-SOURCE BODY FAILED ABSOLUTE GATE**

Absolute gate: **FAIL** — 8 of 14 items passed, 6 failed, 0 pending.

The shipped default stays `opticalBody=current`. This brief registers no automatic flip and its final states do not include one; product review owns that decision. **Target Visual PASS: NOT ASSERTED.**

## §六 — control identity

**PASS.** 35 comparisons — 5 viewports x 7 states — between `opticalBody=current` at the O5 code commit and a `5a87751` worktree build on deterministic shared media: **exactly zero** differing pixels, every state probe matching, 0 console errors.

Every comparison below is therefore against the accepted O2 body and not against something that drifted.

## §七 — compiled body audit

**15/15.** The candidate's program contains 5 `refract()` calls at high and 3 at low, tracking the sample count exactly; declares **no shared normal varying at all**, so the O4A zero-normal defect has no surface to occur on; and compiles to 13691 bytes against the control's 28304.

The analytic normal decodes to unit length on 95.0% of 634495 card pixels with per-channel standard deviation [46.94, 46.119, 46.619] — the O4A discriminator, where a zero normal reads as std 0. Zero non-finite and zero all-black pixels.

Item 9 is settled at runtime rather than by a string search: the scene-colour pass draws 0 calls and the media plane is hidden, yet the cards still show media. Item 10 carries a positive control — the same probe finds 20 explicit-LOD samples in the control program and 0 here.

## The fourteen gate items

| # | Item | Result |
|---|---|---|
| 1 | reflection band width enters the Target window | **PASS** |
| 2 | dark-side edge luma enters the Target window | **FAIL** |
| 3 | white reflection ratio enters the Target window | **FAIL** |
| 4 | grayscale adds no colour | **FAIL** |
| 5 | saturated edge chroma approaches the Target without a broad coloured rim | **PASS** |
| 6 | HF checker preserves content-local spectral structure | **PASS** |
| 7 | edge compression reproduces the Target's direction and magnitude | **FAIL** |
| 8 | own-media isolation: no neighbour bleed, no scene-colour cross-card contamination | **PASS** |
| 9 | interior fidelity: luminance, chroma, sharpness, cover position | **FAIL** |
| 10 | silhouette matches the Target's SDF rule; no light beyond the rounded rect | **FAIL** |
| 11 | pointer reflection moves in the Target's direction without a discontinuity | **PASS** |
| 12 | no temporal pop during pointer sweep, slow drag, fast flick or touch release | **PASS** |
| 13 | portrait and landscape show the same optical direction | **PASS** |
| 14 | full-frame reading: no longer thick white plastic, a coloured glass frame, or a blurred scene-colour lens | **PASS** |

## What the candidate achieved

**The reflection band enters the Target's window at every viewport** — the measurement O3 and O4 both failed.

| Viewport | Target | control | candidate | window | candidate Δ |
|---|---|---|---|---|---|
| 1440x900 | 3.3 px | 15.3 px | **3.3 px** | ±1.5 | 0.0 |
| 390x844 | 1.5 px | 8.0 px | **2.0 px** | ±1.5 | 0.5 |
| 844x390 | 2.0 px | 8.0 px | **2.0 px** | ±1.5 | 0.0 |
| 700x700 | 2.0 px | 7.0 px | **2.0 px** | ±1.5 | 0.0 |

Dark-side edge luminance lands on the Target at three of four viewports, from a control that was roughly twice as bright:

| Viewport | Target | control | candidate | window | enters |
|---|---|---|---|---|---|
| 1440x900 | 48.15 | 95.19 | **48.61** | ±6.0 | yes |
| 390x844 | 51.28 | 78.94 | **58.46** | ±6.0 | NO |
| 844x390 | 86.19 | 94.43 | **87.05** | ±6.0 | yes |
| 700x700 | 44.2 | 89.83 | **44.47** | ±6.0 | yes |

- Item 6: per-tile high-frequency structure correlates **0.9274** with the Target across 4477 tiles, against the control's 0.6886 and a floor of 0.7. HF energy retention is 1.0276 — the candidate reads 153.6823 against the Target's 149.548, where the control reads 183.3412.
- Item 8: own-media isolation is structural — the refracted UV is clamped before the cover transform, and the scene-colour pass draws nothing in this lane.
- Item 12: no pop on any recorded sequence.
- Item 14: the candidate is closer to the Target than the control on all three failure modes §九.14 names — band width 3.3 vs the Target's 3.3 (control 15.3), interior high-frequency energy 153.6823 vs 149.548 (control 183.3412). The third sub-check, fringe width on cool-blue, reads 0.0 for all three lanes and is therefore DEGENERATE — it carries no signal and its "closer" verdict is vacuous. Two of three sub-checks discriminate; that is what the item rests on.

## What failed, and which failures are the instrument's

Six items failed. They are not all the same kind of thing, and the difference matters more than the count.

### Candidate behaviour

**Items 2 and 3 fail at 390x844 only.** Dark-side luma reads 58.46 against a Target of 51.28 (window ±6.0), and the white reflection ratio 3.8712 against 4.9035. Both are inside the window at the other three viewports, and both moved toward the Target from the control everywhere. Portrait mobile is the narrowest card in the set, so its bevel occupies the largest fraction of the card — the one geometry where a small error in the bevel profile has the most room to show.

### Instrument limitations, reported as failures because the codings were sealed

These three were sealed before capture and are scored exactly as written. Each is a FAIL. In each case the diagnosis is that the instrument, not the candidate, is what could not do the job — and that is recorded here rather than fixed after the fact, because fixing a coding once its pixels exist is the failure mode the whole sealing discipline exists to prevent.

**Item 4 — grayscale chroma.** The candidate reads 18.0 against a ceiling of 6.0. So does the control, at 18.0 — and so does **the Target, at 30.0**, five times the ceiling. The ceiling was set as an absolute and is simply too tight for media that has been through a 4:2:0 video encode, where chroma subsampling puts colour on every sharp luminance edge. A test the Target fails worse than the candidate is not measuring the candidate.

**Item 9 — interior fidelity.** The sealed coding asks that the candidate be *no blurrier than the control*, which is the wrong question: on hf-checker the Target reads 149.548, the control 183.3412 and the candidate 153.6823 — the candidate is far closer to the Target and fails the item *for being closer*, because the control is sharper than the Target is. The coding should have asked for proximity to the Target.

But re-scoring it that way would not simply flip it, and saying so matters more than the excuse. Under a proximity coding the candidate wins hf-checker decisively (Δ 4.1 against the control's 33.8) and loses bw-split (3.57 vs 3.40) and rgb-bars (3.21 vs 2.87) narrowly. Those two assets have flat interiors, so the interior sharpness measure is sitting near its own noise floor there — all three lanes read between 1.2 and 5.7 on a scale where the textured asset reads 150 — and a 0.2 difference between numbers that small is not evidence of anything. The honest summary is: strong on the asset that has interior structure to measure, indeterminate on the two that do not.

Interior chroma is the more interesting number and is not part of the item's verdict: on hf-checker the candidate reads 79.073 against the Target's 79.772, where the control reads 0.116. The candidate reproduces the Target's interior spectral behaviour almost exactly; the control has none of it at all.

**Item 10 — silhouette.** The instrument evaluates an axis-aligned rounded-rect SDF over the card's screen-space bounding box. The cards are perspective-projected onto a sphere, so their quad corners sit up to **109 px** away from the bounding box corners, and the region the instrument calls "outside the silhouette" therefore contains background and neighbouring cards. Both lanes fail it — the control at 18348 lit pixels, the candidate at 12232 — which is the tell: a test that fails the accepted body as well as the candidate is not separating them. At 844x390, where the card rect is clamped to the viewport, a synthetically PERFECT rounded-rect card scores indistinguishably from the real render, so the item carries no silhouette signal there at all.

**Item 7 — edge compression.** The analytic flat baseline assumes the media maps linearly across a flat card. The card is a domed plane under perspective, so it does not, and the guard sealed with the instrument correctly **refused to answer** on most cards rather than emitting a confident wrong number — `flatBaselineVerified: false`. The guard worked exactly as designed; what it protected against was the model, not the candidate. Note also an asymmetry worth disclosing: the Target has no media-only render, so its baseline could not be checked at all and its readings pass the guard by default.

## §十 — pipeline and performance

Scene-colour pass: 52 draw calls in the control, 0 in the candidate. Final pass 17 vs 17. CPU frame time p50 0.8 vs 0.7 ms, p99 1.4 vs 1 ms. Ready in 361 vs 305 ms. 7/7 checks pass.

## §十二 — frozen regressions

**18/18** suites pass at the O5 build. The shipped default is the control lane, so these exercise the accepted body; that it is unmoved is the point.

One of them earned its keep this round. **O2 Media-only Controls** failed on the first run: the candidate's QA media plane sat at a different depth from the control's, so the two lanes projected the same media at slightly different sizes and their media-only captures were not comparable. That plane is hidden in the candidate's Beauty path, so no optical measurement reads it — but the true-silhouette derivation and the edge-compression baseline check both compare lanes through it. The plane was given the control's depth and ONLY the media-only and glass-only layers were re-captured; every Beauty capture on disk is the one the gate was scored on, so items 1–6 and 9–14 are unchanged by construction. Control identity was re-run after the change and is still exactly zero.

## Method notes

- Source contract: 57 sites, 0 failed, every offset seek-verified against the live bundle. Absences use two spans — the 3747-byte material factory for output claims, the 9886-byte card component for geometry claims, because the factory contains no geometry code and a claim made there would be vacuous.
- Instruments: 61/61 tests pass, each with a negative partner, sealed before any candidate pixel.
- Target repeatability was captured BEFORE any candidate frame, 3 runs per viewport; every window is max(2 x repeatability, floor).
- Architecture: 13 decisions, each marked transcription or a named deviation. Our frozen layout reproduces the Target's L6 exactly at all five viewports; the cover fit matches its centred formula for two clips and deliberately does not for the third, which carries a frozen product crop.
- **Known deviation, disclosed rather than fixed:** our O2 `envSampleCeiling` clamps the environment sample at 16 and the Target has no such clamp. An earlier draft justified it as unable to bind by comparing 16 to envIntensity x envMaxMix = 0.521 — a radiance bound against a dimensionless mix weight, which is meaningless. Measured on the asset: 0.98% of texels exceed the ceiling and the brightest is 3568, 223x it. The clamp binds. The render was NOT changed after the gate pixels existed; removing it now would be the post-capture adjustment §十一 forbids.
- Console and page errors during scoring capture: 0.
- Target pixels and video appear only in the private package.

Captured at `b11051a541940c2199a4afb857f45980f449e5b6`.
