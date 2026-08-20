# MirrorWeb V5 — current status

Single canonical entry point. Every delivery updates this file.

Last updated: 2026-08-20T10:59:34Z

| | |
| --- | --- |
| Repository | `lhfer/mirrorweb` |
| Branch | `rebuild/liquid-glass-v5-foundation` |
| Current HEAD | the commit that ships this file, `v5-f3-vertical-curvature-diagnosis`. A file cannot contain its own hash; resolve with `git rev-parse HEAD`. Its parent is `b5cff63` `v5-f2-audit-remediation`. |
| Preview URL | `http://127.0.0.1:5280/?optics=v4` — layout view `&foundation=layout&annotate=0` |
| Evidence index | [`qa-v5/f2/README.md`](../../qa-v5/f2/README.md), [`qa-v5/f3-diagnosis/README.md`](../../qa-v5/f3-diagnosis/README.md) |
| Manifests | `qa-v5/<stage>/MANIFEST.json` |
| Private review package | `qa-v5/private/f2-audit-review.zip` (git-ignored) |

## Commit ledger

**Accepted by product**
- `62f5772` `v5-f0-f1-accept` — F0/F1 Foundation baseline
- `b524dc5` `v5-f1-media-focus` — NL-03 focus 0.50 / 0.46, zoom 1.06

**Candidate, not accepted**
- `dd6d7bf` `v5-f2-responsive-scaling-code`
- `4ca597f` `v5-f2-responsive-scaling-evidence`
- `b5cff63` `v5-f2-audit-remediation` — this delivery, evidence only
- `v5-f3-vertical-curvature-diagnosis` — this delivery, diagnosis only

**Superseded / withdrawn**
- `qa-v5/f2/cross-validation.json` and `scripts/v5/f2-crossval.py` — **withdrawn as invalid.**
  The table labelled "scale" held the *gain* 1.8975, which was then divided by
  width/1440 as though it were a scale. Every portrait viewport therefore
  reported the same measuredScale, and 390x844 — documented as held out — was in
  the table. Replaced by `cross-validation-v2.json`.
- The F2 gate revision that replaced the contract's absolute 3 px gutter
  threshold with 0.6% of viewport width, and scored a `missing bands` check the
  contract does not contain. The approved contract is restored in
  `scripts/v5/f2-gate.py`.

## Current stage

**F2 Responsive Composition Scaling — audit remediation delivered, candidate still open.**
F3 vertical curvature — **diagnosis only**, no product code.

## Verdicts

| | |
| --- | --- |
| Engineering result | **BLOCKED — EVIDENCE INSUFFICIENT** |
| Absolute Target Gate | **FAIL** — failing contract items: cardCentre, gutterPx, rowParity; NOT_MEASURED: cardSize, edgeYaw |
| Target visual result | Not asserted. Composition matches within contract at four of six viewports; two do not. |
| F0 regression | **PASS** — the accepted baseline still passes 20/20 at 1440x900 |
| Runtime (resize) | **PASS** — 15/15 assertions in both sessions, offset preserved across 45 steps |

### Contract coverage

```json
{
  "cardCentre": "FAIL",
  "cardSize": "NOT_MEASURED",
  "gutterPx": "FAIL",
  "edgeYaw": "NOT_MEASURED",
  "rowParity": "FAIL",
  "centreDarkBand": "PASS",
  "overlap": "PASS",
  "largeVoid": "PASS",
  "f0Regression": "PASS"
}
```

## What the remediation established

- **Orientation switch is real.** Measured 1 px either side of square at two
  corners: gain 1.807 portrait vs 0.983 landscape at 900, 1.806 vs 0.982 at 700
  — a 1.8385x step across one pixel. A square takes the
  **landscape** side, which is what the shipped rule does. No other breakpoint
  between aspect 0.53 and 1.88. It is a scale step, not merely a rest-offset or
  parity change.
- **Cross-validation, done properly.** Landscape gain 1.00288,
  leave-one-out worst error **0.404%**. Portrait trained on
  ['360x800', '414x896', '430x932'] gives gain **1.86361**; the genuinely
  held-out 390x844 predicts to **+0.444%**.
- **The shipped portrait gain is wrong by 1.8%.** Shipped 1.8975,
  cross-validated 1.86361. Not corrected here: this delivery
  may not change product rendering.
- **Portrait gain is not constant.** It drifts from 1.880 at aspect 0.53 to
  1.806 near square. A single constant is an approximation.

## P0 / P1 / P2

**P0 — vertical grid curvature is missing from the baseline.** Target outer rows
are 10-13% shorter than inner ones at tall viewports. Diagnosis complete: a
dual-axis model (M1, `radiusY ≈ 2053.4186`) halves the
residual on training *and* on a held-out viewport (4.908 px vs
4.968 px), while the camera-pitch alternative barely beats
doing nothing. Fixing it reopens the accepted F0 baseline and needs an explicit
product decision. See [VERTICAL_CURVATURE_DIAGNOSIS.md](VERTICAL_CURVATURE_DIAGNOSIS.md).

**P0 — row parity is wrong at 844x390.** The Target's two rows carry the opposite
brick parity to ours at that viewport, while 1440x900, 1366x768, 1920x1080 and
1100x720 all match. The vertical rest offset is viewport-dependent in a way one
constant `restY0` does not reproduce. Rest offset **is** inside F2's permitted
edits, so this is an F2 defect, not an F3 one.

**P1 — shipped portrait gain 1.8975 vs cross-validated 1.8636.**

**P1 — gutter width misses the 3 px contract by 1 px at 1440x900** (target 14/22,
local 18/22) and by 3 px at 390x844.

**P1 — drag feel now varies with viewport**; `dragGain` maps input px to world
units while world-to-screen no longer does. Motion is frozen.

**P1 — glass rim eats the gutter on yawed cards** (11 px rendered vs 19 px).

**P2 — portrait gain has a real aspect dependence** (1.880 to 1.806).

**P2 — 320x900 scale fit does not converge** (+40% ). Excluded from
conclusions and reported rather than hidden.

**P2 — cyan/magenta rim fringing; typography 9.2cqw vs 12cqw; TILE.radius 58 vs ~61.5.**

**P2 — `npm run v4:source` fails**, four checks from the baseline and three from
V5. Not re-baselined; that remains the product owner's call.

## Next stage

**Not authorised to start.** F2 is not accepted, and two P0 items are open. The
recommended order is: fix the 844x390 rest-offset parity inside F2, re-run the
contract gate, and only then decide whether to reopen the F0 baseline for F3.

## Frozen systems

Typography, MotionController, InputController, MOTION, LiquidGlassMaterialV4,
refraction, dispersion, blur, reflection, environment, grid recycling, video
focus, the accepted F0 parameters, and the V4 source contract are all unchanged.
