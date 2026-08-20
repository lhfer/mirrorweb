# V5 Stage F2.5 — joint responsive and vertical composition recovery

Branch `rebuild/liquid-glass-v5-foundation`. Page `/?optics=v4`.
Reversible: the F2 candidate stays reachable at `?composition=v1`; this stage is
`?composition=v2`, with `&verticalMode=depth|tangent`.

## Why the parameters were solved together

Portrait scale, vertical depth and rest phase are coupled. The F2 procedure —
lock the portrait gain under a flat grid, then hand the leftover error to a
vertical radius — cannot distinguish "the grid curves" from "the scale is
slightly wrong", so it would have produced a confident wrong answer either way.

`scripts/v5/f25-joint-fit.py` solves one shared parameter set against every
viewport at once, with **no per-viewport freedom at all**, consuming the
independent measurements in `qa-v5/f2/target-measurements.json`. Nothing is
seeded from a previous stage's *result*: the F3 diagnostic `radiusY = -2053`
came from a parabolic approximation fitted to row heights alone, and once
gutters and band positions also have to be satisfied the joint fit lands at
about half that curvature. It was a seed, and it is not ground truth.

Held fixed by prior acceptance and not refitted: TILE, `GRID.cellW`, the
horizontal radius, and the landscape gain.

Observations are contaminated — a dark video frame can read as void and open a
gutter that is not there (1100x720 reports six gutters in a row that has two).
The fit therefore uses a robust `soft_l1` loss instead of anyone hand-picking
which observations are allowed to count, and reports median and p90 rather than
RMS alone.

## The two candidates

Both use the same exact cosine **depth** law — a row recedes with its vertical
distance from the axis and keeps its spacing. Neither touches the horizontal
curvature.

- **Candidate D, depth only.** Rows recede. Cards keep `rotX = 0`.
- **Candidate T, tangent.** Same depth law, plus `rotX = atan(sin(phi))`, the
  actual slope of the surface, so a card lies along it.

| | train median | train p90 | held-out 390x844 median | held-out p90 |
| --- | --- | --- | --- | --- |
| D | 1.432 px | 8.198 px | 1.863 px | 6.497 px |
| **T** | **1.125 px** | **6.3 px** | **1.373 px** | **4.515 px** |

The gate is the decider, and it is not close:

| viewport | Candidate D | **Candidate T** |
| --- | --- | --- |
| 1100x720 | FAIL | **PASS** |
| 1366x768 | PASS | **PASS** |
| 1440x900 | FAIL | **PASS** |
| 1920x1080 | PASS | **PASS** |
| 390x844 | FAIL | **FAIL** |
| 844x390 | PASS | **PASS** |

**Candidate T ships.** `?verticalMode=tangent` is the default; D stays reachable.

Fitted shared parameters for T:

```
radiusY                 -4707.6005      (exact cosine depth law)
cellH                   419.949
restY0                  -200.9942
portraitGainBase        1.9468
portraitGainAspectSlope -0.31
```

## Landscape rest phase and row parity

Derived, not special-cased. There is no `if (width === 844)` anywhere.

The canonical horizontal phase — `scrollX mod cellW`, folded once when
`scrollY` crosses a row so the two representations of one composition collapse
— is bimodal at 0 or half a cell. It does **not** separate on orientation: the
landscape 844x390 sits at half a cell and the portrait 700x900 at zero. The best
single rule the sweep supports is a switch on composition scale:

```
restOffsetX = (compositionScale < 0.674) ? cellW/2 : 0
```

**This rule is provisional and its limits are known.** Across the nine required
landscape viewports it agrees with 4 and disagrees with
5; restricted to the five whose scale fit converged it agrees
with three (800x425, 844x390, 1000x700) and disagrees with two (760x470,
926x428). It is shipped because it is strictly better than the v1 orientation
split and it fixes the gated 844x390 — not because it is established. A correct
law needs a denser sweep. See `qa-v5/f25/landscape-parity-law.json`.

The vertical phase needs no rule: one constant `restY0` covers everything, with
the canonical y phase measuring 196–226 across every viewport against
`cellH/2 = 210.2`.

## Portrait scale

Refitted **after** the vertical candidate was introduced, because the two are
coupled. Cross-validated on its own in `qa-v5/f25/cross-validation.json`,
trained on ['360x800', '414x896', '430x932', '390x700', '500x900', '700x900'] with 390x844 held out:

| model | held-out error | worst training error |
| --- | --- | --- |
| constant gain | +1.059% | 0.66% |
| **gain + aspect term** | **+0.472%** | **0.044%** |

The aspect term halves the held-out error, so it earns its one extra parameter.
Landscape leave-one-out worst error is 0.322%.

Note the two fits answer different questions and their slopes differ in sign:
the joint fit solves the gain *together with* vertical depth, while this
cross-validation fits it against flat-model measured scales. The shipped value
is the joint one. Viewports whose scale fit did not converge (RMS > 8 px) are
excluded and listed in the JSON — 1100x720, 320x900, 390x1000, 1170x2532, 414x896, 430x932, 700x900, 960x720 —
never silently dropped and never allowed to distort the model.

## Gate

Thresholds unchanged from the approved contract; nothing was relaxed.

**FAIL** — 5 of 6 viewports pass.
Contract coverage: `{"cardCentre": "PASS", "cardSize": "FAIL", "gutterPx": "FAIL", "edgeYaw": "FAIL", "rowParity": "PASS", "centreDarkBand": "PASS", "overlap": "PASS", "largeVoid": "FAIL", "f0Regression": "PASS"}`

1440x900's 4 px gutter-width miss from F2 is **gone**: the joint vertical model
improved it naturally, which is what the brief permitted. `TILE.width`,
`GRID.cellW` and the horizontal radius were not touched.

390x844 is the one failing viewport, and by small margins:

- unclipped card width: 3.597 % against a limit of 3.0
- bottom edge slope: 1.202 deg against a limit of 0.75
- gutter centre: 4.0 px against a limit of 3.0
- largest void blob excess: 2.031 % of frame against a limit of 2.0

F0 regression: **PASS**, 20/20 at 1440x900.
Runtime: **PASS**, 15/15 assertions in both sessions across 45 resize
steps with the offset preserved.

## Status

**CANDIDATE FAILED ABSOLUTE GATE**
