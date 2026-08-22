# O4 — Frozen Body Floor Attribution

**Final state: O4 SELECTED BODY CANDIDATE FAILED ABSOLUTE GATE**

Absolute gate: **FAIL** — 8 of 12 items passed, 4 failed.

The shipped default stays `bodyFloorMode=current`. This brief registers no automatic flip and its final states do not include one; the product review owns that decision.

## O4A — the compiled body-path audit

**AFFECTED.** YES. The geometry normal is unpacked exactly once, inside the `normals` debug branch. Every other branch -- the shipped Beauty path included -- aliases a zero-initialised var<private>, so the Beauty refraction, the projected-normal offset and the facing term all consume a ZERO normal.

The geometry normal is unpacked exactly once, inside the `normals` debug branch. Fourteen sites alias it; thirteen sit in branches with no unpack, including all three in the Beauty branch. Two debug views read it in different branches of one program, same frame, same geometry: `normals` varies (range 38/66/3), `fresnel` is **exactly constant** (0/0/0). The controls that read unshared vertex attributes vary correctly.

This explains GATE-005 rather than reproducing it: `projectedNormalOffset` — documented as the only term tracking the surface normal — is identically zero.

## The factorial

The specified 2^5 over A–E, replicated at both states of a sixth axis N (the normal repair O4A made necessary), because §七.E cannot be judged without N measured on the same basis. 260 desktop captures over four media; OFAT plus pairwise at both mobile viewports.

| factor | subsystem | explains | interaction ratio | eligible |
|---|---|---|---|---|
| A | TARGET OWN-MEDIA / PER-IOR REFRACTION | +3% | 1.2234 | no |
| B | RESTORE TARGET LEVEL-0 / NO-BLUR SAMPLING | +4% | 2.6353 | no |
| C | REMOVE LOCAL ADAPTIVE BODY SHAPING | +141% | 0.1292 | **yes** |
| D | dispersion -- §七 lists NO product candidate for it | +3% | 3.3373 | no |
| E | RESTORE TARGET BODY OUTPUT TRANSFORM | -7% | 1.3999 | no |
| N | SOURCE-EXACT REFRACTION NORMAL REPAIR | +9% | 1.8801 | no |

Selected: **REMOVE LOCAL ADAPTIVE BODY SHAPING** — the only eligible factor.

## The twelve gate items

| # | Item | Result |
|---|---|---|
| 1 | body floor reduced by >= 40% | **PASS** |
| 2 | candidate enters the Target window (two-sided) | **FAIL** |
| 3 | dark-side body luma moves toward the Target | **FAIL** |
| 4 | grayscale does not add colour | **PASS** |
| 5 | no increase in broad coloured rim | **FAIL** |
| 6 | HF checker preserves or improves local high-frequency structure | **PASS** |
| 7 | interior media within sealed tolerance | **PASS** |
| 8 | media-only exact zero | **PASS** |
| 9 | true gutter unchanged | **FAIL** |
| 10 | no temporal pop | **PASS** |
| 11 | control lane exact zero vs the accepted baseline | **PASS** |
| 12 | all frozen suites PASS | **PASS** |

## What failed, and what the numbers mean

**Items 2 and 3 — the candidate undershoots.** Removing the local adaptive body shaping takes the body floor *below* the Target's whole band at every viewport: 9.7 → 1.7 px desktop against a Target of 3.3, 6.0 → 0.0 against 1.5, 6.0 → 0.0 against 2.0. Item 2 is a two-sided window and was sealed as one, so undershooting is scored as a miss.

The comparison §九 mandates is asymmetric, and that is recorded rather than argued around: our System-B-OFF floor against the Target's full render, which includes the Target's own rim and environment. The shipped-state diagnostic is what makes it legible:

| Viewport | control body floor | candidate body floor | control shipped | candidate shipped | Target |
|---|---|---|---|---|---|
| 1440x900 | 9.7 px | 1.7 px | 15.3 px | 13.0 px | 3.3 px |
| 390x844 | 6.0 px | 0.0 px | 8.0 px | 7.0 px | 1.5 px |
| 844x390 | 6.0 px | 0.0 px | 8.0 px | 7.0 px | 2.0 px |

Removing the body shaping takes the floor to essentially nothing, and the shipped band still barely moves — 15.3 → 13.0 px desktop — because with the body dark the O2 reflection support paints the band on its own. **O3 showed the support field is not the binding constraint given this body. O4 shows the body is not the binding constraint given this support.** Both are constraints; neither round was permitted to change the other, and neither could pass alone.

**Item 9 — true gutter.** Scored FAIL at a sealed threshold of exactly zero. Every differing pixel lies within **one** pixel of the true silhouette, at a maximum of 2 and 5 levels; beyond 1 px the two lanes are identical. They are the antialiased boundary of a silhouette derived from the control lane, not light in the gutter. The threshold and instrument are untouched and the item stands as scored. The private package's `cross-section/silhouette-overlay-*.png` plots this directly: 25 of 25 differing pixels on bw-split, 58 of 58 differing pixels on rgb-bars sit on the boundary ring, none beyond it.

**Item 5 — coloured rim.** `fringeRB` rises 79.4 → 80.5 on rgb-bars and 92.3 → 94.4 on cool-blue against a 0.5 envelope; warm-skin passes. The rim does not get *broader* — `fringeWidthPxMean` is flat on two assets and falls 17.8 → 14.6 on the third — it gets marginally more intense, because removing the internal shadow leaves the edge brighter on saturated media.

**Items 6 and 7 pass for a structural reason worth stating.** The two lanes are bit-identical in the card interior. Every adaptive term is gated on `blurZone` and `curvature`, both zero on the clear centre face, so the subsystem the candidate removes never acted there.

## What held

- Item 11: the control lane is **exactly zero** differing pixels against an e913aa6 worktree build at System B OFF, on every scored case. Every comparison above is therefore against the accepted O2 body and not against something else.
- Item 1: the floor falls 82% desktop and 100% at both mobile viewports.
- Item 8: media-only is bit-identical.
- Item 10: no pop on any recorded sequence; worst adjacent-frame change 2.2% against a 40% ceiling.
- The all-off diagnostic program is **byte-identical** to the pre-O4 program at high, medium and low quality, so the factor machinery is provably inert when off.

## §十 — the support re-test was not run

§十 authorises it only after the body candidate passes its own gate. It did not. Running it anyway would be the search for a combination that passes which §七 and §八 exist to prevent. See `support-retest.json`.

## Method notes

- Instruments sealed at `968e7ddfaa67`, gate codings at `66684dd0a48a`, both before the pixels they judge. 32/32 instrument tests pass, each with a negative partner.
- The Target body source contract anchors 17 sites, 0 failed; absences are established by an end-to-end completeness span (bytes 1975111–1976472) rather than pretended byte offsets.
- Band width is only a reflection-band measurement where the media behind the card's dark-side edge is dark. That holds on bw-split (luma 4.5) and not on the other three (26–58), so the excess test uses bw-split and cross-media sign stability uses the continuous measurands sealed before capture.
- The private package's side-band cross-sections are measured independently of the gate scorer and reproduce it exactly — control 9.7 / candidate 1.7 px at System B OFF, 15.3 / 13.0 shipped.
- The Target frames in the private package are the O3 captures reused verbatim, because the 3.3 / 1.5 / 2.0 px anchors this gate is scored against are those captures' own numbers. Re-measured there under the O4 sealed instrument, all three reproduce.
- Console and page errors during gate capture: 0.
- All sixteen §十一 frozen suites PASS at the O4 build.
- Target pixels and video appear only in the private package.

Captured at `df467ed4ae44b0318731fb51db31ff708f9e7a1e`.
