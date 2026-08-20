# MirrorWeb V5 — current status

Single canonical entry point. Every delivery updates this file.

Last updated: 2026-08-20T11:47:05Z

| | |
| --- | --- |
| Repository | `lhfer/mirrorweb` |
| Branch | `rebuild/liquid-glass-v5-foundation` |
| Current HEAD | the commit that ships this file, `v5-f25-joint-composition-evidence`. Resolve with `git rev-parse HEAD`. |
| Preview v1 | `http://127.0.0.1:5280/?optics=v4&composition=v1` |
| Preview v2 | `http://127.0.0.1:5280/?optics=v4&composition=v2&verticalMode=tangent` |
| Evidence index | [`qa-v5/f25/README.md`](../../qa-v5/f25/README.md) |
| Manifests | `qa-v5/<stage>/MANIFEST.json` |
| Private review package | `qa-v5/private/f25-review.zip` (git-ignored) |

## Commit ledger

**Accepted by product**
- `62f5772` `v5-f0-f1-accept` — F0/F1 Foundation baseline
- `b524dc5` `v5-f1-media-focus` — NL-03 focus 0.50 / 0.46, zoom 1.06

**Candidate, not accepted**
- `dd6d7bf` / `4ca597f` — F2 responsive scaling. Superseded by F2.5 but not deleted; still reachable at `?composition=v1`.
- `b5cff63` `v5-f2-audit-remediation`
- `730beb7` `v5-f3-vertical-curvature-diagnosis`
- `v5-f25-joint-composition-code` / `v5-f25-joint-composition-evidence` — this delivery

**Superseded / withdrawn**
- `qa-v5/f2/cross-validation.json` and the original `f2-crossval.py` — withdrawn as invalid (gain stored as scale, hold-out not held out).
- The F2 gate revision that replaced the 3 px absolute gutter threshold with a percentage.
- F3's `radiusY = -2053.4` — a diagnostic seed from a parabolic approximation. The joint fit lands near -4707.6005.

## Current stage

**F2.5 Joint Responsive & Vertical Composition Recovery.**
Typography, Motion, Optics: NOT STARTED.

## Verdicts

| | |
| --- | --- |
| Engineering result | **CANDIDATE FAILED ABSOLUTE GATE** |
| Absolute Target Gate | **FAIL** — 5/6 viewports pass (1100x720, 1366x768, 1440x900, 1920x1080, 844x390 pass; 390x844 fails) |
| Target visual result | Not asserted |
| F0 regression | **PASS** — 20/20 at 1440x900 |
| Runtime | **PASS** — 15/15 assertions in both resize sessions, offset preserved across 45 steps |
| Selected vertical mode | **tangent** (Candidate T), beating Candidate D 5/6 vs 3/6 on the gate |

Contract coverage:

```json
{
  "cardCentre": "PASS",
  "cardSize": "FAIL",
  "gutterPx": "FAIL",
  "edgeYaw": "FAIL",
  "rowParity": "PASS",
  "centreDarkBand": "PASS",
  "overlap": "PASS",
  "largeVoid": "FAIL",
  "f0Regression": "PASS"
}
```

## What this delivery established

- The **844x390 parity defect is fixed** and 844x390 now passes the full contract.
- **1440x900's 4 px gutter-width miss is gone**, improved naturally by the joint
  vertical model. `TILE.width`, `GRID.cellW` and the horizontal radius were not touched.
- **Candidate T beats Candidate D** decisively on the gate, 5/6 against 3/6.
- Portrait scale, refitted after the vertical candidate and cross-validated with
  390x844 held out: **+0.472%** with the aspect term against
  +1.059% without it. Landscape leave-one-out worst 0.322%.

## P0 / P1 / P2

**P0 — 390x844 still fails four contract items**, all by small margins: card
width 3.60% (limit 3), edge yaw 1.20 deg (limit 0.75), gutter centre 4 px
(limit 3), largest void excess 2.03% (limit 2). The portrait model is close but
not exact.

**P0 — the landscape rest-phase law is provisional.** The scale switch at 0.674
agrees with 4 of the nine required landscape viewports, and with three of
the five whose scale fit converged; 760x470 and 926x428 disagree. It ships
because it is strictly better than the v1 orientation split and it fixes the
gated 844x390, not because it is established. A denser Target sweep is needed.

**P1 — two Target scale fits do not converge** (320x900, and several in the
landscape sweep). They are excluded by a fixed RMS threshold, listed in the
JSON, and never allowed to steer a model.

**P1 — drag feel varies with viewport**; `dragGain` maps input px to world units
while world-to-screen no longer does. Motion is frozen.

**P1 — glass rim eats the gutter on yawed cards** (11 px rendered vs 19 px).

**P2 — cyan/magenta rim fringing; typography 9.2cqw vs 12cqw; TILE.radius 58 vs ~61.5.**

**P2 — `npm run v4:source` fails**, four checks from the baseline and three from
V5. Not re-baselined; that remains the product owner's call.

## Next stage

**Not authorised to start.** F2.5 has not passed the absolute gate. The
remaining work is portrait: the 390x844 residual and a denser landscape sweep to
settle the rest-phase law. Typography stays NOT STARTED.

## Frozen systems

Typography and TileLabelLayer visual parameters, MotionController,
InputController, MOTION, LiquidGlassMaterialV4, refraction, dispersion, blur,
reflection, environment, video focus and MediaFit, grid pool and recycling,
TILE.width, TILE.height, GRID.cellW, the horizontal radius, and the accepted F1
are all unchanged.
