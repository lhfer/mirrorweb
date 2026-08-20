# MirrorWeb V5 — current status

Single canonical entry point. Every delivery updates this file.

Last updated: 2026-08-20T12:37:02Z

| | |
| --- | --- |
| Repository | `lhfer/mirrorweb` |
| Branch | `rebuild/liquid-glass-v5-foundation` |
| Current HEAD | the commit that ships this file, `v5-f26-composition-evidence`. Resolve with `git rev-parse HEAD`. |
| Preview v1 | `http://127.0.0.1:5280/?optics=v4&composition=v1` |
| Preview candidate | `http://127.0.0.1:5280/?optics=v4&composition=v2&verticalMode=tangent&portraitLaw=p1` |
| Evidence index | [`qa-v5/f26/README.md`](../../qa-v5/f26/README.md) |
| Private review package | `qa-v5/private/f26-review.zip` (git-ignored) |

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

## Verdicts

| | |
| --- | --- |
| Engineering result | **READY FOR EXPLICIT PRODUCT EXCEPTION REVIEW** |
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

Composition engineering is closed per the F2.6 brief. The open decision is
whether to grant 390x844 an explicit exception or reopen composition. Typography,
Motion and Optics remain **NOT STARTED** and are not authorised.

## Frozen systems

Typography and TileLabelLayer visual parameters, MotionController,
InputController, MOTION, LiquidGlassMaterialV4, refraction, dispersion, blur,
reflection, environment, video focus and MediaFit, grid pool structure,
TILE.width, TILE.height, GRID.cellW, the horizontal radius, and the accepted F1
are all unchanged.
