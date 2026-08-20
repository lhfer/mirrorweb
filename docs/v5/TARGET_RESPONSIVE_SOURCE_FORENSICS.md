# Target responsive source forensics (F2.7, read-only)

Stage F2.7 authorised one read-only forensics pass over the Target's shipped
JavaScript, with instructions to prefer source facts over further regression
guessing if an exact initialisation formula could be found.

**One was found — the whole of it.** This document records what the Target does.
No Target code is copied into this repository, nothing was modified, and nothing
was republished. Bundles were fetched to `artifacts/`, which is git-ignored.

## Provenance

Fetched 2026-08-20 from `https://infinite-liquid-glass.shader.se/?v=2`.

| bundle | SHA-256 |
| --- | --- |
| `_next/static/immutable/chunks/03lo820gl57km.js` (app, 2.0 MB) | `4983307288d9e6c544751d1f969a0bc5c4fdb86ebbe5c93ee97aa74ceb0b3754` |
| `_next/static/immutable/chunks/3r5716256bwc-.js` | `4f52109529c6eb6523339a330825b1ee58495d17feb1b5cbcbb40a828911b05c` |
| `_next/static/immutable/chunks/1s19wbg2gjkv0.js` | `1e3ab0d8a23109ef8d66a856fade259c84fc24b292a592d3c221d245f9e1ac9b` |
| `_next/static/immutable/chunks/0w2iwebs5-c-n.js` | `588e974ee815caa67cf8c99720b10aa44f94caed5fda4cb80d749569f019f7d0` |
| `_next/static/immutable/chunks/2c5x84gieuvai.js` | `2e7f40b2884bba4c8c1a660127354c9b4853c500088f820c887c03db461681ef` |
| `_next/static/immutable/chunks/2l6r176tw29k7.js` | `bbbc1a25996cf2776b4e1d9e6b734bb93893100e439fd97ef216c3c2d2899d4d` |
| `_next/static/immutable/chunks/1xaeaw6ztv3gm.js` | `af4cdb98b480c02123a996babd29cee1f6d07704bae76252960342844098f2f7` |
| `_next/static/immutable/chunks/2fxvkdsdfb39m.js` | `1ab1f44ac0599703e4abfea614f37c4c19859f1e999ca81663dbd080c16da350` |
| `_next/static/immutable/chunks/25kvgcvbp6c14.js` | `8a943b00599e56b53569f36f4341e3465ae7705c1391562cd6c7e1f290c0c387` |
| `_next/static/immutable/chunks/turbopack-1pkwdr4knmj6d.js` | `c2c24fbf5e8cfb98601e39e5e96ca0283ee9a070970b381263225f8a0bded9cc` |

A second, independent channel confirms all of it: the Target renders its
typography with a CSS3D layer, so every card carries its **world transform** as
a computed `matrix3d`, the container carries the CSS `perspective`, and both are
readable with `getComputedStyle`. `scripts/v5/f27-target-dom.mjs` reads them.
Source and live DOM agree to 0.005 world units.

## The grid configuration

```
perspective 1200   sphereRadius 5000   planeAspect 4/3
planeWidthRatio 0.38   planeWidthRatioPortrait 0.72
gapRatio 0.045   referenceWidth 1728   coverageMargin 1.15
minCols 4  maxCols 16   minRows 4  maxRows 16
```

## The layout law

```
s            = max(width, height) / 1728
perspective  = 1200 * s
sphereRadius = 5000 * s
planeWidth   = width * (height > width ? 0.72 : 0.38)
planeHeight  = planeWidth / (4/3)
cellW        = planeWidth  * 1.045
cellH        = planeHeight * 1.045
cols, rows   = coverage bisection, clamped to [4,16], forced EVEN
```

Camera: position `(0, 0, perspective)` looking at the origin,
`fov = 2*atan(height/2/perspective)`, `near 0.1`, `far 1e4`. At rest the pointer
parallax is zero and **there is no pitch** — the camera sits exactly on the axis.

Placement, per pool slot, is on a **sphere**, not a cylinder:

```
xArc = wrap((col - (cols-1)/2) * cellW + scrollX + (poolRow % 2) * cellW/2, cols*cellW)
yArc = wrap(-(poolRow - (rows-1)/2) * cellH - scrollY,                      rows*cellH)
θx = xArc/R,  θy = yArc/R
position = ( R sinθx cosθy , R sinθy , R cosθx cosθy - R )
orientation = the rotation taking +Z to that unit vector
```

`scripts/v5/f27_target_model.py` and `src/scene/RowPhase.ts` are transcriptions
of exactly this.

## What it settles

**1. The initial scroll is (0, 0) at every viewport.** Both scroll springs are
constructed at zero and nothing seeds them. There is no viewport-dependent
initial offset, no integer row branch to unwrap, and `originJ` is 0 everywhere.
F2.7's phase-unwrapping brief was aimed at a quantity that does not exist.

**2. The rest phase is pool-row parity, not aspect ratio.** Row counts are
forced EVEN, so the viewport centre falls between two pool rows and the lower
one is `rows/2`. Odd pool rows carry the half-cell brick offset. That single
parity is the entire phase law — no threshold, no breakpoint, no free parameter.
Verified 12/12 against live DOM state.

**3. The responsive law is `max(width, height)`, and it is continuous.** The
orientation "hard switch" that F2 recorded as a 1.84x step at `width == height`
does not exist in the Target: `max` is continuous there. What *does* switch
discontinuously is `planeWidthRatio`, 0.38 to 0.72 — the cards get bigger
relative to the viewport in portrait, while the sphere and the focal length keep
following `max(w, h)`.

**4. That is why one composition scale cannot fit portrait.** Card size follows
`width`; sphere radius and focal length follow `max(width, height)`. Their ratio
is constant in landscape and is not in portrait, so the portrait composition is
a different SHAPE, not the same shape at a different scale. At 390x844 the
Target's sphere-to-card ratio is 8.70 against 7.61 in landscape. No value of a
single `S` reproduces that, which is the real reason 390x844 has failed the gate
in every round since F2.

**5. Vertical and horizontal curvature are the same radius.** It is one sphere.
Our model fits them separately (`radius -4058.94`, `radiusY -4707.6`) and lacks
the `cosθy` coupling on x and the `sin` on y that a sphere has.

**6. Video assignment is random; geometry is not.** The clip list is shuffled
with `Math.random()` on load, so which video lands in which cell differs every
time. Nothing geometric is random. This is why multi-frame consensus masking was
necessary and it is the only non-determinism in the Target.

**7. Catalog labels are bound to the POOL SLOT, not to a world cell.** `ILG—NN`
is `slotIndex + 1`, padded. A card keeps its number as it wraps, and the pool
resizes with the viewport, so Target catalog content is not a stable function of
world position. Our `catalogAt(i, j)` binds to the world cell instead. That is a
typography-layer difference, frozen this round, recorded here.

## Numbers our frozen parameters disagree with

Measured at 1440x900, where our composition scale is 1 by definition:

| quantity | ours | Target | delta |
| --- | --- | --- | --- |
| card width | `TILE.width` 539.8 | 547.20 | −1.35% |
| card height | `TILE.height` 399.6 | 410.40 | −2.63% |
| card aspect | 1.3508 | 1.33333 | +1.31% |
| cell pitch X | `GRID.cellW` 561.14 | 571.824 | −1.87% |
| cell pitch Y | `cellH` 419.95 | 428.868 | −2.08% |
| curvature radius | `GRID.radius` −4058.94 | ±4166.67 | −2.59% |
| row origin | `restY0` −200.99 | −cellH/2 = −214.434 | +6.3% |
| camera pitch | `CAMERA.y` 8 | 0 | — |

`TILE.width`, `TILE.height`, `GRID.cellW`, the horizontal radius and both scale
laws are frozen by the F2.7 brief, so none of these were changed this round.
They are recorded so the product owner can decide whether to unfreeze them.
