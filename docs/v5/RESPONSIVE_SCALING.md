# V5 Stage F2 — Responsive Composition Scaling

Branch `rebuild/liquid-glass-v5-foundation`. Page under review: `/?optics=v4`.
Builds on the accepted [V5 Foundation baseline](BASELINE.md); the world geometry
is held fixed and only the scale it is viewed at changes.

## The problem F2 was given

The accepted baseline held world size constant: one world unit was one CSS pixel
at every viewport. The Target does not. At 1100×720 our card was 540 px where
the Target's was ~407.

## How the law was measured

25 viewports captured from the live Target in one session
(`scripts/v5/capture-target-viewports.mjs`, output git-ignored under
`artifacts/v5-target/`), then `scripts/v5/fit-scale.py` recovers the composition
scale S at each one — screen pixels per world unit at z = 0 — holding the
accepted world geometry fixed so S cannot absorb a geometry error.

Before mixing anything: a **drift check**. The live 1440×900 frame captured today
reproduces the frozen 2026-08-18 capture's gutter bands and card extents
*exactly* — hbands (29,40) (441,458) (853,871), cards 183..708, 449..990. Frozen
and fresh samples are the same site.

## The law

```
landscape (width >= height)   S = width / 1440
portrait  (width <  height)   S = 1.8975 * width / 1440
```

**It is width, not height or area.** At a fixed 1440 width the Target returns
S = 1.0026 at 700 tall and 0.9794 at 1080 tall — the same S, within noise.

**The split is orientation, not a width breakpoint.** A 700×900 portrait window
uses the portrait law; a 667×375 landscape window uses the landscape one, even
though the portrait window is wider. No width breakpoint can produce that. The
site's own `lg` breakpoint at 1024 is *not* where the behaviour changes: 960×720
and 1000×700 both sit on the landscape law.

**There is no separate mobile-landscape model.** 844×390 fits the landscape law
at S = 0.5880 against a predicted 0.5861 (rms 0.25 px), and 926×428 at 0.6459
against 0.6431. Landscape is one continuous model from 844 to 2560 wide. The
brief asked for three models; the data supports two.

**It is not a user-agent branch.** 844×390 captured with and without a mobile UA
and touch produces an identical composition — identical bands, identical
gutters. The law is pure geometry, which is what makes it reproducible locally.

**It is DPR-invariant.** 390×844 at DPR 1 and DPR 3 give the same CSS-normalised
layout to within 0.8 px.

**It re-derives on resize**, not only at load: the Target's live-resize frame at
1100×720 and a fresh load at 1100×720 agree on scale. The local implementation
therefore lives in `RendererController.resize()`.

## The mechanism: focal length, not camera distance

A scale S can be realised by moving the camera (camZ = 1000/S) or by scaling the
focal length (f = 1000·S). They agree to first order and differ in how fast an
outer card shrinks. The Target's own frames decide it:

| viewport | S | gutter centres, divided by S |
| --- | --- | --- |
| 1440×900 | 1.0000 | −415.5, −0.5, +412.0 |
| 1100×720 | 0.7639 | −415.6, −0.7, +411.7 |
| 960×720 | 0.6667 | −415.5, −0.7, +411.7 |

Identical to 0.1 px across a 1.5× range: the Target's wide frames are a **pure
uniform rescale**. Moving the camera is not — it changes how much of the camera
distance the grid's depth occupies, so the pattern would not normalise. Focal
scaling is what ships (`RESPONSIVE.mechanism`), and it has the added property of
leaving the optics untouched, which this stage requires.

## Portrait rest offset

The Target's portrait composition carries the **opposite brick parity** to its
landscape one: a row with a centre gutter in landscape has a centre card in
portrait. `RESPONSIVE.restOffset.portrait.x = 280.57` world units — exactly half
a cell — is what swaps it. Landscape needs no offset at all.

## Void colour, calibrated by round trip

The Target's gutter median over 161k void pixels is (0, 3, 18). Setting that
literally renders as pure black: the clear colour goes through the tone-mapped,
sRGB-encoded output path, which crushes anything that dark. Measured transfer:

| in | out |
| --- | --- |
| 0x000208 (the old value) | (0, 0, 0) |
| 0x000c1a | (0, 1, 8) |
| 0x001424 | (0, 5, 17) |
| **0x001025** | **(0, 3, 18)** |
| 0x001b35 | (0, 10, 35) |
| 0x00225a | (0, 16, 84) |

`CLEAR_COLOR = 0x001025`. Side effect worth having: the layout detector now
auto-selects its NAVY preset on **both** sides, so Target and local frames are
measured by one instrument with one calibration instead of a black/navy fork.

The Target's void is a gradient (B ranges 13–23 across the frame, down to ~6 at
the edges); a constant clear colour matches its median, not its gradient. The
gradient is an environment concern and out of scope here.

## Gate

`scripts/v5/f2-gate.py`, six viewports, structure derived from each frame's own
measurement rather than from fixed 1440-space probes.

| viewport | verdict | band centres | gutter centres | card size |
| --- | --- | --- | --- | --- |
| 1100×720 | PASS | 0.35% | 0.09% | 0.48% |
| 1366×768 | PASS | 0.07% | 0.00% | — |
| 1440×900 | PASS | 0.39% | 0.07% | 0.55% |
| 1920×1080 | PASS | 0.05% | 0.00% | — |
| 390×844 | **FAIL** | 0.12% | **0.00%** | — |
| 844×390 | PASS | 0.13% | 0.00% | — |

390×844 fails one check only — `missing bands 2` — while every positional check
on it passes, its gutter centres landing at 0.00%. The cause is **not** the
scaling law; see P0 below.

The accepted F0 baseline is unaffected: `scripts/v5/f0-gate.py` still returns
20/20 PASS at 1440×900 with the same numbers.

## Cross-validation

Leave-one-out over 11 landscape viewports from 844 to 2560 wide: the gain
re-fitted without a viewport predicts that viewport's own measured scale to a
**worst error of 0.52%** (`qa-v5/f2/cross-validation.json`). The portrait gain
was fitted on 414×896, 430×932 and 360×800 and the gated 390×844 was held out of
the fit entirely.

## P0 / P1 / P2

**P0 — the Target's grid also curves vertically, and the baseline does not model
it.** Only tall viewports expose it, which is why F0 at 1440×900 could not see
it. Target row heights against distance from the viewport centre:

| viewport | inner rows | outer rows | falloff |
| --- | --- | --- | --- |
| 390×844 | 207 px at ±108 | 185 px at ±313 | −10.6% |
| 414×896 | 219 px at ±115 | 196 px at ±331 | −10.4% |
| 430×932 | 227 px at ±119 | 197 px at ±341 | −13.2% |

Those outer rows are fully inside the frame, so they are genuinely shorter, not
clipped. Our rows are all one size, so at 390×844 we show three row bands where
the Target shows five. A first estimate puts the vertical radius near 1570 world
units against the horizontal −4059. Fixing it means changing `GRID`, which is
the accepted F0 baseline and outside every edit F2 was permitted — so it is
recorded, not fixed. **It should be the next stage.**

**P1 — drag feel now varies with viewport.** `dragGain` maps input pixels to
world units, and world-to-screen is no longer 1:1 outside 1440×900, so the same
gesture moves the composition further at 1920 than at 1100. Motion is frozen
this stage; the fix belongs with the dragGain work already queued.

**P1 — glass rim still eats the gutter on yawed cards** (11 px rendered against
the Target's 19 px at 1440×900). Unchanged from F0, optics out of scope.

**P2 — the portrait gain is a constant fitted over aspects 0.39–0.56.** It holds
to ≤1.4% there and misses by 3.2% at 700×900 (aspect 0.78), a near-square window
no device produces. If P0 is fixed the portrait residual should be re-fitted,
because part of that 1.4% may be the vertical curvature leaking in.

**P2 — cyan/magenta rim fringing, typography `9.2cqw` vs 12cqw, `TILE.radius`
58 vs ~61.5.** Unchanged from F0.

**P2 — `npm run v4:source` still fails**, four checks from the baseline and three
from V5. Not re-baselined; that remains the product owner's call.

## Typography?

**Not yet.** P0 is layout geometry and it is the largest remaining fidelity
error in the build — at 390×844 the Target shows five row bands and we show
three. Typography sits on top of card geometry that is still going to move.
