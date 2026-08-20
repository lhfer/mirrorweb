# V5 Stage F2.6 — final composition closure

Branch `rebuild/liquid-glass-v5-foundation`. Page `/?optics=v4`.
v1 stays reachable and unchanged at `?composition=v1`.

## 1. The portrait law the code runs is now the law that was validated

F2.5 shipped `gain = 1.9468 - 0.31*(aspect-0.5)` while quoting a +0.472%
hold-out that belonged to `1.87715 + 0.12204*(aspect-0.5)`. Different models,
opposite slopes. Measured properly, the shipped law misses the held-out 390x844
scale by **+5.09%**.

Three runnable candidates, all gated, 390x844 held out of both fits:

| | portrait gain | vertical | scale hold-out | gate |
| --- | --- | --- | --- | --- |
| P0 | 1.9468, -0.31 | as F2.5 | **+5.088%** | 5/6 |
| **P1** | **1.87715, +0.12204** | **as F2.5** | **+0.472%** | **5/6** |
| P2 | 1.87715, +0.12204 | refitted | +0.472% | 4/6 |

**P1 ships.** P2's refit buys a better analytic fit but regresses the 1440x900
anchor on the void check, and the brief asked for that anchor to be protected.
The parameters in the code are character-for-character the P1 entry in
`qa-v5/f26/portrait-crossval.json`:

```
radiusY -4707.6   cellH 419.95   restY0 -200.99
portraitGainBase 1.87715   portraitGainAspectSlope 0.12204
```

All three remain selectable at `?portraitLaw=p0|p1|p2`.

## 2. The fitter measures a card that exists

`row_geometry()` sampled `i = -0.5` on odd rows -- not a card, and under the
half-cell phase it sat where the Target has a gutter. It now enumerates integer
`i` and takes the real card nearest the viewport centre, preferring an unclipped
one.

Verified against the engine corner by corner, at both rest phases, both vertical
modes and all six gated viewports: **0.0 px** worst corner error, law
error **0.0**. Tolerance recorded at 0.05 px; the measurement is exactly
zero. Getting there required substituting the engine's TILE into the model --
the fitter carries the silhouette size, `getCardQuads` returns the slab, and the
0.18% difference showed up as a clean 0.07%-of-viewport error at every corner.

## 3. Landscape phase, judged against the runtime law

F2.5's 4/9 figure used the offline fitter's scale. The runtime uses
`S = width/1440` unconditionally, so that number was never the running code's.
Parity is now classified **directly** from row structure, never from a scale
fit -- a fit that fails says nothing about parity.

The scale switch at 0.674 scores **23/39** against the runtime law, so it is
withdrawn. A CSS-width interval cannot replace it either: the same width takes
different phases at different heights (900x420 against 900x899, 1440x700 against
1440x900), so the widths interleave and no interval separates them.

What does separate them is **aspect**:

```
restOffsetX = (portrait || height < 0.5525 * width) ? cellW/2 : 0
```

**35/39** across the sweep. The threshold sits on a plateau from 0.545 to
0.56; 0.5525 is its midpoint. Misses recorded, not tuned away:
667x375, 700x700, 780x470, 1440x1080.

**Known fragility:** 16:9 is 0.5625, about 0.01 above the threshold. The most
common desktop aspect is close to flipping phase. Widening the sweep around 16:9
is the first thing to do if this misbehaves.

## 4. Multi-frame Target consensus

A dark video frame can read as void. Five frames per viewport, a pixel counted
as void only if at least 80% of them agree. It removed up to 9,636 spurious void
pixels (760x470) and cut phantom gutters -- 1100x720's bottom row from 17 to 11,
844x390's top row from 5 to 3 -- while every real row band survived unchanged.
7 viewports re-measured.

## 5. Pool recycling pitch

v2 placed rows on the composition's `cellH` while the pool still derived its
origin row from `GRID.cellH`. Near the origin they agree, so nothing showed; far
out they diverge by a whole row and a slot gets the wrong index. Both now read
`effectiveCellH()`.

Long-scroll test at 0, +/-0.49, +/-0.51, +/-10, +/-50, +/-100 cells:
**PASS, 12/12 assertions** -- placement and recycling agree, rows stay
contiguous, every row keeps the same column count, pool counts never move, no
overlap, no blank region, zero console errors.

## 6. Tangent strength

Permitted only if 390x844's edge yaw still failed. It does (1.231 deg against
0.75), so the option was open -- and deliberately not taken. 390x844 fails four
checks, not one; a global tangent strength fitted with that viewport held out
cannot target its yaw, so it could not flip the verdict, and it carries a real
risk to 1440x900's yaw margin. `tangentStrength` stays at 1.0, which is
Candidate T unchanged.

## 7. Result

| | |
| --- | --- |
| Absolute Gate | **FAIL** — 5/6 |
| Landscape phase sweep | 35/39 against the runtime law |
| Long scroll | **PASS** |
| Runtime sessions | **PASS** |
| F0 regression | **PASS** 20/20 |
| Build | PASS |

Passing: 1100x720, 1366x768, 1440x900, 1920x1080, 844x390.
Failing: 390x844, on

- unclipped card height: 4.905 % against a limit of 3.0
- bottom edge slope: 1.231 deg against a limit of 0.75
- viewport centre in a horizontal gutter: False bool against a limit of True
- largest void blob excess: 2.423 % of frame against a limit of 2.0

**READY FOR EXPLICIT PRODUCT EXCEPTION REVIEW**, with one qualification the
category label would otherwise hide: this residual is not micro. Card height is
63% over its limit and the centre-dark-band check is a structural mismatch, not
a rounding margin. The exception being asked for is substantive, and it is
confined to one viewport.
