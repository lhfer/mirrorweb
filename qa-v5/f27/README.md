# qa-v5/f27 — initial row phase and portrait vertical axis

Status: **READY FOR EXPLICIT PRODUCT EXCEPTION REVIEW**, with the caveat stated
below. Full write-up: [`docs/v5/F27_ROW_PHASE_PORTRAIT_AXIS.md`](../../docs/v5/F27_ROW_PHASE_PORTRAIT_AXIS.md).

This directory holds LOCAL pixels and Target-derived NUMBERS only. Anything
embedding Target pixels is in `qa-v5/private/`, which is git-ignored.

## Headline

The authorised read-only source forensics pass recovered the Target's **entire**
layout initialisation, so both of this round's model questions were answered by
arithmetic rather than by another regression.

- **Initial scroll is (0, 0) at every viewport.** There is no integer row branch
  to unwrap; `originJ` is 0 everywhere. Residual phase 0.0007 world units.
- **The rest phase is the parity of the Target's pool row count**, which is
  forced even. `restOffsetX = (rows/2) % 2 === 0 ? cellW/2 : 0`. No threshold,
  no fitted constant. **36/36 viewports.**
- **Portrait needs one vertical scale, 1.03883.** Fitted in detector space;
  independently derived from source as 1.03923. Held-out 390x844 card-height
  error 4.79% -> 1.03%.
- **`restY0` must be exactly `-cellH/2`.** F2.5 fitted it to -200.99; that
  9-unit offset is the centre-dark-band failure. V2 fixes it in portrait.

## Files

| file | what it is |
| --- | --- |
| `target-phase-determinism.json` | 12 viewports x 5 cold loads. Phase, catalog codes, lattice and focal length stable in all 60. Model agreement 12/12. |
| `row-origin-model.json` | The brief's sweep with per-viewport `rawFittedScrollYCandidates`, `selectedUnwrappedScrollY`, `originJ`, parity, `residualPhaseY`, predicted vs Target brick phase and catalog row IDs. 36/36, zero unwrap discontinuities. |
| `portrait-vertical-models.json` | V0/V1/V2 per viewport: card width and height, row band centres, row heights, row pitch, edge yaw, centre dark band, held-out error. |
| `gate.json` | The candidate over the 14 mandatory viewports. 7/14 viewports, 107/118 checks. |
| `gate-control-f26r.json` | The F2.6R configuration measured **identically**, so the comparison is like for like. 7/14 viewports, 96/113 checks. |
| `gate-diagnostic-landscape-row-origin.json` | Diagnostic, NOT shipped: the landscape half of the `restY0` fix. 9/11 against 7/11, no regression anywhere. |
| `f0-regression.json` | 20/20. The v1 baseline frame is **byte-identical** to the accepted one. |
| `session/runtime-assertions.json` | 32/32 across resize, held-offset resize, +/-100 cell scroll, orientation flip and a row-count boundary crossing. |
| `local/` | Candidate frames and runtime state at all 14 gate viewports. |

## Instruments

`scripts/v5/f27-target-dom.mjs` reads the Target's CSS3D world transforms and
focal length directly, so grid geometry is observed in numbers rather than
inferred from pixels. `f27_target_model.py` and `src/scene/RowPhase.ts`
transcribe the Target's own layout function. `f27-dom-verify.py` checks the
transcription against live DOM state; `f27-row-origin.py` produces the sweep;
`f27-portrait-vertical.py` fits and cross-validates the vertical models with the
gate's own detector; `f27-runtime.mjs` runs the sessions.

## What still fails

- **Edge yaw** at 1100x720, 780x470, 390x844, 360x800. Structural: the Target's
  sphere radius follows `max(w, h)` while our world is fixed and scaled by width.
  Our frozen radius is 2.6% small at 1440x900 and **18.6% small at 390x844**.
  Not fixable without unfreezing `GRID.radius` and the portrait scale law.
- **Centre dark band** at 667x375, 700x700, 780x470. The landscape half of the
  `restY0` defect. Fix known, measured, and deliberately not shipped because
  F2.7 authorises a portrait-only vertical change.
- **Gutter width** at 780x470 and 500x900. Pre-existing.
- **Coverage holes** at 1920x1080 and 667x375: no row pair survives conditioning,
  so four contract items are NOT_MEASURED there. 1920x1080's PASS means "nothing
  measurable failed", not "everything was measured".

## Caveat on the status

The brief's class B is "390x844 has only a small non-structural residual and all
phases are correct". The phase clause holds — phase is now exact at 36/36
viewports and no phase mismatch remains. The residual clause does **not**: what
is left at 390x844 is structural, not a rounding residual, and its cause is a
frozen parameter. Class C is not triggered (no phase mismatch remains and the
390x844 centre band is now correct) and class A is not met.
