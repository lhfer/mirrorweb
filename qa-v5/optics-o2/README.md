# O2 -- System B: White Studio Reflection / Fresnel-capped LERP

**Verdict: READY FOR O2 OPTICS PRODUCT REVIEW.**
**Selected candidate: A+B** (System A (o1-spectral dispersion) stays in the product ONLY through this O2 interaction gate; config default dispersionLaw remains o1-spectral).

Captured at `e913aa6`. Base lanes: V1 accepted `5159cf8` (B-only base / Before), O1 experimental `62d3ac4` (A+B base). Media: the deterministic shared-media harness (all-PASS, see shared-media-harness.json) -- every number below is a same-media, mostly same-page number; cross-page Target numbers are secondary by design.

## Gate verdicts

| # | check | B-only | A+B |
|---|-------|--------|-----|
| F1 | white lever materially non-zero | PASS | PASS |
| F2 | no grayscale/achromatic ringing added | PASS | PASS |
| F3 | luminance dependence moves toward Target | PASS | PASS |
| F4 | saturated edge chroma falls >= 8.0 (2x O1 lever) | PASS | PASS |
| F5 | interior unchanged within law bound | fired (registered coding) -- adjudicated instrument artifact | fired (registered coding) -- adjudicated instrument artifact |
| F6 | desktop/mobile same direction | PASS | PASS |
| F7 | media-only byte-identical | PASS | PASS |
| F10 | gutter not invaded | fired (registered coding) -- adjudicated instrument artifact | fired (registered coding) -- adjudicated instrument artifact |
| F11 | pointer reflection path stable | PASS | PASS |
| F8 | lane integrity (structural, blocking) | PASS (exact 0) | same gate |
| F9 | frozen regressions | PASS | same build |
| F12 | visibly obvious full-frame improvement | PASS | PASS |

### Adjudicated registered codings (nothing edited, both codings recorded)

Three registered codings fired on instrument degeneracies, not optics changes. Each gate JSON carries BOTH codings and the primary evidence; none of the registered thresholds was edited after capture.

* **F5** -- the relative-change coding divides by a near-zero baseline on achromatic media (Before interior saturation 0.0000). Absolute interior gains: max 0.0104 saturation / 0.14 of 255 chroma, at or below the Target's OWN achromatic interior anchor (0.0025). Interior luminance -- the measurand with a meaningful baseline everywhere -- moves <= 5% on every asset (registered ceiling 12%).
* **F10** -- the O0 gutter mask counts partially-visible neighbour CARDS as gutter; on the bright shared media the Before "gutter" is already 0.42. With every drawn card masked, between-card gutter ink is UNCHANGED on bw-split (5 decimals) and DECREASES on rgb-bars.
* **F11** -- the full-dark-half centroid is dominated by the static white card TITLE (centroid lands in the title band). Excluding the label band leaves the glass highlight: the Target path is monotonic decreasing and both candidates are monotonic decreasing in the SAME direction, max adjacent jump ~0.28 < 0.4 card widths.
* **F8** -- the registered runtime-neutralised proof carries a deterministic 1px/1-255-step compiler (FMA) artifact on desktop; the STRUCTURAL proof (?systemB=off, shader byte-identical to pre-O2) is EXACT ZERO against both base commits, cross-origin and cross-build, both viewports. See lane-equivalence.json for the full record and the scope boundary (media-only and A/B gates stay exact-zero).

## Selection (pre-registered rule)

Retain A only if A+B: improves fringe width / fringe chroma versus B-only; does not reduce white reflection ratio; does not worsen Bright/Dark sign stability; does not worsen Mobile; does not alter Media-only; does not create colour ringing on grayscale media. Otherwise choose B-only and remove O1 System A from the accepted product path.

A+B improves fringeRB AND fringe width on all three saturated assets, has HIGHER white ratio on bw-split and grayscale, lower bright-side chroma, equal-or-better mobile movement, byte-identical media-only, and LESS grayscale ringing (3.56 vs 8.12 against the Before 11.22). Winner: **A+B** -- all six criteria strict. Numbers: candidate-selection.json.

## Headline same-media numbers (desktop, A+B fullB vs Before anchor vs Target anchor)

| measurand | Before | A+B candidate | Target |
|---|---|---|---|
| bw-split dark-side edge luma | 28.5 | 95.1 | 48.1 |
| bw-split bright-side edge chroma | 26.05 | 3.22 | 1.41 |
| bw-split edge chroma | 9.73 | 3.68 | 3.58 |
| grayscale-step edge chroma | 11.22 | 3.56 | 3.33 |
| bw-split white reflection ratio | 0.3925 | 0.4364 | 0.4188 |
| saturated edge-chroma mean drop | -- | 18.03 (>= 8.0 required) | -- |

Observed, not gated: the reflection band on black media is both wider (15.3px vs 3.3px mean) and stronger (dark-side edge luma 95.1 vs the Target's 48.1; dark/bright ratio 0.5006 vs 0.248) than the Target's -- the geometry bevel spreads the white band more than the Target's analytic bevel, and every registered check only bounded the DIRECTION and minimum magnitude, so this overshoot passes the gates but is recorded for product review. The hf-checker anomaly from the pre-registration remains observed-not-gated.

### Implementation correction (pre-scoring, recorded)

During smoke testing -- before any scored capture -- the full System B output was visibly wrong (uniform interior wash). Root cause, proven by compiled-shader dumps: three's TSL emits the shared `normalView` varying unpack only into the FIRST debug-select branch that references it, so the beauty path reads the shared normal globals as zeros -- a latent state in which V1's `facing` term has always sat (V1 pixels are frozen and untouched; the V1 body never consumed `facing`). System B therefore reads the interpolated geometry normal through its own varying and mirrors the Target's law in view space, rotating to world with three's own reflectVector idiom (rotations preserve dot products and commute with reflect -- the math equals the Target's world-space form). No registered parameter changed; the correction restored the registered interior law (mix bound 0.0868 at facing=1) that the broken state violated.

## F12 -- recorded full-frame judgment

PASS -- stated plainly: the Before frame reads as a dark, saturated coloured frame (hard red/cyan fringe lines around every card, flat dark edges, black media dark-over-dark); the candidate frame reads as white studio glass (soft white bevel bands hugging the card edges, black media stays black, no visible colour fringing at full-frame scale). The difference is unmistakable without zooming; the candidate is visually much closer to the Target's same-media frame. Judged on the recorded full frames listed above, both lanes; the A+B lane additionally removes the residual tap fringes B-only keeps on saturated media.

## Files

Public (this tree): README.md, MANIFEST.json, shared-media-harness.json, o2-selected-system.json, target-system-b-source.json, b-only-gate.json, a-plus-b-gate.json, candidate-selection.json, same-page-floor.json, bright-dark.json, grayscale-ringing.json, pointer-reflection-path.json, lane-equivalence.json, regressions.json.
Private: `qa-v5/private/o2-optics-review.zip` -- Target/Before/B-only/A+B stills, Edge + Reflection ROI, floors, media-only, H.264 720p gesture clips under the same deterministic media, per-file SHA-256, capturedAtHead + reviewHead.
