# O3 — Target Analytic Bevel Reflection Support

**Final state: O3 ANALYTIC BEVEL REFLECTION FAILED ABSOLUTE GATE**

Absolute gate: **FAIL** — 11 of 20 items passed, 9 failed. Thresholds were sealed at `b4dbb1629a69` before any candidate pixel was captured and were not touched afterwards.

The shipped default therefore stays `reflectionSupport=geometry` — the accepted O2 System B. That is the sealed default-flip rule's negative branch executing, not a separate decision.

## What O3 changed

O2 adopted the Target's reflection **law** and product review froze it. What O2 did not have was the **field** that law is evaluated on: it stood our baked geometry shoulder normal in for the Target's analytic bevel normal, and the `strongLensRim` vertex attribute in for the Target's rounded-rect SDF rim.

O3 transcribes that field from the byte-anchored source contract (`target-bevel-reflection-source.json`, 29 sites, 0 failed) into `src/materials/TargetBevelFieldV4.ts`, and swaps exactly two inputs to the frozen System B block:

| | O2 control (`geometry`) | O3 candidate (`target-sdf`) |
|---|---|---|
| Fresnel / env reflect normal | `v_o2NormalView` geometry normal | analytic bevel normal |
| White rim mask | `strongLensRim` attribute (≈31.7 px) | `smoothstep(-rimWidth, 0, sdf) × 0.11` (8.3 px) |

Both lanes are the same commit, the same page and the same frozen media, selected by a build-time JS branch. No parameter was tuned and no threshold was moved.

## The twenty items

| # | Item | Result | Measured |
|---|---|---|---|
| 1 | O2 control pixel-identical to e913aa6 | **PASS** | 5 cases, all 0 differing px |
| 2 | Analytic source contract PASS | **PASS** | 29 byte-anchored sites, 0 failed; live bundle matches |
| 3 | bw-split reflection band width vs Target | **FAIL** | candidate 8.7 px vs Target 3.3 px (Δ 5.4, ceiling 1.5) |
| 4 | candidate band materially narrower than O2's 15.3 px | **FAIL** | candidate 8.7 px vs control 15.3 px — ratio ceiling 7.65 px, drop 6.6 px |
| 5 | bw-split dark-side edge luma vs Target | **FAIL** | candidate 77.6 vs Target 48.1 (Δ 29.5, ceiling 10.0) |
| 6 | white reflection ratio vs Target | **PASS** | candidate 0.4314 vs Target 0.4188 (Δ 0.0126) |
| 7 | dark / bright ratio closer to Target | **PASS** | candidate distance 0.1904 < control 0.2522 |
| 8 | grayscale edge chroma not worse than O2 | **FAIL** | candidate 4.16 vs control 3.56 (ceiling 4.06) |
| 9 | saturated edge chroma not worse than O2 A+B | **FAIL** | rgb-bars 94.3/91.2, cool-blue 94.92/90.15, warm-skin 44.42/42.74 |
| 10 | no new coloured rim on RGB / cool / warm | **FAIL** | rgb-bars fringeRB 79.06 vs 76.16, cool-blue fringeRB 94.92 vs 89.65, warm-skin fringeRB 44.39 vs 42.22 |
| 11 | interior media not globally brightened or desaturated | **FAIL** | hf-checker |
| 12 | media-only bit-identical | **PASS** | 4 pairs, all 0 differing px |
| 13 | gutter invasion not increased | **FAIL** | bw-split@1440x900 Δ0.02037, rgb-bars@1440x900 Δ0.02386, bw-split@390x844 Δ0.00424, rgb-bars@390x844 Δ0.00424 |
| 14 | pointer reflection path, glass-only metric | **PASS** | branch tracking-reference, fired=False |
| 15 | desktop / portrait / landscape same direction | **PASS** | 1440x900 band -6.6, 390x844 band -5.0, 844x390 band -5.0 |
| 16 | no rim / reflection pop during drag, flick, touch | **PASS** | 15 clips measured |
| 17 | v_o2NormalView control regression | **PASS** | gate 1 zero=True, control declares v_o2NormalView=True |
| 18 | compiled shader proof | **PASS** | all program checks true |
| 19 | all frozen suites PASS | **PASS** | 16/16 suites PASS |
| 20 | full frame no longer reads as a wide white plastic frame | **FAIL** | judged on the full frames — see below |

## Why it failed — the frozen base already exceeds the Target's whole band

This is the finding that matters for what comes next, and it is measured, not argued.

Both lanes were captured at the registered floor states. At `envMixScale=0, rimScale=0` System B is entirely off and the two lanes are **identical** — proven, not assumed. Whatever band survives there is painted by the frozen refraction / dispersion / adaptive-contrast composition, before any reflection exists at all.

| Viewport | Frozen base (System B off) | O2 control | O3 candidate | Target |
|---|---|---|---|---|
| 1440x900 | **9.7 px** | 15.3 px | 8.7 px | 3.3 px |
| 390x844 | **6.0 px** | 8.0 px | 3.0 px | 1.5 px |
| 844x390 | **6.0 px** | 8.0 px | 3.0 px | 2.0 px |

At every viewport the frozen base **alone** paints a wider band than the Target's entire measured band. The reflection support is not the binding constraint: no change to the support field — the Target's own included — can take the band below a floor that exists with the reflection switched off. Gate 3 needs the candidate within 1.5 px of 3.3 px; the base is 9.7 px.

The residual lives in `adaptiveEdgeLift` / `contrastShaped` and the refraction edge treatment — code §一 forbids O3 to touch. That is the boundary this round establishes, and it is the only thing an O4 decision actually needs from here.

It is worth being explicit about the loophole this does not leave open. A support field that saturated the fresnel to the 0.27 envMaxMix cap everywhere could in principle pull the candidate's 77.6 dark-side luma down toward the gate-5 threshold. But that field would not be the Target's field, and the Target's field is exactly what O3 is pinned to. The question was never "can some support field pass"; it is "does the Target's own field pass on our frozen base", and the decomposition answers it.

## What the candidate does achieve

Recorded because a failed gate is not the same as a failed mechanism.

- The rim swap works exactly as the source says it should. Isolating the rim (env-off, rim-on minus env-off, rim-off) the candidate's rim peaks at 37 luma 2 px inward, is down to 5 by 8 px and is 0 by 10 px — an 8.3 px band, as the source specifies. The control's is still lifting 39 luma at 16 px and 32 at 18 px.
- Band width falls 15.3 → 8.7 px, dark-side luma 95.1 → 77.6, dark/bright ratio 0.5006 → 0.4388 — every one of them toward the Target. Items 6 and 7 pass on that movement.
- Item 15 is the same direction at all three viewports.
- Item 16: no rim or reflection pop on any recorded sequence; the worst adjacent-frame change is 2.1% against a 40% ceiling, at or below the control on every clip.
- Items 1, 12, 17, 18: the control lane is still bit-for-bit the e913aa6 O2 program, and the compiled shaders prove each lane consumes its own support with no leakage.

## Failures that need reading carefully

**Item 13 (gutter invasion).** Scored FAIL at +0.020 against a 0.006 ceiling. The instrument and threshold are untouched and the item stands as scored. What the number is made of: outside the **true** glass silhouette — every pixel the glass layer touches, taken from the media-only captures — the two lanes are bit-identical (max channel difference 0.0). The candidate puts no light into real gutter. The whole delta lies between the flat layout quad F10 masks and the larger silhouette the bulged lens actually projects, which is where the candidate concentrates its narrower rim.

**Items 8, 9, 10 (edge chroma).** Scored FAIL. The floor states attribute it: with System B off the lanes are identical; at rim-only the **control** reads lower chroma, because its over-wide white rim covers the edge band with neutral white and dilutes the mean; at env-only the candidate reads higher, because the analytic normal tilts to the source's 60° slope clamp and swings the reflection vector further into a coloured studio HDR. So the rise is partly a real chroma increase and partly the removal of a white rim that had been masking the frozen base's own colour — corroborated by `fringeWidthPxMean` falling on every saturated asset in item 10.

**Item 11 (interior).** Seven of eight assets do not fire. `hf-checker` has baseline interior saturation 0.0104, just above the 0.01 floor, so the sealed rule took the relative branch and a 33.7% relative change fired. The branch was fixed by the baseline before any candidate pixel existed and is not revisited here.

## §九.20 — the judged full frames

Registered failure text: *the candidate full frame still reads as a wide white plastic frame around the card, or its corners still read as thick plastic, when compared with the Target's same-media frame without zooming*

Frames judged at 100%, full frame, no ROI crop: `artifacts/optics-o3/measure/target-rest-bw-split-1440x900.png`, `artifacts/optics-o3/measure/control-full-bw-split-1440x900.png`, `artifacts/optics-o3/measure/candidate-full-bw-split-1440x900.png`

FAIL -- stated plainly. The candidate is a clear improvement on the O2 control: the broad milky ramp the control sweeps inward across the black half is largely gone, the black media reads black much closer to the edge, and the top band is visibly thinner. But against the Target's same-media frame it does not clear the registered standard. The Target's edge is a razor-thin bright lip -- a crisp specular line with black immediately inside it (see 'Field Notes' and 'Glass House' in the Target frame). The candidate's left edge is still a soft white band of order fifteen to twenty pixels (see 'Night Index' and 'Glass House' in the candidate frame), and the outer rollover still carries a fat rounded shoulder, so the corners still read as thick plastic. Judged without zooming, on the three full frames named above.

## Frozen regressions (§十一)

- PASS — V1 Render Culling Gate
- PASS — V0 Label Culling Gate
- PASS — Source Contract
- PASS — Layout Source
- PASS — Typography
- PASS — Motion Freeze Smoke
- PASS — Release History Smoke
- PASS — Card / Label Motion
- PASS — Wrap = 0
- PASS — Touch / Pointer Cancel
- PASS — Console / Page Errors = 0
- PASS — O2 Shared-media Harness
- PASS — O2 Media-only Controls
- PASS — A+B Dispersion Selection
- PASS — TypeScript
- PASS — Vite Build

## Method notes

- Every threshold comes from `o3-preregistration.json`, sealed at `b4dbb1629a69`. Nothing was recoded after capture.
- The F5 / F10 / F11 corrections are imported from `scripts/v5/o3_instruments.py` — the same module `instrument-tests.json` certifies (36 tests, including a non-monotonic input that genuinely fires) and `instrument-dryrun.json` exercised on the O2 captures before sealing.
- Target repeatability was measured before any candidate code existed; all repeats were byte-identical under the deterministic harness, so every §八 threshold binds at its floor rather than at a zero spread.
- Target pixels and video appear only in the private package.

Captured at `669046eb16d21fbcc73543b33b2500e2d425c871`.
