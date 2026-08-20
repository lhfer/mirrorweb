# MirrorWeb V5 — current status

Single canonical entry point. Every delivery updates this file.

Last updated: 2026-08-20T12:37:02Z (metadata hygiene pass `v5-f26r-metadata-hygiene`)

| | |
| --- | --- |
| Repository | `lhfer/mirrorweb` |
| Branch | `rebuild/liquid-glass-v5-foundation` |
| Current HEAD | `e33149992e4e69cd483428c38decf4248d7875d5` (`v5-f26r-corrected-evidence`) at the time this row was written. Resolve the live value with `git rev-parse HEAD`. |
| F2.6R code fix commit | `23de9c7` `v5-f26r-portrait-law-propagation` |
| F2.6R evidence commit | `e331499` `v5-f26r-corrected-evidence` |
| F2.6R corrected candidate gate | **FAIL** — p0 5/6, p1 5/6, p2 4/6 |
| F2.6 original candidate comparison | **INVALID** — `qa-v5/f26/portrait-candidate-gates.json` compared one candidate with itself |
| Preview v1 | `http://127.0.0.1:5280/?optics=v4&composition=v1` |
| Preview candidate | `http://127.0.0.1:5280/?optics=v4&composition=v2&verticalMode=tangent&portraitLaw=p1` |
| Evidence index | [`qa-v5/f26r/README.md`](../../qa-v5/f26r/README.md) (supersedes f26 for the candidate comparison) |
| Private review package | `qa-v5/private/f26r-review.zip` (git-ignored) |

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

## Verdicts

| | |
| --- | --- |
| Engineering result | **READY FOR PRODUCT REVIEW AFTER EVIDENCE CORRECTION** |
| Absolute Target Gate | **FAIL** — 5/6. Passing: 1100x720, 1366x768, 1440x900, 1920x1080, 844x390. Failing: 390x844. |
| Landscape phase sweep | 35/39 against the runtime law |
| Long scroll runtime | **PASS** 12/12 |
| Resize runtime | **PASS** 15/15 in both sessions |
| Model vs engine | **0.0 px** worst corner, both phases and modes |
| F0 regression | **PASS** 20/20 |
| Build | PASS |
| Target visual result | Not asserted |

Contract coverage:

```json
{
  "cardCentre": "PASS",
  "cardSize": "FAIL",
  "gutterPx": "PASS",
  "edgeYaw": "FAIL",
  "rowParity": "PASS",
  "centreDarkBand": "FAIL",
  "overlap": "PASS",
  "largeVoid": "FAIL",
  "f0Regression": "PASS"
}
```

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
composition   v2      verticalMode tangent      portraitLaw p1
radiusY -4707.6   cellH 419.95   restY0 -200.99
portraitGain  1.87715 + 0.12204 * (aspect - 0.5)
landscapeScale S = width / 1440
restOffsetX   (portrait || height < 0.5525 * width) ? cellW/2 : 0
tangentStrength 1.0
```

Every number above appears verbatim in `qa-v5/f26/portrait-crossval.json` or
`qa-v5/f26/landscape-phase.json`.

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

Product decision on F2.6R: harness and evidence integrity **accepted**; P1 kept
as the working candidate; **no 390x844 exception granted**; the aspect phase
rule **not accepted** as the final responsive law. One narrow **F2.7** is
authorised — initial row phase and portrait vertical axis only — and no F2.8
follows it. Typography, Motion and Optics remain **NOT STARTED**.

## Frozen systems

Typography and TileLabelLayer visual parameters, MotionController,
InputController, MOTION, LiquidGlassMaterialV4, refraction, dispersion, blur,
reflection, environment, video focus and MediaFit, grid pool structure,
TILE.width, TILE.height, GRID.cellW, the horizontal radius, and the accepted F1
are all unchanged.
